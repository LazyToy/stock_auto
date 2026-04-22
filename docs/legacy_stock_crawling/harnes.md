# 🎯 Stock Crawling 쉐도잉 도구 확장 — 하네스 엔지니어링 문서

| 항목 | 값 |
|------|-----|
| 문서 버전 | v1.0 |
| 작성일 | 2026-04-16 |
| 작성자 | analyst (result.md 기반) |
| 대상 프로젝트 | stock_crawling (KR/US 시장 쉐도잉 파이프라인) |
| 이슈 수 | 16개 (Phase 1: 5개 / Phase 2: 5개 / Phase 3: 4개 / Bugfix: 2개) |
| 상위 목표 | 기존 쉐도잉 시트는 유지한 채, "어떤 키워드/테마가 시장을 움직이는가" 를 관찰할 수 있도록 확장 |

---

## 📜 본 문서의 사용 원칙

### 본 문서는 두 종류의 AI에게 전달된다
1. **구현 AI** — 각 이슈를 코드로 구현 (TDD 엄수)
2. **검증 AI** — 구현 결과를 독립적으로 검증 (객관성 엄수)

### 양쪽 모두 지켜야 할 공통 원칙
- 본 문서에 명시되지 않은 부분을 **임의로 해석·확장하지 않는다**
- 판단이 애매하면 작업을 **중단**하고 사용자에게 옵션을 제시한다
- 기존 동작 파괴(regression)는 **절대 허용 불가**

---

## 🔑 공통 컨텍스트

### 역할 지정
너는 **한국·미국 주식 시장 쉐도잉 파이프라인**의 개발/검증 엔지니어다. 이 프로젝트는 매매 신호 감지기가 아니라 **"오늘 시장에서 터진 종목과 그 테마 흐름을 아카이브"** 하는 사후 관찰 도구다.

### 기술 스택
- **Python 3.11+** (주력)
  - FinanceDataReader, pandas, gspread, beautifulsoup4, urllib
- **TypeScript / Node 20+ + tsx** (Python 실행 wrapper)
- **Google Sheets API** (서비스 계정 인증)
- **Vite + React 19** (프론트엔드 쉘, 대부분 미사용)
- venv 위치: `stock_crawling/Scripts/python.exe` (Windows) / `stock_crawling/bin/python` (POSIX)

### 핵심 파일 맵
| 파일 | 역할 | 현재 규모 |
|------|------|----------|
| `stock_scraper.py` | KR 급등주·거래대금 쉐도잉 | ~402줄 |
| `us_stock_scraper.py` | US 급등주·거래대금 쉐도잉 | ~349줄 |
| `generate_snapshots.py` | KR/US 일별 스냅샷 + 뉴스요약 오케스트레이션 | ~205줄 |
| `daily_trend_writer.py` | 시장트렌드_YYYY 스프레드시트 I/O | ~289줄 |
| `streak_indicators.py` | 52주신고/신저, 연속봉, ATR14 **(구현됐으나 미연결)** | ~159줄 |
| `news_fetcher.py` | KR/US 뉴스 타이틀 수집 | ~185줄 |
| `news_aggregator.py` | 키워드 추출 + Gemini 요약 | ~152줄 |
| `sector_map_kr.py` | WICS 섹터 맵 + 캐시 | ~334줄 |
| `gemini_client.py` | Gemini REST 클라이언트 (urllib 기반) | ~280줄 |
| `tests/py/test_market_trend.py` | KR/US 시장 스냅샷 빌더 | ~360줄 |
| `tests/py/test_*.py` | 단위 테스트 (pytest 아님, 직접 실행) | 다수 |
| `runners/run_daily.ts` | 일일 파이프라인 오케스트레이터 | ~111줄 |
| `service_account.json` | Google Cloud SA 키 (루트, 보안 민감) | - |
| `.env` | Gemini API 키 (루트, 보안 민감) | - |

### 테스트 관행 (매우 중요)
- 이 프로젝트는 **pytest를 사용하지 않는다.** `tests/py/test_*.py` 파일은 각자 `if __name__ == "__main__":` 으로 실행되는 독립 스크립트다.
- 기존 테스트 패턴 참고: `tests/py/test_streak_indicators.py`, `tests/py/test_news_aggregator.py`, `tests/py/test_daily_trend_writer.py`
- 테스트는 **순수 함수(pure function)** 위주로 짜고, 외부 I/O는 **injectable callable** 로 주입받게 분리한다 (예: `http_get`, `sleep`, `clock`, `fetcher`).
- 네트워크/Google Sheets 실 호출은 단위 테스트에서 금지. 반드시 stub/fake로 대체.

### 코딩 규칙

**Always:**
- 모든 사용자 대상 문자열(로그, 시트 헤더, 에러 메시지)은 **한국어** 로 작성
- 새 Python 모듈은 기존 코드 컨벤션 따라 `from __future__ import annotations` + 타입 힌트 사용
- 외부 I/O가 있는 함수는 **injectable callable** 로 분리 (테스트 가능하게)
- `datetime`, `time.sleep`, `urllib.request`, `gspread` 호출은 의존성 주입 가능 구조로
- **한 번 수정할 때마다 반드시 해당 테스트 파일을 먼저 실행하여 Red 확인 → 구현 → Green 확인**
- 기존 시트 헤더 변경 시 `get_existing_keys()` 의 컬럼 인덱스 재확인 필수

**Never:**
- 기존 시트 워크시트명 변경 금지 (`급등주_쉐도잉`, `거래대금_쉐도잉`, `KR_일별`, `US_일별`, `뉴스요약`)
- 기존 dedup key 로직 파괴 금지 (`(date_str, ticker_str)` 형태)
- `service_account.json` / `.env` 를 코드에서 직접 출력/로깅 금지
- 전역 상태 도입 금지 (모듈 수준 mutable state)
- pytest, unittest, pytest-plugins 설치 금지 (기존 스타일 유지)
- `requirements.txt` 에 있지 않은 외부 라이브러리를 **말 없이** 추가 금지 (의존성 추가 필요 시 사용자에게 먼저 확인)

### 구현 AI가 반드시 지켜야 할 5가지 원칙

1. **정보 부족·판단 분기 시 즉시 멈춤**
   - "이 이슈에서 파일명을 X로 할지 Y로 할지 명시되어 있지 않다" → 진행 중단, 객관적 옵션(A/B/C) 제시, 사용자 결정 대기
   - "기존 시트 컬럼 순서와 새 컬럼 삽입 위치가 충돌한다" → 중단, 둘의 trade-off 제시
   - 추측으로 뚫고 가지 않는다

2. **변경 영향 최소화 + 확장성 고려**
   - 기존 파일을 고칠 때 해당 함수만 수정하고 인접 함수는 건드리지 않는다
   - 신규 기능은 **신규 모듈**로 격리 (예: `theme_cluster.py`, `rvol_computer.py`)
   - `stock_scraper.py` 의 `task1_surge_stocks`, `task2_high_volume_stocks` 의 시그니처는 변경하지 않는다 (하위 호환)
   - 공용 로직은 함수로 분리하되, 한 군데서만 쓸 것은 미리 추상화하지 않는다

3. **독립적 작업은 서브 에이전트 병렬 위임**
   - 의존성 그래프에서 서로 독립적인 이슈(예: 이슈 3 보안점검 ↔ 이슈 1 컬럼추가)는 서브 에이전트 2개를 병렬로 띄워서 동시 진행
   - 병렬 위임 시 각 서브 에이전트에게 **해당 이슈 섹션 + 공통 컨텍스트만** 주입 (다른 이슈 컨텍스트는 제외)

4. **TDD 사이클 엄수 (Red → Green → Refactor)**
   - **Red**: 실패하는 테스트를 먼저 작성하고 실제로 실행해서 실패를 확인한다 (fail for the right reason)
   - **Green**: 테스트를 통과하는 **최소한의** 구현을 작성한다 (over-engineering 금지)
   - **Refactor**: 테스트가 계속 통과하는 것을 확인하며 중복 제거·명명 개선
   - **테스트 없이는 코드를 단 한 줄도 작성하지 않는다**

5. **보고 형식**
   변경 완료 후 반드시 아래 형식으로 보고:
   - ✅ 수정/추가된 파일 목록 (파일 경로 + 절대 경로)
   - ✅ Red 단계에서 작성한 테스트 파일과 초기 실패 로그
   - ✅ Green 단계 이후 테스트 통과 로그
   - ✅ 변경 내용 (diff 형식 또는 핵심 요약)
   - ✅ 영향 범위 (기존 기능 중 영향 받는 것, 받지 않는 것)
   - ✅ 남은 미결 사항 / 후속 이슈와의 연관성

### 검증 AI가 반드시 지켜야 할 원칙

1. **객관성**: 구현 AI의 주장을 액면 그대로 믿지 않는다. 코드를 **직접 읽고** 확인한다.
2. **항목별 실증**: 완료 판정 기준(AC) 각 항목에 대해 **"어떻게 확인했는지"** 를 명시한다 (예: "stock_scraper.py:215에서 compute_indicators 호출 확인", "test_xxx.py 실행 로그 첨부").
3. **논리적 결함 탐지**: 본 문서에 없는 항목이라도, 코드를 보다가 발견한 논리 오류·엣지케이스 누락·잠재적 regression은 반드시 지적 사항에 포함한다.
4. **회귀 확인**: 기존 시트/기능이 깨지지 않았는지 실행 또는 코드 리뷰로 확인한다.
5. **애매할 때 FAIL**: AC 중 하나라도 명확히 통과했다고 말할 수 없으면 **FAIL** 처리. 관대한 판정 금지.

### 보고 형식 (검증 AI)

