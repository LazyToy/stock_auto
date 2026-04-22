"""
theme_trend — 주간 테마 트렌드 집계 (순수 로직).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def aggregate_weekly(
    daily_clusters: list[dict[str, Any]],
    prev_week_frequencies: dict[str, int],
) -> list[dict[str, Any]]:
    if not daily_clusters:
        return []

    freq: dict[str, int] = defaultdict(int)
    avg_changes: dict[str, list[float]] = defaultdict(list)
    reps_seen: dict[str, list[str]] = defaultdict(list)
    keywords_tf: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for cluster in daily_clusters:
        sector = str(cluster["sector"])
        freq[sector] += 1
        avg_changes[sector].append(float(cluster.get("avg_change", 0.0)))
        for rep in cluster.get("representatives", []):
            if rep not in reps_seen[sector]:
                reps_seen[sector].append(rep)
        for token, count in cluster.get("keywords_top5", []):
            keywords_tf[sector][str(token)] += int(count)

    results: list[dict[str, Any]] = []
    for sector, count in sorted(freq.items(), key=lambda x: -x[1]):
        prev = prev_week_frequencies.get(sector)
        if prev is None:
            wow = "NEW"
        else:
            diff = count - prev
            if diff > 0:
                wow = f"▲ +{diff}"
            elif diff < 0:
                wow = f"▼ -{abs(diff)}"
            else:
                wow = "─ 0"

        avg_pct = round(sum(avg_changes[sector]) / len(avg_changes[sector]), 2)
        kw_sorted = sorted(keywords_tf[sector].items(), key=lambda x: -x[1])[:5]
        results.append(
            {
                "sector": sector,
                "frequency": count,
                "wow_change": wow,
                "avg_change_pct": avg_pct,
                "representatives": reps_seen[sector][:5],
                "keywords_top5": kw_sorted,
            }
        )

    return results



def weekly_trend_to_sheet_row(iso_week: str, row: dict[str, Any]) -> list:
    kw = row.get("keywords_top5", [])
    kw_str = ", ".join(f"{tok}({cnt})" for tok, cnt in kw) if kw else ""
    reps = row.get("representatives", [])
    reps_str = ", ".join(reps) if reps else ""
    return [
        iso_week,
        row["sector"],
        row["frequency"],
        row["wow_change"],
        round(float(row.get("avg_change_pct", 0.0)), 2),
        reps_str,
        kw_str,
    ]
