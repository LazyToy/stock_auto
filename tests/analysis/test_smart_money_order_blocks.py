"""PR-04: 캔들 오더블록 탐지 테스트.

detect_order_blocks, update_order_block_status 함수의 공개 계약을 검증한다.

테스트 원칙:
    - 실제 API/네트워크 호출 없이 합성 OHLCV만 사용한다.
    - 구조 돌파 직전 lookback 구간의 마지막 반대색 캔들을 오더블록으로 본다.
    - 오더블록 상태는 구조 돌파가 확정된 이후 캔들만 사용해 갱신한다.
"""

import unittest
from datetime import datetime, timedelta

import pandas as pd


def _make_df(rows: list[dict], start: str = "2024-01-02", freq: str = "1D") -> pd.DataFrame:
    """테스트용 OHLCV DataFrame을 생성한다."""
    dates = pd.date_range(start=start, periods=len(rows), freq=freq)
    data = {
        "open": [r["open"] for r in rows],
        "high": [r["high"] for r in rows],
        "low": [r["low"] for r in rows],
        "close": [r["close"] for r in rows],
        "volume": [r.get("volume", 1000) for r in rows],
    }
    return pd.DataFrame(data, index=dates)


def _candle(
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: int = 1000,
) -> dict:
    """캔들 딕셔너리를 생성한다."""
    return {
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _make_break(
    direction: str,
    bar_index: int,
    break_type: str = "BOS",
    broken_level: float = 110.0,
) -> object:
    """테스트용 StructureBreak를 생성한다."""
    from src.analysis.smart_money.models import BreakDirection, BreakType, StructureBreak

    return StructureBreak(
        timestamp=datetime(2024, 1, 2) + timedelta(days=bar_index),
        break_type=BreakType.BOS if break_type == "BOS" else BreakType.CHOCH,
        direction=BreakDirection.BULLISH if direction == "BULLISH" else BreakDirection.BEARISH,
        broken_level=broken_level,
        bar_index=bar_index,
    )


class TestDetectOrderBlocks(unittest.TestCase):
    """detect_order_blocks 함수 단위 테스트."""

    def setUp(self) -> None:
        from src.analysis.smart_money.order_blocks import detect_order_blocks

        self.fn = detect_order_blocks

    def test_df_None_입력은_ValueError(self) -> None:
        """df=None은 명시적인 ValueError를 발생시킨다."""
        with self.assertRaises(ValueError):
            self.fn(None, [], [])

    def test_swings_None_입력은_ValueError(self) -> None:
        """swings=None은 명시적인 ValueError를 발생시킨다."""
        df = _make_df([_candle(100, 101, 99, 100)] * 3)
        with self.assertRaises(ValueError):
            self.fn(df, None, [])

    def test_breaks_None_입력은_ValueError(self) -> None:
        """breaks=None은 명시적인 ValueError를 발생시킨다."""
        df = _make_df([_candle(100, 101, 99, 100)] * 3)
        with self.assertRaises(ValueError):
            self.fn(df, [], None)

    def test_non_DatetimeIndex_입력은_ValueError(self) -> None:
        """DatetimeIndex가 아니면 ValueError를 발생시킨다."""
        df = pd.DataFrame(
            {
                "open": [100.0] * 3,
                "high": [101.0] * 3,
                "low": [99.0] * 3,
                "close": [100.0] * 3,
                "volume": [1000] * 3,
            }
        )
        with self.assertRaises(ValueError):
            self.fn(df, [], [])

    def test_lookback_1_미만은_ValueError(self) -> None:
        """lookback은 1 이상이어야 한다."""
        df = _make_df([_candle(100, 101, 99, 100)] * 3)
        with self.assertRaises(ValueError):
            self.fn(df, [], [], lookback=0)

    def test_필수_컬럼_누락은_빈_리스트(self) -> None:
        """필수 OHLC 컬럼이 없으면 예외 대신 빈 결과를 반환한다."""
        df = _make_df([_candle(100, 101, 99, 100)] * 5).drop(columns=["close"])
        result = self.fn(df, [], [_make_break("BULLISH", 4)])
        self.assertEqual(result, [])

    def test_breaks가_없으면_빈_리스트(self) -> None:
        """구조 돌파가 없으면 오더블록도 생성하지 않는다."""
        df = _make_df([_candle(100, 101, 99, 100)] * 5)
        self.assertEqual(self.fn(df, [], []), [])

    def test_bullish_BOS는_직전_마지막_bearish_candle을_BULLISH_OB로_생성(self) -> None:
        """Bullish BOS 직전 lookback 구간의 마지막 음봉을 bullish OB로 생성한다."""
        from src.analysis.smart_money.models import OrderBlockDirection, OrderBlockStatus

        rows = [
            _candle(100, 103, 99, 102),
            _candle(102, 104, 100, 103),
            _candle(106, 107, 101, 102),  # 이전 음봉이지만 마지막 음봉은 아님
            _candle(103, 106, 102, 105),
            _candle(108, 109, 100, 101),  # 마지막 음봉, OB 후보
            _candle(104, 113, 103, 112),  # bullish BOS
        ]
        df = _make_df(rows)

        result = self.fn(df, [], [_make_break("BULLISH", 5)], lookback=5)

        self.assertEqual(len(result), 1)
        ob = result[0]
        self.assertEqual(ob.direction, OrderBlockDirection.BULLISH)
        self.assertEqual(ob.status, OrderBlockStatus.FRESH)
        self.assertEqual(ob.bar_index, 4)
        self.assertEqual(ob.break_bar_index, 5)
        self.assertAlmostEqual(ob.lower, 100.0)
        self.assertAlmostEqual(ob.upper, 109.0)

    def test_bearish_BOS는_직전_마지막_bullish_candle을_BEARISH_OB로_생성(self) -> None:
        """Bearish BOS 직전 lookback 구간의 마지막 양봉을 bearish OB로 생성한다."""
        from src.analysis.smart_money.models import OrderBlockDirection, OrderBlockStatus

        rows = [
            _candle(110, 112, 108, 109),
            _candle(109, 111, 107, 108),
            _candle(106, 112, 105, 111),  # 이전 양봉이지만 마지막 양봉은 아님
            _candle(110, 111, 106, 107),
            _candle(104, 110, 103, 109),  # 마지막 양봉, OB 후보
            _candle(106, 107, 95, 96),  # bearish BOS
        ]
        df = _make_df(rows)

        result = self.fn(df, [], [_make_break("BEARISH", 5, broken_level=100.0)], lookback=5)

        self.assertEqual(len(result), 1)
        ob = result[0]
        self.assertEqual(ob.direction, OrderBlockDirection.BEARISH)
        self.assertEqual(ob.status, OrderBlockStatus.FRESH)
        self.assertEqual(ob.bar_index, 4)
        self.assertEqual(ob.break_bar_index, 5)
        self.assertAlmostEqual(ob.lower, 103.0)
        self.assertAlmostEqual(ob.upper, 110.0)

    def test_CHOCH는_오더블록을_생성하지_않음(self) -> None:
        """PR-04 범위에서는 BOS만 오더블록 생성 기준으로 사용한다."""
        rows = [
            _candle(100, 103, 99, 102),
            _candle(106, 109, 100, 101),
            _candle(104, 113, 103, 112),
        ]
        df = _make_df(rows)
        result = self.fn(df, [], [_make_break("BULLISH", 2, break_type="CHOCH")])
        self.assertEqual(result, [])

    def test_lookback_안에_반대색_캔들이_없으면_빈_리스트(self) -> None:
        """lookback 구간에 반대색 캔들이 없으면 OB를 만들지 않는다."""
        rows = [
            _candle(100, 103, 99, 102),
            _candle(102, 104, 100, 103),
            _candle(104, 113, 103, 112),
        ]
        df = _make_df(rows)
        result = self.fn(df, [], [_make_break("BULLISH", 2)], lookback=2)
        self.assertEqual(result, [])

    def test_BOS_volume이_최근_평균_이상이면_strength가_가산됨(self) -> None:
        """BOS 캔들 거래량이 직전 평균 이상이면 strength가 기본값보다 커진다."""
        rows = [
            _candle(100, 103, 99, 102, volume=1000),
            _candle(102, 104, 100, 103, volume=1000),
            _candle(106, 109, 100, 101, volume=1000),  # OB 후보
            _candle(104, 113, 103, 112, volume=2500),  # 평균 이상 BOS
        ]
        df = _make_df(rows)

        result = self.fn(df, [], [_make_break("BULLISH", 3)], lookback=3)

        self.assertEqual(len(result), 1)
        self.assertGreater(result[0].strength, 1.0)

    def test_같은_후보_캔들을_공유하는_다중_BOS는_각각_OB를_생성(self) -> None:
        """같은 후보 캔들을 공유해도 서로 다른 BOS는 각각의 OB를 유지해야 한다."""
        rows = [
            _candle(100, 103, 99, 102),
            _candle(102, 104, 100, 103),
            _candle(103, 105, 101, 104),
            _candle(104, 106, 102, 105),
            _candle(108, 109, 100, 101),  # 공통 OB 후보
            _candle(104, 113, 103, 112),  # 첫 번째 bullish BOS
            _candle(112, 116, 111, 115),  # 두 번째 bullish BOS
        ]
        df = _make_df(rows)

        breaks = [
            _make_break("BULLISH", 5, broken_level=110.0),
            _make_break("BULLISH", 6, broken_level=114.0),
        ]
        result = self.fn(df, [], breaks, lookback=6)

        self.assertEqual(len(result), 2)
        self.assertEqual([ob.bar_index for ob in result], [4, 4])
        self.assertEqual([ob.break_bar_index for ob in result], [5, 6])

    def test_StructureBreak_timestamp와_bar_index가_불일치하면_ValueError(self) -> None:
        """StructureBreak 시점 정보가 DataFrame과 맞지 않으면 명시적으로 거부한다."""
        rows = [
            _candle(100, 103, 99, 102),
            _candle(102, 104, 100, 103),
            _candle(108, 109, 100, 101),
            _candle(104, 113, 103, 112),
        ]
        df = _make_df(rows)
        broken = _make_break("BULLISH", 3)
        broken = type(broken)(
            timestamp=datetime(2024, 1, 2),
            break_type=broken.break_type,
            direction=broken.direction,
            broken_level=broken.broken_level,
            bar_index=broken.bar_index,
        )

        with self.assertRaises(ValueError):
            self.fn(df, [], [broken], lookback=3)


class TestUpdateOrderBlockStatus(unittest.TestCase):
    """update_order_block_status 함수 단위 테스트."""

    def setUp(self) -> None:
        from src.analysis.smart_money.order_blocks import (
            detect_order_blocks,
            update_order_block_status,
        )

        self.detect = detect_order_blocks
        self.update = update_order_block_status

    def _make_bullish_ob(self):
        rows = [
            _candle(100, 103, 99, 102),
            _candle(106, 109, 100, 101),  # bullish OB 후보 [100, 109]
            _candle(104, 113, 103, 112),  # bullish BOS
        ]
        df = _make_df(rows)
        obs = self.detect(df, [], [_make_break("BULLISH", 2)], lookback=2)
        self.assertEqual(len(obs), 1)
        return df, obs

    def _make_bearish_ob(self):
        rows = [
            _candle(110, 112, 108, 109),
            _candle(104, 110, 103, 109),  # bearish OB 후보 [103, 110]
            _candle(106, 107, 95, 96),  # bearish BOS
        ]
        df = _make_df(rows)
        obs = self.detect(df, [], [_make_break("BEARISH", 2, broken_level=100.0)], lookback=2)
        self.assertEqual(len(obs), 1)
        return df, obs

    def test_df_None_입력은_ValueError(self) -> None:
        """df=None은 명시적인 ValueError를 발생시킨다."""
        _, obs = self._make_bullish_ob()
        with self.assertRaises(ValueError):
            self.update(None, obs)

    def test_order_blocks_None_입력은_ValueError(self) -> None:
        """order_blocks=None은 명시적인 ValueError를 발생시킨다."""
        df, _ = self._make_bullish_ob()
        with self.assertRaises(ValueError):
            self.update(df, None)

    def test_non_DatetimeIndex_입력은_ValueError(self) -> None:
        """DatetimeIndex가 아니면 ValueError를 발생시킨다."""
        _, obs = self._make_bullish_ob()
        df = pd.DataFrame({"high": [101.0], "low": [99.0]})
        with self.assertRaises(ValueError):
            self.update(df, obs)

    def test_빈_order_blocks는_빈_리스트(self) -> None:
        """빈 오더블록 목록은 그대로 빈 리스트를 반환한다."""
        df = _make_df([_candle(100, 101, 99, 100)])
        self.assertEqual(self.update(df, []), [])

    def test_필수_컬럼_누락은_원본_상태를_반환(self) -> None:
        """상태 갱신 필수 컬럼이 없으면 원본 상태를 유지한다."""
        from src.analysis.smart_money.models import OrderBlockStatus

        df, obs = self._make_bullish_ob()
        result = self.update(df.drop(columns=["low"]), obs)
        self.assertEqual(result[0].status, OrderBlockStatus.FRESH)

    def test_bullish_OB_가격이_zone에_진입하면_MITIGATED(self) -> None:
        """Bullish OB는 break 이후 저가가 zone에 진입하면 MITIGATED가 된다."""
        from src.analysis.smart_money.models import OrderBlockStatus

        base_df, obs = self._make_bullish_ob()
        future_df = _make_df([_candle(112, 114, 105, 111)], start="2024-01-05")
        full_df = pd.concat([base_df, future_df])

        result = self.update(full_df, obs)

        self.assertEqual(result[0].status, OrderBlockStatus.MITIGATED)

    def test_bearish_OB_가격이_zone에_진입하면_MITIGATED(self) -> None:
        """Bearish OB는 break 이후 고가가 zone에 진입하면 MITIGATED가 된다."""
        from src.analysis.smart_money.models import OrderBlockStatus

        base_df, obs = self._make_bearish_ob()
        future_df = _make_df([_candle(96, 106, 94, 100)], start="2024-01-05")
        full_df = pd.concat([base_df, future_df])

        result = self.update(full_df, obs)

        self.assertEqual(result[0].status, OrderBlockStatus.MITIGATED)

    def test_bullish_OB_low_이탈은_INVALIDATED(self) -> None:
        """Bullish OB는 break 이후 저가가 zone 하단을 이탈하면 INVALIDATED가 된다."""
        from src.analysis.smart_money.models import OrderBlockStatus

        base_df, obs = self._make_bullish_ob()
        future_df = _make_df([_candle(112, 114, 99, 101)], start="2024-01-05")
        full_df = pd.concat([base_df, future_df])

        result = self.update(full_df, obs)

        self.assertEqual(result[0].status, OrderBlockStatus.INVALIDATED)

    def test_bearish_OB_high_돌파는_INVALIDATED(self) -> None:
        """Bearish OB는 break 이후 고가가 zone 상단을 돌파하면 INVALIDATED가 된다."""
        from src.analysis.smart_money.models import OrderBlockStatus

        base_df, obs = self._make_bearish_ob()
        future_df = _make_df([_candle(96, 111, 94, 109)], start="2024-01-05")
        full_df = pd.concat([base_df, future_df])

        result = self.update(full_df, obs)

        self.assertEqual(result[0].status, OrderBlockStatus.INVALIDATED)

    def test_break_확정_이전_캔들은_상태_갱신에_사용하지_않음(self) -> None:
        """OB 후보 이후이지만 BOS 이전인 캔들은 상태 갱신에서 제외한다."""
        from src.analysis.smart_money.models import OrderBlockStatus

        rows = [
            _candle(100, 103, 99, 102),
            _candle(106, 109, 100, 101),  # OB 후보 [100, 109]
            _candle(101, 108, 100, 107),  # break 전 zone 재진입, 무시해야 함
            _candle(108, 114, 107, 113),  # bullish BOS
            _candle(114, 118, 112, 117),  # break 이후 zone 미접촉
        ]
        df = _make_df(rows)
        obs = self.detect(df, [], [_make_break("BULLISH", 3)], lookback=3)

        result = self.update(df, obs)

        self.assertEqual(result[0].status, OrderBlockStatus.FRESH)

    def test_future_only_DataFrame으로_상태_갱신(self) -> None:
        """OB break 이후 캔들만 전달해도 full DataFrame과 같은 상태를 반환한다."""
        from src.analysis.smart_money.models import OrderBlockStatus

        base_df, obs = self._make_bullish_ob()
        future_df = _make_df([_candle(112, 114, 105, 111)], start="2024-01-05")

        result_future = self.update(future_df, obs)
        result_full = self.update(pd.concat([base_df, future_df]), obs)

        self.assertEqual(result_future[0].status, OrderBlockStatus.MITIGATED)
        self.assertEqual(result_future[0].status, result_full[0].status)

    def test_multi_row_future_only_DataFrame도_상태_갱신한다(self) -> None:
        """2행 이상 future-only DataFrame도 full DataFrame과 같은 결과를 반환해야 한다."""
        from src.analysis.smart_money.models import OrderBlockStatus

        base_df, obs = self._make_bullish_ob()
        future_df = _make_df(
            [
                _candle(112, 114, 111, 113),
                _candle(113, 115, 105, 111),
            ],
            start="2024-01-05",
        )

        result_future = self.update(future_df, obs)
        result_full = self.update(pd.concat([base_df, future_df]), obs)

        self.assertEqual(result_future[0].status, OrderBlockStatus.MITIGATED)
        self.assertEqual(result_future[0].status, result_full[0].status)

    def test_INVALIDATED_이후_추가_캔들은_상태를_바꾸지_않음(self) -> None:
        """INVALIDATED 이후의 캔들은 상태를 되돌리거나 변경하지 않아야 한다."""
        from src.analysis.smart_money.models import OrderBlockStatus

        base_df, obs = self._make_bullish_ob()
        future_df = _make_df(
            [
                _candle(112, 114, 99, 101),
                _candle(101, 120, 105, 118),
            ],
            start="2024-01-05",
        )
        full_df = pd.concat([base_df, future_df])

        result = self.update(full_df, obs)

        self.assertEqual(result[0].status, OrderBlockStatus.INVALIDATED)

    def test_full_DataFrame에서_break_at과_break_bar_index가_불일치하면_ValueError(self) -> None:
        """full DataFrame에서는 OrderBlock의 break 시점 정보가 일치해야 한다."""
        base_df, obs = self._make_bullish_ob()
        order_block = obs[0]
        broken_order_block = type(order_block)(
            direction=order_block.direction,
            lower=order_block.lower,
            upper=order_block.upper,
            created_at=order_block.created_at,
            bar_index=order_block.bar_index,
            break_at=datetime(2024, 1, 2),
            break_bar_index=order_block.break_bar_index,
            status=order_block.status,
            strength=order_block.strength,
        )

        with self.assertRaises(ValueError):
            self.update(base_df, [broken_order_block])

    def test_volume이_0이면_strength는_기본값을_유지한다(self) -> None:
        """BOS volume이 0이면 strength 가점을 적용하지 않는다."""
        rows = [
            _candle(100, 103, 99, 102, volume=1000),
            _candle(106, 109, 100, 101, volume=1000),
            _candle(104, 113, 103, 112, volume=0),
        ]
        df = _make_df(rows)

        obs = self.detect(df, [], [_make_break("BULLISH", 2)], lookback=2)

        self.assertEqual(len(obs), 1)
        self.assertEqual(obs[0].strength, 1.0)

    def test_volume이_NaN이면_strength는_기본값을_유지한다(self) -> None:
        """BOS volume이 NaN이어도 strength 가점을 적용하지 않는다."""
        rows = [
            _candle(100, 103, 99, 102, volume=1000),
            _candle(106, 109, 100, 101, volume=1000),
            _candle(104, 113, 103, 112, volume=1000),
        ]
        df = _make_df(rows)
        df.loc[df.index[2], "volume"] = float("nan")

        obs = self.detect(df, [], [_make_break("BULLISH", 2)], lookback=2)

        self.assertEqual(len(obs), 1)
        self.assertEqual(obs[0].strength, 1.0)


class TestOrderBlockPackageImport(unittest.TestCase):
    """smart_money 패키지의 OB public API import 검증."""

    def test_OB_public_API_import가_성공한다(self) -> None:
        """src.analysis.smart_money에서 OB public API를 import할 수 있어야 한다."""
        from src.analysis.smart_money import (  # noqa: F401
            OrderBlock,
            OrderBlockDirection,
            OrderBlockStatus,
            detect_order_blocks,
            update_order_block_status,
        )

    def test_OrderBlock_dataclass가_frozen이다(self) -> None:
        """OrderBlock은 immutable frozen dataclass여야 한다."""
        from src.analysis.smart_money.models import (
            OrderBlock,
            OrderBlockDirection,
            OrderBlockStatus,
        )

        ob = OrderBlock(
            direction=OrderBlockDirection.BULLISH,
            lower=100.0,
            upper=109.0,
            created_at=datetime(2024, 1, 3),
            bar_index=1,
            break_at=datetime(2024, 1, 4),
            break_bar_index=2,
            status=OrderBlockStatus.FRESH,
            strength=1.0,
        )
        with self.assertRaises((AttributeError, TypeError)):
            ob.lower = 999.0  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