```
[전체 결과] ✅ PASS / ❌ FAIL

[AC별 검증 결과]
AC-1: ✅ / ❌  — {근거: 어느 파일 어느 라인에서 어떻게 확인했는지}
AC-2: ✅ / ❌  — {근거}
...

[회귀 검증]
- 기존 {시트명/기능명}: ✅ 영향 없음 / ❌ 영향 있음
...

[논리적 결함·추가 지적 (AC 외)]
- {지적 1}: {파일:라인, 상황, 위험성}
- {지적 2}: ...

[수정 제안]
- {제안 1}
- {제안 2}
```

---

## 📋 이슈 목록

| # | 이슈 | Phase | 복잡도 | 핵심 파일 | 선행 이슈 |
|---|------|-------|--------|----------|----------|
| 1 | `streak_indicators` 를 기존 시트에 연결 (컬럼 5개 추가) | 1 | 🟨 중간 | stock_scraper.py, us_stock_scraper.py | 없음 |
| 2 | 날짜 불일치 버그 수정 (FDR 실제 거래일 사용) | 1 | ⬜ 낮음 | stock_scraper.py | 없음 |
| 3 | 보안 점검 (.gitignore + git history + API 키) | 1 | ⬜ 낮음 | .gitignore | 없음 |
| 4 | `테마클러스터_일별` 시트 구현 | 1 | 🟥 높음 | theme_cluster.py (신규), daily_trend_writer.py | 없음 |
| 5 | `테마트렌드_주간` 시트 구현 | 1 | 🟨 중간 | theme_trend.py (신규), daily_trend_writer.py | #4 |
| 6 | `낙폭과대_관찰` 시트 구현 | 2 | ⬜ 낮음 | stock_scraper.py, us_stock_scraper.py | 없음 |
| 7 | `조기신호_관찰` 시트 (RVOL 기반) | 2 | 🟥 높음 | rvol_computer.py (신규), early_signal.py (신규) | #12 |
| 8 | Telegram 알림 연동 | 2 | 🟨 중간 | telegram_notifier.py (신규) | 없음 |
| 9 | 자동 스케줄링 (Windows Task Scheduler) | 2 | ⬜ 낮음 | scripts/install_schedule.ps1 (신규) | 없음 |
| 10 | US 스크래퍼 날짜 형식 통일 (코드↔문서) | 2 | ⬜ 낮음 | us_stock_scraper.py 또는 CLAUDE.md | 없음 |
| 11 | `수급전환_포착` 시트 (외국인/기관) | 3 | 🟥 높음 | flow_fetcher.py (신규), flow_signal.py (신규) | 없음 |
| 12 | SQLite 이력 축적 (20일 거래량 저장소) | 3 | 🟨 중간 | ohlcv_store.py (신규) | 없음 |
| 13 | React 대시보드 (테마 히트맵) | 3 | 🟥 높음 | src/App.tsx, src/api/sheets.ts | #4 |
| 14 | 조기신호→급등주 연결 백테스트 | 3 | 🟥 높음 | backtest_early_signal.py (신규) | #7, #12 |
| 15 | 거래대금 단위 보정 휴리스틱 개선 | Bug | ⬜ 낮음 | stock_scraper.py | 없음 |
| 16 | TradingView 포지셔널 디코딩 sanity check | Bug | ⬜ 낮음 | us_stock_scraper.py, tests/py/test_market_trend.py | 없음 |

### 의존성 다이어그램

```
Phase 1 (독립적 병렬 실행 가능 그룹)
  #1  ──┐
  #2  ──┤
  #3  ──┤── (모두 독립)
  #4  ──┘──→ #5
                  #5

Phase 2
  #6, #8, #9, #10 ── (독립)
  #12 ──→ #7

Phase 3
  #4 ──→ #13
  #7, #12 ──→ #14
  #11 ── (독립)

Bugfix (독립)
  #15, #16
```

### 병렬 실행 가능 그룹 (권장)

- **그룹 A (즉시 병렬 가능):** #1, #2, #3, #10, #15, #16
- **그룹 B (그룹 A 이후):** #4, #6, #8, #9, #12
- **그룹 C (#4 완료 후):** #5, #13
- **그룹 D (#12 완료 후):** #7, #11
- **그룹 E (#7 완료 후):** #14

---

# Phase 1 — 최우선 이슈

## 이슈 1: `streak_indicators` 를 기존 시트에 연결 (컬럼 5개 추가)

### 4.1 🔍 문제 정의

**현상**: `streak_indicators.py` 에 52주 신고/신저, 연속봉, ATR14 가 이미 구현되어 있으나 `stock_scraper.py`, `us_stock_scraper.py` 어디에서도 import 되지 않고 있다. 기존 쉐도잉 시트에서 **"이 종목이 어떤 맥락(신고가 근처? 연속 양봉? 변동성 큰 종목?)에서 급등했는지"** 를 전혀 알 수 없다.

**근본 원인**:
1. 연결 누락: `stock_scraper.py`, `us_stock_scraper.py` 에 `from streak_indicators import ...` 가 없음
2. 시트 헤더 미반영: 기존 헤더에 관련 컬럼이 없음

**영향 범위**: `급등주_쉐도잉`, `거래대금_쉐도잉`, `미국_급등주_쉐도잉`, `미국_거래대금_쉐도잉` 네 개 워크시트.

---

### 4.2 📦 구현 지시

**전제 조건**:
- `streak_indicators.py` 의 `compute_indicators(df)` 가 dict `{is_52w_high, is_52w_low, streak_days, atr14, atr14_pct}` 를 반환함을 먼저 확인한다.
- `tests/py/test_streak_indicators.py` 가 통과하는 상태임을 확인한다.

**수정/생성 대상 파일**:
- 수정: `stock_scraper.py`, `us_stock_scraper.py`
- 생성: `tests/py/test_indicator_integration.py`

**추가될 5개 컬럼** (두 쌍의 시트에 동일하게):
| 컬럼명 | 타입 | 소스 | 비고 |
|-------|------|------|------|
| `52주신고` | str | `is_52w_high` | True → `"신고"`, False → `""` |
| `52주신저` | str | `is_52w_low` | True → `"신저"`, False → `""` |
| `연속봉` | int | `streak_days` | 부호 포함 (+5 / -3 / 0) |
| `ATR14(%)` | float | `atr14_pct` | 소수점 둘째 자리 |
| `갭(%)` | float | 별도 계산 | `(today_open - prev_close) / prev_close * 100` |

**삽입 위치** (기존 컬럼 밀지 않도록):
- `급등주_쉐도잉`, `거래대금_쉐도잉`: 기존 `키워드` 컬럼 **뒤에** 추가
- `미국_급등주_쉐도잉`, `미국_거래대금_쉐도잉`: 기존 `키워드` 컬럼 **뒤에** 추가

즉, 기존 헤더 끝에 5개를 **append** 만 한다. 중간 삽입 금지. 이유: `resize_cells_for_images` 의 `start_col_index`, `end_col_index` 가 차트 컬럼 인덱스에 의존하므로 그 값이 바뀌지 않아야 한다.

**Red 단계 (테스트 먼저)**:

`tests/py/test_indicator_integration.py` 에 다음 테스트를 작성:

```python
"""
지표 통합 테스트 - streak_indicators 출력을 시트 row에 주입하는 함수 검증.
"""
from __future__ import annotations
import pandas as pd

def test_build_indicator_columns_all_fields_present():
    """compute_indicators 결과 + prev_close/today_open 으로 5개 컬럼 값이 나와야 한다."""
    from stock_scraper import build_indicator_columns  # 아직 없음 → Red
    indicators = {"is_52w_high": True, "is_52w_low": False,
                  "streak_days": 5, "atr14": 1200.0, "atr14_pct": 3.24}
    cols = build_indicator_columns(indicators, prev_close=10000.0, today_open=10500.0)
    assert cols == ["신고", "", 5, 3.24, 5.0]

def test_build_indicator_columns_empty_52w():
    indicators = {"is_52w_high": False, "is_52w_low": False,
                  "streak_days": -2, "atr14": 0.0, "atr14_pct": 0.0}
    cols = build_indicator_columns(indicators, prev_close=10000.0, today_open=9500.0)
    assert cols == ["", "", -2, 0.0, -5.0]

def test_build_indicator_columns_gap_zero_prev():
    """prev_close==0 인 방어 케이스 — 갭은 0.0 으로."""
    from stock_scraper import build_indicator_columns
    indicators = {"is_52w_high": False, "is_52w_low": True,
                  "streak_days": 0, "atr14": 100.0, "atr14_pct": 1.11}
    cols = build_indicator_columns(indicators, prev_close=0.0, today_open=100.0)
    assert cols[4] == 0.0

if __name__ == "__main__":
    test_build_indicator_columns_all_fields_present()
    test_build_indicator_columns_empty_52w()
    test_build_indicator_columns_gap_zero_prev()
    print("[PASS] all tests")
```

**실제로 실행하여 ImportError / NameError 로 실패하는 것을 확인** 후 Green 단계로 넘어간다.

**Green 단계 (최소 구현)**:

`stock_scraper.py` 상단 import 섹션에 추가:
```python
from streak_indicators import compute_indicators
```

새 순수 함수를 `stock_scraper.py` 의 헬퍼 섹션에 추가:
```python
def build_indicator_columns(indicators: dict, prev_close: float, today_open: float) -> list:
    """compute_indicators 결과 + 전일종가/금일시가로 5개 컬럼 값 생성."""
    gap = 0.0
    if prev_close and prev_close > 0:
        gap = round((today_open - prev_close) / prev_close * 100, 2)
    return [
        "신고" if indicators["is_52w_high"] else "",
        "신저" if indicators["is_52w_low"] else "",
        int(indicators["streak_days"]),
        round(float(indicators["atr14_pct"]), 2),
        gap,
    ]
```

`task1_surge_stocks`, `task2_high_volume_stocks` 내부 루프에서 차트 수식 생성 근처에 다음 로직 삽입:
- 종목별 FDR DataReader 로 최근 280거래일 OHLCV 조회 (52주=252일 + 여유분)
- `compute_indicators(df_detail)` 호출
- `build_indicator_columns(...)` 호출하여 `row_data` 끝에 append

헤더에 5개 컬럼 문자열 추가.

`us_stock_scraper.py` 도 동일 패턴으로 수정 (단, US 데이터는 Yahoo Finance 또는 FDR 사용. 기존 코드에서 이미 OHLCV 소스가 없다면 **이 부분은 구현 AI가 중단하고 옵션 제시**: A) FDR DataReader 로 추가 호출 B) TradingView scanner에 `VWAP`, `High.52W`, `Low.52W` 컬럼 추가 C) US는 이번 이슈에서 제외).

