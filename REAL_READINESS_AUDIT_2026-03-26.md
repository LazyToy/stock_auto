# Real Readiness Audit

> Date: 2026-03-26
> Scope: `INSPECTION_REPORT.md` 대조 + 현재 소스/테스트/실행 경로 실검토
> Goal: "ML 옵션이나 API 키만 있으면 모의투자 및 백테스팅이 가능한가?"에 대한 현재 기준 판정

---

## 1. 최종 판정

현재 기준으로는 **아직 아니다**.

- 전통 전략 백테스트: **대체로 가능**
- ML 백테스트: **아직 신뢰 불가**
- dry-run 리밸런싱/로그 시뮬레이션: **일부 가능**
- KIS 모의계좌를 통한 실제 주문형 모의투자: **아직 준비 미완료**
- 실시간/live/self-healing 주문 플로우: **준비 미완료**

즉, "API 키만 넣으면 바로 된다" 수준은 아니다.

---

## 2. 현재 바로 되는 것

### 2-1. 전통 전략 백테스트 엔진

- `src/backtest/engine.py`
- `tests/test_backtest.py` 통과

확인 사항:

- `position_size_pct` 구현됨
- `CAGR` 구현됨
- `win_rate` 구현됨
- 기본적인 매수/매도/수수료 반영 동작함

판정:

- **전통 전략 기준 백테스트 엔진 자체는 usable**

### 2-2. 대시보드의 일부 핵심 보완

이미 보고서 이후 수정된 부분:

- `dashboard/app.py`: AutoML이 실제 `optimizer.evolve()`를 호출함
- `dashboard/app.py`: 자산 기본값 1천만원/1만달러 하드코딩 제거
- `dashboard/components/overview_tab.py`: 자산 추이 차트 구현됨

판정:

- 대시보드는 예전 보고서보다 훨씬 나아졌음
- 다만 freshness/threshold 표시 방식은 아직 개선 여지 있음

---

## 3. 지금 당장 막는 핵심 문제

### 3-1. ML 학습 데이터가 종목 경계를 넘어 오염됨

관련 파일:

- `src/train/trainer.py`
- `src/strategies/ml_strategy.py`

핵심 내용:

- 여러 종목 데이터를 `pd.concat`으로 단순 병합
- 그 상태에서 rolling, RSI, 이동평균, `future_return`, `label` 계산
- 결과적으로 종목 A 마지막 줄과 종목 B 첫 줄이 이어진 것처럼 처리됨

영향:

- 학습 데이터 자체가 오염됨
- ML 결과를 신뢰하기 어려움

판정:

- **ML 백테스트/ML 전략 사용을 막는 최상위 결함**

### 3-2. 기본 ML 학습 파이프라인이 저장 단계에서 깨짐

관련 파일:

- `src/train/trainer.py`
- `src/strategies/ml_strategy.py`

핵심 내용:

- `trainer.py`는 학습 후 `strategy.save_model(...)` 호출
- 하지만 `save_model()`은 사실상 `LSTMStrategy`만 가짐
- `RandomForestStrategy`, `GradientBoostingStrategy`는 저장 메서드 없음

실검토:

- `RandomForestStrategy`에 `save_model` 속성 없음 확인

영향:

- 기본값인 `ml_rf` 학습 루틴이 저장 단계에서 중단

판정:

- **ML 운영 경로 즉시 차단**

### 3-3. ML 추론이 현재 시점이 아니라 뒤처진 시점 기준으로 동작할 수 있음

관련 파일:

- `src/strategies/ml_strategy.py`

핵심 내용:

- 예측 시에도 `prepare_features()` 재사용
- 이 과정에서 라벨 생성과 `df.iloc[:-forward_days]` 절단이 같이 들어감

영향:

- 예측 대상이 최신 봉이 아닐 수 있음
- 실전 신호/백테스트 신호가 뒤로 밀릴 수 있음

판정:

- **ML 신호 사용성 저하**

### 3-4. OrderSaga는 현재 코드 기준으로 아예 깨져 있음

관련 파일:

- `src/trader/order_manager.py`
- `src/data/models.py`
- `src/data/api_client.py`

핵심 내용:

- 존재하지 않는 `OrderStatus` import
- `place_order()` 반환값을 dict로 가정
- 실제 `KISAPIClient.place_order()`는 문자열 order id 반환

영향:

- saga 복구 경로 unusable

판정:

- **주문 안정성/복구 플로우 미완성**

