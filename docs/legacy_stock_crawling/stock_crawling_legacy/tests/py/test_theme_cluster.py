"""
테마 클러스터 단위 테스트.

theme_cluster.build_theme_clusters / compute_intensity / cluster_to_sheet_row 를
순수 함수로서 검증한다. 네트워크/시트 I/O 없음.

실행:
    python tests/py/test_theme_cluster.py
"""
from __future__ import annotations
import os
import sys

# 프로젝트 루트를 sys.path에 추가 (venv 직접 실행 시 theme_cluster 임포트 가능하도록)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pandas as pd


# ---------------------------------------------------------------------------
# compute_intensity 경계값 테스트
# ---------------------------------------------------------------------------

def test_intensity_ladder_exact_thresholds():
    """강도 계산 로직의 경계값 테스트 — 하네스 명세 그대로."""
    from theme_cluster import compute_intensity
    assert compute_intensity(n=3, avg_abs=2.5) == "★☆☆☆☆"
    assert compute_intensity(n=5, avg_abs=2.5) == "★★☆☆☆"
    assert compute_intensity(n=3, avg_abs=3.0) == "★★☆☆☆"
    assert compute_intensity(n=7, avg_abs=0.1) == "★★★☆☆"
    assert compute_intensity(n=15, avg_abs=0.1) == "★★★★★"
    assert compute_intensity(n=3, avg_abs=10.0) == "★★★★★"


def test_intensity_middle_tiers():
    """★★★☆☆, ★★★★☆ 구간 명시적 검증."""
    from theme_cluster import compute_intensity
    assert compute_intensity(n=10, avg_abs=0.5) == "★★★★☆"
    assert compute_intensity(n=3, avg_abs=7.0) == "★★★★☆"   # n=3, avg=7 → avg>=7 → ★★★★☆
    assert compute_intensity(n=7, avg_abs=5.0) == "★★★☆☆"   # n=7, avg=5 → 둘 다 ★★★☆☆ 경계
    assert compute_intensity(n=3, avg_abs=5.0) == "★★★☆☆"   # avg>=5
    assert compute_intensity(n=3, avg_abs=6.9) == "★★★☆☆"   # avg<7 → ★★★☆☆


# ---------------------------------------------------------------------------
# build_theme_clusters — 빈 입력
# ---------------------------------------------------------------------------

def test_build_theme_clusters_empty_input():
    """빈 DataFrame → 빈 리스트."""
    from theme_cluster import build_theme_clusters
    df = pd.DataFrame(columns=["ticker", "sector", "change", "amount"])
    assert build_theme_clusters(df, sector_map={}, news_titles_by_ticker={}) == []


# ---------------------------------------------------------------------------
# build_theme_clusters — 최소 종목수 미달
# ---------------------------------------------------------------------------

def test_build_theme_clusters_min_3_tickers():
    """같은 섹터 2종목은 클러스터로 잡히지 않는다 (MIN_TICKERS=3)."""
    from theme_cluster import build_theme_clusters
    df = pd.DataFrame([
        {"ticker": "A", "sector": "2차전지", "change": 7.0, "amount": 100e8},
        {"ticker": "B", "sector": "2차전지", "change": 6.0, "amount": 200e8},
    ])
    assert build_theme_clusters(
        df,
        sector_map={"A": "2차전지", "B": "2차전지"},
        news_titles_by_ticker={},
    ) == []


# ---------------------------------------------------------------------------
# build_theme_clusters — 상승 클러스터 감지
# ---------------------------------------------------------------------------

