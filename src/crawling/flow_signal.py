"""
이슈 #11: 수급 전환 시그널 판정 로직.

순수 함수만 포함 — 네트워크/시트 I/O 없음.
"""
from __future__ import annotations

FLOW_SIGNAL_HEADERS: list[str] = [
    "날짜",
    "종목코드",
    "종목명",
    "전환유형",
    "당일외국인순매매",
    "당일기관순매매",
    "직전5일외국인누적",
    "직전5일기관누적",
]

_REVERSAL_MAP: dict[tuple[str, str], str] = {
    ("foreign", "buy"): "외국인매수전환",
    ("foreign", "sell"): "외국인매도전환",
    ("institution", "buy"): "기관매수전환",
    ("institution", "sell"): "기관매도전환",
}


def detect_reversal(records: list[dict], lookback: int = 5) -> list[dict]:
    if len(records) < lookback + 1:
        return []

    today = records[0]
    prev = records[1 : lookback + 1]
    signals: list[dict] = []

    def _check(field: str, label: str) -> None:
        today_val: int = today.get(field, 0)
        prev_vals: list[int] = [r.get(field, 0) for r in prev]

        prev_all_negative = all(v < 0 for v in prev_vals)
        prev_all_positive = all(v > 0 for v in prev_vals)

        if today_val > 0 and prev_all_negative:
            signals.append(
                {
                    "reversal_type": _REVERSAL_MAP[(label, "buy")],
                    "today_foreign": today.get("foreign", 0),
                    "today_institution": today.get("institution", 0),
                    "prev_foreign_sum": sum(r.get("foreign", 0) for r in prev),
                    "prev_institution_sum": sum(r.get("institution", 0) for r in prev),
                }
            )
        elif today_val < 0 and prev_all_positive:
            signals.append(
                {
                    "reversal_type": _REVERSAL_MAP[(label, "sell")],
                    "today_foreign": today.get("foreign", 0),
                    "today_institution": today.get("institution", 0),
                    "prev_foreign_sum": sum(r.get("foreign", 0) for r in prev),
                    "prev_institution_sum": sum(r.get("institution", 0) for r in prev),
                }
            )

    _check("foreign", "foreign")
    _check("institution", "institution")
    return signals


def build_flow_signal_row(
    date: str,
    ticker: str,
    name: str,
    reversal_type: str,
    today_foreign: int,
    today_institution: int,
    prev_days_foreign: list[int],
    prev_days_institution: list[int],
    **_: object,
) -> list:
    return [
        date,
        ticker,
        name,
        reversal_type,
        today_foreign,
        today_institution,
        sum(prev_days_foreign),
        sum(prev_days_institution),
    ]
