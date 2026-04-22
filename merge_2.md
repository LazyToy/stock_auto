# stock_auto + stock_crawling 병합 최종안

작성일: 2026-04-20  
목표: `stock_auto` 하나만 실행해도 기존 자동매매/분석 기능과 `stock_crawling`의 크롤링, 신호 생성, Google Sheets 결과 조회 기능을 모두 사용할 수 있게 만든다.

## 결론

요청한 3가지 요구사항은 모두 가능합니다.

1. 가상환경과 git은 `stock_auto` 기준 하나로 통합할 수 있습니다.
2. `stock_crawling` 기능은 `stock_auto` Streamlit 대시보드에서 실행할 수 있습니다.
3. Google Sheets에 저장된 결과는 대시보드에서 직접 조회할 수 있습니다.

최종 목표 구조는 `stock_crawling` Python 코드를 `src/crawling/` 패키지로 흡수하고, Node runner는 Python runner로 대체하는 것입니다. 다만 현재 `stock_crawling` 코드는 독립 폴더 실행과 평면 import 전제가 강하므로, 구현은 안전하게 단계적으로 진행합니다.

즉, 이 문서는 다음 두 관점을 합친 최종안입니다.

- `merge.md`의 장점: 최종 구조가 선명하고, `src/crawling/` 패키지화와 Python runner 전환을 분명히 함
- 기존 `merge_2.md`의 장점: 비밀키, import 경로, Node runner, Google Sheets 조회 리스크를 단계적으로 낮춤

## 최종 결정

| 항목 | 결정 | 비고 |
|---|---|---|
| Git | 루트 `.git`만 사용 | `stock_crawling/.git` 제거 |
| Python 환경 | 루트 `.venv` 기준으로 통합 | 기존 루트 `stock_auto/` venv가 필요하면 전환 기간에만 허용 |
| 내부 venv | `stock_crawling/stock_crawling/` 제거 | 중복 환경 제거 |
| Node runner | 최종적으로 Python runner로 대체 | 필요 시 1차 검증용 bridge로만 유지 |
| 코드 위치 | 최종적으로 `src/crawling/`으로 이동 | 장기 운영 기준 |
| 대시보드 | 실행 탭과 결과 조회 탭 분리 | UX와 책임 분리 |
| Google Sheets 조회 | Streamlit + Python `gspread` reader | 별도 Node/Express 서버 불필요 |
| 서비스 계정 | `GOOGLE_SERVICE_ACCOUNT_FILE`로 경로 지정 | 실제 JSON은 git 제외 |
| Gemini 키 | `GEMINI_API_KEY` 유지 | 필요 시 `GOOGLE_API_KEY` fallback만 지원 |
| 파라미터 조절 | 환경변수 override | 기존 설정 기본값 보존 |
| 로컬 캐시 | SQLite 또는 Parquet 미러 권장 | Sheets 장애/quota 대비 |

## 현재 상태에서 확인된 병합 포인트

`stock_auto`는 Python/Streamlit 중심 프로젝트입니다.

- 대시보드 진입점: `dashboard/app.py`
- 루트 설정: `pyproject.toml`, `uv.lock`
- 주요 코드: `src/`, `dashboard/`, `scripts/`, `tests/`

`stock_crawling`은 독립 프로젝트가 통째로 들어온 상태입니다.

- 내부 `.git`
- 내부 venv: `stock_crawling/stock_crawling/`
- `node_modules`, `dist`
- `.env`, `service_account.json`
- Python 크롤링 코드, TypeScript runner, React/Vite UI 일부

핵심 Python 기능:

- `stock_scraper.py`: KR 급등주, 거래대금, 낙폭과대 수집
- `us_stock_scraper.py`: US 급등주, 거래대금, 낙폭과대 수집
- `generate_snapshots.py`: KR/US 시장 흐름, 뉴스, 테마, 조기신호, 수급전환 생성
- `daily_trend_writer.py`: Google Sheets 쓰기 계층
- `backfill_5day_return.py`: 조기신호 5영업일 수익률 백필
- `backtest_early_signal.py`: 조기신호 백테스트
- `gemini_client.py`, `news_aggregator.py`, `telegram_notifier.py`: AI 요약과 알림

