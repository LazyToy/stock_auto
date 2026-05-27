# stock_auto 자동 분석 기능 상세 정리

- 작성일: 2026-05-26
- 조사 방식: SequentialThinking MCP로 기능 경로를 먼저 분해한 뒤, 현재 폴더의 Streamlit 대시보드, 분석 모듈, 자동매매 연동 코드, 테스트, 설정 파일을 기준으로 정리했다.
- 기준 코드: `dashboard/app.py`, `dashboard/components/*`, `src/analysis/*`, `src/optimization/*`, `src/trader/auto_trader.py`, `config/trading.yaml`
- 주의: 아래 내용은 현재 구현을 설명한 기술 문서이며 투자 조언이 아니다.

## 한눈에 보는 기능 지도

| 기능 | UI 위치 | 핵심 구현 | 주요 데이터 | 최종 출력 |
|---|---|---|---|---|
| 성장주 탐색 | `🌱 성장주 탐색` 탭 | `src/analysis/market_interest.py`, `src/analysis/growth_stock_finder.py`, `src/analysis/supply_flow.py`, `src/analysis/growth_validation.py` | 실시간 시장 스캔, 6개월 일봉, yfinance 재무 데이터, 외국인/기관 수급, 성장 후보 사후검증, 선택 시 Tavily 검색 | Top 5 성장 가능 종목, 시장 관심도, 수급 점수, 섹터 상대순위, 3년 지속성, 성장 점수, 재무 건전성, 뉴스 감성 |
| 심층 분석 | `🧠 심층 분석` 탭 | `src/analysis/multimodal.py` | 6개월 가격, 차트 이미지, RSI/MACD/볼린저/거래량, Reddit 감성 | Gemini 기반 매수/매도/보유, 신뢰도, 근거, 리스크 |
| AutoML | `🧬 AutoML` 탭 | `src/optimization/genetic.py`, `src/optimization/evaluator.py` | yfinance 1년 종가 | MACD+RSI 최적 파라미터, Sharpe 기반 fitness, 세대별 이력 |
| Stress Test | `💥 Stress Test` 탭 | `src/analysis/stress.py` | 포트폴리오 비중, 위기 구간 가격 데이터 | 시나리오 수익률, 예상 손실액, 종목별 충격 |
| Smart Money | `Smart Money` 탭 및 자동매매 옵션 | `src/analysis/smart_money/*`, `src/analysis/timeframes.py` | 5분봉/1시간봉/일봉 OHLCV, ICT/SMC 패턴 | BUY/SELL/HOLD, confidence, entry zone, invalidation, 차트 주석 |

## 1. 성장주 탐색

### 기능 목적

성장주 탐색은 실제 시장을 먼저 스캔해 최근 며칠~몇 주간 관심이 누적된 종목을 후보로 만들고, 상위 후보만 재무 데이터로 검증하는 기능이다. 기본 모드는 실시간 시장 스캔 + 6개월 일봉 기반 시장 관심도 계산 + 섹터 내 상대순위 + yfinance 재무 스크리닝이며, 재무제표가 충분하면 3년 매출 CAGR과 영업이익 개선폭으로 성장 지속성을 추가 평가한다. 한국 종목은 상위 후보에 대해 외국인/기관 수급도 확인하며, 네이버 금융 파서가 비어 있으면 pykrx를 fallback으로 사용한다. 검색된 검토 후보는 날짜별 CSV 스냅샷으로 저장할 수 있어, 이후 20일/60일 사후검증 입력으로 재사용할 수 있다. 사용자가 Tavily API 키를 넣으면 최신 뉴스와 트렌드 검색 결과를 참고 신호로 추가한다. 화면 문구는 투자 권유처럼 보이는 표현 대신 "검토 후보/검토 근거"를 사용한다.

### 진입 경로

- 대시보드 탭: `dashboard/components/growth_tab.py`
- 시장 관심도 후보 생성기: `MarketInterestCandidateProvider`
- 실제 탐색기: `HybridGrowthStockFinder`
- 외국인/기관 수급 분석기: `src/analysis/supply_flow.py`
- 성장 후보 사후검증: `src/analysis/growth_validation.py`
- 호환 alias: `GrowthStockFinder = HybridGrowthStockFinder`
- 대시보드는 `render_growth_tab()`에서 시장 선택, 후보 생성 방식, 재무 확인 후보 수, 일봉 확인 후보 수, 관심 누적 기간, Tavily 키 입력, 탐색 버튼, 결과 카드/표/차트, 성장 후보 저장, 사후 검증 실행 UI를 렌더링한다.

### 후보 생성 방식

기본 경로는 다음 순서다.

1. KR은 KOSPI/KOSDAQ 전체, US는 NYSE/NASDAQ/AMEX 스캐너를 조회한다.
2. 거래대금과 당일 관심도로 먼저 후보를 압축한다.
3. 압축된 후보만 6개월 일봉을 조회한다.
4. 5일 모멘텀, 선택한 관심 누적 기간의 모멘텀, 최근 5일 평균 거래량 대비 이전 20일 평균 거래량, 120일 고점 근접도를 계산한다.
5. 당일 12~20% 이상 급등, 5일 급등, 거래량 폭발이 겹친 단발 과열 후보에는 `overheat_penalty`를 적용한다.
6. 같은 섹터 안에서 시장 관심도 순위와 백분위를 계산한다.
7. 시장 관심도 상위 후보만 yfinance 재무 스크리닝으로 넘긴다.
8. 재무제표가 충분하면 3년 매출 CAGR과 영업이익 개선폭으로 재무 성장 지속성 점수를 계산한다.
9. 한국 종목은 현재 성장 점수 상위 후보에 외국인/기관 수급 점수를 붙인다. 네이버 금융 `frgn.naver` 파서가 1차 소스이고, 비어 있으면 pykrx의 투자자별 거래대금 데이터를 fallback으로 사용한다.

관심 누적 기간은 UI에서 `최근 20일` 또는 `최근 60일`로 선택한다. 재무제표 조회는 전체 시장에 대해 수행하지 않고 시장 관심도 상위 후보에 대해서만 수행한다.

### 고정 후보군 옵션

고정 후보군 옵션도 남아 있다. 한국은 AI/반도체, 2차전지, 로봇/자동화, 바이오, 전력기기/첨단소재 중심이고, 미국은 AI/반도체, 우주항공, EV/자율주행, 양자/AI, SaaS/클라우드 중심이다. 단, 현재 기본값은 고정 목록이 아니라 실시간 시장 스캔이다.

### 사용하는 지표

| 지표 | 코드상 원천 | 의미 | 사용 위치 |
|---|---|---|---|
| 매출 성장률 | `info["revenueGrowth"] * 100`, 없으면 `financials["Total Revenue"]` 직접 계산 | 최근 매출 증가 속도 | 스크리닝, 재무성장성, 검토 근거 |
| 영업/순이익률 | `info["profitMargins"] * 100`, 없으면 `Operating Income / Total Revenue` | 성장의 질, 수익성 | 성장 점수, 재무 건전성 |
| 부채비율 | `info["debtToEquity"]` | 재무 레버리지 위험 | 스크리닝, 성장 점수, 재무 건전성 |
| 유동비율 | `info["currentRatio"]` | 단기 지급 능력 | 스크리닝, 성장 점수, 재무 건전성 |
| PER | `info["trailingPE"]` | 밸류에이션 참고값 | 밸류에이션, 화면 표시 |
| 시가총액 | `info["marketCap"]` | 규모 분류 및 미국 종목 상한 필터 | 스크리닝, 화면 표시 |
| 현재가 | 시장 스캔 `close`, 없으면 yfinance `currentPrice`/`regularMarketPrice` | 후보의 현재 가격 | 카드, 상세 데이터 |
| 가격 통화 | KR은 `KRW`, US는 yfinance `currency` 또는 `USD` | 현재가 기준 화폐 | 카드, 상세 데이터 |
| 시장 관심도 | `MarketInterestCandidate.interest_score` | 실시간 시장에서 누적 관심이 붙은 정도 | 후보 생성, 성장 점수 보정, 화면 표시 |
| 20일/60일 모멘텀 | 6개월 일봉 `Close` | 선택한 관심 누적 기간의 가격 추세 | 시장 관심도 점수 |
| 거래량 비율 | 최근 5일 평균 거래량 / 이전 20일 평균 거래량 | 관심 증가 여부 | 시장 관심도 점수 |
| 고점 근접도 | 최신 종가 / 최근 120일 고가 | 강한 추세 유지 여부 | 시장 관심도 점수 |
| 과열 감점 | 당일 급등, 5일 급등, 거래량 폭발 조합 | 단발 급등주 쏠림 완화 | 시장 관심도 점수, 검토 근거 |
| 섹터 상대순위 | 후보군 내 같은 섹터별 `interest_score` 순위 | 섹터 안에서 실제로 강한 후보인지 확인 | 화면 표시, 상세 데이터 |
| 데이터 신뢰도 | 수집된 재무 지표 수 / 5 | 재무 데이터가 충분한 정도 | 점수 구성, 리스크 감점 |
| 3년 매출 CAGR | `financials["Total Revenue"]` 최근~과거 3년 비교 | 성장 지속성 | 점수 구성, 상세 데이터 |
| 영업이익 개선폭 | `financials["Operating Income"]` 최근~과거 3년 비교 | 성장의 질 개선 여부 | 점수 구성, 상세 데이터 |
| 수급 점수 | `SupplyFlowProvider` | 외국인/기관 수급 유입 또는 전환 여부 | 성장 점수 보정, 화면 표시 |
| 5일 스마트머니 순매수 | 네이버 금융 또는 pykrx | 최근 5일 외국인+기관 누적 수급 | 화면 표시, 상세 데이터 |
| 수급 전환 | `detect_reversal()` | 외국인/기관 매수전환 또는 매도전환 | 수급 점수, 검토 근거 |
| 섹터 | 한국은 내부 매핑 우선, 미국은 yfinance sector | 섹터별 분포 | 섹터 요약, 차트 색상 |
| 뉴스 요약 | Tavily `include_answer` | 최신 성장 전망 보완 | 화면 표시 |
| 뉴스 감성 | 키워드 카운트 | 긍정/중립/부정 | 점수 보정 |

