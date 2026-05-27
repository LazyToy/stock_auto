# 크롤링 구조 정리

작성일: 2026-05-26  
기준 코드: `src/crawling`, `dashboard/components/crawling_*_tab.py`

이 문서는 현재 프로젝트에서 실행되는 크롤링 항목별로 어떤 데이터를 어디서 가져오고, 어떤 기준으로 걸러내며, 어디에 어떤 형태로 저장하는지 정리한 문서입니다. 서비스 계정 JSON, API 키, 토큰 값은 문서에 기록하지 않습니다.

## 1. 전체 실행 구조

### 실행 진입점

크롤링의 공통 진입점은 `src.crawling.run_daily`입니다.

```powershell
python -m src.crawling.run_daily --mode all
```

`dashboard/components/crawling_run_tab.py`의 "크롤링 실행" 탭도 같은 모듈을 실행합니다.

| 모드 | 실행 내용 |
|---|---|
| `dry-run` | `run_daily` 부트스트랩 확인만 수행합니다. 실제 KR/US 스크래퍼의 네트워크/시트 쓰기 검증은 하지 않습니다. |
| `all` | `snapshots` -> `kr` -> `us` -> `backfill` 순서로 실행합니다. |
| `snapshots` | 시장 스냅샷, 뉴스요약, 테마클러스터, 조기신호, OHLCV 캐시, 수급전환을 실행합니다. |
| `kr` | 한국 주식 월간 쉐도잉 시트 3종을 수집합니다. |
| `us` | 미국 주식 월간 쉐도잉 시트 3종을 수집합니다. |
| `backfill` | 조기신호의 5일후수익률을 채웁니다. |
| `backtest` | 조기신호 백테스트 리포트를 생성하는 모드입니다. 단, 현재 `run_daily`는 `--start`, `--end` 인자를 넘기지 않기 때문에 이 모드는 CLI 인자 없이 실행하면 실패합니다. 직접 실행할 때 기간 인자가 필요합니다. |

### 로그 저장

대시보드에서 실행하면 로그는 `logs/crawling` 아래에 저장됩니다.

| 실행 방식 | 로그 파일 |
|---|---|
| 동기 실행 | `{YYYYMMDD-HHMMSS}-crawling-run.log` |
| 백그라운드 실행 stdout | `{YYYYMMDD-HHMMSS}-stdout.log` |
| 백그라운드 실행 stderr | `{YYYYMMDD-HHMMSS}-stderr.log` |

대시보드는 최근 로그 꼬리 부분을 UI에 표시합니다.

### 인증과 환경 변수

Google Sheets 쓰기/읽기는 서비스 계정으로 인증합니다.

서비스 계정 파일 경로 탐색 순서:

1. 명시적으로 전달한 경로
2. `.env`의 `GOOGLE_SERVICE_ACCOUNT_FILE`
3. `config/google_service_account.json`
4. `crawling/config/google_service_account.json`
5. `stock_crawling/service_account.json`

결과 조회 탭은 다음 스프레드시트 ID 환경 변수가 있으면 제목 검색 대신 ID로 엽니다.

| 환경 변수 | 대상 |
|---|---|
| `SHEET_ID_SHADOWING` | `주식_쉐도잉_{YYYYMM}` |
| `SHEET_ID_TREND` | `시장트렌드_{YYYY}` |
| `SHEET_ID_FLOW` | `시장흐름_{YYYY}` |

대시보드 실행 탭에서 조정 가능한 주요 기준값:

