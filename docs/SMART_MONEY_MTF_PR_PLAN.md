# Smart Money Multi-Timeframe Analysis PR Plan

> 작성일: 2026-04-23  
> 목적: 5분봉, 1시간봉, 일봉을 함께 비교해 스윙 프랙탈, 오더블록, FVG, 캔들 패턴 기반으로 매수/매도/유지 타이밍을 판단하는 기능을 작은 PR 단위로 구현하기 위한 계획서  
> 원칙: 각 PR은 단독 리뷰와 단독 테스트가 가능해야 하며, 실거래 주문 실행과 분석 신호 출시는 분리한다.

## 0. 현재 상태 요약

현재 프로젝트에는 다음 기반이 이미 있다.

| 영역 | 현재 상태 | 주요 위치 |
|---|---|---|
| 일반 기술지표 전략 | 이동평균, RSI, MACD, 볼린저밴드 기반 `signal` 생성 가능 | `src/strategies/` |
| 단일 종목 심층 분석 | 6개월 가격, 차트 이미지, 소셜 데이터를 Gemini로 해석해 매수/매도/보유 반환 | `src/analysis/multimodal.py`, `dashboard/app.py` |
| 차트 생성 | `mplfinance` 기반 캔들차트 이미지 생성 | `src/analysis/chart.py` |
| 분봉 API | KIS `get_minute_price(symbol, interval, count)` 존재. 단, 현재 KR 분봉 구현은 `interval`을 query에 반영하지 않으므로 5분/60분은 1분봉 resample을 기본으로 봐야 한다. | `src/data/api_client.py` |
| 일봉 API | KIS `get_daily_price_history(symbol, start_date, end_date)` 존재. 현재 구현은 KR 일봉용이며 US 일봉은 yfinance fallback 또는 해외 일봉 API 추가가 필요하다. | `src/data/api_client.py` |
| 오더플로우 | 호가 불균형, 대량 주문, 매수/매도 압력 분석 존재 | `src/analysis/orderflow.py` |

아직 없는 부분은 다음이다.

- 5분봉, 1시간봉, 일봉을 같은 계약으로 정규화하는 멀티타임프레임 데이터 레이어
- 스윙 프랙탈, 시장구조(BOS/CHOCH), FVG, 오더블록 탐지기
- 각 타임프레임의 신호를 합산해 `BUY`, `SELL`, `HOLD`로 판정하는 엔진
- 패턴 근거를 차트와 대시보드에 표시하는 UI
- 패턴 기반 신호의 백테스트와 회귀 검증

## 1. 설계 원칙

1. **분석과 주문을 분리한다.**  
   Smart Money 기능은 우선 "판단 보조 신호"만 만든다. 실주문 연동은 마지막 PR에서 별도 feature flag로 다룬다.

2. **데이터 계약을 먼저 고정한다.**  
   탐지기는 KIS, yfinance, fixture 어느 곳에서 온 데이터든 동일한 OHLCV DataFrame만 받도록 한다.

3. **패턴 탐지는 순수 함수 중심으로 만든다.**  
   네트워크, Streamlit, LLM 의존성을 패턴 탐지 함수 내부에 넣지 않는다.

4. **신호는 설명 가능해야 한다.**  
   단순히 `BUY`만 반환하지 않고, 어떤 타임프레임에서 어떤 패턴이 몇 점을 만들었는지 함께 반환한다.

5. **타임프레임별 역할을 분리한다.**  
   일봉은 큰 방향, 1시간봉은 구조와 구간, 5분봉은 진입 타이밍으로 사용한다.

6. **테스트 fixture를 먼저 만든다.**  
   FVG, 오더블록, 스윙 프랙탈은 실데이터만으로는 경계 조건 검증이 어렵기 때문에 합성 OHLCV fixture를 사용한다.

## 2. 용어와 데이터 계약

### 2.1 신호 용어

| 값 | 의미 | 사용처 |
|---|---|---|
| `BUY` | 신규 매수 또는 추가 매수 후보 | 대시보드, 리포트, 선택적 주문 필터 |
| `SELL` | 청산 또는 비중 축소 후보 | 대시보드, 리포트, 선택적 주문 필터 |
| `HOLD` | 관망 또는 기존 포지션 유지 | 기본값 |

### 2.2 표준 OHLCV DataFrame

패턴 엔진은 다음 컬럼만 요구한다.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `datetime` 또는 DatetimeIndex | datetime | 캔들 시간 |
| `open` | float | 시가 |
| `high` | float | 고가 |
| `low` | float | 저가 |
| `close` | float | 종가 |
| `volume` | int/float | 거래량 |

정규화 규칙:

- 입력 컬럼이 `Open`, `High`, `Low`, `Close`, `Volume`이면 소문자 컬럼으로 변환한다.
- 시간은 오름차순으로 정렬한다.
- 중복 timestamp는 마지막 값을 사용한다.
- `high < max(open, close)` 또는 `low > min(open, close)`인 비정상 행은 제거하거나 오류로 처리한다.
- 패턴 탐지 함수는 최소 캔들 수를 만족하지 못하면 빈 결과와 `insufficient_data` reason을 반환한다.

### 2.3 Smart Money 패키지 구조

PR-02부터 Smart Money 탐지기는 단일 대형 파일이 아니라 패키지로 구성한다.

```text
src/analysis/smart_money/
  __init__.py
  models.py
  swings.py
  fvg.py
  order_blocks.py
  report.py
  signal.py
  chart.py
  alerts.py
```

원칙:

- `models.py`에는 public dataclass와 enum만 둔다.
- `swings.py`, `fvg.py`, `order_blocks.py`는 순수 탐지 함수만 포함한다.
- `report.py`는 여러 탐지 결과를 timeframe 단위 리포트로 묶는다.
- `signal.py`는 점수화와 최종 `BUY/SELL/HOLD` 판정만 담당한다.
- `chart.py`, `alerts.py`는 각각 시각화와 알림 연동을 담당한다.
- 외부 모듈은 가능한 한 `src.analysis.smart_money`의 public API를 import하고, 내부 파일 직접 의존을 줄인다.

## 3. PR 단위 계획

### PR-01. OHLCV 데이터 계약과 분봉 파서 보정

**목표**  
모든 후속 분석이 사용할 표준 OHLCV 계약을 만들고, 기존 KIS 분봉 파서가 `StockPrice` 모델과 맞지 않는 문제를 바로잡는다.

**구현 방법**

- 신규 파일 추가:
  - `src/analysis/ohlcv.py`
  - `tests/analysis/test_ohlcv.py`
  - `tests/fixtures/ohlcv_factory.py`
  - `tests/fixtures/ohlcv/`
- `src/analysis/ohlcv.py`에 다음 함수 구현:
  - `normalize_ohlcv_frame(df: pd.DataFrame) -> pd.DataFrame`
  - `stock_prices_to_ohlcv(prices: list[StockPrice]) -> pd.DataFrame`
  - `validate_ohlcv_frame(df: pd.DataFrame, min_rows: int = 1) -> tuple[bool, list[str]]`
  - `ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame`
