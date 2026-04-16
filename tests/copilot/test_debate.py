import unittest
from unittest.mock import MagicMock, call, patch

import pandas as pd

from src.copilot.debate import AnalystAgent, DebateManager


class TestDebateSystem(unittest.TestCase):
    def setUp(self):
        self.manager = DebateManager()

    def test_agent_initialization(self):
        """에이전트 페르소나 초기화 테스트"""
        agent = AnalystAgent("TestBot", "You are a tester.")
        self.assertEqual(agent.name, "TestBot")
        self.assertEqual(agent.role, "You are a tester.")

    @patch("src.copilot.debate.AnalystAgent.speak")
    def test_debate_flow(self, mock_speak):
        """토론 흐름 테스트 (Technical -> Risk -> Moderator)"""
        mock_speak.side_effect = [
            "기술적 관점: 매수 우위",
            "리스크 관점: 변동성 주의",
            "최종 판단: HOLD",
        ]

        price_df = pd.DataFrame({"Close": [100.0, 105.0]})

        with patch("src.analysis.market_data.MarketDataFetcher.fetch_history", return_value=price_df):
            result = self.manager.run_debate("AAPL")

        self.assertEqual(len(result["history"]), 3)
        self.assertEqual(result["decision"], "HOLD")
        self.assertEqual(mock_speak.call_count, 3)

    @patch("src.copilot.debate.AnalystAgent.speak")
    def test_run_debate_tries_kr_symbol_candidates_for_numeric_ticker(self, mock_speak):
        """숫자형 한국 종목 코드는 .KS/.KQ 후보를 순차 시도해야 한다."""
        mock_speak.side_effect = [
            "기술적 관점: 관망",
            "리스크 관점: 관망",
            "최종 판단: HOLD",
        ]

        empty_df = pd.DataFrame()
        kq_df = pd.DataFrame({"Close": [1000.0, 1100.0]})

        def fetch_side_effect(symbol, period="2y"):
            if symbol == "317330.KS":
                return empty_df
            if symbol == "317330.KQ":
                return kq_df
            raise AssertionError(f"예상하지 못한 심볼 호출: {symbol}")

        with patch("src.analysis.market_data.MarketDataFetcher.fetch_history", side_effect=fetch_side_effect) as mock_fetch:
            result = self.manager.run_debate("317330")

        self.assertEqual(result["ticker"], "317330")
        self.assertEqual(
            mock_fetch.call_args_list,
            [call("317330.KS", period="1mo"), call("317330.KQ", period="1mo")],
        )

    @patch("src.copilot.debate.get_key_manager")
    @patch("src.copilot.debate.ChatGoogleGenerativeAI")
    def test_speak_uses_korean_prompt_and_context(self, mock_llm_cls, mock_get_key_manager):
        """LLM에 전달되는 시스템/사용자 메시지는 한국어여야 한다."""
        mock_key_manager = MagicMock()
        mock_key_manager.get_available_key.return_value = "test-key"
        mock_key_manager.call_with_fallback.side_effect = lambda func: func("test-key")
        mock_get_key_manager.return_value = mock_key_manager

        mock_response = MagicMock()
        mock_response.content = "응답"
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_llm_cls.return_value = mock_llm

        agent = AnalystAgent("테스트 분석가", "보수적으로 분석합니다.")
        response = agent.speak("종목: 317330, 현재가: 1000원", [])

        self.assertEqual(response, "응답")
        messages = mock_llm.invoke.call_args.args[0]
        self.assertIn("당신은 테스트 분석가입니다", messages[0].content)
        self.assertIn("주식 토론", messages[0].content)
        manager = DebateManager()
        self.assertIn("매수, 매도, 보유", manager.agents[-1].role)
        self.assertNotIn("BUY, SELL, HOLD", manager.agents[-1].role)
        self.assertIn("시장 데이터", messages[1].content)
        self.assertIn("핵심 쟁점을 먼저 제시", messages[1].content)
        self.assertNotIn("You are", messages[0].content)
        self.assertNotIn("Context (Market Data)", messages[1].content)


if __name__ == "__main__":
    unittest.main()
