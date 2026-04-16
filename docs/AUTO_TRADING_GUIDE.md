# 🤖 자동 매매 시스템 가이드 (Hexa-Factor Strategy)

본 시스템은 **거래량, 시장 흐름, 재무제표(PER, ROE), 모멘텀, 변동성** 등 6가지 핵심 요소를 분석하여 자동으로 우량 종목을 선정하고 매매를 수행합니다.

## 🚀 주요 기능
1.  **자동 종목 선정**: 매일 아침 KOSPI 상위 종목 중 가장 유망한 5개 종목을 선정합니다.
2.  **9-Factor 전략 (Deep Research 반영)**:
    *   📈 **Momentum**: 주가가 상승 추세인가?
    *   📉 **Low Volatility**: 주가 변동이 안정적인가?
    *   📊 **Volume Power**: 거래량이 실린 상승인가?
    *   🌊 **Relative Strength**: 시장(KOSPI)보다 강한가?
    *   💰 **Valuation**: 저평가되어 있는가? (Forward P/E)
    *   💎 **Profitability**: 돈을 잘 버는가? (ROE)
    *   🏗️ **Quality (GPA)**: 자산을 효율적으로 굴리는가? (매출총이익/자산)
    *   🚀 **Growth**: 회사가 커지고 있는가? (매출 성장률)
    *   ⚖️ **Stability**: 빚이 너무 많지 않은가? (부채비율)
3.  **포트폴리오 리밸런싱**: 선정된 종목으로 포트폴리오를 자동으로 교체합니다.

## 🛡️ 매도(Exit) 전략 (3중 방어 시스템)
이 시스템은 수익을 지키고 손실을 최소화하기 위해 강력한 매도 로직을 탑재했습니다.

1.  **📉 손절매 (Stop Loss)**
    *   매수가 대비 **-10%** 하락 시 즉시 매도하여 큰 손실을 방지합니다.
2.  **🚀 트레일링 스탑 (Trailing Stop)**
    *   주가가 상승하면 매도 기준선도 따라 올라갑니다.
    *   수익률이 **+10%** 이상일 때 활성화됩니다.
    *   최고점(High Water Mark) 대비 **-5%** 하락 시 이익을 실현하고 나옵니다.
    *   (예: 50% 올랐다가 42.5%로 떨어지면 매도 -> 42.5% 수익 확정)
3.  **📉 자격 미달 퇴출 (Minimum Score)**
    *   종목의 종합 점수가 **1.0점 미만**으로 하락하면, 순위와 상관없이 즉시 매도합니다.
    *   (펀더멘털이나 시장 상황이 급격히 나빠진 경우)

## 🛠️ 설치 및 설정

### 1. 필수 라이브러리 설치
프로젝트 루트에서 다음 명령어를 실행하세요.
```bash
uv pip install -r requirements.txt
# 또는
uv pip install yfinance schedule python-dotenv pandas numpy requests
```

### 2. API 키 설정
한국투자증권 API 키가 필요합니다. 프로젝트 루트에 `.env` 파일을 생성하고 다음 내용을 입력하세요.

**`.env` 파일 예시:**
```ini
KIS_APP_KEY=your_app_key_here
KIS_APP_SECRET=your_app_secret_here
KIS_ACCOUNT_NO=your_account_number_here (대시 제외 8자리)
```

> **주의**: 모의투자용 API 키를 사용하는 것을 권장합니다.

## ▶️ 실행 방법 (Global Auto Trading) 🌍

한국 주식(낮)과 미국 주식(밤)을 모두 자동으로 매매하려면 아래 통합 스크립트를 실행하세요.

```bash
python scripts/run_global_trading.py
```
*   **09:30**: 🇰🇷 한국 주식 자동 매매 실행
*   **23:30**: 🇺🇸 미국 주식 자동 매매 실행
*   이 스크립트 하나만 켜두면 24시간 풀가동 됩니다.

### (선택) 개별 실행 방법
원하는 시장만 골라서 실행할 수도 있습니다.