- `src/data/api_client.py`의 `get_minute_price`에서 `StockPrice(date=...)`처럼 존재하지 않는 인자를 쓰는 부분을 `symbol=...`, `datetime=...`로 보정한다. 현재 KR/US 분봉 파서 모두 `symbol` 필수 인자도 누락되어 있으므로 `symbol=symbol`을 함께 전달한다.
- KR 분봉은 API가 날짜 없이 체결 시간만 줄 가능성이 있으므로, 현재 날짜와 `stck_cntg_hour`를 결합하되 장 종료 후 조회/전일 데이터 이슈는 별도 reason으로 기록한다.
- US 분봉은 `xymd + xhms`를 `datetime`으로 파싱한다.
- 후속 PR에서 공통 fixture를 재사용할 수 있도록 `tests/fixtures/` 구조를 이 PR에서 만든다. 별도 `conftest.py`가 필요하면 이 PR에 포함하되, global fixture 남용은 피한다.
- 이 PR에서는 패턴 탐지를 구현하지 않는다.

**정적 검증**

- `python -m compileall src tests`
- `python -m black --check src/analysis/ohlcv.py tests/analysis/test_ohlcv.py`
- `python -m isort --check-only src/analysis/ohlcv.py tests/analysis/test_ohlcv.py`
- `python -m mypy src/analysis/ohlcv.py`

**동적 검증**

- `python -m pytest tests/analysis/test_ohlcv.py`
- 합성 DataFrame으로 다음을 검증한다.
  - 대문자 OHLCV 컬럼이 소문자로 정규화된다.
  - 날짜 역순 데이터가 오름차순으로 정렬된다.
  - 중복 timestamp가 제거된다.
  - 비정상 high/low 행이 검출된다.
  - 빈 데이터는 명확한 validation error를 반환한다.
- KIS 응답 fixture dict를 사용해 `StockPrice` 리스트가 생성되고 OHLCV DataFrame으로 변환되는지 검증한다. 실제 API 호출은 하지 않는다.
- KR/US 분봉 fixture 모두 `StockPrice` 생성 시 `symbol`과 `datetime`이 빠지지 않는지 검증한다.
- `tests/fixtures/ohlcv_factory.py`의 최소 factory가 import 가능한지 검증한다.

**완료 기준**

- 표준 OHLCV DataFrame 계약이 문서와 테스트로 고정된다.
- 기존 `get_daily_price_history` 테스트가 깨지지 않는다.
- 분봉 파서가 `StockPrice` 모델과 일치한다.

---

### PR-02. 스윙 프랙탈과 시장구조 탐지

**목표**  
캔들 고점/저점 기반 스윙 하이, 스윙 로우를 탐지하고, 최근 구조가 상승/하락/중립인지 계산한다.

**구현 방법**

- 신규 파일 추가:
  - `src/analysis/smart_money/__init__.py`
  - `src/analysis/smart_money/models.py`
  - `src/analysis/smart_money/swings.py`
  - `tests/analysis/test_smart_money_swings.py`
- 데이터 구조 추가:
  - `SwingPoint` (`models.py`)
  - `MarketStructure` (`models.py`)
  - `StructureBreak` (`models.py`)
- 함수 추가:
  - `detect_swing_points(df, left=2, right=2) -> list[SwingPoint]` (`swings.py`)
  - `classify_market_structure(swings) -> MarketStructure` (`swings.py`)
  - `detect_structure_breaks(df, swings) -> list[StructureBreak]` (`swings.py`)
- `src/analysis/smart_money/__init__.py`는 public API만 재노출한다. 내부 구현 파일을 직접 import하는 의존이 퍼지지 않도록 한다.
- 스윙 규칙:
  - `swing_high`: 현재 high가 좌우 `left/right`개 candle high보다 크거나 같고, 최소 한쪽은 엄격히 크다.
  - `swing_low`: 현재 low가 좌우 `left/right`개 candle low보다 작거나 같고, 최소 한쪽은 엄격히 작다.
  - 마지막 `right`개 candle은 확정 전이므로 기본적으로 제외한다.
- 시장구조 규칙:
  - higher high + higher low가 반복되면 `BULLISH`
  - lower high + lower low가 반복되면 `BEARISH`
  - 혼재하면 `RANGE`
- BOS/CHOCH는 구조 전환을 너무 공격적으로 판단하지 않도록 확정 스윙 돌파 기준으로만 탐지한다.
- 이 PR에서는 FVG, 오더블록, 최종 매매 판정을 구현하지 않는다.

**정적 검증**

- `python -m compileall src/analysis/smart_money tests/analysis/test_smart_money_swings.py`
- `python -m black --check src/analysis/smart_money tests/analysis/test_smart_money_swings.py`
- `python -m isort --check-only src/analysis/smart_money tests/analysis/test_smart_money_swings.py`
- `python -m mypy src/analysis/smart_money`

**동적 검증**

- `python -m pytest tests/analysis/test_smart_money_swings.py`
- fixture 케이스:
  - 명확한 상승 구조: HH/HL 탐지
  - 명확한 하락 구조: LH/LL 탐지
  - 박스권: `RANGE` 반환
  - 동일 고점/동일 저점이 포함된 경우 과도한 중복 스윙이 생기지 않음
  - 데이터 수가 `left + right + 1`보다 작으면 빈 스윙 반환
- 회귀 검증:
  - `MultiIndicatorStrategy` 기존 테스트가 깨지지 않음
  - `tests/analysis/test_market_data.py`가 깨지지 않음

**완료 기준**

- 모든 패턴 탐지의 기준점이 되는 스윙 데이터가 안정적으로 생성된다.
- 구조 방향과 구조 돌파가 deterministic하게 테스트된다.

---

### PR-03. Fair Value Gap 탐지

**목표**  
3-candle imbalance 기반 FVG를 탐지하고, 최근 가격이 gap에 진입/완전 메움/미메움 상태인지 계산한다.

**구현 방법**

- `src/analysis/smart_money/fvg.py` 추가
- 신규 테스트:
  - `tests/analysis/test_smart_money_fvg.py`
- 데이터 구조 추가:
  - `FairValueGap` (`models.py`)
- 함수 추가:
  - `detect_fvgs(df, min_gap_pct=0.001) -> list[FairValueGap]` (`fvg.py`)
  - `update_fvg_status(df, fvgs) -> list[FairValueGap]` (`fvg.py`)
- `src/analysis/smart_money/__init__.py`에 FVG public API를 추가한다.
- Bullish FVG 규칙:
  - candle `i-2`의 high < candle `i`의 low
  - gap 범위: `[high[i-2], low[i]]`
- Bearish FVG 규칙:
  - candle `i-2`의 low > candle `i`의 high
  - gap 범위: `[high[i], low[i-2]]`
- 필터:
  - `gap_size / close[i] >= min_gap_pct`
  - volume 필터는 기본 off로 두고 후속 PR에서 scoring에만 반영한다.
- 상태:
  - `OPEN`: 아직 gap 미접촉
  - `TOUCHED`: 가격이 gap 범위에 들어옴
  - `FILLED`: gap 범위가 완전히 메워짐
- 이 PR에서는 오더블록이나 최종 신호 점수화를 하지 않는다.

**정적 검증**

