# stock_auto + stock_crawling 병합 계획서

> 작성일: 2026-04-20 | 상태: **결정 완료 → 구현 대기**

## 결론

3가지 요구사항 모두 기술적으로 가능합니다.

권장 방향: `stock_crawling`의 Python 코드를 `src/crawling/` 패키지로 흡수하여, `stock_auto` 하나만 실행하면 자동매매·분석·크롤링·Google Sheets 조회를 모두 사용할 수 있게 합니다.

## ✅ 결정 사항

| # | 항목 | 결정 |
|---|------|------|
| 1 | service_account.json | `stock_crawling/` 내부 유지 → 병합 후 `config/` 이동, git 제외 |
| 2 | Node.js 러너 | Python runner로 대체 (stock_auto 단일 실행 목표에 부합) |
| 3 | 환경변수 | `GOOGLE_API_KEY`로 일괄 교체 |
| 4 | 대시보드 탭 | 실행탭(파라미터 조절) + 뷰어탭 **분리** |

---

## 1️⃣ 환경·Git 통합

### 정리 대상

| 항목 | 처리 |
|------|------|
| `stock_crawling/.git` | 삭제 → 루트 git만 사용 |
| `stock_crawling/stock_crawling/` (venv) | 삭제 → 루트 `.venv` 사용 |
| `stock_crawling/node_modules`, `dist` | 삭제 (Python runner로 대체) |
| `stock_crawling/.env`, `.env.local` | 삭제 → 루트 `.env`로 통합 |
| `stock_crawling/service_account.json` | `config/google_service_account.json`으로 이동 |
| `__pycache__`, `.pytest_cache` | 삭제 |

### 의존성 통합 (pyproject.toml 추가)

```toml
"gspread>=6.0.0",
"google-auth>=2.0.0",
"FinanceDataReader>=0.9.0",
"beautifulsoup4>=4.12.0",
"lxml>=4.9.0",
```

### 환경변수 통합 (.env)

```env
# 기존 stock_auto 키 유지 (KIS, DART, FRED 등)
GOOGLE_API_KEY=키1,키2,키3           # GEMINI_API_KEY → 통일
GOOGLE_SERVICE_ACCOUNT_FILE=config/google_service_account.json
TELEGRAM_BOT_TOKEN=봇토큰
TELEGRAM_CHAT_ID=챗ID
```

### 환경변수 교체 대상 (gemini_client.py)

```python
# 변경 전
if key.strip() != "GEMINI_API_KEY":
_GEMINI_KEY_RE = re.compile(r'^GEMINI_API_KEY(_\d+)?$')

# 변경 후
if key.strip() != "GOOGLE_API_KEY":
_GEMINI_KEY_RE = re.compile(r'^GOOGLE_API_KEY(_\d+)?$')
```

### .gitignore 추가 항목

```gitignore
config/google_service_account.json
stock_crawling/node_modules/
stock_crawling/dist/
stock_crawling/stock_crawling/
stock_crawling/.env*
```

---

## 2️⃣ Python 패키지화 (핵심 작업)

### 이동 구조

```
stock_crawling/stock_scraper.py     → src/crawling/stock_scraper.py
stock_crawling/us_stock_scraper.py  → src/crawling/us_stock_scraper.py
stock_crawling/generate_snapshots.py→ src/crawling/generate_snapshots.py
stock_crawling/daily_trend_writer.py→ src/crawling/daily_trend_writer.py
stock_crawling/market_trend.py      → src/crawling/market_trend.py
stock_crawling/theme_cluster.py     → src/crawling/theme_cluster.py
stock_crawling/early_signal.py      → src/crawling/early_signal.py
stock_crawling/flow_fetcher.py      → src/crawling/flow_fetcher.py
stock_crawling/flow_signal.py       → src/crawling/flow_signal.py
... (기타 공통 모듈 전체)
```

### import 수정

```python
# 변경 전 (평면 import)
from market_trend import kr_trend_snapshot
from daily_trend_writer import DailyTrendSheet

# 변경 후 (패키지 import)
from src.crawling.market_trend import kr_trend_snapshot
from src.crawling.daily_trend_writer import DailyTrendSheet

# 또는 같은 패키지 내부
from .market_trend import kr_trend_snapshot
```

