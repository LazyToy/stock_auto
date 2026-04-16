"""ML 전략 테스트

TDD: 머신러닝 기반 전략의 동작을 테스트합니다.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ML 라이브러리 체크
try:
    from sklearn.ensemble import RandomForestClassifier
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


@pytest.fixture
def sample_ohlcv_data():
    """ML 학습에 충분한 샘플 OHLCV 데이터 생성 (200일)"""
    np.random.seed(42)
    dates = pd.date_range(start='2024-01-01', periods=200, freq='D')
    
    # 추세가 있는 가격 데이터 생성
    base_price = 50000
    trend = np.cumsum(np.random.randn(200) * 500)
    noise = np.random.randn(200) * 200
    
    close = base_price + trend + noise
    high = close + np.abs(np.random.randn(200) * 300)
    low = close - np.abs(np.random.randn(200) * 300)
    open_price = (high + low) / 2 + np.random.randn(200) * 100
    volume = np.random.randint(100000, 1000000, 200)
    
    return pd.DataFrame({
        'date': dates,
        'open': open_price,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume
    })


class TestFeatureEngineering:
    """피처 엔지니어링 테스트"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """테스트 설정"""
        from src.strategies.ml_strategy import FeatureEngineering
        self.fe = FeatureEngineering
    
    def test_add_technical_features(self, sample_ohlcv_data):
        """기술적 지표 피처 추가 테스트"""
        result = self.fe.add_technical_features(sample_ohlcv_data)
        
        # 이동평균 피처 확인
        assert 'ma_5' in result.columns
        assert 'ma_10' in result.columns
        assert 'ma_20' in result.columns
        assert 'ma_50' in result.columns
        assert 'ma_5_ratio' in result.columns
        
        # RSI 확인
        assert 'rsi' in result.columns
        assert result['rsi'].dropna().between(0, 100).all()
        
        # MACD 확인
        assert 'macd' in result.columns
        assert 'macd_signal' in result.columns
        assert 'macd_hist' in result.columns
        
        # 볼린저 밴드 확인
        assert 'bb_upper' in result.columns
        assert 'bb_lower' in result.columns
        assert 'bb_width' in result.columns
        assert 'bb_position' in result.columns
        
        # ATR 확인
        assert 'atr' in result.columns
        assert 'atr_ratio' in result.columns
    
    def test_create_labels(self, sample_ohlcv_data):
        """레이블 생성 테스트"""
        result = self.fe.create_labels(sample_ohlcv_data, forward_days=5, threshold=0.02)
        
        assert 'future_return' in result.columns
        assert 'label' in result.columns
        
        # 레이블 값 확인 (-1, 0, 1)
        valid_labels = result['label'].dropna().unique()
        for label in valid_labels:
            assert label in [-1, 0, 1]


class TestMLPrediction:
    """ML 예측 결과 데이터클래스 테스트"""
    
    def test_ml_prediction_creation(self):
        """MLPrediction 생성 테스트"""
        from src.strategies.ml_strategy import MLPrediction
        
        pred = MLPrediction(
            signal=1,
            probability=0.85,
            features_used=['ma_5_ratio', 'rsi'],
            model_name="TestModel",
            timestamp=datetime.now().isoformat()
        )
        
        assert pred.signal == 1
        assert pred.probability == 0.85
        assert len(pred.features_used) == 2
        assert pred.model_name == "TestModel"


@pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn 미설치")
class TestRandomForestStrategy:
    """RandomForest 전략 테스트"""
    
    def test_strategy_creation(self):
        """RandomForest 전략 생성 테스트"""
        from src.strategies.ml_strategy import RandomForestStrategy
        
        strategy = RandomForestStrategy(n_estimators=50)
        
        assert strategy.n_estimators == 50
        assert strategy.model is not None
        assert strategy.is_trained is False
    
    def test_get_feature_names(self):
        """피처 목록 조회 테스트"""
        from src.strategies.ml_strategy import RandomForestStrategy
        
        strategy = RandomForestStrategy()
        features = strategy.get_feature_names()
        
        assert isinstance(features, list)
        assert len(features) > 0
        assert 'rsi' in features
        assert 'macd' in features
    
    def test_train_with_sufficient_data(self, sample_ohlcv_data):
        """충분한 데이터로 학습 테스트"""
        from src.strategies.ml_strategy import RandomForestStrategy
        
        strategy = RandomForestStrategy(n_estimators=10)  # 빠른 테스트용
        accuracy = strategy.train(sample_ohlcv_data)
        
        assert strategy.is_trained is True
        assert 0.0 <= accuracy <= 1.0
    
    def test_train_with_insufficient_data(self):
        """부족한 데이터로 학습 시 경고 테스트"""
        from src.strategies.ml_strategy import RandomForestStrategy
        
        # 50개 데이터만 (최소 100개 필요)
        small_data = pd.DataFrame({
            'date': pd.date_range(start='2024-01-01', periods=50, freq='D'),
            'open': np.random.randn(50) * 100 + 50000,
            'high': np.random.randn(50) * 100 + 50500,
            'low': np.random.randn(50) * 100 + 49500,
            'close': np.random.randn(50) * 100 + 50000,
            'volume': np.random.randint(100000, 1000000, 50)
        })
        
        strategy = RandomForestStrategy()
        accuracy = strategy.train(small_data)
        
        assert accuracy == 0.0
        assert strategy.is_trained is False
    
    def test_predict_after_training(self, sample_ohlcv_data):
        """학습 후 예측 테스트"""
        from src.strategies.ml_strategy import RandomForestStrategy
        
        strategy = RandomForestStrategy(n_estimators=10)
        strategy.train(sample_ohlcv_data)
        
        prediction = strategy.predict(sample_ohlcv_data)
        
        assert prediction.signal in [-1, 0, 1]
        assert 0.0 <= prediction.probability <= 1.0
        assert prediction.model_name == "RandomForest"
    
    def test_predict_before_training(self, sample_ohlcv_data):
        """학습 전 예측 시 기본값 반환 테스트"""
        from src.strategies.ml_strategy import RandomForestStrategy
        
        strategy = RandomForestStrategy()
        prediction = strategy.predict(sample_ohlcv_data)
        
        assert prediction.signal == 0
        assert prediction.probability == 0.0
    
    def test_generate_signals(self, sample_ohlcv_data):
        """신호 생성 테스트"""
        from src.strategies.ml_strategy import RandomForestStrategy
        
        strategy = RandomForestStrategy(n_estimators=10)
        strategy.train(sample_ohlcv_data)
        
        result = strategy.generate_signals(sample_ohlcv_data)
        
        assert 'signal' in result.columns
        # 마지막 행에만 신호가 있음
        assert result['signal'].iloc[-1] in [-1, 0, 1]


@pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn 미설치")
class TestGradientBoostingStrategy:
    """GradientBoosting 전략 테스트"""
    
    def test_strategy_creation(self):
        """GradientBoosting 전략 생성 테스트"""
        from src.strategies.ml_strategy import GradientBoostingStrategy
        
        strategy = GradientBoostingStrategy(n_estimators=50)
        
        assert strategy.n_estimators == 50
        assert strategy.model is not None
        assert strategy.is_trained is False
    
    def test_train_and_predict(self, sample_ohlcv_data):
        """학습 및 예측 통합 테스트"""
        from src.strategies.ml_strategy import GradientBoostingStrategy
        
        strategy = GradientBoostingStrategy(n_estimators=10)
        accuracy = strategy.train(sample_ohlcv_data)
        
        assert strategy.is_trained is True
        assert 0.0 <= accuracy <= 1.0
        
        prediction = strategy.predict(sample_ohlcv_data)
        assert prediction.signal in [-1, 0, 1]
        assert prediction.model_name == "GradientBoosting"


@pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn 미설치")
class TestEnsembleMLStrategy:
    """앙상블 ML 전략 테스트"""
    
    def test_ensemble_creation_default(self):
        """기본 앙상블 생성 테스트"""
        from src.strategies.ml_strategy import EnsembleMLStrategy
        
        strategy = EnsembleMLStrategy()
        
        assert len(strategy.models) == 2  # RF + GB
        assert strategy.voting == "soft"
    
    def test_ensemble_creation_custom(self):
        """커스텀 앙상블 생성 테스트"""
        from src.strategies.ml_strategy import (
            EnsembleMLStrategy, RandomForestStrategy, GradientBoostingStrategy
        )
        
        models = [
            RandomForestStrategy(n_estimators=10),
            GradientBoostingStrategy(n_estimators=10)
        ]
        strategy = EnsembleMLStrategy(models=models, voting="hard")
        
        assert len(strategy.models) == 2
        assert strategy.voting == "hard"
    
    def test_train_all(self, sample_ohlcv_data):
        """모든 모델 학습 테스트"""
        from src.strategies.ml_strategy import (
            EnsembleMLStrategy, RandomForestStrategy, GradientBoostingStrategy
        )
        
        models = [
            RandomForestStrategy(n_estimators=10),
            GradientBoostingStrategy(n_estimators=10)
        ]
        strategy = EnsembleMLStrategy(models=models)
        
        results = strategy.train_all(sample_ohlcv_data)
        
        assert 'RandomForestStrategy' in results
        assert 'GradientBoostingStrategy' in results
        assert all(0.0 <= acc <= 1.0 for acc in results.values())

    def test_ensemble_train_and_predict(self):
        from src.strategies.ml_strategy import EnsembleMLStrategy, MLPrediction

        class DummyModelA:
            def __init__(self, accuracy, prediction):
                self.accuracy = accuracy
                self.prediction = prediction
                self.is_trained = False

            def train(self, df):
                self.is_trained = True
                return self.accuracy

            def predict(self, df):
                return self.prediction

        class DummyModelB(DummyModelA):
            pass

        models = [
            DummyModelA(0.8, MLPrediction(1, 0.9, [], "A", "2024-01-01T00:00:00")),
            DummyModelB(0.6, MLPrediction(0, 0.7, [], "B", "2024-01-01T00:00:00")),
        ]
        strategy = EnsembleMLStrategy(models=models, voting="soft")
        sample = pd.DataFrame(
            {
                "date": pd.date_range(start="2024-01-01", periods=3, freq="D"),
                "open": [1.0, 1.1, 1.2],
                "high": [1.1, 1.2, 1.3],
                "low": [0.9, 1.0, 1.1],
                "close": [1.0, 1.1, 1.2],
                "volume": [100, 110, 120],
            }
        )

        accuracy = strategy.train(sample)
        prediction = strategy.predict(sample)

        assert accuracy == pytest.approx(0.7)
        assert prediction.signal == 1
        assert prediction.probability == pytest.approx(0.8)
    
    def test_generate_signals_soft_voting(self, sample_ohlcv_data):
        """Soft voting 신호 생성 테스트"""
        from src.strategies.ml_strategy import (
            EnsembleMLStrategy, RandomForestStrategy, GradientBoostingStrategy
        )
        
        models = [
            RandomForestStrategy(n_estimators=10),
            GradientBoostingStrategy(n_estimators=10)
        ]
        strategy = EnsembleMLStrategy(models=models, voting="soft")
        strategy.train_all(sample_ohlcv_data)
        
        result = strategy.generate_signals(sample_ohlcv_data)
        
        assert 'signal' in result.columns
        assert result['signal'].iloc[-1] in [-1, 0, 1]
    
    def test_generate_signals_hard_voting(self, sample_ohlcv_data):
        """Hard voting 신호 생성 테스트"""
        from src.strategies.ml_strategy import (
            EnsembleMLStrategy, RandomForestStrategy, GradientBoostingStrategy
        )
        
        models = [
            RandomForestStrategy(n_estimators=10),
            GradientBoostingStrategy(n_estimators=10)
        ]
        strategy = EnsembleMLStrategy(models=models, voting="hard")
        strategy.train_all(sample_ohlcv_data)
        
        result = strategy.generate_signals(sample_ohlcv_data)
        
        assert 'signal' in result.columns
        assert result['signal'].iloc[-1] in [-1, 0, 1]
    
    def test_generate_signals_without_training(self, sample_ohlcv_data):
        """학습 없이 신호 생성 시 기본값 반환 테스트"""
        from src.strategies.ml_strategy import EnsembleMLStrategy
        
        strategy = EnsembleMLStrategy()
        result = strategy.generate_signals(sample_ohlcv_data)
        
        assert 'signal' in result.columns
        assert result['signal'].iloc[-1] == 0


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="PyTorch 미설치")
class TestLSTMStrategy:
    """LSTM 전략 테스트"""
    
    @pytest.fixture
    def large_ohlcv_data(self):
        """LSTM 학습에 충분한 대용량 데이터 (300일)"""
        np.random.seed(42)
        dates = pd.date_range(start='2023-06-01', periods=300, freq='D')
        
        base_price = 50000
        trend = np.cumsum(np.random.randn(300) * 500)
        
        return pd.DataFrame({
            'date': dates,
            'open': base_price + trend + np.random.randn(300) * 100,
            'high': base_price + trend + np.abs(np.random.randn(300) * 300),
            'low': base_price + trend - np.abs(np.random.randn(300) * 300),
            'close': base_price + trend + np.random.randn(300) * 200,
            'volume': np.random.randint(100000, 1000000, 300)
        })
    
    def test_lstm_strategy_creation(self):
        """LSTM 전략 생성 테스트"""
        from src.strategies.ml_strategy import LSTMStrategy
        
        strategy = LSTMStrategy(lookback=30, hidden_size=32, epochs=5)
        
        assert strategy.lookback == 30
        assert strategy.hidden_size == 32
        assert strategy.epochs == 5
        assert strategy.is_trained is False
    
    def test_lstm_train(self, large_ohlcv_data):
        """LSTM 학습 테스트"""
        from src.strategies.ml_strategy import LSTMStrategy
        
        strategy = LSTMStrategy(lookback=30, hidden_size=32, epochs=5)
        accuracy = strategy.train(large_ohlcv_data)
        
        assert strategy.is_trained is True
        assert 0.0 <= accuracy <= 1.0
        assert strategy.model is not None
    
    def test_lstm_predict(self, large_ohlcv_data):
        """LSTM 예측 테스트"""
        from src.strategies.ml_strategy import LSTMStrategy
        
        strategy = LSTMStrategy(lookback=30, hidden_size=32, epochs=5)
        strategy.train(large_ohlcv_data)
        
        prediction = strategy.predict(large_ohlcv_data)
        
        assert prediction.signal in [-1, 0, 1]
        assert 0.0 <= prediction.probability <= 1.0
        assert prediction.model_name == "LSTM"
    
    def test_lstm_insufficient_data(self):
        """LSTM 부족한 데이터 테스트"""
        from src.strategies.ml_strategy import LSTMStrategy
        
        small_data = pd.DataFrame({
            'date': pd.date_range(start='2024-01-01', periods=100, freq='D'),
            'open': np.random.randn(100) * 100 + 50000,
            'high': np.random.randn(100) * 100 + 50500,
            'low': np.random.randn(100) * 100 + 49500,
            'close': np.random.randn(100) * 100 + 50000,
            'volume': np.random.randint(100000, 1000000, 100)
        })
        
        strategy = LSTMStrategy(lookback=60)
        accuracy = strategy.train(small_data)
        
        # 데이터 부족 시 0.0 반환
        assert accuracy == 0.0 or strategy.is_trained is False
