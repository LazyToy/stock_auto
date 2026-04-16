import os
from typing import List, Dict, Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool

from src.config import Config
from src.utils.gemini_key_manager import get_key_manager, GeminiKeyExhaustedError
from src.copilot.tools import get_portfolio_summary, get_recent_trades, explain_trade_decision

class CopilotAgent:
    """AI Trading Copilot Agent"""
    
    def __init__(self, model_name: str = None):
        """
        초기화
        Args:
            model_name: 사용할 Google Gemini 모델명. None이면 Config.LLM_MODEL_NAME 사용.
        """
        self.is_active = False
        self._model_name = model_name or Config.LLM_MODEL_NAME
        self._key_manager = get_key_manager()

        # 사용 가능한 키 확인
        first_key = self._key_manager.get_available_key()
        if not first_key:
            self.llm = None
            print("Warning: GOOGLE_API_KEY가 없습니다. Copilot이 작동하지 않습니다.")
            return

        try:
            self.llm = ChatGoogleGenerativeAI(
                model=self._model_name,
                google_api_key=first_key,
                temperature=0.3
            )
            self.tools = [get_portfolio_summary, get_recent_trades, explain_trade_decision]
            self.llm_with_tools = self.llm.bind_tools(self.tools)
            self.is_active = True
        except Exception as e:
            print(f"Failed to initialize Copilot: {e}")
            self.llm = None

        self.system_prompt = """당신은 전문 주식 트레이딩 비서 'StockCopilot'입니다.
사용자의 포트폴리오 상태, 거래 내역, 매매 이유 등을 조회하여 명확하고 친절하게 답변해주세요.
주어진 도구(Tools)를 적극적으로 활용하여 정확한 데이터를 기반으로 대답해야 합니다.
사용자의 질문이 도구 범위를 벗어나면, 일반적인 금융 지식을 바탕으로 짧게 조언하거나 모른다고 답하세요."""

        self.chat_history: List[Any] = [
            SystemMessage(content=self.system_prompt)
        ]
        
    def process_query(self, query: str) -> str:
        """
        사용자 질의 처리 — 키 소진 시 자동 fallback
        Args:
            query: 사용자 질문 텍스트
        Returns:
            str: AI 응답 텍스트
        """
        if not self.is_active:
            return "⚠️ Google API Key가 설정되지 않았습니다. .env 파일에 'GOOGLE_API_KEY'를 추가해주세요."

        try:
            # 사용자 메시지 추가
            self.chat_history.append(HumanMessage(content=query))

            def _invoke_with_key(api_key: str):
                """api_key를 사용해 llm 실행 (fallback 지원용)"""
                lc_llm = ChatGoogleGenerativeAI(
                    model=self._model_name,
                    google_api_key=api_key,
                    temperature=0.3
                ).bind_tools(self.tools)
                return lc_llm.invoke(self.chat_history)

            # 모델 호출 (키 fallback 포함)
            response = self._key_manager.call_with_fallback(_invoke_with_key)

            # Tool Call 처리 루프
            # Gemini가 Tool Call을 반환하면 실행 후 결과를 다시 모델에 전달
            while response.tool_calls:
                # Tool Call 메시지도 기록에 추가
                self.chat_history.append(response)

                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_id = tool_call["id"]

                    # 도구 실행
                    result = self._execute_tool(tool_name, tool_args)

                    # 결과 메시지 생성
                    tool_msg = ToolMessage(
                        tool_call_id=tool_id,
                        name=tool_name,
                        content=str(result)
                    )
                    self.chat_history.append(tool_msg)

                # 도구 결과 포함하여 다시 모델 호출
                response = self._key_manager.call_with_fallback(_invoke_with_key)

            # 최종 응답 기록 및 반환
            self.chat_history.append(response)
            return response.content

        except GeminiKeyExhaustedError as e:
            return f"⚠️ 모든 Gemini API 키가 할당량을 초과했습니다. 잠시 후 다시 시도하세요."
        except Exception as e:
            error_msg = f"죄송합니다. 처리 중 오류가 발생했습니다: {str(e)}"
            return error_msg

    def _execute_tool(self, name: str, args: Dict[str, Any]) -> str:
        """도구 이름으로 함수 실행"""
        tool_map = {t.name: t for t in self.tools}
        if name in tool_map:
            # LangChain Tool 실행 (.invoke 사용)
            return tool_map[name].invoke(args)
        return f"Error: Tool {name} not found"