| 환경 변수 | 기본값 | 의미 |
|---|---:|---|
| `CRAWL_KR_SURGE_THRESHOLD` | `15.0` | KR 급등 기준 등락률 |
| `CRAWL_KR_DROP_THRESHOLD` | `-15.0` | KR 낙폭과대 절대 기준 |
| `CRAWL_KR_DROP_SECONDARY_THRESHOLD` | `-6.0` | KR 낙폭과대 거래대금 동반 기준 |
| `CRAWL_KR_VOLUME_THRESHOLD` | `500` | KR 거래대금 기준, 억 원 |
| `CRAWL_KR_FLUCTUATION_THRESHOLD` | `6.0` | KR 당일 변동폭 기준 |
| `CRAWL_US_SURGE_THRESHOLD_LARGE` | `8.0` | US 대형주 급등 기준 |
| `CRAWL_US_SURGE_THRESHOLD_SMALL` | `15.0` | US 소형주 급등 기준 |
| `CRAWL_US_DROP_THRESHOLD_LARGE` | `-8.0` | US 대형주 낙폭과대 기준 |
| `CRAWL_US_DROP_THRESHOLD_SMALL` | `-15.0` | US 소형주 낙폭과대 기준 |
| `CRAWL_US_MARKET_CAP_THRESHOLD` | `2000000000` | US 대형주/소형주 구분 시총, 달러 |
| `CRAWL_US_VOLUME_THRESHOLD` | `100000000` | US 거래대금 기준, 달러 |
| `CRAWL_US_VOLATILITY_THRESHOLD` | `5.0` | US 당일 변동폭 기준 |
| `CRAWL_EARLY_SIGNAL_RVOL_MIN` | `3.0` | 조기신호 RVOL 최소값 |
| `CRAWL_EARLY_SIGNAL_CHANGE_MIN` | `3.0` | 조기신호 등락률 하한 |
| `CRAWL_EARLY_SIGNAL_CHANGE_MAX` | `10.0` | 조기신호 등락률 상한 |
| `CRAWL_EARLY_SIGNAL_STREAK_MIN` | `3` | 조기신호 연속 상승일 기준 |
| `CRAWL_EARLY_SIGNAL_RATIO_52W_MIN` | `0.95` | 조기신호 52주 고가 근접 비율 |

## 2. 저장소 전체 맵

### Google Sheets

| 워크북 | 생성 기준 | 탭 | 쓰는 모듈 |
|---|---|---|---|
| `주식_쉐도잉_{YYYYMM}` | 월 단위 | `급등주_쉐도잉`, `거래대금_쉐도잉`, `낙폭과대_쉐도잉`, `미국_급등주_쉐도잉`, `미국_거래대금_쉐도잉`, `미국_낙폭과대_쉐도잉` | `stock_scraper.py`, `us_stock_scraper.py` |
| `시장트렌드_{YYYY}` | 연 단위 | `KR_일별`, `US_일별`, `뉴스요약` | `generate_snapshots.py`, `daily_trend_writer.py` |
| `시장흐름_{YYYY}` | 연 단위 | `테마클러스터_일별`, `테마트렌드_주간`, `조기신호_관찰`, `수급전환_포착` | `generate_snapshots.py`, `daily_trend_writer.py`, `backfill_5day_return.py` |

시트가 없으면 새로 만들고, 첫 행에 헤더를 추가합니다. 대부분의 탭은 중복 방지를 위해 `(날짜, 종목코드)` 또는 `(날짜, 방향, 섹터)` 같은 키를 먼저 읽은 뒤 이미 있는 행은 건너뜁니다.

### 로컬 파일/DB

| 경로 | 형태 | 내용 |
|---|---|---|
| `data/ohlcv.db` | SQLite | `daily_ohlcv` 테이블. `ticker`, `date`, `open`, `high`, `low`, `close`, `volume`, `amount`를 `(ticker, date)` 기준 upsert합니다. 조기신호 RVOL 계산에 사용됩니다. |
| `data/crawling/cache/sheets_cache.sqlite3` | SQLite | 결과 조회 탭의 Google Sheets 읽기 캐시입니다. live 조회 성공 시 DataFrame을 JSON payload로 저장하고, 실패 시 캐시를 표시합니다. |
| `sector_map_kr.json` | JSON | 네이버 업종/WICS 기반 `{종목코드: 섹터명}` 캐시입니다. `fetched_at`, `data` 구조입니다. |
| `reports/backtest_YYYYMMDD.md` | Markdown | 조기신호 백테스트 결과 리포트입니다. |

## 3. 시장 스냅샷 수집 (`snapshots`)

실행 모듈: `src.crawling.generate_snapshots`

### 3.1 KR 시장 일별 스냅샷

| 항목 | 내용 |
|---|---|
| 데이터 소스 | `FinanceDataReader.StockListing("KRX")` |
| 대상 | `Market`이 `KOSPI`, `KOSDAQ`인 종목 |
| 주요 원천 컬럼 | `Code`, `Name`, `Market`, `Close`, `ChagesRatio`, `Amount`, `Marcap`, `Volume` |
| 계산 기준 | 상승/하락/보합 수, breadth, KOSPI/KOSDAQ breadth, 거래대금 TOP20 집중도, 15% 이상 급등 수, -15% 이하 급락 수, 상한가/하한가 수, 시총가중 등락률, 등락률/거래대금 TOP10 |
| 저장 위치 | `시장트렌드_{YYYY}` -> `KR_일별` |
| 중복 기준 | 첫 번째 컬럼 `날짜` |

저장 컬럼:

