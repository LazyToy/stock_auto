# 🎯 Stock Auto Dashboard — 하네스 엔지니어링 문서

| 항목 | 값 |
|------|-----|
| 문서 버전 | v1.0 |
| 작성일 | 2026-04-13 |
| 작성자 | Antigravity (계획 AI) |
| 대상 프로젝트 | stock_auto |
| 이슈 수 | 6개 |
| 예상 총 소요 시간 | 3~4시간 |

---

## 🔑 공통 컨텍스트

### 역할 지정
너는 `stock_auto` 프로젝트의 시니어 Python 백엔드/프론트엔드 개발자야.
Streamlit 대시보드의 버그를 수정하고, AI 모듈의 호환성 문제를 해결하는 작업을 수행한다.

### 기술 스택
- **프레임워크**: Streamlit (대시보드), Python 3.x
- **패키지 관리**: uv (pip 호환)
- **가상환경**: `stock_auto` (경로: `d:\HY\develop_Project\stock_auto\stock_auto\`)
- **주요 라이브러리**:
  - `yfinance` — Yahoo Finance 데이터 수집
  - `google-generativeai` — Google Gemini AI (Vision/Text)
  - `langchain-google-genai` — LangChain 기반 Gemini 래핑
  - `mplfinance` — 캔들차트 이미지 생성
  - `deap` — 유전 알고리즘
  - `plotly` — 차트 시각화
  - `pandas`, `numpy` — 데이터 처리

### 핵심 파일 맵
| 파일 | 역할 | 현재 줄 수 |
|------|------|-----------:|
| `dashboard/app.py` | 메인 대시보드 (Streamlit) | 490줄 |
| `dashboard/components/growth_tab.py` | 성장주 탐색 탭 UI | 127줄 |
| `src/analysis/growth_stock_finder.py` | 성장주 탐색 로직 (yfinance+Tavily) | 437줄 |
| `src/analysis/multimodal.py` | 멀티모달 분석기 (Gemini Vision) | 126줄 |
| `src/analysis/chart.py` | 캔들차트 이미지 생성기 | 61줄 |
| `src/analysis/market_data.py` | 시장 데이터 수집기 | 76줄 |
| `src/analysis/stress.py` | 스트레스 테스트 시뮬레이터 | 131줄 |
| `src/optimization/genetic.py` | 유전 알고리즘 최적화기 | 142줄 |
| `src/optimization/evaluator.py` | 전략 평가기 | 134줄 |
| `src/copilot/debate.py` | 멀티에이전트 토론 매니저 | 121줄 |
| `src/copilot/agent.py` | AI Copilot 에이전트 | 108줄 |
| `src/config.py` | 중앙 설정 관리 (.env 기반) | 107줄 |
| `.env` | 환경 변수 (API 키 등) | 52줄 |
| `trading_state.json` | 거래 상태 파일 | 16줄 |

### 코딩 규칙 (Always/Never)
**Always:**
- 모든 주석/에러 메시지는 한국어로 작성
- 변경 후 반드시 서버를 재시작하여 동작 확인
- 에러 발생 가능 구간에 try-except 포함
- 기존 import 구조와 호환성 유지
- Red→Green→Refactor TDD 사이클 엄수 (테스트 먼저 작성)

**Never:**
- 기존 API 인터페이스를 breaking change 하지 않음
- 테스트 없이 로직 변경 금지
- `.env` 파일의 실제 API 키를 코드에 직접 하드코딩하지 않음
- 작동하는 기존 기능을 훼손하지 않음

### 보고 형식
변경 완료 후 반드시 아래 형식으로 보고:
- ✅ 수정/추가된 파일 목록
- ✅ 변경 내용 (diff 형식)
- ✅ 변경 이유
- ✅ 영향 범위
- ✅ 다음 단계

---

## 이슈 목록

| # | 이슈 | 복잡도 | 핵심 파일 | 선행 이슈 |
|---|------|--------|----------|----------|
| 1 | 성장주 탐색 — 한국 종목 섹터/재무지표 N/A 표시 | 🟨 중간 | `growth_stock_finder.py` | 없음 |
| 2 | 성장주 탐색 — 추천 종목명이 코드로만 표시 | 🟨 중간 | `growth_stock_finder.py` | #1과 병렬 가능 |
| 3 | Multimodal Deep Analysis — 모델 단종 + Streamlit API 변경 | ⬜ 낮음 | `config.py`, `multimodal.py`, `app.py`, `debate.py`, `agent.py` | 없음 |
| 4 | AutoML — 유전 알고리즘 가격 DataFrame 미전달 | 🟨 중간 | `app.py`, `genetic.py` | 없음 |
| 5 | Stress Test — 포트폴리오 데이터 미인식 | ⬜ 낮음 | `app.py` | 없음 |
| 6 | Multi-Agent Debate — 모델 단종 + 잘못된 티커 전달 | 🟨 중간 | `debate.py`, `app.py` | #3 |

### 의존성 다이어그램
```
#1 ──→ (독립)
#2 ──→ (독립, #1과 같은 파일이지만 수정 영역 다름)
#3 ──→ #6 (#3의 모델명 변경이 #6에도 영향)
#4 ──→ (독립)
#5 ──→ (독립)
```

---

## 이슈 1: 성장주 탐색 — 한국 종목 섹터/재무지표 N/A 표시

### 🔍 문제 정의

**현상**: 성장주 탐색 탭에서 한국 시장(🇰🇷) 선택 후 검색하면, 추천된 2개 종목의 주요섹터가 "Unknown"으로 표시되고, 매출 성장률/영업이익률이 모두 "N/A"로 나타남.

**근본 원인**:
1. **yfinance 한국 종목 info 미반환**: `yfinance`의 `Ticker.info`는 `.KQ`(코스닥), `.KS`(코스피) 접미사가 붙은 한국 종목에 대해 `sector`, `revenueGrowth`, `profitMargins` 등의 필드를 **일관되게 반환하지 않음**. Yahoo Finance 자체가 한국 종목의 fundamental 데이터를 불완전하게 제공하거나, 필드명이 다를 수 있음.
   - `src/analysis/growth_stock_finder.py` L163~L176: `stock.info`에서 `sector`는 `'Unknown'`으로, `revenueGrowth`/`profitMargins`는 `None`으로 반환되는 종목이 다수.
2. **스크리닝 조건이 None을 통과시킴**: `_passes_screening()` (L214~L235)에서 `revenue_growth is None`일 때 체크를 건너뛰도록 설계되어 있어, 재무 데이터가 없는 종목도 통과됨.
3. **일부 한국 종목 코드 오류**: `KR_CANDIDATE_SYMBOLS` 리스트(L57~L78)에서 일부 종목이 실제로 `.KQ` suffix가 아닌 `.KS`가 맞거나, 종목 코드가 변경되었을 가능성 있음. 예: `112610.KQ`(씨에스윈드)는 실제로 `112610.KS`여야 할 수 있음.

**영향 범위**: 성장주 탐색 탭 — 한국 시장 검색 결과 전체

---

### 📦 구현 지시

**전제 조건**:
- 가상환경 `stock_auto` 활성화 상태
- `yfinance` 라이브러리 최신 버전 확인

**수정 대상 파일**: `src/analysis/growth_stock_finder.py`

**구현 프롬프트**:
```
[작업 지시]
harnes 문서 "이슈 1: 성장주 탐색 — 한국 종목 섹터/재무지표 N/A 표시"를 구현해줘.

[구현 단계]

== 단계 1: 한국 종목 섹터 매핑 테이블 추가 ==
`src/analysis/growth_stock_finder.py` 수정:

- HybridGrowthStockFinder 클래스 내부에 한국 종목별 섹터 매핑 딕셔너리 추가:
  KR_SECTOR_MAP = {
      "439090.KQ": "반도체",     # 하나마이크론
      "317330.KQ": "반도체",     # 덕산테코피아
      "036930.KQ": "반도체장비", # 주성엔지니어링
      "357780.KQ": "반도체소재", # 솔브레인
      "240810.KQ": "반도체장비", # 원익IPS
      "247540.KQ": "2차전지",   # 에코프로비엠
      "112610.KQ": "풍력에너지", # 씨에스윈드
      "373220.KQ": "2차전지",   # LG에너지솔루션
      "090460.KQ": "전자부품",  # 비에이치
      "058610.KQ": "로봇/자동화", # 에스피지
      "950140.KQ": "바이오",    # 잉글우드랩
      "145020.KQ": "바이오",    # 휴젤
      "196170.KQ": "바이오",    # 알테오젠
      "298050.KS": "첨단소재",  # 효성첨단소재
      "267260.KS": "전력기기",  # HD현대일렉트릭
  }

- 변경 이유: yfinance가 한국 종목의 sector를 안정적으로 제공하지 않으므로, 
  수동 매핑으로 fallback 처리.

== 단계 2: _screen_with_yfinance에서 sector fallback 처리 ==
`_screen_with_yfinance` 메서드 (L153~L212) 수정:

- 현재 코드 (L176):
  sector = info.get('sector', 'Unknown')

- 변경할 코드:
  sector = info.get('sector', None)
  if not sector or sector == 'Unknown':
      sector = self.KR_SECTOR_MAP.get(symbol, 'Unknown')

- 변경 이유: yfinance가 sector를 반환하면 그대로 쓰되, 
  없거나 'Unknown'이면 우리 매핑에서 가져옴.

== 단계 3: 재무 데이터 대체 소스 추가 ==
`_screen_with_yfinance` 메서드에서, 한국 종목의 revenue_growth, profit_margin이
None인 경우 yfinance의 financials/quarterly_financials에서 직접 계산하는 
fallback 로직 추가:

- revenue_growth이 None인 경우:
  try:
      financials = stock.financials
      if financials is not None and not financials.empty:
          if 'Total Revenue' in financials.index:
              revenues = financials.loc['Total Revenue']
              if len(revenues) >= 2 and revenues.iloc[0] and revenues.iloc[1]:
                  revenue_growth = ((revenues.iloc[0] - revenues.iloc[1]) / abs(revenues.iloc[1])) * 100
  except Exception:
      pass

- profit_margin이 None인 경우:
  try:
      financials = stock.financials
      if financials is not None and not financials.empty:
          revenue_key = 'Total Revenue'
          profit_key = 'Operating Income'
          if revenue_key in financials.index and profit_key in financials.index:
              rev = financials.loc[revenue_key].iloc[0]
              profit = financials.loc[profit_key].iloc[0]
              if rev and rev > 0:
                  profit_margin = (profit / rev) * 100
  except Exception:
      pass

- 변경 이유: info에서 직접 가져오지 못하는 재무 데이터를 
  financials 테이블에서 계산하여 보완.

== 단계 4: 종목 코드 검증 및 수정 ==
KR_CANDIDATE_SYMBOLS 리스트를 검증:
- 터미널에서 각 종목 코드의 yfinance 유효성을 빠르게 테스트하는 스크립트를 작성-실행하여
  실제로 데이터가 반환되는지 확인.
- 유효하지 않은 종목 코드는 올바른 코드(예: .KQ → .KS 또는 그 반대)로 수정.
- 예: 씨에스윈드(112610)는 코스피 상장이므로 `112610.KQ` → `112610.KS`로 변경 필요할 수 있음.
  실제 yfinance 반환값으로 판단할 것.

[경계 조건 — 하지 말 것]
- 미국 종목(US_CANDIDATE_SYMBOLS) 로직은 건드리지 말 것
- 기존 GrowthStock 데이터클래스 필드를 변경하지 말 것
- _enrich_with_tavily 로직은 건드리지 말 것

[완료 조건]
- 한국 시장 검색 시 최소 3개 이상 종목이 결과에 포함
- 결과 종목의 sector 필드가 'Unknown'이 아닌 한국어 섹터명
- revenue_growth 또는 profit_margin 중 최소 하나는 N/A가 아니어야 함
- 기존 미국 시장 검색에 regression 없음
- 수정 파일 목록 + diff 보고
```

---

### ✅ 완료 판정 기준 (Acceptance Criteria)

| # | 기준 | 검증 방법 |
|---|------|----------|
| AC-1 | 한국 시장 검색 시 섹터가 "Unknown"이 아닌 한국어 섹터명으로 표시 | 대시보드에서 🇰🇷 한국 → 성장 가능성 주 찾기 클릭 후 결과 확인 |
| AC-2 | 매출 성장률 또는 영업이익률 중 최소 하나가 N/A가 아닌 수치로 표시 | 결과 카드형 UI에서 확인 |
| AC-3 | 최소 3개 이상 종목이 결과에 포함 | 결과 목록 개수 확인 |
| AC-4 | KR_SECTOR_MAP 딕셔너리가 추가되어 있음 | 코드 리뷰 |
| AC-5 | financials fallback 로직이 try-except로 감싸져 있음 | 코드 리뷰 |
| AC-6 | 미국 시장 검색이 기존과 동일하게 동작 | 🇺🇸 미국 → 검색 클릭 후 결과 확인 |

---

### 🔍 검증 지시

**검증 프롬프트**:
```
[작업 지시]
이슈 1 "성장주 탐색 — 한국 종목 섹터/재무지표 N/A 표시" 구현이 완료되었다고 합니다. 검증해주세요.

[1단계: 정적 검증]
1. `src/analysis/growth_stock_finder.py`를 열어 다음을 확인:
   □ KR_SECTOR_MAP 딕셔너리가 HybridGrowthStockFinder 클래스에 정의되어 있는지
   □ _screen_with_yfinance() 메서드에서 sector fallback 로직이 존재하는지
   □ revenue_growth / profit_margin을 financials에서 계산하는 fallback 로직이 존재하는지
   □ 모든 fallback 로직이 try-except로 감싸져 있는지
   □ US_CANDIDATE_SYMBOLS 및 미국 관련 로직이 변경되지 않았는지

[2단계: 동적 검증 (브라우저/런타임)]
□ 대시보드 실행 (`streamlit run dashboard/app.py`)
□ "🌱 성장주 탐색" 탭 → 🇰🇷 한국 선택 → "성장 가능성 주 찾기" 클릭
□ 결과 확인:
  - 종목 수: 최소 3개 이상
  - 각 종목의 섹터: "Unknown"이 아닌 한국어 섹터명 (예: "반도체", "바이오")
  - 매출 성장률 / 영업이익률: 적어도 일부 종목에서 N/A가 아닌 수치 표시
□ 🇺🇸 미국 선택 → "성장 가능성 주 찾기" 클릭
  - 기존과 동일하게 정상 동작 (regression 없음)

[3단계: 단위 테스트]
□ 아래 테스트 케이스가 통과하는지 확인:
  - test_kr_sector_fallback: KR_SECTOR_MAP에 있는 종목의 sector가 올바르게 반환되는지
  - test_financial_fallback: financials fallback 로직이 None이 아닌 값을 반환하는지
  - test_us_stocks_unchanged: US 종목 검색 결과가 기존과 동일한지

[보고 형식]
전체 결과: ✅ 통과 / ❌ 실패
- 각 항목별 ✅/❌
- 실패 항목: 재현 단계 + 스크린샷/로그
- 수정 제안 (있는 경우)
```

---

## 이슈 2: 성장주 탐색 — 추천 종목명이 코드로만 표시

### 🔍 문제 정의

**현상**: 추천 종목 리스트에서 종목명이 `112610.KQ,0P00014ZM7,872385 (112610) - Unknown` 같은 형태로 표시됨. 사용자가 어떤 회사인지 전혀 알 수 없음. "씨에스윈드" 같은 실제 회사명이 표시되어야 함.

**근본 원인**:
1. **yfinance shortName 필드 문제**: `info.get('shortName', symbol)` (L195)에서 한국 종목의 `shortName`이 영문 약어나 코드로만 반환되거나, 전혀 반환되지 않는 경우가 있음.
2. **한국 종목 이름 매핑 부재**: 한국 종목의 경우 yfinance가 `longName` 또는 `shortName`을 한국어로 제공하지 않으므로, 별도의 한글 종목명 매핑이 필요.

**영향 범위**: 성장주 탐색 탭 — 추천 종목 리스트 표시

---

### 📦 구현 지시

**전제 조건**:
- 이슈 #1과 같은 파일을 수정하므로, 같은 세션에서 순차 작업 권장

**수정 대상 파일**: `src/analysis/growth_stock_finder.py`

**구현 프롬프트**:
```
[작업 지시]
harnes 문서 "이슈 2: 성장주 탐색 — 추천 종목명이 코드로만 표시"를 구현해줘.

[구현 단계]

== 단계 1: 한국 종목명 매핑 테이블 추가 ==
`src/analysis/growth_stock_finder.py` 수정:

- HybridGrowthStockFinder 클래스 내부에 한국 종목별 한국어 이름 매핑 추가:
  KR_NAME_MAP = {
      "439090.KQ": "하나마이크론",
      "317330.KQ": "덕산테코피아",
      "036930.KQ": "주성엔지니어링",
      "357780.KQ": "솔브레인",
      "240810.KQ": "원익IPS",
      "247540.KQ": "에코프로비엠",
      "112610.KQ": "씨에스윈드",
      "373220.KQ": "LG에너지솔루션",
      "090460.KQ": "비에이치",
      "058610.KQ": "에스피지",
      "950140.KQ": "잉글우드랩",
      "145020.KQ": "휴젤",
      "196170.KQ": "알테오젠",
      "298050.KS": "효성첨단소재",
      "267260.KS": "HD현대일렉트릭",
  }

- 변경 이유: yfinance가 한국 종목의 shortName을 한국어로 안정적으로 반환하지
  않으므로, 수동 매핑으로 fallback 처리.

== 단계 2: _screen_with_yfinance에서 name fallback 처리 ==
`_screen_with_yfinance` 메서드 수정:

- 현재 코드 (L195):
  name=info.get('shortName', symbol),

- 변경할 코드:
  raw_name = info.get('shortName', '') or info.get('longName', '')
  # 한국 종목이고 yfinance 이름이 코드처럼 보이면 매핑 사용
  if not raw_name or raw_name == symbol or len(raw_name) < 2:
      name = self.KR_NAME_MAP.get(symbol, symbol)
  else:
      # yfinance에서 반환한 이름이 코드 형태인지 체크
      # 예: "112610.KQ,0P00014ZM7,872385" 같은 패턴
      if ',' in raw_name or raw_name.replace('.', '').replace(' ', '').isdigit():
          name = self.KR_NAME_MAP.get(symbol, raw_name)
      else:
          name = raw_name

- 변경 이유: yfinance에서 정상적인 회사명이 오면 사용하되, 
  코드 형태이거나 비어있으면 우리 매핑에서 가져옴.

== 단계 3: 종목 코드 수정 시 매핑 동기화 ==
이슈 #1의 단계 4에서 종목 코드가 변경된 경우(예: .KQ → .KS),
KR_NAME_MAP과 KR_SECTOR_MAP의 키도 동일하게 업데이트해야 함.
→ 두 매핑의 키가 KR_CANDIDATE_SYMBOLS와 일치하는지 반드시 확인.

[경계 조건 — 하지 말 것]
- GrowthStock 데이터클래스의 name 필드 타입을 변경하지 말 것
- 미국 종목의 이름 처리 로직은 건드리지 말 것
- to_dataframe_dict()의 '종목명' 키는 그대로 유지

[완료 조건]
- 한국 종목의 이름이 "씨에스윈드", "주성엔지니어링" 등 한국어 회사명으로 표시
- 미국 종목의 이름은 기존과 동일하게 영문으로 표시
- 대시보드 카드형 UI에서 "1. 씨에스윈드 (112610) - 풍력에너지" 형태로 표시
- 수정 파일 목록 + diff 보고
```

---

### ✅ 완료 판정 기준 (Acceptance Criteria)

| # | 기준 | 검증 방법 |
|---|------|----------|
| AC-1 | KR_NAME_MAP 딕셔너리가 KR_CANDIDATE_SYMBOLS와 1:1 대응 | 코드 리뷰 |
| AC-2 | 한국 종목 이름이 한국어 회사명으로 표시 | 대시보드 결과 UI 확인 |
| AC-3 | name fallback 로직에서 코드 형태 감지 패턴이 올바름 | 코드 리뷰 |
| AC-4 | 미국 종목 이름에 변화 없음 | 대시보드 🇺🇸 검색 결과 확인 |
| AC-5 | 대시보드 카드형 UI 표시 형식: "N. {회사명} ({종목코드}) - {섹터}" | UI 확인 |

---

### 🔍 검증 지시

**검증 프롬프트**:
```
[작업 지시]
이슈 2 "성장주 탐색 — 추천 종목명이 코드로만 표시" 구현이 완료되었다고 합니다. 검증해주세요.

[1단계: 정적 검증]
1. `src/analysis/growth_stock_finder.py`를 열어 다음을 확인:
   □ KR_NAME_MAP 딕셔너리 존재 여부
   □ KR_NAME_MAP의 키가 KR_CANDIDATE_SYMBOLS와 동기화되어 있는지
   □ _screen_with_yfinance()에서 name fallback 로직이 올바르게 구현되어 있는지
   □ 코드 형태 감지 조건문이 합리적인지 (콤마 포함, 숫자만 등)
   □ 미국 종목 로직이 영향받지 않았는지

[2단계: 동적 검증 (브라우저/런타임)]
□ 대시보드에서 🇰🇷 한국 → "성장 가능성 주 찾기" 클릭
□ 결과 확인:
  - 각 카드의 제목 형식: "N. {한국어회사명} ({종목코드}) - {섹터}"
  - 예시: "1. 씨에스윈드 (112610) - 풍력에너지"
  - 코드 형태의 이름(숫자나 콤마 포함)이 표시되지 않는지
□ 🇺🇸 미국 → 검색
  - 이름이 영문 회사명으로 정상 표시되는지 (예: "Super Micro Computer")

[보고 형식]
전체 결과: ✅ 통과 / ❌ 실패
- 각 항목별 ✅/❌
- 실패 항목: 재현 단계 + 스크린샷/로그
- 수정 제안 (있는 경우)
```

---

## 이슈 3: Multimodal Deep Analysis — Gemini 모델 단종 + Streamlit API 변경

### 🔍 문제 정의

**현상**: 
1. 차트 표시 시 `ImageMixin.image() got an unexpected keyword argument 'use_container_width'` 에러 발생
2. AI 분석 시 `404 models/gemini-1.5-flash is not found for API version v1beta` 에러 발생

**근본 원인**:
1. **Streamlit API 변경**: `st.image()`의 `use_container_width` 파라미터가 deprecated됨. 현재 버전에서는 `width="stretch"` 파라미터를 사용해야 함.
   - `dashboard/app.py` L256: `st.image(img_bytes, caption=..., use_container_width=True)`
2. **Gemini 1.5 Flash 모델 단종**: 2026년 4월 현재 `gemini-1.5-flash` 모델이 Google API에서 완전 제거됨. `gemini-2.5-flash`로 마이그레이션 필요.
   - `src/config.py` L49: `LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gemini-1.5-flash")`
   - `src/copilot/debate.py` L18: `model="gemini-1.5-flash"` (하드코딩)
   - `src/copilot/agent.py` L14: `model_name: str = "gemini-1.5-flash"` (기본값 하드코딩)

**영향 범위**: 
- Deep Analysis 탭 (차트 표시 + AI 분석)
- AI Copilot 탭
- Agent Debate 탭
- `Config.LLM_MODEL_NAME`을 사용하는 모든 모듈

---

### 📦 구현 지시

**전제 조건**:
- `.env` 파일의 `GOOGLE_API_KEY`가 유효한 상태
- 가상환경에 `google-generativeai` 및 `langchain-google-genai` 설치

**수정 대상 파일**: `src/config.py`, `dashboard/app.py`, `src/copilot/debate.py`, `src/copilot/agent.py`

**구현 프롬프트**:
```
[작업 지시]
harnes 문서 "이슈 3: Multimodal Deep Analysis — 모델 단종 + Streamlit API 변경"을 구현해줘.

[구현 단계]

== 단계 1: Config.py에서 기본 모델명 변경 ==
`src/config.py` L49 수정:

- 현재 코드:
  LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gemini-1.5-flash")

- 변경할 코드:
  LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gemini-2.5-flash")

- 변경 이유: gemini-1.5-flash 모델이 2026년 4월 기준 완전 단종(404).
  gemini-2.5-flash가 현재 활성 모델 중 가장 유사한 대체제.

== 단계 2: debate.py에서 하드코딩된 모델명을 Config 참조로 변경 ==
`src/copilot/debate.py` L17~L21 수정:

- 현재 코드:
  self.llm = ChatGoogleGenerativeAI(
      model="gemini-1.5-flash",
      google_api_key=Config.GOOGLE_API_KEY,
      temperature=0.7
  )

- 변경할 코드:
  self.llm = ChatGoogleGenerativeAI(
      model=Config.LLM_MODEL_NAME,
      google_api_key=Config.GOOGLE_API_KEY,
      temperature=0.7
  )

- 변경 이유: 모델명을 Config에서 중앙 관리하여 향후 모델 변경 시 
  한 곳만 수정하면 되도록 함.

== 단계 3: agent.py에서 기본 모델명을 Config 참조로 변경 ==
`src/copilot/agent.py` L14 수정:

- 현재 코드:
  def __init__(self, model_name: str = "gemini-1.5-flash"):

- 변경할 코드:
  def __init__(self, model_name: str = None):

- 그리고 L29 부근에서:
  현재: self.llm = ChatGoogleGenerativeAI(model=model_name, ...)
  변경: self.llm = ChatGoogleGenerativeAI(model=model_name or Config.LLM_MODEL_NAME, ...)

- 변경 이유: 기본 모델명을 Config에서 통일 관리.

== 단계 4: app.py에서 use_container_width → width="stretch" 변경 ==
`dashboard/app.py` L256 수정:

- 현재 코드:
  st.image(img_bytes, caption=f"{ticker_input} Technical Chart", use_container_width=True)

- 변경할 코드:
  st.image(img_bytes, caption=f"{ticker_input} Technical Chart", width="stretch")

- 변경 이유: Streamlit 최신 버전에서 use_container_width 파라미터가
  deprecated됨. width="stretch"가 동일 기능의 대체 파라미터.

== 단계 5: .env에 LLM_MODEL_NAME 추가 (선택) ==
`.env` 파일에 주석과 함께 추가:
  # LLM 모델명 (기본: gemini-2.5-flash)
  # LLM_MODEL_NAME=gemini-2.5-flash

→ 이 단계는 선택사항이지만, 사용자가 .env에서 모델을 변경할 수 있도록 안내.

[경계 조건 — 하지 말 것]
- GOOGLE_API_KEY 자체를 변경하지 말 것
- multimodal.py의 프롬프트나 분석 로직은 건드리지 말 것
- Streamlit 버전을 다운그레이드하지 말 것

[완료 조건]
- Deep Analysis 탭에서 차트 이미지가 에러 없이 표시
- AI 분석이 404 에러 없이 정상 실행
- AI Copilot 탭에서 질문 입력 시 정상 응답
- 수정 파일 목록 + diff 보고
```

---

### ✅ 완료 판정 기준 (Acceptance Criteria)

| # | 기준 | 검증 방법 |
|---|------|----------|
| AC-1 | `Config.LLM_MODEL_NAME` 기본값이 `gemini-2.5-flash` | `src/config.py` 코드 리뷰 |
| AC-2 | `debate.py`에서 `Config.LLM_MODEL_NAME` 참조 | 코드 리뷰 |
| AC-3 | `agent.py`에서 `Config.LLM_MODEL_NAME` 참조 | 코드 리뷰 |
| AC-4 | `app.py`에서 `use_container_width` → `width="stretch"` 변경 | 코드 리뷰 |
| AC-5 | Deep Analysis 탭에서 차트 에러 없음 | 대시보드 동작 확인 |
| AC-6 | Deep Analysis 탭에서 AI 분석이 signal/confidence/reason 반환 | 대시보드 동작 확인 |
| AC-7 | 서버 콘솔에 404 에러 없음 | 터미널 로그 확인 |

---

### 🔍 검증 지시

**검증 프롬프트**:
```
[작업 지시]
이슈 3 "Multimodal Deep Analysis — 모델 단종 + Streamlit API 변경" 구현이 완료되었다고 합니다. 검증해주세요.

[1단계: 정적 검증]
1. src/config.py를 열어 확인:
   □ LLM_MODEL_NAME 기본값이 "gemini-2.5-flash"인지
2. src/copilot/debate.py를 열어 확인:
   □ AnalystAgent.__init__에서 model= 파라미터가 Config.LLM_MODEL_NAME인지
   □ "gemini-1.5-flash" 문자열이 어디에도 하드코딩되어 있지 않은지
3. src/copilot/agent.py를 열어 확인:
   □ __init__의 model_name 기본값이 Config.LLM_MODEL_NAME 또는 None인지
   □ ChatGoogleGenerativeAI 생성 시 Config.LLM_MODEL_NAME이 사용되는지
4. dashboard/app.py를 열어 확인:
   □ st.image() 호출에 use_container_width 파라미터가 없는지
   □ width="stretch" 파라미터가 사용되는지
5. 프로젝트 전체에서 "gemini-1.5-flash" 문자열 검색:
   □ grep -r "gemini-1.5-flash" src/ dashboard/ 결과가 0건인지

[2단계: 동적 검증 (브라우저/런타임)]
□ 대시보드 실행 후 "🧠 Deep Analysis" 탭 이동
□ 종목 코드 "AAPL" 입력 → "심층 분석 시작" 클릭
□ 확인:
  - 왼쪽: 차트 이미지가 에러 없이 표시되는지
  - 오른쪽: Signal, Confidence, Reasoning이 정상 표시되는지
  - 서버 콘솔에 404 에러가 없는지
□ "🤖 AI Copilot" 탭 이동 → 아무 질문 입력 → 정상 응답 오는지

[3단계: 회귀 검증]
□ 기존 "📊 Overview" 탭 정상 동작
□ 기존 "🌱 성장주 탐색" 탭 정상 동작

[보고 형식]
전체 결과: ✅ 통과 / ❌ 실패
- 각 항목별 ✅/❌
- 실패 항목: 재현 단계 + 로그
- 수정 제안 (있는 경우)
```

---

## 이슈 4: AutoML — 유전 알고리즘 가격 DataFrame 미전달

### 🔍 문제 정의

**현상**: AutoML 탭에서 "Start Evolution" 버튼 클릭 시 에러 메시지:
`AutoML 최적화 엔진을 불러올 수 없습니다. (GeneticOptimizer requires a price DataFrame. Provide df=... before evolve() or initialize with df.)`

**근본 원인**:
1. **DataFrame 미전달**: `dashboard/app.py` L307~L325에서 `GeneticOptimizer`를 생성할 때 `df` 파라미터를 전달하지 않음. 이후 `optimizer.evolve(symbol=test_symbol)`을 호출하지만 `df`도 전달하지 않아, `evolve()` 내부(genetic.py L107)에서 `self.df is None`으로 판단하고 `ValueError`를 raise함.
2. **가격 데이터 수집 로직 부재**: 사용자가 입력한 `test_symbol` (예: "005930")에 대해 yfinance에서 가격 데이터를 다운로드하여 GeneticOptimizer에 전달하는 로직이 `app.py`에 없음.
3. **결과 표시 시 'history' 키 미포함**: `genetic.py`의 `evolve()` 반환값에 `history` 키가 없는데, `app.py` L344에서 `result["history"]`를 참조하여 추가 에러 발생 가능.

**영향 범위**: AutoML 탭 전체

---

### 📦 구현 지시

**전제 조건**:
- `yfinance` 설치 확인
- 가상환경 활성화

**수정 대상 파일**: `dashboard/app.py`, `src/optimization/genetic.py`

**구현 프롬프트**:
```
[작업 지시]
harnes 문서 "이슈 4: AutoML — 유전 알고리즘 가격 DataFrame 미전달"을 구현해줘.

[구현 단계]

== 단계 1: app.py에서 가격 데이터 다운로드 후 전달 ==
`dashboard/app.py` L307~L325 수정:

- 현재 코드 (L307~L325):
  if st.button("🚀 Start Evolution", type="primary", key="automl_start"):
      if "automl_optimizer" not in st.session_state:
          st.session_state["automl_optimizer"] = GeneticOptimizer(
              population_size=population_size,
              generations=generations,
              mutation_rate=mutation_rate
          )
      
      optimizer = st.session_state["automl_optimizer"]
      
      progress_bar = st.progress(0, text="진화 초기화 중...")
      try:
          result_evo = optimizer.evolve(
              symbol=test_symbol,
              progress_callback=lambda i, n: progress_bar.progress(
                  (i + 1) / n,
                  text=f"세대 {i + 1}/{n} 진화 중..."
              )
          )
          ...

- 변경할 코드:
  if st.button("🚀 Start Evolution", type="primary", key="automl_start"):
      progress_bar = st.progress(0, text="가격 데이터 다운로드 중...")
      
      try:
          # 1. 가격 데이터 다운로드
          import yfinance as yf
          # 한국 종목이면 .KS 접미사 추가 (숫자로만 구성된 경우)
          yf_symbol = test_symbol
          if test_symbol.isdigit():
              yf_symbol = f"{test_symbol}.KS"
          
          ticker_data = yf.Ticker(yf_symbol)
          df = ticker_data.history(period="1y")
          
          if df.empty:
              # .KQ로 재시도
              if test_symbol.isdigit():
                  yf_symbol = f"{test_symbol}.KQ"
                  ticker_data = yf.Ticker(yf_symbol)
                  df = ticker_data.history(period="1y")
          
          if df.empty:
              st.error(f"종목 {test_symbol}의 가격 데이터를 가져올 수 없습니다. 종목 코드를 확인하세요.")
              st.stop()
          
          progress_bar.progress(0.1, text="가격 데이터 로드 완료. 진화 시작...")
          
          # 2. GeneticOptimizer 생성 (항상 새로 생성하여 파라미터 반영)
          optimizer = GeneticOptimizer(
              df=df,
              population_size=population_size,
              generations=generations,
              mutation_rate=mutation_rate
          )
          
          # 3. 진화 실행
          result_evo = optimizer.evolve(
              symbol=test_symbol,
              progress_callback=lambda i, n: progress_bar.progress(
                  min((i + 1) / n, 1.0),
                  text=f"세대 {i + 1}/{n} 진화 중..."
              )
          )
          st.success("✅ Evolution Complete!")
          st.session_state["automl_result"] = result_evo
      except Exception as evo_err:
          st.error(f"AutoML 최적화 중 오류가 발생했습니다: {evo_err}")

- 변경 이유: 사용자가 입력한 test_symbol에서 yfinance로 가격 데이터를 
  다운로드하여 GeneticOptimizer에 df로 전달. 
  한국 종목은 숫자만 입력하면 .KS/.KQ를 자동으로 붙여 시도.

== 단계 2: genetic.py의 evolve() 반환값에 history 추가 ==
`src/optimization/genetic.py`의 evolve() 메서드 수정:

- 현재 반환값 (L121~L128):
  return {
      "symbol": symbol,
      "best_params": best_params,
      "best_fitness": float(best_fitness),
      "population_size": self.pop_size,
      "generations": self.ngen,
      "mutation_rate": self.mutation_rate,
  }

- run() 메서드에서 logbook(log)을 반환하도록 수정 후, 
  evolve()에서 history를 추출하여 포함:

  run() 메서드 반환값을 (best_params, best_fitness, logbook) 튜플로 변경:
  - L96:
    return list(best_ind), best_ind.fitness.values[0], log

  - L76 (에러 시):
    return [], 0.0, None

  evolve() 메서드에서:
  best_params, best_fitness, logbook = self.run()
  
  # 세대별 최고 fitness 기록 추출
  history = []
  if logbook:
      try:
          history = [record.get("max", 0) for record in logbook]
      except Exception:
          history = []

  return {
      "symbol": symbol,
      "best_params": best_params,
      "best_fitness": float(best_fitness),
      "population_size": self.pop_size,
      "generations": self.ngen,
      "mutation_rate": self.mutation_rate,
      "history": history,
  }

- 변경 이유: app.py의 결과 표시 코드(L344)에서 result["history"]를 
  참조하므로, evolve() 반환값에 history 키를 추가.

== 단계 3: app.py 결과 표시부 방어 코드 추가 ==
`dashboard/app.py` L334~L354의 결과 표시 코드에 방어 로직 추가:

- result["history"]가 비어있거나 없을 때 차트를 표시하지 않도록:
  if "automl_result" in st.session_state:
      result = st.session_state["automl_result"]
      
      st.metric("Best Fitness Score", f"{result['best_fitness']:.4f}")
      
      st.markdown("**Best Parameters (MACD_RSI):**")
      param_names = ["Fast EMA", "Slow EMA", "Signal", "RSI Window", "RSI Lower", "RSI Upper"]
      if result["best_params"]:
          params_display = {name: val for name, val in zip(param_names, result["best_params"])}
          st.json(params_display)
      else:
          st.warning("최적 파라미터를 찾지 못했습니다.")
      
      # Fitness History Chart
      history = result.get("history", [])
      if history:
          fitness_df = pd.DataFrame({
              "Generation": list(range(len(history))),
              "Fitness": history
          })
          fig = px.line(fitness_df, x="Generation", y="Fitness",
                       title="Fitness Evolution",
                       markers=True)
          st.plotly_chart(fig, use_container_width=True)

[경계 조건 — 하지 말 것]
- evaluator.py의 전략 평가 로직은 건드리지 말 것
- GeneticOptimizer의 DEAP 관련 코드(toolbox, creator)는 변경하지 말 것
- run() 메서드의 핵심 알고리즘 로직은 그대로 유지

[완료 조건]
- "Start Evolution" 버튼 클릭 시 에러 없이 진화 실행
- 진행률 바가 진행 상태를 표시
- 완료 후 Best Fitness Score와 Best Parameters 표시
- Fitness Evolution 차트가 정상 표시
- 수정 파일 목록 + diff 보고
```

---

### ✅ 완료 판정 기준 (Acceptance Criteria)

| # | 기준 | 검증 방법 |
|---|------|----------|
| AC-1 | 가격 데이터 다운로드 로직이 app.py에 존재 | 코드 리뷰 |
| AC-2 | 한국 종목(숫자만 입력) → .KS/.KQ 자동 접미사 추가 | 코드 리뷰 + "005930" 입력 테스트 |
| AC-3 | GeneticOptimizer에 df가 전달됨 | 코드 리뷰 |
| AC-4 | evolve() 반환값에 "history" 키 포함 | 코드 리뷰 |
| AC-5 | Fitness Evolution 차트가 정상 표시 | 대시보드 동작 확인 |
| AC-6 | "Start Evolution" 버튼 클릭 시 에러 없음 | 대시보드 동작 확인 |
| AC-7 | Best Parameters가 MACD/RSI 파라미터명과 함께 표시 | 대시보드 동작 확인 |

---

### 🔍 검증 지시

**검증 프롬프트**:
```
[작업 지시]
이슈 4 "AutoML — 유전 알고리즘 가격 DataFrame 미전달" 구현이 완료되었다고 합니다. 검증해주세요.

[1단계: 정적 검증]
1. dashboard/app.py AutoML 탭 코드를 확인:
   □ yfinance를 사용한 가격 데이터 다운로드 로직이 있는지
   □ 한국 종목(숫자만) → .KS/.KQ 접미사 자동 추가 로직이 있는지
   □ GeneticOptimizer 생성 시 df= 파라미터가 전달되는지
   □ 빈 DataFrame에 대한 에러 처리가 있는지

2. src/optimization/genetic.py를 확인:
   □ run() 반환값에 logbook이 포함되는지
   □ evolve() 반환값에 "history" 키가 포함되는지
   □ run()의 에러 경로에서도 일관된 반환값을 주는지

[2단계: 동적 검증 (브라우저/런타임)]
□ 대시보드 "🧬 AutoML" 탭 이동
□ Test Symbol: "005930" (삼성전자), Population: 20, Generations: 5, Mutation: 0.2
□ "Start Evolution" 클릭
□ 확인:
  - 에러 없이 진행률 바가 진행되는지
  - 완료 후 Best Fitness Score가 표시되는지
  - Best Parameters에 MACD_RSI 파라미터명이 표시되는지
  - Fitness Evolution 차트가 생성되는지
□ Test Symbol: "AAPL" (미국 종목)로도 테스트
  - 에러 없이 동작하는지

[3단계: 에지 케이스 검증]
□ 존재하지 않는 종목 코드 "XXXXXXXXX" 입력 → 적절한 에러 메시지 표시
□ 빈 문자열 입력 → 에러 처리

[보고 형식]
전체 결과: ✅ 통과 / ❌ 실패
- 각 항목별 ✅/❌
- 실패 항목: 재현 단계 + 로그
- 수정 제안 (있는 경우)
```

---

## 이슈 5: Stress Test — 포트폴리오 데이터 미인식

### 🔍 문제 정의

**현상**: Portfolio Stress Test 탭 진입 시 `포트폴리오 데이터를 찾을 수 없습니다. AutoTrader를 먼저 실행하여 포지션을 생성하세요.` 메시지만 표시됨.

**근본 원인**:
1. **조건식 불일치**: `dashboard/app.py` L369에서 `state_data['high_water_marks']`의 존재 여부와 비어있지 않은지를 체크. 현재 `trading_state.json`에 `high_water_marks`가 존재하고 비어있지 않음 (NVDA, 005930, 035420, 000660이 있음).
2. **로드 경로 문제**: `load_state("KR")` 함수에서 `dashboard_kr.json` → `trading_state.json` 순서로 시도하는데, `trading_state.json`의 상대 경로가 Streamlit 실행 디렉토리에 의존. 또한 로드된 state_data의 구조가 `high_water_marks`를 포함하더라도, L369의 AND 조건 3개가 모두 True여야 함.
3. **한국 종목 코드 yfinance 비호환**: `high_water_marks`의 키("005930", "035420", "000660")에 `.KS`/`.KQ` 접미사가 없어 `StressTester`가 yfinance에서 데이터를 가져오지 못함.
4. **근본적 문제**: 포트폴리오가 없어도 스트레스 테스트를 사용할 수 있어야 하지만, 현재 UI가 `high_water_marks`에 의존하여 진입 자체를 차단.

**영향 범위**: Stress Test 탭 전체

---

### 📦 구현 지시

**전제 조건**: 없음 (독립 이슈)

**수정 대상 파일**: `dashboard/app.py`

**구현 프롬프트**:
```
[작업 지시]
harnes 문서 "이슈 5: Stress Test — 포트폴리오 데이터 미인식"을 구현해줘.

[구현 단계]

== 단계 1: Stress Test 탭에 수동 포트폴리오 입력 UI 추가 ==
`dashboard/app.py` L359~L461의 Stress Test 탭 코드를 전면 리팩터링:

- 포트폴리오 데이터가 있든 없든 항상 사용 가능하도록 변경.
- 두 가지 모드 제공:
  1. "수동 입력" — 사용자가 직접 종목과 비율 입력 (기본 모드)
  2. "기존 포트폴리오 사용" — high_water_marks에서 로드

- 구현 코드 (전체 대체):
  with tab8:
      st.header("💥 Portfolio Stress Test")
      if not STRESS_AVAILABLE:
          st.warning("Stress Test 모듈을 로드할 수 없습니다.")
      else:
          st.markdown("### 과거 위기 시나리오에서 포트폴리오 시뮬레이션")
          
          col1, col2 = st.columns([1, 2])
          
          with col1:
              st.subheader("📋 Portfolio Setup")
              
              # 포트폴리오 입력 모드 선택
              mode = st.radio("포트폴리오 입력 방식", 
                             ["수동 입력", "기존 포트폴리오"], 
                             horizontal=True)
              
              if mode == "수동 입력":
                  st.caption("종목 코드와 비율을 입력하세요 (미국: AAPL, 한국: 005930.KS)")
                  
                  # 기본 예시
                  default_portfolio = "AAPL:0.3\nMSFT:0.3\nGOOGL:0.4"
                  portfolio_text = st.text_area(
                      "종목:비율 (한 줄에 하나씩)", 
                      value=default_portfolio,
                      height=150,
                      help="형식: 종목코드:비율 (예: AAPL:0.5)"
                  )
                  
                  # 파싱
                  portfolio_weights = {}
                  try:
                      for line in portfolio_text.strip().split("\n"):
                          if ":" in line:
                              parts = line.strip().split(":")
                              symbol = parts[0].strip()
                              weight = float(parts[1].strip())
                              portfolio_weights[symbol] = weight
                  except ValueError:
                      st.error("비율은 숫자로 입력해주세요 (예: 0.5)")
                      portfolio_weights = {}
                  
                  # 비율 합계 체크
                  if portfolio_weights:
                      total_weight = sum(portfolio_weights.values())
                      if abs(total_weight - 1.0) > 0.01:
                          st.warning(f"비율 합계: {total_weight:.2f} (1.0이 권장됩니다)")
              
              else:  # 기존 포트폴리오
                  state_data = load_state("KR")
                  hwm = state_data.get('high_water_marks', {})
                  if hwm:
                      portfolio_symbols = list(hwm.keys())
                      # 한국 종목에 .KS 접미사 추가 (yfinance 호환)
                      adjusted_symbols = []
                      for s in portfolio_symbols:
                          if s.isdigit():
                              adjusted_symbols.append(f"{s}.KS")
                          else:
                              adjusted_symbols.append(s)
                      weight = 1.0 / len(adjusted_symbols)
                      portfolio_weights = {s: weight for s in adjusted_symbols}
                  else:
                      st.warning("기존 포트폴리오 데이터가 없습니다. 수동 입력을 사용하세요.")
                      portfolio_weights = {}
              
              if portfolio_weights:
                  st.dataframe(pd.DataFrame({
                      "Symbol": list(portfolio_weights.keys()),
                      "Weight": [f"{w*100:.1f}%" for w in portfolio_weights.values()]
                  }))
                  
                  total_value = st.number_input("총 포트폴리오 가치", 
                                               min_value=100, 
                                               max_value=1000000000,
                                               value=10000000,
                                               step=1000000,
                                               help="원화 또는 달러 기준")
                  
                  st.divider()
                  
                  scenario_name = st.selectbox("위기 시나리오",
                                              ["2008_Financial_Crisis",
                                               "2020_Covid_Crash",
                                               "2022_Inflation_Shock"])
                  
                  run_test = st.button("🚀 Run Stress Test", type="primary", key="stress_test_run")
              else:
                  run_test = False
          
          with col2:
              st.subheader("📊 Simulation Results")
              
              if portfolio_weights and run_test:
                  tester = StressTester()
                  
                  with st.spinner(f"Running {scenario_name} simulation..."):
                      result = tester.simulate_scenario(portfolio_weights, total_value, scenario_name)
                  
                  if "error" in result:
                      st.error(f"Error: {result['error']}")
                  else:
                      portfolio_return = result.get("portfolio_return", 0.0)
                      loss_amount = result.get("total_loss_amount", 0.0)
                      
                      st.metric("Portfolio Return", f"{portfolio_return*100:.2f}%",
                               delta=f"{portfolio_return*100:.2f}%")
                      st.metric("Estimated Loss", f"₩{abs(loss_amount):,.0f}",
                               delta=f"{loss_amount:,.0f}")
                      
                      details = result.get("details", {})
                      if details:
                          st.markdown("**종목별 수익률:**")
                          details_df = pd.DataFrame({
                              "Symbol": list(details.keys()),
                              "Return (%)": [f"{v*100:.2f}%" for v in details.values()]
                          })
                          st.dataframe(details_df, use_container_width=True)
                          
                          fig = px.bar(details_df, x="Symbol", y="Return (%)",
                                      title=f"Asset Returns in {scenario_name}")
                          st.plotly_chart(fig, use_container_width=True)
                      
                      if portfolio_return < -0.20:
                          st.error("🔴 **고위험**: 이 시나리오에서 20% 이상 손실!")
                      elif portfolio_return < -0.10:
                          st.warning("🟡 **중위험**: 이 시나리오에서 10~20% 손실.")
                      else:
                          st.success("🟢 **저위험**: 포트폴리오가 비교적 견고합니다.")
              else:
                  st.info("포트폴리오를 설정하고 시나리오를 선택한 후 테스트를 실행하세요.")

- 변경 이유: 기존 코드는 high_water_marks가 비어있으면 아무것도 할 수 없었음.
  수동 입력 모드를 추가하여 AutoTrader 없이도 Stress Test를 사용 가능하게 함.
  또한 한국 종목 코드에 .KS 접미사를 자동으로 추가하여 yfinance 호환성 확보.

[경계 조건 — 하지 말 것]
- StressTester 클래스 자체의 로직은 변경하지 말 것
- 기존 load_state() 함수는 변경하지 말 것

[완료 조건]
- Stress Test 탭 진입 시 수동 입력 UI 표시
- 수동 입력으로 포트폴리오 구성 후 Stress Test 실행 가능
- 기존 포트폴리오 데이터가 있는 경우에도 정상 동작
- 수정 파일 목록 + diff 보고
```

---

### ✅ 완료 판정 기준 (Acceptance Criteria)

| # | 기준 | 검증 방법 |
|---|------|----------|
| AC-1 | Stress Test 탭 진입 시 UI가 정상 표시 (에러 메시지 아님) | 대시보드 동작 확인 |
| AC-2 | "수동 입력" 모드에서 포트폴리오 직접 입력 가능 | UI 동작 확인 |
| AC-3 | "기존 포트폴리오" 모드에서 high_water_marks 데이터 정상 로드 | UI 동작 확인 |
| AC-4 | 한국 종목 코드에 .KS 접미사 자동 추가 | 코드 리뷰 |
| AC-5 | Stress Test 실행 시 결과가 정상 표시 | 대시보드 동작 확인 |
| AC-6 | 비율 합계 1.0이 아닌 경우 경고 메시지 표시 | UI 동작 확인 |

---

### 🔍 검증 지시

**검증 프롬프트**:
```
[작업 지시]
이슈 5 "Stress Test — 포트폴리오 데이터 미인식" 구현이 완료되었다고 합니다. 검증해주세요.

[1단계: 정적 검증]
1. dashboard/app.py의 Stress Test 탭 코드를 확인:
   □ 수동 입력 / 기존 포트폴리오 라디오 버튼이 있는지
   □ 수동 입력 모드에서 text_area 파싱 로직이 올바른지
   □ 기존 포트폴리오 모드에서 한국 종목 .KS 접미사 추가 로직이 있는지
   □ 비율 합계 검증 로직이 있는지
   □ 예외 처리(try-except)가 적절히 있는지

[2단계: 동적 검증 (브라우저/런타임)]
□ 대시보드 "💥 Stress Test" 탭 이동
□ "수동 입력" 모드 선택 → 기본 예시(AAPL, MSFT, GOOGL)로 테스트
  - 포트폴리오 테이블이 정상 표시되는지
  - "Run Stress Test" 클릭 후 결과가 표시되는지
□ "기존 포트폴리오" 모드 선택
  - high_water_marks에서 종목이 로드되는지
  - .KS 접미사가 추가되어 표시되는지
□ 시나리오 변경(2008, 2020, 2022) 각각 테스트
□ 잘못된 비율 입력(문자열) → 적절한 에러 메시지

[보고 형식]
전체 결과: ✅ 통과 / ❌ 실패
- 각 항목별 ✅/❌
- 실패 항목: 재현 단계 + 스크린샷/로그
- 수정 제안 (있는 경우)
```

---

## 이슈 6: Multi-Agent Debate — 모델 단종 + 잘못된 티커 전달

### 🔍 문제 정의

**현상**: 
1. 서버 콘솔에 `404 models/gemini-1.5-flash is not found` 에러 반복
2. `$SAMSUNG ELECTRONICS: possibly delisted; no price data found` — Yahoo Finance에서 "Samsung Electronics"를 찾을 수 없음
3. 사용자 화면에 모든 에이전트가 "I have nothing to add."만 표시

**근본 원인**:
1. **Gemini 모델 단종**: `debate.py` L18에서 `model="gemini-1.5-flash"`를 하드코딩하고 있어 404 에러. → 이슈 #3에서 수정됨.
2. **잘못된 티커 전달**: `dashboard/app.py` L475에서 `dm.run_debate("Samsung Electronics")`로 호출. Yahoo Finance는 영문 풀네임이 아닌 티커 심볼(예: `005930.KS` 또는 `SSNLF`)을 요구함.
3. **한국어 종목명 미지원**: `DebateManager.run_debate()`에서 ticker를 `MarketDataFetcher.fetch_history()`에 직접 전달하는데, Yahoo Finance에서 "Samsung Electronics"라는 심볼은 존재하지 않으므로 데이터를 가져올 수 없음.
4. **LLM 초기화 실패 연쇄**: LLM 초기화 실패 → `speak()` 에서 fallback 메시지 "I have nothing to add." 반환 → 모든 에이전트가 동일 메시지 → 의미 있는 토론 불가.

**영향 범위**: Agent Debate 탭 전체

---

### 📦 구현 지시

**전제 조건**:
- 이슈 #3(모델명 변경)이 완료되어 있어야 함

**수정 대상 파일**: `dashboard/app.py`, `src/copilot/debate.py`

**구현 프롬프트**:
```
[작업 지시]
harnes 문서 "이슈 6: Multi-Agent Debate — 모델 단종 + 잘못된 티커 전달"을 구현해줘.

[구현 단계]

== 단계 1: Debate 탭 UI 개선 — 사용자가 유효한 티커를 입력하도록 ==
`dashboard/app.py` L467~L476 수정:

- 현재 코드:
  with tab9:
      st.header("💬 Multi-Agent Debate Consensus")
      if not DEBATE_AVAILABLE:
          st.warning("Debate 모듈을 로드할 수 없습니다.")
      else:
          st.info("여러 AI 에이전트가 매매 여부를 두고 토론합니다.")
          if st.button("Start Debate", key="debate_btn"):
              dm = DebateManager()
              consensus = dm.run_debate("Samsung Electronics")
              st.json(consensus)

- 변경할 코드:
  with tab9:
      st.header("💬 Multi-Agent Debate Consensus")
      if not DEBATE_AVAILABLE:
          st.warning("Debate 모듈을 로드할 수 없습니다.")
      else:
          st.info("여러 AI 에이전트(Technical Analyst, Risk Manager, Moderator)가 매매 여부를 두고 토론합니다.")
          
          col1, col2 = st.columns([1, 3])
          
          with col1:
              # 인기 종목 프리셋
              preset = st.selectbox("종목 프리셋", 
                                   ["직접 입력",
                                    "삼성전자 (005930.KS)",
                                    "SK하이닉스 (000660.KS)",
                                    "NVIDIA (NVDA)",
                                    "Apple (AAPL)",
                                    "Tesla (TSLA)"])
              
              if preset == "직접 입력":
                  debate_ticker = st.text_input("종목 코드 (Yahoo Finance 형식)",
                                               value="AAPL",
                                               help="예: AAPL, TSLA, 005930.KS, 000660.KS",
                                               key="debate_ticker_input")
              else:
                  # 프리셋에서 티커 추출 (괄호 안의 값)
                  import re
                  match = re.search(r'\(([^)]+)\)', preset)
                  debate_ticker = match.group(1) if match else "AAPL"
                  st.info(f"선택된 티커: **{debate_ticker}**")
              
              start_debate = st.button("🚀 Start Debate", type="primary", key="debate_btn")
          
          with col2:
              if start_debate:
                  with st.spinner(f"🗣️ {debate_ticker}에 대한 토론 진행 중... (30초~1분 소요)"):
                      try:
                          dm = DebateManager()
                          consensus = dm.run_debate(debate_ticker)
                      except Exception as e:
                          st.error(f"토론 중 오류가 발생했습니다: {e}")
                          consensus = None
                  
                  if consensus:
                      # 최종 판정 표시
                      decision = consensus.get("decision", "HOLD")
                      color_map = {"BUY": "green", "SELL": "red", "HOLD": "orange"}
                      st.markdown(f"### 📊 최종 판정: :{color_map.get(decision, 'gray')}[{decision}]")
                      
                      st.divider()
                      
                      # 토론 내용 표시
                      for entry in consensus.get("history", []):
                          agent_name = entry.get("agent", "Unknown")
                          msg = entry.get("msg", "")
                          
                          # 에이전트별 아이콘
                          icon_map = {
                              "Technical Analyst": "📈",
                              "Risk Manager": "🛡️",
                              "Moderator": "⚖️"
                          }
                          icon = icon_map.get(agent_name, "💬")
                          
                          with st.expander(f"{icon} {agent_name}", expanded=True):
                              st.markdown(msg)
              else:
                  st.info("종목을 선택하고 토론을 시작하세요.")

- 변경 이유: 
  1. "Samsung Electronics" 같은 영문 풀네임 대신 유효한 Yahoo Finance 티커를 사용
  2. 사용자가 직접 티커를 입력하거나 프리셋에서 선택할 수 있도록 UI 개선
  3. 토론 결과를 JSON 덤프 대신 시각적으로 보기 좋게 표시

== 단계 2: debate.py에서 LLM 초기화 실패 시 더 나은 에러 처리 ==
`src/copilot/debate.py`의 AnalystAgent.speak() 메서드 수정:

- 현재 코드 (L30~L31):
  if not self.llm:
      return "Error: LLM not initialized."

- 변경할 코드:
  if not self.llm:
      return f"⚠️ {self.name}: LLM 초기화 실패. API 키와 모델명을 확인하세요."

- 또한 L60~L61:
  현재: return "I have nothing to add."
  변경: return f"⚠️ {self.name}: 분석 생성 중 오류 발생 — {str(e)[:200]}"

- 변경 이유: 에러 시 사용자에게 더 의미 있는 메시지를 표시하여 
  문제 원인을 파악할 수 있도록 함.

== 단계 3: debate.py의 run_debate에서 데이터 없을 때 컨텍스트 개선 ==
`src/copilot/debate.py` L82~L89 수정:

- 현재 코드:
  try:
      df = self.market_fetcher.fetch_history(ticker, period="1mo")
      current_price = df['Close'].iloc[-1]
      change = (df['Close'].iloc[-1] - df['Close'].iloc[0]) / df['Close'].iloc[0] * 100
      context = f"Ticker: {ticker}. Current Price: {current_price:.2f}. ..."
  except Exception as e:
      context = f"Ticker: {ticker}. Data unavailable. ..."

- 변경할 코드 (except 부분 개선):
  except Exception as e:
      logger.warning(f"시장 데이터 조회 실패 ({ticker}): {e}")
      context = (f"Ticker: {ticker}. Market data is currently unavailable. "
                 f"Please provide general analysis based on your knowledge of this asset. "
                 f"Focus on recent market trends and sector performance.")

- 변경 이유: 데이터가 없더라도 LLM이 일반 지식으로 분석할 수 있도록
  더 유용한 프롬프트 컨텍스트를 제공.

[경계 조건 — 하지 말 것]
- DebateManager의 에이전트 구성(3명, 역할)은 변경하지 말 것
- MarketDataFetcher의 로직은 변경하지 말 것
- 기존 run_debate()의 반환 구조({ticker, decision, history})는 유지

[완료 조건]
- Debate 탭에서 "Start Debate" 클릭 시 에러 없이 토론 진행
- 각 에이전트의 분석 내용이 의미 있게 표시 (빈 메시지 아님)
- 최종 판정(BUY/SELL/HOLD)이 색상과 함께 표시
- 서버 콘솔에 404 에러 없음
- 수정 파일 목록 + diff 보고
```

---

### ✅ 완료 판정 기준 (Acceptance Criteria)

| # | 기준 | 검증 방법 |
|---|------|----------|
| AC-1 | 종목 프리셋 또는 직접 입력 UI가 있음 | 대시보드 동작 확인 |
| AC-2 | 유효한 티커(예: AAPL)로 토론 시 에러 없이 진행 | 대시보드 동작 확인 |
| AC-3 | 각 에이전트가 의미 있는 분석 내용을 표시 | 토론 결과 확인 |
| AC-4 | 최종 판정이 색상/아이콘과 함께 시각적으로 표시 | UI 확인 |
| AC-5 | 서버 콘솔에 404 에러 없음 | 터미널 로그 확인 |
| AC-6 | LLM 에러 시 "I have nothing to add." 대신 의미있는 에러 메시지 표시 | 에러 시나리오 확인 |
| AC-7 | 한국 종목(005930.KS) 프리셋으로도 토론 가능 | 대시보드 동작 확인 |

---

### 🔍 검증 지시

**검증 프롬프트**:
```
[작업 지시]
이슈 6 "Multi-Agent Debate — 모델 단종 + 잘못된 티커 전달" 구현이 완료되었다고 합니다. 검증해주세요.

[1단계: 정적 검증]
1. dashboard/app.py의 Agent Debate 탭 코드를 확인:
   □ "Samsung Electronics" 문자열이 제거되었는지
   □ 종목 프리셋 selectbox 또는 text_input이 있는지
   □ 프리셋에서 티커 추출 로직이 올바른지
   □ 토론 결과가 시각적으로 표시되는 코드가 있는지 (JSON 덤프 아님)
   □ try-except로 에러 처리가 되어 있는지

2. src/copilot/debate.py를 확인:
   □ AnalystAgent.__init__에서 model이 Config.LLM_MODEL_NAME인지 (이슈 #3)
   □ speak()의 에러 메시지가 개선되었는지
   □ run_debate()의 데이터 미조회 시 컨텍스트가 개선되었는지

3. 프로젝트 전체에서 "Samsung Electronics" 문자열 검색:
   □ grep 결과가 0건인지

[2단계: 동적 검증 (브라우저/런타임)]
□ 대시보드 "💬 Agent Debate" 탭 이동
□ 시나리오 1: 프리셋 "Apple (AAPL)" 선택 → Start Debate 클릭
  - 에러 없이 토론 진행되는지
  - 각 에이전트의 분석이 의미 있는 내용인지 (빈 메시지 아님)
  - 최종 판정이 표시되는지
□ 시나리오 2: 프리셋 "삼성전자 (005930.KS)" 선택 → Start Debate 클릭
  - 에러 없이 진행되는지
□ 시나리오 3: 직접 입력 → 잘못된 티커 "XXXXXXXXX" → Start Debate 클릭
  - 적절한 에러 처리 또는 데이터 없이도 토론 진행
□ 서버 콘솔에 404 에러가 없는지 확인

[3단계: 회귀 검증]
□ AI Copilot 탭 정상 동작 확인
□ Deep Analysis 탭 정상 동작 확인

[보고 형식]
전체 결과: ✅ 통과 / ❌ 실패
- 각 항목별 ✅/❌
- 실패 항목: 재현 단계 + 로그
- 수정 제안 (있는 경우)
```

---

## 📋 실행 순서

### 권장 순서
이슈 #3 → 이슈 #1 + #2 (병렬) → 이슈 #4 → 이슈 #5 → 이슈 #6

### 순서 결정 근거
- **#3이 최우선**: Gemini 모델명 변경은 #6(Debate)의 전제 조건이며, 다른 AI 기능(Copilot, Deep Analysis)에도 영향을 줌. 가장 광범위한 영향.
- **#1, #2 병렬 가능**: 같은 파일이지만 수정 영역이 다름. 한 세션에서 순차 처리 권장.
- **#4 독립**: AutoML 탭만 영향. 다른 이슈와 무관.
- **#5 독립**: Stress Test 탭만 영향.
- **#6은 #3 이후**: 모델명 변경이 완료된 후에야 Debate 기능이 정상 동작 가능.

### 병렬 실행 가능 그룹
- **그룹 A (병렬 가능)**: #3, #4, #5 — 서로 다른 파일/탭, 상호 의존성 없음
- **그룹 B (#3 완료 후)**: #6
- **그룹 C (독립 병렬)**: #1, #2 — 같은 파일이므로 순차 처리가 안전하나, 서브에이전트가 다른 파일 작업과는 병렬 가능

---

## 🚨 장애 대응

### 검증 실패 시
```
[이전 구현에서 아래 검증 결과가 나왔어. 수정해줘]
{검증 AI의 보고서 붙여넣기}
해당 이슈의 구현 지시를 다시 확인하고 위 버그들을 모두 수정해줘.
```

### 구현 중 문서와 충돌 발견 시
1. 구현을 중단
2. 충돌 내용을 보고 (어떤 지시가 현재 코드와 맞지 않는지)
3. 문서 수정 후 재개

### 롤백이 필요한 경우
1. `git stash` 또는 `git checkout -- .` 으로 변경 사항 복원
2. 실패 원인 분석 보고
3. 문서의 구현 지시를 수정한 후 재시도

### gemini-2.5-flash 모델이 동작하지 않는 경우
1. `python -c "import google.generativeai as genai; genai.configure(api_key='YOUR_KEY'); [print(m.name) for m in genai.list_models()]"` 실행
2. 사용 가능한 모델 목록에서 적절한 대체 모델 선택
3. `.env`의 `LLM_MODEL_NAME`을 해당 모델로 변경

### yfinance 한국 종목 데이터 완전 실패 시
1. 대체 데이터 소스 검토 (pykrx, FinanceDataReader 등)
2. 해당 라이브러리 설치: `uv pip install pykrx`
3. growth_stock_finder.py에 대체 데이터 수집 로직 추가
4. 이 경우 이슈 #1의 구현 지시를 문서에서 업데이트할 것