**Refactor 단계**:
- KR/US 양쪽에서 중복되는 "FDR DataReader + compute_indicators + build_indicator_columns" 시퀀스가 명확히 반복되면 `enrich_with_indicators(ticker)` 헬퍼로 분리. 그렇지 않으면 분리하지 않는다 (premature abstraction 금지).

**경계 조건 (하지 말 것)**:
- ❌ 기존 헤더 순서 변경
- ❌ `resize_cells_for_images` 의 `start_col_index`, `end_col_index` 인자 값 변경 (차트 컬럼 위치 불변)
- ❌ `streak_indicators.py` 자체 수정 (이미 테스트 통과 상태)
- ❌ FDR DataReader 타임아웃 없이 호출 (기존 패턴 따라 `concurrent.futures` + 15초 타임아웃)

**완료 조건**:
- `build_indicator_columns` 3개 테스트 모두 통과
- `stock_scraper.py` 를 dry-run 모드(1종목만)로 실행했을 때 에러 없이 row 끝에 5개 값이 들어감 (실 시트 쓰기는 하지 않아도 됨 — stdout print 로 확인)
- 기존 헤더의 차트 컬럼 인덱스가 변하지 않음
- 수정 파일 목록 + diff + 실행 로그 보고

---

### 4.3 ✅ 완료 판정 기준 (AC)

| # | 기준 | 검증 방법 |
|---|------|----------|
| AC-1 | `stock_scraper.py` 에 `from streak_indicators import compute_indicators` import 추가 | grep 또는 파일 열람 |
| AC-2 | `build_indicator_columns` 순수 함수가 존재하고 3개 단위 테스트를 모두 통과 | `python tests/py/test_indicator_integration.py` 실행 |
| AC-3 | `task1_surge_stocks`, `task2_high_volume_stocks` 의 `row_data` 에 5개 값이 끝에 append 됨 | 코드 리뷰 + stdout 로그 |
| AC-4 | `us_stock_scraper.py` 도 동일 패턴 적용 또는 "제외 사유 + 후속 이슈 제안" 이 보고됨 | 코드 리뷰 + 보고서 |
| AC-5 | 헤더에 5개 컬럼명(`52주신고`, `52주신저`, `연속봉`, `ATR14(%)`, `갭(%)`)이 키워드 **뒤에** 추가됨 | 헤더 리스트 리뷰 |
| AC-6 | `resize_cells_for_images(worksheet, 11, 14)`, `(12, 15)` 인자값이 변경되지 않음 | grep 으로 원본 유지 확인 |
| AC-7 | 기존 `tests/py/test_streak_indicators.py` 계속 통과 | 실행 로그 |
| AC-8 | dry-run 로그에 52주신고/연속봉/ATR/갭 값이 1건 이상 실제 채워져 출력됨 | stdout 캡처 |

---

### 4.4 🔍 검증 지시

```
[작업 지시]
이슈 1 "streak_indicators 를 기존 시트에 연결" 구현이 완료되었다. 검증해줘.

[1단계: 정적 검증]
1. 아래 명령을 실제 실행:
   - python tests/py/test_indicator_integration.py
   - python tests/py/test_streak_indicators.py
   각각 [PASS] 로그가 나와야 함.

2. 코드 리뷰 (stock_scraper.py):
   □ `from streak_indicators import compute_indicators` 존재
   □ `build_indicator_columns` 함수 존재 + docstring 존재
   □ task1_surge_stocks 의 headers 리스트 끝에 5개 컬럼 추가됨
   □ task2_high_volume_stocks 의 headers 리스트 끝에 5개 컬럼 추가됨
   □ row_data 의 append 순서가 headers 순서와 1:1 매핑되는지
   □ resize_cells_for_images(ws, 11, 14) / (12, 15) 가 그대로 유지되는지

3. 코드 리뷰 (us_stock_scraper.py):
   □ 동일 패턴 적용 여부 OR 명시적 제외 사유 보고 여부

[2단계: 동적 검증 (가능하면)]
□ stock_scraper.py 를 "DRY_RUN" 모드(시트 쓰기 스킵)로 1종목만 돌렸을 때 
  row_data 에 5개 값이 모두 들어가는지 stdout 로 확인
□ 값의 타입 확인: 52주신고/신저는 str, 연속봉은 int, ATR14(%)/갭(%)은 float

[3단계: 회귀 검증]
□ 기존 헤더의 "날짜", "종목명", "종목코드" 등 순서가 바뀌지 않았는지
□ 기존 뉴스1~3, 차트3종(KR) / 차트6종(US) 컬럼 순서가 유지되는지
□ get_existing_keys 의 인덱스(row[0], row[2]) 가 여전히 유효한지

[4단계: 논리적 결함 탐지]
- prev_close == 0 방어 로직 유무
- FDR DataReader 호출 시 타임아웃 지정 여부 (기존 패턴은 15초)
- 종목별 DataReader 추가 호출로 인한 성능 영향 (30종목 × 2초 = 60초?) → 개선 제안
- is_52w_high 판정 시 데이터가 52주에 못 미치는 신규 상장 종목의 처리

[보고 형식]
위 공통 섹션의 "검증 AI 보고 형식" 따름.
```

---

## 이슈 2: 날짜 불일치 버그 수정 (FDR 실제 거래일 사용)

### 4.1 🔍 문제 정의

**현상**: `stock_scraper.py:334` 에서 `today_str = today.strftime("%Y%m%d")` 로 **실행 시점 날짜**를 사용하고 있다. FDR이 반환하는 데이터는 "가장 최근 영업일" 기준이므로:
- 토요일 실행 → `today_str`은 토요일이지만 데이터는 금요일
- 공휴일도 마찬가지
→ dedup key 가 실제 거래일과 어긋나 중복 저장 발생

**근본 원인**: `stock_scraper.py:334` — 실행 시점 캘린더 날짜와 데이터 거래일의 혼용.

**영향 범위**: KR 쉐도잉 시트 전체의 dedup key 정합성.

---

### 4.2 📦 구현 지시

**전제 조건**: FDR의 `StockListing('KRX')` 결과에 `Date` 컬럼이 있거나, 별도 방법으로 "최근 영업일" 을 얻을 수 있음을 확인 (존재하지 않으면 구현 AI는 중단하고 옵션 제시: A) FDR에 Date 컬럼 유무 확인 후 있으면 사용 B) FDR DataReader('KS11', ...) 의 마지막 Index 사용 C) `pandas_market_calendars` 라이브러리 도입).

**수정 대상**: `stock_scraper.py`, 신규 `tests/py/test_trading_date.py`.

**Red**:

```python
# tests/py/test_trading_date.py
from datetime import datetime

def test_resolve_trading_date_uses_fdr_date_column_when_present():
    from stock_scraper import resolve_trading_date
    # FDR 데이터에 Date 컬럼이 있고 모두 같은 날짜일 때
    import pandas as pd
    df = pd.DataFrame({"Date": ["2026-04-17"] * 3})
    assert resolve_trading_date(df, now=datetime(2026, 4, 18)) == "20260417"

def test_resolve_trading_date_falls_back_to_now_when_no_date_column():
    from stock_scraper import resolve_trading_date
    import pandas as pd
    df = pd.DataFrame({"Code": ["005930"]})  # Date 없음
    assert resolve_trading_date(df, now=datetime(2026, 4, 17)) == "20260417"

def test_resolve_trading_date_uses_most_common_when_mixed():
    """혼재 시 최빈 거래일 사용."""
    from stock_scraper import resolve_trading_date
    import pandas as pd
    df = pd.DataFrame({"Date": ["2026-04-17", "2026-04-17", "2026-04-16"]})
    assert resolve_trading_date(df, now=datetime(2026, 4, 18)) == "20260417"

if __name__ == "__main__":
    test_resolve_trading_date_uses_fdr_date_column_when_present()
    test_resolve_trading_date_falls_back_to_now_when_no_date_column()
    test_resolve_trading_date_uses_most_common_when_mixed()
    print("[PASS]")
```

**Green**:

`stock_scraper.py` 에 순수 함수 추가:
```python
def resolve_trading_date(df, now: datetime.datetime) -> str:
    """FDR 데이터에서 실제 거래일을 YYYYMMDD 로 반환. Date 컬럼 없으면 now 기준."""
    if "Date" in df.columns and not df["Date"].isna().all():
        dates = pd.to_datetime(df["Date"], errors="coerce").dropna()
        if len(dates) > 0:
            most_common = dates.mode().iloc[0]
            return most_common.strftime("%Y%m%d")
    return now.strftime("%Y%m%d")
```

`main()` 내부에서 `today_str` 재계산:
```python
today_str = resolve_trading_date(df_krx, today)
month_str = datetime.datetime.strptime(today_str, "%Y%m%d").strftime("%Y%m")
```

**Refactor**: 없음 (한 번만 쓰이는 순수 함수).

**경계 조건**:
- ❌ `today.strftime` 호출을 지우지 말 것 (fallback 으로 여전히 필요)
- ❌ 다른 파일에서 `today_str` 을 재정의하지 말 것

**완료 조건**: 3개 테스트 통과 + `main()` 에서 `resolve_trading_date` 사용 + 로그에 "거래일: {date}" 출력.

---

### 4.3 ✅ AC

