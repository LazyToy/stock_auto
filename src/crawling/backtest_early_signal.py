"""
이슈 #14: 조기신호 → 급등주 연결 백테스트.

목표
----
조기신호_관찰 탭에 쌓인 신호의 사후 유효성을 측정한다.
* 신호 +1, +3, +5영업일 종가 수익률 분포 (median, q25, q75, win rate)
* 조기신호 중 +5영업일 내 +threshold(%) 이상 도달 비율 (surge hit rate)
* 섹터별 hit rate 분포

설계
----
* 통계/계산 함수는 모두 **순수 함수** — 외부 I/O 없음.
* 시트 조회와 종가 조회는 **inject** 받아서 단위 테스트 가능.
* 결과는 `reports/backtest_YYYYMMDD.md` markdown 파일로 출력.

CLI
---
    python backtest_early_signal.py \
        --start 2026-01-01 --end 2026-04-17 \
        --horizons 1,3,5 --surge-threshold 15 \
        --sector 2차전지 \
        --output reports/backtest_20260417.md

가정/한계 (lookahead/survivorship 노트는 리포트에 명시):
* entry price = **신호일 종가** (보수적 — 다음날 open 사용 시 lookahead bias 가 줄어드는 대신 시뮬레이션 비용 증가)
* survivorship: close_lookup 이 None 반환하는 종목은 분모에서 제외하고 dropped 카운트로 보고
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import statistics
import sys
import traceback
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# 순수 함수: 영업일 계산 + 수익률
# ---------------------------------------------------------------------------

def _plus_bdays(signal_date: str, n: int) -> Optional[str]:
    """signal_date 로부터 n 영업일 뒤 날짜 ('YYYY-MM-DD'). 실패 시 None.

    backfill_5day_return._plus_bdays 와 동일 시맨틱 — 중복을 피하기 위해 import.
    """
    try:
        from src.crawling.backfill_5day_return import _plus_bdays as _impl
        return _impl(signal_date, n)
    except Exception:
        return None


def compute_max_return_over_window(
    *,
    ticker: str,
    signal_date: str,
    window_bdays: int,
    close_lookup: Callable[[str, str], Optional[float]],
) -> tuple[Optional[float], Optional[int]]:
    """신호일 종가 대비 +1..+window_bdays 영업일 종가 수익률(%) 의 최대값과 도달일.

    horizon list 의 듬성듬성한 점만 보지 않고 **모든 +1..+N 영업일을 스캔** 하여
    중간일(예: +2, +4) 에 발생한 peak 도 잡아낸다.

    반환: (max_return_pct, hit_bday).
      * 신호일 close 가 None/0 이하면 (None, None)
      * 모든 미래 close 조회 실패면 (None, None)
    """
    base = close_lookup(ticker, signal_date)
    if base is None or float(base) <= 0:
        return (None, None)
    base_f = float(base)

    best: Optional[float] = None
    best_day: Optional[int] = None
    for h in range(1, max(1, int(window_bdays)) + 1):
        plus = _plus_bdays(signal_date, h)
        if plus is None:
            continue
        c = close_lookup(ticker, plus)
        if c is None:
            continue
        ret = (float(c) / base_f - 1.0) * 100.0
        if best is None or ret > best:
            best = ret
            best_day = h
    return (best, best_day)


def compute_horizon_returns(
    *,
    ticker: str,
    signal_date: str,
    horizons: list[int],
    close_lookup: Callable[[str, str], Optional[float]],
) -> dict[int, Optional[float]]:
    """신호일 종가 대비 +h 영업일 종가 수익률(%) 을 horizon 별로 반환.

    * 신호일 close 가 0 이하거나 None 이면 모든 horizon → None.
    * +h 영업일 close 가 None 이면 해당 horizon 만 None.
    """
    base = close_lookup(ticker, signal_date)
    if base is None or float(base) <= 0:
        return {h: None for h in horizons}
    base_f = float(base)

    out: dict[int, Optional[float]] = {}
    for h in horizons:
        plus = _plus_bdays(signal_date, h)
        if plus is None:
            out[h] = None
            continue
        c = close_lookup(ticker, plus)
        if c is None:
            out[h] = None
            continue
        out[h] = (float(c) / base_f - 1.0) * 100.0
    return out


# ---------------------------------------------------------------------------
# 통계 — 순수 함수
# ---------------------------------------------------------------------------

def _quantile(values: list[float], q: float) -> float:
    """선형 보간 분위수 (numpy.quantile 디폴트와 동치).

    pandas.quantile() 디폴트(linear) 와도 일치.
    빈 입력 → 0.0.
    """
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return float(s[lo]) * (1 - frac) + float(s[hi]) * frac


def summarize_returns(values) -> dict:
    """수익률 리스트(None 포함 가능) → median/q25/q75/win_rate/count.

    * win_rate = (값 > 0) / count.  값=0 (보합) 은 분자에서 제외.
    * count = None 제외 후 실제 수익률 표본 수.
    """
    cleaned: list[float] = []
    for v in values or []:
        if v is None:
            continue
        try:
            cleaned.append(float(v))
        except (TypeError, ValueError):
            continue

    if not cleaned:
        return {"count": 0, "median": 0.0, "q25": 0.0, "q75": 0.0, "win_rate": 0.0}

    n = len(cleaned)
    median = float(statistics.median(cleaned))
    q25 = _quantile(cleaned, 0.25)
    q75 = _quantile(cleaned, 0.75)
    wins = sum(1 for x in cleaned if x > 0)
    return {
        "count": n,
        "median": median,
        "q25": q25,
        "q75": q75,
        "win_rate": wins / n,
    }


def compute_surge_hit_rate(signals: list[dict], *, threshold: float) -> float:
    """조기신호 중 max_return_5d >= threshold 비율.

    * max_return_5d 가 None 인 신호는 분모에서 제외 (survivorship 방어).
    """
    valid = [s for s in signals if s.get("max_return_5d") is not None]
    if not valid:
        return 0.0
    hits = sum(1 for s in valid if float(s["max_return_5d"]) >= threshold)
    return hits / len(valid)


def compute_sector_hit_rate(signals: list[dict], *, threshold: float) -> dict[str, dict]:
    """섹터별 hit/total/rate dict.

    * sector 키가 없거나 빈 값이면 '미분류' 섹터로 분류.
    * max_return_5d 가 None 인 신호는 해당 섹터 분모에서 제외.
    """
    table: dict[str, dict] = {}
    for s in signals:
        sector = str(s.get("sector") or "").strip() or "미분류"
        mret = s.get("max_return_5d")
        if mret is None:
            continue
        bucket = table.setdefault(sector, {"hit": 0, "total": 0, "rate": 0.0})
        bucket["total"] += 1
        if float(mret) >= threshold:
            bucket["hit"] += 1
    for sector, bucket in table.items():
        bucket["rate"] = bucket["hit"] / bucket["total"] if bucket["total"] else 0.0
    return table


# ---------------------------------------------------------------------------
# 시트 로딩 (sheet inject)
# ---------------------------------------------------------------------------

def _parse_iso(d: str) -> Optional[_dt.date]:
    try:
        return _dt.date.fromisoformat(d)
    except (ValueError, TypeError):
        return None


def load_early_signals(
    mf_sheet,
    *,
    start_date: _dt.date,
    end_date: _dt.date,
) -> list[dict]:
    """조기신호_관찰 탭에서 [start_date, end_date] 범위 신호를 dict 리스트로 반환.

    각 dict:
      ticker, name, signal_date, change, rvol, streak, close_ratio_52w, amount,
      five_day_return_recorded (시트에 기록된 값, 백필 안 됐으면 None)

    sector 는 별도 인자로 합쳐야 함 (이 함수는 시트만 본다).
    """
    from src.crawling.daily_trend_writer import EARLY_SIGNAL_TAB, EARLY_SIGNAL_HEADERS

    ws = mf_sheet._ensure_worksheet(EARLY_SIGNAL_TAB, EARLY_SIGNAL_HEADERS)
    values = ws.get_all_values()

    out: list[dict] = []
    for row in values[1:]:
        if not row or len(row) < 2:
            continue
        sd_str = str(row[0]).strip()
        ticker = str(row[1]).strip()
        if not sd_str or not ticker:
            continue
        sd = _parse_iso(sd_str)
        if sd is None:
            continue
        if sd < start_date or sd > end_date:
            continue

        def _f(idx, default=0.0):
            try:
                return float(row[idx])
            except (IndexError, TypeError, ValueError):
                return default

        def _i(idx, default=0):
            try:
                return int(float(row[idx]))
            except (IndexError, TypeError, ValueError):
                return default

        recorded = None
        if len(row) >= len(EARLY_SIGNAL_HEADERS):
            tail = str(row[-1]).strip()
            if tail:
                try:
                    recorded = float(tail)
                except ValueError:
                    recorded = None

        out.append({
            "signal_date": sd_str,
            "ticker": ticker,
            "name": str(row[2]) if len(row) > 2 else "",
            "change": _f(3),
            "rvol": _f(4),
            "streak": _i(5),
            "close_ratio_52w": _f(6),
            "amount": _f(7),
            "five_day_return_recorded": recorded,
        })

    return out


# ---------------------------------------------------------------------------
# 신호 enrich — 수익률/최대수익률 부착
# ---------------------------------------------------------------------------

def enrich_signals_with_returns(
    signals: list[dict],
    *,
    horizons: list[int],
    close_lookup: Callable[[str, str], Optional[float]],
    window_bdays: int = 5,
) -> list[dict]:
    """각 신호에 returns_by_horizon, max_return_5d, max_return_hit_day 추가.

    * returns_by_horizon: horizons 에 명시된 점만 (보고용 표 데이터).
    * max_return_5d: **+1..+window_bdays 모든 영업일을 스캔** 한 진짜 max — horizons 와 무관.
      (논리결함 #1 수정: horizons=[1,3,5] 만 봐서 +2/+4 peak 를 놓치는 버그 차단.)
    * max_return_hit_day: max 가 도달된 영업일 offset.
    """
    enriched: list[dict] = []
    for s in signals:
        ticker = str(s["ticker"])
        signal_date = str(s["signal_date"])
        rets = compute_horizon_returns(
            ticker=ticker,
            signal_date=signal_date,
            horizons=horizons,
            close_lookup=close_lookup,
        )
        max_ret, hit_day = compute_max_return_over_window(
            ticker=ticker,
            signal_date=signal_date,
            window_bdays=window_bdays,
            close_lookup=close_lookup,
        )
        s2 = dict(s)
        s2["returns_by_horizon"] = rets
        s2["max_return_5d"] = max_ret
        s2["max_return_hit_day"] = hit_day
        enriched.append(s2)
    return enriched


# ---------------------------------------------------------------------------
# AC-1: 기간 검증 (1개월 이상 이력 강제)
# ---------------------------------------------------------------------------

def validate_period(
    start: _dt.date,
    end: _dt.date,
    *,
    min_days: int = 28,
) -> tuple[bool, str]:
    """기간 유효성 검사.

    * end < start → fail
    * (end - start).days + 1 < min_days → fail (1개월 ≈ 28일 기본)
    * 통과 시 (True, '') 반환.
    """
    if end < start:
        return (False, "기간 종료일이 시작일보다 빠릅니다.")
    span = (end - start).days + 1
    if span < int(min_days):
        return (
            False,
            f"기간이 {span}일로 최소({min_days}일/약 1개월) 미만입니다.",
        )
    return (True, "")


# ---------------------------------------------------------------------------
# AC-3: 조기신호 조건 필터 (change/RVOL/streak/52w)
# ---------------------------------------------------------------------------

def apply_signal_filters(signals: list[dict], filters: dict) -> list[dict]:
    """조기신호 조건 필터.

    filters keys (모두 optional):
      * min_change / max_change: 등락률(%) 하/상한
      * min_rvol: 상대거래량 하한
      * min_streak: 연속봉 하한 (int)
      * min_ratio_52w: 52주고가비율 하한
    """
    if not filters:
        return list(signals)

    min_change = filters.get("min_change")
    max_change = filters.get("max_change")
    min_rvol = filters.get("min_rvol")
    min_streak = filters.get("min_streak")
    min_ratio_52w = filters.get("min_ratio_52w")

    def _ok(s: dict) -> bool:
        if min_change is not None and float(s.get("change", 0.0)) < float(min_change):
            return False
        if max_change is not None and float(s.get("change", 0.0)) > float(max_change):
            return False
        if min_rvol is not None and float(s.get("rvol", 0.0)) < float(min_rvol):
            return False
        if min_streak is not None and int(s.get("streak", 0)) < int(min_streak):
            return False
        if min_ratio_52w is not None and float(s.get("close_ratio_52w", 0.0)) < float(min_ratio_52w):
            return False
        return True

    return [s for s in signals if _ok(s)]


# ---------------------------------------------------------------------------
# 논리결함 #2: 실제 급등주 시트 매칭
# ---------------------------------------------------------------------------

def _normalize_ticker(t: str) -> str:
    """ticker 정규화 — KR(숫자만) zfill(6), 그 외 upper().

    조기신호와 급등주 시트 양쪽이 같은 키로 비교될 수 있도록.
    """
    raw = str(t).strip().lstrip("'")
    if raw.isdigit():
        return raw.zfill(6)
    return raw.upper()


def compute_surge_sheet_hit_rate(
    signals: list[dict],
    *,
    surge_entries,
    within_bdays: int = 5,
) -> float:
    """조기신호 중 **실제 급등주 시트** 에 +1..+within_bdays 영업일 내 등재된 비율.

    surge_entries: iterable of (ticker, surge_date_str).
    분모는 전체 signals (signal 발생만으로도 카운트), 분자는 매칭된 unique signal 수.
    같은 (signal_ticker, signal_date) 가 여러 surge_entry 에 매칭되어도 1회만 카운트.
    """
    if not signals:
        return 0.0

    # surge_entries 를 ticker → set(date_str) 로 집계
    surge_by_ticker: dict[str, set[str]] = {}
    for raw_t, raw_d in surge_entries or []:
        nt = _normalize_ticker(raw_t)
        sd = str(raw_d).strip()
        if not nt or not sd:
            continue
        surge_by_ticker.setdefault(nt, set()).add(sd)

    if not surge_by_ticker:
        return 0.0

    hits = 0
    for s in signals:
        nt = _normalize_ticker(str(s.get("ticker", "")))
        sig_date = str(s.get("signal_date", "")).strip()
        if not nt or not sig_date or nt not in surge_by_ticker:
            continue
        # window 내 매칭이 하나라도 있으면 hit
        candidate_dates = {
            _plus_bdays(sig_date, h)
            for h in range(1, int(within_bdays) + 1)
        }
        candidate_dates.discard(None)
        if surge_by_ticker[nt] & candidate_dates:
            hits += 1
    return hits / len(signals)


# ---------------------------------------------------------------------------
# 논리결함 #3: survivorship dropped 카운트 보고
# ---------------------------------------------------------------------------

def count_dropped_survivorship(enriched: list[dict]) -> int:
    """max_return_5d 가 None 인 enriched 신호 수 (survivorship 누락)."""
    return sum(1 for s in (enriched or []) if s.get("max_return_5d") is None)


# ---------------------------------------------------------------------------
# 리포트 — markdown 렌더
# ---------------------------------------------------------------------------

def _pct(v: float) -> str:
    return f"{v * 100:.2f}%"


def _num(v: float) -> str:
    return f"{v:.2f}"


def render_report(
    *,
    title: str,
    period: tuple[str, str],
    signal_count: int,
    horizon_summary: dict[int, dict],
    surge_threshold: float,
    surge_hit_rate: float,
    sector_table: dict[str, dict],
    notes: dict[str, str],
    surge_sheet_hit_rate: Optional[float] = None,
    dropped_count: Optional[int] = None,
    period_warning: Optional[str] = None,
) -> str:
    """백테스트 결과를 markdown 으로 직렬화."""
    start, end = period
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- 기간: {start} ~ {end}")
    lines.append(f"- 신호 {signal_count}건")
    if dropped_count is not None:
        lines.append(f"- survivorship 드랍: {dropped_count}건 (close 조회 실패로 분모 제외)")
    if period_warning:
        lines.append(f"- ⚠️ 경고: {period_warning}")
    lines.append("")

    # horizon 통계 표
    lines.append("## 시그널 +N영업일 수익률 분포")
    lines.append("")
    lines.append("| horizon | count | median(%) | q25(%) | q75(%) | win_rate |")
    lines.append("|---------|-------|-----------|--------|--------|----------|")
    for h in sorted(horizon_summary.keys()):
        s = horizon_summary[h]
        lines.append(
            f"| +{h}d | {s['count']} | {_num(s['median'])} | "
            f"{_num(s['q25'])} | {_num(s['q75'])} | {_pct(s['win_rate'])} |"
        )
    lines.append("")

    # 종가 기반 진입 비율 (수익률 surrogate)
    lines.append(f"## 종가 기반 진입 비율 (max(+1..+5d return) >= {surge_threshold:.1f}%)")
    lines.append("")
    lines.append(f"- surge_hit_rate (close-return 기준): {_pct(surge_hit_rate)}")
    lines.append("")

    # 실제 급등주 시트 매칭 비율
    if surge_sheet_hit_rate is not None:
        lines.append("## 실제 급등주 시트 진입 비율 (+1..+5영업일 내 시트 등재 매칭)")
        lines.append("")
        lines.append(
            f"- surge_sheet_hit_rate: {_pct(surge_sheet_hit_rate)} "
            f"(조기신호 → 실제 급등주 시트로 진입한 비율)"
        )
        lines.append("")

    # 섹터별 hit rate
    lines.append("## 섹터별 hit rate")
    lines.append("")
    if sector_table:
        lines.append("| 섹터 | hit | total | rate |")
        lines.append("|------|-----|-------|------|")
        for sector in sorted(sector_table.keys(), key=lambda k: -sector_table[k]["rate"]):
            b = sector_table[sector]
            lines.append(f"| {sector} | {b['hit']} | {b['total']} | {_pct(b['rate'])} |")
    else:
        lines.append("- (집계 가능한 섹터 데이터 없음)")
    lines.append("")

    # 가정/한계
    lines.append("## 가정 및 한계")
    lines.append("")
    if notes:
        for k, v in notes.items():
            lines.append(f"- **{k}**: {v}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_horizons(s: str) -> list[int]:
    return [int(x.strip()) for x in s.split(",") if x.strip()]


def build_cli_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="조기신호 백테스트 - +N일 수익률/급등주 진입율/섹터 hit rate 리포트 생성"
    )
    p.add_argument("--start", required=True, help="기간 시작 (YYYY-MM-DD)")
    p.add_argument("--end", required=True, help="기간 종료 (YYYY-MM-DD)")
    p.add_argument("--horizons", default="1,3,5", help="수익률 측정 horizon (CSV, 영업일)")
    p.add_argument("--surge-threshold", default="15", help="급등 임계값(%%) - 진입 비율 계산")
    p.add_argument("--sector", default=None, help="섹터 필터 (선택, 부분문자열 일치)")
    p.add_argument(
        "--output",
        default=None,
        help="리포트 출력 경로. 미지정 시 reports/backtest_YYYYMMDD.md 자동 생성",
    )
    p.add_argument(
        "--service-account",
        default=None,
        help="gspread 서비스계정 JSON 경로 (미지정 시 GOOGLE_SERVICE_ACCOUNT_FILE 또는 기본 경로)",
    )
    # AC-3: 조기신호 조건 필터
    p.add_argument("--min-change", default=None, help="등락률(%%) 하한")
    p.add_argument("--max-change", default=None, help="등락률(%%) 상한 (예: 급등주 임계값 미만으로 컷)")
    p.add_argument("--min-rvol", default=None, help="상대거래량(RVOL) 하한")
    p.add_argument("--min-streak", default=None, help="연속봉(int) 하한")
    p.add_argument("--min-52w-ratio", dest="min_52w_ratio", default=None, help="52주고가비율 하한 (0~1)")
    # AC-1: 최소 기간(일) 오버라이드
    p.add_argument("--min-period-days", default="28", help="최소 기간(일). 기본 28(약 1개월)")
    return p


# ---------------------------------------------------------------------------
# Production wiring — 단위 테스트 대상 아님
# ---------------------------------------------------------------------------

def _default_output_path(today: _dt.date) -> str:
    return os.path.join("reports", f"backtest_{today.strftime('%Y%m%d')}.md")


def _filter_by_sector(signals: list[dict], needle: Optional[str]) -> list[dict]:
    if not needle:
        return signals
    return [s for s in signals if needle in str(s.get("sector") or "")]


def _attach_sectors(signals: list[dict]) -> list[dict]:
    """조기신호 row 에 sector 정보를 부착 (sector_map_kr 사용, 실패 시 미분류).

    네트워크 호출이 발생할 수 있으므로 production 전용.
    """
    try:
        from src.crawling.sector_map_kr import SectorMapKR
    except Exception:
        return signals
    try:
        smap = SectorMapKR("sector_map_kr.json")
        for s in signals:
            try:
                s["sector"] = smap.classify([str(s["ticker"])]).get(str(s["ticker"]), "")
            except Exception:
                s["sector"] = ""
    except Exception:
        for s in signals:
            s.setdefault("sector", "")
    return signals


def _build_filters_from_args(args) -> dict:
    flt: dict = {}
    if args.min_change is not None:
        flt["min_change"] = float(args.min_change)
    if args.max_change is not None:
        flt["max_change"] = float(args.max_change)
    if args.min_rvol is not None:
        flt["min_rvol"] = float(args.min_rvol)
    if args.min_streak is not None:
        flt["min_streak"] = int(args.min_streak)
    if args.min_52w_ratio is not None:
        flt["min_ratio_52w"] = float(args.min_52w_ratio)
    return flt


def _load_surge_entries(mf_sheet, *, start_date: _dt.date, end_date: _dt.date):
    """월별 '주식_쉐도잉_YYYYMM' 시트의 급등주 탭에서 (ticker, date) 추출.

    실패 시 빈 리스트 — surge_sheet_hit_rate=0 으로 fallback.
    """
    try:
        import calendar
        import importlib
        gspread = importlib.import_module("gspread")

        client = getattr(mf_sheet, "_client", None) or getattr(mf_sheet, "client", None)
        if client is None:
            return []

        out: list[tuple[str, str]] = []
        cur = _dt.date(start_date.year, start_date.month, 1)
        last = _dt.date(end_date.year, end_date.month, 1)
        while cur <= last:
            ym = cur.strftime("%Y%m")
            try:
                sh = client.open(f"주식_쉐도잉_{ym}")
            except gspread.SpreadsheetNotFound:
                cur = (cur.replace(day=28) + _dt.timedelta(days=4)).replace(day=1)
                continue
            for ws in sh.worksheets():
                if "급등주" not in ws.title:
                    continue
                rows = ws.get_all_values()
                for r in rows[1:]:
                    if len(r) < 3:
                        continue
                    d = str(r[0]).strip()
                    t = str(r[2]).strip()
                    if not d or not t:
                        continue
                    sd = _parse_iso(d)
                    if sd is None or sd < start_date or sd > end_date:
                        continue
                    out.append((t, d))
            cur = (cur.replace(day=28) + _dt.timedelta(days=4)).replace(day=1)
        return out
    except Exception:
        traceback.print_exc(limit=3)
        return []


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_cli_parser()
    args = parser.parse_args(argv)

    start = _parse_iso(args.start)
    end = _parse_iso(args.end)
    if start is None or end is None:
        print("[backtest] 잘못된 기간 인자 (날짜 파싱 실패)", file=sys.stderr)
        return 2

    min_period_days = int(args.min_period_days)
    ok, msg = validate_period(start, end, min_days=min_period_days)
    period_warning: Optional[str] = None
    if not ok:
        # AC-1: 1개월 미만이면 fail (CLI 기본값 28일). 명시적 오버라이드 시 경고만.
        if min_period_days >= 28:
            print(f"[backtest] 기간 검증 실패: {msg}", file=sys.stderr)
            return 2
        period_warning = msg

    horizons = parse_horizons(args.horizons)
    if not horizons:
        print("[backtest] horizons 가 비어있음", file=sys.stderr)
        return 2

    surge_threshold = float(args.surge_threshold)
    filters = _build_filters_from_args(args)

    try:
        from src.crawling.daily_trend_writer import MarketFlowSheet, make_sheet_client
        from src.crawling.backfill_5day_return import _production_close_lookup_factory
    except Exception:
        print("[backtest] 의존성 import 실패", file=sys.stderr)
        traceback.print_exc(limit=5)
        return 1

    try:
        gc = make_sheet_client(args.service_account)
        mf_sheet = MarketFlowSheet(gc, end.year)
    except Exception:
        print("[backtest] gspread 클라이언트 생성 실패", file=sys.stderr)
        traceback.print_exc(limit=5)
        return 1

    signals = load_early_signals(mf_sheet, start_date=start, end_date=end)
    signals = _attach_sectors(signals)
    signals = _filter_by_sector(signals, args.sector)
    signals = apply_signal_filters(signals, filters)

    close_lookup = _production_close_lookup_factory()
    window_bdays = max([5] + horizons)
    enriched = enrich_signals_with_returns(
        signals, horizons=horizons, close_lookup=close_lookup, window_bdays=window_bdays
    )

    horizon_summary = {
        h: summarize_returns([e["returns_by_horizon"][h] for e in enriched])
        for h in horizons
    }
    surge_hit_rate = compute_surge_hit_rate(enriched, threshold=surge_threshold)
    sector_table = compute_sector_hit_rate(enriched, threshold=surge_threshold)

    surge_entries = _load_surge_entries(mf_sheet, start_date=start, end_date=end)
    surge_sheet_hit_rate = compute_surge_sheet_hit_rate(
        enriched, surge_entries=surge_entries, within_bdays=window_bdays
    )
    dropped_count = count_dropped_survivorship(enriched)

    md = render_report(
        title="조기신호 백테스트 리포트",
        period=(args.start, args.end),
        signal_count=len(enriched),
        horizon_summary=horizon_summary,
        surge_threshold=surge_threshold,
        surge_hit_rate=surge_hit_rate,
        surge_sheet_hit_rate=surge_sheet_hit_rate,
        dropped_count=dropped_count,
        period_warning=period_warning,
        sector_table=sector_table,
        notes={
            "entry_price": "신호일 종가 (lookahead bias 회피 위해 다음날 open 미사용)",
            "survivorship": f"close 조회 실패 {dropped_count}건은 분모 제외 — 상장폐지/거래정지 추정",
            "max_return_window": f"max_return_5d 는 +1..+{window_bdays}영업일 전구간 스캔 결과",
            "horizons": ",".join(str(h) for h in horizons),
            "filters": ", ".join(f"{k}={v}" for k, v in filters.items()) if filters else "(없음)",
        },
    )

    out_path = args.output or _default_output_path(_dt.date.today())
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[backtest] 리포트 작성 완료 -> {out_path} ({len(enriched)}건, dropped={dropped_count})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