## 1. 환경과 Git 통합

### 제거 또는 git 제외 대상

```text
stock_crawling/.git/
stock_crawling/stock_crawling/
stock_crawling/node_modules/
stock_crawling/dist/
stock_crawling/__pycache__/
stock_crawling/.pytest_cache/
stock_crawling/.env
stock_crawling/.env.local
stock_crawling/service_account.json
```

`service_account.json`은 삭제가 아니라 위치 이동 대상입니다. 권장 위치:

```text
config/google_service_account.json
```

루트 `.env`:

```env
GOOGLE_SERVICE_ACCOUNT_FILE=config/google_service_account.json
GEMINI_API_KEY=...
GEMINI_API_KEY_2=...
GEMINI_API_KEY_3=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
SHEET_ID_SHADOWING=
SHEET_ID_TREND=
SHEET_ID_FLOW=
```

### `.gitignore` 보강

```gitignore
# stock_crawling merge artifacts
stock_crawling/.git/
stock_crawling/stock_crawling/
stock_crawling/node_modules/
stock_crawling/dist/
stock_crawling/.env*
stock_crawling/service_account*.json

# secrets
service_account*.json
config/google_service_account.json
secrets/
```

### 의존성 통합

루트 `pyproject.toml`에 추가할 후보:

```toml
"gspread>=6.0.0",
"google-auth>=2.0.0",
"FinanceDataReader>=0.9.0",
"beautifulsoup4>=4.12.0",
"lxml>=4.9.0",
"pykrx>=1.2.0",
"yfinance>=0.2.0",
"tqdm>=4.0.0",
```

이미 루트에 있는 `pandas`, `requests`, `plotly`, `python-dotenv` 등은 중복 추가하지 않습니다.

## 2. Gemini API 키 정책

`GEMINI_API_KEY`를 `GOOGLE_API_KEY`로 일괄 교체하지 않습니다.

이유:

- 현재 `gemini_client.py`는 `GEMINI_API_KEY`, `GEMINI_API_KEY_2`, `GEMINI_API_KEY_3` 형태의 fallback을 이미 지원합니다.
- `GOOGLE_API_KEY`는 의미가 넓어 Gemini 외 Google API와 섞일 수 있습니다.
- 기존 테스트와 문서 호환성을 깨뜨릴 수 있습니다.

권장 구현:

```python
def load_api_key(env_path: str = ".env.local") -> str | None:
    key = _read_env_key(env_path, "GEMINI_API_KEY")
    if key:
        return key
    return _read_env_key(env_path, "GOOGLE_API_KEY")
```

다중 키도 `GEMINI_API_KEY_*`를 우선하고, `GOOGLE_API_KEY`는 호환 alias로만 둡니다.

## 3. Python 패키지화

최종 목표는 `stock_crawling` Python 파일을 `src/crawling/`으로 이동하는 것입니다.

예상 이동:

```text
stock_crawling/stock_scraper.py      -> src/crawling/stock_scraper.py
stock_crawling/us_stock_scraper.py   -> src/crawling/us_stock_scraper.py
stock_crawling/generate_snapshots.py -> src/crawling/generate_snapshots.py
stock_crawling/daily_trend_writer.py -> src/crawling/daily_trend_writer.py
stock_crawling/market_trend.py       -> src/crawling/market_trend.py
stock_crawling/theme_cluster.py      -> src/crawling/theme_cluster.py
stock_crawling/theme_trend.py        -> src/crawling/theme_trend.py
stock_crawling/early_signal.py       -> src/crawling/early_signal.py
stock_crawling/flow_fetcher.py       -> src/crawling/flow_fetcher.py
stock_crawling/flow_signal.py        -> src/crawling/flow_signal.py
stock_crawling/backfill_5day_return.py  -> src/crawling/backfill_5day_return.py
stock_crawling/backtest_early_signal.py -> src/crawling/backtest_early_signal.py
```

