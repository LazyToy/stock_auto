# 한국투자증권 API 키 발급 가이드

## 1. 계좌 개설

### 모의투자 계좌 (테스트용)
1. [한국투자증권 OpenAPI 포털](https://apiportal.koreainvestment.com) 접속
2. 회원가입 (간편 가입 가능)
3. 상단 메뉴에서 **[모의투자]** 클릭
4. **[모의투자 신청]** 버튼 클릭
5. 약관 동의 후 신청 완료
6. 모의투자 계좌번호 확인 (마이페이지에서 확인 가능)

### 실전투자 계좌
- 한국투자증권 영업점 방문 또는 온라인으로 실제 계좌 개설 필요
- 비대면 계좌 개설: [한국투자증권 홈페이지](https://www.koreainvestment.com)

## 2. API 키 발급

### Step 1: 앱 등록
1. OpenAPI 포털 로그인
2. 상단 메뉴 **[개발자]** > **[앱 등록]** 클릭
3. 앱 정보 입력:
   - **앱 이름**: `stock_auto` (원하는 이름)
   - **앱 설명**: `주식 자동매매 시스템`
   - **사용 목적**: 개인 투자용
4. **[등록]** 버튼 클릭

### Step 2: API 키 확인
1. **[마이페이지]** > **[나의 앱]** 메뉴로 이동
2. 등록한 앱 클릭
3. **앱키(App Key)** 와 **앱시크릿(App Secret)** 확인
4. ⚠️ **중요**: 앱시크릿은 다시 확인할 수 없으므로 안전한 곳에 보관!

### Step 3: 계좌 연결
1. 앱 상세 페이지에서 **[계좌 연결]** 클릭
2. 모의투자 계좌 또는 실전 계좌 선택
3. 계좌번호 입력 및 확인

## 3. 환경 변수 설정

프로젝트의 `.env` 파일에 발급받은 정보를 입력하세요:

```env
# 모의투자 설정
KIS_APP_KEY=발급받은_앱키_입력
KIS_APP_SECRET=발급받은_앱시크릿_입력
KIS_ACCOUNT_NUMBER=모의투자_계좌번호_8자리
KIS_ACCOUNT_PRODUCT_CODE=01

# 거래 모드 (mock: 모의투자, real: 실전투자)
TRADING_MODE=mock
```

**실전투자를 사용하는 경우** (충분한 테스트 후):
```env
# 실전투자 설정
KIS_REAL_APP_KEY=실전_앱키
KIS_REAL_APP_SECRET=실전_앱시크릿
KIS_REAL_ACCOUNT_NUMBER=실전_계좌번호
KIS_REAL_ACCOUNT_PRODUCT_CODE=01

# 거래 모드를 real로 변경
TRADING_MODE=real
```

## 4. API 연결 테스트

API 키가 정상적으로 작동하는지 테스트:

```python
from dotenv import load_dotenv
import os
from src.data.api_client import KISAPIClient

# 환경 변수 로드
load_dotenv()

# 클라이언트 생성
client = KISAPIClient(
    app_key=os.getenv("KIS_APP_KEY"),
    app_secret=os.getenv("KIS_APP_SECRET"),
    account_number=os.getenv("KIS_ACCOUNT_NUMBER"),
    account_product_code=os.getenv("KIS_ACCOUNT_PRODUCT_CODE"),
    is_mock=True  # 모의투자
)

# 삼성전자 현재가 조회 테스트
try:
    price = client.get_current_price("005930")
    print(f"삼성전자 현재가: {price:,}원")
    print("✅ API 연결 성공!")
except Exception as e:
    print(f"❌ API 연결 실패: {e}")
```

## 5. API 사용 제한

### Rate Limit
- **초당 요청 수**: 최대 20건
- **일일 요청 수**: 모의투자는 제한 없음, 실전투자는 확인 필요
- 제한 초과 시 429 에러 발생

### 운영 시간
- **한국 주식시장**: 평일 09:00 ~ 15:30
- **장전/장후 시간외**: 08:30 ~ 09:00, 15:40 ~ 16:00
- **모의투자**: 평일 09:00 ~ 15:30 (장중 시간만)

## 6. 문제 해결

### 토큰 발급 실패
- 앱키와 앱시크릿이 정확한지 확인
- 네트워크 연결 확인
- OpenAPI 포털에서 앱 상태 확인 (활성화 여부)

### 조회/주문 실패
- 액세스 토큰이 만료되었을 가능성 → 자동 재발급됨
- 종목 코드가 정확한지 확인 (6자리)
- 장 운영 시간인지 확인

### 모의투자 주문 체결 안됨
- 모의투자는 실제 시장 가격으로 체결되므로 시장가 주문 권장
- 지정가 주문은 호가와 일치해야 체결됨

## 7. 참고 자료

- [한국투자증권 OpenAPI 문서](https://apiportal.koreainvestment.com/apiservice/)
- [API 사용 가이드 (PDF)](https://apiportal.koreainvestment.com/intro)
- [GitHub 샘플 코드](https://github.com/koreainvestment/open-trading-api)

## 8. 보안 주의사항

⚠️ **절대 API 키를 공개 저장소에 업로드하지 마세요!**

- `.env` 파일은 `.gitignore`에 포함되어 있어 Git에 추적되지 않습니다
- API 키가 유출되면 즉시 OpenAPI 포털에서 재발급하세요
- 실전 계좌 사용 시 특히 주의하세요
