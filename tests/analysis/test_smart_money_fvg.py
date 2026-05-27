"""PR-03: Fair Value Gap 탐지 테스트

detect_fvgs, update_fvg_status 함수를 검증합니다.

테스트 원칙:
    - 실제 API/네트워크 호출 없음. 합성 fixture만 사용.
    - 모든 케이스는 deterministic (동일 입력 → 동일 출력).
    - 경계 조건(데이터 부족, min_gap_pct 미달, 상태 전환)을 명시적으로 검증.
"""

import unittest
from datetime import datetime, timedelta

import pandas as pd


def _make_df(rows: list[dict], start: str = "2024-01-02", freq: str = "1D") -> pd.DataFrame:
    """테스트용 OHLCV DataFrame 생성 헬퍼."""
    dates = pd.date_range(start=start, periods=len(rows), freq=freq)
    data = {
        "open": [r["open"] for r in rows],
        "high": [r["high"] for r in rows],
        "low": [r["low"] for r in rows],
        "close": [r["close"] for r in rows],
        "volume": [r.get("volume", 1000) for r in rows],
    }
    return pd.DataFrame(data, index=dates)


def _candle(o: float, h: float, lo: float, c: float) -> dict:
    """캔들 딕셔너리 생성 헬퍼."""
    return {"open": o, "high": h, "low": lo, "close": c}


