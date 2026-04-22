"""stock_scraper.py의 dry_run_indicator_check 출력에서 유니코드 특수문자를 ASCII로 교체."""
import re

with open("stock_scraper.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1) 박스 문자 ─ (U+2500) × 60 패턴
content = content.replace(
    "print(f\"\\n{'\\u2500' * 60}\")",
    "print('\\n' + '-' * 60)",
)
content = content.replace(
    "print(f\"{'\\u2500' * 60}\")",
    "print('-' * 60)",
)

# 2) DRY RUN 완료 라인
content = content.replace(
    "print(f\"\\n[DRY RUN 완료] row_data 길이={len(row_data)} (헤더 {len(headers)}개와 일치: {len(row_data)==len(headers)})\")",
    "length_ok = len(row_data) == len(headers)\n        "
    "print(f\"[DRY RUN OK] len={len(row_data)} header={len(headers)} match={'YES' if length_ok else 'NO'}\")",
)

# 3) 타입 검증 헤더
content = content.replace(
    "print(f\"[지표 타입 검증]\")",
    "print('[TYPE CHECK]')",
)

# 4) ✅ → OK, ❌ → NG  (check/cross emoji)
content = content.replace("'✅' if", "'OK' if")
content = content.replace("else '❌'", "else 'NG'")

with open("stock_scraper.py", "w", encoding="utf-8") as f:
    f.write(content)

print("patch done - ASCII ok")
