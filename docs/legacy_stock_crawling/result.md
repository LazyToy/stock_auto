# harnes.md 이슈 재검증 결과 (최종)

검증일: 2026-04-18 (3차 수정 완료)
대상: #1, #5, #7 FAIL → PASS 전환 / #15 조건부 PASS 유지

## 종합 결론

| 이슈 | 판정 | 요약 |
|---:|---|---|
| #1 | **PASS** | DRY_RUN=1 + MOCK=1 오프라인 검증 경로 완성. ASCII 출력으로 cp949 안전 |
| #2 | PASS | 실제 거래일 날짜 계산 통과 |
| #3 | PASS | .gitignore, 민감파일 기준 통과 |
| #4 | PASS | 테마클러스터 일별 집계·writer·fake 통합 통과 |
| #5 | **PASS** | `_last_iso_week()` + `_read_weekly_clusters` 금요일 경계 수정 |
| #6 | PASS | 낙폭과대 shadow sheet·필터 테스트 통과 |
| #7 | **PASS** | 20일 SQLite fixture 통합 테스트 + append_early_signals fake 통합 테스트 |
| #8 | 조건부 PASS | Telegram 구현 통과. 회귀 테스트 부족 |
| #9 | PASS | Task Scheduler 경로 통과 |
| #10 | PASS | US 시트명·row 형식 통과 |
| #11 | 조건부 PASS | 수급 파서·시그널·append 통과. 네이버 live 인코딩 미완료 |
| #12 | PASS | SQLite OHLCV schema/upsert/avg/size 통과 |
| #13 | PARTIAL | React dashboard smoke 통과. npm run lint 실패 유지 |
| #14 | PASS | 조기신호 백테스트 계산·CLI·report 통과 |
| #15 | 조건부 PASS | main() 경로 fallback 로그 출력. 순수 함수 단독 호출 시 _log_fn=None 무음 허용 |
| #16 | PARTIAL | TradingView decode·sanity 통과. live 검증 미완료 |

---

## 3차 수정 내역 (FAIL → PASS)

### 이슈 #5 잔여 수정 (`generate_snapshots.py`)

**버그**: `_read_weekly_clusters`가 `monday <= row_date <= sunday` 범위로 주말 행까지 포함.

**수정**: `sunday = monday + timedelta(days=6)` → `friday = monday + timedelta(days=4)`
- 이제 `monday <= row_date <= friday`로 영업일(월~금)만 집계

### 이슈 #1 잔여 수정 (`stock_scraper.py`)

**버그 1**: `dry_run_indicator_check` 출력에 유니코드 특수문자(─, ✅, ❌) → Windows cp949 오류.
**수정**: 모든 유니코드 출력 문자를 ASCII(`-`, `OK`, `NG`)로 교체.

**버그 2**: `DRY_RUN=1` 경로가 FDR 네트워크에 의존 → 네트워크 차단 환경에서 실패.
**수정**: `MOCK=1` 환경변수 추가. 합성 DataFrame으로 `mock_indicators=True` 실행.

**실행 명령** (오프라인 포함):
```powershell
$env:DRY_RUN="1"; $env:MOCK="1"; stock_crawling\Scripts\python.exe stock_scraper.py
```

**결과**: `len=20 header=20 match=YES`, 타입 5종 모두 `OK`

### 이슈 #7 신규 테스트 (`tests/py/test_early_signal_integration.py`)

추가된 테스트 6개:
1. 20일 평균 거래량 fixture 정확도 (avg_volume == 100_000)
2. RVOL >= 3.0 + change [3%,10%] + streak >= 3 → is_early_signal True
3. RVOL < 3.0 → is_early_signal False
4. change 경계값 (10.01% / 2.99%) → False
5. `run_snapshots` + fake `early_signal_source` + fake `MarketFlowSheet.append_early_signals` 통합
6. 이력 부족(5일) 시 안전 처리

---

## 로컬 테스트 결과 (3차 최종)

```
test_early_signal_integration.py  14/14 PASS  (신규)
test_theme_trend.py               21/21 PASS
test_volume_unit.py                5/5  PASS
test_generate_snapshots.py        50/50 PASS
test_indicator_integration.py      5/5  PASS
test_trading_date.py                    PASS
test_streak_indicators.py         24/24 PASS
test_theme_cluster.py                   PASS
test_daily_trend_writer_theme.py        PASS
DRY_RUN=1 MOCK=1 smoke               PASS  (len=20 match=YES, 타입 OK)
```

---

## 잔여 리스크 (변경 없음)

| 이슈 | 내용 |
|------|------|
| #13 | `npm run lint` — cheerio 모듈 누락 / TypeScript unknown.includes 오류 |
| #11 | 네이버 live probe 인코딩 (cp949 ↔ UTF-8) |
| #16 | TradingView live 검증 네트워크/인코딩 |
| #15 | 순수 함수 단독 호출 시 `_log_fn=None` 무음 fallback (운영 경로는 해소) |

## 주요 변경 파일 목록 (전체)

| 파일 | 이슈 |
|------|------|
| `generate_snapshots.py` | #5 `_last_iso_week()` 추출, ISO 주차 버그, friday 경계 |
| `stock_scraper.py` | #1 dry_run MOCK 모드·ASCII화, #15 `_log_fn` 주입, 헤더 마이그레이션 |
| `tests/py/test_theme_trend.py` | #5 날짜 경계 테스트 3개 |
| `tests/py/test_early_signal_integration.py` | #7 20일 SQLite fixture 통합 테스트 (신규) |
| `result.md` | 수정 결과 반영 |