`날짜`, `총종목`, `상승`, `하락`, `보합`, `전체_breadth(%)`, `KOSPI_breadth(%)`, `KOSDAQ_breadth(%)`, `시총가중변동(%)`, `TOP20_거래대금비중(%)`, `급등15_개수`, `급락15_개수`, `상한가`, `하한가`, `최대상승종목`, `최대상승률(%)`, `최대하락종목`, `최대하락률(%)`, `최대거래대금종목`, `최대거래대금(억원)`

### 3.2 US 시장 일별 스냅샷

| 항목 | 내용 |
|---|---|
| 데이터 소스 | TradingView Scanner API `https://scanner.tradingview.com/america/scan` |
| 대상 | `type`이 `stock` 또는 `dr`, 거래소가 `AMEX`, `NASDAQ`, `NYSE` |
| 1차 필터 | `Value.Traded > 1,000,000` |
| 조회 수 | 최대 2,000개 |
| 정렬 | `Value.Traded` 내림차순 |
| 주요 컬럼 | `ticker`, `name`, `close`, `change`, `volume_value`, `high`, `low`, `market_cap`, `sector`, `volume` |
| 계산 기준 | 상승/하락/보합 수, breadth, 시총가중 등락률, 8% 이상 급등 수, -8% 이하 급락 수, 섹터별 평균 등락률/상승비율, 등락률/거래대금 TOP10 |
| 저장 위치 | `시장트렌드_{YYYY}` -> `US_일별` |
| 중복 기준 | 첫 번째 컬럼 `date` |

저장 컬럼:

`date`, `total`, `up`, `down`, `flat`, `breadth(%)`, `cap_weighted(%)`, `surge8_count`, `drop8_count`, `top_gainer`, `top_gainer(%)`, `top_loser`, `top_loser(%)`, `top_volume`, `top_volume($B)`, `sector_leader`, `sector_leader_avg(%)`, `sector_laggard`, `sector_laggard_avg(%)`

### 3.3 뉴스 요약

| 항목 | 내용 |
|---|---|
| 데이터 소스 | KR: 네이버 금융 종목 페이지, US: 네이버 주식 뉴스 API |
| 대상 | KR/US 스냅샷의 `top_gainers` 상위 10개 종목 |
| 수집량 | 종목당 뉴스 제목 최대 3개 |
| 키워드 추출 | `news_aggregator.extract_keywords`, 한/영 stopword 제외 후 빈도 상위 10개 |
| AI 요약 | `.env.local`의 `GEMINI_API_KEY`, `GEMINI_API_KEY_2...`가 있으면 Gemini REST API 호출. 없거나 실패하면 deterministic fallback 문장 사용 |
| 저장 위치 | `시장트렌드_{YYYY}` -> `뉴스요약` |
| 중복 기준 | `날짜` |

저장 컬럼:

`날짜`, `KR_키워드`, `US_키워드`, `AI_요약`

## 4. 테마/시장흐름 수집 (`snapshots`)

### 4.1 KR 섹터 맵 캐시

| 항목 | 내용 |
|---|---|
| 데이터 소스 | 네이버 금융 업종 페이지 `sise_group.naver?type=upjong` 및 업종 상세 페이지 |
| 저장 위치 | `sector_map_kr.json` |
| 캐시 갱신 기준 | 파일 없음, JSON 파싱 실패, `fetched_at` 기준 30일 초과, 또는 현재 종목 universe 대비 커버리지 95% 미만 |
| 실패 처리 | 새로 가져오기 실패 + 기존 캐시 있음: stale cache 사용. 캐시도 없으면 예외 |

### 4.2 테마클러스터_일별

| 항목 | 내용 |
|---|---|
| 데이터 소스 | `FinanceDataReader.StockListing("KRX")`, 네이버 섹터 맵, 네이버 종목 뉴스 제목 |
| 대상 | KOSPI/KOSDAQ 전종목 |
| 1차 기준 | 종목별 절대 등락률 `>= 5%` |
| 그룹 기준 | 방향 `up`/`down` + 섹터 |
| 클러스터 기준 | 같은 방향/섹터에서 최소 3종목 이상 |
| 제외 | 섹터가 `기타`인 종목 그룹 |
| 뉴스 수집 | 절대 등락률 5% 이상 종목 중 앞에서 최대 50종목에 대해 네이버 제목 수집 |
| 테마강도 | 종목 수와 평균 절대 등락률로 `★☆☆☆☆` ~ `★★★★★` 산정 |
| 저장 위치 | `시장흐름_{YYYY}` -> `테마클러스터_일별` |
| 중복 기준 | `(날짜, 방향, 섹터)` |

