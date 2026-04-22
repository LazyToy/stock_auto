"""
theme_cluster — 일별 테마 클러스터 집계 (순수 로직).

시장 전종목 데이터에서 같은 섹터 내 3종목 이상 ±5% 이상 움직임을 감지하여
'오늘의 테마'로 묶는다. 네트워크/시트 I/O 없음.

공개 인터페이스
--------------
* ``compute_intensity(n, avg_abs)``
    종목수(n)와 평균등락률 절대값(avg_abs)으로 강도 등급 반환.

* ``build_theme_clusters(df, *, sector_map, news_titles_by_ticker)``
    DataFrame → 클러스터 dict 리스트.

* ``cluster_to_sheet_row(date, cluster)``
    클러스터 dict → 시트 행 직렬화 (테마클러스터_일별 헤더 순서).
"""
from __future__ import annotations

from typing import Any, cast

import pandas as pd

# ---------------------------------------------------------------------------
# 설정 상수
# ---------------------------------------------------------------------------

THRESHOLD_CHANGE: float = 5.0   # 클러스터 집입 최소 등락률 절대값 (포함)
MIN_TICKERS: int = 3             # 섹터별 최소 종목수 (포함)

# ---------------------------------------------------------------------------
# 강도 등급
# ---------------------------------------------------------------------------

def compute_intensity(n: int, avg_abs: float) -> str:
    """
    종목수(n)와 평균등락률 절대값(avg_abs)으로 테마강도 등급 반환.

    복수 조건 만족 시 더 높은 등급 채택 (최상위 조건부터 순차 평가).

    등급 기준:
        ★★★★★: n >= 15  또는 avg_abs >= 10
        ★★★★☆: n >= 10  또는 avg_abs >= 7
        ★★★☆☆: n >= 7   또는 avg_abs >= 5
        ★★☆☆☆: n >= 5   또는 avg_abs >= 3
        ★☆☆☆☆: 그 외 (n >= 3 이 이미 MIN_TICKERS 통과 조건)
    """
    if n >= 15 or avg_abs >= 10:
        return "★★★★★"
    if n >= 10 or avg_abs >= 7:
        return "★★★★☆"
    if n >= 7 or avg_abs >= 5:
        return "★★★☆☆"
    if n >= 5 or avg_abs >= 3:
        return "★★☆☆☆"
    return "★☆☆☆☆"


# ---------------------------------------------------------------------------
# 클러스터 집계
# ---------------------------------------------------------------------------