| # | 기준 | 검증 방법 |
|---|------|----------|
| AC-1 | `resolve_trading_date` 순수 함수 존재 + 3개 테스트 통과 | 테스트 실행 |
| AC-2 | `main()` 에서 `today_str = resolve_trading_date(df_krx, today)` 형태로 사용 | 코드 리뷰 |
| AC-3 | `month_str` 도 `today_str` 기반 재계산 | 코드 리뷰 |
| AC-4 | 실행 시 "거래일: YYYYMMDD" 로그 출력 | stdout |
| AC-5 | 기존 dedup 로직(`get_existing_keys`) 과 호환 | 코드 리뷰 |

---

### 4.4 🔍 검증 지시

```
[정적 검증]
1. python tests/py/test_trading_date.py 실행 → [PASS]
2. 코드 리뷰:
   □ FDR Date 컬럼 유무 확인 로직
   □ NaN/빈값 방어 로직
   □ pd.to_datetime errors="coerce" 사용 여부
   □ Date 컬럼 없을 때 fallback 로직

[동적 검증]
□ 토요일/일요일 시각으로 now 를 주입했을 때 금요일 날짜가 반환되는지
□ 공휴일 다음날 시뮬레이션 (이전 영업일이 반환되는지)

[논리적 결함 탐지]
- Date 컬럼이 문자열이 아닌 datetime64일 때도 동작하는가
- 시간대(KST vs UTC) 혼란 가능성
- 월 경계(31일 → 1일)에서 month_str 이 제대로 전환되는가
- US 스크래퍼(us_stock_scraper.py)에도 유사 문제가 있는지 추가 확인 → 있으면 지적
```

---

## 이슈 3: 보안 점검 (.gitignore + git history + API 키)

### 4.1 🔍 문제 정의

**현상**: 루트에 `service_account.json` (Google Cloud SA private key), `.env` (Gemini API key 3개) 존재. 이들이 `.gitignore` 에 없으면 git push 시 유출 위험.

**근본 원인**: 미확인 상태.

**영향 범위**: Google Cloud 계정, Gemini API 쿼터/과금.

---

### 4.2 📦 구현 지시

**전제 조건**: 이 이슈는 **점검 성격** 이며 코드 변경은 조건부다. TDD 가 어색할 수 있으나, 점검 결과를 검증 가능한 체크리스트로 작성한다.

**수정 대상**: `.gitignore` (조건부).

**순서**:

1. `.gitignore` 읽기. 다음 항목이 모두 포함되어 있는지 확인:
   - `.env`
   - `.env.local`
   - `service_account.json`
   - `*.json` 의 일부로 포함되어 있다면 명시적으로 `service_account.json` 추가 권장

2. 누락이 있으면 추가.

3. git log 에 해당 파일이 과거 커밋된 적 있는지 확인:
   ```bash
   git log --all --full-history -- .env .env.local service_account.json
   ```

4. 결과를 보고:
   - (A) git history 에 없음 → `.gitignore` 만 보완하고 완료
   - (B) git history 에 있음 → **작업 중단**. 다음 옵션 제시:
     - B-1) API 키 즉시 교체 + git history 정리 (`git filter-repo` 또는 BFG)
     - B-2) API 키 교체만 하고 기록은 그대로 (리포가 private 인 경우)
     - 사용자 결정 대기

**Red 가 애매한 경우**: 이 이슈는 "checklist 확인" 이 본질이므로 TDD 대신 **체크리스트 실행 로그** 로 완료 증거를 대체한다.

**경계 조건**:
- ❌ 검증자가 재현할 수 있도록 명령 로그(stdout/stderr)를 남길 것
- ❌ API 키 값을 로그에 출력 금지 (마스킹 필수)

**완료 조건**:
- `.gitignore` 에 3개 파일 패턴 포함 확인 로그
- `git log --all --full-history -- ...` 실행 결과 로그
- 히스토리 존재 시 사용자에게 옵션 제시

---

### 4.3 ✅ AC

| # | 기준 | 검증 방법 |
|---|------|----------|
| AC-1 | `.gitignore` 에 `.env`, `.env.local`, `service_account.json` 3개 모두 포함 | 파일 읽기 |
| AC-2 | `git log --all --full-history -- .env service_account.json` 실행 결과 첨부 | 보고서 |
| AC-3 | 히스토리 존재 시 옵션(B-1/B-2)가 사용자에게 제시되고 대기 상태 | 보고서 |
| AC-4 | 작업 로그에 API 키 값이 포함되지 않음 | 로그 검사 |

---

### 4.4 🔍 검증 지시

```
[정적 검증]
1. .gitignore 파일 열어서 세 파턴 존재 확인
2. git ls-files | grep -E "\.(env|local)$|service_account\.json" 실행 → 결과가 없어야 함

[동적 검증]
□ git log 결과 재실행하여 구현 AI의 보고와 일치하는지 교차 확인

[논리적 결함 탐지]
- .env.local 이 별도로 존재하는가 (gemini_client.load_api_key 는 .env.local 을 읽음)
- .env 와 .env.local 의 역할 구분이 문서화되어 있는가
- service_account.json 외 다른 credential 파일이 있는지 find로 확인
- __pycache__, *.pyc 도 .gitignore 에 있는지 (보안은 아니지만 위생)
```

---

## 이슈 4: `테마클러스터_일별` 시트 구현

### 4.1 🔍 문제 정의

**현상**: 사용자 목적("어떤 키워드 종목이 어떤 흐름을 가져가는지")의 핵심이 되는 시트가 없다. 개별 종목만 나열되고, 같은 섹터/테마 동시 이상 움직임 패턴이 묻힌다.

**근본 원인**: 데이터 집계 레이어 부재.

**영향 범위**: 신규 기능. 기존 기능에 영향 없음.

---

### 4.2 📦 구현 지시

**전제 조건**:
- `sector_map_kr.py` 의 `SectorMapKR.classify()` 정상 동작
- `news_aggregator.py` 의 `extract_keywords()` 정상 동작
- `daily_trend_writer.py` 의 `DailyTrendSheet` 패턴 숙지

**수정/생성 대상 파일**:
- 신규: `theme_cluster.py` (순수 로직)
- 신규: `tests/py/test_theme_cluster.py`
- 수정: `daily_trend_writer.py` (새 탭 I/O 추가)
- 신규: `tests/py/test_daily_trend_writer_theme.py`
- 수정: `generate_snapshots.py` (오케스트레이션 훅 추가)

**발동 조건 (명시)**:
- 동일 WICS 섹터 내에서 **3종목 이상** 이 ±5% 이상 움직일 때 해당 섹터를 "클러스터" 로 기록
- 상승 방향과 하락 방향은 별도 행으로 (direction 컬럼 추가)

**대상 스프레드시트**: `시장흐름_{YYYY}` (신규, `DailyTrendSheet` 와 별도 클라이언트)
**대상 워크시트명**: `테마클러스터_일별`

**헤더** (최종):
```
날짜, 방향, 섹터, 포함종목수, 대표종목(3개), 평균등락률(%), 최대등락률(%), 테마강도, 합산거래대금(억), 관련뉴스키워드(Top5)
```

**테마강도 산출 로직** (명시, 구현 AI가 임의로 결정 금지):
```
n = 포함종목수, avg = 평균등락률 절대값
★☆☆☆☆: n >= 3
★★☆☆☆: n >= 5 or avg >= 3
★★★☆☆: n >= 7 or avg >= 5
★★★★☆: n >= 10 or avg >= 7
★★★★★: n >= 15 or avg >= 10
(복수 조건 만족 시 더 높은 강도 채택)
```

**Red (핵심 테스트만 발췌)**:

```python
# tests/py/test_theme_cluster.py
import pandas as pd

def test_build_theme_clusters_empty_input():
    from theme_cluster import build_theme_clusters
    df = pd.DataFrame(columns=["ticker", "sector", "change", "amount"])
    assert build_theme_clusters(df, sector_map={}, news_titles_by_ticker={}) == []

def test_build_theme_clusters_min_3_tickers():
    """같은 섹터 2종목은 클러스터로 잡히지 않는다."""
    from theme_cluster import build_theme_clusters
    df = pd.DataFrame([
        {"ticker": "A", "sector": "2차전지", "change": 7.0, "amount": 100e8},
        {"ticker": "B", "sector": "2차전지", "change": 6.0, "amount": 200e8},
    ])
    assert build_theme_clusters(df, sector_map={"A": "2차전지", "B": "2차전지"},
                                news_titles_by_ticker={}) == []

def test_build_theme_clusters_detects_up_cluster():
    from theme_cluster import build_theme_clusters
    df = pd.DataFrame([
        {"ticker": "A", "sector": "2차전지", "change": 7.0, "amount": 100e8},
        {"ticker": "B", "sector": "2차전지", "change": 6.0, "amount": 200e8},
        {"ticker": "C", "sector": "2차전지", "change": 8.0, "amount": 150e8},
    ])
    clusters = build_theme_clusters(
        df, sector_map={"A": "2차전지", "B": "2차전지", "C": "2차전지"},
        news_titles_by_ticker={"A": ["리튬 수주 호재"], "B": ["ESS 계약"],
                               "C": ["유럽 관세 리스크 해소"]},
    )
    assert len(clusters) == 1
    c = clusters[0]
    assert c["direction"] == "up"
    assert c["sector"] == "2차전지"
    assert c["ticker_count"] == 3
    assert len(c["representatives"]) == 3
    assert abs(c["avg_change"] - 7.0) < 0.01
    assert c["max_change"] == 8.0
    assert c["intensity_stars"] in ("★☆☆☆☆", "★★☆☆☆")  # n=3, avg=7 → ★★☆☆☆ 승격
    assert abs(c["total_amount_100m"] - 450.0) < 0.01  # 450억
    assert len(c["keywords_top5"]) <= 5

def test_build_theme_clusters_detects_down_cluster_separately():
    from theme_cluster import build_theme_clusters
    df = pd.DataFrame([
        {"ticker": "X", "sector": "바이오", "change": -6.0, "amount": 100e8},
        {"ticker": "Y", "sector": "바이오", "change": -5.5, "amount": 200e8},
        {"ticker": "Z", "sector": "바이오", "change": -7.0, "amount": 150e8},
    ])
    clusters = build_theme_clusters(
        df, sector_map={"X": "바이오", "Y": "바이오", "Z": "바이오"},
        news_titles_by_ticker={},
    )
    assert len(clusters) == 1
    assert clusters[0]["direction"] == "down"
    assert clusters[0]["avg_change"] < 0

def test_intensity_ladder_exact_thresholds():
    """강도 계산 로직의 경계값 테스트."""
    from theme_cluster import compute_intensity
    assert compute_intensity(n=3, avg_abs=2.5) == "★☆☆☆☆"
    assert compute_intensity(n=5, avg_abs=2.5) == "★★☆☆☆"
    assert compute_intensity(n=3, avg_abs=3.0) == "★★☆☆☆"
    assert compute_intensity(n=7, avg_abs=0.1) == "★★★☆☆"
    assert compute_intensity(n=15, avg_abs=0.1) == "★★★★★"
    assert compute_intensity(n=3, avg_abs=10.0) == "★★★★★"
```