평면 import는 패키지 import로 바꿉니다.

```python
# 변경 전
from market_trend import kr_trend_snapshot
from daily_trend_writer import DailyTrendSheet

# 변경 후, 같은 패키지 내부 권장
from .market_trend import kr_trend_snapshot
from .daily_trend_writer import DailyTrendSheet
```

외부에서 호출할 때:

```python
from src.crawling.run_daily import main
```

이 작업이 병합의 핵심 병목입니다. 다만 이 과정을 끝내야 `stock_auto` 하나의 코드베이스로 안정적으로 운영할 수 있습니다.

## 4. Runner 전략

### 최종 목표: Python runner

`stock_crawling/runners/run_daily.ts`는 최종적으로 Python runner로 대체합니다.

```python
# src/crawling/run_daily.py
from __future__ import annotations

import argparse
import subprocess
import sys

STEPS = [
    ("Daily trend snapshot", "src.crawling.generate_snapshots"),
    ("KR scraper", "src.crawling.stock_scraper"),
    ("US scraper", "src.crawling.us_stock_scraper"),
    ("Backfill 5d return", "src.crawling.backfill_5day_return"),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    env = None
    for idx, (name, module) in enumerate(STEPS, start=1):
        print(f"[{idx}/{len(STEPS)}] {name} - {module}")
        cmd = [sys.executable, "-m", module]
        rc = subprocess.call(cmd, env=env)
        if rc != 0:
            print(f"[FAIL] {name}: exit code {rc}")
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`pyproject.toml`:

```toml
[project.scripts]
stock-crawling-daily = "src.crawling.run_daily:main"
```

### 1차 bridge로 Node runner를 유지하는 경우

단기 검증에서 기존 `run_daily.ts`를 잠시 사용할 수 있습니다. 단, 이건 최종 구조가 아니라 전환용 bridge입니다.

현재 `run_daily.ts`의 `repoRoot`는 `stock_crawling/runners` 기준으로 `stock_crawling` 폴더입니다. 루트 venv를 보려면 상위 경로를 봐야 합니다.

```typescript
const candidates: string[] =
    opts.platform === 'win32'
        ? [
              join(opts.repoRoot, '../.venv/Scripts/python.exe'),
              join(opts.repoRoot, '../stock_auto/Scripts/python.exe'),
              join(opts.repoRoot, 'stock_crawling/Scripts/python.exe'),
              join(opts.repoRoot, '.venv/Scripts/python.exe'),
          ]
        : [
              join(opts.repoRoot, '../.venv/bin/python'),
              join(opts.repoRoot, '../stock_auto/bin/python'),
              join(opts.repoRoot, 'stock_crawling/bin/python'),
              join(opts.repoRoot, '.venv/bin/python'),
          ];
```

bridge 종료 조건:

- `src.crawling.run_daily --dry-run` 성공
- KR/US 개별 스크래퍼가 루트 venv에서 실행됨
- 대시보드 실행 탭이 Python runner를 호출함
- Task Scheduler 스크립트가 Python runner 기준으로 갱신됨

이 조건이 충족되면 `runners/`, `package.json`, `node_modules`, `dist`, React/Vite UI는 제거하거나 참고 자료로만 보관합니다.

## 5. 대시보드 구조

실행 탭과 결과 조회 탭을 분리합니다.

```text
dashboard/
  app.py
  components/
    crawling_run_tab.py
    crawling_results_tab.py

src/
  crawling/
    run_daily.py
    sheets_reader.py
    schemas.py
