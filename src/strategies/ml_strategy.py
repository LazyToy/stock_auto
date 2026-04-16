"""Machine-learning based trading strategies."""

from __future__ import annotations

import logging
import os
from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

from src.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)

try:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    StandardScaler = None  # type: ignore[assignment]
    logger.warning("scikit-learn is not installed. Run: pip install scikit-learn")

try:
    import torch
    import torch.nn as nn

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    logger.warning("PyTorch is not installed. Run: pip install torch")

try:
    from src.mlops.mlflow_manager import MLflowManager

    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    MLflowManager = None  # type: ignore[assignment]

try:
    from src.strategies.adaptive_strategy import AdaptiveStrategy

    ADAPTIVE_AVAILABLE = True
except ImportError:
    ADAPTIVE_AVAILABLE = False
    AdaptiveStrategy = None  # type: ignore[assignment]


@dataclass
class MLPrediction:
    signal: int
    probability: float
    features_used: List[str]
    model_name: str
    timestamp: str


class FeatureEngineering:
    """Feature helpers shared by the ML strategies."""

    @staticmethod
    def _apply_per_symbol(df: pd.DataFrame, builder) -> pd.DataFrame:
        if "symbol" not in df.columns:
            return builder(df)

        grouped = [builder(group.copy()) for _, group in df.groupby("symbol", sort=False)]
        return pd.concat(grouped).sort_index()

    @staticmethod
    def add_technical_features(df: pd.DataFrame) -> pd.DataFrame:
        def _builder(frame: pd.DataFrame) -> pd.DataFrame:
            frame = frame.copy()

            for period in [5, 10, 20, 50]:
                frame[f"ma_{period}"] = frame["close"].rolling(window=period).mean()
                frame[f"ma_{period}_ratio"] = frame["close"] / frame[f"ma_{period}"]

            delta = frame["close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            frame["rsi"] = 100 - (100 / (1 + rs))

            exp12 = frame["close"].ewm(span=12, adjust=False).mean()
            exp26 = frame["close"].ewm(span=26, adjust=False).mean()
            frame["macd"] = exp12 - exp26
            frame["macd_signal"] = frame["macd"].ewm(span=9, adjust=False).mean()
            frame["macd_hist"] = frame["macd"] - frame["macd_signal"]

            frame["bb_middle"] = frame["close"].rolling(window=20).mean()
            bb_std = frame["close"].rolling(window=20).std()
            frame["bb_upper"] = frame["bb_middle"] + (bb_std * 2)
            frame["bb_lower"] = frame["bb_middle"] - (bb_std * 2)
            frame["bb_width"] = (frame["bb_upper"] - frame["bb_lower"]) / frame["bb_middle"]
            frame["bb_position"] = (frame["close"] - frame["bb_lower"]) / (
                frame["bb_upper"] - frame["bb_lower"]
            )

            frame["volume_ma10"] = frame["volume"].rolling(window=10).mean()
            frame["volume_ratio"] = frame["volume"] / frame["volume_ma10"]

            for period in [1, 3, 5, 10]:
                frame[f"return_{period}d"] = frame["close"].pct_change(period)

            high_low = frame["high"] - frame["low"]
            high_close = np.abs(frame["high"] - frame["close"].shift())
            low_close = np.abs(frame["low"] - frame["close"].shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            frame["atr"] = tr.rolling(window=14).mean()
            frame["atr_ratio"] = frame["atr"] / frame["close"]
            return frame

        return FeatureEngineering._apply_per_symbol(df, _builder)

    @staticmethod
    def create_labels(
        df: pd.DataFrame, forward_days: int = 5, threshold: float = 0.02
    ) -> pd.DataFrame:
        def _builder(frame: pd.DataFrame) -> pd.DataFrame:
            frame = frame.copy()
            frame["future_return"] = frame["close"].shift(-forward_days) / frame["close"] - 1
            frame["label"] = 0
            frame.loc[frame["future_return"] > threshold, "label"] = 1
            frame.loc[frame["future_return"] < -threshold, "label"] = -1
            if forward_days > 0:
                frame = frame.iloc[:-forward_days]
            return frame

        return FeatureEngineering._apply_per_symbol(df, _builder)


class MLStrategy(BaseStrategy):
    """Base class for ML strategies."""

    def __init__(self, name: str = "MLStrategy", lookback: int = 60):
        super().__init__(name)
        self.lookback = lookback
        self.model = None
        self.scaler = StandardScaler() if SKLEARN_AVAILABLE else None
        self.feature_columns: List[str] = []
        self.is_trained = False
        self.mlflow = MLflowManager() if MLFLOW_AVAILABLE else None

    def get_feature_importances(self) -> Dict[str, float]:
        return {}

    def get_feature_names(self) -> List[str]:
        return [
            "ma_5_ratio",
            "ma_10_ratio",
            "ma_20_ratio",
            "ma_50_ratio",
            "rsi",
            "macd",
            "macd_hist",
            "bb_width",
            "bb_position",
            "volume_ratio",
            "return_1d",
            "return_3d",
            "return_5d",
            "atr_ratio",
        ]

    def prepare_feature_frame(
        self, df: pd.DataFrame, include_labels: bool = True
    ) -> pd.DataFrame:
        frame = FeatureEngineering.add_technical_features(df)
        if include_labels:
            frame = FeatureEngineering.create_labels(frame)

        self.feature_columns = self.get_feature_names()
        required_columns = list(self.feature_columns)
        if include_labels:
            required_columns.append("label")
        frame = frame.dropna(subset=required_columns)
        return frame

    def prepare_features(
        self, df: pd.DataFrame, include_labels: bool = True
    ) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        frame = self.prepare_feature_frame(df, include_labels=include_labels)
        x = frame[self.feature_columns].values
        y = frame["label"].values if include_labels and "label" in frame.columns else None
        return x, y

    def save_model(self, filepath: str):
        if self.model is None:
            return

        payload = {
            "model": self.model,
            "scaler": self.scaler,
            "feature_columns": self.feature_columns,
            "is_trained": self.is_trained,
            "lookback": self.lookback,
            "name": self.name,
        }
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        joblib.dump(payload, filepath)

    def load_model(self, filepath: str):
        if not os.path.exists(filepath):
            return

        payload = joblib.load(filepath)
        self.model = payload.get("model")
        self.scaler = payload.get("scaler", self.scaler)
        self.feature_columns = payload.get("feature_columns", self.feature_columns)
        self.is_trained = payload.get("is_trained", False)
        self.lookback = payload.get("lookback", self.lookback)

    @abstractmethod
    def train(self, df: pd.DataFrame) -> float:
        pass

    def log_to_mlflow(self, metrics: Dict[str, float], params: Dict[str, Any] | None = None):
        if not self.mlflow:
            return
        try:
            with self.mlflow.start_run(run_name=f"{self.name}_Training"):
                if params:
                    self.mlflow.log_params(params)
                self.mlflow.log_metrics(metrics)
                if self.model is not None:
                    self.mlflow.log_model(self.model, "model")
        except Exception as exc:
            logger.error("MLflow logging failed: %s", exc)

    @abstractmethod
    def predict(self, df: pd.DataFrame) -> MLPrediction:
        pass

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.is_trained:
            result = df.copy()
            result["signal"] = 0
            return result

        result = df.copy()
        prediction = self.predict(df)
        result["signal"] = 0
        result.iloc[-1, result.columns.get_loc("signal")] = prediction.signal
        return result


class RandomForestStrategy(MLStrategy):
    def __init__(self, n_estimators: int = 100, lookback: int = 60):
        super().__init__(name="RandomForest", lookback=lookback)
        self.n_estimators = n_estimators
        self.parameters = {"n_estimators": n_estimators, "max_depth": 10}
        if SKLEARN_AVAILABLE:
            self.model = RandomForestClassifier(
                n_estimators=n_estimators,
                max_depth=10,
                random_state=42,
                n_jobs=1,
            )

    def train(self, df: pd.DataFrame) -> float:
        if not SKLEARN_AVAILABLE:
            return 0.0

        x, y = self.prepare_features(df)
        if len(x) < 100 or y is None:
            logger.warning("Not enough data to train RandomForest")
            return 0.0

        x_train, x_test, y_train, y_test = train_test_split(
            x, y, test_size=0.2, shuffle=False
        )
        x_train_scaled = self.scaler.fit_transform(x_train)
        x_test_scaled = self.scaler.transform(x_test)

        self.model.fit(x_train_scaled, y_train)
        accuracy = self.model.score(x_test_scaled, y_test)
        self.is_trained = True
        self.log_to_mlflow({"accuracy": accuracy}, self.parameters)
        return accuracy

    def get_feature_importances(self) -> Dict[str, float]:
        if not self.is_trained or self.model is None:
            return {}
        return dict(
            sorted(
                zip(self.feature_columns, self.model.feature_importances_),
                key=lambda item: item[1],
                reverse=True,
            )
        )

    def predict(self, df: pd.DataFrame) -> MLPrediction:
        if not self.is_trained:
            return MLPrediction(0, 0.0, [], "RandomForest", datetime.now().isoformat())

        frame = self.prepare_feature_frame(df, include_labels=False)
        if frame.empty:
            return MLPrediction(0, 0.0, [], "RandomForest", datetime.now().isoformat())

        x_last = frame[self.feature_columns].iloc[[-1]].values
        x_scaled = self.scaler.transform(x_last)
        pred = int(self.model.predict(x_scaled)[0])
        proba = self.model.predict_proba(x_scaled)[0]
        return MLPrediction(
            signal=pred,
            probability=float(max(proba)),
            features_used=self.feature_columns,
            model_name="RandomForest",
            timestamp=datetime.now().isoformat(),
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        result = df.copy()
        result["signal"] = 0
        if not self.is_trained:
            return result

        frame = self.prepare_feature_frame(df, include_labels=False)
        if frame.empty:
            return result

        x_scaled = self.scaler.transform(frame[self.feature_columns].values)
        result.loc[frame.index, "signal"] = self.model.predict(x_scaled).astype(int)
        return result


class GradientBoostingStrategy(MLStrategy):
    def __init__(self, n_estimators: int = 100, lookback: int = 60):
        super().__init__(name="GradientBoosting", lookback=lookback)
        self.n_estimators = n_estimators
        self.parameters = {
            "n_estimators": n_estimators,
            "max_depth": 5,
            "learning_rate": 0.1,
        }
        if SKLEARN_AVAILABLE:
            self.model = GradientBoostingClassifier(
                n_estimators=n_estimators,
                learning_rate=0.1,
                random_state=42,
            )

    def train(self, df: pd.DataFrame) -> float:
        if not SKLEARN_AVAILABLE:
            return 0.0

        x, y = self.prepare_features(df)
        if len(x) < 100 or y is None:
            logger.warning("Not enough data to train GradientBoosting")
            return 0.0

        x_train, x_test, y_train, y_test = train_test_split(
            x, y, test_size=0.2, shuffle=False
        )
        x_train_scaled = self.scaler.fit_transform(x_train)
        x_test_scaled = self.scaler.transform(x_test)

        self.model.fit(x_train_scaled, y_train)
        accuracy = self.model.score(x_test_scaled, y_test)
        self.is_trained = True
        self.log_to_mlflow({"accuracy": accuracy}, self.parameters)
        return accuracy

    def get_feature_importances(self) -> Dict[str, float]:
        if not self.is_trained or self.model is None:
            return {}
        return dict(
            sorted(
                zip(self.feature_columns, self.model.feature_importances_),
                key=lambda item: item[1],
                reverse=True,
            )
        )

    def predict(self, df: pd.DataFrame) -> MLPrediction:
        if not self.is_trained:
            return MLPrediction(0, 0.0, [], "GradientBoosting", datetime.now().isoformat())

        frame = self.prepare_feature_frame(df, include_labels=False)
        if frame.empty:
            return MLPrediction(0, 0.0, [], "GradientBoosting", datetime.now().isoformat())

        x_last = frame[self.feature_columns].iloc[[-1]].values
        x_scaled = self.scaler.transform(x_last)
        pred = int(self.model.predict(x_scaled)[0])
        proba = self.model.predict_proba(x_scaled)[0]
        return MLPrediction(
            signal=pred,
            probability=float(max(proba)),
            features_used=self.feature_columns,
            model_name="GradientBoosting",
            timestamp=datetime.now().isoformat(),
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        result = df.copy()
        result["signal"] = 0
        if not self.is_trained:
            return result

        frame = self.prepare_feature_frame(df, include_labels=False)
        if frame.empty:
            return result

        x_scaled = self.scaler.transform(frame[self.feature_columns].values)
        result.loc[frame.index, "signal"] = self.model.predict(x_scaled).astype(int)
        return result


class EnsembleMLStrategy(BaseStrategy):
    def __init__(self, models: Optional[List[MLStrategy]] = None, voting: str = "soft"):
        super().__init__(name="Ensemble")
        self.voting = voting
        self.mlflow = MLflowManager() if MLFLOW_AVAILABLE else None
        self.is_trained = False
        self.models = models or [
            RandomForestStrategy(n_estimators=100),
            GradientBoostingStrategy(n_estimators=100),
        ]

    def train(self, df: pd.DataFrame) -> float:
        results = self.train_all(df)
        trained_results = [score for score in results.values() if score is not None]
        self.is_trained = any(getattr(model, "is_trained", False) for model in self.models)
        if not trained_results:
            return 0.0
        return float(sum(trained_results) / len(trained_results))

    def train_all(self, df: pd.DataFrame) -> Dict[str, float]:
        results = {}
        for model in self.models:
            results[model.__class__.__name__] = model.train(df)
        self.is_trained = any(getattr(model, "is_trained", False) for model in self.models)
        return results

    def predict(self, df: pd.DataFrame) -> MLPrediction:
        member_predictions = []
        for model in self.models:
            if getattr(model, "is_trained", False):
                member_predictions.append(model.predict(df))

        if not member_predictions:
            return MLPrediction(0, 0.0, [], "Ensemble", datetime.now().isoformat())

        signals = np.array([prediction.signal for prediction in member_predictions], dtype=float)
        probabilities = [
            float(prediction.probability)
            for prediction in member_predictions
            if prediction.probability is not None
        ]

        if self.voting == "soft":
            combined_signal = float(signals.mean())
            signal = 1 if combined_signal > 0.3 else (-1 if combined_signal < -0.3 else 0)
        else:
            signal = int(pd.Series(signals.astype(int)).mode().iloc[0])

        features_used = []
        for prediction in member_predictions:
            features_used.extend(prediction.features_used)

        return MLPrediction(
            signal=int(signal),
            probability=float(sum(probabilities) / len(probabilities)) if probabilities else 0.0,
            features_used=list(dict.fromkeys(features_used)),
            model_name="Ensemble",
            timestamp=datetime.now().isoformat(),
        )

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        result = df.copy()
        result["signal"] = 0

        member_signals = []
        for model in self.models:
            if model.is_trained:
                member_signals.append(model.generate_signals(df)["signal"])

        if not member_signals:
            self.is_trained = False
            return result

        signal_frame = pd.concat(member_signals, axis=1)
        if self.voting == "soft":
            combined = signal_frame.mean(axis=1)
            result["signal"] = combined.apply(
                lambda value: 1 if value > 0.3 else (-1 if value < -0.3 else 0)
            ).astype(int)
        else:
            result["signal"] = signal_frame.mode(axis=1)[0].fillna(0).astype(int)
        self.is_trained = True
        return result


if TORCH_AVAILABLE:

    class LSTMModel(nn.Module):
        def __init__(
            self,
            input_size: int,
            hidden_size: int = 64,
            num_layers: int = 2,
            num_classes: int = 3,
        ):
            super().__init__()
            self.hidden_size = hidden_size
            self.num_layers = num_layers
            self.lstm = nn.LSTM(
                input_size,
                hidden_size,
                num_layers,
                batch_first=True,
                dropout=0.2,
            )
            self.fc = nn.Linear(hidden_size, num_classes)

        def forward(self, x):
            h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size)
            c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size)
            out, _ = self.lstm(x, (h0, c0))
            return self.fc(out[:, -1, :])


    class LSTMStrategy(MLStrategy):
        def __init__(self, lookback: int = 60, hidden_size: int = 64, epochs: int = 50):
            super().__init__(name="LSTM", lookback=lookback)
            self.hidden_size = hidden_size
            self.epochs = epochs
            self.parameters = {
                "lookback": lookback,
                "hidden_size": hidden_size,
                "epochs": epochs,
            }

        def train(self, df: pd.DataFrame) -> float:
            x, y = self.prepare_features(df)
            if len(x) < 200 or y is None:
                logger.warning("Not enough data to train LSTM")
                return 0.0

            x_scaled = self.scaler.fit_transform(x)
            x_seq, y_seq = [], []
            for idx in range(self.lookback, len(x_scaled)):
                x_seq.append(x_scaled[idx - self.lookback : idx])
                y_seq.append(y[idx] + 1)

            if not x_seq:
                return 0.0

            x_seq = np.array(x_seq)
            y_seq = np.array(y_seq)
            split = int(len(x_seq) * 0.8)
            x_train, x_test = x_seq[:split], x_seq[split:]
            y_train, y_test = y_seq[:split], y_seq[split:]

            if len(x_test) == 0:
                return 0.0

            x_train_tensor = torch.FloatTensor(x_train)
            y_train_tensor = torch.LongTensor(y_train)
            x_test_tensor = torch.FloatTensor(x_test)
            y_test_tensor = torch.LongTensor(y_test)

            self.model = LSTMModel(input_size=x_train.shape[2], hidden_size=self.hidden_size)
            criterion = nn.CrossEntropyLoss()
            optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)

            self.model.train()
            for _ in range(self.epochs):
                optimizer.zero_grad()
                outputs = self.model(x_train_tensor)
                loss = criterion(outputs, y_train_tensor)
                loss.backward()
                optimizer.step()

            self.model.eval()
            with torch.no_grad():
                outputs = self.model(x_test_tensor)
                predicted = torch.argmax(outputs, dim=1)
                accuracy = float((predicted == y_test_tensor).float().mean().item())

            self.is_trained = True
            self.log_to_mlflow({"accuracy": accuracy}, self.parameters)
            return accuracy

        def predict(self, df: pd.DataFrame) -> MLPrediction:
            if not self.is_trained or self.model is None:
                return MLPrediction(0, 0.0, [], "LSTM", datetime.now().isoformat())

            frame = self.prepare_feature_frame(df, include_labels=False)
            if len(frame) < self.lookback:
                return MLPrediction(0, 0.0, [], "LSTM", datetime.now().isoformat())

            scaled = self.scaler.transform(frame[self.feature_columns].values)
            x_seq = torch.FloatTensor(scaled[-self.lookback :]).unsqueeze(0)

            self.model.eval()
            with torch.no_grad():
                output = self.model(x_seq)
                probabilities = torch.softmax(output, dim=1).numpy()[0]
            pred_class = int(np.argmax(probabilities))
            return MLPrediction(
                signal=pred_class - 1,
                probability=float(max(probabilities)),
                features_used=self.feature_columns,
                model_name="LSTM",
                timestamp=datetime.now().isoformat(),
            )

        def save_model(self, filepath: str):
            if self.model is None:
                return
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            torch.save(
                {
                    "state_dict": self.model.state_dict(),
                    "hidden_size": self.hidden_size,
                    "lookback": self.lookback,
                    "feature_columns": self.feature_columns,
                    "is_trained": self.is_trained,
                },
                filepath,
            )

        def load_model(self, filepath: str):
            if not os.path.exists(filepath):
                return
            payload = torch.load(filepath)
            self.hidden_size = payload.get("hidden_size", self.hidden_size)
            self.lookback = payload.get("lookback", self.lookback)
            self.feature_columns = payload.get("feature_columns", self.feature_columns)
            self.model = LSTMModel(
                input_size=len(self.get_feature_names()),
                hidden_size=self.hidden_size,
            )
            self.model.load_state_dict(payload["state_dict"])
            self.model.eval()
            self.is_trained = payload.get("is_trained", True)

else:

    class LSTMStrategy(MLStrategy):  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            super().__init__(name="LSTM", lookback=kwargs.get("lookback", 60))

        def train(self, df: pd.DataFrame) -> float:
            logger.error("PyTorch is required for LSTMStrategy")
            return 0.0

        def predict(self, df: pd.DataFrame) -> MLPrediction:
            return MLPrediction(0, 0.0, [], "LSTM", datetime.now().isoformat())


class StrategyFactory:
    @staticmethod
    def create(strategy_type: str, **kwargs) -> BaseStrategy:
        if strategy_type in {"ml_rf", "ml_strategy"}:
            return RandomForestStrategy(**kwargs)
        if strategy_type == "ml_gb":
            return GradientBoostingStrategy(**kwargs)
        if strategy_type == "ml_ensemble":
            return EnsembleMLStrategy(**kwargs)
        if strategy_type == "ml_lstm":
            if TORCH_AVAILABLE:
                return LSTMStrategy(**kwargs)
            logger.error("LSTM strategy is unavailable because PyTorch is missing")
            return None
        if strategy_type == "adaptive":
            if not ADAPTIVE_AVAILABLE:
                logger.error("AdaptiveStrategy is unavailable")
                return None
            try:
                from src.analysis.regime import MarketRegime

                rf = RandomForestStrategy(n_estimators=100)
                gb = GradientBoostingStrategy(n_estimators=100)
                strategy_map = {
                    MarketRegime.BULL: rf,
                    MarketRegime.SIDEWAYS: gb,
                    MarketRegime.BEAR: rf,
                    MarketRegime.HIGH_VOL: gb,
                }
                return AdaptiveStrategy(strategy_map=strategy_map)
            except Exception as exc:
                logger.error("Adaptive strategy creation failed: %s", exc)
                return None
        raise ValueError(f"Unsupported strategy type: {strategy_type}")
