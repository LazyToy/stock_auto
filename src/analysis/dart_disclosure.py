"""DART 공시 분석 모듈

DART Open API를 통해 실시간 공시를 수집하고 LLM으로 분석합니다.

DART API 키 발급:
1. https://opendart.fss.or.kr/ 접속
2. 회원가입 후 "인증키 신청"
3. 발급받은 키를 .env 파일에 DART_API_KEY=xxx 로 저장

지원하는 공시 유형:
- 유상증자/무상증자
- 합병/분할/영업양수도
- 최대주주 변경
- 대규모 계약 체결
- 특정 시설 투자
- 자기주식 취득/처분
- 임원 변경
"""

import os
import logging
import requests
from enum import Enum
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from src.config import Config

logger = logging.getLogger("DartDisclosure")


class DisclosureType(Enum):
    """공시 유형"""
    CAPITAL_INCREASE = "유상증자"        # 유상증자
    CAPITAL_DECREASE = "자본감소"        # 감자
    MERGER_ACQUISITION = "합병인수"      # M&A
    SPIN_OFF = "분할"                    # 분할
    MAJOR_CONTRACT = "대규모계약"        # 대규모 계약
    MAJOR_INVESTMENT = "대규모투자"      # 대규모 시설투자
    MAJOR_SHAREHOLDER = "대주주변동"     # 주요주주 변동
    TREASURY_STOCK = "자기주식"          # 자기주식 취득/처분
    EXECUTIVE_CHANGE = "임원변경"        # 임원 변경
    EARNINGS_SURPRISE = "실적공시"       # 실적 발표
    OTHER = "기타"                       # 기타


@dataclass
class DisclosureEvent:
    """공시 이벤트"""
    corp_code: str
    corp_name: str
    stock_code: str
    report_title: str
    report_no: str
    disclosure_date: str
    disclosure_type: DisclosureType = DisclosureType.OTHER
    url: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)


class DartClient:
    """DART Open API 클라이언트
    
    API 문서: https://opendart.fss.or.kr/guide/main.do
    """
    
    BASE_URL = "https://opendart.fss.or.kr/api"
    
    # 공시 유형 매핑
    TYPE_KEYWORDS = {
        DisclosureType.CAPITAL_INCREASE: ["유상증자", "신주발행"],
        DisclosureType.CAPITAL_DECREASE: ["감자", "자본감소"],
        DisclosureType.MERGER_ACQUISITION: ["합병", "영업양수", "영업양도", "주식교환"],
        DisclosureType.SPIN_OFF: ["분할", "분리"],
        DisclosureType.MAJOR_CONTRACT: ["판매계약", "공급계약", "수주", "계약체결"],
        DisclosureType.MAJOR_INVESTMENT: ["시설투자", "신규시설", "대규모투자"],
        DisclosureType.MAJOR_SHAREHOLDER: ["대량보유", "주식등의", "최대주주"],
        DisclosureType.TREASURY_STOCK: ["자기주식", "자사주"],
        DisclosureType.EXECUTIVE_CHANGE: ["임원", "대표이사", "이사"],
        DisclosureType.EARNINGS_SURPRISE: ["실적", "영업이익", "매출액", "분기보고서", "반기보고서"],
    }
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("DART_API_KEY") or getattr(Config, "DART_API_KEY", None)
        
        if not self.api_key:
            logger.warning("DART API 키가 설정되지 않았습니다. .env 파일에 DART_API_KEY를 추가하세요.")
    
    def get_recent_disclosures(
        self, 
        corp_code: str = None,
        start_date: str = None,
        end_date: str = None,
        page_count: int = 100
    ) -> List[DisclosureEvent]:
        """
        최근 공시 목록 조회
        
        Args:
            corp_code: 기업 고유코드 (없으면 전체)
            start_date: 시작일 (YYYYMMDD)
            end_date: 종료일 (YYYYMMDD)
            page_count: 페이지당 건수
            
        Returns:
            공시 이벤트 리스트
        """
        if not self.api_key:
            return []
        
        # 기본값: 오늘
        if not end_date:
            end_date = date.today().strftime("%Y%m%d")
        if not start_date:
            start_date = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
        
        params = {
            "crtfc_key": self.api_key,
            "bgn_de": start_date,
            "end_de": end_date,
            "page_count": page_count
        }
        
        if corp_code:
            params["corp_code"] = corp_code
        
        try:
            response = requests.get(
                f"{self.BASE_URL}/list.json",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            return self.parse_response(data)
            
        except Exception as e:
            logger.error(f"DART API 호출 실패: {e}")
            return []
    
    def parse_response(self, data: Dict[str, Any]) -> List[DisclosureEvent]:
        """API 응답 파싱"""
        disclosures = []
        
        if data.get("status") != "000":
            logger.error(f"DART API 오류: {data.get('message')}")
            return []
        
        for item in data.get("list", []):
            disclosure_type = self.classify_disclosure_type(item.get("report_nm", ""))
            
            event = DisclosureEvent(
                corp_code=item.get("corp_code", ""),
                corp_name=item.get("corp_name", ""),
                stock_code=item.get("stock_code", ""),
                report_title=item.get("report_nm", ""),
                report_no=item.get("rcept_no", ""),
                disclosure_date=item.get("rcept_dt", ""),
                disclosure_type=disclosure_type,
                url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item.get('rcept_no', '')}",
                raw_data=item
            )
            disclosures.append(event)
        
        return disclosures
    
    def classify_disclosure_type(self, title: str) -> DisclosureType:
        """공시 제목으로 유형 분류"""
        for dtype, keywords in self.TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in title:
                    return dtype
        return DisclosureType.OTHER
    
    def get_disclosure_detail(self, report_no: str) -> Optional[str]:
        """
        공시 상세 내용 조회
        
        Args:
            report_no: 접수번호
            
        Returns:
            공시 문서 내용 (XML)
        """
        if not self.api_key:
            return None
        
        try:
            # 공시서류 원문 (XML)
            response = requests.get(
                f"{self.BASE_URL}/document.xml",
                params={
                    "crtfc_key": self.api_key,
                    "rcept_no": report_no
                },
                timeout=30
            )
            response.raise_for_status()
            return response.text
            
        except Exception as e:
            logger.error(f"공시 상세 조회 실패: {e}")
            return None


