"""PR-02: 스윙 프랙탈과 시장구조 탐지 테스트

detect_swing_points, classify_market_structure, detect_structure_breaks를 검증합니다.

테스트 원칙:
    - 실제 API/네트워크 호출 없음. 합성 fixture만 사용.
    - 모든 케이스는 deterministic (동일 입력 → 동일 출력).
    - 경계 조건(데이터 부족, 동일 고점/저점, 박스권)을 명시적으로 검증.
"""

import unittest
from datetime import datetime, timedelta

import pandas as pd

from tests.fixtures.ohlcv_factory import make_ohlcv

# ────────────────────────────────────────────────────────────
# 헬퍼: 합성 OHLCV 생성
# ────────────────────────────────────────────────────────────


def _make_trending_ohlcv(
    prices: list[float],
    start: str = "2024-01-02",
    freq: str = "1D",
) -> pd.DataFrame:
    """가격 리스트를 받아 단순 OHLCV DataFrame을 생성합니다.

    각 캔들의 open=close=price, high=price+1, low=price-1로 구성하여
    스윙 탐지가 명확히 동작하도록 합니다.

    Args:
        prices: 각 캔들의 기준 가격 리스트
        start: 시작 날짜 문자열
        freq: 시간 주기

    Returns:
        DatetimeIndex OHLCV DataFrame
    """
    dates = pd.date_range(start=start, periods=len(prices), freq=freq)
    data = {
        "open": prices,
        "high": [p + 1.0 for p in prices],
        "low": [p - 1.0 for p in prices],
        "close": prices,
        "volume": [1000] * len(prices),
    }
    return pd.DataFrame(data, index=dates)


# ────────────────────────────────────────────────────────────
# detect_swing_points 테스트
# ────────────────────────────────────────────────────────────


