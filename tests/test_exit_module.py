"""Exit 전략 모듈 테스트

TDD 원칙에 따라 exit 전략의 동작을 테스트합니다.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.strategies.exit_base import (
    BaseExitStrategy, ExitSignal, PositionContext, CompositeExitStrategy
)
from src.strategies.exit_strategies import (
    FixedStopLoss, ATRTrailingStop, PercentTrailingStop,
    PartialTakeProfit, TimeBasedExit, MinScoreExit, calculate_atr
)


class TestExitSignal:
    """ExitSignal 데이터클래스 테스트"""
    
    def test_hold_signal(self):
        """보유 유지 신호 테스트"""
        signal = ExitSignal.hold()
        assert signal.should_exit == False
        assert signal.exit_ratio == 0.0
        assert signal.reason == "HOLD"
    
    def test_full_exit_signal(self):
        """전량 청산 신호 테스트"""
        signal = ExitSignal.full_exit(reason="STOP_LOSS", price=10000)
        assert signal.should_exit == True
        assert signal.exit_ratio == 1.0
        assert "STOP_LOSS" in signal.reason
        assert signal.price == 10000
    
    def test_partial_exit_signal(self):
        """부분 청산 신호 테스트"""
        signal = ExitSignal.partial_exit(ratio=0.5, reason="TAKE_PROFIT")
        assert signal.should_exit == True
        assert signal.exit_ratio == 0.5
    
    def test_partial_exit_ratio_bounds(self):
        """부분 청산 비율 경계값 테스트"""
        # 초과 비율은 1.0으로 제한
        signal = ExitSignal.partial_exit(ratio=1.5, reason="TEST")
        assert signal.exit_ratio == 1.0
        
        # 음수 비율은 0.0으로 제한
        signal = ExitSignal.partial_exit(ratio=-0.5, reason="TEST")
        assert signal.exit_ratio == 0.0


class TestPositionContext:
    """PositionContext 데이터클래스 테스트"""
    
    def test_profit_pct_calculation(self):
        """수익률 계산 테스트"""
        context = PositionContext(
            symbol="005930.KS",
            quantity=10,
            avg_price=10000,
            current_price=11000  # +10%
        )
        assert context.profit_pct == pytest.approx(0.10, rel=0.01)
    
    def test_loss_pct_calculation(self):
        """손실률 계산 테스트"""
        context = PositionContext(
            symbol="005930.KS",
            quantity=10,
            avg_price=10000,
            current_price=9000  # -10%
        )
        assert context.loss_pct == pytest.approx(-0.10, rel=0.01)
    
    def test_drop_from_hwm(self):
        """고점 대비 하락률 테스트"""
        context = PositionContext(
            symbol="005930.KS",
            quantity=10,
            avg_price=10000,
            current_price=9500,
            high_water_mark=10500  # HWM에서 -9.5%
        )
        assert context.drop_from_hwm == pytest.approx(-0.095, rel=0.01)


class TestFixedStopLoss:
    """FixedStopLoss 전략 테스트"""
    
    def test_stop_loss_triggers(self):
        """손절선 도달 시 청산 테스트"""
        strategy = FixedStopLoss(stop_pct=-0.07)
        
        context = PositionContext(
            symbol="005930.KS",
            quantity=10,
            avg_price=10000,
            current_price=9200  # -8%
        )
        market_data = pd.Series({'close': 9200})
        
        signal = strategy.check_exit(context, market_data)
        assert signal.should_exit == True
        assert signal.exit_ratio == 1.0
        assert "STOP_LOSS" in signal.reason
    
    def test_stop_loss_not_triggers(self):
        """손절선 미도달 시 보유 유지"""
        strategy = FixedStopLoss(stop_pct=-0.07)
        
        context = PositionContext(
            symbol="005930.KS",
            quantity=10,
            avg_price=10000,
            current_price=9500  # -5%
        )
        market_data = pd.Series({'close': 9500})
        
        signal = strategy.check_exit(context, market_data)
        assert signal.should_exit == False


class TestATRTrailingStop:
    """ATRTrailingStop 전략 테스트"""
    
    def test_atr_trailing_stop_triggers(self):
        """ATR Trailing Stop 작동 테스트"""
        strategy = ATRTrailingStop(multiplier=2.0)
        
        # 고점 10500, ATR 100 → Stop at 10300
        context = PositionContext(
            symbol="005930.KS",
            quantity=10,
            avg_price=10000,
            current_price=10200,  # 10300 아래
            high_water_mark=10500,
            atr=100
        )
        market_data = pd.Series({'close': 10200})
        
        # 먼저 update 호출 (HWM 설정)
        strategy._high_water_mark["005930.KS"] = 10500
        
        signal = strategy.check_exit(context, market_data)
        assert signal.should_exit == True
        assert "ATR_TRAILING" in signal.reason
    
    def test_atr_trailing_stop_holds_in_uptrend(self):
        """상승 추세에서 보유 유지"""
        strategy = ATRTrailingStop(multiplier=2.0)
        
        context = PositionContext(
            symbol="005930.KS",
            quantity=10,
            avg_price=10000,
            current_price=10400,  # 10300 위
            high_water_mark=10500,
            atr=100
        )
        market_data = pd.Series({'close': 10400})
        
        strategy._high_water_mark["005930.KS"] = 10500
        
        signal = strategy.check_exit(context, market_data)
        assert signal.should_exit == False
    
    def test_hwm_updates(self):
        """High Water Mark 업데이트 테스트"""
        strategy = ATRTrailingStop(multiplier=2.0)
        
        context = PositionContext(
            symbol="005930.KS",
            quantity=10,
            avg_price=10000,
            current_price=11000,  # 신고점
            atr=100
        )
        market_data = pd.Series({'close': 11000})
        
        strategy.update(context, market_data)
        
        assert strategy._high_water_mark["005930.KS"] == 11000


class TestPercentTrailingStop:
    """PercentTrailingStop 전략 테스트"""
    
    def test_trailing_stop_not_active_below_threshold(self):
        """활성화 기준 미달 시 작동하지 않음"""
        strategy = PercentTrailingStop(trail_pct=-0.05, activation_pct=0.10)
        
        context = PositionContext(
            symbol="005930.KS",
            quantity=10,
            avg_price=10000,
            current_price=10500  # +5% (활성화 기준 10% 미달)
        )
        market_data = pd.Series({'close': 10500})
        
        signal = strategy.check_exit(context, market_data)
        assert signal.should_exit == False
    
    def test_trailing_stop_triggers_after_activation(self):
        """활성화 후 고점 대비 하락 시 청산"""
        strategy = PercentTrailingStop(trail_pct=-0.05, activation_pct=0.10)
        
        # HWM 설정 (이전에 12000까지 갔었음)
        strategy._high_water_mark["005930.KS"] = 12000
        
        context = PositionContext(
            symbol="005930.KS",
            quantity=10,
            avg_price=10000,
            current_price=11300  # +13% (활성화 OK), HWM 12000 대비 -5.8%
        )
        market_data = pd.Series({'close': 11300})
        
        signal = strategy.check_exit(context, market_data)
        assert signal.should_exit == True
        assert "TRAILING_STOP" in signal.reason


class TestPartialTakeProfit:
    """PartialTakeProfit 전략 테스트"""
    
    def test_first_level_partial_exit(self):
        """첫 번째 레벨에서 부분 청산"""
        strategy = PartialTakeProfit(levels={0.10: 0.25, 0.20: 0.50})
        
        context = PositionContext(
            symbol="005930.KS",
            quantity=100,
            avg_price=10000,
            current_price=11200  # +12%
        )
        market_data = pd.Series({'close': 11200})
        
        signal = strategy.check_exit(context, market_data)
        assert signal.should_exit == True
        assert signal.exit_ratio == 0.25  # 첫 레벨 25%
        assert "TAKE_PROFIT" in signal.reason
    
    def test_second_level_after_first(self):
        """첫 번째 레벨 실현 후 두 번째 레벨"""
        strategy = PartialTakeProfit(levels={0.10: 0.25, 0.20: 0.50})
        
        # 첫 번째 레벨 실현
        strategy._realized_levels["005930.KS"] = {0.10}
        
        context = PositionContext(
            symbol="005930.KS",
            quantity=75,  # 25% 청산 후 남은 수량
            avg_price=10000,
            current_price=12500  # +25%
        )
        market_data = pd.Series({'close': 12500})
        
        signal = strategy.check_exit(context, market_data)
        assert signal.should_exit == True
        assert signal.exit_ratio == 0.50  # 두 번째 레벨 50%
    
    def test_no_double_trigger_same_level(self):
        """같은 레벨 중복 청산 방지"""
        strategy = PartialTakeProfit(levels={0.10: 0.25})
        
        # 이미 실현된 레벨
        strategy._realized_levels["005930.KS"] = {0.10}
        
        context = PositionContext(
            symbol="005930.KS",
            quantity=75,
            avg_price=10000,
            current_price=11200  # +12%
        )
        market_data = pd.Series({'close': 11200})
        
        signal = strategy.check_exit(context, market_data)
        assert signal.should_exit == False


class TestTimeBasedExit:
    """TimeBasedExit 전략 테스트"""
    
    def test_time_exit_triggers(self):
        """보유 기간 초과 시 청산"""
        strategy = TimeBasedExit(max_holding_days=30, force_exit=True)
        
        context = PositionContext(
            symbol="005930.KS",
            quantity=10,
            avg_price=10000,
            current_price=10000,
            holding_days=35
        )
        market_data = pd.Series({'close': 10000})
        
        signal = strategy.check_exit(context, market_data)
        assert signal.should_exit == True
        assert "TIME_EXIT" in signal.reason
    
    def test_time_exit_holds_within_limit(self):
        """보유 기간 내 보유 유지"""
        strategy = TimeBasedExit(max_holding_days=30, force_exit=True)
        
        context = PositionContext(
            symbol="005930.KS",
            quantity=10,
            avg_price=10000,
            current_price=10000,
            holding_days=20
        )
        market_data = pd.Series({'close': 10000})
        
        signal = strategy.check_exit(context, market_data)
        assert signal.should_exit == False


class TestCompositeExitStrategy:
    """CompositeExitStrategy 테스트"""
    
    def test_composite_first_trigger_wins(self):
        """첫 번째로 트리거되는 전략 반환"""
        strategies = [
            FixedStopLoss(stop_pct=-0.10),  # 트리거 안됨
            FixedStopLoss(stop_pct=-0.05),  # 트리거됨
        ]
        composite = CompositeExitStrategy(strategies)
        
        context = PositionContext(
            symbol="005930.KS",
            quantity=10,
            avg_price=10000,
            current_price=9300  # -7%
        )
        market_data = pd.Series({'close': 9300})
        
        signal = composite.check_exit(context, market_data)
        assert signal.should_exit == True
    
    def test_composite_all_hold(self):
        """모든 전략이 보유 유지"""
        strategies = [
            FixedStopLoss(stop_pct=-0.10),
            PercentTrailingStop(activation_pct=0.20),
        ]
        composite = CompositeExitStrategy(strategies)
        
        context = PositionContext(
            symbol="005930.KS",
            quantity=10,
            avg_price=10000,
            current_price=10500  # +5%
        )
        market_data = pd.Series({'close': 10500})
        
        signal = composite.check_exit(context, market_data)
        assert signal.should_exit == False


class TestCalculateATR:
    """ATR 계산 함수 테스트"""
    
    def test_atr_calculation(self):
        """ATR 계산 테스트"""
        # 간단한 데이터프레임 생성 (date_range 없이)
        data = pd.DataFrame({
            'high': [100, 102, 101, 103, 102, 104, 103, 105, 104, 106,
                     105, 107, 106, 108, 107, 109, 108, 110, 109, 111,
                     110, 112, 111, 113, 112, 114, 113, 115, 114, 116],
            'low':  [98, 100, 99, 101, 100, 102, 101, 103, 102, 104,
                     103, 105, 104, 106, 105, 107, 106, 108, 107, 109,
                     108, 110, 109, 111, 110, 112, 111, 113, 112, 114],
            'close': [99, 101, 100, 102, 101, 103, 102, 104, 103, 105,
                      104, 106, 105, 107, 106, 108, 107, 109, 108, 110,
                      109, 111, 110, 112, 111, 113, 112, 114, 113, 115],
        })
        
        atr = calculate_atr(data, period=14)
        
        assert len(atr) == 30
        assert atr.iloc[-1] > 0  # ATR은 항상 양수


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
