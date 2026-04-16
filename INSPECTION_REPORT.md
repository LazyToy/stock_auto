# 주식 자동매매 시스템 정밀 검사 보고서

> **검사 일자:** 2026-03-26
> **검사 범위:** 전체 소스 코드 (src/, dashboard/, scripts/, config/)
> **방법론:** 파일별 전수 라인 검사, 4개 서브에이전트 병렬 수행

---

## 목차

1. [심각도 요약](#1-심각도-요약)
2. [대시보드 — 하드코딩 및 가짜 데이터](#2-대시보드--하드코딩-및-가짜-데이터)
3. [전략 — 금융 수식 오류 및 룩어헤드 바이어스](#3-전략--금융-수식-오류-및-룩어헤드-바이어스)
4. [ML/RL — 미초기화 및 학습 미구현](#4-mlrl--미초기화-및-학습-미구현)
5. [백테스트 엔진 — 미완성 지표 및 수식 오류](#5-백테스트-엔진--미완성-지표-및-수식-오류)
6. [브로커 및 주문 — 스텁 코드 및 런타임 크래시](#6-브로커-및-주문--스텁-코드-및-런타임-크래시)
7. [실시간 매매 엔진 — 미구현 메서드 호출](#7-실시간-매매-엔진--미구현-메서드-호출)
8. [트레이더 및 자가복구 — 목업 구현](#8-트레이더-및-자가복구--목업-구현)
9. [데이터 클라이언트 — 무음 실패 및 세션 오류](#9-데이터-클라이언트--무음-실패-및-세션-오류)
10. [설정 및 스크립트 — 불일치 및 하드코딩](#10-설정-및-스크립트--불일치-및-하드코딩)
11. [해결 방안 우선순위 로드맵](#11-해결-방안-우선순위-로드맵)

---

## 1. 심각도 요약

| 등급 | 건수 | 주요 내용 |
|------|------|-----------|
| 🔴 **CRITICAL** | 18건 | 런타임 크래시, 가짜 데이터를 실데이터로 표시, 룩어헤드 바이어스 |
| 🟠 **HIGH** | 22건 | 잘못된 금융 수식, 스텁 코드, 무음 실패, 환경변수 불일치 |
| 🟡 **MEDIUM** | 20건 | 하드코딩 값, 설정 중복, 미구현 기능 플레이스홀더 |
| 🟢 **LOW** | 6건 | deprecated API, 중복 로그, 사소한 기본값 문제 |
| **합계** | **66건** | |

---

## 2. 대시보드 — 하드코딩 및 가짜 데이터

### 2-1. AutoML 결과가 가짜 하드코딩 값 🔴 CRITICAL

**파일:** `dashboard/app.py` · 라인 318–329

```python
# 임시 데모 실행 (실제로는 optimizer.evolve() 호출)
for i in range(generations):
    time.sleep(0.1)  # 시뮬레이션만 함
    progress_bar.progress((i + 1) / generations)

st.session_state["automl_result"] = {
    "best_params": {"short_ma": 10, "long_ma": 50, "rsi_period": 14},
    "best_fitness": 0.78,
    "history": [0.3, 0.45, 0.6, 0.72, 0.78]
}
```

**문제:** `optimizer.evolve()`를 실제로 호출하지 않고 progress bar만 돌린 뒤, 고정된 파라미터(short_ma=10, long_ma=50, fitness=0.78)를 마치 유전 알고리즘이 진화시킨 결과처럼 사용자에게 보여준다. 개발자 코멘트 자체에 "임시 데모 실행"이라고 명시되어 있다.

**해결 방안:** `GeneticOptimizer.evolve()` 메서드를 실제로 호출하고 그 결과를 반환한다. 백그라운드 비동기 실행이 필요하면 `st.session_state`에 실행 상태를 저장하는 방식으로 구현한다.

---

### 2-2. 포트폴리오 기본값이 실제 잔고처럼 표시됨 🔴 CRITICAL

**파일:** `dashboard/app.py` · 라인 109–110, 123–124

```python
'total_asset': 10000000 if market == "KR" else 10000.0,
'deposit': 5000000 if market == "KR" else 5000.0,
```

**문제:** 상태 파일이 없거나 로드에 실패하면 1천만 원/1만 달러를 실제 잔고처럼 대시보드에 표시한다. 사용자는 자신이 이 자금을 보유한 것으로 오인할 수 있다.

**해결 방안:** 상태 파일 로드 실패 시 자산 값을 `None` 또는 `0`으로 설정하고, 대시보드에 "데이터 없음 — 매매 시스템을 먼저 실행하세요" 메시지를 표시한다.

---

### 2-3. 거시경제 지표 전체가 하드코딩 폴백 🔴 CRITICAL

**파일:** `dashboard/components/macro_tab.py` · 라인 117–131, 157–159

```python
# FRED API 실패 시
data['US_RATE'] = {'val': 5.25}   # 연준 기준금리
data['UNRATE'] = {'val': 3.9}    # 실업률
data['US_CPI']  = {'val': 3.4}   # CPI

# 한국 기준금리
data['KR_RATE'] = {'val': 3.50}  # 코멘트: "잘 안 바뀜, 현재 3.50"

# US PMI
data['US_PMI'] = {'val': 49.1}   # 코멘트: "공짜 ISM 없음, 대략 49~51"

# pykrx 실패 시 외국인 순매수
data['FOREIGN_BUY'] = {'val': -8.3}
data['RETAIL_BUY']  = {'val': 6.1}
data['PENSION_BUY'] = {'val': 2.8}
```

**문제:** API 호출 실패 시 구체적인 숫자(연준금리 5.25%, CPI 3.4% 등)를 현재 데이터처럼 보여준다. 한국 기준금리와 US PMI는 애초에 API 연동 자체가 없다. 시장 상황이 바뀌어도 대시보드에는 과거 특정 시점의 값이 영구 표시된다.

**해결 방안:**
- API 실패 시 해당 지표를 `N/A`로 표시하고 마지막 업데이트 시각을 함께 표시한다.
- 한국 기준금리는 한국은행 Open API(경제통계시스템, ECOS)를 연동한다.
- US PMI는 FRED의 `NAPM` 시리즈를 통해 무료로 조회 가능하다.
- 스텔한 데이터임을 표시하는 `is_stale: bool` 플래그를 데이터 구조에 추가한다.

---

### 2-4. yfinance 실패 시 모든 시장 지표가 0.0 🟠 HIGH

**파일:** `dashboard/components/macro_tab.py` · 라인 76–77

```python
data[key] = {'val': 0.0, 'change': 0.0, 'direction': 'neu', 'sign': '—', 'change_str': "0.0%"}
```

**문제:** DXY, VIX, WTI, 금, US10Y 등 전체 yfinance 조회 실패 시 모두 0으로 설정된다. 0이 표시되면 지표가 없는 것인지 실제 0인지 구분이 불가능하다.

**해결 방안:** `None` 또는 `"—"` 을 사용하고 UI에서 데이터 없음을 명시적으로 렌더링한다.

---

### 2-5. 외국인 순매수 방향 지표 로직 반전 🟠 HIGH

**파일:** `dashboard/components/macro_tab.py` · 라인 341

```python
<div class="dot {'dn' if data['FOREIGN_BUY']['val'] > 0 else 'up'}">스마트머니 동향</div>
```

**문제:** 외국인이 순매수(양수)일 때 `dn`(하락 화살표)가, 순매도(음수)일 때 `up`(상승 화살표)가 표시된다. 완전히 반전된 신호다.

**해결 방안:** 조건을 `'up' if data['FOREIGN_BUY']['val'] > 0 else 'dn'`으로 수정한다.

---

### 2-6. 성장주 분석 폴백 데이터가 가짜 재무 수치 🟠 HIGH

**파일:** `src/analysis/growth_stock_finder.py` · 라인 392–405

```python
def _get_fallback_data(self, symbols):
    return [
        GrowthStock(symbol="439090", name="하나마이크론",
                    growth_score=8.5, revenue_growth=35.2, profit_margin=12.5),
        GrowthStock(symbol="SMCI",   name="Super Micro Computer",
                    growth_score=8.7, revenue_growth=45.0, profit_margin=8.5),
    ]
```

**문제:** yfinance 사용 불가 시 growth_score, revenue_growth, profit_margin 등 모든 수치가 개발자가 직접 입력한 임의의 숫자다. 사용자는 이것이 실제 분석 결과인 줄 알고 투자 판단에 활용할 수 있다.

**해결 방안:** 폴백 데이터 메서드 자체를 제거하고 데이터 없음 상태를 명시적으로 반환한다. 대안 데이터 소스(FinanceDataReader, KRX Open API 등)를 구현한다.

---

### 2-7. 자산 추이 그래프 미구현 🟡 MEDIUM

**파일:** `dashboard/components/overview_tab.py` · 라인 24–25

```python
# 통합 차트 (추후 구현: 자산 추이 DB 연동 필요)
st.info("자산 추이 그래프는 데이터 누적 후 제공됩니다.")
```

**문제:** 포트폴리오 가치 추이가 핵심 대시보드 기능임에도 완전히 비어 있다.

**해결 방안:** `src/utils/database.py`의 SQLite에 포트폴리오 스냅샷 테이블을 생성하고, 매매 루프 종료 시마다 총자산을 기록한 뒤 이 데이터를 차트로 표시한다.

---

### 2-8. 거시경제 알림 임계값 전체 하드코딩 🟡 MEDIUM

**파일:** `dashboard/components/macro_tab.py` · 라인 272, 286, 293, 307

```python
{'b-red' if data['DXY']['val']   > 103  else 'b-amb'}   # DXY
{'b-red' if data['US10Y']['val'] > 4.5  else 'b-grn'}   # 미국 10년물
{'b-red' if data['VIX']['val']   > 30   else 'b-amb'}   # VIX
{'b-red' if data['KRW']['val']   > 1400 else 'b-amb'}   # 원달러
```

**문제:** 경보 임계값(DXY 103, 10년물 4.5%, VIX 30 등)이 전혀 설정 파일 없이 소스코드에 박혀 있다.

**해결 방안:** `config/trading.yaml`에 `dashboard.thresholds` 섹션을 만들고 해당 값들을 이동한다.

---

## 3. 전략 — 금융 수식 오류 및 룩어헤드 바이어스

### 3-1. RSI 계산에 Wilder's EMA 대신 SMA 사용 🟠 HIGH

**파일:** `src/strategies/rsi.py` · 라인 56–57

```python
# "Wilder's smoothing" 주석이 있으나 실제로는 SMA
avg_gain = gain.rolling(window=self.period, min_periods=1).mean()
avg_loss = loss.rolling(window=self.period, min_periods=1).mean()
```

**문제:** Wilder의 RSI는 반드시 지수이동평균(alpha=1/period)을 사용해야 한다. SMA를 사용하면 표준 RSI와 수치가 달라지고 과매수/과매도 신호가 표준 트레이딩 플랫폼과 일치하지 않는다.

**해결 방안:** `gain.ewm(com=self.period - 1, adjust=False).mean()` 형태의 EMA로 교체한다.

---

### 3-2. 볼린저 밴드 매수 임계값 1% 근접 기준 하드코딩 🟡 MEDIUM

**파일:** `src/strategies/exit_strategies.py` · 라인 76

```python
if curr_price <= curr_lower * 1.01:  # 1% 여유
```

**문제:** 하단 밴드 1% 이내를 매수 조건으로 쓰는 것은 근거가 없으며, 시장/종목별로 다르게 설정해야 한다.

**해결 방안:** 이 비율을 `BollingerStrategy` 생성자 파라미터로 분리하고 `config/strategies.yaml`에서 설정 가능하게 한다.

---

### 3-3. MinScoreExit 로직에 빈 줄만 있는 불완전 코드 🟡 MEDIUM

**파일:** `src/strategies/exit_strategies.py` · 라인 268–270

```python
score = context.current_score

            # 빈 줄 두 개 — 로직 비어 있음
if score == 5.0 and self._current_scores:
```

**문제:** 코드 블록 중간에 로직 없이 공백만 있어 점수 기반 청산이 제대로 작동하지 않는다.

**해결 방안:** 해당 블록의 실제 의도를 명확히 하고, 빠진 조건 분기를 채워 넣는다.

---

## 4. ML/RL — 미초기화 및 학습 미구현

### 4-1. 룩어헤드 바이어스 — 미래 가격으로 레이블 생성 🔴 CRITICAL

**파일:** `src/strategies/ml_strategy.py` · 라인 139

```python
df['future_return'] = df['close'].shift(-forward_days) / df['close'] - 1
df['label'] = 0
df.loc[df['future_return'] > threshold, 'label'] = 1
```

**문제:** `shift(-forward_days)`는 미래 가격을 현재 시점 레이블에 끌어당기는 것이다. 이 레이블로 훈련된 모델은 훈련 과정에서 미래 정보를 학습하므로, 백테스트 결과는 과대 추정되고 실전에서는 전혀 다른 성과를 낸다. 이것은 퀀트 전략 개발에서 가장 치명적인 오류 중 하나다.

**해결 방안:** 레이블 생성은 허용하되, **훈련 데이터를 시간 순서 기준으로 과거 구간만 사용**해야 한다. Walk-Forward 방식으로 훈련/검증 분리를 강제하고, 레이블 생성 시 `shift(-forward_days)`는 그 자체로는 문제없으나 **훈련 데이터셋에서 마지막 `forward_days`개 행을 제거**해야 한다.

---

### 4-2. `is_trained` 속성 미초기화 → AttributeError 🔴 CRITICAL

**파일:** `src/strategies/ml_strategy.py` · 라인 221, 303, 389, 507, 576

```python
# RandomForestStrategy, GradientBoostingStrategy, LSTMStrategy 공통
def generate_signals(self, df):
    if not self.is_trained:   # ← train() 호출 전이면 AttributeError
```

**문제:** `MLStrategy.__init__`에서 `self.is_trained = False`를 초기화하지 않아 `train()` 호출 전에 `generate_signals()`가 실행되면 `AttributeError`가 발생한다.

**해결 방안:** 모든 ML 전략 `__init__`에 `self.is_trained = False`를 추가한다. `LSTMStrategy`(라인 507)에도 동일하게 적용한다.

---

### 4-3. LSTM 모델 로딩 완전 비동작 🔴 CRITICAL

**파일:** `src/strategies/ml_strategy.py` · 라인 627–629

```python
if self.model is None:
    pass  # 아무것도 하지 않음 — model이 None인 채로 유지

if self.model:  # 항상 False — 모델 로딩 불가
    self.model.load_state_dict(torch.load(filepath))
```

**문제:** `pass` 때문에 `self.model`은 영원히 `None`이고 그 아래 `if self.model`은 항상 `False`가 된다. LSTM 모델은 어떤 상황에서도 저장된 가중치를 불러올 수 없다.

**해결 방안:** `model`이 `None`일 때 메타데이터(input_size 등)를 함께 저장/로드하여 모델 구조를 복원한 뒤 `load_state_dict`를 호출하는 로직을 구현한다.

---

### 4-4. 모델 훈련 자체가 시뮬레이션 🔴 CRITICAL

**파일:** `src/train/trainer.py` · 라인 81–83

```python
logger.info("모델 학습 진행 중... (Simulated)")
# strategy.train(X, y)   # 주석 처리되어 있음
strategy.is_trained = True  # 학습 없이 플래그만 True로 설정
```

**문제:** 실제 훈련 코드가 주석 처리되어 있고, 훈련 없이 `is_trained = True`만 설정한다. 이 `trainer.py`로 "훈련"된 모델은 가중치가 없는 껍데기다.

**해결 방안:** `strategy.train(X, y)` 호출을 복원하고, 훈련 완료 후 모델을 `src/ml/registry.py`를 통해 저장하는 파이프라인을 완성한다.

---

### 4-5. Sharpe Ratio 연율화 수식 오류 🟠 HIGH

**파일:** `src/ml/tuning.py` · 라인 382

```python
sharpe_ratio = (np.mean(returns) / np.std(returns)) * np.sqrt(252 / self.test_period)
```

**문제:** `sqrt(252 / test_period)` 대신 `sqrt(252)`를 곱해야 한다. 일별 수익률의 연율화 공식은 `(평균 / 표준편차) × sqrt(252)`다. `test_period=21`이면 현재 코드는 Sharpe가 3.46배 과대 계산된다.

**해결 방안:** `np.sqrt(252)` 고정값으로 수정한다.

---

### 4-6. RL 전략의 Sharpe가 거래별 수익률로 계산됨 🟠 HIGH

**파일:** `src/ml/rl_strategy.py` · 라인 279

```python
sharpe_ratio = np.mean(self.returns) / np.std(self.returns) * np.sqrt(252)
```

**문제:** `self.returns`가 **거래별** 수익률 리스트인데 일별 252거래일로 연율화하고 있다. 거래 건수와 일수가 다르므로 이 Sharpe는 의미가 없다.

**해결 방안:** 일별 포트폴리오 가치 변화로 Sharpe를 계산하도록 변경한다.

---

### 4-7. GA 최적화 테스트에 시드 없는 랜덤 데이터 사용 🟡 MEDIUM

**파일:** `src/optimization/genetic.py` · 라인 92–101

```python
if __name__ == "__main__":
    df = pd.DataFrame({
        'Close': np.cumsum(np.random.normal(0, 1, 200)) + 100  # 시드 없음
    })
```

**문제:** 재현 불가능한 랜덤 데이터로 최적화 테스트를 수행한다. 결과가 실행마다 달라져 파라미터 평가에 의미가 없다.

**해결 방안:** `np.random.seed(42)` 설정 또는 실제 과거 데이터를 사용한다.

---

### 4-8. 유전 알고리즘 수렴 비효율 — 제약 조건 미적용 🟢 LOW

**파일:** `src/optimization/genetic.py` · 라인 52–53

```python
self.toolbox.register("mutate", tools.mutUniformInt,
    low=[5, 21, ...], up=[20, 60, ...], indpb=0.2)
```

**문제:** `short_period`와 `long_period`의 범위가 겹쳐(5~20 vs 21~60) 크로스오버 연산 이후 `short >= long`인 개체가 생성된다. 이 개체들은 평가 시에만 패널티를 받아 불필요한 세대 낭비가 발생한다.

**해결 방안:** 교차 후 `short < long` 조건을 강제하는 수리 함수(repair function)를 등록한다.

---

## 5. 백테스트 엔진 — 미완성 지표 및 수식 오류

### 5-1. CAGR, 승률이 항상 0.0 🟠 HIGH

**파일:** `src/backtest/engine.py` · 라인 312–315

```python
return BacktestResult(
    total_return=total_return,
    cagr=0.0,      # TODO: 구현 필요
    sharpe_ratio=sharpe_ratio,
    win_rate=0.0,  # TODO: 매매 내역 기반 계산
)
```

**문제:** CAGR과 승률이 항상 0이다. 이 두 지표가 없으면 전략의 실질적 평가가 불가능하다.

**해결 방안:**
- CAGR: `(최종자산 / 초기자산) ** (252 / 총거래일수) - 1`
- 승률: 거래 기록에서 수익 거래 수 / 전체 거래 수 계산

---

### 5-2. 포지션 사이징 95%로 하드코딩 🟡 MEDIUM

**파일:** `src/backtest/engine.py` · 라인 188

```python
target_amount = self.portfolio.cash * 0.95  # 고정 95%
```

**문제:** 포지션 크기 전략을 다르게 테스트할 수 없다.

**해결 방안:** `BacktestEngine.__init__`에 `position_size_pct: float = 0.95` 파라미터로 분리한다.

---

### 5-3. 수수료 계산 방식 오류 🟡 MEDIUM

**파일:** `src/optimization/evaluator.py` · 라인 112, 118

```python
strategy_ret[i] -= self.fee  # 수익률에서만 차감
```

**문제:** 실거래에서는 수수료가 **매수 자금에서** 차감되므로 포지션 가치가 줄어든다. 현재 코드는 수익률에서 단순 빼는 방식이라 포지션 가치가 부풀려진다. 수수료 효과가 과소 계산되어 전략이 실제보다 좋아 보인다.

**해결 방안:** 매수 시 `quantity = floor((cash - fee) / price)` 방식으로 수수료를 자금에서 먼저 차감한다.

---

## 6. 브로커 및 주문 — 스텁 코드 및 런타임 크래시

### 6-1. KiwoomBroker · ShinhanBroker 전체 NotImplementedError 🔴 CRITICAL

**파일:** `src/broker/kiwoom.py` · 라인 18, 21, 24, 27, 30
**파일:** `src/broker/shinhan.py` · 라인 17, 20, 23, 26, 29

```python
def get_current_price(self, symbol: str) -> float:
    raise NotImplementedError("Kiwoom API not available.")

def buy_order(self, ...):
    raise NotImplementedError("Kiwoom API not available.")
# ... 5개 메서드 모두 동일
```

**문제:** 두 브로커는 모든 핵심 메서드가 `NotImplementedError`다. `BrokerFactory`에서 선택 가능한 상태로 노출되어 있어 설정 실수로 선택되면 첫 API 호출에서 즉시 크래시가 발생한다.

**해결 방안:** BrokerFactory에서 KIS 외의 브로커를 명시적으로 비활성화하거나, 미구현 브로커를 `broker/stubs/` 디렉토리로 이동하고 생산 코드에서 제외한다.

---

### 6-2. `cancel_order` 메서드가 KISAPIClient에 없음 🔴 CRITICAL

**파일:** `src/trader/order_manager.py` · 라인 114

```python
self.api.cancel_order(order.order_id)  # API에 cancel_order 구현 필요
```

**문제:** 주문 실패 시 보상 트랜잭션으로 취소를 시도하지만 `KISAPIClient`에 이 메서드가 없다. 주문 오류 발생 시 보상 로직 실행 중 `AttributeError`로 2차 크래시가 발생한다.

**해결 방안:** KIS API의 주문 취소 엔드포인트(`/uapi/domestic-stock/v1/trading/order-rvsecncl`)를 `KISAPIClient`에 구현한다.

---

### 6-3. DB 보상 트랜잭션 pass로 비어 있음 🟠 HIGH

**파일:** `src/trader/order_manager.py` · 라인 120

```python
elif step == "DB_RECORDED":
    # DB 기록 삭제 또는 '취소됨' 마킹
    pass  # 아무것도 실행되지 않음
```

**문제:** 주문 실패 시 DB에 남는 불완전 레코드가 정리되지 않아 상태 불일치가 누적된다.

**해결 방안:** `database.py`의 주문 상태를 `CANCELLED`로 업데이트하는 메서드를 호출한다.

---

### 6-4. KIS 브로커 `get_daily_price` 빈 리스트 반환 🟠 HIGH

**파일:** `src/broker/kis.py` · 라인 36–38

```python
# TODO: KIS API Client에 일봉 조회 기능 추가 필요
self.logger.warning("KISBroker.get_daily_price not implemented yet.")
return []  # 빈 리스트 반환
```

**문제:** 일봉 데이터를 의존하는 전략은 빈 DataFrame으로 실행되어 신호를 생성하지 못하지만 오류 없이 조용히 실패한다.

**해결 방안:** KIS API `/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice`를 `KISAPIClient`에 구현하고 이를 호출한다.

---

## 7. 실시간 매매 엔진 — 미구현 메서드 호출

### 7-1. `CircuitBreaker.call()` 메서드 없음 → 즉시 크래시 🔴 CRITICAL

**파일:** `src/live/engine.py` · 라인 252–254, 293–294, 321–322, 365–366

```python
df = self.circuit_breaker.call(
    self._fetch_price_data, symbol
)
```

**파일:** `src/utils/circuit_breaker.py`
**문제:** `CircuitBreaker` 클래스에 `call()` 메서드가 존재하지 않는다. `LiveTradingEngine`을 시작하면 첫 번째 가격 조회에서 `AttributeError`가 발생하여 실시간 매매 엔진 전체가 동작하지 않는다.

**해결 방안:** `CircuitBreaker`에 `call(func, *args)` 메서드를 구현한다. 이 메서드는 `CLOSED` 상태이면 함수를 실행하고, `OPEN` 상태이면 호출을 차단한다.

---

### 7-2. `get_daily_price_history` 메서드 없음 🔴 CRITICAL

**파일:** `src/live/engine.py` · 라인 282

```python
prices = self.api_client.get_daily_price_history(symbol, start_date, end_date)
```

**문제:** `KISAPIClient`에 이 메서드가 없다. 초기화 과정에서 `AttributeError` 발생.

**해결 방안:** `api_client.py`에 일별 가격 이력 조회 메서드를 구현한다.

---

### 7-3. 시작 날짜 2024-01-01 하드코딩 🟠 HIGH

**파일:** `src/live/engine.py` · 라인 280

```python
start_date = "20240101"
```

**문제:** 가격 이력을 항상 2024년 1월 1일부터 조회한다. 2025년 이후에는 현재 시점 대비 1년 이상의 불필요한 데이터를 요청하거나 데이터가 누락될 수 있다.

**해결 방안:** `(datetime.now() - timedelta(days=365)).strftime("%Y%m%d")`로 동적으로 계산한다.

---

## 8. 트레이더 및 자가복구 — 목업 구현

### 8-1. 자가복구 엔진이 실제 주문 API를 호출하지 않음 🔴 CRITICAL

**파일:** `src/trader/self_healing.py` · 라인 296–298

```python
# 시뮬레이션용 mock
logger.info(f"주문 제출: {context.side} {context.symbol} {context.quantity}주")
return f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}"  # 가짜 주문 ID
```

**문제:** 자가복구 엔진의 `_submit_order()`가 KIS API를 호출하지 않고 가짜 주문 ID를 반환한다. 장애 복구 시 실제 주문이 전혀 제출되지 않는다.

**해결 방안:** 실제 브로커 인스턴스를 `SelfHealingEngine`에 주입하고, `_submit_order()`에서 브로커의 `buy_order()` / `sell_order()`를 호출한다.

---

### 8-2. 복구 액션 핸들러 전체 pass 🟠 HIGH

**파일:** `src/trader/self_healing.py` · 라인 342–353

```python
if action.action_type == "CANCEL_REMAINING":
    pass  # 잔량 취소 API 호출 미구현

elif action.action_type == "CANCEL_ALL":
    pass  # 전량 취소 API 호출 미구현
```

**문제:** 자가복구 엔진이 복구 액션을 결정해도 실제 실행은 아무것도 이루어지지 않는다.

**해결 방안:** `cancel_order` API 구현 후 각 액션 타입에 맞는 취소/재주문 로직을 연결한다.

---

### 8-3. ML 전략 통합 주석 처리 🟡 MEDIUM

**파일:** `src/trader/auto_trader.py` · 라인 318–320

```python
# TODO: ML 모델을 이용해 all_results의 점수를 재조정하거나 필터링
# 예: self._ml_strategy.predict(df)
logger.info("ML 전략 적용 (현재는 로직 통합 중... 기본 Selector 결과 사용)")
```

**문제:** ML 신호 필터가 실제로는 적용되지 않는다. 로그만 남고 기본 Selector 결과만 사용된다.

**해결 방안:** ML 모델 예측 결과를 Selector 결과와 앙상블하는 가중 스코어링 로직을 구현한다.

---

### 8-4. 시장 레짐 감지가 전략에 반영되지 않음 🟡 MEDIUM

**파일:** `src/trader/auto_trader.py` · 라인 295

```python
# TODO: 레짐에 따른 전략 파라미터(현금 비중 등) 조정
```

**문제:** 레짐 감지기가 현재 시장 상태를 분류하지만 그 결과가 전략 파라미터나 포지션 크기에 전혀 반영되지 않는다.

**해결 방안:** 레짐별 파라미터 매핑을 `config/trading.yaml`에 정의하고 레짐 변화 시 AutoTrader가 이를 반영하도록 한다.

---

### 8-5. 손절/청산 파라미터 전부 하드코딩 🟡 MEDIUM

**파일:** `src/trader/auto_trader.py` · 라인 91–94

```python
self.exit_strategy = CompositeExitStrategy([
    FixedStopLoss(stop_pct=-0.07),
    PercentTrailingStop(activation_pct=0.10, trail_pct=0.05),
    MinScoreExit(min_score=1.0),
])
```

**문제:** 손절(-7%), 트레일링 스탑(+10% 이후 -5%) 등이 소스코드에 고정되어 있다. 리스크 허용도 변경 시 코드 수정이 필요하다.

**해결 방안:** 이 파라미터들을 `config/trading.yaml`의 `exit_strategy` 섹션으로 이동한다.

---

## 9. 데이터 클라이언트 — 무음 실패 및 세션 오류

### 9-1. 현재가 파싱 실패 시 0.0 반환 🔴 CRITICAL

**파일:** `src/data/api_client.py` · 라인 220

```python
logger.error(f"현재가 응답 파싱 오류: {e}")
return 0.0  # 가짜 현재가 반환
```

**문제:** 가격이 0.0이면 매수 수량 계산 시 0 또는 무한대가 되고, 수익률 계산도 잘못된다. 전략은 오류 없이 0원짜리 가격으로 계속 동작한다.

**해결 방안:** 예외를 상위로 전파하거나, 명시적인 `None`을 반환하고 호출 측에서 `None` 처리를 강제한다.

---

### 9-2. 종목 선택기 3곳에 `except: pass` 🟠 HIGH

**파일:** `src/strategies/selector.py` · 라인 113, 120, 201

```python
except:
    pass  # 모든 예외 무시
```

**문제:** 어떤 예외가 발생해도 로그조차 없이 무시된다. 데이터 처리 실패를 알 방법이 없다.

**해결 방안:** `except Exception as e: logger.warning(f"...")` 로 교체한다.

---

### 9-3. WebSocket 구독 메서드가 stub 🟠 HIGH

**파일:** `src/data/websocket_client.py` · 라인 104

```python
async def _subscribe_symbols(self, websocket, symbols):
    # 구독 메시지 포맷은 API 문서 참조
    pass  # 실제 구독 요청 미전송
```

**문제:** WebSocket 연결은 맺어지지만 종목 구독 메시지가 전송되지 않아 실시간 데이터를 수신하지 못한다.

**해결 방안:** KIS WebSocket API 문서의 `H0STCNT0` 등록 포맷에 맞는 구독 메시지를 구현한다.

---

### 9-4. WebSocket URL 세 개가 서로 충돌 🟡 MEDIUM

**파일:** `src/data/websocket_client.py` · 라인 26, 31, 33

```python
self.ws_url = "ws://ops.koreainvestment.com:21000"  # 실전
if Config.IS_MOCK:
    self.ws_url = "ws://ops.koreainvestment.com:31000"  # 모의 (공식 URL 확인 필요)
    self.ws_url = "ws://ops.koreainvestment.com:21000"  # 보통 공용
```

**문제:** 세 줄이 순서대로 실행되면 마지막 줄이 항상 덮어쓴다. 모의 모드에서도 실전 URL로 접속하게 된다.

**해결 방안:** KIS 공식 문서를 확인하여 모의/실전 URL을 각각 단일 상수로 정의한다.

---

### 9-5. 비동기 API 클라이언트 세션 즉시 소멸 🟡 MEDIUM

**파일:** `src/data/async_api_client.py` · 라인 95–100

```python
if not self.session:
    async with aiohttp.ClientSession() as session:
        self.session = session
        # context 블록 종료 시 세션이 닫힘
```

**문제:** `async with` 블록이 끝나면 세션이 닫혀 이후 사용 시 `ClientSession is closed` 오류가 발생한다.

**해결 방안:** 세션을 `connect()`/`close()` 메서드나 `async with` 컨텍스트 매니저로 생명주기를 명시적으로 관리한다.

---

## 10. 설정 및 스크립트 — 불일치 및 하드코딩

### 10-1. 환경변수 이름 불일치 (`KIS_ACCOUNT_NO` vs `KIS_ACCOUNT_NUMBER`) 🟠 HIGH

**파일별 사용 현황:**

| 파일 | 사용 변수명 |
|------|-------------|
| `.env.example` | `KIS_ACCOUNT_NUMBER` |
| `src/config.py` | `KIS_ACCOUNT_NUMBER` |
| `scripts/run_backtest.py` | `KIS_ACCOUNT_NUMBER` |
| `scripts/run_scheduler.py` | `KIS_ACCOUNT_NO` ← 다름 |
| `scripts/init_dashboard_data.py` | `KIS_ACCOUNT_NO` ← 다름 |
| `scripts/experiments/run_auto_trading.py` | `KIS_ACCOUNT_NO` ← 다름 |
| `scripts/experiments/run_us_trading.py` | `KIS_ACCOUNT_NO` ← 다름 |

**문제:** `.env`에 `KIS_ACCOUNT_NUMBER`로 설정해도 일부 스크립트는 `None`을 받아 인증이 실패한다.

**해결 방안:** `src/config.py`의 `Config.KIS_ACCOUNT_NUMBER`를 단일 소스로 정하고 모든 스크립트에서 `Config.KIS_ACCOUNT_NUMBER`를 직접 참조한다.

---

### 10-2. 하드코딩된 폴백 유니버스 — 설정 오류 마스킹 🟠 HIGH

**파일:** `scripts/run_trading.py` · 라인 119–126

```python
universe = Config.load_universe().get(market, [])
if not universe:
    logger.warning("유니버스 설정 없음. 기본값 사용.")
    if market == "KR":
        universe = ["005930", "000660", "035420", "035720", "005380"]
    else:
        universe = ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL"]
```

**추가 파일들:** `scripts/experiments/run_us_trading.py`, `scripts/experiments/run_auto_trading.py`는 `Config.load_universe()`를 아예 호출하지 않고 하드코딩된 목록만 사용한다.

**문제:** `universe.json`이 없거나 잘못되어도 경고만 하고 계속 실행한다. 사용자는 의도치 않은 5개 종목으로 실제 매매가 이루어질 수 있다.

**해결 방안:** 유니버스 로딩 실패 시 예외를 발생시키고 종료한다. 실험용 스크립트도 동일한 `Config.load_universe()`를 사용하도록 통일한다.

---

### 10-3. 하드코딩된 날짜 — 미래에 동작 불능 🟡 MEDIUM

| 파일 | 라인 | 하드코딩 값 |
|------|------|------------|
| `scripts/experiments/simulate_200k.py` | 67 | `datetime(2026, 2, 5)` |
| `scripts/experiments/backtest_2025.py` | 60, 99 | `"2024-06-01"` ~ `"2025-12-31"` |
| `scripts/experiments/backtest_2025_compare.py` | 251, 274 | `"2025-01-01"`, `"2024-12-31"` |
| `scripts/run_backtest.py` | 23 | `default="20240101"` |

**해결 방안:** `datetime.now() - timedelta(days=N)` 방식의 동적 기본값을 사용하고, 날짜를 CLI 인수로 받도록 변경한다.

---

### 10-4. `--dry-run` 기본값 로직 혼란 🟡 MEDIUM

**파일:** `scripts/run_trading.py` · 라인 325

```python
parser.add_argument('--dry-run', action='store_true', default=True)
```

**문제:** `action='store_true'`이면서 `default=True`는 `--dry-run` 플래그를 추가해도 추가하지 않아도 항상 `True`다. 실제 매매를 실행하는 방법이 없다.

**해결 방안:** `--live` 플래그를 만들어 `action='store_true', default=False`로 설정하고, `--live` 없으면 dry-run으로 동작하게 한다.

---

### 10-5. 티커 형식 불일치 (`.KS` 접미사 유무) 🟡 MEDIUM

| 파일 | 형식 예시 |
|------|----------|
| `config/universe.json` | `"005930.KS"` |
| `config/trading.yaml` (watchlist) | `"005930"` |
| `scripts/experiments/run_auto_trading.py` | `"005930.KS"` |

**문제:** 코드가 두 형식을 모두 받아들이는지 명시적 처리 없이 혼용되어 있어 티커 조회 실패가 발생할 수 있다.

**해결 방안:** 진입점에서 티커 형식을 정규화하는 유틸리티 함수를 만들고 모든 로딩 경로에서 호출한다.

---

### 10-6. 초기 자본금이 3개 파일에 각각 정의 🟡 MEDIUM

| 파일 | 라인 | 값 |
|------|------|-----|
| `config/trading.yaml` | 108 | `initial_capital: 10000000` |
| `config/trading.yaml` | 139 | `capital: 10000000` |
| `config/trading.yaml` | 153 | `initial_capital: 10000000` |
| `config/strategies.yaml` | 154 | `initial_capital: 10000000` |

**해결 방안:** `config/trading.yaml` 최상위에 `default_capital: 10000000` 하나만 정의하고 나머지는 이를 참조한다.

---

### 10-7. 수수료율이 두 설정 파일에 중복 정의 🟢 LOW

**파일:** `config/trading.yaml` · 라인 109 / `config/strategies.yaml` · 라인 154 — 둘 다 `0.00015`

**해결 방안:** `config/trading.yaml`에만 정의하고 백테스트 코드도 같은 값을 참조한다.

---

### 10-8. API 키 없는 스크립트 실행 시 암호화 오류 🟢 LOW

**파일:** `src/utils/security.py` · 라인 29

```python
# TODO: Set file permissions to secure readable only by owner
```

**문제:** 암호화 키 파일이 기본 권한으로 생성되어 Windows에서는 다른 사용자도 접근 가능하다.

**해결 방안:** 파일 생성 후 `os.chmod(key_path, 0o600)` 호출 (Linux/Mac) 또는 Windows ACL 설정을 추가한다.

---

## 11. 해결 방안 우선순위 로드맵

### 🔴 즉시 수정 (실전 투자 전 필수)

| 순위 | 작업 | 파일 |
|------|------|------|
| 1 | `CircuitBreaker.call()` 메서드 구현 | `src/utils/circuit_breaker.py` |
| 2 | `KISAPIClient.cancel_order()` 구현 | `src/data/api_client.py` |
| 3 | `KISAPIClient.get_daily_price_history()` 구현 | `src/data/api_client.py` |
| 4 | 자가복구 `_submit_order()`에 실제 API 연결 | `src/trader/self_healing.py` |
| 5 | 복구 액션 핸들러 `pass` 교체 | `src/trader/self_healing.py` |
| 6 | Kiwoom/Shinhan 스텁 브로커 생산 코드에서 격리 | `src/broker/factory.py` |
| 7 | `--dry-run` 기본값 로직 수정 | `scripts/run_trading.py` |
| 8 | 환경변수 이름 `KIS_ACCOUNT_NO` → `KIS_ACCOUNT_NUMBER` 통일 | 전체 scripts/ |

### 🟠 단기 수정 (백테스트 신뢰성)

| 순위 | 작업 | 파일 |
|------|------|------|
| 9 | 룩어헤드 바이어스 제거 (훈련 데이터 마지막 N행 제거) | `src/strategies/ml_strategy.py` |
| 10 | `is_trained = False` 초기화 추가 | `src/strategies/ml_strategy.py` |
| 11 | LSTM 모델 로드 로직 구현 | `src/strategies/ml_strategy.py` |
| 12 | 모델 훈련 코드 주석 해제 + 실제 학습 연결 | `src/train/trainer.py` |
| 13 | RSI EMA 방식으로 수정 | `src/strategies/rsi.py` |
| 14 | CAGR 및 승률 계산 구현 | `src/backtest/engine.py` |
| 15 | Sharpe Ratio 수식 수정 (`sqrt(252)` 고정) | `src/ml/tuning.py` |
| 16 | WebSocket 구독 메서드 구현 | `src/data/websocket_client.py` |
| 17 | `order_manager.py` DB 보상 로직 구현 | `src/trader/order_manager.py` |

### 🟡 중기 개선 (대시보드 신뢰성)

| 순위 | 작업 | 파일 |
|------|------|------|
| 18 | API 실패 시 N/A 표시 (하드코딩 폴백 제거) | `dashboard/components/macro_tab.py` |
| 19 | AutoML 실제 `optimizer.evolve()` 연결 | `dashboard/app.py` |
| 20 | 외국인 순매수 방향 화살표 반전 수정 | `dashboard/components/macro_tab.py` |
| 21 | 성장주 폴백 데이터 제거 | `src/analysis/growth_stock_finder.py` |
| 22 | 포트폴리오 기본값을 0/None으로 변경 | `dashboard/app.py` |
| 23 | 자산 추이 SQLite 저장 및 차트 구현 | `dashboard/components/overview_tab.py` |
| 24 | 비동기 API 세션 생명주기 관리 | `src/data/async_api_client.py` |
| 25 | 티커 형식 정규화 유틸리티 추가 | 공통 유틸리티 |
| 26 | 초기 자본금 설정 단일화 | `config/trading.yaml` |
| 27 | 하드코딩 날짜를 동적 계산으로 교체 | `scripts/experiments/*.py` |

---

> **참고:** 이 보고서는 코드 구현을 포함하지 않으며, 각 문제의 위치와 원인 분석 및 해결 방향만을 기술합니다.