class LLMDisclosureAnalyzer:
    """LLM 기반 공시 분석기"""
    
    def __init__(self):
        self.model = None

        # Gemini 모델 초기화 (다중 키 fallback 지원)
        try:
            import google.generativeai as genai
            from src.utils.gemini_key_manager import get_key_manager

            _key_manager = get_key_manager()
            api_key = _key_manager.get_available_key()
            if api_key:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel(Config.LLM_MODEL_NAME)
                logger.info("Gemini 모델 초기화 완료")
            else:
                logger.warning("GOOGLE_API_KEY가 설정되지 않았습니다.")
        except ImportError:
            logger.warning("google-generativeai 패키지가 설치되지 않았습니다.")
    
    def analyze(self, disclosure: DisclosureEvent) -> Dict[str, Any]:
        """
        공시 분석
        
        Args:
            disclosure: 공시 이벤트
            
        Returns:
            분석 결과 (impact_score, summary, action, confidence)
        """
        if not self.model:
            return self._fallback_analysis(disclosure)
        
        try:
            return self._call_llm(disclosure)
        except Exception as e:
            logger.error(f"LLM 분석 실패: {e}")
            return self._fallback_analysis(disclosure)
    
    def _call_llm(self, disclosure: DisclosureEvent) -> Dict[str, Any]:
        """LLM API 호출"""
        prompt = f"""
당신은 주식 투자 전문가입니다. 다음 공시를 분석하고 투자 의견을 제시하세요.

[공시 정보]
- 기업명: {disclosure.corp_name}
- 종목코드: {disclosure.stock_code}
- 공시제목: {disclosure.report_title}
- 공시일자: {disclosure.disclosure_date}
- 공시유형: {disclosure.disclosure_type.value}

다음 형식으로 JSON 응답해주세요:
{{
    "impact_score": (float, -1.0 ~ 1.0, 음수는 악재, 양수는 호재),
    "summary": "(공시 내용 2-3줄 요약)",
    "action": "(BUY/SELL/HOLD 중 하나)",
    "confidence": (float, 0.0 ~ 1.0, 분석 신뢰도),
    "reasoning": "(판단 근거)"
}}
"""
        
        response = self.model.generate_content(prompt)
        text = response.text
        
        # JSON 파싱
        import json
        
        # ```json ... ``` 제거
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        return json.loads(text.strip())
    
    def _fallback_analysis(self, disclosure: DisclosureEvent) -> Dict[str, Any]:
        """규칙 기반 폴백 분석"""
        # 유형별 기본 영향도
        impact_map = {
            DisclosureType.CAPITAL_INCREASE: -0.5,  # 유상증자는 보통 악재
            DisclosureType.MERGER_ACQUISITION: 0.3,  # M&A는 보통 호재
            DisclosureType.MAJOR_CONTRACT: 0.5,      # 대규모 계약은 호재
            DisclosureType.MAJOR_INVESTMENT: 0.2,   # 투자는 약간 호재
            DisclosureType.TREASURY_STOCK: 0.3,     # 자사주 매입은 호재
            DisclosureType.EXECUTIVE_CHANGE: 0.0,   # 임원 변경은 중립
            DisclosureType.OTHER: 0.0
        }
        
        impact = impact_map.get(disclosure.disclosure_type, 0.0)
        
        action = "HOLD"
        if impact >= 0.3:
            action = "BUY"
        elif impact <= -0.3:
            action = "SELL"
        
        return {
            "impact_score": impact,
            "summary": f"{disclosure.corp_name}: {disclosure.report_title}",
            "action": action,
            "confidence": 0.5,  # 규칙 기반은 낮은 신뢰도
            "reasoning": "규칙 기반 분석 (LLM 미사용)"
        }