### 1차 스크리닝 기준

`SCREENING_CRITERIA`는 다음 네 가지다.

| 조건 | 기준 | 예외 |
|---|---:|---|
| 최소 매출 성장률 | 10% 이상 | 값이 없으면 해당 조건은 통과 처리 |
| 최대 부채비율 | 150% 이하 | 값이 없으면 해당 조건은 통과 처리 |
| 최소 유동비율 | 1.0 이상 | 값이 없으면 해당 조건은 통과 처리 |
| 최대 시가총액 | 500억 달러 미만 | 한국 종목은 yfinance가 원화 시총을 반환하므로 상한 비교를 건너뜀 |

중요한 점은 데이터가 없는 지표를 즉시 탈락시키지 않는다는 것이다. 예를 들어 매출 성장률이 없으면 성장 점수 가점은 못 받지만, 그 자체로 탈락하지는 않는다.

### 성장 점수 계산 방식

성장 점수는 단일 점수로만 보이지 않고 구성 요소도 함께 보여준다. 기본 점수는 5.0점이며 최종 점수는 1.0~10.0 범위로 clamp된다.

| 구성 요소 | 조건 | 점수 변화 |
|---|---|---:|
| 시장 관심도 | 실시간 후보의 `interest_score` | 최대 +1.0 |
| 외국인/기관 수급 | 최근 5일 누적, 양수 일수, 매수/매도 전환 | -0.5~+1.0 |
| 3년 재무 지속성 | 매출 CAGR, 영업이익 개선 | 최대 +2.5 |
| 매출 성장률 | 30% 초과 | +2.0 |
| 매출 성장률 | 20% 초과 | +1.5 |
| 매출 성장률 | 10% 초과 | +1.0 |
| 이익률 | 15% 초과 | +1.5 |
| 이익률 | 10% 초과 | +1.0 |
| 이익률 | 5% 초과 | +0.5 |
| 부채비율 | 50% 미만 | +1.0 |
| 부채비율 | 100% 미만 | +0.5 |
| 유동비율 | 2.0 초과 | +0.5 |
| 유동비율 | 1.5 초과 | +0.25 |
| PER | 0~20 | +0.4 |
| PER | 80 초과 | -0.4 |
| 데이터 신뢰도 | 재무 지표 5개 중 4개 미만 확보 | `risk_penalty` 적용 |
| Tavily 뉴스 감성 | Positive | +0.5 |

점수 구성은 화면에서 시장 관심도, 수급 점수, 재무성장성, 수익성/건전성, 3년 지속성, 밸류에이션, 리스크감점, 데이터신뢰도로 분해해 확인할 수 있다. 재무 데이터가 부족하면 `data_confidence`가 낮아지고, 0.8 미만일 때 `risk_penalty = -((0.8 - data_confidence) * 2.0)` 방식의 감점이 적용된다. 값 누락은 즉시 탈락이 아니라 confidence penalty로 다룬다.

### 수급 보강 방식

`SupplyFlowProvider`는 한국 종목 코드에서 `.KQ`, `.KS`를 제거한 6자리 ticker를 사용한다. 1차로 `src/crawling/flow_fetcher.py`의 네이버 금융 파서를 호출하고, 결과가 비어 있거나 실패하면 pykrx `get_market_trading_value_by_date()`를 호출한다. 네이버 금융 값은 순매매량이므로 `주` 단위로 표시하고, pykrx fallback 값은 거래대금이므로 `KRW` 단위로 표시한다. 계산 항목은 최근 외국인 순매수, 최근 기관 순매수, 최근 5일 외국인+기관 누적, 최근 5일 중 수급 양수 일수, 외국인/기관 매수전환 또는 매도전환이다.

수급 점수는 `-0.5~+1.0` 범위다. 최근 외국인+기관 합산 수급이 양수이고 5일 중 양수 일수가 많으면 가점한다. `외국인매수전환`, `기관매수전환`은 추가 가점이며, 매도전환과 5일 누적 순매도는 감점한다. 이 점수는 성장 점수에 직접 더하되, 후보 전체가 아니라 현재 점수 상위 한국 후보에만 적용해 요청량을 제한한다.

### 재무 건전성 등급

재무 건전성은 별도의 0~6점 내부 점수로 Excellent/Good/Fair/Poor를 매긴다.

| 항목 | 조건 | 내부 점수 |
|---|---|---:|
| 부채비율 | 50% 미만 | +2 |
| 부채비율 | 100% 미만 | +1 |
| 유동비율 | 2.0 초과 | +2 |
| 유동비율 | 1.5 초과 | +1 |
| 이익률 | 10% 초과 | +2 |
| 이익률 | 5% 초과 | +1 |

등급 변환:

| 내부 점수 | 등급 |
|---:|---|
| 5 이상 | Excellent |
| 3 이상 | Good |
| 1 이상 | Fair |
| 0 | Poor |

### Tavily 보강 방식

Tavily API 키가 있으면 yfinance 스크리닝 결과 상위 종목에 대해 다음 검색어를 만든다.

```text
{종목명} {섹터} 성장 전망 2026
```

요청은 `https://api.tavily.com/search`에 `search_depth=basic`, `max_results=3`, `include_answer=True`로 보낸다. 응답의 `answer`를 최대 200자까지 뉴스 요약으로 저장하고, 감성 키워드를 세어 `Positive`, `Negative`, `Neutral`을 판정한다.

긍정 키워드:

```text
성장, 상승, 호재, 긍정, 기대, 확대, 증가, 수혜, growth, positive, bullish
```

부정 키워드:

```text
하락, 부진, 악재, 우려, 감소, 축소, 리스크, decline, negative, bearish
```

긍정 키워드 수가 부정 키워드 수보다 2개 이상 많으면 Positive, 반대이면 Negative, 그 외는 Neutral이다.

### 결과 화면

대시보드는 다음 정보를 보여준다.

- 분석 종목 수
- 평균 성장 점수
- 주요 섹터
- 검토 후보 Top 5 카드
- 현재가, 가격 통화, 성장 점수, 재무 건전성, 매출 성장률, 영업이익률
- 부채비율, 유동비율, PER
- 시장 관심도, 모멘텀, 거래량 비율, 데이터 신뢰도
- 수급 점수, 5일 스마트머니, 최근 외국인, 최근 기관 및 수급 단위
- 점수 구성: 재무성장성, 수익성/건전성, 3년 지속성, 밸류에이션, 리스크감점
- 3년 매출 CAGR, 섹터 순위, 섹터 백분위
- 검토 근거
- Tavily 사용 시 뉴스 요약과 뉴스 감성
- 상세 DataFrame
- 종목별 성장 점수 막대 차트
- 현재 검토 후보 저장 버튼

현재가는 `1,234 KRW`, `1,234.50 USD`처럼 통화와 천단위 콤마를 함께 표시한다. 수급 지표는 라벨과 값 양쪽에 단위를 표시한다. 예를 들어 네이버 금융 수급이면 `5일 스마트머니(주)` / `6,566 주`, pykrx fallback이면 `5일 스마트머니(KRW)` / `1,234,000 KRW`처럼 보인다. 카드의 주요 용어 라벨 바로 옆에는 작은 `?` 도움말 아이콘이 있으며, 해당 지표가 무엇을 의미하고 점수에 어떻게 쓰이는지 설명한다.