**Green (구현 지시)**:

`theme_cluster.py`:

```python
"""
theme_cluster — 일별 테마 클러스터 집계 (순수 로직).

시장 전종목 데이터에서 같은 섹터 내 3종목 이상 ±5% 이상 움직임을 감지하여
'오늘의 테마'로 묶는다. 네트워크/시트 I/O 없음.
"""
from __future__ import annotations
from typing import Any
import pandas as pd

THRESHOLD_CHANGE = 5.0
MIN_TICKERS = 3

def compute_intensity(n: int, avg_abs: float) -> str:
    """n(종목수), avg_abs(평균등락률 절대값) 기반 강도 등급."""
    # 우선순위: 더 높은 조건 하나라도 만족하면 그 등급
    if n >= 15 or avg_abs >= 10: return "★★★★★"
    if n >= 10 or avg_abs >= 7:  return "★★★★☆"
    if n >= 7  or avg_abs >= 5:  return "★★★☆☆"
    if n >= 5  or avg_abs >= 3:  return "★★☆☆☆"
    return "★☆☆☆☆"

def build_theme_clusters(
    df: pd.DataFrame,
    *,
    sector_map: dict[str, str],
    news_titles_by_ticker: dict[str, list[str]],
) -> list[dict]:
    """
    Parameters
    ----------
    df : columns = ticker, change, amount (필수)
    sector_map : {ticker: sector_name}
    news_titles_by_ticker : {ticker: [title1, title2, ...]}

    Returns
    -------
    list[dict] with keys:
      date, direction, sector, ticker_count, representatives,
      avg_change, max_change, intensity_stars, total_amount_100m,
      keywords_top5
    """
    # 구현 생략 (명세 기반 작성)
    ...
```

`daily_trend_writer.py` 에 새 클래스 또는 기존 `DailyTrendSheet` 에 탭 추가:
- 신규 클래스 `MarketFlowSheet` 권장 (스프레드시트 이름이 `시장흐름_{YYYY}` 로 다름)
- 또는 `DailyTrendSheet` 를 확장해 `open_or_create` 시 `시장트렌드_` 외에 `시장흐름_` 도 지원하도록
- **구현 AI는 이 분기점에서 옵션 제시 후 사용자 결정 대기**: A) 새 클래스 / B) 기존 클래스 확장

`generate_snapshots.py` 의 `run_snapshots` 에 `theme_source` 훅 추가 (기존 `news_source` 패턴 그대로 복제, 독립적으로 실패 isolation).

**Refactor**: 테마 클러스터 계산 후 `to_sheet_row(cluster)` 직렬화 함수를 별도로 두어 단위 테스트 용이하게.

**경계 조건**:
- ❌ `stock_scraper.py` 수정 금지 (이 이슈는 신규 모듈만)
- ❌ 실시간 네트워크 호출을 `theme_cluster.py` 내부에서 하지 말 것 (순수 함수 유지)
- ❌ Gemini 호출 금지 (키워드는 `extract_keywords` 의 TF 기반만)

**완료 조건**: 테스트 전부 통과 + `run_daily.ts` 실행 시 `시장흐름_2026` 에 `테마클러스터_일별` 탭이 생성되고 1행 이상 기록됨 (해당 날에 클러스터 조건이 없으면 0행도 허용하되 로그에 사유 명시).

---

### 4.3 ✅ AC

| # | 기준 | 검증 방법 |
|---|------|----------|
| AC-1 | `theme_cluster.py` 존재, `build_theme_clusters`, `compute_intensity` 순수 함수 | 파일 리뷰 |
| AC-2 | `tests/py/test_theme_cluster.py` 5개 이상 테스트 모두 통과 | 실행 |
| AC-3 | `compute_intensity` 의 경계값(n=3, n=5, n=7, n=10, n=15, avg=3, 5, 7, 10) 테스트 커버 | 테스트 코드 리뷰 |
| AC-4 | Direction=up / down 분리 기록 | 테스트 + 시트 샘플 |
| AC-5 | 헤더 순서가 명세와 일치 | 코드 |
| AC-6 | `시장흐름_{YYYY}` 스프레드시트 신규 생성되거나 기존 확장 (결정 근거 명시) | 보고서 |
| AC-7 | `run_daily.ts` 혹은 `generate_snapshots.py main()` 에 통합되어 실제 작성됨 | 실행 로그 |
| AC-8 | 실패 isolation: 테마 파트가 에러 나도 KR/US 스냅샷 append 는 완료 | 코드 리뷰 |

---

### 4.4 🔍 검증 지시

```
[정적 검증]
1. python tests/py/test_theme_cluster.py 실행 → [PASS]
2. python tests/py/test_daily_trend_writer_theme.py 실행 → [PASS]
3. 코드 리뷰:
   □ theme_cluster.py 에 외부 I/O 없음 (grep for urllib, requests, gspread)
   □ THRESHOLD_CHANGE=5.0, MIN_TICKERS=3 상수 노출
   □ up/down 분리 로직 (두 번 그룹화)
   □ 대표종목 3개 선정 기준 (|change| desc? amount desc? → 명세 확인, 문서와 다르면 지적)
   □ keywords_top5 는 extract_keywords 활용

[동적 검증 — Sheet 실 쓰기 검증 단계]
□ 소량 샘플 DataFrame 으로 실제 시트에 쓴 후, Google Sheets 에서 헤더/데이터 육안 확인
□ 같은 날 재실행 시 중복 없이 skip 되는가 (dedup key: (date, direction, sector))
□ 클러스터 0개인 날 로그 확인

[회귀 검증]
□ 기존 KR_일별, US_일별, 뉴스요약 시트 변경 없음
□ 기존 급등주_쉐도잉, 거래대금_쉐도잉 영향 없음
□ run_daily.ts 의 3단계 파이프라인 순서 변동 없음

[논리적 결함 탐지]
- 대표종목 3개 선정 기준이 문서에 명시되어 있지 않다면 지적하고 확인 요청
- |change| 가 정확히 5.0 인 경계값 포함/제외 여부
- sector_map 에 없는 ticker (UNKNOWN_SECTOR="기타") 처리: "기타" 클러스터로 묶일 위험
- 같은 티커가 여러 섹터에 매핑되는 일이 있는가 (sector_map 단일값이므로 없음, 확인)
- 거래대금(amount)이 NaN 인 경우 합산 처리
- 뉴스 없는 종목이 대다수인 날 keywords_top5 가 빈 리스트일 때의 시트 표현
```

---

## 이슈 5: `테마트렌드_주간` 시트 구현

### 4.1 🔍 문제 정의

**현상**: 일별 테마는 포착되더라도 "이번 주에 어떤 테마가 **부상/쇠퇴** 중인지" 는 여전히 수동 집계 필요.

**영향 범위**: 이슈 #4 의 부속 집계 시트.

---

### 4.2 📦 구현 지시

**전제 조건**: 이슈 #4 완료.

**수정/생성 대상**:
- 신규: `theme_trend.py`
- 신규: `tests/py/test_theme_trend.py`
- 수정: `daily_trend_writer.py` 또는 `MarketFlowSheet` 에 주간 탭 I/O 추가
- 수정: `generate_snapshots.py` (매주 일요일에만 실행되는 조건부 호출 추가)

**발동 조건**: **매주 일요일** 또는 **월요일 첫 실행** 시 지난주(월~금) 테마클러스터 데이터 집계.

**헤더**:
```
주차(ISO), 섹터, 출현빈도, WoW변화, 주간누적평균등락률(%), 대표종목, 주요뉴스키워드(Top5)
```

**WoW 변화 문자열**:
- 지난주 대비 증가 → `▲ +N`
- 지난주 대비 감소 → `▼ -N`
- 변동 없음 → `─ 0`
- 이번 주 처음 등장 → `NEW`
- 지지난주에 있었는데 지난주에 사라진 섹터는 포함하지 않음

**Red**:

```python
def test_weekly_aggregate_empty():
    from theme_trend import aggregate_weekly
    assert aggregate_weekly([], prev_week_frequencies={}) == []

def test_weekly_aggregate_new_sector():
    from theme_trend import aggregate_weekly
    daily_clusters = [
        {"sector": "2차전지", "avg_change": 7.0, "ticker_count": 3, "representatives": ["A", "B", "C"], "keywords_top5": [("리튬", 3)]},
        {"sector": "2차전지", "avg_change": 5.0, "ticker_count": 4, "representatives": ["A", "B", "D"], "keywords_top5": [("유럽", 2)]},
    ]
    rows = aggregate_weekly(daily_clusters, prev_week_frequencies={})
    assert len(rows) == 1
    assert rows[0]["sector"] == "2차전지"
    assert rows[0]["frequency"] == 2
    assert rows[0]["wow_change"] == "NEW"

def test_weekly_aggregate_wow_increase():
    from theme_trend import aggregate_weekly
    daily_clusters = [{"sector": "바이오", "avg_change": 5.0, "ticker_count": 3, "representatives": [], "keywords_top5": []}] * 5
    rows = aggregate_weekly(daily_clusters, prev_week_frequencies={"바이오": 2})
    assert rows[0]["wow_change"] == "▲ +3"
```