### 3-5. Self-healing은 실제 복구 엔진이라기보다 뼈대에 가까움

관련 파일:

- `src/trader/self_healing.py`
- `src/data/api_client.py`

핵심 내용:

- `_monitor_order()`가 항상 `True`
- 주문 취소 호출 시그니처 불일치
- 부분체결/타임아웃/실패를 실제로 관측하지 않음

영향:

- 이름과 달리 실제 자동 복구를 보장하지 못함

판정:

- **실전/모의 주문 안정성에 사용 불가**

### 3-6. 미국장 live 경로는 끝까지 연결되어 있지 않음

관련 파일:

- `src/live/engine.py`
- `src/data/api_client.py`

핵심 내용:

- `get_daily_price_history()`가 KR 엔드포인트 기준
- US sell 주문에서 가격값이 `"None"`이 될 가능성 존재

영향:

- `market="US"` live 경로 신뢰 불가

판정:

- **미국장 live/mock 주문 플로우 미완성**

### 3-7. dry-run과 KIS 모의계좌 주문은 다름

관련 파일:

- `scripts/run_scheduler.py`
- `scripts/experiments/run_auto_trading.py`
- `scripts/experiments/run_us_trading.py`

핵심 내용:

- 여러 엔트리포인트가 `dry_run=True` 고정
- 실제 KIS mock account에 주문을 넣지 않음

영향:

- "모의투자"를 dry-run으로 착각할 수 있음

판정:

- **현재 가능한 것은 주로 로그 기반 시뮬레이션**

---

## 4. 보고서 대비 이미 고쳐진 항목

다음 항목은 `INSPECTION_REPORT.md` 기준으로는 맞았을 수 있지만, 현재 트리에서는 이미 개선됨:

- `dashboard/app.py`: AutoML demo 하드코딩 제거
- `dashboard/app.py`: 자산 기본값 하드코딩 제거
- `dashboard/components/overview_tab.py`: 자산추이 차트 구현
- `src/utils/circuit_breaker.py`: `call()` 메서드 존재
- `src/data/api_client.py`: `cancel_order()` 존재
- `src/data/api_client.py`: `get_daily_price_history()` 존재
- `scripts/run_trading.py`: `--live` 기반 로직으로 dry-run 전환 가능
- `src/strategies/ml_strategy.py`: `is_trained` 초기화 문제 해결
- `src/backtest/engine.py`: `CAGR`, `win_rate`, `position_size_pct` 구현

판정:

- 원 보고서를 그대로 믿고 판단하면 과하게 비관적일 수 있음
- 하지만 **수정된 항목이 있다고 해서 현재 사용 가능 수준이 된 것은 아님**

---

## 5. 테스트 기준 현재 신뢰도

실행 결과 요약:

- `tests/test_backtest.py`: 통과
- `tests/test_ml_strategy.py`: 일부 실패
- `tests/test_api_client.py`: 다수 실패
- `tests/test_circuit_breaker.py`: 일부 실패
- `tests/test_live.py`: 얕은 초기화 수준 검증
- `tests/test_self_healing.py`: 상태 머신/보조 로직 위주
- `tests/test_auto_trader_dry_run.py`: 일반 pytest 테스트라기보다 수동성 강한 스크립트 성격

추가 관찰:

- 통합/E2E 테스트는 mock 비중이 큼
- 실제 KIS client wiring, 주문, 복구, ML 학습/추론 경로를 끝까지 증명하지 못함

판정:

- **테스트가 "실제로 돌아간다"를 증명하는 수준은 아님**

---

## 6. 현재 기준 경로별 사용 가능 판정

### 6-1. 전통 전략 백테스트

판정: **가능**

조건:

- KIS 일봉 조회가 정상 동작해야 함
- 전통 전략만 사용

비고:

- `scripts/run_backtest.py`는 ML 전략을 지원하지 않음

### 6-2. ML 백테스트

판정: **불가 또는 비권장**

이유:

- 학습 데이터 오염
- 저장/로딩 경로 불완전
- 표준 엔트리포인트 미연결
- 추론 시점 뒤틀림

### 6-3. dry-run 리밸런싱

판정: **부분 가능**

이유:

- `AutoTrader.run_daily_routine()` 중심의 로직은 일부 수행 가능
- 다만 외부 데이터 의존성과 일부 보조 경로 오류 존재

### 6-4. KIS 모의계좌 주문형 모의투자

판정: **아직 불가에 가까움**

이유:

- dry-run과 실제 mock order path가 혼재
- 복구/취소/주문 후속관리 경로가 불완전

### 6-5. 실시간/live 주문

판정: **불가**

이유:

- self-healing 미완성
- websocket approval key 미구현
- US 경로 미완성
- 일부 실주문 헬퍼 경로 시그니처 오류

---

## 7. 최소 수정 1순위 목록

목표: **ML 제외하고 "KIS 모의계좌 기반 모의주문" 또는 최소한 "신뢰 가능한 dry-run" 상태 만들기**

1. `src/trader/order_manager.py` 정리
   - 깨진 import 제거
   - API client 반환 계약에 맞게 수정

2. `src/trader/self_healing.py` 수정
   - `_monitor_order()` 실제 체결/주문상태 조회 연결
   - `cancel_order()` 시그니처 맞춤

3. `src/data/api_client.py` 정리
   - KR/US 주문 계약 분리 명확화
   - US market sell path 정정
   - 테스트가 기대하는 request path와 현재 구현 정렬

4. `src/trader/auto_trader.py` 수정
   - `_sell_stock()` 잘못된 `place_order()` 호출 수정
   - live 보조 경로와 main rebalance path 계약 통일

5. `scripts/*` 정리
   - dry-run과 KIS mock order 모드 명시적 분리
   - 운영용 엔트리포인트 하나로 통합

6. `src/utils/logger.py` 보완
   - 파일 핸들러 실패 시 graceful fallback
   - 테스트/권한 제약 환경에서 import 단계 크래시 방지

---

## 8. ML 없이 먼저 모의투자 가능 상태로 만드는 경로

목표: **전통 전략 + KIS mock account 주문까지 연결**

1. `run_trading.py`를 단일 운영 엔트리포인트로 고정
2. `--dry-run` / `--mock-order` / `--live`를 명확히 분리
3. `AutoTrader`의 주문 호출을 하나의 공통 함수로 통일
4. `cancel_order`, 주문조회, 체결조회 API를 실제 복구 루프와 연결
5. KR 시장 기준으로 먼저 완성
6. 그 다음 US 경로 별도 보강

완료 기준:

- KR 기준으로 KIS mock account 주문 성공
- 주문 실패/취소/재시도 경로 동작
- dry-run과 mock-order 결과가 명확히 구분

---

## 9. ML 백테스트를 진짜 되게 만드는 패치 순서

목표: **ML 옵션을 실제 백테스트 가능한 수준으로 승격**

1. 종목별 feature engineering 분리
   - 종목별 rolling/label 생성 후 concat

2. 추론용 feature path 분리
   - 학습용 label 생성 함수와 예측용 feature 함수 분리

3. RF/GB save/load 구현
   - `joblib` 기반 직렬화 추가

4. ML 백테스트 엔트리포인트 추가
   - `scripts/run_backtest.py`에 `ml_rf`, `ml_gb`, `ml_lstm`, `ensemble` 연결

5. Walk-forward를 표준 경로로 승격
   - 단순 holdout이 아니라 시계열 검증 강제

6. 종속성 정리
   - `pyproject.toml`에 `scikit-learn`, `torch`, `deap`, `mlflow`, `scipy` 등 반영

7. 테스트 보강
   - 종목 경계 오염 방지 테스트
   - save/load round-trip 테스트
   - 최신 시점 예측 테스트
   - ML backtest smoke test 추가

완료 기준:

- ML 모델 학습 후 저장/재로딩 가능
- 최신 시점 기준 신호 생성 가능
- ML 전략이 표준 CLI에서 백테스트 가능

---

## 10. 추천 실행 순서

### Phase 1

- 주문/복구/취소 계약 정리
- `AutoTrader` 및 `KISAPIClient` 시그니처 정렬
- 로깅/테스트 import 안정화

목표:

- **KR 기준 mock-order 또는 신뢰 가능한 dry-run 확보**

### Phase 2

- ML 데이터 파이프라인 정리
- RF/GB save/load 구현
- ML backtest CLI 연결

목표:

- **ML 백테스트 실제 사용 가능**

### Phase 3

- websocket approval key
- 실시간 체결 모니터링
- US live 경로 완성

목표:

- **실시간/live 경로 신뢰성 확보**

---

## 11. 결론 한 줄

현재 프로젝트는 **전통 전략 백테스트 엔진은 살아 있지만, ML 백테스트와 주문형 모의투자/실시간 거래는 아직 "구현 완료"라고 보기 어렵다.**