- `python -m compileall src/analysis/smart_money tests/analysis/test_smart_money_fvg.py`
- `python -m black --check src/analysis/smart_money tests/analysis/test_smart_money_fvg.py`
- `python -m isort --check-only src/analysis/smart_money tests/analysis/test_smart_money_fvg.py`
- `python -m mypy src/analysis/smart_money`

**동적 검증**

- `python -m pytest tests/analysis/test_smart_money_fvg.py`
- fixture 케이스:
  - bullish FVG 1개 탐지
  - bearish FVG 1개 탐지
  - min gap 미달이면 무시
  - gap touched 상태 검증
  - gap filled 상태 검증
  - 여러 FVG가 겹쳐도 시간순으로 반환
- 샘플 실데이터형 CSV fixture를 만들어 FVG 탐지가 예외 없이 수행되는지 검증한다. 네트워크 호출은 하지 않는다.

**완료 기준**

- FVG 탐지와 상태 업데이트가 독립적으로 검증된다.
- 후속 신호 엔진이 사용할 `direction`, `lower`, `upper`, `status`, `created_at` 데이터가 제공된다.

---

### PR-04. 오더블록 탐지

**목표**  
구조 돌파 직전의 마지막 반대색 캔들을 오더블록 후보로 잡고, 이후 가격 반응 상태를 추적한다.

**구현 방법**

- `src/analysis/smart_money/order_blocks.py` 추가
- 신규 테스트:
  - `tests/analysis/test_smart_money_order_blocks.py`
- 데이터 구조 추가:
  - `OrderBlock` (`models.py`)
- 함수 추가:
  - `detect_order_blocks(df, swings, breaks, lookback=10) -> list[OrderBlock]` (`order_blocks.py`)
  - `update_order_block_status(df, order_blocks) -> list[OrderBlock]` (`order_blocks.py`)
- `src/analysis/smart_money/__init__.py`에 candle order block public API를 추가한다.
- Bullish Order Block 규칙:
  - bullish BOS 발생 직전 `lookback` 구간에서 마지막 bearish candle
  - zone: `low`부터 `open` 또는 `high`까지 설정한다. 기본은 보수적으로 `[low, high]`를 쓰고, scoring에서 close/open 세부 반응을 본다.
- Bearish Order Block 규칙:
  - bearish BOS 발생 직전 `lookback` 구간에서 마지막 bullish candle
  - zone: `[low, high]`
- 상태:
  - `FRESH`: 생성 후 아직 zone 미접촉
  - `MITIGATED`: 가격이 zone에 진입
  - `INVALIDATED`: bullish OB의 low 이탈 또는 bearish OB의 high 돌파
- 선택 필터:
  - BOS candle volume이 최근 20개 평균 이상이면 `strength` 가점
  - 너무 오래된 OB는 후속 scoring에서 감점한다.
- 이 PR에서는 `src/analysis/orderflow.py`의 호가창 Order Flow와 혼동하지 않도록 명확히 "candle order block"으로 명명한다.

**정적 검증**

- `python -m compileall src/analysis/smart_money tests/analysis/test_smart_money_order_blocks.py`
- `python -m black --check src/analysis/smart_money tests/analysis/test_smart_money_order_blocks.py`
- `python -m isort --check-only src/analysis/smart_money tests/analysis/test_smart_money_order_blocks.py`
- `python -m mypy src/analysis/smart_money`

**동적 검증**

- `python -m pytest tests/analysis/test_smart_money_order_blocks.py`
- fixture 케이스:
  - bullish BOS 후 bullish OB 생성
  - bearish BOS 후 bearish OB 생성
  - OB 재방문 시 `MITIGATED`
  - OB 무효화 시 `INVALIDATED`
  - BOS가 없으면 OB 없음
  - lookback 안에 반대색 캔들이 없으면 OB 없음
- 회귀 검증:
  - `python -m pytest tests/analysis/test_smart_money_swings.py tests/analysis/test_smart_money_fvg.py`

**완료 기준**

- 구조 돌파와 연결된 candle order block을 재현 가능하게 탐지한다.
- status 업데이트가 과거 데이터 재실행에서도 같은 결과를 낸다.

---

### PR-05. 캔들 패턴 탐지

**목표**  
진입/청산 타이밍 보조에 사용할 기본 캔들 패턴을 탐지한다.

**구현 방법**

- 신규 파일 추가:
  - `src/analysis/candlestick_patterns.py`
  - `tests/analysis/test_candlestick_patterns.py`
- 데이터 구조 추가:
  - `CandlePattern`
- 우선 구현할 패턴:
  - bullish engulfing
  - bearish engulfing
  - hammer
  - shooting star
  - doji
  - strong bullish candle
  - strong bearish candle
- 함수 추가:
  - `detect_candlestick_patterns(df) -> list[CandlePattern]`
- 패턴은 마지막 N개 전체를 계산하되, 후속 scoring에서는 최근 3~5개 캔들만 반영한다.
- 모든 임계값은 상수 또는 함수 인자로 둔다.
  - doji body 비율
  - wick/body 비율
  - strong candle body/range 비율
- `ta-lib`, `pandas-ta` 같은 외부 캔들 패턴 라이브러리는 초기 구현에서 사용하지 않는다. 현재 필요한 패턴 수가 제한적이고 Windows 설치/빌드 리스크가 있으므로, 정의를 테스트 fixture로 고정한 직접 구현을 우선한다.
- 이 PR에서는 Smart Money 패턴과 결합하지 않는다.

**정적 검증**

- `python -m compileall src/analysis/candlestick_patterns.py tests/analysis/test_candlestick_patterns.py`
- `python -m black --check src/analysis/candlestick_patterns.py tests/analysis/test_candlestick_patterns.py`
- `python -m isort --check-only src/analysis/candlestick_patterns.py tests/analysis/test_candlestick_patterns.py`
- `python -m mypy src/analysis/candlestick_patterns.py`

**동적 검증**

- `python -m pytest tests/analysis/test_candlestick_patterns.py`
- fixture 케이스:
  - bullish engulfing 탐지
  - bearish engulfing 탐지
  - hammer와 shooting star 구분
  - doji body 비율 경계값
  - gap candle에서도 range 0 division 방지
  - 데이터 1개만 있어도 단일 캔들 패턴은 탐지 가능
- 기존 전략 테스트 회귀:
  - `python -m pytest tests/test_strategies.py`

**완료 기준**

- 진입 타이밍에 사용할 캔들 패턴 결과가 독립 모듈로 제공된다.
- 패턴명, 방향, timestamp, strength가 일관되게 반환된다.

---

### PR-06. 멀티타임프레임 데이터 수집기

**목표**  
한 종목에 대해 `5m`, `1h`, `1d` OHLCV를 한 번에 가져오고, 실패한 타임프레임을 명확히 표시한다.

**구현 방법**

- 신규 파일 추가:
  - `src/analysis/timeframes.py`
  - `tests/analysis/test_timeframes.py`
- 데이터 구조 추가:
  - `Timeframe`
  - `TimeframeData`
  - `MultiTimeframeDataset`
- 함수/클래스 추가:
  - `MultiTimeframeFetcher`
  - `fetch_symbol(symbol, market="KR", exchange="NASD") -> MultiTimeframeDataset`
  - `resample_ohlcv(df, rule) -> pd.DataFrame`