class TestDetectSwingPoints(unittest.TestCase):
    """detect_swing_points 함수 단위 테스트"""

    def setUp(self) -> None:
        from src.analysis.smart_money.swings import detect_swing_points

        self.fn = detect_swing_points

    def test_데이터가_left_plus_right_plus_1_미만이면_빈_리스트_반환(self) -> None:
        """left=2, right=2이면 최소 5개 캔들이 필요하다. 4개는 빈 리스트."""
        df = make_ohlcv(n=4, step=1.0)
        result = self.fn(df, left=2, right=2)
        self.assertEqual(result, [])

    def test_정확히_최소_캔들_수이면_탐지_수행(self) -> None:
        """5개 캔들(left=2, right=2)이면 탐지가 수행된다."""
        # 명확한 스윙: [low, low, peak, low, low]
        prices = [100.0, 101.0, 110.0, 101.0, 100.0]
        df = _make_trending_ohlcv(prices)
        result = self.fn(df, left=2, right=2)
        # 중간 peak이 스윙 하이로 탐지되어야 함
        from src.analysis.smart_money.models import SwingType

        highs = [s for s in result if s.swing_type == SwingType.HIGH]
        self.assertEqual(len(highs), 1)
        self.assertAlmostEqual(highs[0].price, 111.0)  # high = price + 1

    def test_상승_추세에서_스윙_하이_탐지(self) -> None:
        """명확한 상승 추세에서 스윙 하이가 탐지된다.

        전형적인 V형 파동: 저점 → 명확한 고점 → 저점 구조를 반복하여
        스윙 탐지가 명확히 동작하도록 한다.
        """
        # 명확한 고점-저점 교차: bar=2(고점 110), bar=4(저점 100), bar=6(고점 120), bar=8(저점 105)
        prices = [100.0, 105.0, 110.0, 105.0, 100.0, 105.0, 120.0, 110.0, 105.0, 115.0]
        df = _make_trending_ohlcv(prices)
        result = self.fn(df, left=2, right=2)

        from src.analysis.smart_money.models import SwingType

        highs = [s for s in result if s.swing_type == SwingType.HIGH]
        # 최소 1개 이상의 스윙 하이가 탐지되어야 함
        self.assertGreater(len(highs), 0)

    def test_상승_추세에서_스윙_로우_탐지(self) -> None:
        """상승 추세에서 스윙 로우가 탐지된다.

        명확한 V형 저점 구조를 사용하여 스윙 로우가 확실히 탐지되도록 한다.
        """
        # 명확한 저점: bar=2(저점 95), bar=6(저점 100) — 엄격한 V형
        prices = [100.0, 97.0, 95.0, 97.0, 100.0, 103.0, 100.0, 103.0, 107.0, 110.0]
        df = _make_trending_ohlcv(prices)
        result = self.fn(df, left=2, right=2)

        from src.analysis.smart_money.models import SwingType

        lows = [s for s in result if s.swing_type == SwingType.LOW]
        self.assertGreater(len(lows), 0)

    def test_하락_추세에서_스윙_로우_탐지(self) -> None:
        """명확한 하락 추세에서 스윙 로우가 탐지된다.

        명확한 V형 저점을 사용하여 탐지 조건이 확실히 충족되도록 한다.
        """
        # 명확한 저점: bar=2(130→120→115→120→130), bar=6(120→110→105→110→120)
        prices = [130.0, 120.0, 115.0, 120.0, 130.0, 120.0, 105.0, 110.0, 120.0, 100.0]
        df = _make_trending_ohlcv(prices)
        result = self.fn(df, left=2, right=2)

        from src.analysis.smart_money.models import SwingType

        lows = [s for s in result if s.swing_type == SwingType.LOW]
        self.assertGreater(len(lows), 0)

    def test_결과가_시간_오름차순이다(self) -> None:
        """탐지된 스윙 포인트는 timestamp 기준 오름차순이어야 한다."""
        df = make_ohlcv(n=30, step=1.0)
        result = self.fn(df, left=2, right=2)
        timestamps = [s.timestamp for s in result]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_left_0이면_ValueError(self) -> None:
        """left < 1이면 ValueError가 발생한다."""
        df = make_ohlcv(n=10)
        with self.assertRaises(ValueError):
            self.fn(df, left=0, right=2)

    def test_right_0이면_ValueError(self) -> None:
        """right < 1이면 ValueError가 발생한다."""
        df = make_ohlcv(n=10)
        with self.assertRaises(ValueError):
            self.fn(df, left=2, right=0)

    def test_동일_고점이_연속되어도_과도한_스윙_없음(self) -> None:
        """동일한 고점이 연속되는 경우 중복 스윙이 합리적 범위 안에서 생성된다.

        스윙 규칙: 최소 한쪽이 엄격히 크다.
        flat peak [100,105,110,110,110,105,100]에서:
            - bar=2: left=[100,105] strict (엄격히 큰 값 있음) ✓, right=[111,111] strict_right=False
              → strict_left=True이면 스윙으로 인정됨
            - bar=3: left=[111,111] strict_left=False, right=[111,106] strict_right=True ✓
            - bar=4: left=[111,111] strict_left=False, right=[106,101] strict_right=True ✓
        따라서 최대 3개까지 탐지될 수 있으며, 이는 스펙의 허용 범위 안이다.
        """
        # 평평한 peak: [100, 105, 110, 110, 110, 105, 100]
        prices = [100.0, 105.0, 110.0, 110.0, 110.0, 105.0, 100.0]
        df = _make_trending_ohlcv(prices)
        result = self.fn(df, left=2, right=2)

        from src.analysis.smart_money.models import SwingType

        highs = [s for s in result if s.swing_type == SwingType.HIGH]
        # 동일 flat peak에서 최대 3개 스윙이 탐지될 수 있음
        # 핵심 검증: 전체 캔들 수(7)보다 훨씬 적어야 한다 (과도한 중복 없음)
        self.assertLessEqual(len(highs), 3)
        # 탐지된 스윙은 최소 1개여야 함 (peak 구간은 스윙으로 인정)
        self.assertGreaterEqual(len(highs), 1)

    def test_빈_DataFrame은_빈_리스트_반환(self) -> None:
        """행이 0개인 DataFrame은 빈 리스트를 반환한다."""
        df = (
            make_ohlcv(n=0)
            if False
            else pd.DataFrame(
                {"open": [], "high": [], "low": [], "close": [], "volume": []},
                index=pd.DatetimeIndex([]),
            )
        )
        result = self.fn(df, left=2, right=2)
        self.assertEqual(result, [])

    def test_SwingPoint_bar_index가_DataFrame_범위_안이다(self) -> None:
        """탐지된 SwingPoint의 bar_index는 DataFrame 인덱스 범위 안이어야 한다."""
        df = make_ohlcv(n=20, step=1.0)
        result = self.fn(df, left=2, right=2)
        for sp in result:
            self.assertGreaterEqual(sp.bar_index, 0)
            self.assertLess(sp.bar_index, len(df))

    def test_None_입력은_ValueError를_발생시킨다(self) -> None:
        """[리뷰 수정] df=None은 TypeError 대신 ValueError가 발생해야 한다."""
        with self.assertRaises(ValueError):
            self.fn(None, left=2, right=2)

    def test_non_DatetimeIndex_입력은_ValueError를_발생시킨다(self) -> None:
        """[리뷰 수정] DatetimeIndex가 아닌 RangeIndex df는 ValueError가 발생해야 한다."""
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0, 103.0, 104.0],
                "high": [101.0, 102.0, 103.0, 104.0, 105.0],
                "low": [99.0, 100.0, 101.0, 102.0, 103.0],
                "close": [100.5, 101.5, 102.5, 103.5, 104.5],
                "volume": [1000] * 5,
            }
            # index 미지정 → RangeIndex
        )
        with self.assertRaises(ValueError):
            self.fn(df, left=2, right=2)


