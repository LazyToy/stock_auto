# 주식 자동매매 시스템

한국투자증권 REST API를 활용한 주식 백테스팅 및 실전 자동매매 시스템입니다.

## ✨ 주요 기능

- 📊 **백테스팅 엔진**: 과거 데이터로 매매 전략 검증
- 🤖 **실전 매매**: 실시간 자동매매 실행
- 📈 **다양한 전략**: 이동평균, 볼린저밴드, RSI, 모멘텀 등
- 🧠 **AI/ML 전략**: RandomForest, GradientBoosting, LSTM, 강화학습(DQN/PPO)
- 💼 **멀티 포트폴리오**: 여러 전략 동시 운영 및 성과 비교
- 🔒 **리스크 관리**: 손절/익절/트레일링 스탑 자동 실행
- 📉 **성과 분석**: 수익률, 샤프비율, MDD 등 상세 지표
- 📱 **텔레그램/카카오톡 알림**: 거래 체결, 손익 알림

### 🆕 V2 신규 기능

- 🩺 **Self-Healing Engine**: 장애 발생 시 자동 복구 + Saga 패턴 보상 트랜잭션
- 📰 **DART 공시 분석**: LLM 기반 실시간 공시 파싱 및 영향 분석
- 💬 **카카오톡 알림**: 원터치 승인 기능이 포함된 모바일 알림
- 📊 **호가창 분석**: Order Flow Intelligence - 기관/외국인 방향 예측
- 💱 **크로스마켓 차익거래**: ADR vs 원주 가격 괴리 분석
- 📝 **감사 로그**: 모든 주문/설정 변경 추적 (Audit Trail)



## 🚀 빠른 시작

### 1. 설치

```bash
# 저장소 클론
cd d:\HY\develop_Project\stock_auto

# 가상환경 활성화
.\stock_auto\Scripts\Activate.ps1

# 필수 패키지 설치 (ML 기능 사용 시)
pip install scikit-learn torch stable-baselines3 gymnasium
```

### 2. 환경 설정

`.env.example` 파일을 `.env`로 복사하고 API 키를 설정하세요:

```env
# 한국투자증권 API
KIS_APP_KEY=발급받은_앱키
KIS_APP_SECRET=발급받은_앱시크릿
KIS_ACCOUNT_NUMBER=계좌번호_8자리
KIS_ACCOUNT_PRODUCT_CODE=01

# 모의투자 모드
TRADING_MODE=mock

# 텔레그램 알림 (선택)
TELEGRAM_BOT_TOKEN=봇토큰
TELEGRAM_CHAT_ID=챗ID
```

---

## 🎯 통합 트레이딩 시스템

### 3가지 운영 모드

통합 스크립트 `scripts/run_trading.py`로 다양한 조합 사용 가능:

| 모드 | 설명 | 사용 사례 |
|------|------|----------|
| `single` | 단일 전략 | 기존 모멘텀 또는 AI 전략 단독 실행 |
| `enhanced` | AI 강화 | 기존 전략 + AI 필터로 신뢰도 향상 |
| `multi` | 멀티 포트폴리오 | 여러 전략 독립 운영 및 성과 비교 |

### 사용 예시

```bash
# 단일 전략 - 모멘텀 (한국)
python scripts/run_trading.py --mode single --strategy momentum --market KR

# 단일 전략 - AI RandomForest (미국)
python scripts/run_trading.py --mode single --strategy ml_rf --market US

# 강화 모드 - 모멘텀 + AI 필터
python scripts/run_trading.py --mode enhanced --strategy momentum --ai-filter ml_rf

# 멀티 포트폴리오 - KR 모멘텀 50% + US AI 50%
python scripts/run_trading.py --mode multi --capital 2000000

# ML 비교 모드 - mock/runtime 비교 리포트
python scripts/run_trading.py --compare-ml --market KR --ml-strategies ml_rf ml_gb ensemble

# 실전 투자 (주의!)
python scripts/run_trading.py --mode single --strategy ml_rf --live
```

### CLI 옵션

| 옵션 | 기본값 | 설명 |
|------|-------|------|
| `--mode` | single | 실행 모드 (single/enhanced/multi) |
| `--market` | KR | 시장 (KR/US) |
| `--strategy` | momentum | 전략 (momentum/value/ml_rf/ml_gb/ensemble) |
| `--ai-filter` | ml_rf | AI 필터 (enhanced 모드) |
| `--capital` | 1000000 | 투자 금액 |
| `--compare-ml` | False | ML 전략 mock/runtime 비교 실행 |
| `--dry-run` | True | 모의투자 |
| `--live` | False | 실전투자 |

ML 런타임 실행 시 `ml_rf`/`ml_gb`/`ensemble` 전략은 `models/` 아래의 최신 저장 모델을 먼저 로드합니다. 저장 모델이 없거나 로드에 실패하면 새 전략 인스턴스로 계속 진행합니다.

---

## 🧠 AI/ML 전략

### 지원 전략