- 수집 전략:
  - KR 5분봉: 현재 KR 분봉 구현이 `interval`을 query에 반영하지 않으므로 KIS 1분봉을 가져온 뒤 `5min`으로 resample한다.
  - KR 1시간봉: KR 1분봉 또는 5분봉 데이터를 `60min`으로 resample한다. API가 실제 60분봉을 지원하도록 별도 구현되기 전까지 `get_minute_price(interval=60)`을 KR 기본 경로로 사용하지 않는다.
  - KR 일봉: KIS `get_daily_price_history`를 사용한다.
  - US 5분봉: KIS 해외 분봉 `get_minute_price(interval=5, count=100)`을 사용한다.
  - US 1시간봉: KIS 해외 분봉 `get_minute_price(interval=60, count=100)`을 우선 사용하고, 실패 시 5분봉을 `60min`으로 resample한다.
  - US 일봉: 현재 `get_daily_price_history`는 KR용이므로 기본은 yfinance fallback을 사용한다. KIS 해외 일봉 API를 추가할 경우 이 PR 안에서 명시적으로 별도 메서드와 테스트를 만든다.
- 응답 구조:
  - 성공한 timeframe은 OHLCV DataFrame 포함
  - 실패한 timeframe은 `error`와 `source` 포함
  - 일부 실패해도 전체 분석은 가능한 범위에서 진행
- 네트워크 호출은 이 PR의 단위 테스트에서 mock 처리한다.

**정적 검증**

- `python -m compileall src/analysis/timeframes.py tests/analysis/test_timeframes.py`
- `python -m black --check src/analysis/timeframes.py tests/analysis/test_timeframes.py`
- `python -m isort --check-only src/analysis/timeframes.py tests/analysis/test_timeframes.py`
- `python -m mypy src/analysis/timeframes.py`

**동적 검증**

- `python -m pytest tests/analysis/test_timeframes.py`
- mock 검증:
  - KR 5분봉/1시간봉은 1분봉 원천 데이터에서 resample된다.
  - KR 경로에서 `interval=5`, `interval=60` 호출이 필수 전제처럼 테스트되지 않는다.
  - KR 일봉 API가 start/end date로 호출된다.
  - US 5분봉 API가 interval 5로 호출된다.
  - US 1시간봉 API가 interval 60으로 호출된다.
  - US 일봉은 yfinance fallback 또는 새로 추가한 KIS 해외 일봉 메서드로 호출된다.
  - US 60분 API 실패 시 5분봉 resample fallback이 동작한다.
  - 한 timeframe 실패 시 dataset 전체가 실패하지 않는다.
- resample 검증:
  - open은 첫 값
  - high는 max
  - low는 min
  - close는 마지막 값
  - volume은 sum

**수동/라이브 검증**

- API 키가 준비된 환경에서만 별도 smoke를 수행한다.
  - `python -m scripts.smart_money_smoke --symbol AAPL --market US --exchange NASD`
  - `python -m scripts.smart_money_smoke --symbol 005930 --market KR`
- smoke는 데이터 개수, 최신 timestamp, 각 timeframe validation error만 출력한다. 매매 신호는 아직 출력하지 않는다.

**완료 기준**

- 패턴 엔진이 멀티타임프레임 데이터를 동일한 방식으로 받을 수 있다.
- 네트워크 실패가 분석 전체 장애로 번지지 않는다.

---

### PR-07. 타임프레임별 패턴 분석 리포트

**목표**  
각 timeframe마다 스윙, 구조, FVG, 오더블록, 캔들 패턴을 한 번에 분석한 리포트를 만든다.

**구현 방법**

- 신규 파일 추가:
  - `src/analysis/smart_money/report.py`
  - `tests/analysis/test_smart_money_report.py`
- 데이터 구조 추가:
  - `TimeframePatternReport`
  - `PatternSummary`
- 함수 추가:
  - `analyze_timeframe_patterns(df, timeframe) -> TimeframePatternReport`
  - `analyze_multi_timeframe_patterns(dataset) -> dict[str, TimeframePatternReport]`
- 리포트 포함 내용:
  - timeframe
  - latest close
  - market structure
  - recent swing high/low
  - open/touched/filled FVG 목록
  - fresh/mitigated/invalidated OB 목록
  - recent candle patterns
  - warnings
- 이 PR은 최종 `BUY/SELL/HOLD`를 내지 않고, 관측 리포트만 반환한다.

**정적 검증**

- `python -m compileall src/analysis/smart_money/report.py tests/analysis/test_smart_money_report.py`
- `python -m black --check src/analysis/smart_money/report.py tests/analysis/test_smart_money_report.py`
- `python -m isort --check-only src/analysis/smart_money/report.py tests/analysis/test_smart_money_report.py`
- `python -m mypy src/analysis/smart_money/report.py`

**동적 검증**

- `python -m pytest tests/analysis/test_smart_money_report.py`
- fixture 검증:
  - 상승 구조 + bullish FVG + bullish OB + bullish candle 조합 리포트
  - 하락 구조 + bearish FVG + bearish OB + bearish candle 조합 리포트
  - 데이터 부족 warning 포함
  - 일부 pattern list가 비어도 리포트 생성
- 회귀 검증:
  - `python -m pytest tests/analysis/test_smart_money_swings.py tests/analysis/test_smart_money_fvg.py tests/analysis/test_smart_money_order_blocks.py tests/analysis/test_candlestick_patterns.py`

**완료 기준**

- 한 timeframe의 분석 결과를 UI/신호 엔진에서 바로 사용할 수 있는 구조로 반환한다.
- 패턴 탐지 결과가 사람이 읽을 수 있는 summary로 변환된다.

---

### PR-08. 멀티타임프레임 신호 점수화 엔진

**목표**  
일봉, 1시간봉, 5분봉 리포트를 조합해 최종 `BUY`, `SELL`, `HOLD`와 confidence를 산출한다.

**구현 방법**

- 신규 파일 추가:
  - `src/analysis/smart_money/signal.py`
  - `tests/analysis/test_smart_money_signal.py`
- 데이터 구조 추가:
  - `SmartMoneySignal`
  - `SignalContribution`
  - `SignalConfig`
- 함수 추가:
  - `score_timeframe_report(report, config) -> list[SignalContribution]`
  - `combine_multi_timeframe_signals(reports, config) -> SmartMoneySignal`
- 기본 점수 구조:
  - 일봉 구조 방향: 큰 방향 필터, 가중치 40%
  - 1시간봉 OB/FVG 구간: setup 필터, 가중치 35%
  - 5분봉 캔들/구조 반응: entry trigger, 가중치 25%
- 최종 신호 gate:
  - `BUY`는 최소 2개 timeframe이 bullish 확인을 제공해야 한다.
  - `SELL`은 최소 2개 timeframe이 bearish 확인을 제공해야 한다.
  - 5분봉 단독 trigger는 `BUY` 또는 `SELL`을 만들 수 없고, 상위 timeframe 확인이 없으면 `HOLD`로 유지한다.
  - 일봉과 1시간봉 방향이 명확히 충돌하면 5분봉 trigger가 있어도 `HOLD`를 우선한다.
  - 핵심 timeframe 중 2개 이상이 실패하거나 데이터 부족이면 `HOLD`를 우선한다.
