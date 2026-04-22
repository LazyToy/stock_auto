from enum import Enum, auto
import pickle
from types import SimpleNamespace

import pandas as pd
import numpy as np

class MarketRegime(Enum):
    BULL = "BULL"        # 상승장 (MA20 > MA60)
    BEAR = "BEAR"        # 하락장 (MA20 < MA60)
    SIDEWAYS = "SIDEWAYS" # 횡보장 (이평선 밀집)
    HIGH_VOL = "HIGH_VOL" # 고변동성 (ATR 급증)
    UNKNOWN = "UNKNOWN"

class RegimeDetector:
    """
    시장 상태(Regime)를 감지하는 클래스.
    초기 버전은 기술적 지표(MA, ATR) 기반으로 구현하며, 
    추후 HMM(Hidden Markov Model) 또는 LSTM으로 고도화 예정.
    """
    
    def __init__(
        self,
        ma_short=20,
        ma_long=60,
        atr_period=14,
        vol_threshold=2.0,
        n_components: int | None = None,
    ):
        self.ma_short = ma_short
        self.ma_long = ma_long
        self.atr_period = atr_period
        self.vol_threshold = vol_threshold
        self.n_components = int(n_components or 3)
        self.model = _SimpleRegimeModel(self.n_components)

    def detect(self, df: pd.DataFrame) -> MarketRegime:
        """
        주어진 데이터프레임(OHLCV)을 분석하여 현재 시장 레짐을 반환합니다.
        """
        if len(df) < self.ma_long:
            return MarketRegime.UNKNOWN
        
        # 1. 이동평균 계산
        ma_s = df['close'].rolling(window=self.ma_short).mean().iloc[-1]
        ma_l = df['close'].rolling(window=self.ma_long).mean().iloc[-1]
        
        # 2. 변동성(ATR) 계산 (고변동성 감지용)
        # True Range
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(window=self.atr_period).mean().iloc[-1]
        current_price = df['close'].iloc[-1]
        
        # ATR 비율 (가격 대비 변동성)
        atr_ratio = (atr / current_price) * 100
        
        # 3. 레짐 판별 로직
        
        # 3.1 고변동성 체크 (ATR Ratio가 임계값 초과 시)
        if atr_ratio > self.vol_threshold:
            return MarketRegime.HIGH_VOL
            
        # 3.2 추세 판별 (MA Cross)
        # 횡보장: 두 이평선의 차이가 1% 이내일 때
        diff_ratio = abs(ma_s - ma_l) / ma_l * 100
        if diff_ratio < 1.0:
            return MarketRegime.SIDEWAYS
            
        if ma_s > ma_l:
            return MarketRegime.BULL
        else:
            return MarketRegime.BEAR

    def train_model(self, df: pd.DataFrame) -> None:
        self.model.fit(df)

    def predict_regime(self, df: pd.DataFrame) -> int:
        return int(self.model.predict(df)[0])

    def save_model(self, path: str) -> None:
        with open(path, "wb") as f:
            pickle.dump(self.model, f)

    def load_model(self, path: str) -> None:
        with open(path, "rb") as f:
            self.model = pickle.load(f)


class _SimpleRegimeModel:
    """Small deterministic regime model kept for legacy tests without HMM deps."""

    def __init__(self, n_components: int) -> None:
        self.n_components = int(n_components)
        self.monitor_ = SimpleNamespace(converged=False)
        self.means_ = np.zeros((self.n_components, 0))

    def _features(self, df: pd.DataFrame) -> np.ndarray:
        numeric = df.select_dtypes(include=[np.number])
        if numeric.empty:
            raise ValueError("Regime model requires numeric features")
        return numeric.to_numpy(dtype=float)

    def fit(self, df: pd.DataFrame) -> "_SimpleRegimeModel":
        values = self._features(df)
        order = np.argsort(values[:, 0])
        buckets = np.array_split(values[order], self.n_components)
        means = []
        fallback = np.nanmean(values, axis=0)
        for bucket in buckets:
            if len(bucket) == 0:
                means.append(fallback)
            else:
                means.append(np.nanmean(bucket, axis=0))
        self.means_ = np.vstack(means)
        self.monitor_ = SimpleNamespace(converged=True)
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        values = self._features(df)
        if self.means_.size == 0:
            raise ValueError("Regime model is not trained")
        distances = ((values[:, None, :] - self.means_[None, :, :]) ** 2).sum(axis=2)
        return np.argmin(distances, axis=1).astype(int)

