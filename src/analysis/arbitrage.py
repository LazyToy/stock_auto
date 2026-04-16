"""크로스 마켓 차익거래 탐지 모듈

KR/US 시장 간 가격 차이를 분석하여 차익거래 기회를 발견합니다.

주요 기능:
1. ADR vs 원주 가격 괴리 분석
2. 환율 반영 실질 가격 비교
3. ADR 비율 계산
4. 차익거래 기회 알림
"""

import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import yfinance as yf

logger = logging.getLogger("CrossMarketArbitrage")


@dataclass
class ADRMapping:
    """ADR 매핑 정보"""
    kr_symbol: str      # 한국 종목코드 (예: 005930)
    kr_name: str        # 한국 종목명 (예: 삼성전자)
    us_symbol: str      # 미국 ADR 코드 (예: SSNLF)
    us_name: str        # 미국 ADR 종목명
    adr_ratio: float    # ADR 비율 (ADR 1주 = 원주 N주)


# 주요 한국 기업 ADR 매핑
ADR_MAPPINGS = [
    ADRMapping("005930", "삼성전자", "SSNLF", "삼성전자 OTC", 1.0),
    ADRMapping("000660", "SK하이닉스", "HXSCF", "SK Hynix OTC", 1.0),
    ADRMapping("035420", "NAVER", "NAVRN", "Naver Corp", 1.0),
    ADRMapping("035720", "카카오", "KKPCY", "Kakao Corp", 1.0),
    ADRMapping("006400", "삼성SDI", "SSDIY", "Samsung SDI", 1.0),
    ADRMapping("051910", "LG화학", "LGCLF", "LG Chem", 1.0),
    ADRMapping("105560", "KB금융", "KB", "KB Financial Group ADR", 2.0),
    ADRMapping("055550", "신한지주", "SHG", "Shinhan Financial Group ADR", 2.0),
    ADRMapping("373220", "LG에너지솔루션", "LGESY", "LG Energy Solution", 0.5),
    ADRMapping("068270", "셀트리온", "CLTRF", "Celltrion OTC", 1.0),
]


@dataclass
class ArbitrageOpportunity:
    """차익거래 기회"""
    kr_symbol: str
    us_symbol: str
    kr_price: float            # 원화 가격
    us_price: float            # 달러 가격
    exchange_rate: float       # 환율 (원/달러)
    kr_price_usd: float        # 원주 달러 환산 가격
    premium_pct: float         # 프리미엄 비율 (%)
    direction: str             # "KR_OVERVALUED" or "US_OVERVALUED"
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def is_actionable(self) -> bool:
        """거래 가능한 수준의 괴리인지"""
        return abs(self.premium_pct) >= 2.0  # 2% 이상