- confidence 계산:
  - `raw_confidence = min(1.0, abs(score) / max_abs_score)`
  - 방향 충돌, 데이터 부족, 오래된 패턴, 무효화 직전 zone은 confidence penalty로 차감한다.
  - `confidence = max(0.0, min(1.0, raw_confidence - penalties))`
  - threshold 판정은 `score`, timeframe confirmation, `confidence >= min_confidence`를 모두 만족해야 통과한다.
- BUY 예시:
  - 일봉 `BULLISH` 또는 `RANGE` 하단
  - 1시간봉 bullish OB/FVG가 fresh 또는 touched
  - 5분봉에서 bullish candle pattern 또는 bullish CHOCH
- SELL 예시:
  - 일봉 `BEARISH` 또는 주요 swing low 이탈
  - 1시간봉 bearish OB/FVG가 fresh 또는 touched
  - 5분봉에서 bearish candle pattern 또는 bearish CHOCH
- HOLD 예시:
  - 방향 충돌
  - 핵심 timeframe 데이터 부족
  - confidence가 threshold 미만
- 반환값:
  - `signal`
  - `confidence`
  - `score`
  - `risk_level`
  - `entry_zone`
  - `invalidation_level`
  - `take_profit_candidates`
  - `reasons`
  - `warnings`
  - `contributions`
- 이 PR에서는 자동주문과 대시보드 UI를 연결하지 않는다.

**정적 검증**

- `python -m compileall src/analysis/smart_money/signal.py tests/analysis/test_smart_money_signal.py`
- `python -m black --check src/analysis/smart_money/signal.py tests/analysis/test_smart_money_signal.py`
- `python -m isort --check-only src/analysis/smart_money/signal.py tests/analysis/test_smart_money_signal.py`
- `python -m mypy src/analysis/smart_money/signal.py`

**동적 검증**

- `python -m pytest tests/analysis/test_smart_money_signal.py`
- fixture 검증:
  - 모든 timeframe bullish 정렬 시 `BUY`
  - 모든 timeframe bearish 정렬 시 `SELL`
  - 2개 timeframe만 bullish 정렬되고 하나가 중립이면 threshold 충족 시 `BUY`
  - 2개 timeframe만 bearish 정렬되고 하나가 중립이면 threshold 충족 시 `SELL`
  - 일봉 bullish, 1시간 bearish 충돌 시 `HOLD`
  - 5분봉만 bullish이고 상위 timeframe 약세면 `HOLD`
  - 5분봉만 bearish이고 상위 timeframe 강세면 `HOLD`
  - 데이터 부족 시 confidence 하락과 warning 포함
  - entry_zone과 invalidation_level이 올바른 OB/FVG에서 나온다.
  - score는 threshold를 넘었지만 timeframe confirmation이 부족하면 `HOLD`
  - score는 threshold를 넘었지만 confidence가 `min_confidence` 미만이면 `HOLD`
- snapshot성 검증:
  - 동일 입력이면 동일 score와 reason 순서 반환

**완료 기준**

- 최종 신호가 deterministic하게 산출된다.
- 각 신호는 근거와 위험 수준을 함께 제공한다.

---

### PR-09. 차트 주석과 시각화 도우미

**목표**  
FVG, 오더블록, 스윙 포인트, 최종 신호를 차트에 표시할 수 있는 reusable helper를 만든다.

**구현 방법**

- 신규 파일 추가:
  - `src/analysis/smart_money/chart.py`
  - `tests/analysis/test_smart_money_chart.py`
- 구현 선택:
  - 대시보드용은 Plotly candlestick 우선
  - `plotly>=5.14.0`는 이미 `pyproject.toml`에 있으므로 새 의존성 추가는 필요 없다.
  - 기존 정적 이미지 연동이 필요하면 `ChartGenerator`에 optional annotation 인자를 별도 PR에서 추가
- 함수 추가:
  - `build_smart_money_figure(df, report, signal=None) -> plotly.graph_objects.Figure`
- 표시 요소:
  - swing high/low marker
  - bullish/bearish FVG rectangle
  - bullish/bearish OB rectangle
  - entry zone horizontal band
  - invalidation level line
- 스타일:
  - 색상은 과도한 단일 색상 테마를 피한다.
  - 모바일에서도 hover text가 겹치지 않도록 legend와 margin을 고정한다.
  - rectangle은 최근 N개만 표시해 차트가 과밀해지지 않도록 한다.

**정적 검증**

- `python -m compileall src/analysis/smart_money/chart.py tests/analysis/test_smart_money_chart.py`
- `python -m black --check src/analysis/smart_money/chart.py tests/analysis/test_smart_money_chart.py`
- `python -m isort --check-only src/analysis/smart_money/chart.py tests/analysis/test_smart_money_chart.py`
- `python -m mypy src/analysis/smart_money/chart.py`

**동적 검증**

- `python -m pytest tests/analysis/test_smart_money_chart.py`
- 검증 항목:
  - Figure에 candlestick trace가 포함된다.
  - FVG rectangle shape 수가 report와 일치한다.
  - OB rectangle shape 수가 report와 일치한다.
  - entry/invalidation line이 signal에 따라 추가된다.
  - 빈 report라도 차트 생성이 실패하지 않는다.

**브라우저 검증**

- 대시보드 연결 전이라면 fixture figure를 HTML로 저장해 수동 확인한다.
- 대시보드 연결 후 Playwright로 desktop/mobile screenshot을 확인한다.

**완료 기준**

- UI는 패턴 엔진을 직접 해석하지 않고 figure helper만 호출하면 된다.
- 차트 annotation이 패턴 근거와 일치한다.

---

### PR-10. 대시보드 Smart Money 탭

**목표**  
사용자가 여러 종목을 입력하고, 각 종목의 5분봉/1시간봉/일봉 분석과 최종 신호를 확인할 수 있는 Streamlit 탭을 추가한다.

**구현 방법**

- 신규 파일 추가:
  - `dashboard/components/smart_money_tab.py`
  - `tests/dashboard/test_smart_money_tab.py`
- `dashboard/app.py`에 새 탭 연결
- UI 구성:
  - 종목 입력: comma-separated text area
  - 시장 선택: KR/US
  - 거래소 선택: US일 때 NASD/NYSE/AMEX
  - 분석 실행 버튼
  - 결과 표:
    - symbol
    - signal
    - confidence
    - daily structure
    - 1h setup
    - 5m trigger
    - entry zone
    - invalidation
    - 주요 reason
  - 선택 종목 상세:
    - timeframe tabs: 5m, 1h, 1d
    - annotated chart
    - pattern summary
    - warnings
- 네트워크/API 실패 UX:
  - 실패한 timeframe만 warning으로 표시
  - 전체 종목 실패 시 error 표시
  - 일부 종목 성공 시 성공 결과는 계속 보여준다.
- 자동주문 버튼은 만들지 않는다.

**정적 검증**

- `python -m compileall dashboard/components/smart_money_tab.py tests/dashboard/test_smart_money_tab.py`
- `python -m black --check dashboard/components/smart_money_tab.py tests/dashboard/test_smart_money_tab.py`
- `python -m isort --check-only dashboard/components/smart_money_tab.py tests/dashboard/test_smart_money_tab.py`
- `python -m mypy dashboard/components/smart_money_tab.py`

