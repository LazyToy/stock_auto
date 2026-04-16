from typing import List, Dict, Any
from langchain.tools import tool
from src.data.api_client import KISAPIClient
from src.utils.database import get_db

@tool
def get_portfolio_summary() -> str:
    """
    현재 포트폴리오 상태(총 자산, 예수금, 보유 종목 및 수익률)를 조회합니다.
    Returns:
        str: 포트폴리오 요약 텍스트
    """
    try:
        client = KISAPIClient()
        balance = client.get_balance()
        
        total_asset = balance.get('total_asset', 0)
        deposit = balance.get('deposit', 0)
        stocks = balance.get('stocks', [])
        
        summary = f"💰 **포트폴리오 요약**\n"
        summary += f"- 총 자산: {total_asset:,}원\n"
        summary += f"- 예수금: {deposit:,}원\n"
        summary += f"- 보유 종목 수: {len(stocks)}개\n\n"
        
        if stocks:
            summary += "**보유 종목 목록:**\n"
            for s in stocks:
                name = s.get('name', s['symbol'])
                qty = int(s['quantity'])
                price = float(s['current_price'])
                avg = float(s['avg_price'])
                profit = (price - avg) / avg * 100 if avg > 0 else 0
                
                summary += f"- {name} ({s['symbol']}): {qty}주, 수익률 {profit:.2f}%\n"
        else:
            summary += "보유 중인 종목이 없습니다."
            
        return summary
    except Exception as e:
        return f"포트폴리오 조회 중 오류 발생: {e}"

@tool
def get_recent_trades(limit: int = 5) -> str:
    """
    최근 거래 내역을 조회합니다.
    Args:
        limit (int): 조회할 거래 건수 (기본값: 5)
    Returns:
        str: 최근 거래 내역 텍스트
    """
    try:
        db = get_db()
        trades = db.get_trades(limit=limit)
        
        if not trades:
            return "최근 거래 내역이 없습니다."
            
        summary = f"📜 **최근 거래 내역 ({len(trades)}건)**\n"
        for t in trades:
            # DB 레코드는 딕셔너리 형태라고 가정
            time = t.get('timestamp', 'N/A')
            symbol = t.get('symbol', 'N/A')
            side = t.get('side', 'N/A')
            qty = t.get('quantity', 0)
            price = t.get('price', 0)
            reason = t.get('reason', '')
            
            summary += f"- [{time}] {side} {symbol} {qty}주 @ {price:,.0f}원"
            if reason:
                summary += f" (사유: {reason})"
            summary += "\n"
            
        return summary
    except Exception as e:
        return f"거래 내역 조회 중 오류 발생: {e}"

@tool
def explain_trade_decision(symbol: str) -> str:
    """
    특정 종목에 대한 최근 매매 결정(매수/매도)의 이유를 설명합니다.
    Args:
        symbol (str): 종목 코드 (예: 005930)
    Returns:
        str: 매매 사유 설명
    """
    try:
        db = get_db()
        # 해당 종목의 가장 최근 거래 조회 (limit=1)
        trades = db.get_trades(symbol=symbol, limit=1)
        
        if not trades:
            return f"{symbol} 종목에 대한 최근 거래 기록이 없습니다."
            
        t = trades[0]
        side = t.get('side', 'N/A')
        time = t.get('timestamp', 'N/A')
        reason = t.get('reason', '알 수 없음')
        
        return f"🧐 **{symbol} {side} 결정 이유 ({time})**\n- {reason}"
        
    except Exception as e:
        return f"매매 사유 조회 중 오류 발생: {e}"
