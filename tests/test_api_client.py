"""한국투자증권 API 클라이언트 테스트

TDD: API 클라이언트의 동작을 먼저 테스트로 정의합니다.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date


class TestKISAPIClient:
    """한국투자증권 API 클라이언트 테스트"""
    
    def test_client_initialization(self):
        """클라이언트 초기화 테스트"""
        from src.data.api_client import KISAPIClient
        
        client = KISAPIClient(
            app_key="test_app_key",
            app_secret="test_secret",
            account_number="12345678",
            account_product_code="01",
            is_mock=True
        )
        
        assert client.app_key == "test_app_key"
        assert client.is_mock is True
        assert client.account_number == "12345678"
    
    @patch('requests.post')
    def test_get_access_token(self, mock_post):
        """액세스 토큰 발급 테스트"""
        from src.data.api_client import KISAPIClient
        
        # Mock 응답 설정
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_token_12345",
            "token_type": "Bearer",
            "expires_in": 86400
        }
        mock_post.return_value = mock_response
        
        client = KISAPIClient(
            app_key="test_key",
            app_secret="test_secret",
            account_number="12345678",
            account_product_code="01",
            is_mock=True
        )
        
        token = client.get_access_token()
        
        assert token == "test_token_12345"
        assert mock_post.called
    
    @patch('requests.get')
    def test_get_current_price(self, mock_get):
        """현재가 조회 테스트"""
        from src.data.api_client import KISAPIClient
        
        # Mock 응답 설정
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {
                "stck_prpr": "75800",  # 현재가
                "prdy_vrss": "500",     # 전일대비
                "prdy_ctrt": "0.66"     # 전일대비율
            }
        }
        mock_get.return_value = mock_response
        
        client = KISAPIClient(
            app_key="test_key",
            app_secret="test_secret",
            account_number="12345678",
            account_product_code="01",
            is_mock=True
        )
        client.access_token = "test_token"
        
        price = client.get_current_price("005930")
        
        assert price == 75800
        assert mock_get.called
    
    @patch('requests.get')
    def test_get_daily_price_history(self, mock_get):
        """일봉 데이터 조회 테스트"""
        from src.data.api_client import KISAPIClient
        from src.data.models import StockPrice
        
        # Mock 응답 설정
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output2": [
                {
                    "stck_bsop_date": "20240102",
                    "stck_oprc": "75000",
                    "stck_hgpr": "76000",
                    "stck_lwpr": "74500",
                    "stck_clpr": "75800",
                    "acml_vol": "10000000"
                },
                {
                    "stck_bsop_date": "20240103",
                    "stck_oprc": "75800",
                    "stck_hgpr": "77000",
                    "stck_lwpr": "75500",
                    "stck_clpr": "76500",
                    "acml_vol": "12000000"
                }
            ]
        }
        mock_get.return_value = mock_response
        
        client = KISAPIClient(
            app_key="test_key",
            app_secret="test_secret",
            account_number="12345678",
            account_product_code="01",
            is_mock=True
        )
        client.access_token = "test_token"
        
        prices = client.get_daily_price_history(
            symbol="005930",
            start_date="20240102",
            end_date="20240103"
        )
        
        # 검증
        assert len(prices) == 2
        assert isinstance(prices[0], StockPrice)
        assert prices[0].symbol == "005930"
        assert prices[0].close == 75800
        assert prices[1].close == 76500
    
    @patch('requests.post')
    def test_place_market_order(self, mock_post):
        """시장가 주문 테스트"""
        from src.data.api_client import KISAPIClient
        from src.data.models import Order, OrderType, OrderSide
        
        # Mock 응답 설정
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "rt_cd": "0",
            "msg1": "주문이 완료되었습니다",
            "output": {
                "KRX_FWDG_ORD_ORGNO": "12345",
                "ODNO": "0000123456",
                "ORD_TMD": "153000"
            }
        }
        mock_post.return_value = mock_response
        
        client = KISAPIClient(
            app_key="test_key",
            app_secret="test_secret",
            account_number="12345678",
            account_product_code="01",
            is_mock=True
        )
        client.access_token = "test_token"
        
        order = Order(
            symbol="005930",
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            quantity=10,
            price=None,
            created_at=datetime.now()
        )
        
        order_id = client.place_order(order)
        
        assert order_id == "0000123456"
        assert mock_post.called
    
    @patch('requests.get')
    def test_get_account_balance(self, mock_get):
        """계좌 잔고 조회 테스트"""
        from src.data.api_client import KISAPIClient
        from src.data.models import Account
        
        # Mock 응답 설정
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output2": [
                {
                    "dnca_tot_amt": "10000000",  # 예수금
                    "nxdy_excc_amt": "5000000"   # 인출 가능 금액
                }
            ],
            "output1": [
                {
                    "pdno": "005930",
                    "hldg_qty": "100",
                    "pchs_avg_pric": "75000",
                    "prpr": "76000"
                }
            ]
        }
        mock_get.return_value = mock_response
        
        client = KISAPIClient(
            app_key="test_key",
            app_secret="test_secret",
            account_number="12345678",
            account_product_code="01",
            is_mock=True
        )
        client.access_token = "test_token"
        
        account = client.get_account_balance()
        
        assert isinstance(account, Account)
        assert account.cash == 10000000
        assert len(account.positions) == 1
        assert account.positions[0].symbol == "005930"
        assert account.positions[0].quantity == 100


class TestAPIErrorHandling:
    """API 에러 처리 테스트"""
    
    @patch('requests.get')
    def test_handle_api_error(self, mock_get):
        """API 에러 처리 테스트"""
        from src.data.api_client import KISAPIClient, APIError
        
        # 에러 응답 Mock
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "rt_cd": "1",
            "msg1": "잘못된 요청입니다"
        }
        mock_get.return_value = mock_response
        
        client = KISAPIClient(
            app_key="test_key",
            app_secret="test_secret",
            account_number="12345678",
            account_product_code="01",
            is_mock=True
        )
        client.access_token = "test_token"
        
        # API 에러 발생 확인
        with pytest.raises(APIError) as exc_info:
            client.get_current_price("INVALID_SYMBOL")
        
        assert "잘못된 요청" in str(exc_info.value)
    
    @patch('requests.get')
    def test_retry_on_network_error(self, mock_get):
        """네트워크 에러 시 재시도 테스트"""
        from src.data.api_client import KISAPIClient
        import requests
        
        # 첫 번째 호출은 실패, 두 번째 호출은 성공
        mock_get.side_effect = [
            requests.exceptions.ConnectionError("Connection failed"),
            Mock(
                status_code=200,
                json=lambda: {"output": {"stck_prpr": "75800"}}
            )
        ]
        
        client = KISAPIClient(
            app_key="test_key",
            app_secret="test_secret",
            account_number="12345678",
            account_product_code="01",
            is_mock=True,
            max_retries=3
        )
        client.access_token = "test_token"
        
        # 재시도 후 성공
        price = client.get_current_price("005930")
        assert price == 75800
        assert mock_get.call_count == 2  # 1번 실패 + 1번 성공