**동적 검증**

- `python -m pytest tests/dashboard/test_smart_money_tab.py`
- test double로 다음 검증:
  - 여러 종목 입력 파싱
  - 빈 종목 입력 시 API 호출 없음
  - 성공 결과 표 렌더 함수가 필요한 컬럼을 만든다.
  - 실패 warning이 결과에 포함된다.
  - chart helper 호출 인자가 report/signal과 일치한다.

**브라우저 검증**

- Streamlit 실행:
  - `streamlit run dashboard/app.py --server.headless true --server.port 8506`
- Playwright 검증:
  - 탭이 보인다.
  - 종목 입력 후 mock 또는 fixture 모드에서 결과 표가 보인다.
  - desktop 1280x720과 mobile viewport에서 텍스트 겹침이 없다.
  - 차트가 blank가 아니다.

**완료 기준**

- 사용자 입장에서 "여러 종목 Smart Money 분석"을 대시보드에서 실행할 수 있다.
- 결과가 투자 판단 보조 신호임을 UI 문구로 명확히 표시한다.

---

### PR-11. CLI/스케줄러용 분석 리포트

**목표**  
대시보드 없이도 특정 종목 리스트에 대해 Smart Money 분석을 실행하고 JSON/Markdown 리포트를 만들 수 있게 한다.

**구현 방법**

- 신규 파일 추가:
  - `scripts/run_smart_money_analysis.py`
  - `tests/scripts/test_run_smart_money_analysis.py`
- CLI 인자:
  - `--symbols AAPL,MSFT`
  - `--market US`
  - `--exchange NASD`
  - `--output reports/smart_money_YYYYMMDD.json`
  - `--format json|markdown`
  - `--no-network` 또는 `--fixture` 테스트 모드
- 출력:
  - 실행 시각
  - symbol별 signal
  - confidence
  - entry/invalidation
  - timeframe별 summary
  - warnings/errors
- 실패 정책:
  - 한 종목 실패는 전체 실패로 만들지 않는다.
  - 모든 종목 실패 시 exit code 1

**정적 검증**

- `python -m compileall scripts/run_smart_money_analysis.py tests/scripts/test_run_smart_money_analysis.py`
- `python -m black --check scripts/run_smart_money_analysis.py tests/scripts/test_run_smart_money_analysis.py`
- `python -m isort --check-only scripts/run_smart_money_analysis.py tests/scripts/test_run_smart_money_analysis.py`
- `python -m mypy scripts/run_smart_money_analysis.py`

**동적 검증**

- `python -m pytest tests/scripts/test_run_smart_money_analysis.py`
- fixture 모드 검증:
  - JSON 파일 생성
  - Markdown 파일 생성
  - 일부 종목 실패가 리포트 warnings에 기록
  - 모든 종목 실패 시 exit code 1

**수동 검증**

- `python scripts/run_smart_money_analysis.py --symbols AAPL,MSFT --market US --fixture --format markdown --output reports/smart_money_sample.md`
- 생성된 리포트에서 signal, confidence, reasons, warnings가 빠지지 않았는지 확인한다.

**완료 기준**

- 대시보드 외 자동 리포트/스케줄링 기반이 생긴다.
- 향후 Telegram/Kakao 알림과 연결할 수 있는 JSON 계약이 고정된다.

---

### PR-12. 백테스트와 성능 검증

**목표**  
Smart Money 신호가 과거 데이터에서 어떤 성과와 실패 패턴을 보이는지 검증한다.

**구현 방법**

- 신규 파일 추가:
  - `src/backtest/smart_money_engine.py`
  - `tests/backtest/test_smart_money_engine.py`
- 구현 범위:
  - walk-forward 방식으로 각 시점까지의 캔들만 사용
  - lookahead bias 방지
  - `BUY` 후 N봉 보유 또는 invalidation 이탈 시 청산
  - `SELL`은 보유 포지션 청산 또는 short 미지원 환경에서는 exit signal로만 기록
- 지표:
  - 총 거래 수
  - 승률
  - 평균 손익
  - 최대 낙폭
  - profit factor
  - signal coverage
  - BUY/SELL/HOLD 비율
- 데이터:
  - unit test는 합성 fixture
  - integration smoke는 저장된 CSV fixture
  - live download backtest는 별도 수동 명령

**정적 검증**

- `python -m compileall src/backtest/smart_money_engine.py tests/backtest/test_smart_money_engine.py`
- `python -m black --check src/backtest/smart_money_engine.py tests/backtest/test_smart_money_engine.py`
- `python -m isort --check-only src/backtest/smart_money_engine.py tests/backtest/test_smart_money_engine.py`
- `python -m mypy src/backtest/smart_money_engine.py`

**동적 검증**

- `python -m pytest tests/backtest/test_smart_money_engine.py`
- fixture 검증:
  - 미래 캔들을 참조하지 않는다.
  - entry price가 signal 발생 다음 candle 기준으로 계산된다.
  - invalidation level 이탈 시 청산된다.
  - 데이터 부족 구간은 거래하지 않는다.
  - 수수료/슬리피지 옵션이 손익에 반영된다.

**수동 검증**

- `python scripts/run_smart_money_backtest.py --symbols AAPL --period 1y --market US`
- 결과 리포트에서 거래 수가 0이 아닌지, 과도한 매매 빈도가 아닌지 확인한다.
- 동일 명령을 2회 실행했을 때 결과가 동일해야 한다.

**완료 기준**

- Smart Money 신호가 단순 시각화가 아니라 검증 가능한 전략 후보가 된다.
- threshold 조정 전후 성과 비교가 가능하다.

---

### PR-13. 알림 연동

**목표**  
대시보드나 CLI를 계속 보고 있지 않아도 신호 변화를 알림으로 받을 수 있게 한다. 1차 알림 채널은 카카오톡 "나에게 보내기"로 두고, Telegram은 선택 채널로 유지한다.

**구현 방법**

- 신규 파일 추가:
  - `src/analysis/smart_money/alerts.py`
  - `tests/analysis/test_smart_money_alerts.py`
- 기존 notifier 재사용:
  - `src/utils/kakao_notifier.py`를 기본 채널로 사용한다.
  - `src/utils/telegram_notifier.py`는 fallback 또는 보조 채널로 유지한다.
- 알림 provider 설정:
  - `smart_money.alerts.enabled: false`
  - `smart_money.alerts.provider: kakao`
  - `smart_money.alerts.cooldown_minutes: 30`
  - `smart_money.alerts.min_confidence: 0.60`
  - `smart_money.alerts.notify_on: ["BUY", "SELL"]`
  - `smart_money.alerts.repeat_on_confidence_jump: true`
  - `smart_money.alerts.confidence_jump_threshold: 0.15`
- 카카오톡 환경변수:
  - `KAKAO_REST_API_KEY`
  - `KAKAO_ACCESS_TOKEN`
  - `KAKAO_REFRESH_TOKEN`
- 카카오톡 최초 인증 절차:
  - Kakao Developers에서 애플리케이션 생성
  - 카카오 로그인 활성화
  - Redirect URI 등록
  - 동의항목에서 카카오톡 메시지 전송 권한 활성화
  - OAuth code로 access token과 refresh token 발급
  - 토큰을 `.env`에 저장
