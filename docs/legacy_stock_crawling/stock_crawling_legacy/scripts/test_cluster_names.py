"""테마 클러스터 대표종목 이름 표시 단위 테스트."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from theme_cluster import build_theme_clusters, cluster_to_sheet_row

# 테스트 데이터: name 포함
df = pd.DataFrame({
    "ticker": ["005930", "000660", "035420", "051910", "006400", "003550"],
    "name":   ["삼성전자", "SK하이닉스", "NAVER", "LG화학", "삼성SDI", "LG"],
    "change": [6.0, 7.0, 8.0, -6.0, -7.0, -8.0],
    "amount": [1e10, 2e10, 3e10, 1e10, 2e10, 3e10],
})

sector_map = {
    "005930": "반도체", "000660": "반도체", "035420": "반도체",
    "051910": "화학", "006400": "화학", "003550": "화학",
}

clusters = build_theme_clusters(df, sector_map=sector_map, news_titles_by_ticker={})

print("=" * 60)
print("  대표종목 이름 표시 테스트")
print("=" * 60)
for c in clusters:
    print(f"  방향={c['direction']}, 섹터={c['sector']}")
    print(f"  대표종목: {c['representatives']}")
    row = cluster_to_sheet_row("2026-04-18", c)
    print(f"  시트행[4](대표종목 셀): {row[4]}")
    print()

if not clusters:
    print("[FAIL] 클러스터가 비어있음!")
else:
    has_name = any("(" in rep for c in clusters for rep in c["representatives"])
    if has_name:
        print("[PASS] 대표종목에 이름이 포함되어 있습니다!")
    else:
        print("[FAIL] 대표종목에 이름이 없습니다!")
