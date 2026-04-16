from typing import Any, Dict, List
import logging
import os
import warnings

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from src.analysis.market_data import MarketDataFetcher
from src.config import Config
from src.utils.gemini_key_manager import GeminiKeyExhaustedError, get_key_manager

logger = logging.getLogger("DebateManager")


def _normalize_ticker_candidates(ticker: str) -> tuple[str, list[str]]:
    cleaned_ticker = (ticker or "").strip().upper()
    if not cleaned_ticker:
        return "", []

    if cleaned_ticker.isdigit():
        return cleaned_ticker, [f"{cleaned_ticker}.KS", f"{cleaned_ticker}.KQ"]

    return cleaned_ticker, [cleaned_ticker]


class AnalystAgent:
    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role
        self._key_manager = get_key_manager()
        self._model_name = Config.LLM_MODEL_NAME

        first_key = self._key_manager.get_available_key()
        try:
            if first_key:
                self.llm = self._build_llm(first_key)
            else:
                logger.warning(f"{name}: GOOGLE_API_KEY\uac00 \uc5c6\uc5b4 LLM\uc744 \ucd08\uae30\ud654\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.")
                self.llm = None
        except Exception as e:
            logger.error(f"Failed to initialize LLM for {name}: {e}")
            self.llm = None

    def _build_llm(self, api_key: str | None = None) -> ChatGoogleGenerativeAI:
        previous_key = os.environ.get("GOOGLE_API_KEY")
        if api_key:
            os.environ["GOOGLE_API_KEY"] = api_key

        try:
            return ChatGoogleGenerativeAI(
                model=self._model_name,
                temperature=0.7,
            )
        finally:
            if api_key:
                if previous_key is None:
                    os.environ.pop("GOOGLE_API_KEY", None)
                else:
                    os.environ["GOOGLE_API_KEY"] = previous_key

    @staticmethod
    def _coerce_response_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(part if isinstance(part, str) else str(part) for part in content)
        return str(content)

    def speak(self, context: str, previous_messages: List[str]) -> str:
        if not self.llm:
            return f"\u26a0\ufe0f {self.name}: LLM \ucd08\uae30\ud654 \uc2e4\ud328. API \ud0a4\uc640 \ubaa8\ub378\uba85\uc744 \ud655\uc778\ud558\uc138\uc694."

        system_msg = SystemMessage(
            content=(
                f"\ub2f9\uc2e0\uc740 {self.name}\uc785\ub2c8\ub2e4.\n"
                f"\uc5ed\ud560 \uc124\uba85: {self.role}\n\n"
                "\uc8fc\uc2dd \ud1a0\ub860\uc5d0 \ucc38\uc5ec\ud574 \ub2f9\uc2e0\uc758 \uad00\uc810\uc73c\ub85c \ubd84\uc11d\ud558\uc138\uc694. "
                "\uc751\ub2f5\uc740 \ud55c\uad6d\uc5b4\ub85c, \ucd5c\ub300 3\ubb38\uc7a5\uc73c\ub85c \uac04\uacb0\ud558\uac8c \uc791\uc131\ud558\uc138\uc694. "
                "\ud544\uc694\ud558\uba74 \uc55e\uc120 \uc758\uacac\uc5d0 \ubc18\ubc15\ud558\uc138\uc694."
            )
        )

        user_content = f"\uc2dc\uc7a5 \ub370\uc774\ud130: {context}\n\n"
        if previous_messages:
            user_content += "\uc774\uc804 \ud1a0\ub860:\n"
            for msg in previous_messages:
                user_content += f"- {msg}\n"
        else:
            user_content += "핵심 쟁점을 먼저 제시하며 토론을 시작하세요."

        user_msg = HumanMessage(content=user_content)
        messages = [system_msg, user_msg]

        def _invoke(api_key: str) -> str:
            llm = self._build_llm(api_key)
            response = llm.invoke(messages)
            return self._coerce_response_text(response.content)

        try:
            return self._key_manager.call_with_fallback(_invoke)
        except GeminiKeyExhaustedError:
            return f"\u26a0\ufe0f {self.name}: \ubaa8\ub4e0 API \ud0a4 \ud560\ub2f9\ub7c9 \ucd08\uacfc. \uc7a0\uc2dc \ud6c4 \ub2e4\uc2dc \uc2dc\ub3c4\ud558\uc138\uc694."
        except Exception as e:
            logger.error(f"Error generating response for {self.name}: {e}")
            return f"\u26a0\ufe0f {self.name}: \ubd84\uc11d \uc0dd\uc131 \uc911 \uc624\ub958 \ubc1c\uc0dd \u2014 {str(e)[:200]}"