테마강도 기준:

| 등급 | 기준 |
|---|---|
| `★★★★★` | 종목 수 `>= 15` 또는 평균 절대 등락률 `>= 10%` |
| `★★★★☆` | 종목 수 `>= 10` 또는 평균 절대 등락률 `>= 7%` |
| `★★★☆☆` | 종목 수 `>= 7` 또는 평균 절대 등락률 `>= 5%` |
| `★★☆☆☆` | 종목 수 `>= 5` 또는 평균 절대 등락률 `>= 3%` |
| `★☆☆☆☆` | 그 외, 단 최소 3종목 조건은 통과한 경우 |

저장 컬럼:

`날짜`, `방향`, `섹터`, `포함종목수`, `대표종목(3개)`, `평균등락률(%)`, `최대등락률(%)`, `테마강도`, `합산거래대금(억)`, `관련뉴스키워드(Top5)`

### 4.3 테마트렌드_주간

| 항목 | 내용 |
|---|---|
| 데이터 소스 | `시장흐름_{YYYY}`의 `테마클러스터_일별` |
| 실행 요일 | 기본적으로 일요일 또는 월요일에 지난주 ISO 주차 기준 실행. `force_weekly=True`면 강제 가능 |
| 집계 기간 | 해당 ISO 주차의 월요일~금요일 |
| 계산 기준 | 섹터별 출현빈도, 직전 주 대비 빈도 변화, 주간 평균 등락률, 대표종목, 키워드 |
| 저장 위치 | `시장흐름_{YYYY}` -> `테마트렌드_주간` |
| 중복 기준 | `(주차(ISO), 섹터)` |

저장 컬럼:

`주차(ISO)`, `섹터`, `출현빈도`, `WoW변화`, `주간누적평균등락률(%)`, `대표종목`, `주요뉴스키워드(Top5)`

## 5. 조기신호 수집 (`snapshots`)

### 5.1 OHLCV 로컬 이력 저장

조기신호 RVOL 계산을 위해 `data/ohlcv.db`에 일별 OHLCV를 누적합니다.

| 항목 | 내용 |
|---|---|
| 데이터 소스 | KR/US 시장 스냅샷의 `ohlcv_rows` |
| 저장 위치 | SQLite `data/ohlcv.db` |
| 테이블 | `daily_ohlcv` |
| 키 | `(ticker, date)` |
| 저장 방식 | `INSERT OR REPLACE` |
| 용도 | 최근 20거래일 평균 거래량 계산, RVOL 계산 |
| 크기 경고 | DB 파일이 300MB 이상이면 경고 로그 |

테이블 컬럼:

`ticker`, `date`, `open`, `high`, `low`, `close`, `volume`, `amount`

중요한 실행 순서:

조기신호 감지는 `ohlcv_sink`보다 먼저 실행됩니다. 즉, 당일 거래량이 평균 거래량에 섞이지 않도록 이전 이력 기준으로 RVOL을 계산합니다.

### 5.2 조기신호_관찰

| 항목 | 내용 |
|---|---|
| 데이터 소스 | `FinanceDataReader.StockListing("KRX")`, `data/ohlcv.db`, 종목별 `FinanceDataReader.DataReader` |
| 대상 | KOSPI/KOSDAQ 전종목 |
| RVOL | 당일 거래량 / 최근 20거래일 평균 거래량 |
| 기본 조건 1 | `RVOL >= 3.0` |
| 기본 조건 2 | `3.0% <= 등락률 <= 10.0%` |
| 기본 조건 3 | `연속봉 >= 3` 또는 `종가 / 52주고가 >= 0.95` |
| 지표 계산 | 종목별 OHLCV에서 52주고가 근접도, 연속봉, 52주고가를 계산 |
| 저장 위치 | `시장흐름_{YYYY}` -> `조기신호_관찰` |
| 중복 기준 | `(날짜, 종목코드)` |

저장 컬럼:

`날짜`, `종목코드`, `종목명`, `등락률(%)`, `RVOL`, `연속봉`, `52주고가비율`, `합산거래대금(억)`, `5일후수익률(%)`

`5일후수익률(%)`은 최초 저장 시 빈 값이며, `backfill` 작업이 나중에 채웁니다.

## 6. 수급전환 수집 (`snapshots`)