### 사후 검증

성장주 탭에는 `💾 성장 후보 저장` 섹션이 있다. 현재 검토 후보를 저장하면 `data/growth_candidates/growth_candidates_YYYYMMDD.csv` 파일이 생성된다. 저장 컬럼은 `date`, `symbol`, `name`, `score`, `sector`이며, 같은 날짜/종목은 중복 저장하지 않는다.

성장주 탭 하단에는 `🧪 사후 검증` 섹션도 있다. 저장된 성장 후보 CSV를 선택하고 `저장 후보 사후검증 실행` 버튼을 누르면 yfinance 가격 이력을 조회해 후보 선정 이후 20영업일/60영업일 수익률, hit 여부, 평균 수익률, hit rate를 화면에서 바로 계산한다. 한국 6자리 종목코드는 조회 시 `.KQ`, `.KS`를 순서대로 시도한다.

기존 시장흐름 검증도 터미널 입력 없이 `조기신호 백테스트 실행` 버튼으로 실행할 수 있다. 사용자가 검증 시작일, 종료일, 관찰 영업일, 급등 기준을 입력하면 Streamlit 서버가 현재 Python으로 다음 모듈을 실행한다.

```powershell
python -m src.crawling.backtest_early_signal --start YYYY-MM-DD --end YYYY-MM-DD --horizons 1,3,5 --surge-threshold 15
```

`reports/backtest_*.md` 리포트가 있으면 최신 파일을 미리보기로 보여준다. 이 백테스트는 현재 시장흐름의 `조기신호_관찰`과 KR 급등주 데이터를 기준으로 검증한다.

성장 후보 자체의 20일/60일 사후검증을 위해 `src/analysis/growth_validation.py`도 추가되어 있다. `load_growth_candidate_snapshots()`로 저장된 CSV를 읽고, `GrowthCandidateSnapshot` 목록과 종목별 가격 이력을 `validate_growth_candidates()`에 넣으면 20영업일/60영업일 수익률, hit 여부, 평균 수익률, hit rate를 계산한다.

### 자동매매 Growth Mode와의 차이

대시보드의 성장주 탐색과 자동매매의 `style="GROWTH"`는 다른 경로다.

자동매매 Growth Mode는 `src/strategies/selector.py`의 `StockSelector._calculate_growth_score()`를 사용한다. 여기서는 전체 기간 모멘텀, 변동성, 거래량 비율, revenueGrowth, PSR, 시가총액을 활용해 selector score를 만든다.

자동매매 Growth score 특징:

- `raw_score = (momentum * 2.0) / max(0.1, volatility * 0.3)`
- 거래량 비율은 0.8~1.5 범위 multiplier
- 매출 성장률 50% 초과 +1.0, 30% 초과 +0.5, 15% 초과 +0.2
- 매출 성장률 5% 미만 -0.5, 음수 -0.8
- PSR 3 미만 +0.2, PSR 30 초과 -0.3
- 시가총액 500억 달러 미만이면서 매출 성장률 20% 초과이면 +0.3

즉, 대시보드 성장주 탐색은 "시장 관심도 후보 생성 + 재무 스크리닝 + 뉴스 보강"이고, 자동매매 Growth Mode는 "모멘텀/변동성 기반 selector 점수에 성장 팩터를 곱하는 방식"이다.

## 2. 심층 분석

### 기능 목적

심층 분석은 단일 종목을 대상으로 차트 이미지, 기술 지표 요약, 시장 컨텍스트를 Gemini에 전달해 최종 매수/매도/보유 판단을 받는 멀티모달 분석 기능이다. 실제 뉴스 제목을 수집한 경우에는 뉴스 맥락도 함께 전달하고, Reddit API로 실제 게시글을 수집한 경우에만 Reddit 원문도 함께 전달한다. 뉴스/소셜 판단은 Gemini 리포트 작성 단계에서 수행한다.

### 진입 경로

- 대시보드 탭: `dashboard/app.py`의 Deep Analysis 영역
- 핵심 클래스: `src/analysis/multimodal.py`의 `MultimodalAnalyst`
- 차트 생성: `src/analysis/chart.py`의 `ChartGenerator`
- 가격 조회: `src/analysis/market_data.py`의 `MarketDataFetcher`
- 뉴스 데이터: `src/data/news.py`의 `NewsFetcher`, 내부적으로 `src/crawling/news_fetcher.py` 재사용
- 소셜 데이터: `src/data/social.py`의 `RedditScraper`

### 데이터 흐름

1. 사용자가 종목 코드를 입력한다.
2. 숫자만 입력하면 한국 종목으로 보고 `.KS`, `.KQ` 후보를 순차 조회한다.
3. 영문 티커면 그대로 조회한다.
4. `MarketDataFetcher.fetch_history()`가 yfinance history를 가져온다.
5. 기본 조회 기간은 6개월이다.
6. `ChartGenerator.generate_chart()`가 캔들 차트 PNG bytes를 만든다.
7. `NewsFetcher.fetch_for_ticker(selected_ticker, limit=Config.DEEP_ANALYSIS_NEWS_LIMIT)`로 뉴스 제목과 URL을 가져오려고 시도한다.
8. `RedditScraper.fetch_ticker_posts(selected_ticker, Config.REDDIT_SUBREDDIT, limit=Config.REDDIT_POST_LIMIT)`로 설정된 서브레딧에서 해당 티커가 명시된 게시글 원문과 반응 메타데이터를 검색한다.
9. 가격 데이터에서 기술 지표 요약과 시장 컨텍스트를 만든다.
10. 뉴스가 실제로 수집된 경우에만 뉴스 제목과 URL을 프롬프트에 포함하고 Gemini가 뉴스 맥락을 직접 판단하게 한다.
11. Reddit 게시글이 실제로 수집된 경우에만 원문을 프롬프트에 포함하고 Gemini가 소셜 심리를 직접 판단하게 한다. 그렇지 않으면 소셜 데이터가 없으므로 추정하지 말라고 지시한다.
12. Gemini에 텍스트 프롬프트와 차트 이미지를 같이 보낸다.
13. Gemini JSON 응답을 파싱해 화면에 표시한다.

### 티커 정규화

| 입력 | 조회 후보 |
|---|---|
| `005930` | `005930.KS`, `005930.KQ` |
| `317330` | `317330.KS`, `317330.KQ` |
| `AAPL` | `AAPL` |
| 공백 | 분석 중단, "종목 코드를 입력하세요." |

한국 종목은 `.KS` 조회가 비거나 예외가 나면 `.KQ`로 재시도한다.

### 시장 컨텍스트 지표

`_build_market_context_summary()`는 최소 20개 종가가 있어야 안정적으로 계산한다.

| 지표 | 계산 | 해석 |
|---|---|---|
| 20일선 위치 | 최신 종가와 20일 이동평균 비교 | 단기 상승/약세/중립 흐름 |
| 60일선 위치 | 최신 종가와 60일 이동평균 비교 | 중기 위치 |
| 20거래일 모멘텀 | `(latest_close - close[-20]) / close[-20] * 100` | 최근 약 한 달 수익률 |

데이터가 20개 미만이면 "데이터가 부족해 추세 맥락을 안정적으로 계산하지 못했습니다."라는 fallback 문구를 넣는다.

### 기술 지표

`_build_technical_summary()`는 최소 26개 종가가 있어야 RSI/MACD/볼린저를 안정적으로 계산한다.

| 지표 | 계산 | 화면/프롬프트 해석 |
|---|---|---|
| 종가 | 최신 `Close` | 현재 가격 |
| 전일 대비 | 최신 일간 수익률 | 단기 변화율 |
| RSI(14) | 평균 상승폭/하락폭 기반 14일 RSI | 70 이상 과매수, 30 이하 과매도, 그 외 중립 |
| MACD | EMA(12) - EMA(26) | MACD가 signal 위면 상방 우위, 아래면 하방 우위 |
| Signal | MACD의 EMA(9) | MACD 비교 기준 |
| Histogram | MACD - Signal | 모멘텀 차이 |
| 볼린저 밴드 | 20일 평균 ± 2표준편차 | 상단 근접, 하단 근접, 중앙권, 밴드 폭 협소 |
| 거래량 비율 | 최신 거래량 / 최근 20개 평균 거래량 | 평균 대비 몇 배인지 |

데이터가 26개 미만이면 RSI/MACD/볼린저를 계산하지 않고 fallback 문구를 넣는다.

### 차트 이미지

`ChartGenerator`는 `mplfinance`를 사용한다.

- 차트 유형: 캔들스틱
- 보조 표시: 거래량
- 이동평균: 20일, 60일
- 스타일: 기본 `yahoo`
- 출력: PNG bytes
- 한글 제목이면 사용 가능한 한글 폰트를 찾아 matplotlib rc를 적용한다.