class DisclosureMonitor:
    """공시 모니터
    
    관심 종목의 공시를 실시간 모니터링합니다.
    """
    
    # 중요 공시 유형
    IMPORTANT_TYPES = {
        DisclosureType.CAPITAL_INCREASE,
        DisclosureType.CAPITAL_DECREASE,
        DisclosureType.MERGER_ACQUISITION,
        DisclosureType.SPIN_OFF,
        DisclosureType.MAJOR_CONTRACT,
        DisclosureType.MAJOR_INVESTMENT,
        DisclosureType.MAJOR_SHAREHOLDER,
    }
    
    def __init__(self, api_key: str = None, watch_list: List[str] = None):
        self.client = DartClient(api_key=api_key)
        self.analyzer = LLMDisclosureAnalyzer()
        self.watch_list = watch_list or []
        self._seen_reports: set = set()
    
    def add_to_watchlist(self, stock_code: str):
        """관심 종목 추가"""
        if stock_code not in self.watch_list:
            self.watch_list.append(stock_code)
    
    def remove_from_watchlist(self, stock_code: str):
        """관심 종목 제거"""
        if stock_code in self.watch_list:
            self.watch_list.remove(stock_code)
    
    def check_new_disclosures(self) -> List[Dict[str, Any]]:
        """
        새로운 공시 확인
        
        Returns:
            분석된 공시 리스트
        """
        # 최근 공시 조회
        all_disclosures = self.client.get_recent_disclosures()
        
        # 관심 종목 필터링
        if self.watch_list:
            all_disclosures = self.filter_by_watchlist(all_disclosures)
        
        # 중요 공시만 필터링
        important = self.filter_important(all_disclosures)
        
        # 새로운 공시만 처리
        new_disclosures = []
        for disclosure in important:
            if disclosure.report_no not in self._seen_reports:
                self._seen_reports.add(disclosure.report_no)
                
                # LLM 분석
                analysis = self.analyzer.analyze(disclosure)
                
                new_disclosures.append({
                    "disclosure": disclosure,
                    "analysis": analysis
                })
        
        return new_disclosures
    
    def filter_by_watchlist(self, disclosures: List[DisclosureEvent]) -> List[DisclosureEvent]:
        """관심 종목만 필터링"""
        return [d for d in disclosures if d.stock_code in self.watch_list]
    
    def filter_important(self, disclosures: List[DisclosureEvent]) -> List[DisclosureEvent]:
        """중요 공시만 필터링"""
        return [d for d in disclosures if d.disclosure_type in self.IMPORTANT_TYPES]


# 전역 인스턴스
_global_monitor: Optional[DisclosureMonitor] = None


def get_disclosure_monitor(watch_list: List[str] = None) -> DisclosureMonitor:
    """전역 공시 모니터 인스턴스 반환"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = DisclosureMonitor(watch_list=watch_list)
    return _global_monitor
