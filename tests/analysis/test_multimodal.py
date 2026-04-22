import unittest
from typing import cast
from unittest.mock import MagicMock, call, patch

import pandas as pd

from src.analysis.multimodal import MultimodalAnalyst


class TestMultimodalAnalyst(unittest.TestCase):
    def setUp(self):
        self.config_patcher = patch("src.config.Config.GOOGLE_API_KEY", "dummy_key")
        self.config_patcher.start()

        self.genai_patcher = patch("google.generativeai.configure")
        self.genai_patcher.start()

        self.model_patcher = patch("google.generativeai.GenerativeModel")
        self.MockModel = self.model_patcher.start()

        self.analyst = MultimodalAnalyst()
        self.model = cast(MagicMock, self.analyst.model)

    def tearDown(self):
        self.config_patcher.stop()
        self.genai_patcher.stop()
        self.model_patcher.stop()

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_hot_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock(self, mock_chart, mock_reddit, mock_history):
        """멀티모달 통합 분석 테스트"""
        mock_history.return_value = pd.DataFrame({"Close": [100, 110]}, index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
        mock_reddit.return_value = [{"title": "AAPL Good", "sentiment": 0.8}]
        mock_chart.return_value = b"fake_image_bytes"

        mock_response = MagicMock()
        mock_response.text = '{"signal": "BUY", "confidence": 0.9, "reason": "Strong chart + Positive sentiment"}'
        self.model.generate_content.return_value = mock_response

        result = self.analyst.analyze_stock("AAPL")

        mock_history.assert_called()
        mock_chart.assert_called()
        self.model.generate_content.assert_called()
        self.assertIn("signal", result)
        self.assertIn("confidence", result)
        self.assertIn("technical_summary", result)
        self.assertIn("기술 지표 요약", result["technical_summary"])
        self.assertEqual(result["signal"], "BUY")

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_hot_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_tries_kr_symbol_candidates_for_numeric_ticker(self, mock_chart, mock_reddit, mock_history):
        """숫자형 한국 종목은 .KS/.KQ 후보를 순차 시도해야 한다."""
        mock_history.side_effect = [pd.DataFrame(), pd.DataFrame({"Close": [100, 110]})]
        mock_reddit.return_value = []
        mock_chart.return_value = b"fake_image_bytes"

        mock_response = MagicMock()
        mock_response.text = '{"signal": "HOLD", "confidence": 0.5, "reason": "중립"}'
        self.model.generate_content.return_value = mock_response

        self.analyst.analyze_stock("317330")

        self.assertEqual(
            mock_history.call_args_list,
            [call("317330.KS", period="6mo"), call("317330.KQ", period="6mo")],
        )

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_hot_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_retries_with_next_kr_candidate_after_exception(self, mock_chart, mock_reddit, mock_history):
        """.KS 조회 예외가 나도 다음 KR 후보로 재시도해야 한다."""
        mock_history.side_effect = [RuntimeError("boom"), pd.DataFrame({"Close": [100, 110]})]
        mock_reddit.return_value = []
        mock_chart.return_value = b"fake_image_bytes"

        mock_response = MagicMock()
        mock_response.text = '{"signal": "BUY", "confidence": 0.7, "reason": "재시도 성공"}'
        self.model.generate_content.return_value = mock_response

        result = self.analyst.analyze_stock("317330")

        self.assertEqual(result["signal"], "BUY")
        self.assertEqual(
            mock_history.call_args_list,
            [call("317330.KS", period="6mo"), call("317330.KQ", period="6mo")],
        )

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_hot_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_uses_korean_prompt(self, mock_chart, mock_reddit, mock_history):
        """멀티모달 프롬프트는 한국어여야 한다."""
        mock_history.return_value = pd.DataFrame({"Close": [100, 110]})
        mock_reddit.return_value = [{"title": "테스트", "sentiment": 0.1}]
        mock_chart.return_value = b"fake_image_bytes"

        mock_response = MagicMock()
        mock_response.text = '{"signal": "BUY", "confidence": 0.8, "reason": "호전적"}'
        self.model.generate_content.return_value = mock_response

        self.analyst.analyze_stock("005930")

        prompt_text = self.model.generate_content.call_args.args[0][0]
        self.assertIn("다음 종목", prompt_text)
        self.assertIn("출력 형식", prompt_text)
        self.assertIn("매수, 매도, 보유", prompt_text)
        self.assertNotIn("BUY, SELL, HOLD", prompt_text)
        self.assertNotIn("Analyze the following stock", prompt_text)

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_hot_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_short_data_uses_indicator_fallback_text(self, mock_chart, mock_reddit, mock_history):
        """지표 계산 길이가 부족하면 프롬프트에 fallback 문구가 들어가야 한다."""
        mock_history.return_value = pd.DataFrame({"Close": [100, 101, 102, 103, 104]})
        mock_reddit.return_value = []
        mock_chart.return_value = b"fake_image_bytes"

        mock_response = MagicMock()
        mock_response.text = '{"signal": "HOLD", "confidence": 0.4, "reason": "중립"}'
        self.model.generate_content.return_value = mock_response

        self.analyst.analyze_stock("005930")

        prompt_text = self.model.generate_content.call_args.args[0][0]
        self.assertIn("기술 지표 요약", prompt_text)
        self.assertIn("데이터가 부족해 RSI/MACD/볼린저 밴드", prompt_text)

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_hot_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_prompt_includes_non_ma_indicator_summary(self, mock_chart, mock_reddit, mock_history):
        """심층분석 프롬프트는 RSI/MACD/볼린저/거래량 요약을 포함해야 한다."""
        index = pd.date_range("2024-01-01", periods=40, freq="D")
        mock_history.return_value = pd.DataFrame(
            {
                "Close": [100 + i for i in range(40)],
                "Volume": [1000 + (i * 10) for i in range(40)],
            },
            index=index,
        )
        mock_reddit.return_value = []
        mock_chart.return_value = b"fake_image_bytes"

        mock_response = MagicMock()
        mock_response.text = '{"signal": "BUY", "confidence": 0.8, "reason": "호전적"}'
        self.model.generate_content.return_value = mock_response

        self.analyst.analyze_stock("005930")

        prompt_text = self.model.generate_content.call_args.args[0][0]
        self.assertIn("기술 지표 요약", prompt_text)
        self.assertIn("RSI(14)", prompt_text)
        self.assertIn("MACD", prompt_text)
        self.assertIn("볼린저 밴드", prompt_text)
        self.assertIn("20일 평균 대비", prompt_text)


    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_hot_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_prompt_requests_market_context_and_structured_explanation(self, mock_chart, mock_reddit, mock_history):
        """심층분석 프롬프트는 시장 컨텍스트와 구조화된 설명 필드를 요구해야 한다."""
        index = pd.date_range("2024-01-01", periods=70, freq="D")
        mock_history.return_value = pd.DataFrame(
            {
                "Close": [100 + i for i in range(70)],
                "Volume": [1000 + (i * 5) for i in range(70)],
            },
            index=index,
        )
        mock_reddit.return_value = []
        mock_chart.return_value = b"fake_image_bytes"

        mock_response = MagicMock()
        mock_response.text = '{"signal": "BUY", "confidence": 0.8, "reason": "호전적"}'
        self.model.generate_content.return_value = mock_response

        self.analyst.analyze_stock("005930")

        prompt_text = self.model.generate_content.call_args.args[0][0]
        self.assertIn("시장 컨텍스트", prompt_text)
        self.assertIn('"key_drivers"', prompt_text)
        self.assertIn('"risk_factors"', prompt_text)

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_hot_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_returns_market_context_and_default_explanation_lists(self, mock_chart, mock_reddit, mock_history):
        """LLM이 상세 설명을 비워도 시장 컨텍스트와 기본 설명 리스트는 반환해야 한다."""
        index = pd.date_range("2024-01-01", periods=70, freq="D")
        mock_history.return_value = pd.DataFrame(
            {
                "Close": [100 + i for i in range(70)],
                "Volume": [1000 + (i * 5) for i in range(70)],
            },
            index=index,
        )
        mock_reddit.return_value = []
        mock_chart.return_value = b"fake_image_bytes"

        mock_response = MagicMock()
        mock_response.text = '{"signal": "BUY", "confidence": 0.8, "reason": "호전적"}'
        self.model.generate_content.return_value = mock_response

        result = self.analyst.analyze_stock("005930")

        self.assertIn("market_context_summary", result)
        self.assertIn("시장 컨텍스트", result["market_context_summary"])
        self.assertEqual(result["key_drivers"], [])
        self.assertEqual(result["risk_factors"], [])


    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_hot_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_returns_analysis_sources_provenance(self, mock_chart, mock_reddit, mock_history):
        """심층분석 결과는 어떤 입력 축을 사용했는지 provenance를 반환해야 한다."""
        index = pd.date_range("2024-01-01", periods=70, freq="D")
        mock_history.return_value = pd.DataFrame(
            {
                "Close": [100 + i for i in range(70)],
                "Volume": [1000 + (i * 5) for i in range(70)],
            },
            index=index,
        )
        mock_reddit.return_value = []
        mock_chart.return_value = b"fake_image_bytes"

        mock_response = MagicMock()
        mock_response.text = '{"signal": "BUY", "confidence": 0.8, "reason": "호전적"}'
        self.model.generate_content.return_value = mock_response

        result = self.analyst.analyze_stock("005930")

        self.assertEqual(result["analysis_sources"], ["시장 컨텍스트", "기술 지표", "소셜 심리"])


if __name__ == "__main__":
    unittest.main()
