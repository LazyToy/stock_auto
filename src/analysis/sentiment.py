"""뉴스 감성 분석 및 리스크 감지 모듈

Yahoo Finance (미국/한국) 및 네이버 금융 (한국) 뉴스를 크롤링하여
악재 키워드를 분석하고 부정 점수를 산출합니다.
"""

import logging
import requests
from bs4 import BeautifulSoup
try:
    import yfinance as yf
except ImportError:  # pragma: no cover - optional dependency
    yf = None
from datetime import datetime, timedelta
import os
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

from src.config import Config
from src.utils.gemini_key_manager import get_key_manager, GeminiKeyExhaustedError


logger = logging.getLogger("SentimentAnalyzer")


class SentimentAnalyzer:
    def __init__(self):
        # 악재 키워드 정의 (치명적인 단어 위주)
        self.fatal_keywords_kr = [
            "횡령", "배임", "상장폐지", "거래정지", "부도", "파산",
            "검찰", "압수수색", "구속", "분식회계", "한정의견", "의견거절",
            "유상증자", "폭락", "하한가", "불성실공시"
        ]

        self.fatal_keywords_us = [
            "fraud", "investigation", "delisting", "bankruptcy", "lawsuit",
            "scandal", "crash", "plunge", "sec probe", "accounting error",
            "restatement", "auditor resignation", "class action"
        ]

        # Google Gemini 클라이언트 초기화 (다중 키 fallback 지원)
        self.gemini_model = None
        self._key_manager = get_key_manager()
        first_key = self._key_manager.get_available_key()
        if GEMINI_AVAILABLE and first_key:
            try:
                genai.configure(api_key=first_key)
                self.gemini_model = genai.GenerativeModel('gemini-pro')
                logger.info("Google Gemini LLM 감성 분석 활성화")
            except Exception as e:
                logger.warning(f"Google Gemini 초기화 실패: {e}")

    def analyze_ticker(self, ticker: str) -> float:
        """종목별 뉴스 분석을 통해 부정 점수 반환 (-1.0 ~ 0.0)

        Returns:
            float: 0.0 (중립/긍정) ~ -1.0 (치명적 악재)
        """
        try:
            is_kr = ticker.isdigit() or ticker.endswith(".KS") or ticker.endswith(".KQ")

            if is_kr:
                # 한국 주식: 네이버 금융 크롤링 (보조) + Yahoo Finance
                score_naver = self._analyze_naver_finance(ticker)
                return score_naver
            else:
                # 미국 주식: Yahoo Finance API
                score_yf = self._analyze_yahoo_finance(ticker)
                return score_yf

        except Exception as e:
            logger.error(f"{ticker} 감성 분석 실패: {e}")
            return 0.0

    def _analyze_yahoo_finance(self, ticker: str) -> float:
        """Yahoo Finance 뉴스 분석 (미국 주식용)"""
        try:
            if yf is None:
                logger.warning("yfinance is unavailable; skipping Yahoo Finance analysis for %s", ticker)
                return 0.0
            stock = yf.Ticker(ticker)
            news_list = stock.news

            negative_score = 0.0

            for item in news_list:
                title = item.get('title', '').lower()
                # 키워드 매칭
                for kw in self.fatal_keywords_us:
                    if kw in title:
                        logger.warning(f"🚨 [US] 악재 감지 ({ticker}): {title}")
                        negative_score -= 0.5  # 키워드 하나당 -0.5

            # LLM 사용 가능한 경우
            if news_list:
                titles = [item.get('title', '') for item in news_list]
                llm_score = self._analyze_with_llm(titles)

                if llm_score < 0:
                    return min(max(-1.0, negative_score), llm_score)

            return max(-1.0, negative_score)  # 최대 -1.0까지

        except Exception as e:
            logger.warning(f"Yahoo Finance 뉴스 조회 실패: {e}")
            return 0.0

    def _analyze_naver_finance(self, ticker: str) -> float:
        """네이버 금융 뉴스 분석 (한국 주식용)"""
        try:
            # Ticker 처리 (005930.KS -> 005930)
            code = ticker.split('.')[0]
            url = f"https://finance.naver.com/item/news_news.nhn?code={code}"

            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')

            titles = soup.select('.title')
            negative_score = 0.0

            for t in titles:
                title = t.get_text().strip()
                # 키워드 매칭
                for kw in self.fatal_keywords_kr:
                    if kw in title:
                        logger.warning(f"🚨 [KR] 악재 감지 ({ticker}): {title}")
                        negative_score -= 0.5

            # LLM 사용 가능한 경우
            if titles:
                title_texts = [t.get_text().strip() for t in titles]
                llm_score = self._analyze_with_llm(title_texts)

                # 키워드 방식과 LLM 방식 중 더 보수적인(낮은) 점수 채택
                if llm_score < 0:
                    return min(max(-1.0, negative_score), llm_score)
                else:
                    return max(-1.0, negative_score)

            return max(-1.0, negative_score)

        except Exception as e:
            logger.warning(f"네이버 금융 뉴스 조회 실패: {e}")
            return 0.0

    def _analyze_with_llm(self, titles: list) -> float:
        """LLM을 이용한 뉴스 제목 감성 분석 (Gemini Pro) — 키 fallback 포함

        gemini_model이 직접 주입된 경우 해당 모델을 우선 사용합니다.
        (테스트 mock 주입 및 레거시 호환)
        """
        if not titles:
            return 0.0

        prompt = """
            너는 금융 뉴스 분석 전문가야. 다음 뉴스 제목들을 분석하여 해당 종목 주가에 미칠 영향을 -1.0 (매우 부정/악재) ~ 1.0 (매우 긍정/호재) 사이의 점수로 평가해줘.

            규칙:
            1. 결과는 오직 숫자 하나만 출력해야 해. (예: -0.8, 0.5, 0.0)
            2. 설명이나 다른 텍스트는 절대 포함하지 마.

            뉴스 제목들:
            """
        for t in titles[:10]:  # 토큰 절약을 위해 10개만
            prompt += f"- {t}\n"

        import re

        def _parse_score(text: str) -> float:
            """LLM 응답에서 숫자 점수 추출"""
            content = text.strip()
            match = re.search(r"[-+]?\d*\.\d+|\d+", content)
            if match:
                score = float(match.group())
                return max(-1.0, min(1.0, score))
            return 0.0

        # 경로 1: gemini_model이 직접 주입된 경우 (테스트 mock 및 레거시 호환)
        if self.gemini_model is not None:
            try:
                response = self.gemini_model.generate_content(prompt)
                return _parse_score(response.text)
            except Exception as e:
                logger.warning(f"LLM 분석 실패 (직접 모델): {e}")
                return 0.0

        # 경로 2: GeminiKeyManager를 통한 fallback 실행
        if not self._key_manager.key_count():
            return 0.0

        def _call(api_key: str) -> float:
            """api_key로 Gemini 호출 (fallback 지원용)"""
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt)
            return _parse_score(response.text)

        try:
            return self._key_manager.call_with_fallback(_call)
        except GeminiKeyExhaustedError:
            logger.warning("LLM 분석 실패: 모든 API 키 할당량 초과")
            return 0.0
        except Exception as e:
            logger.warning(f"LLM 분석 실패: {e}")
            return 0.0


if __name__ == "__main__":
    # 테스트
    analyzer = SentimentAnalyzer()
    print(f"Test US (AAPL): {analyzer.analyze_ticker('AAPL')}")
    print(f"Test KR (005930.KS): {analyzer.analyze_ticker('005930.KS')}")
    # 가상의 악재 테스트 (실제로는 잘 안 나오겠지만)
