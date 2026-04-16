"""DART 공시 분석 테스트

DART Open API를 통해 실시간 공시를 수집하고 LLM으로 분석하는 기능을 테스트합니다.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, date
from src.analysis.dart_disclosure import (
    DartClient,
    DisclosureEvent,
    DisclosureType,
    LLMDisclosureAnalyzer,
    DisclosureMonitor
)


class TestDartClient(unittest.TestCase):
    """DART API 클라이언트 테스트"""
    
    def setUp(self):
        self.client = DartClient(api_key="test_key")
        
    def test_disclosure_type_classification(self):
        """공시 유형 분류 테스트"""
        # 유상증자
        title1 = "주식등의대량보유상황보고서"
        self.assertEqual(
            self.client.classify_disclosure_type(title1),
            DisclosureType.MAJOR_SHAREHOLDER
        )
        
        # 합병
        title2 = "합병결정"
        self.assertEqual(
            self.client.classify_disclosure_type(title2),
            DisclosureType.MERGER_ACQUISITION
        )
        
        # 대규모 계약
        title3 = "단일판매ㆍ공급계약체결"
        self.assertEqual(
            self.client.classify_disclosure_type(title3),
            DisclosureType.MAJOR_CONTRACT
        )
        
    def test_parse_disclosure_response(self):
        """API 응답 파싱 테스트"""
        mock_response = {
            "status": "000",
            "message": "정상",
            "list": [
                {
                    "corp_code": "00126380",
                    "corp_name": "삼성전자",
                    "stock_code": "005930",
                    "report_nm": "주요사항보고서(유상증자결정)",
                    "rcept_no": "20260209000001",
                    "rcept_dt": "20260209"
                }
            ]
        }
        
        disclosures = self.client.parse_response(mock_response)
        
        self.assertEqual(len(disclosures), 1)
        self.assertEqual(disclosures[0].corp_name, "삼성전자")
        self.assertEqual(disclosures[0].stock_code, "005930")


class TestLLMDisclosureAnalyzer(unittest.TestCase):
    """LLM 공시 분석기 테스트"""
    
    def setUp(self):
        self.analyzer = LLMDisclosureAnalyzer()
        
    def test_analyze_disclosure_returns_impact_score(self):
        """공시 분석 결과에 영향도 점수가 포함되는지 테스트"""
        disclosure = DisclosureEvent(
            corp_code="00126380",
            corp_name="삼성전자",
            stock_code="005930",
            report_title="주요사항보고서(유상증자결정)",
            report_no="20260209000001",
            disclosure_date="20260209",
            disclosure_type=DisclosureType.CAPITAL_INCREASE
        )
        
        # Mock LLM 응답
        with patch.object(self.analyzer, '_call_llm') as mock_llm:
            mock_llm.return_value = {
                "impact_score": -0.6,
                "summary": "삼성전자가 대규모 유상증자를 결정했습니다. 주가 희석 우려.",
                "action": "SELL",
                "confidence": 0.8
            }
            
            result = self.analyzer.analyze(disclosure)
            
        self.assertIn("impact_score", result)
        self.assertIn("summary", result)
        self.assertIn("action", result)
        self.assertEqual(result["action"], "SELL")


class TestDisclosureMonitor(unittest.TestCase):
    """공시 모니터 테스트"""
    
    def setUp(self):
        self.monitor = DisclosureMonitor(
            api_key="test_key",
            watch_list=["005930", "000660", "035420"]
        )
        
    def test_filter_by_watchlist(self):
        """관심 종목 필터링 테스트"""
        all_disclosures = [
            DisclosureEvent("1", "삼성전자", "005930", "Test1", "1", "20260209", DisclosureType.OTHER),
            DisclosureEvent("2", "SK하이닉스", "000660", "Test2", "2", "20260209", DisclosureType.OTHER),
            DisclosureEvent("3", "현대차", "005380", "Test3", "3", "20260209", DisclosureType.OTHER),  # 관심목록 외
        ]
        
        filtered = self.monitor.filter_by_watchlist(all_disclosures)
        
        self.assertEqual(len(filtered), 2)
        self.assertTrue(all(d.stock_code in self.monitor.watch_list for d in filtered))
        
    def test_filter_by_importance(self):
        """중요 공시 필터링 테스트"""
        disclosures = [
            DisclosureEvent("1", "A", "005930", "유상증자", "1", "20260209", DisclosureType.CAPITAL_INCREASE),
            DisclosureEvent("2", "B", "000660", "단순참고", "2", "20260209", DisclosureType.OTHER),
        ]
        
        # 중요 공시만 필터링
        important = self.monitor.filter_important(disclosures)
        
        self.assertEqual(len(important), 1)
        self.assertEqual(important[0].disclosure_type, DisclosureType.CAPITAL_INCREASE)


if __name__ == '__main__':
    unittest.main()