class TestDetectFVGs(unittest.TestCase):
    """detect_fvgs 함수 단위 테스트"""

    def setUp(self) -> None:
        from src.analysis.smart_money.fvg import detect_fvgs

        self.fn = detect_fvgs

    # ── 입력 검증 ─────────────────────────────────────────────

    def test_None_입력은_ValueError(self) -> None:
        with self.assertRaises(ValueError):
            self.fn(None)

    def test_non_DatetimeIndex_입력은_ValueError(self) -> None:
        df = pd.DataFrame(
            {
                "open": [100.0] * 5,
                "high": [101.0] * 5,
                "low": [99.0] * 5,
                "close": [100.0] * 5,
                "volume": [1000] * 5,
            }
        )
        with self.assertRaises(ValueError):
            self.fn(df)

    def test_min_gap_pct_음수는_ValueError(self) -> None:
        dates = pd.date_range("2024-01-02", periods=5, freq="1D")
        df = pd.DataFrame(
            {
                "open": [100.0] * 5,
                "high": [101.0] * 5,
                "low": [99.0] * 5,
                "close": [100.0] * 5,
                "volume": [1000] * 5,
            },
            index=dates,
        )
        with self.assertRaises(ValueError):
            self.fn(df, min_gap_pct=-0.001)

    def test_캔들_3개_미만이면_빈_리스트(self) -> None:
        dates = pd.date_range("2024-01-02", periods=2, freq="1D")
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0],
                "high": [101.0, 102.0],
                "low": [99.0, 100.0],
                "close": [100.0, 101.0],
                "volume": [1000, 1000],
            },
            index=dates,
        )
        self.assertEqual(self.fn(df), [])

    def test_필수_컬럼_누락시_빈_리스트(self) -> None:
        dates = pd.date_range("2024-01-02", periods=5, freq="1D")
        df = pd.DataFrame(
            {
                "open": [100.0] * 5,
                "high": [101.0] * 5,
                "volume": [1000] * 5,
            },
            index=dates,
        )
        self.assertEqual(self.fn(df), [])

    # ── Bullish FVG 탐지 ──────────────────────────────────────

    def test_bullish_FVG_1개_탐지(self) -> None:
        """캔들 i-2의 high < 캔들 i의 low → Bullish FVG 탐지."""
        from src.analysis.smart_money.models import FVGDirection, FVGStatus

        # 캔들 0: high=100, 캔들 1: 중간, 캔들 2: low=110 → gap [100, 110]
        rows = [
            _candle(98, 100, 97, 99),  # i-2: high=100
            _candle(102, 105, 101, 103),  # i-1: 중간 (gap 내부)
            _candle(111, 115, 110, 112),  # i: low=110 > high[i-2]=100 → Bullish FVG
        ]
        df = _make_df(rows)
        result = self.fn(df, min_gap_pct=0.001)

        self.assertEqual(len(result), 1)
        fvg = result[0]
        self.assertEqual(fvg.direction, FVGDirection.BULLISH)
        self.assertAlmostEqual(fvg.lower, 100.0)
        self.assertAlmostEqual(fvg.upper, 110.0)
        self.assertEqual(fvg.status, FVGStatus.OPEN)
        self.assertEqual(fvg.bar_index, 2)

    # ── Bearish FVG 탐지 ──────────────────────────────────────

    def test_bearish_FVG_1개_탐지(self) -> None:
        """캔들 i-2의 low > 캔들 i의 high → Bearish FVG 탐지."""
        from src.analysis.smart_money.models import FVGDirection, FVGStatus

        # 캔들 0: low=110, 캔들 2: high=100 → gap [100, 110]
        rows = [
            _candle(115, 118, 110, 112),  # i-2: low=110
            _candle(107, 112, 105, 108),  # i-1: 중간
            _candle(98, 100, 95, 97),  # i: high=100 < low[i-2]=110 → Bearish FVG
        ]
        df = _make_df(rows)
        result = self.fn(df, min_gap_pct=0.001)

        self.assertEqual(len(result), 1)
        fvg = result[0]
        self.assertEqual(fvg.direction, FVGDirection.BEARISH)
        self.assertAlmostEqual(fvg.lower, 100.0)
        self.assertAlmostEqual(fvg.upper, 110.0)
        self.assertEqual(fvg.status, FVGStatus.OPEN)
        self.assertEqual(fvg.bar_index, 2)

    # ── min_gap_pct 필터 ──────────────────────────────────────

    def test_min_gap_미달이면_무시(self) -> None:
        """gap_size / close < min_gap_pct 이면 FVG를 반환하지 않는다."""
        # gap = 0.01 (100.00 → 100.01), close ≈ 100 → ratio ≈ 0.0001 < 0.001
        rows = [
            _candle(99.98, 100.00, 99.97, 99.99),  # i-2: high=100.00
            _candle(100.00, 100.05, 99.99, 100.02),  # i-1
            _candle(100.01, 100.10, 100.01, 100.05),  # i: low=100.01 → gap=0.01
        ]
        df = _make_df(rows)
        result = self.fn(df, min_gap_pct=0.001)
        self.assertEqual(result, [])

    def test_min_gap_pct_0이면_모두_탐지(self) -> None:
        """min_gap_pct=0이면 아주 작은 갭도 탐지한다."""
        rows = [
            _candle(99.98, 100.00, 99.97, 99.99),
            _candle(100.00, 100.05, 99.99, 100.02),
            _candle(100.01, 100.10, 100.01, 100.05),
        ]
        df = _make_df(rows)
        result = self.fn(df, min_gap_pct=0.0)
        self.assertEqual(len(result), 1)

    # ── 여러 FVG ──────────────────────────────────────────────

    def test_여러_FVG가_겹쳐도_시간순_반환(self) -> None:
        """[리뷰 수정] 여러 FVG가 탐지될 때 개수/방향/시간 오름차순을 정확히 검증한다.

        탐지 결과 (실측):
            bar_index=2: Bullish FVG [high[0]=100, low[2]=110]
            bar_index=3: Bullish FVG [high[1]=105, low[3]=106]  ← bar1.high < bar3.low
            bar_index=4: Bearish FVG [high[4]=100, low[2]=110]  ← bar2.low(=110) > bar4.high(=100)
        """
        from src.analysis.smart_money.models import FVGDirection

        rows = [
            _candle(98, 100, 97, 99),  # 0: high=100, low=97
            _candle(102, 105, 101, 103),  # 1: high=105, low=101
            _candle(111, 115, 110, 112),  # 2: high=115, low=110
            _candle(108, 111, 106, 109),  # 3: high=111, low=106
            _candle(98, 100, 95, 97),  # 4: high=100, low=95
        ]
        df = _make_df(rows)
        result = self.fn(df, min_gap_pct=0.001)

        # 정확히 3개의 FVG가 탐지되어야 한다
        self.assertEqual(len(result), 3, f"FVG 3개 기대, 실제: {len(result)}")
        # bar_index=2: Bullish [100, 110]
        self.assertEqual(result[0].direction, FVGDirection.BULLISH)
        self.assertEqual(result[0].bar_index, 2)
        self.assertAlmostEqual(result[0].lower, 100.0)
        self.assertAlmostEqual(result[0].upper, 110.0)
        # bar_index=3: Bullish [105, 106]
        self.assertEqual(result[1].direction, FVGDirection.BULLISH)
        self.assertEqual(result[1].bar_index, 3)
        self.assertAlmostEqual(result[1].lower, 105.0)
        self.assertAlmostEqual(result[1].upper, 106.0)
        # bar_index=4: Bearish [100, 110]  ← bar2.low=110 > bar4.high=100
        self.assertEqual(result[2].direction, FVGDirection.BEARISH)
        self.assertEqual(result[2].bar_index, 4)
        self.assertAlmostEqual(result[2].lower, 100.0)
        self.assertAlmostEqual(result[2].upper, 110.0)

    def test_FVG_없는_데이터는_빈_리스트(self) -> None:
        """인접 캔들이 겹치면 FVG가 없어야 한다."""
        # 모든 캔들이 인접 (gap 없음)
        rows = [
            _candle(99, 101, 98, 100),
            _candle(100, 102, 99, 101),
            _candle(101, 103, 100, 102),
            _candle(102, 104, 101, 103),
            _candle(103, 105, 102, 104),
        ]
        df = _make_df(rows)
        result = self.fn(df, min_gap_pct=0.001)
        self.assertEqual(result, [])

    def test_결과_status가_모두_OPEN이다(self) -> None:
        """detect_fvgs는 초기 OPEN 상태만 반환한다."""
        from src.analysis.smart_money.models import FVGStatus

        rows = [
            _candle(98, 100, 97, 99),
            _candle(102, 105, 101, 103),
            _candle(111, 115, 110, 112),
        ]
        df = _make_df(rows)
        result = self.fn(df)
        for fvg in result:
            self.assertEqual(fvg.status, FVGStatus.OPEN)