**Green**: 명세 기반 구현.

**경계 조건**:
- ❌ 이슈 #4 의 `build_theme_clusters` 시그니처 변경 금지
- ❌ 신규 네트워크 호출 금지 (이전 주 데이터는 이미 기록된 시트에서 읽거나, 일별 누적본에서 파생)

**완료 조건**: 5개 이상 테스트 통과 + 일요일 실행 시 `테마트렌드_주간` 탭에 기록.

---

### 4.3 ✅ AC

| # | 기준 | 검증 방법 |
|---|------|----------|
| AC-1 | `theme_trend.py` + 순수 함수 `aggregate_weekly` 존재 | 리뷰 |
| AC-2 | 테스트 5개 이상 통과 | 실행 |
| AC-3 | WoW 4가지 케이스(NEW, ▲, ▼, ─) 모두 테스트 커버 | 테스트 리뷰 |
| AC-4 | ISO 주차 형식 YYYY-W## 사용 | 샘플 확인 |
| AC-5 | 월요일 실행 시에만 발동하는 조건문 존재 (수동 강제 옵션도) | 코드 리뷰 |

---

### 4.4 🔍 검증 지시

```
[정적 검증]
1. python tests/py/test_theme_trend.py → [PASS]

[동적 검증]
□ 이번 주 일요일 저녁 실행 시 "테마트렌드_주간" 1건 이상 기록
□ 같은 주 재실행 시 dedup 으로 스킵

[논리적 결함 탐지]
- ISO 주차 계산의 연말 경계(예: 2026-W52 vs 2027-W01)
- prev_week_frequencies 를 어디서 조회하는가 (이전 주 시트 or 인메모리 캐시?) → 불명확하면 지적
- 지난주 있었고 이번주 없는 섹터는 레코드에 포함하지 않는다는 명세 확인
- 월요일 아침 실행 vs 일요일 저녁 실행 중 어느 것을 "이번 주 집계" 로 볼지 — 타임존 고려
```

---

# Phase 2 — 선택 확장 이슈

## 이슈 6: `낙폭과대_관찰` 시트

### 4.1 🔍 문제 정의
급락주 미수집으로 시장 공포/반등 후보 아카이브 불가능.

### 4.2 📦 구현 지시
**수정 대상**: `stock_scraper.py`, `us_stock_scraper.py`.
**패턴**: 기존 `task1_surge_stocks` 복제 후 **부호 반대로** 적용.
- KR: `ChagesRatio <= -15%` 또는 `거래대금 >= 500억 and change <= -6%`
- 워크시트명: `낙폭과대_쉐도잉` (KR), `미국_낙폭과대_쉐도잉` (US)
- 헤더는 기존 `급등주_쉐도잉` 과 동일하게 (대칭성)

**Red**: `test_drop_stocks_filter.py` 에 필터 로직 단위 테스트 (`filter_drop_stocks(df, threshold=-15)` 순수 함수).

**Green**: 기존 task 복제, 이름만 `task3_drop_stocks`, 임계값 부호 반대.

**경계 조건**:
- ❌ `task1`, `task2` 코드는 건드리지 말 것 (복제만)
- ❌ 헤더 구조 변경 금지 (기존과 동일)

### 4.3 ✅ AC
- AC-1 `filter_drop_stocks` 순수 함수 + 테스트
- AC-2 신규 워크시트 `낙폭과대_쉐도잉` 생성 및 1건 이상 기록
- AC-3 US 스크래퍼도 동일 패턴 적용 (또는 명시적 제외 사유)
- AC-4 `main()` 에서 `task3_drop_stocks` 호출 추가

### 4.4 🔍 검증 지시
```
[정적] 코드 리뷰 — task1 과 task3 의 차이점이 부호와 워크시트명뿐인지 확인
[동적] 실제 실행 시 급락주 1건 이상 기록
[논리적 결함]
- 상한가(+29.5%) 대칭인 하한가(-29.5%) 도 limit_down 으로 표시되는가
- 단계별 필터 순서(절대 등락률 vs 거래대금) 가 task1/task2 와 일관된가
```

---

## 이슈 7: `조기신호_관찰` 시트 (RVOL 기반)

### 4.1 🔍 문제 정의
급등 "전조" 를 포착해서 기존 급등주 시트와 사후 비교하여 신호 유효성 검증.

### 4.2 📦 구현 지시
**전제 조건**: 이슈 #12 (SQLite 20일 이력) 완료.

**수정/생성**:
- 신규: `rvol_computer.py` + `tests/py/test_rvol_computer.py`
- 신규: `early_signal.py` + `tests/py/test_early_signal.py`
- 수정: `daily_trend_writer.py` 에 `조기신호_관찰` 탭 I/O
- 수정: `generate_snapshots.py` 에 훅 추가

**발동 조건 (AND)**:
- `RVOL = today_volume / avg_20d_volume >= 3.0`
- `change` 가 `[+3%, +10%]` 구간 (이미 15%+ 는 급등주 시트로 감)
- (`streak_days >= 3` AND 양봉) OR `close >= 52주고가 * 0.95`

**후속 수익률 추적**: 기록 후 5영업일 뒤 자동 재방문하여 `5일후수익률(%)` 컬럼 업데이트. 이 업데이트는 별도 스케줄 잡 (또는 `run_daily.ts` 에서 매일 "과거 5일 전 조기신호 레코드" 를 찾아 수익률 채움).

**Red (핵심)**:
```python
def test_compute_rvol_basic():
    from rvol_computer import compute_rvol
    assert compute_rvol(today=300, avg20=100) == 3.0

def test_compute_rvol_zero_avg_returns_none():
    from rvol_computer import compute_rvol
    assert compute_rvol(today=100, avg20=0) is None

def test_early_signal_gated_by_rvol():
    from early_signal import is_early_signal
    # RVOL 2.5 → 미달
    assert is_early_signal(change=5, rvol=2.5, streak=3, close_ratio_52w=0.9) is False

def test_early_signal_hits_streak_branch():
    from early_signal import is_early_signal
    assert is_early_signal(change=5, rvol=3.0, streak=3, close_ratio_52w=0.5) is True

def test_early_signal_hits_52w_near_high_branch():
    from early_signal import is_early_signal
    assert is_early_signal(change=5, rvol=3.0, streak=1, close_ratio_52w=0.96) is True

def test_early_signal_out_of_range_upper():
    from early_signal import is_early_signal
    # 이미 +12% — 조기 아님
    assert is_early_signal(change=12, rvol=3.0, streak=5, close_ratio_52w=1.0) is False
```

**Green**: 명세 기반 구현.

**경계 조건**:
- ❌ 이슈 #12의 SQLite 스키마 완료 전에는 시작 금지 → 시작하려 하면 중단하고 사용자에게 "#12 선행 필요" 보고
- ❌ 기존 `task1/task2` 수정 금지

### 4.3 ✅ AC
- AC-1 `rvol_computer.py` + 2개 테스트
- AC-2 `early_signal.py` + 5개 테스트 (경계 조건 커버)
- AC-3 `조기신호_관찰` 탭 실 쓰기
- AC-4 5일후수익률 업데이트 스케줄 메커니즘 명시 (코드 또는 문서)
- AC-5 이슈 #12 선행 확인

### 4.4 🔍 검증 지시
```
[정적] 5개 분기(RVOL 미달/통과 × streak vs 52w) 모두 테스트 커버
[동적] 실제 SQLite 에 20일 이력이 있을 때 1종목 이상 잡히는지
[논리적 결함]
- RVOL 분모의 avg_20d_volume 이 거래량(shares) 인지 거래대금(won) 인지 일관성
- 52주 신고가가 아직 확정되지 않은 신규 상장 종목 처리
- 5일후수익률 업데이트가 빠진 레코드(비영업일 실행, 데이터 누락) 처리
- 이미 급등주 시트에 기록된 종목이 동일한 날 조기신호로도 잡히는 이중 기록 여부
```

---

## 이슈 8: Telegram 알림 연동

### 4.1 🔍 문제 정의
실시간성 확보. 쉐도잉 결과가 시트에만 있고 푸시 채널이 없음.

### 4.2 📦 구현 지시
**수정/생성**:
- 신규: `telegram_notifier.py` + `tests/py/test_telegram_notifier.py`
- 수정: `.env.local` 에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 로드 (`gemini_client.load_api_key` 패턴 재사용)
- 수정: `generate_snapshots.py` 에 알림 훅 추가 (실패 isolation)

**알림 정책**:
- KR 급등주 ≥ 5건 → 요약 메시지 1개
- 테마클러스터 ★★★★☆ 이상 → 즉시 메시지 1개
- 전 작업 실패 → 에러 메시지

**Red**: `http_post` injectable 로 받아 fake 응답으로 테스트 (`gemini_client.py` 패턴).

**Green**: `urllib.request` 로 `https://api.telegram.org/bot{TOKEN}/sendMessage` POST.

**경계 조건**:
- ❌ 토큰을 로그에 출력 금지
- ❌ 동기 요청 타임아웃 생략 금지 (10초)
- ❌ 테스트에서 실 API 호출 금지

### 4.3 ✅ AC
- AC-1 `telegram_notifier.py` + 3개 이상 테스트 (성공/실패/토큰 없음)
- AC-2 `.env.local` 에 토큰 파싱 추가
- AC-3 `generate_snapshots.py` 의 알림 실패는 snapshot 성공에 영향 없음
- AC-4 토큰 마스킹 확인 (`****TOKEN_SUFFIX`)

