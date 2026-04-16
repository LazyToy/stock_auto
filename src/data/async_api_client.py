"""
비동기 한국투자증권 API 클라이언트

aiohttp를 사용하여 비동기 방식으로 API 요청을 처리합니다.
대량의 종목 시세 조회 시 성능을 최적화합니다.
"""

import aiohttp
import asyncio
import logging
import json
import time
from typing import List, Dict, Any, Optional
from src.config import Config
from src.data.models import Order, OrderSide

logger = logging.getLogger(__name__)

class AsyncKISAPIClient:
    def __init__(self, app_key: str = None, app_secret: str = None, account_number: str = None):
        self.app_key = app_key or Config.KIS_APP_KEY
        self.app_secret = app_secret or Config.KIS_APP_SECRET
        self.account_number = account_number or Config.KIS_ACCOUNT_NUMBER
        self.base_url = "https://openapi.koreainvestment.com:9443"  # 실전
        if Config.TRADING_MODE == "mock":
            self.base_url = "https://openapivts.koreainvestment.com:29443"
            
        self.access_token = None
        self.token_expiry = 0
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        await self._ensure_token()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """세션 종료"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    async def _ensure_token(self):
        """액세스 토큰 확보 (비동기)"""
        if self.access_token and time.time() < self.token_expiry:
            return

        url = f"{self.base_url}/oauth2/tokenP"
        headers = {"content-type": "application/json"}
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }

        async with self.session.post(url, headers=headers, json=body) as resp:
            data = await resp.json()
            if "access_token" in data:
                self.access_token = data["access_token"]
                self.token_expiry = time.time() + data.get("expires_in", 3600) - 60
                logger.info("Access token refreshed (Async)")
            else:
                logger.error(f"Failed to refresh token: {data}")
                raise Exception("Token refresh failed")

    async def get_current_price(self, symbol: str) -> float:
        """현재가 조회 (비동기)"""
        if not self.session:
            raise RuntimeError("Session not initialized. Use 'async with' context manager.")
            
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = {
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "FHKST01010100"
        }
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": symbol
        }

        async with self.session.get(url, headers=headers, params=params) as resp:
            data = await resp.json()
            if data.get("rt_cd") == "0":
                # 한국 주식 현재가는 output.stck_prpr
                return float(data["output"]["stck_prpr"])
            else:
                logger.error(f"Failed to get price for {symbol}: {data.get('msg1')}")
                return 0.0

    async def fetch_prices_batch(self, symbols: List[str]) -> Dict[str, float]:
        """
        여러 종목의 현재가를 병렬로 조회
        """
        if not self.session or self.session.closed:
            # 세션이 없으면 생성 (호출자가 close() 책임)
            self.session = aiohttp.ClientSession()
            await self._ensure_token()
        
        # 이미 세션이 있으면 그대로 사용
        tasks = [self.get_current_price(sym) for sym in symbols]
        results = await asyncio.gather(*tasks)
        return dict(zip(symbols, results))