class TestUpdateFVGStatus(unittest.TestCase):
    """update_fvg_status 함수 단위 테스트"""

    def setUp(self) -> None:
        from src.analysis.smart_money.fvg import detect_fvgs, update_fvg_status

        self.detect = detect_fvgs
        self.update = update_fvg_status

    def _make_bullish_fvg_df(self) -> pd.DataFrame:
        """Bullish FVG [100, 110]을 형성하는 3개 캔들 DataFrame."""
        rows = [
            _candle(98, 100, 97, 99),  # i-2: high=100
            _candle(102, 105, 101, 103),  # i-1
            _candle(111, 115, 110, 112),  # i=2: low=110 → FVG [100,110]
        ]
        return _make_df(rows)

    def _make_bearish_fvg_df(self) -> pd.DataFrame:
        """Bearish FVG [100, 110]을 형성하는 3개 캔들 DataFrame."""
        rows = [
            _candle(115, 118, 110, 112),  # i-2: low=110
            _candle(107, 112, 105, 108),  # i-1
            _candle(98, 100, 95, 97),  # i=2: high=100 → FVG [100,110]
        ]
        return _make_df(rows)

    # ── 입력 검증 ─────────────────────────────────────────────

    def test_df_None_입력은_ValueError(self) -> None:
        from src.analysis.smart_money.fvg import detect_fvgs

        base_df = self._make_bullish_fvg_df()
        fvgs = detect_fvgs(base_df)
        with self.assertRaises(ValueError):
            self.update(None, fvgs)

    def test_fvgs_None_입력은_ValueError(self) -> None:
        base_df = self._make_bullish_fvg_df()
        with self.assertRaises(ValueError):
            self.update(base_df, None)

    def test_non_DatetimeIndex_입력은_ValueError(self) -> None:
        from src.analysis.smart_money.fvg import detect_fvgs

        base_df = self._make_bullish_fvg_df()
        fvgs = detect_fvgs(base_df)
        df_no_idx = pd.DataFrame(
            {
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.0],
                "volume": [1000],
            }
        )
        with self.assertRaises(ValueError):
            self.update(df_no_idx, fvgs)

    def test_빈_fvgs_리스트는_빈_리스트_반환(self) -> None:
        base_df = self._make_bullish_fvg_df()
        result = self.update(base_df, [])
        self.assertEqual(result, [])

    # ── TOUCHED 상태 ─────────────────────────────────────────

    def test_bullish_FVG_touched_상태(self) -> None:
        """Bullish FVG에 가격이 진입하면 TOUCHED가 된다."""
        from src.analysis.smart_money.models import FVGStatus

        base_df = self._make_bullish_fvg_df()
        fvgs = self.detect(base_df)
        self.assertEqual(len(fvgs), 1)

        # FVG [100, 110]: 캔들 3에서 low=105로 gap 내 진입 (100 < 105 < 110)
        extra_rows = [
            _candle(111, 114, 105, 112),  # bar=3: low=105 → TOUCHED
        ]
        extra_df = _make_df(extra_rows, start="2024-01-05")
        full_df = pd.concat([base_df, extra_df])

        result = self.update(full_df, fvgs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].status, FVGStatus.TOUCHED)

    def test_bearish_FVG_touched_상태(self) -> None:
        """Bearish FVG에 가격이 진입하면 TOUCHED가 된다."""
        from src.analysis.smart_money.models import FVGStatus

        base_df = self._make_bearish_fvg_df()
        fvgs = self.detect(base_df)
        self.assertEqual(len(fvgs), 1)

        # FVG [100, 110]: 캔들 3에서 high=105로 gap 내 진입 (100 < 105 < 110)
        extra_rows = [
            _candle(98, 105, 96, 101),  # bar=3: high=105 → TOUCHED
        ]
        extra_df = _make_df(extra_rows, start="2024-01-05")
        full_df = pd.concat([base_df, extra_df])

        result = self.update(full_df, fvgs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].status, FVGStatus.TOUCHED)

    # ── FILLED 상태 ──────────────────────────────────────────

    def test_bullish_FVG_filled_상태(self) -> None:
        """Bullish FVG를 가격이 완전히 통과하면 FILLED가 된다."""
        from src.analysis.smart_money.models import FVGStatus

        base_df = self._make_bullish_fvg_df()
        fvgs = self.detect(base_df)

        # FVG [100, 110]: low=99 (≤ lower=100) → FILLED
        extra_rows = [
            _candle(103, 106, 99, 102),  # bar=3: low=99 ≤ 100 → FILLED
        ]
        extra_df = _make_df(extra_rows, start="2024-01-05")
        full_df = pd.concat([base_df, extra_df])

        result = self.update(full_df, fvgs)
        self.assertEqual(result[0].status, FVGStatus.FILLED)

    def test_bearish_FVG_filled_상태(self) -> None:
        """Bearish FVG를 가격이 완전히 통과하면 FILLED가 된다."""
        from src.analysis.smart_money.models import FVGStatus

        base_df = self._make_bearish_fvg_df()
        fvgs = self.detect(base_df)

        # FVG [100, 110]: high=111 (≥ upper=110) → FILLED
        extra_rows = [
            _candle(105, 111, 103, 109),  # bar=3: high=111 ≥ 110 → FILLED
        ]
        extra_df = _make_df(extra_rows, start="2024-01-05")
        full_df = pd.concat([base_df, extra_df])

        result = self.update(full_df, fvgs)
        self.assertEqual(result[0].status, FVGStatus.FILLED)

    def test_FILLED_이후_상태_변경_없음(self) -> None:
        """FILLED 상태는 최종 상태이다. 이후 캔들에서 변경되지 않는다."""
        from src.analysis.smart_money.models import FVGStatus

        base_df = self._make_bullish_fvg_df()
        fvgs = self.detect(base_df)

        # bar=3: FILLED, bar=4: 다시 FVG 범위 위로 올라가도 FILLED 유지
        extra_rows = [
            _candle(103, 106, 99, 102),  # bar=3: FILLED
            _candle(113, 116, 112, 115),  # bar=4: FVG 위 (상관 없음)
        ]
        extra_df = _make_df(extra_rows, start="2024-01-05")
        full_df = pd.concat([base_df, extra_df])

        result = self.update(full_df, fvgs)
        self.assertEqual(result[0].status, FVGStatus.FILLED)

    def test_FVG_형성_캔들_이전은_상태_업데이트에_사용_안함(self) -> None:
        """bar_index 이전 캔들은 상태 업데이트에 사용하지 않는다."""
        from src.analysis.smart_money.models import FVGStatus

        base_df = self._make_bullish_fvg_df()
        fvgs = self.detect(base_df)

        # fvg.bar_index=2이므로, base_df(0~2) 자체에서 상태 업데이트 시
        # bar=0, bar=1은 bar_index+1=3 이후가 아니므로 무시됨
        result = self.update(base_df, fvgs)
        self.assertEqual(result[0].status, FVGStatus.OPEN)

    # ── CSV fixture 검증 ──────────────────────────────────────

    def test_샘플_실데이터형_CSV_fixture(self) -> None:
        """CSV 형태의 fixture 데이터로 FVG 탐지가 예외 없이 수행된다."""
        import io

        csv_data = """date,open,high,low,close,volume
2024-01-02,100.0,102.0,98.0,101.0,10000
2024-01-03,101.0,103.0,100.0,102.0,10500
2024-01-04,102.0,115.0,112.0,114.0,11000
2024-01-05,114.0,117.0,113.0,116.0,10200
2024-01-08,116.0,118.0,110.0,112.0,9800
2024-01-09,112.0,119.0,111.0,118.0,12000
"""
        df = pd.read_csv(io.StringIO(csv_data), parse_dates=["date"], index_col="date")
        df.index = pd.DatetimeIndex(df.index)

        # 예외 없이 수행되어야 함
        try:
            fvgs = self.detect(df, min_gap_pct=0.001)
            _ = self.update(df, fvgs)
        except Exception as e:
            self.fail(f"CSV fixture에서 예외 발생: {e}")

    def test_필수_컬럼_누락시_원본_fvgs_반환(self) -> None:
        """[리뷰 수정] update_fvg_status에서 'high' 컬럼 누락 시 원본 fvgs를 그대로 반환한다."""
        from src.analysis.smart_money.models import FVGStatus

        base_df = self._make_bullish_fvg_df()
        fvgs = self.detect(base_df)
        self.assertEqual(len(fvgs), 1)
        self.assertEqual(fvgs[0].status, FVGStatus.OPEN)

        # 'high' 컬럼이 없는 DataFrame (필수 컬럼 누락)
        extra_rows = [
            _candle(111, 114, 105, 112),  # low=105 → TOUCHED 가 되어야 하지만
        ]
        extra_df = _make_df(extra_rows, start="2024-01-05")
        full_df = pd.concat([base_df, extra_df]).drop(columns=["high"])

        # 컬럼 누락이면 원본 fvgs(status=OPEN)를 그대로 반환해야 한다
        result = self.update(full_df, fvgs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].status, FVGStatus.OPEN)

    def test_future_only_DataFrame으로_상태_갱신(self) -> None:
        """[리뷰 수정] FVG 형성 이후 캔들만 담은 DataFrame으로도 상태가 정상 갱신된다.

        기존 bar_index 위치 기반 구현에서는 future-only DataFrame을
        전달하면 range(fvg.bar_index+1, n)이 비어 OPEN이 유지됐다.
        timestamp 기반으로 수정된 후에는 올바르게 TOUCHED/FILLED가 된다.
        """
        from src.analysis.smart_money.models import FVGStatus

        # Bullish FVG [100, 110]을 full df로 탐지
        base_df = self._make_bullish_fvg_df()
        fvgs = self.detect(base_df)
        self.assertEqual(len(fvgs), 1)

        # FVG 형성 이후 캔들만 담은 슬라이스 DataFrame 생성
        # low=105 → TOUCHED 기대
        future_rows = [
            _candle(111, 114, 105, 112),  # TOUCHED: low=105 ∈ [100, 110]
        ]
        future_df = _make_df(future_rows, start="2024-01-05")

        # future-only DataFrame + full DataFrame 모두 동일한 결과여야 함
        result_future = self.update(future_df, fvgs)
        result_full = self.update(pd.concat([base_df, future_df]), fvgs)

        self.assertEqual(
            result_future[0].status,
            FVGStatus.TOUCHED,
            "future-only DataFrame에서도 TOUCHED가 되어야 한다",
        )
        self.assertEqual(
            result_future[0].status,
            result_full[0].status,
            "future-only와 full DataFrame 결과가 일치해야 한다",
        )


class TestFVGPackageImport(unittest.TestCase):
    """smart_money 패키지에서 FVG public API import 검증"""

    def test_FVG_public_API_import가_성공한다(self) -> None:
        """src.analysis.smart_money에서 FVG public API를 import할 수 있어야 한다."""
        from src.analysis.smart_money import (  # noqa: F401
            FairValueGap,
            FVGDirection,
            FVGStatus,
            detect_fvgs,
            update_fvg_status,
        )

    def test_FairValueGap_dataclass가_frozen이다(self) -> None:
        """FairValueGap은 immutable frozen dataclass여야 한다."""
        from src.analysis.smart_money.models import FairValueGap, FVGDirection, FVGStatus

        fvg = FairValueGap(
            direction=FVGDirection.BULLISH,
            lower=100.0,
            upper=110.0,
            created_at=datetime(2024, 1, 4),
            bar_index=2,
            status=FVGStatus.OPEN,
        )
        with self.assertRaises((AttributeError, TypeError)):
            fvg.lower = 999.0  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