### 뉴스 수집

`NewsFetcher`는 기존 `src/crawling/news_fetcher.py`를 재사용한다.

| 시장/티커 | 수집 방식 |
|---|---|
| 숫자형 한국 종목 또는 `.KS`/`.KQ` | 네이버 금융 종목 페이지에서 뉴스 제목과 URL 크롤링 |
| 영문 티커 | 네이버 증권 미국주식 뉴스 API에서 뉴스 제목과 URL 수집 |

설정값:

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| `DEEP_ANALYSIS_NEWS_LIMIT` | `3` | 심층분석에서 가져올 뉴스 수 |

뉴스 수집 결과가 없으면 프롬프트에는 "뉴스 데이터는 이번 분석에 사용하지 않았습니다."가 들어가고, `analysis_sources`에는 `"뉴스"`가 추가되지 않는다. 수집 결과가 있으면 각 뉴스의 제목 원문과 URL을 함께 전달한다.

### 소셜 원문 분석

`RedditScraper`는 Reddit API 키가 있을 때만 실제 Reddit API 클라이언트를 만든다. 키가 없거나 API 호출이 실패하거나 게시글이 비어 있으면 빈 리스트를 반환하고, 프롬프트에는 "소셜 데이터는 이번 분석에 사용하지 않았습니다."가 들어간다.

Reddit 설정값:

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| `REDDIT_CLIENT_ID` | 없음 | Reddit 앱의 client id |
| `REDDIT_CLIENT_SECRET` | 없음 | Reddit 앱의 client secret |
| `REDDIT_USER_AGENT` | `stock_auto_bot/1.0` | Reddit API user-agent |
| `REDDIT_SUBREDDIT` | `stocks` | 수집할 서브레딧 이름 |
| `REDDIT_POST_LIMIT` | `5` | 티커 검색으로 가져올 Reddit 게시글 수 |
| `REDDIT_SEARCH_SORT` | `relevance` | Reddit 검색 정렬 방식 |
| `REDDIT_SEARCH_TIME_FILTER` | `month` | Reddit 검색 기간 필터 |

`RedditScraper`는 키워드 기반 감성 점수를 미리 계산하지 않는다. 각 게시글의 제목 원문, 본문 원문, score, 댓글 수, URL, 출처를 그대로 프롬프트에 넣고 Gemini가 리포트 작성 과정에서 낙관/비관/중립/혼재 여부를 판단한다.

### Gemini 프롬프트와 응답

Gemini에는 다음 축이 들어간다.

- 조회 심볼
- 최근 뉴스 제목과 URL (뉴스가 실제 수집된 경우에만)
- 시장 컨텍스트
- 기술 지표 요약
- 차트 이미지 PNG
- 최근 소셜 원문 (Reddit 게시글이 실제 수집된 경우에만)

요구 작업은 다음과 같다.

- 차트의 추세, 지지/저항, 거래량 분석
- RSI, MACD, 볼린저 밴드, 거래량 해석
- 시장 컨텍스트 기반 핵심 판단 근거와 리스크 요인 정리
- 뉴스가 실제 수집된 경우에만 제목과 URL 기반 뉴스 맥락 판단
- Reddit 게시글이 실제 수집된 경우에만 원문 기반 소셜 심리 판단
- 최종 신호를 매수/매도/보유 중 하나로 제시

응답 JSON 필드:

| 필드 | 의미 |
|---|---|
| `signal` | 매수/매도/보유 |
| `confidence` | 0.0~1.0 신뢰도 |
| `reason` | 한국어 분석 근거 |
| `key_drivers` | 핵심 판단 근거 리스트 |
| `risk_factors` | 주의할 리스크 리스트 |
| `technical_summary` | 코드가 붙여 넣는 기술 지표 요약 |
| `market_context_summary` | 코드가 붙여 넣는 시장 컨텍스트 |
| `analysis_sources` | 기본 `["시장 컨텍스트", "기술 지표"]`; 뉴스가 실제 수집된 경우 `"뉴스"` 추가, Reddit 게시글이 실제 수집된 경우 `"소셜 심리"` 추가 |

### 실패 처리

| 상황 | 동작 |
|---|---|
| Gemini 모델 초기화 실패 | 기본 결과 `NEUTRAL`, confidence 0.0 반환 |
| 빈 종목 코드 | "종목 코드를 입력하세요." |
| 가격 데이터 없음 | "시장 데이터를 찾을 수 없습니다." |
| 차트 생성 실패 | 이미지 없이 텍스트만 Gemini에 전달 |
| 뉴스 데이터 없음 | 뉴스 데이터 미사용 문구를 넣고 `analysis_sources`에서 `"뉴스"` 제외 |
| Reddit 데이터 없음 | 소셜 데이터 미사용 문구를 넣고 `analysis_sources`에서 `"소셜 심리"` 제외 |
| Gemini JSON 파싱 실패 | `raw_text`를 남기고 reason에 파싱 실패 메시지 |

## 3. AutoML

### 기능 목적

AutoML은 전략 자체를 새로 발명하는 기능이라기보다, 현재 코드 기준으로 MACD+RSI 전략의 파라미터 조합을 유전자 알고리즘으로 탐색해 Sharpe Ratio가 가장 높은 조합을 찾는 기능이다.

### 진입 경로

- 대시보드 탭: `dashboard/app.py`의 AutoML 영역
- 데이터 보조: `src/optimization/automl_support.py`
- 최적화기: `src/optimization/genetic.py`
- 평가기: `src/optimization/evaluator.py`

### UI 설정값

| UI 입력 | 기본값 | 실제 사용 여부 |
|---|---:|---|
| Population Size | 50 | 사용 |
| Generations | 20 | 사용 |
| Mutation Rate | 0.2 | 사용 |
| Target Strategy | MA Crossover/RSI/MACD/Bollinger 선택 | 현재 실제 최적화에는 전달되지 않음 |
| Test Symbol | `005930` | 가격 데이터 조회에 사용 |

중요: UI에는 여러 Target Strategy 선택지가 있지만, 현재 `GeneticOptimizer.evolve()`는 항상 evaluator에 `strategy_type="MACD_RSI"`를 넘긴다. 따라서 실제 AutoML 대상은 MACD+RSI 하나다.

### 가격 데이터 조회

`download_automl_price_history()`가 yfinance 데이터를 가져온다.

| 입력 | 처리 |
|---|---|
| 빈 문자열 | 빈 DataFrame과 "종목 코드를 입력하세요." |
| 숫자형 한국 종목 | `.KS`, `.KQ` 순서로 재시도 |
| 영문 티커 | 대문자로 변환해 그대로 조회 |
| 기간 | 기본 1년 |
| 캐시 | `.cache/yfinance`로 yfinance timezone cache 고정 |

### 유전자 표현

하나의 개체는 다음 6개 정수 파라미터 리스트다.

```text
[fast_ema, slow_ema, signal_ema, rsi_window, rsi_lower, rsi_upper]
```

범위:

| 파라미터 | 범위 | 의미 |
|---|---:|---|
| Fast EMA | 5~20 | MACD 빠른 EMA |
| Slow EMA | 21~60 | MACD 느린 EMA |
| Signal | 5~15 | MACD signal EMA |
| RSI Window | 10~30 | RSI 계산 기간 |
| RSI Lower | 20~40 | 매수 RSI 하단 기준 |
| RSI Upper | 60~80 | 매도 RSI 상단 기준 |

### 유전 알고리즘 구성

DEAP를 사용한다.

| 구성 | 구현 |
|---|---|
| Fitness | 최대화, `FitnessMax(weights=(1.0,))` |
| 개체 | 6개 파라미터 list |
| 초기화 | 각 파라미터를 지정 범위에서 랜덤 생성 |
| 교차 | `tools.cxTwoPoint` |
| 변이 | `tools.mutUniformInt` |
| 선택 | tournament selection, `tournsize=3` |
| 교차 확률 | 0.5 |
| 변이 확률 | UI의 mutation rate |
| 통계 | 세대별 avg/min/max fitness |
| Hall of Fame | 최고 개체 1개 |

### MACD+RSI 전략 평가

`StrategyEvaluator._evaluate_macd_rsi()`의 동작:

1. 파라미터를 정수로 변환한다.
2. 제약 조건을 확인한다.
3. MACD와 RSI를 계산한다.
4. 매수/매도 조건을 만든다.
5. 하루 전 신호를 다음 날 포지션에 반영한다.
6. 수수료를 반영한 전략 일간 수익률을 계산한다.
7. 연율화 Sharpe Ratio를 fitness로 반환한다.

제약 조건:

| 조건 | 위반 시 |
|---|---|
| `fast >= slow` | fitness -999.0 |
| `fast < 2` 또는 `slow < 5` | fitness -999.0 |
| `rsi_lower >= rsi_upper` | fitness -999.0 |
| DataFrame empty | fitness -9999.0 |
| 미지원 strategy type | fitness -9999.0 |

매매 조건:

| 신호 | 조건 |
|---|---|
| Buy | `MACD > Signal` 그리고 `RSI < rsi_lower` |
| Sell | `MACD < Signal` 또는 `RSI > rsi_upper` |
| 포지션 | long-only, 현금/공매도 모델 없음 |

수수료:

- `StrategyEvaluator(initial_capital=10000000, fee=0.0015)`
- 진입/청산일 수익률에 `(1 - fee)`를 곱하는 단순 방식

Fitness:

```text
Sharpe = mean(strategy_return) / std(strategy_return) * sqrt(252)
```

표준편차가 0이면 0.0을 반환한다.

### 결과

대시보드에는 다음이 표시된다.

- Best Fitness Score
- Best Parameters
- Fitness Evolution line chart
- resolved yfinance symbol

Best Parameters는 고정 label로 표시된다.

```text
Fast EMA
Slow EMA
Signal
RSI Window
RSI Lower
RSI Upper
```

### 현재 한계

- UI의 Target Strategy 선택값이 최적화기에 연결되어 있지 않다.
- 실제 전략은 MACD_RSI 하나다.
- 평가 대상은 단일 종목의 1년 가격 데이터다.
- 거래 비용 모델은 단순 수수료 반영이며 슬리피지, 세금, 체결 실패는 없다.
- walk-forward 검증이 아니라 같은 데이터 안에서 파라미터를 찾는 구조다.
- 과최적화 위험이 높으므로 실전 적용 전 별도 검증이 필요하다.

## 4. Stress Test

### 기능 목적

Stress Test는 현재 포트폴리오 또는 사용자가 직접 입력한 포트폴리오가 과거 위기 구간에서 어느 정도 손실을 볼 수 있었는지 추정하는 기능이다.

### 진입 경로

- 대시보드 탭: `dashboard/app.py`의 Stress Test 영역
- 입력 보조: `dashboard/stress_helpers.py`
- 핵심 엔진: `src/analysis/stress.py`

### 입력 방식

수동 입력:

```text
AAPL:0.3
MSFT:0.3
GOOGL:0.4
```

기존 포트폴리오:

- `load_state("KR")`에서 상태 데이터를 읽는다.
- `high_water_marks`에 있는 symbol을 사용한다.
- 숫자형 symbol은 `.KS`를 붙인다.
- 모든 보유 종목에 동일 비중 `1 / 종목 수`를 부여한다.

현재 UI는 비중 합계가 1.0에서 크게 벗어나도 실행 자체를 막지 않고 warning만 보여준다.

### 시나리오

| 시나리오 key | 구간 | 설명 | 데이터 실패 시 프록시 |
|---|---|---|---:|
| `2008_Financial_Crisis` | 2008-09-01 ~ 2008-11-30 | Lehman Brothers Bankruptcy | -30% |
| `2020_Covid_Crash` | 2020-02-19 ~ 2020-03-23 | Pandemic onset | -34% |
| `2022_Inflation_Shock` | 2022-01-01 ~ 2022-10-14 | Aggressive Rate Hikes | -25% |

### 시뮬레이션 방식

`simulate_scenario(portfolio, total_value, scenario_name)`의 흐름:

1. 시나리오 key로 기간을 찾는다.
2. 포트폴리오의 각 종목에 대해 yfinance `download()`를 호출한다.
3. 시나리오 시작 구간의 첫 종가와 마지막 종가를 비교한다.
4. 종목별 수익률을 계산한다.
5. 다운로드 실패, 빈 데이터, 종가 2개 미만이면 시나리오 프록시 수익률을 적용한다.
6. 포트폴리오 수익률은 `sum(weight * asset_return)`으로 계산한다.
7. 손익 금액은 `total_value * portfolio_return`으로 계산한다.

수식:

```text
asset_return = (last_close - first_close) / first_close
portfolio_return = Σ(weight_i * asset_return_i)
total_loss_amount = total_value * portfolio_return
```

주의: 변수명은 `total_loss_amount`지만 양수 시 이익, 음수 시 손실을 의미한다.

### 리스크 지표 계산 함수

`calculate_risk_metrics()`는 별도 함수로 존재한다.

| 지표 | 계산 |
|---|---|
| VaR_95 | 수익률의 5 percentile |
| VaR_99 | 수익률의 1 percentile |
| CVaR_95 | VaR_95 이하 손실의 평균 |
| Max_Drawdown | 누적 수익률 기준 peak 대비 최저 drawdown |

현재 대시보드 Stress Test 결과 화면은 이 리스크 지표 함수를 직접 호출하지 않고, 시나리오 수익률과 손실액 중심으로 보여준다.

### 결과 화면

- Portfolio Return
- Estimated Loss
- 종목별 수익률 details
- 프록시 사용 여부와 notes
- 종목별 수익률 bar chart
- 위험 판정

위험 판정:

| 포트폴리오 수익률 | 화면 판정 |
|---:|---|
| -20% 미만 | 고위험 |
| -10% 미만 | 중위험 |
| 그 외 | 저위험 |

### 현재 한계

- 위기 기간의 단순 시작/끝 수익률만 사용한다.
- 시나리오 도중 최대 낙폭이나 경로 의존 손실은 대시보드에 반영되지 않는다.
- 종목별 위기 당시 상장 여부나 티커 변경 이슈는 yfinance 데이터 품질에 의존한다.
- 한국 종목은 과거 위기 구간 데이터가 부족할 수 있고, 이 경우 프록시 수익률이 들어간다.
- 비중 합계가 1.0이 아니어도 계산은 그대로 진행된다.

## 5. Smart Money

### 기능 목적

Smart Money 기능은 ICT/SMC 관점의 시장 구조, 구조 돌파, Fair Value Gap, Order Block, liquidity sweep, 최근 캔들 패턴을 5분봉/1시간봉/일봉에서 동시에 분석해 BUY/SELL/HOLD 신호를 만드는 기능이다.

현재 구현 범위는 실시간 호가/order flow가 아니라 OHLCV 기반 SMC 패턴 점수화다. confidence도 모델 확률이 아니라 규칙 기반 score에서 penalty를 차감한 운용 신뢰도다.

핵심 방향은 "자동 주문"이 아니라 "판단 보조 신호"다. 자동매매 연동도 기본값은 꺼져 있고, 켜더라도 SELL 후보 제외나 경고 중심으로 제한되어 있다.

### 진입 경로

대시보드:

- `dashboard/components/smart_money_tab.py`
- `render_smart_money_tab()`

분석 엔진:

- 데이터 수집: `src/analysis/timeframes.py`
- 패턴 리포트: `src/analysis/smart_money/report.py`
- 스윙/구조: `src/analysis/smart_money/swings.py`
- FVG: `src/analysis/smart_money/fvg.py`
- Order Block: `src/analysis/smart_money/order_blocks.py`
- Liquidity Sweep: `src/analysis/smart_money/liquidity.py`
- 캔들 패턴: `src/analysis/candlestick_patterns.py`
- 설정 변환: `src/analysis/smart_money/config.py`
- 신호 결합: `src/analysis/smart_money/signal.py`
- 차트 주석: `src/analysis/smart_money/chart.py`
- 알림: `src/analysis/smart_money/alerts.py`

자동매매 연동:

- `src/trader/auto_trader.py`
- `config/trading.yaml`의 `smart_money` 설정

CLI/검증:

- `scripts/run_smart_money_analysis.py`
- `scripts/run_smart_money_backtest.py`
- `src/backtest/smart_money_engine.py`

### 대시보드 입력

| 입력 | 설명 |
|---|---|
| 종목 입력 | 쉼표 또는 줄바꿈으로 여러 종목 입력 |
| 시장 | KR 또는 US |
| 거래소 | US는 NASD/NYSE/AMEX 선택, KR은 KRX 고정 |

`parse_symbol_input()`은 입력을 대문자로 변환하고 중복을 제거한다.

### 멀티타임프레임 데이터 수집

표준 timeframe:

| Enum | 문자열 key | 의미 |
|---|---|---|
| `Timeframe.MINUTE_5` | `5m` | 5분봉 |
| `Timeframe.HOUR_1` | `1h` | 1시간봉 |
| `Timeframe.DAY_1` | `1d` | 일봉 |

KR 시장:

- KIS 1분봉을 가져온다.
- 1분봉을 5분봉으로 resample한다.
- 1분봉을 60분봉으로 resample한다.
- 일봉은 KIS 일봉 API로 가져온다.

US 시장:

- KIS 5분봉을 가져온다.
- KIS 60분봉을 우선 가져온다.
- 60분봉 실패 시 5분봉을 60분으로 resample한다.
- 일봉은 yfinance history 1년 데이터를 fallback으로 가져온다.

