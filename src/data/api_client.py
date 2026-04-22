"""한국투자증권 API 클라이언트

REST API를 사용하여 주식 데이터 조회 및 주문 실행을 수행합니다.
"""

import requests
import time
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from src.data.models import StockPrice, Order, Position, Account, OrderSide, OrderType
from src.config import Config
from src.utils.logger import get_logger

logger = get_logger(__name__)

class APIError(Exception):
    """API 에러"""
    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

class AuthenticationError(APIError):
    """인증 실패 에러"""
    pass

class RateLimiter:
    """토큰 버킷 방식의 Rate Limiter"""
    def __init__(self, max_tokens: int = 20, refill_rate: float = 5.0):
        """
        Args:
            max_tokens: 최대 토큰 수 (버킷 크기) - 순간 트래픽 허용량
            refill_rate: 초당 충전되는 토큰 수 - 지속 트래픽 제한
        """
        self.max_tokens = max_tokens
        self.tokens = max_tokens
        self.refill_rate = refill_rate
        self.last_update = time.time()
        
    def wait(self):
        """토큰이 생길 때까지 대기"""
        while True:
            now = time.time()
            elapsed = now - self.last_update
            
            # 토큰 충전
            new_tokens = elapsed * self.refill_rate
            if new_tokens > 0:
                self.tokens = min(self.max_tokens, self.tokens + new_tokens)
                self.last_update = now
            
            if self.tokens >= 1:
                self.tokens -= 1
                return
            
            # 대기 (부족할 경우)
            wait_time = (1 - self.tokens) / self.refill_rate
            time.sleep(max(0.05, min(wait_time, 1.0)))


