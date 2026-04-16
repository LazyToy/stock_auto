# 시작 가이드

> 대시보드 및 자동매매 시스템 실행 전 체크리스트

---

## 1단계 — API 키 설정 (필수)

```bash
cp .env.example .env
```

`.env` 파일을 열어 아래 값을 입력하세요.

| 항목 | 발급처 | 필수 |
|------|--------|------|
| `KIS_APP_KEY` | [apiportal.koreainvestment.com](https://apiportal.koreainvestment.com) → 모의투자 앱 생성 | **필수** |
| `KIS_APP_SECRET` | 동일 | **필수** |
| `KIS_ACCOUNT_NUMBER` | 한국투자증권 모의투자 계좌번호 8자리 | **필수** |
| `TRADING_MODE` | `mock` (모의) 또는 `real` (실전) | 기본값 `mock` 유지 권장 |
| `FRED_API_KEY` | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) 무료 발급 | 거시경제 탭 |
| `DART_API_KEY` | [opendart.fss.or.kr](https://opendart.fss.or.kr) 무료 발급 | 공시 분석 탭 |
| `GOOGLE_API_KEY` | [aistudio.google.com](https://aistudio.google.com/app/apikey) | AI 필터 기능 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | @BotFather | 알림 (선택) |

---

## 2단계 — 패키지 설치

```bash
cd D:\HY\develop_Project\stock_auto

# 기본 + 개발 패키지
pip install -e ".[dev]"

# 대시보드 추가 패키지
pip install streamlit yfinance pykrx fredapi

# ML/RL 기능 사용 시 (선택)
pip install scikit-learn torch stable-baselines3 gymnasium
```

---

## 3단계 — 데이터 디렉토리 생성

```bash
mkdir data
mkdir reports
```

---

## 4단계 — 실행 순서

대시보드에 실제 데이터가 표시되려면 **매매 시스템을 먼저 1회 실행**해야 DB와 상태 파일이 생성됩니다.

```bash
# 1. 모의 매매 실행 (KR 모멘텀 전략)
python scripts/run_trading.py --mode single --strategy momentum --market KR

# 2. 대시보드 실행
streamlit run dashboard/app.py
```

매매 시스템 없이 대시보드만 열어도 되지만, 포트폴리오·자산 수치는 "—"로 표시됩니다.

---

## 기능별 동작 조건

| 기능 | 조건 |
|------|------|
| 대시보드 레이아웃 | 조건 없음 (바로 실행 가능) |
| yfinance 차트 | 인터넷 연결 |
| 거시경제 탭 (FRED) | `FRED_API_KEY` 필요 |
| 거시경제 탭 (KRX 외국인 수급) | `pykrx` 설치 + 인터넷 |
| 포트폴리오 현황 | KIS API 키 + 매매 시스템 1회 이상 실행 |
| 자산 추이 차트 | 매매 시스템 누적 실행 후 자동 생성 |
| AutoML 최적화 | KIS API 키 (데이터 조회용) |
| 백테스트 | KIS API 키 불필요 (로컬 데이터만 사용) |

---

## 기타 실행 명령어

```bash
# 백테스트
python scripts/run_backtest.py

# 멀티 포트폴리오 모드
python scripts/run_trading.py --mode multi --capital 2000000

# 실전 매매 (KIS_REAL_* 키 설정 후)
python scripts/run_trading.py --mode single --strategy momentum --market KR --live

# 테스트 실행
pytest tests/ -v
```