| 항목 | 내용 |
|---|---|
| 데이터 소스 | 네이버 금융 종목별 외국인/기관 페이지 `https://finance.naver.com/item/frgn.naver?code={ticker}` |
| 대상 | KR 스냅샷의 급등률 상위 30종목 |
| 요청 제한 | 종목당 기본 `0.5초` sleep |
| 파싱 값 | 날짜, 외국인 순매매, 기관 순매매 |
| 매수전환 기준 | 오늘 값이 양수이고, 직전 5일 값이 모두 음수 |
| 매도전환 기준 | 오늘 값이 음수이고, 직전 5일 값이 모두 양수 |
| 판정 주체 | 외국인, 기관을 각각 별도 판정 |
| 저장 위치 | `시장흐름_{YYYY}` -> `수급전환_포착` |
| 중복 기준 | `(날짜, 종목코드, 전환유형)` |

저장 컬럼:

`날짜`, `종목코드`, `종목명`, `전환유형`, `당일외국인순매매`, `당일기관순매매`, `직전5일외국인누적`, `직전5일기관누적`

전환유형:

`외국인매수전환`, `외국인매도전환`, `기관매수전환`, `기관매도전환`

## 7. KR 월간 쉐도잉 스크래퍼 (`kr`)

실행 모듈: `src.crawling.stock_scraper`

### 공통 수집 로직

| 항목 | 내용 |
|---|---|
| 데이터 소스 | `FinanceDataReader.StockListing("KRX")` |
| 대상 | `Market`에 `KOSPI` 또는 `KOSDAQ`이 포함된 종목 |
| 거래일 | FDR의 `Date` 컬럼 최빈값을 `YYYYMMDD`로 사용. 없으면 실행일 사용 |
| 월 워크북 | `주식_쉐도잉_{YYYYMM}` |
| 거래대금 단위 보정 | 삼성전자 `005930`의 `Amount`가 합리 기준보다 작으면 FDR `Amount`를 백만원 단위로 보고 `1,000,000`배 보정 |
| 섹터 | `sector_map_kr.json`의 네이버 업종 캐시 |
| 뉴스 | 네이버 금융 종목 페이지에서 상위 3개 제목/URL |
| 차트 | 네이버 이미지 URL을 Google Sheets `IMAGE()` 수식으로 저장. 3개월, 1년, 3년 |
| 기술 지표 | 종목별 `FinanceDataReader.DataReader(ticker, start=오늘-400일)`로 52주신고, 52주신저, 연속봉, ATR14(%), 갭(%) 계산 |
| 요청 간격 | 종목 처리 중 네이버 뉴스 요청 뒤 `0.5초` sleep |
| 중복 기준 | `(날짜, 종목코드)` |

공통 지표 컬럼:

`52주신고`, `52주신저`, `연속봉`, `ATR14(%)`, `갭(%)`

### 7.1 급등주_쉐도잉

| 항목 | 내용 |
|---|---|
| 기준 | `등락률 >= CRAWL_KR_SURGE_THRESHOLD` |
| 기본값 | `15.0%` 이상 |
| 저장 위치 | `주식_쉐도잉_{YYYYMM}` -> `급등주_쉐도잉` |

저장 컬럼:

`날짜`, `종목명`, `종목코드`, `등락률(%)`, `거래대금(억)`, `뉴스1_제목`, `뉴스1_URL`, `뉴스2_제목`, `뉴스2_URL`, `뉴스3_제목`, `뉴스3_URL`, `3개월차트`, `1년차트`, `3년차트`, `키워드`, `52주신고`, `52주신저`, `연속봉`, `ATR14(%)`, `갭(%)`

### 7.2 거래대금_쉐도잉

| 항목 | 내용 |
|---|---|
| 1차 기준 | `거래대금 >= CRAWL_KR_VOLUME_THRESHOLD * 100,000,000` |
| 기본값 | `500억 원` 이상 |
| 제외 종목 | 삼성전자, SK하이닉스, LG에너지솔루션, 삼성바이오로직스, 현대차, 기아, 셀트리온, POSCO홀딩스, KB금융, 삼성물산 |
| 2차 기준 | 종목별 OHLCV의 `(High - Low) / Low * 100 >= CRAWL_KR_FLUCTUATION_THRESHOLD` |
| 기본값 | 변동폭 `6.0%` 이상 |
| 저장 위치 | `주식_쉐도잉_{YYYYMM}` -> `거래대금_쉐도잉` |

저장 컬럼:

`날짜`, `종목명`, `종목코드`, `등락률(%)`, `변동폭(%)`, `거래대금(억)`, `뉴스1_제목`, `뉴스1_URL`, `뉴스2_제목`, `뉴스2_URL`, `뉴스3_제목`, `뉴스3_URL`, `3개월차트`, `1년차트`, `3년차트`, `키워드`, `52주신고`, `52주신저`, `연속봉`, `ATR14(%)`, `갭(%)`