class KISAPIClient:
    """한국투자증권 API 클라이언트
    
    Attributes:
        app_key: 앱 키
        app_secret: 앱 시크릿
        account_number: 계좌번호
        account_product_code: 상품코드 (보통 "01")
        is_mock: 모의투자 여부
        max_retries: 최대 재시도 횟수
    """
    
    def __init__(
        self,
        app_key: str = None,
        app_secret: str = None,
        account_number: str = None,
        account_product_code: str = "01",
        is_mock: bool = True,
        max_retries: int = 3,
        market: str = "KR"  # "KR" or "US"
    ):
        """초기화
        
        Args:
            app_key: 앱 키 (None이면 Config 사용)
            app_secret: 앱 시크릿 (None이면 Config 사용)
            account_number: 계좌번호 (None이면 Config 사용)
            account_product_code: 상품코드
            is_mock: 모의투자 여부
            max_retries: 최대 재시도 횟수
            market: 시장 구분 ("KR": 국내, "US": 미국)
        """
        self.app_key = app_key or Config.KIS_APP_KEY
        self.app_secret = app_secret or Config.KIS_APP_SECRET
        self.account_number = account_number or Config.KIS_ACCOUNT_NUMBER
        self.account_product_code = account_product_code or Config.KIS_ACCOUNT_PRODUCT_CODE
        self.is_mock = is_mock
        self.max_retries = max_retries
        self.market = market
        
        self.base_url = Config.URL_MOCK if is_mock else Config.URL_REAL
        self.access_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        
        if not self.app_key or not self.app_secret or not self.account_number:
            logger.warning("API Key 또는 계좌 정보가 설정되지 않았습니다. Config.validate()를 확인하세요.")
            
        # Rate Limiter 초기화 (초당 5회 제한 예시)
        # 실전/모의투자에 따라 다르게 설정 가능
        limit_rate = 2.0 if is_mock else 10.0 # 모의투자는 좀 더 보수적으로, 실전은 10~20
        self.rate_limiter = RateLimiter(max_tokens=10, refill_rate=limit_rate)

    
    def _ensure_token(self):
        """액세스 토큰 유효성 확인 및 갱신"""
        if self.access_token is None:
            self.get_access_token()
            return

        # 토큰 만료 여부 확인 (여유 시간 60초)
        if self.token_expires_at and (datetime.now() - self.token_expires_at).total_seconds() > -60:
            logger.info("토큰 만료 임박, 재발급 시도...")
            self.get_access_token()

    def get_access_token(self):
        """접근 토큰 발급"""
        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        
        try:
            res = requests.post(url, headers=headers, json=body, timeout=10)
            res.raise_for_status()
            data = res.json()
            
            self.access_token = data['access_token']
            
            # 만료 시간 설정 (expires_in은 초 단위)
            expires_in = int(data.get('expires_in', 86400))
            self.token_expires_at = datetime.now() + timedelta(seconds=expires_in)
            
            logger.info(f"Access Token 발급 완료. 만료: {self.token_expires_at}")
            
            return self.access_token

        except Exception as e:
            logger.error(f"Token 발급 실패: {e}")
            raise AuthenticationError("토큰 발급 실패", response_body=str(e))

    def _make_request(self, method: str, url: str, headers: dict, params: dict = None, json_data: dict = None) -> dict:
        """API 요청 공통 함수"""
        # Rate Limiting
        self.rate_limiter.wait()
        
        for attempt in range(self.max_retries):

            try:
                method_name = method.upper()
                if method_name == "GET":
                    res = requests.get(url, headers=headers, params=params, timeout=10)
                elif method_name == "POST":
                    res = requests.post(url, headers=headers, json=json_data, timeout=10)
                else:
                    res = requests.request(method_name, url, headers=headers, params=params, json=json_data, timeout=10)
                
                # 에러 처리
                if res.status_code != 200:
                    logger.error(f"API Error ({res.status_code}): {res.text}")
                    try:
                        body = res.json()
                        message = body.get("msg1") or body.get("message") or str(body)
                    except Exception:
                        message = res.text
                    raise APIError(message, status_code=res.status_code, response_body=res.text)
                    # 만약 토큰 만료 에러라면 재발급 시도 로직이 필요할 수 있음 (여기선 생략)
                
                res.raise_for_status()
                return res.json()
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"API Request Failed (Attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt == self.max_retries - 1:
                    raise APIError(f"API 호출 실패 (Max Retries Exceeded): {e}") from e
                time.sleep(1) # 재시도 대기

    def get_current_price(self, symbol: str, exchange: str = "NASD") -> float:
        """현재가 조회
        
        Args:
            symbol: 종목 코드
            exchange: 거래소 코드 (US only, e.g., NASD, NYSE, AMEX)
        """
        self._ensure_token()
        
        if self.market == "KR":
            url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
            tr_id = "FHKST01010100"
            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": symbol
            }
            # 국내주식 앱키 헤더 사용
        else: # US
            url = f"{self.base_url}/uapi/overseas-price/v1/quotations/price"
            tr_id = "HHDFS00000300"
            params = {
                "AUTH": "",
                "EXCD": exchange,
                "SYMB": symbol
            }
            
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id
        }
        
        result = self._make_request("GET", url, headers, params=params)
        
        try:
            if self.market == "KR":
                return float(result["output"]["stck_prpr"])
            else:
                return float(result["output"]["last"])
        except (KeyError, ValueError) as e:
            logger.error(f"현재가 응답 파싱 오류: {e}, Response: {result}")
            return 0.0

    def place_order(self, order: Order, exchange: str = "NASD") -> str:
        """주문 실행"""
        self._ensure_token()
        
        if self.market == "KR":
            # (기존 국내 주식 주문 로직)
            if self.is_mock:
                tr_id = "VTTC0802U" if order.side == OrderSide.BUY else "VTTC0801U"
            else:
                tr_id = "TTTC0802U" if order.side == OrderSide.BUY else "TTTC0801U"
            
            url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
            
            if order.order_type == OrderType.MARKET:
                ord_dv = "01"
                price = "0"
            else:
                ord_dv = "00"
                price = str(int(order.price))
                
            data = {
                "CANO": self.account_number,
                "ACNT_PRDT_CD": self.account_product_code,
                "PDNO": order.symbol,
                "ORD_DVSN": ord_dv,
                "ORD_QTY": str(order.quantity),
                "ORD_UNPR": price
            }
        
        else: # US
            # 미국 주식 주문
            if self.is_mock:
                tr_id = "VTTT1002U" if order.side == OrderSide.BUY else "VTTT1001U"
            else:
                tr_id = "TTTT1002U" if order.side == OrderSide.BUY else "TTTT1001U"
                
            url = f"{self.base_url}/uapi/overseas-stock/v1/trading/order"
            
            # 미국은 보통 지정가(Limit) 주문
            ord_dv = "00" 
            price = str(order.price)
            
            data = {
                "CANO": self.account_number,
                "ACNT_PRDT_CD": self.account_product_code,
                "OVRS_EXCG_CD": exchange,
                "PDNO": order.symbol,
                "ORD_QTY": str(order.quantity),
                "OVRS_ORD_UNPR": price,
                "ORD_SVR_DVSN_CD": "0"
            }
            
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id
        }
        
        result = self._make_request("POST", url, headers, json_data=data)
        
        try:
            if self.market == "KR":
                ord_no = result["output"]["ODNO"]
            else:
                ord_no = result["output"]["ORD_NO"]
            logger.info(f"주문 접수 완료: {order.symbol} {order.side} {order.quantity}주, 주문번호: {ord_no}")
            return ord_no
        except KeyError:
            logger.error(f"주문 응답 파싱 오류: {result}")
            raise APIError("주문 응답 파싱 실패", response_body=str(result))

    def get_account_balance(self, exchange: str = "NASD") -> Account:
        """계좌 잔고 조회"""
        self._ensure_token()
        
        if self.market == "KR":
            # (기존 국내 잔고 조회 로직)
            url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
            tr_id = "VTTC8434R" if self.is_mock else "TTTC8434R"
            params = {
                "CANO": self.account_number,
                "ACNT_PRDT_CD": self.account_product_code,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "01",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": ""
            }
        else: # US
            url = f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-balance"
            tr_id = "VTTS3012R" if self.is_mock else "TTTS3012R"
            params = {
                "CANO": self.account_number,
                "ACNT_PRDT_CD": self.account_product_code,
                "OVRS_EXCG_CD": exchange,
                "TR_CRCY_CD": "USD",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": ""
            }
            
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id
        }
        
        result = self._make_request("GET", url, headers, params=params)
        
        try:
            if self.market == "KR":
                # API 응답 구조에 따라 키 확인 필요
                output2 = result.get("output2", [])
                cash = float(output2[0]["dnca_tot_amt"]) if output2 else 0.0
                
                positions = []
                for item in result.get("output1", []):
                    if int(item.get("hldg_qty", "0")) > 0:
                        positions.append(Position(
                            symbol=item["pdno"],
                            quantity=int(item["hldg_qty"]),
                            avg_price=float(item["pchs_avg_pric"]),
                            current_price=float(item["prpr"]),
                            exchange="KR"
                        ))
            else: # US
                output2 = result.get("output2", {})
                cash = float(output2.get("frcr_dnca_tot_amt", 0)) # 외화예수금
                
                positions = []
                for item in result.get("output1", []):
                    # ovrs_cblc_qty가 실수형 문자열일 수 있음
                    qty = float(item.get("ovrs_cblc_qty", "0"))
                    if qty > 0:
                        positions.append(Position(
                            symbol=item["ovrs_pdno"],
                            quantity=int(qty),
                            avg_price=float(item["pchs_avg_pric"]),
                            current_price=float(item["now_pric2"]),
                            exchange=item.get("ovrs_excg_cd", "NASD") # Default to NASD if missing
                        ))
            
            # total_value는 Account의 property로 자동 계산됨
            return Account(account_number=self.account_number, cash=cash, positions=positions)
            
        except (KeyError, ValueError, IndexError) as e:
            logger.error(f"잔고 응답 파싱 오류: {e}, Response: {result}")
            return Account(account_number=self.account_number, cash=0, positions=[])
    
    def get_minute_price(self, symbol: str, interval: int = 1, count: int = 100, exchange: str = "NASD") -> List[StockPrice]:
        """분봉 데이터 조회
        
        Args:
            symbol: 종목 코드
            interval: 분봉 간격 (1, 3, 5, 10, 15, 30, 60)
            count: 조회 개수 (최대 100)
            exchange: 거래소 코드 (US only)
        
        Returns:
            분봉 데이터 리스트
        """
        self._ensure_token()
        
        if self.market == "KR":
            # 국내 분봉 조회
            url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
            tr_id = "FHKST03010200"
            
            # 현재 시간
            now = datetime.now()
            end_time = now.strftime("%H%M%S")
            
            params = {
                "FID_ETC_CLS_CODE": "",
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": symbol,
                "FID_INPUT_HOUR_1": end_time,
                "FID_PW_DATA_INCU_YN": "N"
            }
        else:
            # 미국 분봉 조회
            url = f"{self.base_url}/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice"
            tr_id = "HHDFS76950200"
            params = {
                "AUTH": "",
                "EXCD": exchange,
                "SYMB": symbol,
                "NMIN": str(interval),
                "PINC": "1",
                "NEXT": "",
                "NREC": str(count),
                "FILL": "",
                "KEYB": ""
            }
        
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id
        }
        
        try:
            result = self._make_request("GET", url, headers, params=params)
            
            prices = []
            output_key = "output2" if self.market == "KR" else "output2"
            
            for item in result.get(output_key, []):
                if self.market == "KR":
                    prices.append(StockPrice(
                        date=datetime.strptime(item["stck_cntg_hour"], "%H%M%S"),
                        open=float(item.get("stck_oprc", 0)),
                        high=float(item.get("stck_hgpr", 0)),
                        low=float(item.get("stck_lwpr", 0)),
                        close=float(item.get("stck_prpr", 0)),
                        volume=int(item.get("cntg_vol", 0))
                    ))
                else:
                    prices.append(StockPrice(
                        date=datetime.strptime(item.get("xymd", "") + item.get("xhms", ""), "%Y%m%d%H%M%S"),
                        open=float(item.get("open", 0)),
                        high=float(item.get("high", 0)),
                        low=float(item.get("low", 0)),
                        close=float(item.get("last", 0)),
                        volume=int(float(item.get("evol", 0)))
                    ))
            
            return prices
            
        except Exception as e:
            logger.error(f"분봉 데이터 조회 실패: {e}")
            return []
    
    def place_limit_order(self, symbol: str, side: OrderSide, quantity: int, price: float, exchange: str = "NASD") -> str:
        """지정가 주문"""
        order = Order(
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            price=price,
            quantity=quantity,
            created_at=datetime.now()
        )
        return self.place_order(order, exchange)
                    
    def cancel_order(self, order_id: str, symbol: str, quantity: int) -> dict:
        """주문 취소

        Args:
            order_id: 취소할 주문 번호
            symbol: 종목 코드
            quantity: 취소 수량

        Returns:
            취소 결과 dict
        """
        self._ensure_token()

        if self.is_mock:
            tr_id = "VTTC0803U"
        else:
            tr_id = "TTTC0803U"

        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-rvsecncl"

        data = {
            "CANO": self.account_number,
            "ACNT_PRDT_CD": self.account_product_code,
            "KRX_FWDG_ORD_ORGNO": "",
            "ORGN_ODNO": order_id,
            "ORD_DVSN": "00",
            "RVSE_CNCL_DVSN_CD": "02",  # 02: 취소
            "ORD_QTY": str(quantity),
            "ORD_UNPR": "0",
            "PDNO": symbol,
            "QTY_ALL_ORD_YN": "N"
        }

        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id
        }

        result = self._make_request("POST", url, headers, json_data=data)

        try:
            output = result.get("output", {})
            logger.info(f"주문 취소 완료: {symbol}, 주문번호: {order_id}, 취소수량: {quantity}")
            return output
        except Exception as e:
            logger.error(f"주문 취소 응답 파싱 오류: {e}, Response: {result}")
            raise APIError("주문 취소 응답 파싱 실패", response_body=str(result))

    def get_daily_price_history(self, symbol: str, start_date: str, end_date: str) -> List[StockPrice]:
        """일봉 데이터 조회

        Args:
            symbol: 종목 코드
            start_date: 시작일 (YYYYMMDD)
            end_date: 종료일 (YYYYMMDD)

        Returns:
            일봉 데이터 리스트 (StockPrice)
        """
        self._ensure_token()

        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        tr_id = "FHKST03010100"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0"
        }

        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id
        }

        try:
            result = self._make_request("GET", url, headers, params=params)

            prices = []
            for item in result.get("output2", []):
                try:
                    prices.append(StockPrice(
                        symbol=symbol,
                        datetime=datetime.strptime(item["stck_bsop_date"], "%Y%m%d"),
                        open=float(item.get("stck_oprc", 0)),
                        high=float(item.get("stck_hgpr", 0)),
                        low=float(item.get("stck_lwpr", 0)),
                        close=float(item.get("stck_clpr", 0)),
                        volume=int(item.get("acml_vol", 0))
                    ))
                except (KeyError, ValueError) as e:
                    logger.warning(f"일봉 항목 파싱 오류: {e}, item: {item}")

            return prices

        except Exception as e:
            logger.error(f"일봉 데이터 조회 실패: {e}")
            return []

    def get_balance(self) -> dict:
        """AutoTrader 호환용 잔고 조회 (Dict 반환)"""
        account = self.get_account_balance()
        
        stocks = []
        total_stock_value = 0
        
        for p in account.positions:
            val = p.current_price * p.quantity
            total_stock_value += val
            stocks.append({
                'symbol': p.symbol,
                'name': p.symbol, # 이름 정보 부재
                'quantity': p.quantity,
                'current_price': p.current_price,
                'avg_price': p.avg_price,
                'exchange': p.exchange,
                'purchase_amt': p.avg_price * p.quantity,
                'eval_amt': val,
                'eval_profit': val - (p.avg_price * p.quantity)
            })
            
        total_asset = int(account.cash + total_stock_value)
        
        return {
            'total_asset': total_asset,
            'deposit': int(account.cash),
            'stocks': stocks
        }
