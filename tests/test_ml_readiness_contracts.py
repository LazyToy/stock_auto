from datetime import datetime

import numpy as np
import pandas as pd
from unittest.mock import MagicMock


def _sample_ohlcv_data(rows: int = 220) -> pd.DataFrame:
    np.random.seed(7)
    dates = pd.date_range(start="2024-01-01", periods=rows, freq="D")
    base = 50000 + np.cumsum(np.random.randn(rows) * 300)
    high = base + np.abs(np.random.randn(rows) * 150)
    low = base - np.abs(np.random.randn(rows) * 150)
    open_price = base + np.random.randn(rows) * 50
    volume = np.random.randint(100000, 1000000, rows)
    return pd.DataFrame(
        {
            "date": dates,
            "open": open_price,
            "high": high,
            "low": low,
            "close": base,
            "volume": volume,
        }
    )


def test_random_forest_save_and_load_roundtrip(tmp_path):
    from src.strategies.ml_strategy import RandomForestStrategy

    strategy = RandomForestStrategy(n_estimators=10)
    data = _sample_ohlcv_data()
    accuracy = strategy.train(data)
    assert strategy.is_trained is True
    assert 0.0 <= accuracy <= 1.0

    model_path = tmp_path / "rf_model.pkl"
    strategy.save_model(str(model_path))
    assert model_path.exists()

    restored = RandomForestStrategy(n_estimators=10)
    restored.load_model(str(model_path))

    prediction = restored.predict(data)
    assert restored.is_trained is True
    assert prediction.model_name == "RandomForest"
    assert prediction.signal in [-1, 0, 1]


def test_prepare_features_without_labels_keeps_latest_predictable_row():
    from src.strategies.ml_strategy import RandomForestStrategy

    strategy = RandomForestStrategy(n_estimators=10)
    data = _sample_ohlcv_data()

    labeled_x, labeled_y = strategy.prepare_features(data, include_labels=True)
    predict_x, predict_y = strategy.prepare_features(data, include_labels=False)

    assert labeled_y is not None
    assert predict_y is None
    assert len(predict_x) >= len(labeled_x)
    assert len(predict_x) - len(labeled_x) <= 5


def test_technical_features_do_not_leak_across_symbol_boundaries():
    from src.strategies.ml_strategy import FeatureEngineering

    df = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "BBB", "BBB"],
            "date": pd.date_range(start="2024-01-01", periods=4, freq="D"),
            "open": [100.0, 110.0, 1000.0, 1010.0],
            "high": [101.0, 111.0, 1001.0, 1011.0],
            "low": [99.0, 109.0, 999.0, 1009.0],
            "close": [100.0, 110.0, 1000.0, 1010.0],
            "volume": [1000, 1100, 2000, 2100],
        }
    )

    result = FeatureEngineering.add_technical_features(df)

    first_bbb = result[result["symbol"] == "BBB"].iloc[0]
    assert pd.isna(first_bbb["return_1d"])


def test_create_labels_drops_forward_window_per_symbol():
    from src.strategies.ml_strategy import FeatureEngineering

    dates = pd.date_range(start="2024-01-01", periods=6, freq="D")
    df = pd.DataFrame(
        {
            "symbol": ["AAA"] * 6 + ["BBB"] * 6,
            "date": list(dates) + list(dates),
            "open": [100, 101, 102, 103, 104, 105, 200, 201, 202, 203, 204, 205],
            "high": [101, 102, 103, 104, 105, 106, 201, 202, 203, 204, 205, 206],
            "low": [99, 100, 101, 102, 103, 104, 199, 200, 201, 202, 203, 204],
            "close": [100, 101, 102, 103, 104, 105, 200, 201, 202, 203, 204, 205],
            "volume": [1000] * 12,
        }
    )

    labeled = FeatureEngineering.create_labels(df, forward_days=2, threshold=0.01)

    counts = labeled.groupby("symbol").size().to_dict()
    assert counts == {"AAA": 4, "BBB": 4}


def test_generate_signals_maps_batch_predictions_back_to_time_series():
    from src.strategies.ml_strategy import RandomForestStrategy

    strategy = RandomForestStrategy(n_estimators=10)
    strategy.is_trained = True
    strategy.feature_columns = strategy.get_feature_names()
    strategy.scaler = MagicMock()
    strategy.scaler.transform.side_effect = lambda values: values
    strategy.model = MagicMock()
    strategy.model.predict.return_value = np.array([1, -1, 0])

    feature_frame = pd.DataFrame(
        {
            feature_name: [0.1, 0.2, 0.3]
            for feature_name in strategy.feature_columns
        },
        index=[2, 3, 4],
    )
    strategy.prepare_feature_frame = MagicMock(return_value=feature_frame)

    result = strategy.generate_signals(_sample_ohlcv_data(rows=5))

    assert result["signal"].tolist() == [0, 0, 1, -1, 0]