### 7.3 낙폭과대_쉐도잉

| 항목 | 내용 |
|---|---|
| 조건 A | `등락률 <= CRAWL_KR_DROP_THRESHOLD` |
| 조건 A 기본값 | `-15.0%` 이하 |
| 조건 B | `거래대금 >= CRAWL_KR_VOLUME_THRESHOLD * 100,000,000` 그리고 `등락률 <= CRAWL_KR_DROP_SECONDARY_THRESHOLD` |
| 조건 B 기본값 | `500억 원` 이상 및 `-6.0%` 이하 |
| 최종 기준 | 조건 A 또는 조건 B |
| 저장 위치 | `주식_쉐도잉_{YYYYMM}` -> `낙폭과대_쉐도잉` |

저장 컬럼:

`날짜`, `종목명`, `종목코드`, `등락률(%)`, `거래대금(억)`, `뉴스1_제목`, `뉴스1_URL`, `뉴스2_제목`, `뉴스2_URL`, `뉴스3_제목`, `뉴스3_URL`, `3개월차트`, `1년차트`, `3년차트`, `키워드`, `52주신고`, `52주신저`, `연속봉`, `ATR14(%)`, `갭(%)`

## 8. US 월간 쉐도잉 스크래퍼 (`us`)

실행 모듈: `src.crawling.us_stock_scraper`

### 공통 수집 로직

| 항목 | 내용 |
|---|---|
| 데이터 소스 | TradingView Scanner API `https://scanner.tradingview.com/america/scan` |
| 대상 | `stock`, `dr`, 거래소 `AMEX`, `NASDAQ`, `NYSE` |
| 1차 필터 | `Value.Traded > CRAWL_US_VOLUME_THRESHOLD` |
| 기본값 | `100,000,000달러` 초과 |
| 조회 수 | 최대 500개 |
| 정렬 | `change` 내림차순 |
| sanity check | `close > 0`, `volume_value >= 0`, ticker가 `^[A-Z.]+$` |
| 월 워크북 | `주식_쉐도잉_{YYYYMM}` |
| 행 날짜 | `YYYY-MM-DD` |
| 뉴스 | 네이버 미국주식 뉴스 API. suffix가 없으면 `.O` -> `.N` -> `.A` 순서로 시도. 실패 시 Yahoo Finance RSS fallback |
| 차트 | Finviz URL을 Google Sheets `IMAGE()` 수식으로 저장. 일봉, 주봉, 월봉, 3개월, 1년, 3년 |
| 기술 지표 | `FinanceDataReader.DataReader(ticker, start=오늘-400일)`로 52주신고, 52주신저, 연속봉, ATR14(%), 갭(%) 계산 |
| 요청 간격 | 종목 처리 중 뉴스 요청 뒤 `0.5초` sleep |
| 중복 기준 | `(날짜, 티커)` |

### 8.1 미국_급등주_쉐도잉

| 항목 | 내용 |
|---|---|
| 대형주 기준 | `market_cap >= CRAWL_US_MARKET_CAP_THRESHOLD` |
| 대형주 기본값 | 시총 `20억 달러` 이상 |
| 대형주 급등 기준 | `change >= CRAWL_US_SURGE_THRESHOLD_LARGE` |
| 대형주 급등 기본값 | `8.0%` 이상 |
| 소형주 급등 기준 | `market_cap < 20억 달러` 그리고 `change >= CRAWL_US_SURGE_THRESHOLD_SMALL` |
| 소형주 급등 기본값 | `15.0%` 이상 |
| 최종 기준 | 대형주 조건 또는 소형주 조건 |
| 저장 위치 | `주식_쉐도잉_{YYYYMM}` -> `미국_급등주_쉐도잉` |

저장 컬럼:

`날짜`, `종목명`, `티커`, `등락률(%)`, `거래대금($)`, `시총($)`, `뉴스1`, `URL1`, `뉴스2`, `URL2`, `뉴스3`, `URL3`, `일봉`, `주봉`, `월봉`, `3개월`, `1년`, `3년`, `키워드`, `52주신고`, `52주신저`, `연속봉`, `ATR14(%)`, `갭(%)`

### 8.2 미국_거래대금_쉐도잉