```

`dashboard/app.py`에는 새 탭 2개를 추가합니다.

```python
from dashboard.components.crawling_run_tab import render_crawling_run_tab
from dashboard.components.crawling_results_tab import render_crawling_results_tab
```

## 6. 실행 탭 설계

### 실행 모드

- 전체 파이프라인 실행
- KR 스크래퍼만 실행
- US 스크래퍼만 실행
- 시장 스냅샷만 실행
- 조기신호 백필만 실행
- 조기신호 백테스트 실행
- DRY RUN 실행

### 표시 정보

- 실행 상태: 대기, 실행 중, 완료, 실패
- 시작/종료 시각
- 실행 단계
- 최근 로그
- Google Sheets 저장 대상
- 종료 코드
- 최근 실행 이력

### 파라미터 전달 방식

기존 `CONFIG` 하드코딩 값에 환경변수 override를 추가합니다. 기본값은 반드시 유지합니다.

```python
import os

CONFIG = {
    "SURGE_THRESHOLD": float(os.environ.get("CRAWL_KR_SURGE_THRESHOLD", "15.0")),
    "DROP_THRESHOLD": float(os.environ.get("CRAWL_KR_DROP_THRESHOLD", "-15.0")),
    "VOLUME_THRESHOLD": int(os.environ.get("CRAWL_KR_VOLUME_THRESHOLD", "500")),
}
```

Streamlit에서 실행할 때:

```python
env["CRAWL_KR_SURGE_THRESHOLD"] = str(kr_surge_threshold)
env["CRAWL_KR_VOLUME_THRESHOLD"] = str(kr_volume_threshold)
```

### KR 파라미터

| 파라미터 | 기본값 | UI |
|---|---:|---|
| `SURGE_THRESHOLD` | 15.0 | slider 5.0~30.0 |
| `DROP_THRESHOLD` | -15.0 | slider -30.0~-5.0 |
| `DROP_SECONDARY_THRESHOLD` | -6.0 | slider -15.0~0.0 |
| `VOLUME_THRESHOLD` | 500 | number input |
| `FLUCTUATION_THRESHOLD` | 6.0 | slider 1.0~15.0 |

### US 파라미터

| 파라미터 | 기본값 | UI |
|---|---:|---|
| `SURGE_THRESHOLD_LARGE` | 8.0 | slider 3.0~20.0 |
| `SURGE_THRESHOLD_SMALL` | 15.0 | slider 5.0~30.0 |
| `DROP_THRESHOLD_LARGE` | -8.0 | slider -25.0~-3.0 |
| `DROP_THRESHOLD_SMALL` | -15.0 | slider -30.0~-5.0 |
| `MARKET_CAP_THRESHOLD` | 2,000,000,000 | number input |
| `VOLUME_THRESHOLD` | 100,000,000 | number input |
| `VOLATILITY_THRESHOLD` | 5.0 | slider 1.0~15.0 |

### 조기신호 파라미터

| 파라미터 | 기본값 | UI |
|---|---:|---|
| `_RVOL_MIN` | 3.0 | slider 1.0~10.0 |
| `_CHANGE_MIN` | 3.0 | slider 1.0~10.0 |
| `_CHANGE_MAX` | 10.0 | slider 5.0~20.0 |
| `_STREAK_MIN` | 3 | number input |
| `_RATIO_52W_MIN` | 0.95 | slider 0.8~1.0 |

## 7. 결과 조회 탭 설계

Google Sheets 결과를 Streamlit에서 바로 조회합니다.

### 조회 대상

| 카테고리 | 워크북 | 탭 |
|---|---|---|
| KR 급등주 | `주식_쉐도잉_YYYYMM` | `급등주_쉐도잉` |
| KR 거래대금 | `주식_쉐도잉_YYYYMM` | `거래대금_쉐도잉` |
| KR 낙폭과대 | `주식_쉐도잉_YYYYMM` | `낙폭과대_쉐도잉` |
| US 급등주 | `주식_쉐도잉_YYYYMM` | `미국_급등주_쉐도잉` |
| US 거래대금 | `주식_쉐도잉_YYYYMM` | `미국_거래대금_쉐도잉` |
| US 낙폭과대 | `주식_쉐도잉_YYYYMM` | `미국_낙폭과대_쉐도잉` |
| 시장 트렌드 | `시장트렌드_YYYY` | `KR_일별`, `US_일별`, `뉴스요약` |
| 시장 흐름 | `시장흐름_YYYY` | `테마클러스터_일별`, `테마트렌드_주간`, `조기신호_관찰`, `수급전환_포착` |

### 구현 방식

```python
@st.cache_data(ttl=300)
def load_sheet(workbook_title: str, worksheet_title: str) -> pd.DataFrame:
    ...