### 4.4 🔍 검증 지시
```
[정적] http_post injectable 패턴 준수, timeout 지정, 토큰 노출 없음
[동적] 실제 토큰으로 1회 전송 (샌드박스 채팅방 권장)
[논리적 결함]
- Telegram API rate limit (초당 30건) 고려 여부
- 유니코드/이모지 메시지 전송 시 인코딩 이슈
- chat_id 오타로 인한 403 처리
```

---

## 이슈 9: 자동 스케줄링 (Windows Task Scheduler)

### 4.1 🔍 문제 정의
수동 실행 의존. 영업일 오후 15:40 (KR 마감 10분 후), 아침 06:10 KST (US 마감 10분 후) 자동 실행 필요.

### 4.2 📦 구현 지시
**생성**:
- `scripts/install_schedule.ps1` (Windows)
- `scripts/README_schedule.md` (수동 등록 가이드)

**PowerShell 개요**:
```powershell
$action_kr = New-ScheduledTaskAction -Execute "npx" -Argument "tsx runners/run_daily.ts" -WorkingDirectory "D:\HY\develop_Project\stock_crawling"
$trigger_kr = New-ScheduledTaskTrigger -Daily -At 15:40
Register-ScheduledTask -TaskName "StockCrawling_KR_Daily" -Action $action_kr -Trigger $trigger_kr -RunLevel Highest
# US 용 06:10 트리거도 동일 패턴
```

**Red/Green**: PowerShell 은 TDD 가 어색 → 대신 "등록 후 조회" 스크립트 (`scripts/verify_schedule.ps1`) 와 스모크 실행 로그로 대체.

**경계 조건**:
- ❌ 사용자 권한 없이 Register 시도하지 말 것 (`RunLevel Highest` 로 권한 확인 유도)
- ❌ 기존 등록된 태스크 덮어쓰기 경고 없이 하지 말 것

### 4.3 ✅ AC
- AC-1 install/verify 스크립트 둘 다 존재
- AC-2 등록 후 `Get-ScheduledTask -TaskName StockCrawling_*` 으로 확인
- AC-3 로그 파일 경로 지정 (`--log-file=logs/run_daily_YYYYMMDD.log`)

### 4.4 🔍 검증 지시
```
[정적] 스크립트 내용 검토 — 하드코딩된 절대경로가 있다면 지적
[동적] 스크립트 실제 실행 (관리자 권한)
[논리적 결함]
- 공휴일에도 실행됨 → 한국/미국 영업일 캘린더 연동 고려 여부
- 네트워크 미연결 시 실패 핸들링
```

---

## 이슈 10: US 스크래퍼 날짜 형식 통일 (코드↔문서)

### 4.1 🔍 문제 정의
`us_stock_scraper.py:268` 은 `YYYYMM` 월 단위, CLAUDE.md 는 `YYYY-MM-DD` 일 단위라고 명시 → 문서-코드 불일치.

### 4.2 📦 구현 지시
**옵션 제시 후 사용자 결정 대기**:
- **A**: 코드를 문서에 맞춰 `YYYY-MM-DD` 일 단위로 변경 (매일 새 스프레드시트 생성 → Drive 오염 우려)
- **B**: 문서를 코드에 맞춰 `YYYYMM` 월 단위로 수정 (단일 월 스프레드시트에 누적)
- **C**: 하이브리드 — 스프레드시트명은 월 단위, 내부 워크시트에 일 단위 파티셔닝

구현 AI는 이 이슈에서 **반드시 선택 전 중단**하고 사용자 결정을 받는다.

**Green**: 결정된 안에 따라 수정.

### 4.3 ✅ AC
- AC-1 코드/문서가 한 방향으로 일치
- AC-2 `today_str` 변경 시 기존 dedup key 와의 호환성 확인
- AC-3 기존 기록 데이터 마이그레이션 필요 여부 판단 및 보고

### 4.4 🔍 검증 지시
```
[정적] 코드/문서 grep 교차 확인
[동적] 실제 1회 실행으로 파일명 규칙 확인
[논리적 결함]
- 기존에 저장된 월 단위 스프레드시트와 새 일 단위 스프레드시트가 혼재하는 경우
- gspread create() 가 같은 이름 여러 개를 허용하는 문제
```

---

# Phase 3 — 심화 이슈

## 이슈 11: `수급전환_포착` 시트 (외국인/기관)

### 4.1 🔍 문제 정의
KR 시장 흐름의 결정 요소인 외국인·기관 수급 부재.

### 4.2 📦 구현 지시
**생성**:
- `flow_fetcher.py` — `https://finance.naver.com/item/frgn.naver?code={ticker}` 파싱
- `tests/py/test_flow_fetcher.py` — 고정된 HTML 샘플로 파싱 단위 테스트
- `flow_signal.py` — "5일 연속 외국인 순매도 → 당일 순매수 전환" 같은 규칙 구현
- `tests/py/test_flow_signal.py`
- `daily_trend_writer` or `MarketFlowSheet` 에 `수급전환_포착` 탭

**Red**: HTML fixture + `parse_foreign_institutional_flow(html)` 테스트.

**경계 조건**:
- ❌ 대량 크롤링(초당 >2회) 금지 (sleep 0.5s)
- ❌ 네트워크 실 호출 테스트 금지 → fixture 사용

### 4.3 ✅ AC
- 파서 + 시그널 모두 단위 테스트 존재
- 네이버 HTML 구조 변경 내성 (None/빈 테이블 방어)
- 샘플 실행 후 시트 1건 이상 기록

### 4.4 🔍 검증 지시
```
[정적] BeautifulSoup 셀렉터가 네이버 현행 구조와 일치하는지 (live probe)
[논리적 결함]
- 장중 실행 시 "당일 수급" 미확정 값이 들어오는 위험
- 외국인 순매수 전환 판정의 모호성 (직전 5거래일이 모두 매도여야 하는가, 누적이 음수면 되는가)
- 수급 데이터 지연 (1~2일 늦게 공시되는 경우)
```

---

## 이슈 12: SQLite 이력 축적 (20일 거래량 저장소)

### 4.1 🔍 문제 정의
RVOL 계산을 위한 20일 이력 저장소가 없어 매번 FDR DataReader 호출 → 느리고 불안정.

### 4.2 📦 구현 지시
**생성**:
- `ohlcv_store.py` — SQLite 스키마: `daily_ohlcv(ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, amount REAL, PRIMARY KEY(ticker, date))`
- `tests/py/test_ohlcv_store.py` — `:memory:` DB 로 테스트
- 일일 파이프라인에 "오늘 데이터 upsert" 훅 추가
- `compute_avg_volume(ticker, window=20)` 조회 API

**Red**:
```python
def test_ohlcv_upsert_and_avg():
    from ohlcv_store import OHLCVStore
    s = OHLCVStore(":memory:")
    for d, v in [("20260401", 100), ("20260402", 200), ("20260403", 300)]:
        s.upsert("005930", d, open_=0, high=0, low=0, close=0, volume=v, amount=0)
    assert s.avg_volume("005930", window=3) == 200.0
```

**Green/Refactor**: sqlite3 stdlib 만 사용.

**경계 조건**:
- ❌ ORM 도입 금지 (stdlib sqlite3)
- ❌ 전종목 × 20일 = ~50,000 행 이상 → 인덱스 필수

### 4.3 ✅ AC
- `daily_ohlcv` 테이블 생성 + PRIMARY KEY 검증
- upsert 동일키 2회 호출 시 덮어쓰기
- avg_volume N일 이동평균 정확
- 300MB 이상 시 경고 로그

### 4.4 🔍 검증 지시
```
[정적] sqlite3 만 사용 (pip 의존성 추가 없음)
[동적] 실제 100종목 upsert 후 avg_volume 조회 시간 < 50ms
[논리적 결함]
- ticker 정규화 (KR 은 zfill(6), US 는 대문자)
- 공휴일/주말 upsert 중복 시도
- DB 파일 경로가 repo 내부인지 외부인지 명시
```

---

## 이슈 13: React 대시보드 (테마 히트맵)

### 4.1 🔍 문제 정의
`src/App.tsx` 가 비어있음. 일/주간 테마 히트맵 가시화 가능성 미활용.

### 4.2 📦 구현 지시
**수정/생성**:
- `src/App.tsx` — 메인 페이지
- `src/api/sheets.ts` — Google Sheets API v4 fetch wrapper (readonly, service account 키로 인증)
- `src/components/ThemeHeatmap.tsx` — 섹터×일자 그리드
- `src/components/ThemeTrendTimeline.tsx` — 주간 추세
- `tests/ts/` 는 지금 단순 probe 이므로, 컴포넌트 테스트는 `vitest` 도입 여부 **사용자 확인 후 결정**

**Red**: `vitest` 도입 시 컴포넌트 테스트 먼저 작성. 도입 안 하면 별도 스모크 스크립트.

**경계 조건**:
- ❌ 서비스 계정 private key 를 브라우저에 노출 금지 — 백엔드 API 서버(express) 경유 or OAuth2
- ❌ DISABLE_HMR 가드 제거 금지 (vite.config.ts)

### 4.3 ✅ AC
- 테마 히트맵 컴포넌트가 1달치 이상 데이터 렌더
- 서비스 키 노출 없음
- `npm run build` 성공

### 4.4 🔍 검증 지시
```
[정적] src/ 이하에서 service_account 문자열 grep → 0 hits
       .env.local 에 VITE_PUBLIC_ 이 아닌 키를 브라우저 코드가 읽는지
[동적] npm run dev 로 로컬 실행, 샘플 데이터 렌더링
[논리적 결함]
- Google Sheets API 레이트리밋 (분당 60) 대응
- 대량 데이터 렌더 성능 (virtualization 없음 → 지적)
- CORS 설정
```

---

## 이슈 14: 조기신호→급등주 연결 백테스트

### 4.1 🔍 문제 정의
조기신호 시트에 쌓인 데이터의 "실제 유효성" 을 확인할 수단 없음.