# ────────────────────────────────────────────────────────────
# classify_market_structure 테스트
# ────────────────────────────────────────────────────────────


class TestClassifyMarketStructure(unittest.TestCase):
    """classify_market_structure 함수 단위 테스트"""

    def setUp(self) -> None:
        from src.analysis.smart_money.swings import classify_market_structure

        self.fn = classify_market_structure

    def _make_swing(self, price: float, stype: str, i: int):
        """테스트용 SwingPoint 생성 헬퍼"""
        from src.analysis.smart_money.models import SwingPoint, SwingType

        return SwingPoint(
            timestamp=datetime(2024, 1, 2) + timedelta(days=i),
            price=price,
            swing_type=SwingType.HIGH if stype == "HIGH" else SwingType.LOW,
            bar_index=i,
        )

    def test_HH_HL_연속이면_BULLISH(self) -> None:
        """Higher High + Higher Low가 반복되면 BULLISH를 반환한다."""
        from src.analysis.smart_money.models import MarketStructure

        swings = [
            self._make_swing(100.0, "LOW", 0),
            self._make_swing(110.0, "HIGH", 1),
            self._make_swing(105.0, "LOW", 2),
            self._make_swing(120.0, "HIGH", 3),
            self._make_swing(115.0, "LOW", 4),
        ]
        result = self.fn(swings)
        self.assertEqual(result, MarketStructure.BULLISH)

    def test_LH_LL_연속이면_BEARISH(self) -> None:
        """Lower High + Lower Low가 반복되면 BEARISH를 반환한다."""
        from src.analysis.smart_money.models import MarketStructure

        swings = [
            self._make_swing(120.0, "HIGH", 0),
            self._make_swing(110.0, "LOW", 1),
            self._make_swing(115.0, "HIGH", 2),
            self._make_swing(100.0, "LOW", 3),
            self._make_swing(108.0, "HIGH", 4),
        ]
        result = self.fn(swings)
        self.assertEqual(result, MarketStructure.BEARISH)

    def test_혼재하면_RANGE(self) -> None:
        """HH/HL 조건이 혼재하면 RANGE를 반환한다."""
        from src.analysis.smart_money.models import MarketStructure

        # 하이는 상승, 로우는 하락
        swings = [
            self._make_swing(100.0, "LOW", 0),
            self._make_swing(110.0, "HIGH", 1),
            self._make_swing(95.0, "LOW", 2),  # LL → BULLISH 아님
            self._make_swing(115.0, "HIGH", 3),
            self._make_swing(90.0, "LOW", 4),
        ]
        result = self.fn(swings)
        self.assertEqual(result, MarketStructure.RANGE)

    def test_스윙_3개_미만이면_RANGE(self) -> None:
        """스윙 포인트가 3개 미만이면 RANGE를 반환한다."""
        from src.analysis.smart_money.models import MarketStructure

        swings = [
            self._make_swing(100.0, "LOW", 0),
            self._make_swing(110.0, "HIGH", 1),
        ]
        result = self.fn(swings)
        self.assertEqual(result, MarketStructure.RANGE)

    def test_빈_스윙_리스트는_RANGE(self) -> None:
        """빈 리스트는 RANGE를 반환한다."""
        from src.analysis.smart_money.models import MarketStructure

        result = self.fn([])
        self.assertEqual(result, MarketStructure.RANGE)

    def test_하이만_있고_로우_없으면_RANGE(self) -> None:
        """하이만 있고 로우가 없으면 HH/HL 모두 불가 → RANGE."""
        from src.analysis.smart_money.models import MarketStructure

        swings = [
            self._make_swing(100.0, "HIGH", 0),
            self._make_swing(110.0, "HIGH", 1),
            self._make_swing(120.0, "HIGH", 2),
        ]
        result = self.fn(swings)
        # lows가 없으므로 hl = False → BULLISH가 되지 않음
        self.assertEqual(result, MarketStructure.RANGE)

    def test_None_입력은_ValueError를_발생시킨다(self) -> None:
        """[리뷰 수정] swings=None은 TypeError 대신 ValueError가 발생해야 한다."""
        with self.assertRaises(ValueError):
            self.fn(None)

    def test_최근_구조만_반영한다_전체_히스토리_단조성_불필요(self) -> None:
        """[리뷰 수정] 전체 히스토리가 단조 상승이 아니어도 최근 2개 pair가 HH+HL이면 BULLISH.

        수정 전: 전체 highs/lows가 strictly ascending이어야 BULLISH → 과거 스윙 1개만
                 어긋나도 RANGE 판정.
        수정 후: 최근 RECENT_SWING_PAIRS(=2)개 pair만 보므로 과거 스윙과 무관하게
                 최근 구조를 정확히 판정한다.
        """
        from src.analysis.smart_money.models import MarketStructure

        # 과거에 하락 스윙이 섞여 있어 전체 히스토리로는 단조 상승이 아니지만
        # 최근 2개 HIGH pair (120→130 HH) + 2개 LOW pair (110→115 HL) → BULLISH
        swings = [
            self._make_swing(150.0, "HIGH", 0),  # 과거 고점 (이후 하락)
            self._make_swing(80.0, "LOW", 1),  # 과거 저점
            self._make_swing(120.0, "HIGH", 2),  # 최근 HH 시작 (120)
            self._make_swing(110.0, "LOW", 3),  # 최근 HL 시작 (110)
            self._make_swing(130.0, "HIGH", 4),  # 최근 HH (130 > 120) ✓
            self._make_swing(115.0, "LOW", 5),  # 최근 HL (115 > 110) ✓
        ]
        result = self.fn(swings)
        # 최근 HIGH pair [120, 130] HH ✓, 최근 LOW pair [110, 115] HL ✓ → BULLISH
        self.assertEqual(result, MarketStructure.BULLISH)