def test_build_theme_clusters_detects_up_cluster():
    """3종목 이상 같은 섹터 ±5% 이상 상승 → up 클러스터 1개 생성."""
    from theme_cluster import build_theme_clusters
    df = pd.DataFrame([
        {"ticker": "A", "sector": "2차전지", "change": 7.0, "amount": 100e8},
        {"ticker": "B", "sector": "2차전지", "change": 6.0, "amount": 200e8},
        {"ticker": "C", "sector": "2차전지", "change": 8.0, "amount": 150e8},
    ])
    clusters = build_theme_clusters(
        df,
        sector_map={"A": "2차전지", "B": "2차전지", "C": "2차전지"},
        news_titles_by_ticker={
            "A": ["리튬 수주 호재"],
            "B": ["ESS 계약"],
            "C": ["유럽 관세 리스크 해소"],
        },
    )
    assert len(clusters) == 1
    c = clusters[0]
    assert c["direction"] == "up"
    assert c["sector"] == "2차전지"
    assert c["ticker_count"] == 3
    assert len(c["representatives"]) == 3
    assert abs(c["avg_change"] - 7.0) < 0.01
    assert c["max_change"] == 8.0
    # 하네스 원본: in ("★☆☆☆☆", "★★☆☆☆") — 오류.
    # compute_intensity(n=3, avg_abs=7.0): avg>=7 → ★★★★☆ (래더 정의 따름)
    assert c["intensity_stars"] == "★★★★☆"
    assert abs(c["total_amount_100m"] - 450.0) < 0.01
    assert len(c["keywords_top5"]) <= 5


# ---------------------------------------------------------------------------
# build_theme_clusters — 하락 클러스터 감지
# ---------------------------------------------------------------------------

def test_build_theme_clusters_detects_down_cluster_separately():
    """3종목 이상 같은 섹터 -5% 이하 하락 → down 클러스터 1개 생성."""
    from theme_cluster import build_theme_clusters
    df = pd.DataFrame([
        {"ticker": "X", "sector": "바이오", "change": -6.0, "amount": 100e8},
        {"ticker": "Y", "sector": "바이오", "change": -5.5, "amount": 200e8},
        {"ticker": "Z", "sector": "바이오", "change": -7.0, "amount": 150e8},
    ])
    clusters = build_theme_clusters(
        df,
        sector_map={"X": "바이오", "Y": "바이오", "Z": "바이오"},
        news_titles_by_ticker={},
    )
    assert len(clusters) == 1
    assert clusters[0]["direction"] == "down"
    assert clusters[0]["avg_change"] < 0


# ---------------------------------------------------------------------------
# build_theme_clusters — 임계값 경계 (|change| == 5.0 포함)
# ---------------------------------------------------------------------------

def test_build_theme_clusters_threshold_boundary_inclusive():
    """|change| == THRESHOLD_CHANGE(5.0) 는 포함돼야 한다."""
    from theme_cluster import build_theme_clusters
    df = pd.DataFrame([
        {"ticker": "A", "sector": "반도체", "change": 5.0, "amount": 100e8},
        {"ticker": "B", "sector": "반도체", "change": 5.0, "amount": 100e8},
        {"ticker": "C", "sector": "반도체", "change": 5.0, "amount": 100e8},
    ])
    clusters = build_theme_clusters(
        df,
        sector_map={"A": "반도체", "B": "반도체", "C": "반도체"},
        news_titles_by_ticker={},
    )
    assert len(clusters) == 1


def test_build_theme_clusters_threshold_boundary_below():
    """|change| < 5.0 은 제외돼야 한다."""
    from theme_cluster import build_theme_clusters
    df = pd.DataFrame([
        {"ticker": "A", "sector": "반도체", "change": 4.9, "amount": 100e8},
        {"ticker": "B", "sector": "반도체", "change": 4.9, "amount": 100e8},
        {"ticker": "C", "sector": "반도체", "change": 4.9, "amount": 100e8},
    ])
    clusters = build_theme_clusters(
        df,
        sector_map={"A": "반도체", "B": "반도체", "C": "반도체"},
        news_titles_by_ticker={},
    )
    assert clusters == []


# ---------------------------------------------------------------------------
# build_theme_clusters — 같은 섹터 상승/하락 동시 → 각각 별도 행
# ---------------------------------------------------------------------------