resample 규칙:

| 컬럼 | 집계 |
|---|---|
| open | first |
| high | max |
| low | min |
| close | last |
| volume | sum |

각 timeframe 실패는 전체 실패로 바로 번지지 않고 `TimeframeData.error`에 격리된다. 성공한 frame만 `dataset.successful_ohlcv()`로 분석에 들어간다.

### OHLCV 정규화와 검증

패턴 리포트는 입력 DataFrame을 표준 OHLCV 계약에 맞춘다.

- DatetimeIndex 필요
- 컬럼은 소문자 `open`, `high`, `low`, `close`, `volume`
- 숫자 dtype 필요
- 비정상 캔들 차단: `high < max(open, close)` 또는 `low > min(open, close)`이면 오류
- 데이터 부족이나 컬럼 부족은 가능한 경우 warning으로 남긴다.

### 패턴 1: 스윙 하이/스윙 로우

기본 window:

```text
left = 2
right = 2
```

스윙 하이:

```text
현재 high >= 좌우 2개 high
그리고 최소 한쪽은 현재 high가 엄격히 큼
```

스윙 로우:

```text
현재 low <= 좌우 2개 low
그리고 최소 한쪽은 현재 low가 엄격히 작음
```

마지막 `right`개 캔들은 아직 확정 전으로 보고 탐지하지 않는다. 따라서 lookahead bias를 줄이는 구조다.

### 패턴 2: 시장 구조

시장 구조는 최근 스윙 pair를 기준으로 판정한다.

| 구조 | 조건 |
|---|---|
| BULLISH | 최근 swing high가 상승하고, 최근 swing low도 상승 |
| BEARISH | 최근 swing high가 하락하고, 최근 swing low도 하락 |
| RANGE | 위 조건이 아니거나 스윙이 부족 |

최소 스윙 수:

```text
MIN_SWINGS_FOR_STRUCTURE = 3
```

최근 구조 판정에 사용하는 pair 수:

```text
RECENT_SWING_PAIRS = 2
```

전체 히스토리의 단조 상승/하락이 아니라 최근 구조만 본다.

### 패턴 3: BOS / CHOCH

구조 돌파는 확정된 과거 스윙 레벨을 종가가 돌파하는지 본다.

| 이벤트 | 조건 |
|---|---|
| 상방 돌파 | `close > swing_high.price` |
| 하방 이탈 | `close < swing_low.price` |

BOS와 CHOCH 구분:

| 현재 구조 | 돌파 방향 | 분류 |
|---|---|---|
| BEARISH | 상방 돌파 | CHOCH |
| 그 외 | 상방 돌파 | BOS |
| BULLISH | 하방 이탈 | CHOCH |
| 그 외 | 하방 이탈 | BOS |

각 bar 시점에서 `bar_index < i`인 과거 스윙만으로 현재 구조를 계산한다. 같은 스윙 레벨은 한 번 돌파되면 재사용하지 않는다.

선택 필터:

```text
patterns.displacement_atr_multiplier > 0
```

이 값이 켜져 있으면 구조 돌파 캔들의 body가 해당 시점 ATR의 `multiplier`배 이상인 경우만 유효 구조 돌파로 유지한다. 기본값은 `0.0`이라 기존 동작처럼 필터를 적용하지 않는다.

### 패턴 4: Fair Value Gap

FVG는 3개 연속 캔들에서 캔들 `i-2`와 캔들 `i` 사이에 겹치지 않는 가격 구간이 있을 때 만든다.

Bullish FVG:

```text
high[i-2] < low[i]
gap = [high[i-2], low[i]]
```

Bearish FVG:

```text
low[i-2] > high[i]
gap = [high[i], low[i-2]]
```

필터:

```text
gap_size / close[i] >= 0.001
```

즉 기본 최소 갭 비율은 0.1%다.

FVG 상태:

| 상태 | Bullish 기준 | Bearish 기준 |
|---|---|---|
| OPEN | 아직 gap 범위 진입 없음 | 아직 gap 범위 진입 없음 |
| TOUCHED | 이후 캔들의 low가 gap 범위 안으로 진입 | 이후 캔들의 high가 gap 범위 안으로 진입 |
| FILLED | 이후 캔들의 low가 gap lower 이하 | 이후 캔들의 high가 gap upper 이상 |

상태 갱신은 FVG 생성 캔들 이후 timestamp만 본다.

### 패턴 5: Order Block

Order Block은 BOS 직전 lookback 구간의 마지막 반대색 캔들로 만든다.

기본 lookback:

```text
DEFAULT_LOOKBACK = 10
```

탐지 규칙:

| BOS 방향 | 후보 캔들 | OB 방향 |
|---|---|---|
| Bullish BOS | 직전 10개 안의 마지막 음봉 | Bullish OB |
| Bearish BOS | 직전 10개 안의 마지막 양봉 | Bearish OB |

현재 구현은 BOS만 Order Block 생성 기준으로 사용하고, CHOCH는 OB 생성 기준에서 제외한다.

Zone:

```text
lower = 후보 캔들의 low
upper = 후보 캔들의 high
```

강도:

```text
기본 strength = 1.0
BOS 캔들 거래량 >= 직전 20개 평균 거래량이면 +0.25
```

상태:

| 상태 | 의미 |
|---|---|
| FRESH | 생성 후 zone 재진입 없음 |
| MITIGATED | 가격이 zone에 재진입 |
| INVALIDATED | 가격이 zone 반대편을 돌파 |

Bullish OB는 이후 low가 zone lower 아래로 내려가면 invalidated다. Bearish OB는 이후 high가 zone upper 위로 올라가면 invalidated다.

### 패턴 6: Liquidity Sweep

Liquidity sweep은 확정된 과거 swing level을 고가/저가가 찌른 뒤 종가가 다시 레벨 안쪽으로 돌아오는 이벤트다.

Bearish liquidity sweep:

```text
high > swing_high.price * (1 + tolerance_pct)
close < swing_high.price
```

Bullish liquidity sweep:

```text
low < swing_low.price * (1 - tolerance_pct)
close > swing_low.price
```

기본 tolerance:

```text
patterns.liquidity_sweep_tolerance_pct = 0.001
```

5분봉에서 최신 liquidity sweep은 trigger 보조 점수로 반영된다.

### 패턴 7: 최근 캔들 패턴

캔들 패턴은 외부 TA 라이브러리 없이 직접 계산한다.

지원 패턴:

| 패턴 | 방향 | 조건 요약 |
|---|---|---|
| bullish_engulfing | BULLISH | 이전 음봉, 현재 양봉, 현재 몸통이 이전 몸통을 감쌈 |
| bearish_engulfing | BEARISH | 이전 양봉, 현재 음봉, 현재 몸통이 이전 몸통을 감쌈 |
| hammer | BULLISH | 아래꼬리 >= 몸통 2배, 위꼬리 < 몸통 |
| shooting_star | BEARISH | 위꼬리 >= 몸통 2배, 아래꼬리 < 몸통 |
| doji | NEUTRAL | 몸통 / 전체 range <= 0.1 |
| strong_bullish | BULLISH | 몸통 / range >= 0.7, 양봉 |
| strong_bearish | BEARISH | 몸통 / range >= 0.7, 음봉 |

단일 캔들 패턴은 한 캔들당 하나만 잡는다. 우선순위는 doji, hammer, shooting_star, strong 순서다. 리포트에는 최근 5개 캔들 구간의 패턴만 유지한다.

### TimeframePatternReport

각 timeframe은 다음 정보를 가진 리포트로 변환된다.

| 필드 | 의미 |
|---|---|
| `latest_close` | 최신 종가 |
| `market_structure` | BULLISH/BEARISH/RANGE |
| `recent_swing_high` | 최근 스윙 고점 |
| `recent_swing_low` | 최근 스윙 저점 |
| `swings` | 전체 스윙 목록 |
| `structure_breaks` | BOS/CHOCH 목록 |
| `open_fvgs` | OPEN FVG |
| `touched_fvgs` | TOUCHED FVG |
| `filled_fvgs` | FILLED FVG |
| `fresh_order_blocks` | FRESH OB |
| `mitigated_order_blocks` | MITIGATED OB |
| `invalidated_order_blocks` | INVALIDATED OB |
| `liquidity_sweeps` | Liquidity sweep 목록 |
| `recent_candle_patterns` | 최근 캔들 패턴 |
| `summary` | 개수 집계 |
| `warnings` | 데이터 부족/컬럼 부족 경고 |

### 신호 점수 설정

`SignalConfig` 기본값:

| 설정 | 기본값 | 의미 |
|---|---:|---|
| buy_threshold | 0.50 | BUY 최소 총점 |
| sell_threshold | -0.50 | SELL 최대 총점 |
| min_confidence | 0.55 | 최종 신호 최소 신뢰도 |
| min_confirming_timeframes | 2 | 같은 방향 확인 timeframe 최소 수 |
| daily weight | 0.40 | 일봉 가중치 |
| hourly weight | 0.35 | 1시간봉 가중치 |
| minute_5 weight | 0.25 | 5분봉 가중치 |
| stale_pattern_penalty_per_bar | 0.01 | 오래된 패턴 penalty |
| max_patterns_per_type | 5 | 최근 패턴 반영 개수 제한 |
| conflict_penalty | 0.20 | 상위 timeframe 방향 충돌 penalty |
| insufficient_data_penalty | 0.15 | 데이터 부족 penalty |
| invalidation_proximity_penalty | 0.05 | 무효화선이 너무 가까울 때 penalty |

`config/trading.yaml`의 `smart_money.signal`에서 위 값을 조정할 수 있다.

### 패턴 탐지 설정

`config/trading.yaml`의 `smart_money.patterns` 기본값:

| 설정 | 기본값 | 의미 |
|---|---:|---|
| swing_left | 2 | 스윙 탐지 왼쪽 비교 캔들 수 |
| swing_right | 2 | 스윙 탐지 오른쪽 비교 캔들 수 |
| fvg_min_gap_pct | 0.001 | FVG 최소 gap 비율 |
| order_block_lookback | 10 | BOS 직전 OB 후보 탐색 범위 |
| liquidity_sweep_tolerance_pct | 0.001 | liquidity sweep 레벨 초과 허용 기준 |
| displacement_atr_multiplier | 0.0 | 구조 돌파 body/ATR 최소 배수, 0이면 비활성 |
| atr_period | 14 | displacement filter용 ATR 기간 |

### timeframe별 점수화

일봉은 방향성 큰 그림을 담당한다.

| 컴포넌트 | 조건 | 점수 |
|---|---|---:|
| market_structure | BULLISH | `+0.40 * 0.75 = +0.30` |
| market_structure | BEARISH | `-0.40 * 0.75 = -0.30` |
| latest structure break | bullish | `+0.40 * 0.25 = +0.10` |
| latest structure break | bearish | `-0.40 * 0.25 = -0.10` |

1시간봉은 setup을 담당한다.

| 컴포넌트 | 조건 | 점수 |
|---|---|---:|
| best Order Block | MITIGATED | `±0.35 * 4/7 = ±0.20` |
| best Order Block | FRESH | `±0.35 * 3/7 = ±0.15` |
| best FVG | TOUCHED | `±0.35 * 3/7 = ±0.15` |
| best FVG | OPEN | `±0.35 * 2/7 = ±0.10` |

5분봉은 trigger를 담당한다.

| 컴포넌트 | 조건 | 점수 |
|---|---|---:|
| latest structure break | bullish/bearish | `±0.25 * 0.60 = ±0.15` |
| latest liquidity sweep | bullish/bearish | `±0.25 * 0.20 = ±0.05` |
| best candle pattern | bullish/bearish | `±0.25 * 0.40 = ±0.10` |

방향이 bullish이면 양수, bearish이면 음수다.

Order Block 점수는 OB `strength`를 곱한다. 기본 strength는 1.0이고, BOS 캔들 거래량이 직전 평균 이상이면 1.25가 되어 해당 OB 기여 점수가 커진다.

### 최종 점수와 confidence

전체 score:

```text
score = 모든 SignalContribution.score 합계
```

기본 max score budget:

```text
max_abs_score = daily_weight + hourly_weight + minute_5_weight = 1.0
```

초기 confidence:

```text
raw_confidence = min(1.0, abs(score) / max_abs_score)
```

최종 confidence:

```text
confidence = clamp(raw_confidence - penalties, 0.0, 1.0)
```

Penalty 항목:

| penalty | 조건 |
|---|---|
| conflict penalty 0.20 | 일봉과 1시간봉 방향이 명확히 반대 |
| insufficient data 0.15 | timeframe 리포트 없음 또는 latest_close 없음 |
| insufficient data 절반 | 리포트 warning 존재 |
| stale penalty | 관련 패턴이 최신 bar에서 멀수록 `age * 0.01` |
| invalidation proximity 0.05 | 진입 zone 폭의 0.5배 이하로 무효화선이 가까움 |

### BUY/SELL/HOLD 게이트

BUY 조건:

```text
score >= 0.50
confidence >= 0.55
bullish confirming timeframes >= 2
일봉/1시간봉 방향 충돌 없음
핵심 timeframe 데이터 부족이 2개 미만
```

SELL 조건:

```text
score <= -0.50
confidence >= 0.55
bearish confirming timeframes >= 2
일봉/1시간봉 방향 충돌 없음
핵심 timeframe 데이터 부족이 2개 미만
```

그 외는 HOLD다.

HOLD 사유 예시:

- confidence가 최소 기준보다 낮음
- bullish/bearish 확인 timeframe 수 부족
- 상위 timeframe 방향 충돌
- 핵심 timeframe 데이터 부족

### Entry zone, invalidation, take profit

BUY일 때:

1. 1시간봉 bullish Order Block이 있으면 그 zone을 entry zone으로 사용한다.
2. 없으면 1시간봉 bullish FVG zone을 사용한다.
3. invalidation level은 zone lower다.

SELL일 때:

1. 1시간봉 bearish Order Block이 있으면 그 zone을 entry zone으로 사용한다.
2. 없으면 1시간봉 bearish FVG zone을 사용한다.
3. invalidation level은 zone upper다.

HOLD이면 entry zone과 invalidation은 없다.

Take profit 후보:

- BUY: 최신가보다 위에 있는 최근 swing high
- SELL: 최신가보다 아래에 있는 최근 swing low
- timeframe 우선순위는 1d, 1h, 5m 모두 확인하고 중복 제거 후 정렬

Risk level:

| 조건 | risk_level |
|---|---|
| confidence >= 0.75 그리고 warning 없음 | LOW |
| confidence >= 0.55 | MEDIUM |
| 그 외 | HIGH |

### 대시보드 출력

결과 표 컬럼:

| 컬럼 | 의미 |
|---|---|
| symbol | 종목 |
| signal | BUY/SELL/HOLD 또는 ERROR |
| confidence | 신뢰도 |
| daily structure | 일봉 구조 |
| 1h setup | 1시간봉 FVG/OB 활성 개수 |
| 5m trigger | 5분봉 구조 돌파/캔들 패턴 개수 |
| entry zone | 진입 후보 zone |
| invalidation | 무효화 가격 |
| 주요 reason | 첫 번째 판단 근거 또는 warning |

상세 화면:

- 5분봉/1시간봉/일봉 탭
- Plotly candlestick chart
- Swing High/Low marker
- FVG rectangle
- Order Block rectangle
- Entry zone overlay
- Invalidation line
- 신호/신뢰도/리스크 annotation
- timeframe별 summary count

### 알림 정책

`config/trading.yaml`의 기본 설정:

```yaml
smart_money:
  enabled: false
  mode: "advisory"
  buy_score_bonus: 0.0
  signal:
    buy_threshold: 0.50
    sell_threshold: -0.50
    min_confidence: 0.55
    min_confirming_timeframes: 2
    weights:
      daily: 0.40
      hourly: 0.35
      minute_5: 0.25
    stale_pattern_penalty_per_bar: 0.01
    max_patterns_per_type: 5
    conflict_penalty: 0.20
    insufficient_data_penalty: 0.15
    invalidation_proximity_penalty: 0.05
  patterns:
    swing_left: 2
    swing_right: 2
    fvg_min_gap_pct: 0.001
    order_block_lookback: 10
    liquidity_sweep_tolerance_pct: 0.001
    displacement_atr_multiplier: 0.0
    atr_period: 14
  alerts:
    enabled: false
    provider: "kakao"
    cooldown_minutes: 30
    min_confidence: 0.60
    notify_on:
      - "BUY"
      - "SELL"
    repeat_on_confidence_jump: true
    confidence_jump_threshold: 0.15
```

알림 provider:

- Kakao
- Telegram

알림 조건:

| 조건 | 설명 |
|---|---|
| alerts.enabled | true여야 함 |
| signal | `notify_on`에 포함된 BUY/SELL이어야 함 |
| confidence | `min_confidence` 이상이어야 함 |
| cooldown | 같은 symbol/timeframe의 중복 알림은 cooldown 동안 막음 |
| signal changed | 이전 신호와 달라지면 알림 |
| confidence jump | cooldown 이후 confidence가 threshold 이상 상승하면 재알림 |

알림 상태는 기본적으로 `data/smart_money_alert_state.json`의 `smart_money_alerts` namespace에 저장된다.

### 자동매매 연동

