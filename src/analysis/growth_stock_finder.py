"""하이브리드 성장 가능성 주 탐색기

1단계: Yahoo Finance (yfinance) - 재무 데이터 기반 스크리닝
2단계: Tavily API - 웹 검색으로 최신 뉴스/트렌드 분석

사용법:
    finder = HybridGrowthStockFinder(tavily_api_key="your_api_key")
    results = finder.search_growth_stocks(market="KR")
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

# yfinance import
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

# Tavily API import (requests로 직접 호출)
import requests

logger = logging.getLogger(__name__)


@dataclass
class GrowthStock:
    """성장 가능성 종목 정보"""
    symbol: str                   # 종목 코드
    name: str                     # 종목명
    sector: str                   # 업종
    growth_score: float           # 성장 점수 (1-10)
    financial_health: str         # 재무 건전성 (Excellent, Good, Fair, Poor)
    reason: str                   # 추천 사유
    market_cap: str               # 시가총액 구분
    revenue_growth: Optional[float] = None  # 매출 성장률 (%)
    profit_margin: Optional[float] = None   # 영업이익률 (%)
    debt_to_equity: Optional[float] = None  # 부채비율 (%)
    current_ratio: Optional[float] = None   # 유동비율
    pe_ratio: Optional[float] = None        # PER
    news_summary: str = ""                  # 최신 뉴스 요약 (Tavily)
    news_sentiment: str = ""                # 뉴스 감성 (Positive/Neutral/Negative)


class HybridGrowthStockFinder:
    """하이브리드 성장주 탐색기
    
    1단계: yfinance로 재무 데이터 스크리닝
    2단계: Tavily로 웹 검색 보완
    """
    
    # 한국 중소형 성장주 후보 (코스닥 중심)
    KR_CANDIDATE_SYMBOLS = [
        # AI/반도체
        "439090.KQ",  # 하나마이크론
        "317330.KQ",  # 덕산테코피아
        "036930.KQ",  # 주성엔지니어링
        "357780.KQ",  # 솔브레인
        "240810.KQ",  # 원익IPS
        # 2차전지
        "247540.KQ",  # 에코프로비엠
        "112610.KS",  # 씨에스윈드 (코스피 상장)
        "373220.KQ",  # LG에너지솔루션 (대형이지만 참고)
        # 로봇/자동화
        "090460.KQ",  # 비에이치
        "058610.KQ",  # 에스피지
        # 바이오
        "950140.KQ",  # 잉글우드랩
        "145020.KQ",  # 휴젤
        "196170.KQ",  # 알테오젠
        # 전력기기
        "298050.KS",  # 효성첨단소재
        "267260.KS",  # HD현대일렉트릭
    ]

    # [이슈 #1] 한국 종목별 섹터 매핑 (yfinance가 sector를 반환하지 않는 경우 fallback)
    KR_SECTOR_MAP = {
        "439090.KQ": "반도체",
        "317330.KQ": "반도체",
        "036930.KQ": "반도체장비",
        "357780.KQ": "반도체소재",
        "240810.KQ": "반도체장비",
        "247540.KQ": "2차전지",
        "112610.KS": "풍력에너지",  # 씨에스윈드 (코스피)
        "373220.KQ": "2차전지",
        "090460.KQ": "전자부품",
        "058610.KQ": "로봇/자동화",
        "950140.KQ": "바이오",
        "145020.KQ": "바이오",
        "196170.KQ": "바이오",
        "298050.KS": "첨단소재",
        "267260.KS": "전력기기",
    }

    # [이슈 #2] 한국 종목별 한국어 이름 매핑 (yfinance shortName이 코드/영문일 때 fallback)
    KR_NAME_MAP = {
        "439090.KQ": "하나마이크론",
        "317330.KQ": "덕산테코피아",
        "036930.KQ": "주성엔지니어링",
        "357780.KQ": "솔브레인",
        "240810.KQ": "원익IPS",
        "247540.KQ": "에코프로비엠",
        "112610.KS": "씨에스윈드",  # 코스피 상장
        "373220.KQ": "LG에너지솔루션",
        "090460.KQ": "비에이치",
        "058610.KQ": "에스피지",
        "950140.KQ": "잉글우드랩",
        "145020.KQ": "휴젤",
        "196170.KQ": "알테오젠",
        "298050.KS": "효성첨단소재",
        "267260.KS": "HD현대일렉트릭",
    }
    
    # 미국 중소형 성장주 후보
    US_CANDIDATE_SYMBOLS = [
        # AI/반도체
        "SMCI",       # Super Micro Computer
        "AEHR",       # Aehr Test Systems
        "CEVA",       # CEVA Inc
        "POWI",       # Power Integrations
        # 우주항공
        "ASTS",       # AST SpaceMobile
        "RKLB",       # Rocket Lab
        "SPCE",       # Virgin Galactic
        # 자율주행/EV
        "LAZR",       # Luminar Technologies
        "RIVN",       # Rivian
        # 양자컴퓨팅/AI
        "IONQ",       # IonQ
        "AI",         # C3.ai
        "PLTR",       # Palantir
        # 클라우드/SaaS
        "NET",        # Cloudflare
        "DDOG",       # Datadog
        "CRWD",       # CrowdStrike
    ]
    
    # 재무 스크리닝 기준
    SCREENING_CRITERIA = {
        "min_revenue_growth": 10,      # 최소 매출 성장률 10%
        "max_debt_to_equity": 150,     # 최대 부채비율 150%
        "min_current_ratio": 1.0,      # 최소 유동비율 1.0
        "max_market_cap_billions": 50, # 최대 시가총액 500억 달러 (중소형)
    }
    
    TAVILY_API_URL = "https://api.tavily.com/search"
    
    def __init__(self, tavily_api_key: str = None):
        """초기화
        
        Args:
            tavily_api_key: Tavily API 키 (없으면 환경변수 TAVILY_API_KEY 사용)
        """
        self.tavily_api_key = tavily_api_key or os.getenv("TAVILY_API_KEY")
        self.last_update = None
        self.cached_results: List[GrowthStock] = []
        
        if not YFINANCE_AVAILABLE:
            logger.warning("yfinance 패키지가 설치되지 않았습니다. pip install yfinance")
    
    def search_growth_stocks(self, market: str = "KR", top_n: int = 5) -> List[GrowthStock]:
        """성장 가능성 주 검색 (하이브리드)
        
        Args:
            market: 시장 구분 (KR/US)
            top_n: 반환할 종목 수
            
        Returns:
            Top N 성장 가능성 종목 리스트
        """
        self.last_update = datetime.now()
        
        # 1단계: yfinance로 재무 데이터 스크리닝
        candidates = self.KR_CANDIDATE_SYMBOLS if market == "KR" else self.US_CANDIDATE_SYMBOLS
        screened_stocks = self._screen_with_yfinance(candidates)
        
        # 2단계: Tavily로 웹 검색 보완 (상위 종목만)
        if self.tavily_api_key and screened_stocks:
            screened_stocks = self._enrich_with_tavily(screened_stocks[:top_n], market)
        
        # 성장 점수 기준 정렬
        screened_stocks.sort(key=lambda x: x.growth_score, reverse=True)
        self.cached_results = screened_stocks[:top_n]
        
        return self.cached_results
    
    def _screen_with_yfinance(self, symbols: List[str]) -> List[GrowthStock]:
        """yfinance로 재무 데이터 기반 스크리닝"""
        results = []
        
        if not YFINANCE_AVAILABLE:
            logger.warning("yfinance 사용 불가 - 기본 데이터 반환")
            return self._get_fallback_data(symbols)
        
        # 한국 종목 여부 판별 (시가총액 단위 처리에 사용)
        is_kr_market = any(s.endswith('.KQ') or s.endswith('.KS') for s in symbols)

        for symbol in symbols:
            try:
                stock = yf.Ticker(symbol)
                info = stock.info

                # info가 없거나 비어있으면 건너뜀
                if not info:
                    continue

                # 현재 종목이 한국 종목인지 판별
                is_kr = symbol.endswith('.KQ') or symbol.endswith('.KS')

                # ── [이슈 #1] 재무 지표 추출 ──────────────────────────────────────
                revenue_growth = info.get('revenueGrowth', 0) * 100 if info.get('revenueGrowth') else None
                profit_margin = info.get('profitMargins', 0) * 100 if info.get('profitMargins') else None
                debt_to_equity = info.get('debtToEquity', None)
                current_ratio = info.get('currentRatio', None)
                pe_ratio = info.get('trailingPE', None)
                market_cap = info.get('marketCap', 0)

                # [이슈 #1 최종 수정] 한국 종목은 KR_SECTOR_MAP을 항상 우선 사용
                # yfinance가 영문 섹터(Healthcare, Technology 등)를 반환해도 무시하고 한국어로 덮어씀
                if is_kr:
                    sector = self.KR_SECTOR_MAP.get(symbol, info.get('sector', 'Unknown'))
                else:
                    # 미국 종목은 yfinance 값 사용, 없으면 Unknown
                    sector = info.get('sector', None) or 'Unknown'

                # [이슈 #1 수정] financials를 한 번만 가져와서 재사용 (두 번 호출 방지)
                financials_cache = None
                try:
                    financials_cache = stock.financials
                except Exception:
                    pass

                # revenue_growth fallback: financials 테이블에서 직접 계산
                if revenue_growth is None and financials_cache is not None and not financials_cache.empty:
                    try:
                        if 'Total Revenue' in financials_cache.index:
                            revenues = financials_cache.loc['Total Revenue'].dropna()
                            if len(revenues) >= 2:
                                r0, r1 = float(revenues.iloc[0]), float(revenues.iloc[1])
                                if r1 != 0:
                                    revenue_growth = ((r0 - r1) / abs(r1)) * 100
                    except Exception as fe:
                        logger.debug(f"{symbol} revenue_growth fallback 실패: {fe}")

                # profit_margin fallback: financials 테이블에서 직접 계산
                if profit_margin is None and financials_cache is not None and not financials_cache.empty:
                    try:
                        revenue_key = 'Total Revenue'
                        profit_key = 'Operating Income'
                        if revenue_key in financials_cache.index and profit_key in financials_cache.index:
                            rev_series = financials_cache.loc[revenue_key].dropna()
                            profit_series = financials_cache.loc[profit_key].dropna()
                            if len(rev_series) >= 1 and len(profit_series) >= 1:
                                rev = float(rev_series.iloc[0])
                                profit = float(profit_series.iloc[0])
                                if rev > 0:
                                    profit_margin = (profit / rev) * 100
                    except Exception as fe:
                        logger.debug(f"{symbol} profit_margin fallback 실패: {fe}")

                # ── [이슈 #2 최종 수정] 종목명 처리 ────────────────────────────────
                raw_name = info.get('shortName', '') or info.get('longName', '')
                if is_kr:
                    # 한국 종목은 KR_NAME_MAP을 항상 우선 사용
                    # yfinance가 영문 이름(Hugel, Alteogen 등)을 반환해도 한국어로 덮어씀
                    name = self.KR_NAME_MAP.get(symbol, raw_name or symbol)
                else:
                    # 미국 종목: yfinance 이름 사용, 코드 형태이면 원본 symbol 사용
                    if not raw_name or raw_name == symbol or len(raw_name) < 2:
                        name = symbol
                    elif ',' in raw_name or raw_name.replace('.', '').replace(' ', '').isdigit():
                        name = raw_name  # 코드 패턴이어도 미국 종목은 KR_NAME_MAP 적용 안 함
                    else:
                        name = raw_name

                # ── 종목 유효성 검사 ───────────────────────────────────────────────
                # [이슈 #2 버그 수정] shortName/longName 중 하나라도 있거나
                # KR_NAME_MAP에 있으면 통과 (미국 longName-only 종목 누락 방지)
                has_name = bool(info.get('shortName') or info.get('longName'))
                if not has_name and symbol not in self.KR_NAME_MAP:
                    logger.debug(f"종목 {symbol}: 이름 정보 없음, 건너뜀")
                    continue

                # [이슈 #1 버그 수정] 한국 종목은 시가총액 단위가 원화(KRW)이므로
                # 달러 기준 상한선 비교를 건너뜀 — 대신 is_kr 플래그를 전달
                if not self._passes_screening(
                    revenue_growth, debt_to_equity, current_ratio, market_cap, is_kr=is_kr
                ):
                    continue

                # 성장 점수 계산
                growth_score = self._calculate_growth_score(
                    revenue_growth, profit_margin, debt_to_equity, current_ratio, pe_ratio
                )

                # 재무 건전성 평가
                financial_health = self._evaluate_financial_health(debt_to_equity, current_ratio, profit_margin)

                # 시가총액 구분
                market_cap_label = self._categorize_market_cap(market_cap)

                results.append(GrowthStock(
                    symbol=symbol.replace(".KQ", "").replace(".KS", ""),
                    name=name,
                    sector=sector,
                    growth_score=growth_score,
                    financial_health=financial_health,
                    reason=f"매출 성장률 {revenue_growth:.1f}%" if revenue_growth else "성장 잠재력 보유",
                    market_cap=market_cap_label,
                    revenue_growth=revenue_growth,
                    profit_margin=profit_margin,
                    debt_to_equity=debt_to_equity,
                    current_ratio=current_ratio,
                    pe_ratio=pe_ratio,
                ))

            except Exception as e:
                logger.debug(f"종목 {symbol} 분석 실패: {e}")
                continue
        
        return results
    
    def _passes_screening(
        self, revenue_growth, debt_to_equity, current_ratio, market_cap, is_kr: bool = False
    ) -> bool:
        """스크리닝 조건 통과 여부

        Args:
            is_kr: 한국 종목 여부. True이면 시가총액 달러 상한 비교를 건너뜀.
                   (yfinance가 한국 종목의 marketCap을 원화로 반환하므로 달러 기준 비교 불가)
        """
        criteria = self.SCREENING_CRITERIA

        # 매출 성장률 체크 (값이 있는 경우에만)
        if revenue_growth is not None and revenue_growth < criteria["min_revenue_growth"]:
            return False

        # 부채비율 체크 (값이 있는 경우에만)
        if debt_to_equity is not None and debt_to_equity > criteria["max_debt_to_equity"]:
            return False

        # 유동비율 체크 (값이 있는 경우에만)
        if current_ratio is not None and current_ratio < criteria["min_current_ratio"]:
            return False

        # 시가총액 체크: 한국 종목은 yfinance가 원화(KRW)로 반환하므로 달러 기준 비교 불가
        # → 한국 종목은 시가총액 상한 체크를 건너뜀
        if not is_kr:
            max_cap = criteria["max_market_cap_billions"] * 1e9  # 달러 기준 $50B
            if market_cap and market_cap > max_cap:
                return False

        return True
    
    def _calculate_growth_score(self, revenue_growth, profit_margin, debt_to_equity, current_ratio, pe_ratio) -> float:
        """성장 점수 계산 (1-10)"""
        score = 5.0  # 기본 점수
        
        # 매출 성장률 (최대 +2점)
        if revenue_growth:
            if revenue_growth > 30:
                score += 2.0
            elif revenue_growth > 20:
                score += 1.5
            elif revenue_growth > 10:
                score += 1.0
        
        # 이익률 (최대 +1.5점)
        if profit_margin:
            if profit_margin > 15:
                score += 1.5
            elif profit_margin > 10:
                score += 1.0
            elif profit_margin > 5:
                score += 0.5
        
        # 부채비율 (최대 +1점)
        if debt_to_equity:
            if debt_to_equity < 50:
                score += 1.0
            elif debt_to_equity < 100:
                score += 0.5
        
        # 유동비율 (최대 +0.5점)
        if current_ratio:
            if current_ratio > 2:
                score += 0.5
            elif current_ratio > 1.5:
                score += 0.25
        
        return min(10.0, max(1.0, score))
    
    def _evaluate_financial_health(self, debt_to_equity, current_ratio, profit_margin) -> str:
        """재무 건전성 평가"""
        score = 0
        
        if debt_to_equity is not None:
            if debt_to_equity < 50:
                score += 2
            elif debt_to_equity < 100:
                score += 1
        
        if current_ratio is not None:
            if current_ratio > 2:
                score += 2
            elif current_ratio > 1.5:
                score += 1
        
        if profit_margin is not None:
            if profit_margin > 10:
                score += 2
            elif profit_margin > 5:
                score += 1
        
        if score >= 5:
            return "Excellent"
        elif score >= 3:
            return "Good"
        elif score >= 1:
            return "Fair"
        else:
            return "Poor"
    
    def _categorize_market_cap(self, market_cap: float) -> str:
        """시가총액 분류"""
        if not market_cap:
            return "Unknown"
        
        cap_billions = market_cap / 1e9
        
        if cap_billions < 1:
            return "소형주 (<$1B)"
        elif cap_billions < 10:
            return "중형주 ($1-10B)"
        elif cap_billions < 50:
            return "중대형주 ($10-50B)"
        else:
            return "대형주 (>$50B)"
    
    def _enrich_with_tavily(self, stocks: List[GrowthStock], market: str) -> List[GrowthStock]:
        """Tavily API로 웹 검색 보완"""
        if not self.tavily_api_key:
            logger.warning("Tavily API 키가 설정되지 않았습니다.")
            return stocks
        
        market_name = "한국" if market == "KR" else "미국"
        
        for stock in stocks:
            try:
                # 종목별 뉴스 검색
                query = f"{stock.name} {stock.sector} 성장 전망 2026"
                
                response = requests.post(
                    self.TAVILY_API_URL,
                    json={
                        "api_key": self.tavily_api_key,
                        "query": query,
                        "search_depth": "basic",
                        "max_results": 3,
                        "include_answer": True,
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # AI 요약 답변 추출
                    answer = data.get("answer", "")
                    if answer:
                        stock.news_summary = answer[:200] + "..." if len(answer) > 200 else answer
                    
                    # 감성 분석 (간단한 키워드 기반)
                    stock.news_sentiment = self._analyze_sentiment(answer)
                    
                    # 긍정적 뉴스면 점수 보정
                    if stock.news_sentiment == "Positive":
                        stock.growth_score = min(10.0, stock.growth_score + 0.5)
                        stock.reason += " | 최신 뉴스 긍정적"
                    
            except Exception as e:
                logger.debug(f"Tavily 검색 실패 ({stock.name}): {e}")
                continue
        
        return stocks
    
    def _analyze_sentiment(self, text: str) -> str:
        """간단한 감성 분석"""
        if not text:
            return "Neutral"
        
        text_lower = text.lower()
        
        positive_keywords = ["성장", "상승", "호재", "긍정", "기대", "확대", "증가", "수혜", "growth", "positive", "bullish"]
        negative_keywords = ["하락", "부진", "악재", "우려", "감소", "축소", "리스크", "decline", "negative", "bearish"]
        
        pos_count = sum(1 for kw in positive_keywords if kw in text_lower)
        neg_count = sum(1 for kw in negative_keywords if kw in text_lower)
        
        if pos_count > neg_count + 1:
            return "Positive"
        elif neg_count > pos_count + 1:
            return "Negative"
        else:
            return "Neutral"
    
    def _get_fallback_data(self, symbols: List[str]) -> List[GrowthStock]:
        """yfinance 사용 불가 시 빈 리스트 반환"""
        import logging as _logging
        _logging.getLogger(__name__).warning("성장주 분석 데이터 조회 실패. 데이터 없음.")
        return []
    
    def get_sector_analysis(self) -> Dict[str, Any]:
        """섹터별 분석 요약"""
        if not self.cached_results:
            return {}
        
        sector_counts = {}
        for stock in self.cached_results:
            sector = stock.sector
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
        
        return {
            "sectors": sector_counts,
            "total_stocks": len(self.cached_results),
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "avg_growth_score": sum(s.growth_score for s in self.cached_results) / len(self.cached_results),
            "tavily_enabled": bool(self.tavily_api_key),
        }
    
    def to_dataframe_dict(self) -> List[Dict[str, Any]]:
        """DataFrame 변환용 딕셔너리 리스트 반환"""
        return [
            {
                "종목코드": s.symbol,
                "종목명": s.name,
                "섹터": s.sector,
                "성장점수": s.growth_score,
                "재무건전성": s.financial_health,
                "시가총액": s.market_cap,
                "매출성장률(%)": s.revenue_growth,
                "영업이익률(%)": s.profit_margin,
                "부채비율(%)": s.debt_to_equity,
                "유동비율": s.current_ratio,
                "PER": s.pe_ratio,
                "뉴스감성": s.news_sentiment,
                "추천사유": s.reason,
            }
            for s in self.cached_results
        ]


# 기존 호환성을 위한 alias
GrowthStockFinder = HybridGrowthStockFinder