def test_build_theme_clusters_up_and_down_same_sector():
    """같은 섹터에서 상승/하락 각 3종목 이상 → 2개 클러스터 (direction 분리)."""
    from theme_cluster import build_theme_clusters
    df = pd.DataFrame([
        {"ticker": "A", "sector": "철강", "change": 6.0,  "amount": 100e8},
        {"ticker": "B", "sector": "철강", "change": 7.0,  "amount": 100e8},
        {"ticker": "C", "sector": "철강", "change": 5.5,  "amount": 100e8},
        {"ticker": "D", "sector": "철강", "change": -5.0, "amount": 100e8},
        {"ticker": "E", "sector": "철강", "change": -6.0, "amount": 100e8},
        {"ticker": "F", "sector": "철강", "change": -8.0, "amount": 100e8},
    ])
    sector_map = {t: "철강" for t in list("ABCDEF")}
    clusters = build_theme_clusters(df, sector_map=sector_map, news_titles_by_ticker={})
    directions = {c["direction"] for c in clusters}
    assert directions == {"up", "down"}
    assert len(clusters) == 2


# ---------------------------------------------------------------------------
# build_theme_clusters — amount NaN 방어
# ---------------------------------------------------------------------------

def test_build_theme_clusters_amount_nan():
    """amount 에 NaN 이 있어도 total_amount_100m 계산이 실패하지 않는다."""
    from theme_cluster import build_theme_clusters
    import math
    df = pd.DataFrame([
        {"ticker": "A", "sector": "건설", "change": 6.0, "amount": float("nan")},
        {"ticker": "B", "sector": "건설", "change": 7.0, "amount": 100e8},
        {"ticker": "C", "sector": "건설", "change": 5.0, "amount": 200e8},
    ])
    clusters = build_theme_clusters(
        df,
        sector_map={"A": "건설", "B": "건설", "C": "건설"},
        news_titles_by_ticker={},
    )
    assert len(clusters) == 1
    assert not math.isnan(clusters[0]["total_amount_100m"])


# ---------------------------------------------------------------------------
# cluster_to_sheet_row 직렬화 테스트
# ---------------------------------------------------------------------------

def test_cluster_to_sheet_row_structure():
    """cluster_to_sheet_row 가 헤더 순서(10개 컬럼)에 맞는 row 를 반환한다."""
    from theme_cluster import cluster_to_sheet_row
    cluster = {
        "direction": "up",
        "sector": "2차전지",
        "ticker_count": 3,
        "representatives": ["A", "B", "C"],
        "avg_change": 7.0,
        "max_change": 8.0,
        "intensity_stars": "★★★★☆",
        "total_amount_100m": 450.0,
        "keywords_top5": [("리튬", 3), ("ESS", 2)],
    }
    row = cluster_to_sheet_row("2026-04-16", cluster)
    assert len(row) == 10
    assert row[0] == "2026-04-16"   # 날짜
    assert row[1] == "up"           # 방향
    assert row[2] == "2차전지"      # 섹터
    assert row[3] == 3              # 포함종목수
    assert "A" in row[4]            # 대표종목(3개)
    assert row[5] == 7.0            # 평균등락률(%)
    assert row[6] == 8.0            # 최대등락률(%)
    assert row[7] == "★★★★☆"       # 테마강도
    assert row[8] == 450.0          # 합산거래대금(억)
    assert "리튬" in row[9]         # 관련뉴스키워드(Top5)


def test_cluster_to_sheet_row_empty_keywords():
    """keywords_top5 가 빈 리스트일 때 키워드 컬럼은 빈 문자열."""
    from theme_cluster import cluster_to_sheet_row
    cluster = {
        "direction": "down",
        "sector": "바이오",
        "ticker_count": 3,
        "representatives": ["X"],
        "avg_change": -6.17,
        "max_change": -7.0,
        "intensity_stars": "★☆☆☆☆",
        "total_amount_100m": 450.0,
        "keywords_top5": [],
    }
    row = cluster_to_sheet_row("2026-04-16", cluster)
    assert row[9] == ""


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_intensity_ladder_exact_thresholds()
    test_intensity_middle_tiers()
    test_build_theme_clusters_empty_input()
    test_build_theme_clusters_min_3_tickers()
    test_build_theme_clusters_detects_up_cluster()
    test_build_theme_clusters_detects_down_cluster_separately()
    test_build_theme_clusters_threshold_boundary_inclusive()
    test_build_theme_clusters_threshold_boundary_below()
    test_build_theme_clusters_up_and_down_same_sector()
    test_build_theme_clusters_amount_nan()
    test_cluster_to_sheet_row_structure()
    test_cluster_to_sheet_row_empty_keywords()
    print("[PASS] all tests")