### 4.2 📦 구현 지시
**전제**: #7, #12 완료.

**생성**:
- `backtest_early_signal.py`
- `tests/py/test_backtest_early_signal.py`

**분석 항목**:
- 조기신호 기록일 +1, +3, +5일 수익률 분포
- 조기신호 중 실제 급등주 시트(15%+) 로 진입한 비율
- 섹터별 hit rate

**출력**: `reports/backtest_YYYYMMDD.md` 파일 자동 생성.

### 4.3 ✅ AC
- 1개월 이상 이력 기준 리포트 자동 생성
- median, 25/75분위수, win rate 포함
- 기간/조건 필터링 CLI 인자 지원

### 4.4 🔍 검증 지시
```
[정적] 통계 계산 로직 정확성 (pandas quantile)
[논리적 결함]
- survivorship bias: 상장폐지 종목 제외 여부 명시
- lookahead bias: 시그널 발생일의 close 를 entry price 로 쓸지 다음날 open 으로 쓸지
```

---

# Bugfix 이슈

## 이슈 15: 거래대금 단위 보정 휴리스틱 개선

### 4.1 🔍 문제 정의
`stock_scraper.py:381-382` 의 `if max < 10_000_000_000: ×1_000_000` 가 silent corruption 위험.

### 4.2 📦 구현 지시
**수정**: `stock_scraper.py`.

**개선 방향**:
- FDR 버전을 런타임에 감지 (`fdr.__version__`)
- 삼성전자(005930) 또는 SK하이닉스 거래대금을 sanity anchor 로 사용
- 단위 추정 로그 출력 (silent 제거)

**Red**:
```python
def test_infer_volume_unit_if_krw():
    from stock_scraper import infer_volume_unit
    import pandas as pd
    df = pd.DataFrame({"Code": ["005930"], "Amount": [5e11]})  # 5천억
    assert infer_volume_unit(df) == 1  # 배율

def test_infer_volume_unit_if_million_krw():
    from stock_scraper import infer_volume_unit
    import pandas as pd
    df = pd.DataFrame({"Code": ["005930"], "Amount": [5e5]})  # 50만(백만원 단위로 해석하면 5천억)
    assert infer_volume_unit(df) == 1_000_000
```

**Green**: 삼성전자 기준값 범위로 판정하는 순수 함수.

### 4.3 ✅ AC
- `infer_volume_unit` 순수 함수 + 2개 이상 테스트
- `main()` 에서 로그 출력 (예: `[단위감지] FDR Amount 단위: 원 (배율 1)`)
- silent 분기 제거

### 4.4 🔍 검증 지시
```
[논리적 결함]
- 삼성전자 거래정지일에는 anchor 가 0 → 차선 anchor 필요
- 시장 개장 전 실행 시 Amount 가 모두 0인 경우
```

---

## 이슈 16: TradingView 포지셔널 디코딩 sanity check

### 4.1 🔍 문제 정의
`us_stock_scraper.py:96-106` 의 `d[0]..d[8]` 위치 기반 파싱이 TradingView 응답 변경에 취약.

### 4.2 📦 구현 지시
**수정**: `us_stock_scraper.py`, `tests/py/test_market_trend.py`.

**개선**:
- 디코딩 직후 sanity check: `close > 0`, `volume_value >= 0`, `ticker matches ^[A-Z.]+$`
- 첫 N건에서 1건이라도 실패 시 경고 + 전체 응답 로깅 (키 없이)
- 디코딩 함수를 순수 함수로 분리: `decode_tv_row(d: list) -> dict`

**Red**:
```python
def test_decode_tv_row_ok():
    from us_stock_scraper import decode_tv_row
    d = ["AAPL", "Apple Inc.", 150.0, 2.5, 1e9, 151.0, 149.0, 2.5e12, "Technology"]
    assert decode_tv_row(d)["ticker"] == "AAPL"

def test_decode_tv_row_bad_close_raises():
    from us_stock_scraper import decode_tv_row
    d = ["AAPL", "Apple Inc.", 0, 0, 0, 0, 0, 0, ""]
    import pytest  # 이 프로젝트는 pytest 안 씀 → try/except 로 대체
    try:
        decode_tv_row(d, strict=True)
        assert False, "should have raised"
    except ValueError:
        pass
```

(프로젝트 규약상 pytest 미사용 → `try/except + assert False` 패턴)

### 4.3 ✅ AC
- `decode_tv_row` 순수 함수 존재 + 테스트
- sanity check 실패 비율이 5% 초과 시 stderr 경고
- 기존 `get_tradingview_data()` 는 `decode_tv_row` 사용하도록 리팩토링

### 4.4 🔍 검증 지시
```
[논리적 결함]
- 일부 ticker 가 "."을 포함 (BRK.A, BRK.B) — 정규식 허용 여부
- volume 0 인 ETF/신규 상장 허용
- sanity 실패 시 해당 행만 drop 할지 전체 실패 처리할지 정책
```

---

## 📋 실행 순서 (권장)

### 순서 결정 근거
- **#1, #2, #3, #15** 는 독립적이고 짧아서 먼저 처리 → 빠른 성공 확보 + 기존 데이터 정합성 확보
- **#12** 는 #7, #14 의 기반 → Phase 2~3 진입 전 구축
- **#4** 는 사용자의 핵심 목적 → Phase 1 에서 가장 중요. 단 복잡도가 높으므로 #1~#3 이후
- **#5** 는 #4 의 파생
- **#13** 는 사용자의 프론트 여력 + 사용자 확인 필요 (도입 여부) → 맨 뒤
- **#14** 는 #7, #12 완료 후 가능

### 권장 실행 흐름
```
Week 1: #1, #2, #3, #15  (Phase 1 상반)    — 병렬 가능
Week 1: #4                                   — #1~#3 과 동시 가능
Week 2: #5, #6, #16                          — #4 완료 대기 후 #5
Week 2-3: #10, #12                           — 의존성 적음
Week 3-4: #7, #11, #9, #8                    — #12 완료 후 #7
Week 5+: #14, #13                            — #7 완료 후 #14, 사용자 승인 후 #13
```

### 병렬 위임 지침 (구현 AI용)
- 그룹 A (Week 1 병렬): 서브 에이전트 3개 동시 띄움
  - SubAgent-1: 이슈 #1 (streak 연결)
  - SubAgent-2: 이슈 #2 + #15 (stock_scraper.py 버그/개선, 한 사람이 처리)
  - SubAgent-3: 이슈 #3 (보안 점검, read-only 성격)
- 그룹 B: 이슈 #4 는 복잡도가 높고 혼자 처리 권장 (여러 파일 동시 수정).

---

## 🚨 장애 대응

### 검증 실패 시
```
[이전 구현에서 아래 검증 결과가 나왔어. 수정해줘]

<검증 AI 보고서 붙여넣기>

해당 이슈의 "구현 지시" 섹션을 다시 확인하고, 위 FAIL 항목과 추가 지적사항을 모두 수정해줘.
특히 논리적 결함 탐지에서 제기된 항목은 기존 AC 가 요구하지 않더라도 반드시 반영해야 해.
수정 후 해당 이슈의 검증 AI 보고 형식대로 다시 보고해줘.
```

### 구현 중 문서-코드 충돌 발견 시
1. 구현을 즉시 중단
2. 충돌 내용 보고 (어느 지시가 현재 코드와 맞지 않는지 파일:라인 레벨로)
3. **구현 AI는 문서를 임의로 수정할 수 없다.** 사용자/analyst 가 문서 수정 후 재개.

### 롤백이 필요한 경우
1. 신규 파일만 추가한 이슈 → 해당 파일 삭제
2. 기존 파일 수정 이슈 → `git stash` 또는 `git checkout -- <file>` 로 복원 (사용자 확인 필수)
3. 실패 원인 분석 후 문서 섹션 재조정 후 재시도

### 정보 부족 판단 기준 (구현 AI용 가드)
다음 중 하나라도 해당하면 **즉시 중단하고 옵션 제시**:
- 수정 위치가 여러 파일에 걸쳐있고 어느 파일을 기준으로 할지 문서에 명시되지 않은 경우
- 신규 라이브러리 추가가 필요한데 문서에 없는 경우
- 기존 워크시트/시트명 변경이 해석에 따라 필요해 보이는 경우
- 테스트는 통과하지만 사용자 목적과 다르게 동작할 가능성이 보이는 경우

---

## ✅ 전체 프로젝트 완료 판정

모든 이슈가 각자의 AC 를 통과하고, 다음 회귀 테스트가 모두 성공할 때 프로젝트 완료:

| 회귀 체크 | 방법 |
|-----------|------|
| 기존 KR 급등주 쉐도잉 1건 이상 정상 기록 | `stock_scraper.py` 실행 |
| 기존 US 급등주 쉐도잉 1건 이상 정상 기록 | `us_stock_scraper.py` 실행 |
| 시장트렌드_YYYY 의 KR_일별/US_일별/뉴스요약 정상 기록 | `generate_snapshots.py` 실행 |
| 신규 시장흐름_YYYY 의 테마클러스터_일별 1건 이상 기록 | `run_daily.ts` 실행 |
| 모든 단위 테스트 통과 | `tests/py/test_*.py` 각각 실행 |
| 보안 키 파일 git ls-files 미출현 | 수동 점검 |

---

> **총평:** 이 하네스 문서는 result.md 의 16개 개선 포인트를 **독립적으로 작업 가능한 원자적 이슈** 로 분해했다. 각 이슈는 TDD 의 Red-Green-Refactor 로 구현되며, 구현 AI는 정보 부족 시 즉시 멈추고 옵션을 제시한다. 검증 AI는 AC 각 항목을 코드와 실행 로그로 실증하며, 본 문서에 명시되지 않은 논리적 결함까지 지적한다. Phase 1 5개 이슈만 먼저 완수해도 **본 프로젝트의 쉐도잉 가치는 60% 이상 개선**된다.
