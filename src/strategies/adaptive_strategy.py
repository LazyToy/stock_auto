from typing import Dict, Optional, Type
import logging
import pandas as pd
from .base import BaseStrategy
from ..analysis.regime import RegimeDetector, MarketRegime

# Import default concrete strategies if mapped
# from .ma_strategy import MovingAverageStrategy
# from .rsi_strategy import RSIStrategy

class AdaptiveStrategy(BaseStrategy):
    """
    시장 레짐(Regime)에 따라 동적으로 하위 전략을 선택하여 실행하는 전략.
    """
    
    def __init__(self, 
                 detector: Optional[RegimeDetector] = None, 
                 strategy_map: Dict[MarketRegime, BaseStrategy] = None):
        """
        Args:
            detector (RegimeDetector): 레짐 감지 모델
            strategy_map (Dict[MarketRegime, BaseStrategy]): 각 레짐별 실행할 전략 매핑
        """
        super().__init__("adaptive")
        
        if detector is None:
            detector = RegimeDetector()
        
        if strategy_map is None:
            # Default Mapping (추후 실제 클래스 임포트하여 초기화 필요)
            strategy_map = {} 
            
        self.detector = detector
        self.strategy_map = strategy_map
        self.logger = logging.getLogger(__name__)

    def train(self, df: pd.DataFrame) -> Dict[str, float]:
        """
        매핑된 모든 하위 전략을 학습시킵니다.
        ML 기반 전략이 포함된 경우 필수적으로 호출해야 합니다.
        """
        results = {}
        for regime, strategy in self.strategy_map.items():
            # train 메서드가 있는 경우에만 호출 (MLStrategy 등)
            if hasattr(strategy, 'train') and callable(getattr(strategy, 'train')):
                try:
                    self.logger.info(f"Training strategy for {regime.name}: {strategy.name}")
                    # 모든 데이터로 학습 (레짐별 필터링은 하지 않음 - 모델이 충분한 데이터를 보게 하기 위함)
                    # 만약 레짐별 데이터만 학습시키려면 여기서 df를 필터링해야 함.
                    # 하지만 데이터 부족 문제가 생길 수 있으므로 전체 데이터 사용을 권장.
                    metric = strategy.train(df)
                    results[regime.name] = metric
                except Exception as e:
                    self.logger.error(f"Failed to train {strategy.name} for {regime.name}: {e}")
                    results[regime.name] = 0.0
            else:
                 self.logger.debug(f"Strategy {strategy.name} for {regime.name} is not trainable.")
        
        return results

    def generate_signals(self, data):
        """
        현재 레짐을 감지하고, 해당 레짐에 매핑된 전략을 실행하여 시그널 반환
        """
        if data.empty:
            return pd.DataFrame()
            
        current_regime = self.detector.detect(data)
        self.logger.info(f"Detected Regime: {current_regime.name}")
        
        strategy = self.strategy_map.get(current_regime)
        
        if strategy:
            try:
                # Delegate to the sub-strategy's generate_signals
                result = strategy.generate_signals(data)
                # Since Result is likely a DataFrame from BaseStrategy standard, 
                # we might want to attach regime info if possible, or just return it.
                # If the strategy returns a DataFrame, we can't easily add metadata unless we modify it.
                return result
            except Exception as e:
                self.logger.error(f"Error executing {strategy.name}: {e}")
                # Return empty or HOLD DataFrame? 
                # For now let's return a simple dict as fallback or specific error structure, 
                # but ideally it should match the return type of BaseStrategy which is DataFrame.
                # However, the existin implementation seemed to return dict. 
                # If BaseStrategy enforces DataFrame, we must return DataFrame.
                return pd.DataFrame()
        else:
            self.logger.warning(f"No strategy mapped for {current_regime.name}. Falling back to HOLD.")
            return pd.DataFrame() # Fallback