| 전략 | 클래스 | 설명 |
|------|--------|------|
| RandomForest | `RandomForestStrategy` | 앙상블 트리 기반 분류 |
| GradientBoosting | `GradientBoostingStrategy` | 부스팅 기반 분류 |
| LSTM | `LSTMStrategy` | 딥러닝 시계열 예측 |
| Ensemble | `EnsembleMLStrategy` | 여러 모델 결합 |
| DQN | `DQNAgent` | 강화학습 (Deep Q-Network) |
| PPO | `RLTrainer` | 강화학습 (Proximal Policy Optimization) |

### ML 전략 사용

```python
from src.strategies.ml_strategy import EnsembleMLStrategy

# 앙상블 전략 생성
strategy = EnsembleMLStrategy(voting="soft")

# 학습 (과거 데이터)
accuracy = strategy.train_all(historical_df)
print(f"학습 정확도: {accuracy}")

# 매매 신호 생성
signals = strategy.generate_signals(current_df)
```

`scripts/run_trading.py`에서 `ml_rf`/`ml_gb`/`ensemble`를 실행하면 시장/전략에 맞는 최신 저장 모델을 우선 로드하고, 사용 불가하면 안전하게 기본 ML 전략으로 fallback합니다.

### 강화학습 사용

```python
from src.ml.rl_strategy import TradingEnvironment, RLTrainer

# 트레이딩 환경 생성
env = TradingEnvironment(df, initial_capital=10_000_000)

# DQN 에이전트 학습
trainer = RLTrainer(env, agent_type="DQN")
results = trainer.train(n_episodes=100)

# 모델 저장/로드
trainer.save_model("my_dqn_model")
```

### 파라미터 튜닝

```python
from src.ml.tuning import ParameterTuner, WalkForwardBacktester

# GridSearchCV 기반 튜닝
tuner = ParameterTuner(n_splits=5)
result = tuner.tune_grid_search(model, X, y, use_time_series_split=True)
print(f"최적 파라미터: {result.best_params}")

# Walk-Forward 백테스트
backtester = WalkForwardBacktester(train_period=252, test_period=21)
wf_result = backtester.run(df, strategy)
print(backtester.generate_report(wf_result))
```

`scripts/run_backtest.py`의 walk-forward 요약에는 이제 종목(`symbol`)과 백테스트 기간(`start ~ end`)이 함께 출력됩니다.

---

## 💼 멀티 포트폴리오 관리

여러 전략을 독립적으로 운영하고 성과를 비교할 수 있습니다.

```python
from src.portfolio import MultiPortfolioManager, PortfolioConfig

# 매니저 생성 (총 200만원)
manager = MultiPortfolioManager(total_capital=2_000_000)

# 포트폴리오 추가
manager.add_portfolio(PortfolioConfig(
    name="KR_모멘텀",
    strategy_name="MomentumStrategy",
    allocation_pct=50.0,
    market="KR"
))

manager.add_portfolio(PortfolioConfig(
    name="US_AI",
    strategy_name="MLStrategy",
    allocation_pct=50.0,
    market="US"
))

# 성과 리포트
print(manager.generate_report())
```

---

## 📊 2025년 백테스트 결과

각 100만원씩 한국/미국 주식 투자 시뮬레이션:

| 전략 | 총 수익률 | 최종 자산 |
|------|:--------:|----------:|
| **ML (RandomForest)** | **+68.86%** | **3,378,858원** |
| Traditional (모멘텀) | +59.09% | 3,183,449원 |
| Ensemble (기존+ML) | +56.72% | 3,136,036원 |

```bash
# 백테스트 실행
python scripts/backtest_2025_compare.py
```

---

## 📈 웹 대시보드

Streamlit 기반의 웹 대시보드를 통해 수익률, 포트폴리오 현황, 과거 백테스트 결과를 시각적으로 확인할 수 있습니다.

```bash
# 대시보드 실행
streamlit run dashboard/app.py
```

---

## 2026-03 Runtime Notes

### ML Runtime Loading

- Runtime ML trading now tries to load the latest saved model from `models/` for the selected market and strategy.
- If model loading fails, the runtime logs a warning and falls back safely instead of crashing.
- This applies to the ML runtime path used by `scripts/run_trading.py`.

### ML Comparison Mode

- You can compare runtime ML strategies on the mock path with:

```bash
python scripts/run_trading.py --market KR --compare-ml --ml-strategies ml_rf ml_gb ensemble
```

- The comparison report summarizes strategy name, selected symbols, order count, and loaded model path.
- The default execution mode remains conservative: `broker=mock, orders=dry-run`.

### Walk-Forward Backtest Summary

- Walk-forward ML backtest output now includes:
  - `Symbol`
  - `Period`
  - `Predictions`
  - `Trained predictions`
  - `Coverage`
  - `Accuracy`
  - `Retrain count`

- This is available through `scripts/run_backtest.py` when using ML strategies such as `ml_rf`, `ml_gb`, or `ensemble`.

명령어 실행 후 브라우저에서 `http://localhost:8501`로 접속하여 사용할 수 있습니다.