자동매매는 `AutoTrader` 초기화 시 `config/trading.yaml`의 `smart_money`를 읽는다.

mode:

| mode | 현재 의미 |
|---|---|
| advisory | Smart Money 신호를 참고 정보/로그로만 사용 |
| filter | 신규 매수 후보 필터와 BUY bonus에 사용 |
| execute | 설정값은 허용하지만 실제 주문 실행에는 연결하지 않고 참고 로그 취급 |

`execute`는 이름만 허용된 호환 값이며 실제 자동 주문 실행 모드가 아니다. Smart Money 신호만으로 신규 주문/청산을 실행하지 않는다.

후보 필터 흐름:

1. selector 또는 ML 필터가 만든 후보 DataFrame을 받는다.
2. Smart Money가 꺼져 있으면 그대로 반환한다.
3. 켜져 있으면 후보별로 Smart Money signal resolver를 호출한다.
4. 후보 row에 `smart_money_signal`, `smart_money_confidence`, `smart_money_score`를 붙인다.
5. mode가 `filter`이고 신호가 SELL이면 신규 매수 후보에서 제외한다.
6. mode가 `filter`이고 신호가 BUY이며 `buy_score_bonus > 0`이고 기존 selector score가 1.0 이상이면 score에 bonus를 더한다.
7. Smart Money 분석 실패 시 해당 후보는 유지하고 `smart_money_error`를 남긴다.

중요한 안전장치:

- Smart Money BUY만으로 score가 낮은 후보를 단독 매수 트리거로 만들지 않도록 `SMART_MONEY_BUY_BONUS_MIN_SCORE = 1.0`이 있다.
- Smart Money SELL은 신규 매수 후보 제외에는 쓸 수 있지만, 보유 종목 자동 청산에는 쓰지 않는다.
- 보유 종목에서 Smart Money SELL이 나오면 warning과 notification만 남기고 "자동 청산은 실행하지 않습니다."라고 처리한다.

보유 종목 경고:

- 손절/트레일링/최소점수 exit이 먼저 실행된다.
- 기존 exit이 실행되지 않은 경우에만 Smart Money SELL 경고를 확인한다.
- Smart Money SELL이어도 `_place_order()`로 매도하지 않는다.

### CLI 분석 리포트

`scripts/run_smart_money_analysis.py`는 대시보드 없이 Smart Money 분석 리포트를 만든다.

기능:

- `--symbols AAPL,MSFT`
- `--market US|KR`
- `--exchange NASD`
- `--format json|markdown`
- `--fixture` 또는 `--no-network`로 네트워크 없는 합성 데이터 분석
- 결과는 기본적으로 `reports/smart_money_YYYYMMDD.json|md`

Markdown 리포트에는 signal, confidence, entry, invalidation, reasons, warnings, timeframe summary가 들어간다.

### Smart Money 백테스트

`src/backtest/smart_money_engine.py`는 Smart Money 신호를 walk-forward 방식으로 long-only 검증한다.

백테스트 핵심:

- 현재 시점까지의 데이터 window만 사용해 신호 계산
- BUY가 나오면 다음 캔들 open에 매수
- SELL이 나오면 다음 캔들 open에 매도
- invalidation level 터치 시 청산
- 최대 보유 캔들 수 도달 시 청산
- 데이터 종료 시 남은 포지션 종가 청산
- commission, slippage, position size 반영

백테스트 지표:

| 지표 | 의미 |
|---|---|
| total_trades | 완료 거래 수 |
| win_rate | 순손익 양수 거래 비율 |
| average_return | 거래별 평균 수익률 |
| max_drawdown | equity curve 최대 낙폭 |
| profit_factor | 총이익 / 총손실 |
| signal_coverage | BUY/SELL 신호 비율 |
| signal_counts | BUY/SELL/HOLD 개수 |
| signal_ratios | BUY/SELL/HOLD 비율 |

CLI:

```bash
python scripts/run_smart_money_backtest.py --symbols AAPL,MSFT --market US --period 1y --format markdown
```

### Smart Money 현재 한계

- ICT/SMC 패턴은 해석이 사람마다 다르므로, 이 프로젝트는 YAML로 조정 가능한 코드 정의만 사용한다.
- 실시간 체결/호가 기반 order flow가 아니라 OHLCV 기반 패턴 분석이다.
- equal high/low cluster, premium/discount, session kill zone은 아직 구현하지 않았다.
- confidence는 통계적 승률이나 확률이 아니라 규칙 기반 score 신뢰도다.
- 일봉/1시간봉/5분봉 중 일부가 실패하면 신호 confidence가 크게 낮아진다.
- 기본 설정상 Smart Money 자동매매 연동은 꺼져 있다.
- `execute` mode는 아직 실제 주문 실행 모드가 아니다.
- 알림은 분석 보조이며 자동주문 알림이 아니다.

## 기능별 의사결정 성격 비교

| 기능 | 의사결정 방식 | 정량 지표 비중 | LLM 사용 | 실제 주문 영향 |
|---|---|---:|---|---|
| 성장주 탐색 | 재무 필터 + 점수화 + 선택적 뉴스 감성 | 높음 | 없음 | 직접 없음 |
| 심층 분석 | 기술 요약 + 차트 이미지 + 소셜을 Gemini가 해석 | 중간 | 있음 | 직접 없음 |
| AutoML | 유전 알고리즘으로 Sharpe 최대화 | 매우 높음 | 없음 | 직접 없음 |
| Stress Test | 과거 위기 구간 수익률로 충격 계산 | 매우 높음 | 없음 | 직접 없음 |
| Smart Money | SMC 패턴 점수 + 게이트 + confidence penalty | 높음 | 없음 | 설정 시 후보 필터/경고에 제한적 영향 |

## 실무적으로 봐야 할 체크포인트

1. 성장주 탐색은 후보군이 고정되어 있으므로 "전체 시장 스캐너"로 오해하면 안 된다.
2. 심층 분석은 Gemini API와 가격/소셜 데이터 품질에 크게 의존한다.
3. AutoML은 현재 MACD_RSI 전용이며, UI의 전략 선택지는 아직 실제 최적화 대상 변경에 연결되어 있지 않다.
4. Stress Test는 시작/끝 수익률 기반이라 장중/중간 최대 손실을 대시보드에서 직접 보여주지는 않는다.
5. Smart Money는 가장 정교하지만 기본값은 비활성화이며, 자동 주문 실행이 아니라 판단 보조/필터/경고 중심이다.
6. 모든 기능은 데이터 결측 시 보수적으로 fallback하거나 warning을 남기는 구조지만, fallback 결과를 실제 투자 판단으로 바로 쓰면 안 된다.

## 관련 파일 목록

| 영역 | 파일 |
|---|---|
| 대시보드 탭 구성 | `dashboard/app.py` |
| 성장주 탐색 UI | `dashboard/components/growth_tab.py` |
| 성장주 탐색 엔진 | `src/analysis/growth_stock_finder.py` |
| 심층 분석 엔진 | `src/analysis/multimodal.py` |
| 차트 생성 | `src/analysis/chart.py` |
| 시장 데이터 | `src/analysis/market_data.py` |
| 소셜 감성 | `src/data/social.py` |
| AutoML 데이터 보조 | `src/optimization/automl_support.py` |
| AutoML GA | `src/optimization/genetic.py` |
| AutoML fitness 평가 | `src/optimization/evaluator.py` |
| Stress Test 엔진 | `src/analysis/stress.py` |
| Stress Test 입력 보조 | `dashboard/stress_helpers.py` |
| Smart Money 대시보드 | `dashboard/components/smart_money_tab.py` |
| Smart Money 데이터 수집 | `src/analysis/timeframes.py` |
| Smart Money 모델 | `src/analysis/smart_money/models.py` |
| Smart Money 스윙/구조 | `src/analysis/smart_money/swings.py` |
| Smart Money FVG | `src/analysis/smart_money/fvg.py` |
| Smart Money OB | `src/analysis/smart_money/order_blocks.py` |
| Smart Money Liquidity Sweep | `src/analysis/smart_money/liquidity.py` |
| Smart Money 리포트 | `src/analysis/smart_money/report.py` |
| Smart Money 신호 결합 | `src/analysis/smart_money/signal.py` |
| Smart Money 차트 | `src/analysis/smart_money/chart.py` |
| Smart Money 알림 | `src/analysis/smart_money/alerts.py` |
| Smart Money 자동매매 연동 | `src/trader/auto_trader.py` |
| Smart Money 설정 | `src/analysis/smart_money/config.py`, `config/trading.yaml` |
| Smart Money CLI 분석 | `scripts/run_smart_money_analysis.py` |
| Smart Money 백테스트 | `scripts/run_smart_money_backtest.py`, `src/backtest/smart_money_engine.py` |