> ⚠️ **이 작업이 병합의 핵심 병목입니다.** 패키지화 없이 subprocess+cwd로 우회 가능하나, 장기적으로 import 경로가 흔들리는 문제가 생깁니다.

### Python runner (run_daily.ts 대체)

```python
# src/crawling/run_daily.py
"""stock_crawling 일일 파이프라인 오케스트레이터 (run_daily.ts 대체)"""
import sys, subprocess

STEPS = [
    ("Daily trend snapshot", "generate_snapshots.py"),
    ("KR scraper",           "stock_scraper.py"),
    ("US scraper",           "us_stock_scraper.py"),
    ("Backfill 5d return",   "backfill_5day_return.py"),
]

def main():
    for i, (name, script) in enumerate(STEPS, 1):
        print(f"[{i}/{len(STEPS)}] {name} — {script}")
        rc = subprocess.call([sys.executable, "-m", f"src.crawling.{script[:-3]}"])
        if rc != 0:
            print(f"[FAIL] {name}: exit code {rc}")
            return 1
    return 0
```

pyproject.toml 엔트리포인트:

```toml
[project.scripts]
stock-crawling-daily = "src.crawling.run_daily:main"
```

---

## 3️⃣ 대시보드 실행 탭 (파라미터 조절)

### 조절 가능한 파라미터 전체 목록 (17개)

#### 🇰🇷 KR 스크래퍼 (stock_scraper.py)

| 파라미터 | 기본값 | 설명 | UI 위젯 |
|---------|-------|------|---------|
| `SURGE_THRESHOLD` | 15.0% | 급등 기준 | `st.slider(5.0, 30.0, 15.0)` |
| `DROP_THRESHOLD` | -15.0% | 낙폭과대 절대 | `st.slider(-30.0, -5.0, -15.0)` |
| `DROP_SECONDARY_THRESHOLD` | -6.0% | 낙폭과대 복합 | `st.slider(-15.0, 0.0, -6.0)` |
| `VOLUME_THRESHOLD` | 500억 | 거래대금 기준 | `st.number_input(100, 5000, 500)` |
| `FLUCTUATION_THRESHOLD` | 6.0% | 변동폭 기준 | `st.slider(1.0, 15.0, 6.0)` |

#### 🇺🇸 US 스크래퍼 (us_stock_scraper.py)

| 파라미터 | 기본값 | 설명 | UI 위젯 |
|---------|-------|------|---------|
| `SURGE_THRESHOLD_LARGE` | 8.0% | 대형주 급등 | `st.slider(3.0, 20.0, 8.0)` |
| `SURGE_THRESHOLD_SMALL` | 15.0% | 소형주 급등 | `st.slider(5.0, 30.0, 15.0)` |
| `DROP_THRESHOLD_LARGE` | -8.0% | 대형주 낙폭 | `st.slider(-25.0, -3.0, -8.0)` |
| `DROP_THRESHOLD_SMALL` | -15.0% | 소형주 낙폭 | `st.slider(-30.0, -5.0, -15.0)` |
| `MARKET_CAP_THRESHOLD` | $20억 | 대소형 구분 시총 | `st.number_input` |
| `VOLUME_THRESHOLD` | $1억 | 거래대금 기준 | `st.number_input` |
| `VOLATILITY_THRESHOLD` | 5.0% | 변동폭 기준 | `st.slider(1.0, 15.0, 5.0)` |

#### 🔍 조기신호 (early_signal.py)

| 파라미터 | 기본값 | 설명 | UI 위젯 |
|---------|-------|------|---------|
| `_RVOL_MIN` | 3.0 | 상대거래량 하한 | `st.slider(1.0, 10.0, 3.0)` |
| `_CHANGE_MIN` | 3.0% | 등락률 하한 | `st.slider(1.0, 10.0, 3.0)` |
| `_CHANGE_MAX` | 10.0% | 등락률 상한 | `st.slider(5.0, 20.0, 10.0)` |
| `_STREAK_MIN` | 3일 | 연속봉 최소 | `st.number_input(1, 10, 3)` |
| `_RATIO_52W_MIN` | 0.95 | 52주고가 비율 | `st.slider(0.8, 1.0, 0.95)` |