### 매크로 지표 데이터 소스 (Macro Dashboard Data Sources)

대시보드의 글로벌 매크로 및 한국 시장 수급 탭에서 사용되는 실시간 지표들은 다음의 외부 소스를 통해 실시간 혹은 일/월별로 자동 수집됩니다:

| 분류 | 지표명 | 출처 (API) | 비고 |
|------|--------|------------|------|
| **에너지·원자재** | WTI 유가, 금(Gold), 은(Silver) | `yfinance` (Yahoo Finance) | 실시간 (Ticker: `CL=F`, `GC=F`, `SI=F`) |
| **글로벌 인덱스** | 달러 인덱스(DXY), 미 10년물, VIX | `yfinance` (Yahoo Finance) | 실시간 (Ticker: `DX-Y.NYB`, `^TNX`, `^VIX`) |
| **통화·환율** | 원/달러 환율 (KRW) | `yfinance` (Yahoo Finance) | 실시간 (Ticker: `KRW=X`) |
| **거시경제지표** | 미/한 기준금리, 실업률, 신용 스프레드 | `fredapi` (미국 연준 FRED) / `pandas_datareader` | FRED API Key 필요 |
| **경기 선행지표** | 미국 CPI, 시카고연준 종합지수(CFNAI) | `fredapi` (미국 연준 FRED) | 월간 발표치 조회 |
| **경기 선행지표** | OECD 경기선행지수 (CLI) | `requests` (OECD SDMX JSON API) | API Key 없이 무료 조회 |
| **한국 주식시장** | 코스피 (KOSPI) 실시간 지수 | `yfinance` (Yahoo Finance) | 실시간 (Ticker: `^KS11`) |
| **수급 동향** | 당월 외국인/개인/연기금 순매수 | `requests` (네이버 금융 스크래핑) | [일별 투자자별 매매동향] 크롤링 |

> 💡 지표는 30초 단위로 캐시 업데이트(`TTL=30`)를 수행합니다. 수급 테이블의 경우 **달러화($ Billions)** 단위와 **한국 원화(조원)** 단위가 병기되어 글로벌 관점에서 직관적인 파악 기능을 지원합니다.

---

## 📁 프로젝트 구조

```
stock_auto/
├── src/
│   ├── data/              # 데이터 계층
│   │   ├── models.py      # 데이터 모델
│   │   └── api_client.py  # KIS API 클라이언트
│   ├── backtest/          # 백테스팅 엔진
│   ├── strategies/        # 매매 전략
│   │   ├── base.py        # 기본 인터페이스
│   │   ├── momentum.py    # 모멘텀 전략
│   │   └── ml_strategy.py # 🆕 ML 전략 (RF, GBM, LSTM, Ensemble)
│   ├── ml/                # 🆕 머신러닝 모듈
│   │   ├── tuning.py      # 파라미터 튜닝, Walk-Forward
│   │   └── rl_strategy.py # 강화학습 (DQN, PPO)
│   ├── portfolio/         # 🆕 포트폴리오 관리
│   │   └── manager.py     # 멀티 포트폴리오 매니저
│   ├── trader/            # 자동매매
│   │   ├── auto_trader.py # 자동매매 로직
│   │   └── exit_module.py # 청산 전략
│   ├── live/              # 실전 매매
│   │   └── engine.py      # 라이브 엔진
│   └── utils/             # 유틸리티
│       ├── telegram_notifier.py # 🆕 텔레그램 알림
│       ├── database.py    # 🆕 SQLite DB
│       └── market_hours.py# 🆕 시장 시간 체크
├── scripts/               # 실행 스크립트
│   ├── run_trading.py     # 🆕 통합 트레이딩 스크립트
│   └── backtest_2025_compare.py # 🆕 전략 비교 백테스트
├── dashboard/             # Streamlit 대시보드
├── tests/                 # 테스트 코드
└── docs/                  # 문서
```

---

## 🛠️ 기술 스택

| 분류 | 기술 |
|------|------|
| 언어 | Python 3.12 |
| API | 한국투자증권 REST API |
| 데이터 | pandas, numpy, yfinance |
| ML | scikit-learn, PyTorch |
| 강화학습 | stable-baselines3, gymnasium |
| 시각화 | matplotlib, plotly, streamlit |
| 테스트 | pytest |
| DB | SQLite |
| 알림 | Telegram API |

---

## ⚠️ 주의사항

1. **모의투자 필수**: 실전 매매 전에 반드시 모의투자로 충분히 검증하세요
2. **API Rate Limit**: 한국투자증권 API는 초당 요청 제한이 있습니다
3. **ML 한계**: 과거 학습 데이터가 미래를 보장하지 않습니다
4. **손실 위험**: 주식 투자는 원금 손실 위험이 있으며, 본 시스템 사용으로 인한 손실에 대해 책임지지 않습니다

---

## 📄 라이선스

MIT License

## 🤝 기여

이슈 및 풀 리퀘스트를 환영합니다!