- `KakaoNotifier`가 access token 만료로 401을 받으면 refresh token으로 갱신 후 재시도하는 경로를 그대로 활용한다.
- 알림 정책:
  - `HOLD -> BUY`
  - `HOLD -> SELL`
  - `BUY -> SELL`
  - `SELL -> BUY`
  - confidence가 threshold 이상일 때만
  - 같은 symbol/timeframe/signal은 cooldown 시간 동안 중복 발송 금지
  - 같은 signal이라도 confidence가 `confidence_jump_threshold` 이상 상승하면 1회 재알림 가능
  - 데이터 수집 실패, API rate limit, 토큰 만료 갱신 실패는 매매 신호 알림과 별도 system alert로 분리
- 상태 저장:
  - `trading_state.json` 또는 별도 `data/smart_money_alert_state.json`
  - 실거래 상태와 섞이지 않도록 namespace 분리
- 메시지:
  - symbol
  - signal
  - confidence
  - current price
  - entry/invalidation
  - timeframe 확인 요약
  - 핵심 reason 3개
  - 발생 시각
  - "자동주문 아님" 표시
- 카카오톡 메시지 예시:

```text
[Smart Money Signal]
종목: AAPL
신호: BUY
신뢰도: 68%
현재가: 182.40
진입 후보: 181.80 ~ 183.10
무효화: 178.50
확인: 일봉 BULLISH, 1시간봉 bullish FVG touched, 5분봉 bullish CHOCH
근거:
1. 일봉 구조가 상승 유지
2. 1시간봉 FVG 재진입
3. 5분봉에서 상승 전환 확인
시간: 2026-04-23 09:35:00
주의: 자동주문이 아닌 판단 보조 알림입니다.
```

**정적 검증**

- `python -m compileall src/analysis/smart_money/alerts.py tests/analysis/test_smart_money_alerts.py`
- `python -m black --check src/analysis/smart_money/alerts.py tests/analysis/test_smart_money_alerts.py`
- `python -m isort --check-only src/analysis/smart_money/alerts.py tests/analysis/test_smart_money_alerts.py`
- `python -m mypy src/analysis/smart_money/alerts.py`

**동적 검증**

- `python -m pytest tests/analysis/test_smart_money_alerts.py`
- 검증 항목:
  - threshold 미만 신호는 알림 없음
  - 동일 신호 cooldown 중복 방지
  - signal 변화 시 알림 생성
  - `HOLD -> BUY`, `HOLD -> SELL`, `BUY -> SELL`, `SELL -> BUY` 전환이 알림 대상이 된다.
  - provider가 `kakao`이면 `KakaoNotifier.send_signal_alert` 또는 Smart Money 전용 전송 래퍼가 호출된다.
  - provider가 `telegram`이면 Telegram notifier가 호출된다.
  - 카카오 access token 만료 상황은 `KakaoNotifier`의 refresh 경로를 호출하도록 mock으로 검증한다.
  - 카카오 환경변수가 없으면 알림 실패를 warning으로 남기고 분석 결과는 유지한다.
  - notifier exception이 전체 분석을 실패시키지 않음
  - 메시지에 필수 필드 포함
  - 메시지에 "자동주문 아님" 문구가 포함된다.

**수동 검증**

- sandbox/mock notifier로 dry-run 메시지 출력 확인
- 카카오톡 dry-run:
  - provider를 `kakao`로 설정하고 mock notifier로 메시지 포맷을 확인한다.
- 카카오톡 실제 발송:
  - `.env`에 `KAKAO_REST_API_KEY`, `KAKAO_ACCESS_TOKEN`, `KAKAO_REFRESH_TOKEN`이 있는 로컬에서만 수행한다.
  - 실제 발송 테스트는 `--symbol AAPL --fixture`처럼 fixture 신호로 1건만 보낸다.
  - 토큰 갱신이 발생하는 경우 `.env` 갱신 필요 여부를 로그에 남긴다.
- Telegram 실제 발송은 Telegram 환경변수가 준비된 경우에만 선택 수행한다.

**완료 기준**

- 분석 신호 변화가 카카오톡으로 전달된다.
- 중복 알림과 notifier 장애가 통제된다.
- 카카오톡 인증/토큰/환경변수 미설정 상태에서도 분석 루프는 중단되지 않는다.

---

### PR-14. 자동매매 연동 준비와 feature flag

**목표**  
Smart Money 신호를 실제 주문 로직에 바로 넣지 않고, 기존 자동매매의 필터로만 선택적으로 사용할 수 있게 준비한다.

**구현 방법**

- 설정 추가:
  - `config/trading.yaml` 또는 `config/strategies.yaml`
  - `smart_money.enabled: false`
  - `smart_money.mode: advisory|filter|execute`
  - 초기 지원은 `advisory`와 `filter`까지만
- `src/trader/auto_trader.py`에 최소 연결:
  - 신규 매수 후보 중 Smart Money `SELL`은 제외
  - Smart Money `BUY`는 기존 점수에 bonus를 줄 수 있지만, 단독 매수 트리거로 쓰지 않는다.
  - 보유 종목의 Smart Money `SELL`은 경고/알림부터 시작하고, 자동 청산은 별도 승인 전까지 비활성화한다.
- dry-run 로그:
  - symbol별 기존 selector 판단
  - smart money signal
  - 최종 포함/제외 이유
- 이 PR에서는 `execute` 모드를 구현하지 않는다.

**정적 검증**

- `python -m compileall src/trader/auto_trader.py tests`
- `python -m black --check src/trader/auto_trader.py tests`
- `python -m isort --check-only src/trader/auto_trader.py tests`
- `python -m mypy src/trader/auto_trader.py`

**동적 검증**

- 기존 자동매매 테스트:
  - `python -m pytest tests/test_us_trading_dry_run.py tests/test_live.py`
- 신규 테스트:
  - `tests/trader/test_smart_money_filter.py`
- 검증 항목:
  - feature flag off일 때 기존 동작과 동일
  - filter mode에서 Smart Money `SELL` 후보는 제외
  - filter mode에서 Smart Money 데이터 실패 시 기존 selector 동작 유지
  - dry-run에서 주문 실행 없이 로그만 기록

**수동 검증**

- `TRADING_MODE=mock` 또는 dry-run 모드에서만 실행
- 매수/매도 주문이 실제로 나가지 않는지 로그와 broker mock으로 확인

**완료 기준**

- Smart Money 기능이 자동매매에 영향을 주는 경로가 feature flag로 통제된다.
- 기본값은 항상 비활성화다.

## 4. PR 의존성 지도

| PR | 의존 |
|---|---|
| PR-01 | 없음 |
| PR-02 | PR-01 |
| PR-03 | PR-01 |
| PR-04 | PR-01, PR-02 |
| PR-05 | PR-01 |
| PR-06 | PR-01 |
| PR-07 | PR-02, PR-03, PR-04, PR-05 |
| PR-08 | PR-07 |
| PR-09 | PR-07, PR-08 |
| PR-10 | PR-06, PR-07, PR-08, PR-09 |
| PR-11 | PR-06, PR-07, PR-08 |
| PR-12 | PR-07, PR-08 |
| PR-13 | PR-08 |
| PR-14 | PR-08 |