| 항목 | 내용 |
|---|---|
| 1차 기준 | TradingView 조회 자체가 `Value.Traded > 100,000,000달러` 기본 필터를 적용 |
| 2차 기준 | `(high - low) / low * 100 >= CRAWL_US_VOLATILITY_THRESHOLD` |
| 기본값 | 변동폭 `5.0%` 이상 |
| 저장 위치 | `주식_쉐도잉_{YYYYMM}` -> `미국_거래대금_쉐도잉` |

저장 컬럼:

`날짜`, `종목명`, `티커`, `등락률(%)`, `변동폭(%)`, `거래대금($)`, `뉴스1`, `URL1`, `뉴스2`, `URL2`, `뉴스3`, `URL3`, `일봉`, `주봉`, `월봉`, `3개월`, `1년`, `3년`, `키워드`, `52주신고`, `52주신저`, `연속봉`, `ATR14(%)`, `갭(%)`

### 8.3 미국_낙폭과대_쉐도잉

| 항목 | 내용 |
|---|---|
| 대형주 기준 | `market_cap >= 20억 달러` 그리고 `change <= CRAWL_US_DROP_THRESHOLD_LARGE` |
| 대형주 기본값 | `-8.0%` 이하 |
| 소형주 기준 | `market_cap < 20억 달러` 그리고 `change <= CRAWL_US_DROP_THRESHOLD_SMALL` |
| 소형주 기본값 | `-15.0%` 이하 |
| 최종 기준 | 대형주 조건 또는 소형주 조건 |
| 저장 위치 | `주식_쉐도잉_{YYYYMM}` -> `미국_낙폭과대_쉐도잉` |

저장 컬럼:

`날짜`, `종목명`, `티커`, `등락률(%)`, `거래대금($)`, `시총($)`, `뉴스1`, `URL1`, `뉴스2`, `URL2`, `뉴스3`, `URL3`, `일봉`, `주봉`, `월봉`, `3개월`, `1년`, `3년`, `키워드`, `52주신고`, `52주신저`, `연속봉`, `ATR14(%)`, `갭(%)`

## 9. 5일 수익률 백필 (`backfill`)

실행 모듈: `src.crawling.backfill_5day_return`

| 항목 | 내용 |
|---|---|
| 읽는 위치 | `시장흐름_{YYYY}` -> `조기신호_관찰` |
| 대상 행 | `5일후수익률(%)`이 비어 있고, 신호일로부터 5영업일 이상 지난 행 |
| 종가 데이터 | `FinanceDataReader.DataReader(ticker, start=None)` |
| 기준 가격 | 신호일 종가와 신호일 +5영업일 종가 |
| 계산식 | `(T+5 종가 / 신호일 종가 - 1) * 100` |
| 저장 방식 | 기존 행의 마지막 컬럼 `5일후수익률(%)`을 `update_cell`로 업데이트 |
| 반환 로그 | 업데이트한 행 수 |

날짜가 정확히 매칭되지 않으면 해당 날짜 이전의 가장 가까운 거래일 종가를 사용합니다.

## 10. 조기신호 백테스트 (`backtest`)

실행 모듈: `src.crawling.backtest_early_signal`

직접 실행 예시:

```powershell
python -m src.crawling.backtest_early_signal --start 2026-01-01 --end 2026-04-30 --horizons 1,3,5 --surge-threshold 15
```

| 항목 | 내용 |
|---|---|
| 읽는 위치 | `시장흐름_{YYYY}` -> `조기신호_관찰` |
| 필수 인자 | `--start`, `--end` |
| 선택 필터 | 섹터, 최소/최대 등락률, RVOL, 연속봉, 52주고가비율 |
| 가격 데이터 | `FinanceDataReader.DataReader` 기반 종가 |
| 계산 지표 | +N영업일 수익률 분포, win rate, +1~+5영업일 최대 수익률, 급등 기준 도달률, 섹터별 hit rate |
| 실제 급등주 매칭 | 월별 `주식_쉐도잉_{YYYYMM}`의 급등주 탭을 읽어 +1~+5영업일 내 진입 여부 계산 |
| 출력 위치 | 기본 `reports/backtest_YYYYMMDD.md` |

리포트에는 survivorship 누락 수, 진입가격 가정, horizon, 필터 조건이 함께 기록됩니다.

## 11. 결과 조회 탭

대시보드의 "크롤링 결과 조회" 탭은 `src.crawling.schemas`에 정의된 스키마를 기준으로 Google Sheets를 읽습니다.