```

권장 기능:

- 년/월 선택
- 시장 선택: KR, US, 전체
- 카테고리 선택
- 날짜 필터
- 섹터/종목 검색
- 테이블 다운로드
- 원본 Google Sheet 링크 표시
- KPI 요약
- Plotly 차트
- 테마 클러스터 heatmap
- 주간 테마 timeline

추가 권장:

- Google Sheets 조회 실패 시 로컬 캐시 fallback
- `data/crawling/cache/` 또는 SQLite/Parquet 미러 저장
- API quota 보호를 위한 5분 캐시

## 8. 구현 순서

### Phase 0. 기준선 확인

아직 파일을 옮기기 전에 현재 동작을 확인합니다.

1. 루트 venv에서 필요한 패키지 설치 가능 여부 확인
2. `DRY_RUN=1`로 `stock_scraper.py` 실행
3. `DRY_RUN=1`로 `us_stock_scraper.py` 실행
4. Google 인증 파일이 없을 때 실패 메시지 확인
5. 현재 `stock_crawling` 테스트 중 순수 로직 테스트 범위 확인

### Phase 1. 안전 정리

1. 루트 `.gitignore` 보강
2. `stock_crawling/.git` 제거 또는 백업 후 제외
3. 내부 venv, `node_modules`, `dist`, 캐시 제거
4. `service_account.json`을 `config/google_service_account.json`으로 이동
5. 루트 `.env`에 `GOOGLE_SERVICE_ACCOUNT_FILE` 추가
6. 루트 `pyproject.toml`에 크롤링 의존성 추가

### Phase 2. 패키지화

1. `src/crawling/` 생성
2. Python 모듈 이동
3. 평면 import를 상대 import 또는 패키지 import로 수정
4. `src/crawling/run_daily.py` 생성
5. `pyproject.toml` entrypoint 추가
6. `python -m src.crawling.run_daily --dry-run` 검증

### Phase 3. 파라미터 override

1. `stock_scraper.py` CONFIG 환경변수 override
2. `us_stock_scraper.py` CONFIG 환경변수 override
3. `early_signal.py` 임계값 환경변수 override
4. 기본값 보존 테스트
5. 잘못된 환경변수 값 입력 시 실패 메시지 확인

### Phase 4. 대시보드 실행 탭

1. `dashboard/components/crawling_run_tab.py` 생성
2. 실행 모드 선택 UI 구현
3. 17개 파라미터 UI 구현
4. Python runner subprocess 실행
5. `logs/crawling/` 로그 저장
6. 실행 상태와 최근 로그 표시
7. 긴 실행을 위해 background process + polling 적용

### Phase 5. 결과 조회 탭

1. `src/crawling/sheets_reader.py` 생성
2. `src/crawling/schemas.py`에 workbook/worksheet schema 상수화
3. `dashboard/components/crawling_results_tab.py` 생성
4. `st.cache_data(ttl=300)` 적용
5. 필터, KPI, 차트, 테이블 구현
6. 로컬 SQLite/Parquet 미러 추가

### Phase 6. Node/React 잔여물 정리

아래 조건을 만족하면 제거합니다.

- Python runner가 daily pipeline을 대체함
- 대시보드 실행 탭이 Python runner를 호출함
- Google Sheets 조회가 Streamlit에서 동작함
- 스케줄러가 Python runner 기준으로 갱신됨

정리 대상:

```text
stock_crawling/runners/
stock_crawling/server/
stock_crawling/src/
stock_crawling/package.json
stock_crawling/package-lock.json
stock_crawling/vite.config.ts
stock_crawling/tsconfig.json
stock_crawling/index.html
```

단, 테스트나 참고 자료로 필요하면 `docs/legacy_stock_crawling/` 등에 별도 보관합니다.

## 9. 검증 명령

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:DRY_RUN='1'
.\.venv\Scripts\python.exe stock_crawling\stock_scraper.py
.\.venv\Scripts\python.exe stock_crawling\us_stock_scraper.py
```