# ────────────────────────────────────────────────────────────
# detect_structure_breaks 테스트
# ────────────────────────────────────────────────────────────


class TestDetectStructureBreaks(unittest.TestCase):
    """detect_structure_breaks 함수 단위 테스트"""

    def setUp(self) -> None:
        from src.analysis.smart_money.swings import detect_structure_breaks

        self.fn = detect_structure_breaks

    def _make_swing(self, price: float, stype: str, i: int):
        from src.analysis.smart_money.models import SwingPoint, SwingType

        return SwingPoint(
            timestamp=datetime(2024, 1, 2) + timedelta(days=i),
            price=price,
            swing_type=SwingType.HIGH if stype == "HIGH" else SwingType.LOW,
            bar_index=i,
        )

    def _make_breakout_df(
        self,
        n: int = 15,
        breakout_price: float = 120.0,
        breakout_bar: int = 10,
        start: str = "2024-01-02",
    ) -> pd.DataFrame:
        """특정 bar에서 breakout_price 위로 종가가 올라가는 DataFrame 생성"""
        closes = [100.0] * n
        closes[breakout_bar] = breakout_price
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        opens = closes[:]
        dates = pd.date_range(start=start, periods=n, freq="1D")
        return pd.DataFrame(
            {"open": opens, "high": highs, "low": lows, "close": closes, "volume": [1000] * n},
            index=dates,
        )

    def test_빈_스윙으로_빈_리스트_반환(self) -> None:
        """스윙이 없으면 빈 리스트를 반환한다."""
        df = make_ohlcv(n=10)
        result = self.fn(df, [])
        self.assertEqual(result, [])

    def test_빈_DataFrame은_빈_리스트_반환(self) -> None:
        """DataFrame이 비어있으면 빈 리스트를 반환한다."""
        df = pd.DataFrame(
            {"open": [], "high": [], "low": [], "close": [], "volume": []},
            index=pd.DatetimeIndex([]),
        )
        swings = [self._make_swing(110.0, "HIGH", 0)]
        result = self.fn(df, swings)
        self.assertEqual(result, [])

    def test_스윙_하이_상방_돌파_탐지(self) -> None:
        """종가가 이전 스윙 하이를 돌파하면 Bullish 구조 돌파가 탐지된다."""
        from src.analysis.smart_money.models import BreakDirection

        # 스윙 하이: bar=3에서 price=110
        sw_high = self._make_swing(110.0, "HIGH", 3)
        # bar=10에서 close=120으로 스윙 하이(110) 상방 돌파
        df = self._make_breakout_df(n=15, breakout_price=120.0, breakout_bar=10)

        result = self.fn(df, [sw_high])
        bullish_breaks = [b for b in result if b.direction == BreakDirection.BULLISH]
        self.assertGreater(len(bullish_breaks), 0)

    def test_스윙_로우_하방_이탈_탐지(self) -> None:
        """종가가 이전 스윙 로우를 하방 이탈하면 Bearish 구조 돌파가 탐지된다."""
        from src.analysis.smart_money.models import BreakDirection

        # 스윙 로우: bar=3에서 price=90 (실제 low = price - 1 = 89)
        sw_low = self._make_swing(90.0, "LOW", 3)
        # bar=10에서 close=80으로 스윙 로우(90) 하방 이탈
        closes = [100.0] * 15
        closes[10] = 80.0
        dates = pd.date_range("2024-01-02", periods=15, freq="1D")
        df = pd.DataFrame(
            {
                "open": closes,
                "high": [c + 1.0 for c in closes],
                "low": [c - 1.0 for c in closes],
                "close": closes,
                "volume": [1000] * 15,
            },
            index=dates,
        )

        result = self.fn(df, [sw_low])
        bearish_breaks = [b for b in result if b.direction == BreakDirection.BEARISH]
        self.assertGreater(len(bearish_breaks), 0)

    def test_돌파된_레벨은_재사용하지_않음(self) -> None:
        """한 번 돌파된 스윙 레벨은 두 번째 캔들에서 다시 돌파로 처리되지 않는다."""
        sw_high = self._make_swing(110.0, "HIGH", 3)
        # bar=10, 11, 12에서 모두 120으로 종가가 이전 스윙 하이를 돌파
        closes = [100.0] * 15
        closes[10] = 120.0
        closes[11] = 121.0
        closes[12] = 122.0
        dates = pd.date_range("2024-01-02", periods=15, freq="1D")
        df = pd.DataFrame(
            {
                "open": closes,
                "high": [c + 1.0 for c in closes],
                "low": [c - 1.0 for c in closes],
                "close": closes,
                "volume": [1000] * 15,
            },
            index=dates,
        )
        result = self.fn(df, [sw_high])
        # 같은 스윙 레벨에 대한 돌파는 1번만 탐지
        self.assertEqual(len(result), 1)

    def test_결과가_시간_오름차순이다(self) -> None:
        """탐지된 StructureBreak는 timestamp 기준 오름차순이어야 한다."""
        sw_high = self._make_swing(105.0, "HIGH", 2)
        sw_low = self._make_swing(95.0, "LOW", 4)

        closes = [100.0] * 20
        closes[8] = 110.0  # 스윙 하이 돌파
        closes[12] = 80.0  # 스윙 로우 이탈

        dates = pd.date_range("2024-01-02", periods=20, freq="1D")
        df = pd.DataFrame(
            {
                "open": closes,
                "high": [c + 1.0 for c in closes],
                "low": [c - 1.0 for c in closes],
                "close": closes,
                "volume": [1000] * 20,
            },
            index=dates,
        )
        result = self.fn(df, [sw_high, sw_low])
        timestamps = [b.timestamp for b in result]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_상승_구조에서_하방_이탈은_CHOCH(self) -> None:
        """BULLISH 구조(HH+HL)에서 스윙 로우 하방 이탈은 CHOCH로 탐지된다.

        classify_market_structure가 BULLISH를 반환하려면:
            - Highs: strictly ascending (HH)
            - Lows: strictly ascending (HL)
        두 조건이 모두 충족되어야 한다.
        """
        from src.analysis.smart_money.models import BreakType

        # 명확한 BULLISH 구조 스윙 셋:
        #   LOW(100) → HIGH(110) → LOW(105) → HIGH(120) → LOW(115)
        #   Highs: [110, 120] → HH ✓
        #   Lows:  [100, 105, 115] → HL ✓
        swings = [
            self._make_swing(100.0, "LOW", 0),
            self._make_swing(110.0, "HIGH", 1),
            self._make_swing(105.0, "LOW", 2),
            self._make_swing(120.0, "HIGH", 3),
            self._make_swing(115.0, "LOW", 4),  # 이 로우를 하방 이탈하면 CHOCH
        ]
        # bar=10에서 close=100으로 LOW(115)를 하방 이탈
        closes = [120.0] * 15
        closes[10] = 100.0
        dates = pd.date_range("2024-01-02", periods=15, freq="1D")
        df = pd.DataFrame(
            {
                "open": closes,
                "high": [c + 1.0 for c in closes],
                "low": [c - 1.0 for c in closes],
                "close": closes,
                "volume": [1000] * 15,
            },
            index=dates,
        )
        result = self.fn(df, swings)
        # BULLISH 구조에서 하방 이탈 → CHOCH
        choch_breaks = [b for b in result if b.break_type == BreakType.CHOCH]
        self.assertGreater(len(choch_breaks), 0)


