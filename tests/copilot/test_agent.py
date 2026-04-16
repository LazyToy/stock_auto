import unittest
from unittest.mock import MagicMock, patch
from src.copilot.agent import CopilotAgent

class TestCopilotAgent(unittest.TestCase):
    def setUp(self):
        self.mock_llm_patcher = patch('src.copilot.agent.ChatGoogleGenerativeAI')
        self.mock_llm_cls = self.mock_llm_patcher.start()
        self.mock_llm = self.mock_llm_cls.return_value
        
    def tearDown(self):
        self.mock_llm_patcher.stop()

    def test_initialization(self):
        """에이전트 초기화 테스트"""
        try:
            agent = CopilotAgent()
            self.assertIsNotNone(agent)
        except Exception as e:
            self.fail(f"Agent initialization failed: {e}")

    def test_process_query(self):
        """질의 처리 테스트"""
        agent = CopilotAgent()
        
        # Mocking the chain invoke
        # The agent uses self.llm_with_tools.invoke
        agent.llm_with_tools = MagicMock()
        
        expected_response = "포트폴리오 자산은 100만원입니다."
        
        # Mock response object
        mock_response = MagicMock()
        mock_response.content = expected_response
        mock_response.tool_calls = [] # 중요: tool_calls가 비어있어야 루프 종료
        
        agent.llm_with_tools.invoke.return_value = mock_response
        
        response = agent.process_query("내 자산 얼마야?")
        self.assertEqual(response, expected_response)

if __name__ == '__main__':
    unittest.main()
