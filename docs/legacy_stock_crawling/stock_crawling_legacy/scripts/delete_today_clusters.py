"""오늘 날짜의 테마클러스터 데이터를 삭제하고 재기록하는 스크립트."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import datetime as _dt

def main():
    from daily_trend_writer import MarketFlowSheet, make_sheet_client, THEME_CLUSTER_TAB, THEME_CLUSTER_HEADERS

    today = _dt.date.today()
    year = today.year
    date_str = today.strftime("%Y-%m-%d")

    gc = make_sheet_client()
    mf = MarketFlowSheet(gc, year)
    sh = mf.open_or_create()

    try:
        ws = sh.worksheet(THEME_CLUSTER_TAB)
    except Exception:
        print(f"[에러] '{THEME_CLUSTER_TAB}' 탭을 찾을 수 없습니다.")
        return 1

    values = ws.get_all_values()
    print(f"현재 행 수: {len(values)} (헤더 포함)")

    # 오늘 날짜 행 찾기 (첫 번째 컬럼이 날짜)
    rows_to_delete = []
    for i, row in enumerate(values):
        if i == 0:  # 헤더 스킵
            continue
        if row and row[0] == date_str:
            rows_to_delete.append(i + 1)  # gspread는 1-indexed

    if not rows_to_delete:
        print(f"[정보] {date_str} 데이터가 없습니다. 삭제할 것 없음.")
        return 0

    print(f"[정보] {date_str} 데이터 {len(rows_to_delete)}행 삭제 중...")

    # 뒤에서부터 삭제 (인덱스 밀림 방지)
    for row_idx in reversed(rows_to_delete):
        ws.delete_rows(row_idx)
        print(f"  삭제: row {row_idx}")

    print(f"[완료] {len(rows_to_delete)}행 삭제됨. 이제 파이프라인을 다시 실행하세요.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