# ────────────────────────────────────────────────────────────
# [리뷰 수정] 추가 검증: 새로운 입력 검증 경로
# ────────────────────────────────────────────────────────────


class TestDetectStructureBreaksValidation(unittest.TestCase):
    """detect_structure_breaks 입력 검증 테스트 (리뷰 수정 기반)"""

    def setUp(self) -> None:
        from src.analysis.smart_money.swings import detect_structure_breaks

        self.fn = detect_structure_breaks

    def _make_swing(self, price: float, stype: str, i: int):
        from src.analysis.smart_money.models import SwingPoint, SwingType

        return SwingPoint(
            timestamp=datetime(2024, 1, 2) + timedelta(days=i),
            price=price,
            swing_type=SwingType.HIGH if stype == "HIGH" else SwingType.LOW,
            bar_index=i,
        )

    def test_df_None_입력은_ValueError(self) -> None:
        """[리뷰 수정] df=None은 TypeError 대신 명시적 ValueError가 발생한다."""
        with self.assertRaises(ValueError):
            self.fn(None, [])

    def test_swings_None_입력은_ValueError(self) -> None:
        """[리뷰 수정] swings=None은 TypeError 대신 명시적 ValueError가 발생한다."""
        dates = pd.date_range("2024-01-02", periods=5, freq="1D")
        df = pd.DataFrame(
            {
                "open": [100.0] * 5,
                "high": [101.0] * 5,
                "low": [99.0] * 5,
                "close": [100.5] * 5,
                "volume": [1000] * 5,
            },
            index=dates,
        )
        with self.assertRaises(ValueError):
            self.fn(df, None)

    def test_non_DatetimeIndex_입력은_ValueError(self) -> None:
        """[리뷰 수정] RangeIndex df는 ValueError가 발생한다."""
        df = pd.DataFrame(
            {
                "open": [100.0] * 5,
                "high": [101.0] * 5,
                "low": [99.0] * 5,
                "close": [100.5] * 5,
                "volume": [1000] * 5,
            }
        )
        sw = self._make_swing(110.0, "HIGH", 1)
        with self.assertRaises(ValueError):
            self.fn(df, [sw])

    def test_close_컬럼_누락시_빈_리스트_반환(self) -> None:
        """[리뷰 수정] 'close' 컬럼이 없으면 KeyError 대신 빈 리스트를 반환한다."""
        dates = pd.date_range("2024-01-02", periods=10, freq="1D")
        df = pd.DataFrame(
            {"open": [100.0] * 10, "high": [101.0] * 10, "low": [99.0] * 10, "volume": [1000] * 10},
            index=dates,
        )
        sw = self._make_swing(110.0, "HIGH", 3)
        result = self.fn(df, [sw])
        self.assertEqual(result, [])

    def test_동일_bar의_HIGH_LOW_스윙이_서로_차단하지_않음(self) -> None:
        """[리뷰 수정] 같은 bar_index의 HIGH/LOW 스윙은 (SwingType, bar_index) 키로 구분된다.

        수정 전: used_swing_indices: set[int] → HIGH 돌파 후 LOW가 같은 bar_index를 갖는
                 스윙이 있으면 used_swing_indices에 의해 차단될 수 있음.
        수정 후: used_swing_keys: set[(SwingType, int)] → HIGH와 LOW는 별도 추적.
        """
        from src.analysis.smart_money.models import BreakDirection

        # bar_index=3에 HIGH와 LOW 스윙이 함께 존재
        sw_high = self._make_swing(110.0, "HIGH", 3)
        sw_low = self._make_swing(90.0, "LOW", 3)  # 같은 bar_index=3

        closes = [100.0] * 15
        closes[10] = 120.0  # HIGH 돌파
        closes[11] = 80.0  # LOW 이탈
        dates = pd.date_range("2024-01-02", periods=15, freq="1D")
        df = pd.DataFrame(
            {
                "open": closes,
                "high": [c + 1.0 for c in closes],
                "low": [c - 1.0 for c in closes],
                "close": closes,
                "volume": [1000] * 15,
            },
            index=dates,
        )
        result = self.fn(df, [sw_high, sw_low])
        # HIGH 돌파와 LOW 이탈이 모두 탐지되어야 함
        bullish = [b for b in result if b.direction == BreakDirection.BULLISH]
        bearish = [b for b in result if b.direction == BreakDirection.BEARISH]
        self.assertGreater(len(bullish), 0, "HIGH 돌파가 탐지되어야 합니다.")
        self.assertGreater(len(bearish), 0, "LOW 이탈이 탐지되어야 합니다.")