패키지화 후:

```powershell
.\.venv\Scripts\python.exe -m src.crawling.run_daily --dry-run
.\.venv\Scripts\python.exe -m pytest tests
.\.venv\Scripts\python.exe -m pytest tests/crawling
streamlit run dashboard/app.py
```

## 10. 리스크와 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| 비밀키 git 추적 | 매우 큼 | `service_account*.json`, `.env*`, `secrets/` gitignore |
| import 경로 깨짐 | 큼 | 단계별 패키지화, DRY RUN, 순수 로직 테스트 이전 |
| Node runner 제거로 스케줄 깨짐 | 중간 | Python runner 검증 후 스케줄러 갱신 |
| Google Sheets quota | 중간 | `st.cache_data(ttl=300)`, 로컬 캐시 |
| Streamlit UI 블로킹 | 중간 | background subprocess + polling |
| Gemini 키 변경 충돌 | 중간 | `GEMINI_API_KEY` 유지, `GOOGLE_API_KEY` fallback |
| 인코딩 문제 | 중간 | UTF-8 저장, `PYTHONIOENCODING=utf-8` |
| 파라미터 override 오류 | 낮음~중간 | UI 범위 제한, 기본값 보존, DRY RUN |

## 11. 최종 프로젝트 구조

```text
stock_auto/
  .git/
  .venv/
  pyproject.toml
  uv.lock
  .env
  config/
    google_service_account.json      # git 제외
  dashboard/
    app.py
    components/
      crawling_run_tab.py
      crawling_results_tab.py
      overview_tab.py
      market_tab.py
      growth_tab.py
      macro_tab.py
  src/
    crawling/
      __init__.py
      run_daily.py
      sheets_reader.py
      schemas.py
      stock_scraper.py
      us_stock_scraper.py
      generate_snapshots.py
      daily_trend_writer.py
      market_trend.py
      theme_cluster.py
      theme_trend.py
      early_signal.py
      flow_fetcher.py
      flow_signal.py
      backfill_5day_return.py
      backtest_early_signal.py
      gemini_client.py
      news_aggregator.py
      news_fetcher.py
      telegram_notifier.py
      sector_map_kr.py
      streak_indicators.py
      ohlcv_store.py
    analysis/
    backtest/
    broker/
    copilot/
    data/
    live/
    ml/
    optimization/
    portfolio/
    strategies/
    trader/
    utils/
  tests/
    crawling/
  logs/
    crawling/
  data/
    crawling/
```

## 최종 평가

가장 좋은 병합 전략은 `merge.md`의 최종 목적지를 유지하면서, 구현 순서는 더 안전하게 쪼개는 것입니다.

따라서 최종 기준은 다음입니다.

1. 최종 구조는 `src/crawling/` 패키지와 Python runner입니다.
2. 실행탭과 결과 조회탭은 분리합니다.
3. 17개 파라미터는 환경변수 override로 조절합니다.
4. Google Sheets는 Streamlit에서 `gspread`로 읽습니다.
5. `GEMINI_API_KEY`는 유지하고, `GOOGLE_API_KEY`는 fallback alias로만 둡니다.
6. `service_account.json`은 `config/`로 이동하고 반드시 git 제외합니다.
7. Node/React 잔여물은 Python runner와 Streamlit 조회가 검증된 뒤 제거합니다.