### 파라미터 전달: 환경변수 오버라이드

```python
# stock_scraper.py 수정
import os
CONFIG = {
    "SURGE_THRESHOLD": float(os.environ.get("CRAWL_SURGE_THRESHOLD", "15.0")),
    "VOLUME_THRESHOLD": int(os.environ.get("CRAWL_VOLUME_THRESHOLD", "500")),
    # ...
}
```

대시보드에서 subprocess env에 주입:

```python
env["CRAWL_SURGE_THRESHOLD"] = str(surge_threshold)
env["CRAWL_VOLUME_THRESHOLD"] = str(volume_threshold)
```

### 실행 탭 UI 구조

```
📡 주식 쉐도잉 실행
├── 좌측 (col1)
│   ├── 실행 모드 (전체/개별)
│   ├── DRY RUN 토글
│   ├── ── KR 파라미터 (5개) ──
│   ├── ── US 파라미터 (7개) ──
│   ├── ── 조기신호 파라미터 (5개) ──
│   └── ▶️ 실행 버튼
└── 우측 (col2)
    ├── 실행 상태 (진행/완료/실패)
    ├── 실시간 로그
    ├── Google Sheets 저장 대상 표시
    └── 최근 실행 이력
```

---

## 4️⃣ 대시보드 뷰어 탭

### 조회 대상 시트

| 카테고리 | 워크북 | 탭명 |
|---------|------|------|
| KR 급등주 | `주식_쉐도잉_YYYYMM` | 급등주_쉐도잉 |
| KR 거래대금 | 〃 | 거래대금_쉐도잉 |
| KR 낙폭과대 | 〃 | 낙폭과대_쉐도잉 |
| US 급등주 | 〃 | 미국_급등주_쉐도잉 |
| US 거래대금 | 〃 | 미국_거래대금_쉐도잉 |
| US 낙폭과대 | 〃 | 미국_낙폭과대_쉐도잉 |
| 시장 트렌드 KR/US | `시장트렌드_YYYY` | KR_일별 / US_일별 / 뉴스요약 |
| 테마 클러스터 | `시장흐름_YYYY` | 테마클러스터_일별 / 테마트렌드_주간 |
| 조기 신호 | 〃 | 조기신호_관찰 |
| 수급 전환 | 〃 | 수급전환_포착 |

### UI 구성

- 날짜/시장/섹터/종목 필터
- KPI 요약 (급등 건수, 테마 강도 등)
- 테이블 + plotly 차트
- 테마 클러스터 히트맵 / 주간 타임라인
- 원본 Google Sheet 링크 표시
- `st.cache_data(ttl=300)` 캐시 + **로컬 SQLite/Parquet 미러** (API 장애 대비)

---

## 🗂️ 최종 프로젝트 구조

```
stock_auto/
  .git/
  .venv/
  pyproject.toml / uv.lock
  config/
    google_service_account.json     # 로컬 전용, git 제외
  src/
    crawling/                       # ← stock_crawling 코드 흡수
      __init__.py
      run_daily.py                  # run_daily.ts 대체
      sheets_reader.py              # 읽기 전용 Google Sheets 조회
      stock_scraper.py
      us_stock_scraper.py
      generate_snapshots.py
      daily_trend_writer.py
      market_trend.py
      theme_cluster.py / theme_trend.py
      early_signal.py / flow_signal.py / flow_fetcher.py
      backfill_5day_return.py / backtest_early_signal.py
      gemini_client.py / news_*.py / telegram_notifier.py
      sector_map_kr.py / streak_indicators.py / ohlcv_store.py
    analysis/ backtest/ strategies/ ...  # 기존 stock_auto
  dashboard/
    app.py
    components/
      crawling_run_tab.py           # 🆕 실행 + 파라미터 조절
      crawling_results_tab.py       # 🆕 Google Sheets 뷰어
      (기존 탭들)
  tests/
    crawling/                       # stock_crawling 테스트 이전
  scripts/
    run_crawling_daily.py           # CLI 진입점
  logs/crawling/
  data/crawling/                    # 로컬 캐시 (parquet/sqlite)
```