**1. 한국 주식만 실행**
```bash
python scripts/run_auto_trading.py
```

**2. 미국 주식만 실행**
```bash
python scripts/run_us_trading.py
```

### 실전 투자 전환
`scripts/run_auto_trading.py` 파일을 열어 `IS_MOCK` 변수를 `False`로 변경하세요.

---

## 🇺🇸 미국 성장주 전략 (Growth Mode - New!) 🔥
**"발전 가능성이 높은 기업에 투자하고 싶다면?"**

안정적인 우량주보다 높은 수익률(High Risk, High Return)을 추구하는 분들을 위한 전용 모드입니다.

### 1. 실행 방법
```bash
python scripts/run_us_growth.py
```

### 2. 전략 특징 (Growth vs Value)
| 특징 | 일반 모드 (Value) | 성장주 모드 (Growth) |
| :--- | :--- | :--- |
| **핵심 지표** | 이익 안정성, PER, ROE | **매출 성장률(>20%)**, 모멘텀, PSR |
| **투자 대상** | 애플, 마소, S&P500 등 | **테슬라, 엔비디아, 팔란티어, TQQQ** |
| **리스크** | 낮음 (방어적) | **높음 (공격적)** |
| **매매 성향** | 저평가 시 매수 | **달리는 말에 올라타기 (추세 추종)** |

> **Note**: 성장주 모드는 변동성이 크므로, 반드시 소액으로 모의투자를 먼저 진행해보시길 권장합니다.

```python
# scripts/run_auto_trading.py

IS_MOCK = False  # 실전 투자 모드
```

## 📊 시뮬레이션
전략의 성과를 확인하고 싶다면 시뮬레이션 스크립트를 실행해보세요.
```bash
python scripts/simulate_selection.py
```

## ⚠️ 주의사항
*   자동 매매는 **PC가 켜져 있고 스크립트가 실행 중일 때만 동작**합니다.
*   `yfinance` 데이터를 사용하므로 장중 실시간 데이터와 약 15~20분의 지연이 있을 수 있습니다.
*   투자의 책임은 전적으로 사용자에게 있습니다. 반드시 모의투자로 충분히 검증 후 사용하세요.

## 🇺🇸 미국 주식 자동매매 (US Stock Trading)
**"잠든 사이 수익을 창출합니다."**

한국 주식과 동일한 강력한 알고리즘(9-Factor + Trailing Stop)을 미국 우량주에 적용합니다.

### 1. 실행 방법
```bash
python scripts/run_us_trading.py
```
*   **거래 시간**: 한국 시간 **밤 23:30** (미장 오픈 시) 자동 실행됩니다.
*   **봇 특징**: 밤샘 근무 모드로 전환되어, 새벽에도 시장을 감시하고 최적의 타이밍에 매매를 수행합니다.

### 2. 투자 대상 (Global Top-Tier)
*   **Magnificent 7**: AAPL(애플), MSFT(마이크로소프트), GOOGL(구글), AMZN(아마존), NVDA(엔비디아), TSLA(테슬라), META(메타)
*   **Top ETFs**: SPY(S&P500), QQQ(Nasdaq100), SOXL(반도체 3배), TQQQ(나스닥 3배)
    *   *주의: 3배 레버리지 ETF는 변동성이 매우 크므로 주의가 필요합니다.*

### 3. 주요 특징 (KR vs US)
| 구분 | 한국 주식 (KR) | 미국 주식 (US) |
| :--- | :--- | :--- |
| **벤치마크** | KOSPI (^KS11) | **S&P 500 (^GSPC)** |
| **거래소** | KRX (코스피/코스닥) | **NASD (나스닥), NYSE (뉴욕)** |
| **거래 시간** | 09:00 ~ 15:30 | **23:30 ~ 06:00** (서머타임 22:30~) |
| **전략** | 9-Factor + Trailing Stop | **동일 전략 적용** (추세 추종에 더 유리) |

> **Tip**: 미국 주식은 "추세"가 뚜렷하여 Trailing Stop 전략의 효율이 매우 높습니다.