병렬 진행 가능:

- PR-03과 PR-05는 PR-01 이후 병렬 가능
- PR-04는 PR-02 완료 후 진행
- PR-09는 PR-07의 리포트 계약이 고정된 뒤 진행
- PR-10과 PR-11은 PR-08 이후 병렬 가능
- PR-13과 PR-14는 PR-08의 `SmartMoneySignal` 계약만 있으면 진행 가능하며, CLI 리포트(PR-11)나 알림(PR-13)에 의존하지 않는다.

## 5. 공통 검증 명령

각 PR에서 해당 파일만 먼저 검증한 뒤, 병합 전에는 아래를 실행한다.

```powershell
python -m compileall src dashboard scripts tests
python -m black --check src dashboard scripts tests
python -m isort --check-only src dashboard scripts tests
python -m pytest tests/analysis tests/dashboard tests/backtest tests/scripts
```

전체 테스트는 시간이 오래 걸릴 수 있으므로, PR 리뷰 단계에서는 변경 범위 테스트를 우선 실행하고 main 병합 전 전체 테스트를 실행한다.

## 6. 공통 테스트 Fixture 전략

### 6.1 합성 OHLCV fixture

위치:

- `tests/fixtures/ohlcv_factory.py`

포함할 factory:

- `make_bullish_structure_frame()`
- `make_bearish_structure_frame()`
- `make_range_frame()`
- `make_bullish_fvg_frame()`
- `make_bearish_fvg_frame()`
- `make_bullish_order_block_frame()`
- `make_bearish_order_block_frame()`
- `make_candlestick_pattern_frame(pattern_name)`

원칙:

- 각 fixture는 어떤 패턴을 의도했는지 docstring에 적는다.
- 너무 현실적인 랜덤 데이터보다 deterministic한 계단식 데이터를 우선 사용한다.
- 필요할 때만 seed 고정 random walk fixture를 추가한다.

### 6.2 CSV fixture

위치:

- `tests/fixtures/ohlcv/AAPL_5m_sample.csv`
- `tests/fixtures/ohlcv/AAPL_1h_sample.csv`
- `tests/fixtures/ohlcv/AAPL_1d_sample.csv`

원칙:

- 라이선스 이슈가 있는 대량 원본 데이터는 커밋하지 않는다.
- 테스트용 최소 샘플만 포함한다.
- 컬럼은 표준 OHLCV 계약에 맞춘다.

## 7. 신호 점수 기본안

초기 config 예시:

```yaml
smart_money:
  enabled: false
  signal:
    buy_threshold: 0.50
    sell_threshold: -0.50
    min_confidence: 0.55
    min_confirming_timeframes: 2
    timeframe_weights:
      daily: 0.40
      hourly: 0.35
      minute_5: 0.25
    stale_pattern_penalty_per_bar: 0.01
    max_patterns_per_type: 5
```

초기 점수 예시:

| 조건 | 점수 |
|---|---:|
| 일봉 bullish structure | +0.30 |
| 일봉 bearish structure | -0.30 |
| 1시간봉 bullish OB touched | +0.20 |
| 1시간봉 bearish OB touched | -0.20 |
| 1시간봉 bullish FVG touched | +0.15 |
| 1시간봉 bearish FVG touched | -0.15 |
| 5분봉 bullish CHOCH | +0.15 |
| 5분봉 bearish CHOCH | -0.15 |
| 5분봉 bullish engulfing/hammer | +0.10 |
| 5분봉 bearish engulfing/shooting star | -0.10 |
| 상위 timeframe과 반대 방향 trigger | confidence 감점 |
| 핵심 timeframe 데이터 부족 | confidence 감점 |

최종 판정 규칙:

- `BUY`는 `score >= buy_threshold`, `confidence >= min_confidence`, bullish confirming timeframe 수가 `min_confirming_timeframes` 이상일 때만 반환한다.
- `SELL`은 `score <= sell_threshold`, `confidence >= min_confidence`, bearish confirming timeframe 수가 `min_confirming_timeframes` 이상일 때만 반환한다.
- 5분봉 단독 trigger는 최종 신호를 만들 수 없다.
- 일봉과 1시간봉이 충돌하면 기본값은 `HOLD`다.
- confidence는 `abs(score) / max_abs_score`를 기본값으로 삼고, 방향 충돌, 데이터 부족, 오래된 패턴, invalidation 근접성을 penalty로 차감한다.

이 점수와 threshold는 PR-12 백테스트 결과에 따라 조정한다.

## 8. 주요 리스크와 대응

| 리스크 | 대응 |
|---|---|
| ICT/Smart Money 패턴은 정의가 사람마다 다름 | 각 패턴 규칙을 코드와 테스트 이름으로 고정하고 문서화 |
| lookahead bias | 스윙 확정 전 마지막 `right`개 candle 제외, 백테스트는 walk-forward |
| 분봉 API 제한 | mock/fixture 테스트 우선, 라이브 smoke는 선택 실행 |
| 한국/미국 데이터 포맷 차이 | PR-01 정규화 레이어에서 차이를 흡수하고, PR-06에서 KR/US 분봉/일봉 수집 경로를 분리 |
| 신호 과최적화 | PR-12에서 기간/종목 분리 검증 |
| 자동매매 오작동 | PR-14까지 주문 연결 금지, 기본 feature flag off |
| UI 과밀 | 최근 패턴 N개만 차트 표시, 상세 표는 접을 수 있게 구성 |
| 기존 `orderflow.py`와 candle order block의 개념 혼동 | 초기 구현에서는 결합하지 않고 명명과 문서로 분리. 추후 orderflow score는 PR-08 이후 optional bonus로만 확장 |

## 9. 최종 사용자 경험 목표

대시보드에서 사용자는 다음 흐름을 갖는다.

1. Smart Money 탭을 연다.
2. `AAPL, TSLA, 005930`처럼 여러 종목을 입력한다.
3. 분석 실행을 누른다.
4. 결과 표에서 종목별 `BUY`, `SELL`, `HOLD`, confidence, 핵심 근거를 비교한다.
5. 종목 하나를 선택해 5분봉, 1시간봉, 일봉 차트를 각각 확인한다.
6. 차트에서 FVG, 오더블록, 스윙 포인트, entry/invalidation zone을 본다.
7. 자동주문 없이 판단 보조 자료로 사용한다.

## 10. 권장 구현 순서

가장 작은 단위로 안정성을 쌓으려면 다음 순서를 권장한다.

1. PR-01: OHLCV 계약
2. PR-02: 스윙/구조
3. PR-03: FVG
4. PR-04: 오더블록
5. PR-05: 캔들 패턴
6. PR-07: timeframe 리포트
7. PR-08: 신호 점수화
8. PR-06: 실제 데이터 수집기
9. PR-09: 차트 주석
10. PR-10: 대시보드
11. PR-11: CLI 리포트
12. PR-12: 백테스트
13. PR-13: 알림
14. PR-14: 자동매매 필터 연동

PR-06을 PR-08 이후로 미루는 이유는 패턴/신호 엔진을 fixture 기반으로 먼저 안정화하면, API 제약과 네트워크 이슈가 핵심 로직 개발을 방해하지 않기 때문이다.