class DebateManager:
    def __init__(self):
        self.market_fetcher = MarketDataFetcher()
        self.agents = [
            AnalystAgent(
                "\uae30\uc220 \ubd84\uc11d\uac00",
                "\uac15\uc138 \uad00\uc810\uc758 \uae30\uc220 \ubd84\uc11d\uac00\uc785\ub2c8\ub2e4. \ub3cc\ud30c \ud328\ud134, \uac15\ud55c \ubaa8\uba58\ud140, \uc9c0\uc9c0 \uad6c\uac04\uc744 \uc911\uc810\uc801\uc73c\ub85c \ubcf4\uba70 \ube44\uad50\uc801 \ub099\uad00\uc801\uc73c\ub85c \ud310\ub2e8\ud569\ub2c8\ub2e4.",
            ),
            AnalystAgent(
                "\ub9ac\uc2a4\ud06c \uad00\ub9ac\uc790",
                "\uc57d\uc138 \uad00\uc810\uc758 \ub9ac\uc2a4\ud06c \uad00\ub9ac\uc790\uc785\ub2c8\ub2e4. \uace0\ud3c9\uac00, \uac70\uc2dc \ud658\uacbd \uc545\ud654, \ud558\ubc29 \uc704\ud5d8\uc744 \uc911\uc810\uc801\uc73c\ub85c \ubcf4\uba70 \ud68c\uc758\uc801\uc774\uace0 \ubcf4\uc218\uc801\uc73c\ub85c \ud310\ub2e8\ud569\ub2c8\ub2e4.",
            ),
            AnalystAgent(
                "\uc911\uc7ac\uc790",
                "\uc911\ub9bd\uc801\uc778 \uc911\uc7ac\uc790\uc785\ub2c8\ub2e4. \uae30\uc220 \ubd84\uc11d\uac00\uc640 \ub9ac\uc2a4\ud06c \uad00\ub9ac\uc790\uc758 \uc758\uacac\uc744 \uc885\ud569\ud574 \ucd5c\uc885 \uacb0\uc815\uc744 \ub0b4\ub9bd\ub2c8\ub2e4. \ub9c8\uc9c0\ub9c9 \ubb38\uc7a5\uc5d0\ub294 \ucd5c\uc885 \ud310\ub2e8\uc744 매수, 매도, 보유 \uc911 \ud558\ub098\ub85c \uba85\uc2dc\ud558\uc138\uc694.",
            ),
        ]

    def _build_market_context(self, ticker: str) -> str:
        cleaned_ticker, candidates = _normalize_ticker_candidates(ticker)
        if not candidates:
            return "\uc885\ubaa9 \ucf54\ub4dc\uac00 \ube44\uc5b4 \uc788\uc2b5\ub2c8\ub2e4. \uc77c\ubc18\uc801\uc778 \uc2dc\uc7a5 \uad00\uc810\uc5d0\uc11c\ub9cc \ubd84\uc11d\ud558\uc138\uc694."

        import logging as _logging

        yf_logger = _logging.getLogger("yfinance")
        previous_level = yf_logger.level
        yf_logger.setLevel(_logging.CRITICAL)

        last_error = None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                for candidate in candidates:
                    try:
                        df = self.market_fetcher.fetch_history(candidate, period="1mo")
                    except Exception as exc:
                        last_error = exc
                        continue

                    if df is None or df.empty:
                        last_error = ValueError(f"\ud2f0\ucee4 {candidate}\uc5d0 \ub300\ud55c \ub370\uc774\ud130\uac00 \uc5c6\uc2b5\ub2c8\ub2e4.")
                        continue

                    current_price = df["Close"].iloc[-1]
                    change = (df["Close"].iloc[-1] - df["Close"].iloc[0]) / df["Close"].iloc[0] * 100
                    if change > 0:
                        trend = "\uc0c1\uc2b9"
                    elif change < 0:
                        trend = "\ud558\ub77d"
                    else:
                        trend = "\ubcf4\ud569"

                    return (
                        f"\uc885\ubaa9: {cleaned_ticker}. \uc870\ud68c \uc2ec\ubcfc: {candidate}. \ud604\uc7ac\uac00: {current_price:.2f}. "
                        f"1\uac1c\uc6d4 \ubcc0\ub3d9\ub960: {change:.2f}%. \ucd5c\uadfc \ud750\ub984: {trend}."
                    )
        finally:
            yf_logger.setLevel(previous_level)

        logger.warning(
            "\uc2dc\uc7a5 \ub370\uc774\ud130 \uc870\ud68c \uc2e4\ud328 (%s): %s - %s",
            cleaned_ticker,
            type(last_error).__name__ if last_error else "UnknownError",
            str(last_error)[:100] if last_error else "no details",
        )
        return (
            f"\uc885\ubaa9: {cleaned_ticker}. \uc2dc\uc7a5 \ub370\uc774\ud130\ub97c \ud604\uc7ac \uac00\uc838\uc62c \uc218 \uc5c6\uc2b5\ub2c8\ub2e4 "
            "(\uc720\ud6a8\ud558\uc9c0 \uc54a\uc740 \uc885\ubaa9 \ucf54\ub4dc\uc774\uac70\ub098 \uc0c1\uc7a5\ud3d0\uc9c0 \uac00\ub2a5\uc131). "
            "\ubcf4\uc720 \uc9c0\uc2dd\uc744 \ubc14\ud0d5\uc73c\ub85c \uc77c\ubc18\uc801\uc778 \ubd84\uc11d\uc744 \uc81c\uacf5\ud558\uace0 \ucd5c\uadfc \uc2dc\uc7a5 \ud750\ub984\uacfc \uc5c5\uc885 \uc0c1\ud669 \uc911\uc2ec\uc73c\ub85c \uc124\uba85\ud558\uc138\uc694."
        )

    def run_debate(self, ticker: str) -> Dict[str, Any]:
        context = self._build_market_context(ticker)

        history = []
        debate_log = []

        for agent in self.agents:
            response = agent.speak(context, history)
            debate_entry = {"agent": agent.name, "msg": response}
            debate_log.append(debate_entry)
            history.append(f"{agent.name}: {response}")

        last_msg = debate_log[-1]["msg"]
        normalized_last_msg = last_msg.upper()
        decision = "HOLD"
        if "매수" in last_msg or "BUY" in normalized_last_msg:
            decision = "BUY"
        elif "매도" in last_msg or "SELL" in normalized_last_msg:
            decision = "SELL"
        elif "보유" in last_msg or "HOLD" in normalized_last_msg:
            decision = "HOLD"

        return {
            "ticker": ticker,
            "decision": decision,
            "history": debate_log,
        }