def build_theme_clusters(
    df: pd.DataFrame,
    *,
    sector_map: dict[str, str],
    news_titles_by_ticker: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """
    DataFrame → 오늘의 테마 클러스터 리스트.

    Parameters
    ----------
    df : pd.DataFrame
        필수 컬럼: ticker, change, amount.
        선택 컬럼: name (종목명, 있으면 대표종목에 병기).
        ticker  — 종목코드 (str)
        name    — 종목명 (str, optional)
        change  — 등락률 (float, 부호 포함 %)
        amount  — 거래대금 (float, 원 단위)
    sector_map : dict[str, str]
        {ticker: sector_name}. 없는 ticker 는 "기타" 처리.
    news_titles_by_ticker : dict[str, list[str]]
        {ticker: [뉴스제목1, ...]}.  없으면 키워드 집계 생략.

    Returns
    -------
    list[dict] — 각 dict 의 키:
        direction          : "up" | "down"
        sector             : str
        ticker_count       : int
        representatives    : list[str]  최대 3개, |change| 내림차순, "코드(이름)" 형태
        avg_change         : float      부호 포함 평균 (소수 4자리)
        max_change         : float      up → max(change), down → min(change)
        intensity_stars    : str        ★☆☆☆☆ ~ ★★★★★
        total_amount_100m  : float      합산거래대금 억원 (소수 2자리)
        keywords_top5      : list[tuple[str, int]]  TF 기반 상위 5개
    """
    import importlib
    extract_keywords = importlib.import_module("src.crawling.news_aggregator").extract_keywords
    UNKNOWN_SECTOR = importlib.import_module("src.crawling.sector_map_kr").UNKNOWN_SECTOR

    if df.empty:
        return []

    df = df.copy()
    # 섹터 컬럼 주입 (sector_map 우선, 없으면 UNKNOWN_SECTOR)
    df["_sector"] = df["ticker"].map(lambda t: sector_map.get(str(t), UNKNOWN_SECTOR))
    # 등락률 절대값
    df["_abs_change"] = df["change"].abs()
    # 임계값 이상만 필터
    df_filtered = df[df["_abs_change"] >= THRESHOLD_CHANGE].copy()

    results: list[dict[str, Any]] = []

    for direction in ("up", "down"):
        if direction == "up":
            pool = cast(pd.DataFrame, df_filtered[df_filtered["change"] > 0].copy())
        else:
            pool = cast(pd.DataFrame, df_filtered[df_filtered["change"] < 0].copy())

        for sector, sub in cast(pd.DataFrame, pool).groupby("_sector"):
            if sector == UNKNOWN_SECTOR:
                continue
            if len(sub) < MIN_TICKERS:
                continue

            tickers: list[str] = sub["ticker"].tolist()
            changes: list[float] = sub["change"].tolist()

            avg_change = round(sum(changes) / len(changes), 4)
            max_change = max(changes) if direction == "up" else min(changes)

            # 대표종목: |change| 내림차순 상위 3개 — "코드(이름)" 형태
            sub_sorted = cast(pd.DataFrame, sub.sort_values(by="_abs_change", ascending=False))
            has_name = "name" in sub_sorted.columns
            reps_raw = sub_sorted.head(3)
            representatives = []
            for _, r in reps_raw.iterrows():
                tk = str(r["ticker"])
                name_val = r.get("name")
                if has_name and name_val is not None and bool(pd.notna(name_val)) and str(name_val).strip():
                    representatives.append(f"{tk}({name_val})")
                else:
                    representatives.append(tk)

            # 합산거래대금 (억원, NaN → 0)
            amount_series = cast(pd.Series, sub["amount"])
            total_amount_100m = round(amount_series.fillna(0).sum() / 1e8, 2)

            # 테마강도
            intensity = compute_intensity(len(sub), abs(avg_change))

            # 관련뉴스키워드 (TF 기반, Gemini 사용 안 함)
            all_titles: list[str] = []
            for t in tickers:
                all_titles.extend(news_titles_by_ticker.get(str(t), []))
            keywords_top5 = extract_keywords(all_titles, top_n=5)

            results.append({
                "direction": direction,
                "sector": str(sector),
                "ticker_count": len(sub),
                "representatives": representatives,
                "avg_change": avg_change,
                "max_change": max_change,
                "intensity_stars": intensity,
                "total_amount_100m": total_amount_100m,
                "keywords_top5": keywords_top5,
            })

    return results


# ---------------------------------------------------------------------------
# 시트 행 직렬화
# ---------------------------------------------------------------------------

def cluster_to_sheet_row(date: str, cluster: dict[str, Any]) -> list:
    """
    클러스터 dict + 날짜 → 시트 행 (테마클러스터_일별 헤더 순서 10개 컬럼).

    헤더: 날짜, 방향, 섹터, 포함종목수, 대표종목(3개), 평균등락률(%),
          최대등락률(%), 테마강도, 합산거래대금(억), 관련뉴스키워드(Top5)
    """
    kw = cluster["keywords_top5"]
    keywords_str = (
        ", ".join(f"{tok}({cnt})" for tok, cnt in kw) if kw else ""
    )
    return [
        date,
        cluster["direction"],
        cluster["sector"],
        cluster["ticker_count"],
        ", ".join(cluster["representatives"]),
        round(float(cluster["avg_change"]), 2),
        round(float(cluster["max_change"]), 2),
        cluster["intensity_stars"],
        round(float(cluster["total_amount_100m"]), 2),
        keywords_str,
    ]