class CrossMarketArbitrageDetector:
    """크로스 마켓 차익거래 탐지기"""
    
    def __init__(
        self, 
        exchange_rate: float = None,
        min_premium_pct: float = 2.0
    ):
        self.exchange_rate = exchange_rate or self._get_live_exchange_rate()
        self.min_premium_pct = min_premium_pct
        self.adr_mappings = {m.kr_symbol: m for m in ADR_MAPPINGS}
    
    def _get_live_exchange_rate(self) -> float:
        """실시간 환율 조회"""
        try:
            usdkrw = yf.Ticker("KRW=X")
            rate = usdkrw.info.get("regularMarketPrice") or usdkrw.info.get("previousClose")
            if rate:
                return 1 / rate  # 1 달러 = ? 원
            return 1300.0  # 기본값
        except Exception as e:
            logger.warning(f"환율 조회 실패: {e}, 기본값 1300 사용")
            return 1300.0
    
    def update_exchange_rate(self):
        """환율 업데이트"""
        self.exchange_rate = self._get_live_exchange_rate()
        logger.info(f"환율 업데이트: 1 USD = {self.exchange_rate:.2f} KRW")
    
    def get_kr_price(self, symbol: str) -> Optional[float]:
        """한국 주식 가격 조회"""
        try:
            # yfinance 한국 종목: .KS (코스피) 또는 .KQ (코스닥)
            ticker = yf.Ticker(f"{symbol}.KS")
            info = ticker.info
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            
            if not price:
                # 코스닥 시도
                ticker = yf.Ticker(f"{symbol}.KQ")
                info = ticker.info
                price = info.get("regularMarketPrice") or info.get("currentPrice")
            
            return float(price) if price else None
        except Exception as e:
            logger.error(f"KR 가격 조회 실패 ({symbol}): {e}")
            return None
    
    def get_us_price(self, symbol: str) -> Optional[float]:
        """미국 ADR 가격 조회"""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            return float(price) if price else None
        except Exception as e:
            logger.error(f"US 가격 조회 실패 ({symbol}): {e}")
            return None
    
    def calculate_premium(
        self, 
        kr_symbol: str, 
        us_symbol: str = None,
        adr_ratio: float = 1.0
    ) -> Optional[ArbitrageOpportunity]:
        """
        프리미엄 계산
        
        Args:
            kr_symbol: 한국 종목코드
            us_symbol: 미국 ADR 코드 (없으면 자동 매핑)
            adr_ratio: ADR 비율
            
        Returns:
            차익거래 기회 정보
        """
        # ADR 매핑 조회
        if kr_symbol in self.adr_mappings and not us_symbol:
            mapping = self.adr_mappings[kr_symbol]
            us_symbol = mapping.us_symbol
            adr_ratio = mapping.adr_ratio
        
        if not us_symbol:
            logger.warning(f"ADR 매핑 없음: {kr_symbol}")
            return None
        
        # 가격 조회
        kr_price = self.get_kr_price(kr_symbol)
        us_price = self.get_us_price(us_symbol)
        
        if not kr_price or not us_price:
            return None
        
        # ADR 비율 적용 후 달러 환산
        kr_price_adjusted = kr_price * adr_ratio
        kr_price_usd = kr_price_adjusted / self.exchange_rate
        
        # 프리미엄 계산: (US가격 - KR달러환산) / KR달러환산 * 100
        premium_pct = (us_price - kr_price_usd) / kr_price_usd * 100
        
        # 방향 결정
        if premium_pct > 0:
            direction = "US_OVERVALUED"  # 미국이 비쌈 -> 한국 매수 유리
        else:
            direction = "KR_OVERVALUED"  # 한국이 비쌈 -> 미국 매수 유리
        
        return ArbitrageOpportunity(
            kr_symbol=kr_symbol,
            us_symbol=us_symbol,
            kr_price=kr_price,
            us_price=us_price,
            exchange_rate=self.exchange_rate,
            kr_price_usd=kr_price_usd,
            premium_pct=premium_pct,
            direction=direction
        )
    
    def scan_all_opportunities(self) -> List[ArbitrageOpportunity]:
        """
        전체 ADR 스캔
        
        Returns:
            차익거래 기회 리스트 (프리미엄 절대값 순 정렬)
        """
        opportunities = []
        
        for kr_symbol, mapping in self.adr_mappings.items():
            try:
                opp = self.calculate_premium(
                    kr_symbol=kr_symbol,
                    us_symbol=mapping.us_symbol,
                    adr_ratio=mapping.adr_ratio
                )
                
                if opp:
                    opportunities.append(opp)
                    logger.info(
                        f"{mapping.kr_name} ({kr_symbol}): "
                        f"프리미엄 {opp.premium_pct:+.2f}% ({opp.direction})"
                    )
            except Exception as e:
                logger.error(f"스캔 실패 ({kr_symbol}): {e}")
        
        # 프리미엄 절대값 순 정렬
        opportunities.sort(key=lambda x: abs(x.premium_pct), reverse=True)
        
        return opportunities
    
    def get_actionable_opportunities(self) -> List[ArbitrageOpportunity]:
        """거래 가능한 차익거래 기회만 반환"""
        all_opps = self.scan_all_opportunities()
        return [opp for opp in all_opps if opp.is_actionable]
    
    def get_recommendation(self, opp: ArbitrageOpportunity) -> Dict:
        """
        차익거래 추천
        
        Args:
            opp: 차익거래 기회
            
        Returns:
            추천 정보
        """
        if opp.direction == "US_OVERVALUED":
            # 미국이 비쌈 -> 한국 매수 추천
            return {
                "action": "BUY_KR",
                "symbol": opp.kr_symbol,
                "reason": f"미국 ADR 대비 {abs(opp.premium_pct):.1f}% 저평가",
                "expected_return": abs(opp.premium_pct)
            }
        else:
            # 한국이 비쌈 -> 미국 ADR 매수 추천 (해외 직구)
            return {
                "action": "BUY_US",
                "symbol": opp.us_symbol,
                "reason": f"한국 원주 대비 {abs(opp.premium_pct):.1f}% 저평가",
                "expected_return": abs(opp.premium_pct)
            }


# 전역 인스턴스
_global_detector: Optional[CrossMarketArbitrageDetector] = None


def get_arbitrage_detector() -> CrossMarketArbitrageDetector:
    """전역 차익거래 탐지기 인스턴스 반환"""
    global _global_detector
    if _global_detector is None:
        _global_detector = CrossMarketArbitrageDetector()
    return _global_detector