| 조회 대상 | 읽는 워크북/탭 |
|---|---|
| KR 급등주 | `주식_쉐도잉_{YYYYMM}` -> `급등주_쉐도잉` |
| KR 거래대금 | `주식_쉐도잉_{YYYYMM}` -> `거래대금_쉐도잉` |
| KR 낙폭과대 | `주식_쉐도잉_{YYYYMM}` -> `낙폭과대_쉐도잉` |
| US 급등주 | `주식_쉐도잉_{YYYYMM}` -> `미국_급등주_쉐도잉` |
| US 거래대금 | `주식_쉐도잉_{YYYYMM}` -> `미국_거래대금_쉐도잉` |
| US 낙폭과대 | `주식_쉐도잉_{YYYYMM}` -> `미국_낙폭과대_쉐도잉` |
| 시장트렌드 KR 일별 | `시장트렌드_{YYYY}` -> `KR_일별` |
| 시장트렌드 US 일별 | `시장트렌드_{YYYY}` -> `US_일별` |
| 뉴스 요약 | `시장트렌드_{YYYY}` -> `뉴스요약` |
| 테마 클러스터 일별 | `시장흐름_{YYYY}` -> `테마클러스터_일별` |
| 테마 트렌드 주간 | `시장흐름_{YYYY}` -> `테마트렌드_주간` |
| 조기신호 관찰 | `시장흐름_{YYYY}` -> `조기신호_관찰` |
| 수급전환 포착 | `시장흐름_{YYYY}` -> `수급전환_포착` |

조회 흐름:

1. `SHEET_ID_*` 환경 변수가 있으면 `open_by_key`로 열고, 없으면 워크북 제목으로 엽니다.
2. `worksheet.get_all_values()`로 전체 값을 읽습니다.
3. 첫 행을 헤더로 보고 `pandas.DataFrame`으로 변환합니다.
4. live 조회에 성공하면 `data/crawling/cache/sheets_cache.sqlite3`에 캐시합니다.
5. live 조회 실패 시 캐시가 있으면 캐시 데이터를 표시합니다.
6. UI에서 검색어, 시작일, 종료일 필터를 적용합니다.
7. 일반 결과는 날짜별 건수 막대그래프, 테마클러스터는 섹터 heatmap, 테마트렌드는 섹터별 주간 timeline을 표시합니다.
8. 필터된 결과는 CSV로 다운로드할 수 있습니다.

## 12. 알림

`snapshots` 마지막 단계에서 Telegram 알림을 보낼 수 있습니다.

| 조건 | 내용 |
|---|---|
| 설정 파일 | `.env.local` |
| 필요한 값 | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| KR 급등 알림 | KR 급등주 수가 5개 이상이면 발송 |
| 테마 알림 | 테마강도 `★★★★☆` 또는 `★★★★★` 클러스터가 있으면 발송 |
| 오류 알림 | 파이프라인 일부 실패로 rc가 0이 아니면 발송 |

알림은 파이프라인 성공/실패 판정에는 영향을 주지 않습니다. 실패해도 로그만 남기고 계속 진행합니다.

## 13. 현재 코드상 주의할 점

1. `run_daily --dry-run`은 실제 데이터 소스나 Google Sheets 쓰기까지 검증하지 않고, 실행될 step 목록만 출력합니다. KR/US 모듈 내부에는 별도의 `DRY_RUN=1`, `MOCK=1` 경로가 있지만 대시보드 dry-run과는 다릅니다.
2. `run_daily --mode backtest`는 `backtest_early_signal`에 필요한 `--start`, `--end`를 전달하지 않습니다. 백테스트는 현재 직접 CLI로 실행하는 방식이 안전합니다.
3. Google Sheets를 서비스 계정으로 생성하면 기본적으로 서비스 계정 소유 문서가 됩니다. 개인 계정에서 보려면 해당 시트를 공유해야 합니다.
4. 뉴스/섹터/수급 수집은 네이버 페이지 구조에 의존합니다. 페이지 HTML이 바뀌면 파싱 결과가 빈 값이 될 수 있습니다.
5. TradingView Scanner 응답은 배열 위치 기반으로 디코딩합니다. 첫 5건 sanity 실패 또는 전체 실패율 5% 초과 시 stderr 경고를 남깁니다.
6. `data/ohlcv.db`는 계속 누적되는 로컬 캐시입니다. 300MB 이상이면 경고만 출력하며 자동 삭제는 하지 않습니다.
7. 일부 production wiring에 package prefix 없이 import하는 경로가 남아 있습니다. 실행 환경의 `PYTHONPATH`에 따라 `generate_snapshots`의 테마 뉴스 수집 또는 `backfill` import가 실패할 수 있으므로, 실패 로그가 보이면 import 경로부터 확인해야 합니다.