---

## 📝 구현 순서

### Phase 1: 정리 병합 (난이도: 낮음)
1. `stock_crawling/.git`, venv, `node_modules`, `dist`, 캐시 제거
2. `.gitignore` 보강
3. `pyproject.toml`에 크롤링 의존성 추가 → `uv pip install -e .`
4. `service_account.json` → `config/` 이동
5. `.env` 통합 (`GEMINI_API_KEY` → `GOOGLE_API_KEY`)

### Phase 2: 패키지화 (난이도: 중간 — 핵심 병목)
1. 크롤링 코드를 `src/crawling/` 패키지로 이동
2. 평면 import → 패키지 import 전환 (모든 모듈)
3. `run_daily.ts` → Python `run_daily.py` 대체
4. CONFIG에 환경변수 오버라이드 추가 (3개 파일)
5. `DRY_RUN=1`로 루트 환경에서 실행 가능 확인

### Phase 3: 대시보드 탭 추가 (난이도: 중간)
1. `crawling_run_tab.py` — 실행 + 파라미터 UI (17개)
2. `crawling_results_tab.py` — Google Sheets 뷰어
3. `sheets_reader.py` — gspread 읽기 계층
4. `app.py`에 탭 2개 등록
5. 로컬 캐시(SQLite/Parquet) 미러 구현

### Phase 4: 테스트 및 검증 (난이도: 낮음~중간)
1. 기존 `stock_auto` 테스트 깨지지 않는지 확인
2. `stock_crawling` 순수 로직 테스트 이전
3. Google Sheets fake client 테스트 유지
4. 인증 파일 없을 때 UI 친절한 실패 확인
5. `DRY_RUN=1` 전체 경로 확인

```powershell
# 검증 명령
.\.venv\Scripts\python.exe -m pytest tests
.\.venv\Scripts\python.exe -m pytest tests/crawling
.\.venv\Scripts\python.exe -m src.crawling.run_daily --dry-run
streamlit run dashboard/app.py
```

---

## ⚠️ 리스크 및 대응

| 리스크 | 대응 |
|-------|------|
| **import 경로** (핵심) | 패키지화 필수. subprocess+cwd 우회는 장기적으로 불안정 |
| **인코딩** | 모든 파일 UTF-8 통일, `PYTHONIOENCODING=utf-8` 기본 설정 |
| **Google Sheets quota** | `st.cache_data(ttl=300)` + 로컬 SQLite/Parquet 미러 |
| **파이프라인 5~15분 블로킹** | subprocess 비동기 + 상태 JSON 폴링 |
| **인증 실패** | `service_account.json` 없을 때 친절한 에러 메시지 + 기능 비활성화 |
| **패키지 충돌** | 통합 설치 후 즉시 테스트 |
| **파라미터 오버라이드 안전성** | 슬라이더 min/max 범위 제한 + 기본값 보존 |

---

## 예상 작업량

| Phase | 작업 | 난이도 |
|-------|------|:------:|
| 1 | 환경/git 정리 | 낮음 |
| 2 | 의존성 통합 | 낮음~중간 |
| 2 | **Python import 패키지화** | **중간 (핵심)** |
| 3 | 대시보드 실행 탭 | 중간 |
| 3 | Google Sheets 뷰어 | 중간 |
| 3 | 로컬 캐시 미러 | 중간~높음 |

**가장 먼저 해야 할 것**: `stock_crawling` 코드를 `src/crawling/`으로 옮겨 `DRY_RUN=1`로 실행 가능하게 만드는 것. 그 다음 대시보드 탭을 붙이면 됩니다.

---

> 💡 **Phase 1부터 바로 진행하겠습니다. 승인해주세요!**