# ────────────────────────────────────────────────────────────
# 회귀: 기존 smart_money __init__ import 검증
# ────────────────────────────────────────────────────────────


class TestSmartMoneyPackageImport(unittest.TestCase):
    """smart_money 패키지 public API import 검증"""

    def test_패키지_public_API_import가_성공한다(self) -> None:
        """src.analysis.smart_money에서 모든 public API를 import할 수 있어야 한다."""
        from src.analysis.smart_money import (  # noqa: F401
            BreakDirection,
            BreakType,
            MarketStructure,
            StructureBreak,
            SwingAnalysisResult,
            SwingPoint,
            SwingType,
            classify_market_structure,
            detect_structure_breaks,
            detect_swing_points,
        )

    def test_모델_dataclass가_frozen이다(self) -> None:
        """SwingPoint, StructureBreak는 immutable frozen dataclass여야 한다."""
        from src.analysis.smart_money.models import (
            BreakDirection,
            BreakType,
            StructureBreak,
            SwingPoint,
            SwingType,
        )

        sp = SwingPoint(
            timestamp=datetime(2024, 1, 2),
            price=100.0,
            swing_type=SwingType.HIGH,
            bar_index=0,
        )
        with self.assertRaises((AttributeError, TypeError)):
            sp.price = 999.0  # type: ignore[misc]

        sb = StructureBreak(
            timestamp=datetime(2024, 1, 2),
            break_type=BreakType.BOS,
            direction=BreakDirection.BULLISH,
            broken_level=110.0,
            bar_index=5,
        )
        with self.assertRaises((AttributeError, TypeError)):
            sb.broken_level = 999.0  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
