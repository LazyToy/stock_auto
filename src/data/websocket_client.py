"""WebSocket Client (비동기 실시간 시세 처리)
"""

import asyncio
import websockets
import json
import logging
from typing import Callable, Optional
from src.config import Config
from src.utils.notification import send_notification

logger = logging.getLogger(__name__)

class KISWebSocketClient:
    """한국투자증권 실시간 웹소켓 클라이언트"""
    
    def __init__(self, market: str = "KR", event_callback: Callable[[dict], None] = None):
        """초기화
        
        Args:
            market: "KR" (국내) 또는 "US" (해외)
            event_callback: 실시간 데이터 수신 시 호출될 콜백 함수
        """
        self.market = market
        self.is_connected = False

        # KIS 공식 WebSocket URL: 실전 21000포트, 모의 31000포트
        if Config.IS_MOCK:
            self.ws_url = "wss://ops.koreainvestment.com:31000"
        else:
            self.ws_url = "wss://ops.koreainvestment.com:21000"

        self.approval_key = None # 웹소켓 접속키 (별도 발급 필요)
        self.running = False
        self.callback = event_callback
        self.subscribed_symbols = set()
        
    async def connect(self):
        """웹소켓 연결 및 구독 관리"""
        self.running = True
        
        # 1. 접속키 발급 (여기서는 동기로 가정하거나, API Client 통해 받아야 함)
        # 웹소켓 접속키는 일반 접속 토큰과 다름
        # 편의상 Config나 API Client에서 가져온다고 가정
        # self.approval_key = ... 
        
        logger.info(f"[{self.market}] WebSocket 연결 시도: {self.ws_url}")
        
        try:
            async with websockets.connect(self.ws_url, ping_interval=60) as websocket:
                self.is_connected = True
                logger.info("WebSocket 연결 성공")
                send_notification(f"🔌 [{self.market}] 실시간 시세 서버 연결됨")
                
                # 구독 요청
                if self.subscribed_symbols:
                    await self._subscribe_symbols(websocket, list(self.subscribed_symbols))
                
                # 메시지 루프
                async for message in websocket:
                    if not self.running:
                        break
                        
                    data = json.loads(message)
                    
                    # 핑퐁 (PING/PONG) 처리
                    if data.get('header', {}).get('tr_id') == 'PINGPONG':
                        await websocket.pong(data)
                        continue
                        
                    # 데이터 처리
                    if self.callback:
                        # 별도 콜백 처리 (비동기 Task로 실행하여 루프 차단 방지)
                        asyncio.create_task(self._process_data(data))
                        
        except Exception as e:
            logger.error(f"WebSocket 연결 끊김: {e}")
            self.is_connected = False
            send_notification(f"⚠️ [{self.market}] 실시간 시세 서버 연결 끊김: {e}")
            
            # 재연결 로직 (잠시 대기 후 재시도)
            if self.running:
                await asyncio.sleep(5)
                # 재귀 호출로 재연결 (단, 스택 오버플로우 주의 - 루프로 변경 권장)
                # 여기서는 간단히 while True 패턴을 상위에서 사용한다고 가정

    async def _process_data(self, data):
        """데이터 처리 (비동기 래퍼)"""
        try:
            # 콜백은 동기 함수일 수도 있으므로, 필요시 run_in_executor 사용
            if asyncio.iscoroutinefunction(self.callback):
                await self.callback(data)
            else:
                self.callback(data)
        except Exception as e:
            logger.error(f"데이터 처리 오류: {e}")

    async def _subscribe_symbols(self, websocket, symbols):
        """종목 구독 요청 전송"""
        for symbol in symbols:
            subscribe_msg = {
                "header": {
                    "approval_key": self.approval_key,
                    "custtype": "P",
                    "tr_type": "1",
                    "content-type": "utf-8"
                },
                "body": {
                    "input": {
                        "tr_id": "H0STCNT0",
                        "tr_key": symbol
                    }
                }
            }
            await websocket.send(json.dumps(subscribe_msg))
            logger.info(f"[{self.market}] 종목 구독 요청: {symbol}")

    def start(self):
        """별도 스레드에서 비동기 루프 실행"""
        import threading
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()
        
    def _run_loop(self):
        """Event Loop 실행"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.connect())

