import unittest
from typing import Any, cast
from unittest.mock import MagicMock, call, patch

import pandas as pd

from src.analysis.multimodal import MultimodalAnalyst


class FakeGeminiKeyManager:
    def get_available_key(self) -> str:
        return "dummy_key"

    def call_with_fallback(self, func: Any, retry_on: Any = None) -> Any:
        return func("dummy_key")


def make_price_history(days: int = 70) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=days, freq="D")
    return pd.DataFrame(
        {
            "Close": [100 + i for i in range(days)],
            "Volume": [1000 + (i * 5) for i in range(days)],
        },
        index=index,
    )


class TestMultimodalAnalyst(unittest.TestCase):
    def setUp(self):
        self.key_manager_patcher = patch(
            "src.analysis.multimodal.get_key_manager",
            return_value=FakeGeminiKeyManager(),
        )
        self.key_manager_patcher.start()

        self.genai_patcher = patch("google.generativeai.configure")
        self.mock_configure = self.genai_patcher.start()

        self.model_patcher = patch("google.generativeai.GenerativeModel")
        self.MockModel = self.model_patcher.start()

        self.news_patcher = patch("src.analysis.multimodal.NewsFetcher.fetch_for_ticker", return_value=[])
        self.mock_fetch_news = self.news_patcher.start()

        self.analyst = MultimodalAnalyst()
        self.model = cast(MagicMock, self.analyst.model)

    def tearDown(self):
        self.news_patcher.stop()
        self.key_manager_patcher.stop()
        self.genai_patcher.stop()
        self.model_patcher.stop()

    def set_model_response(self, payload: str = '{"signal": "BUY", "confidence": 0.8, "reason": "ok"}'):
        mock_response = MagicMock()
        mock_response.text = payload
        self.model.generate_content.return_value = mock_response

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_ticker_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_returns_parsed_llm_result(self, mock_chart, mock_reddit, mock_history):
        mock_history.return_value = pd.DataFrame(
            {"Close": [100, 110]},
            index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
        )
        mock_reddit.return_value = [{"title": "AAPL Good"}]
        mock_chart.return_value = b"fake_image_bytes"
        self.set_model_response('{"signal": "BUY", "confidence": 0.9, "reason": "Strong chart"}')

        result = self.analyst.analyze_stock("AAPL")

        mock_history.assert_called()
        mock_chart.assert_called()
        self.model.generate_content.assert_called()
        self.assertEqual(result["signal"], "BUY")
        self.assertEqual(result["confidence"], 0.9)
        self.assertIn("technical_summary", result)

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_ticker_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_tries_kr_symbol_candidates_for_numeric_ticker(
        self,
        mock_chart,
        mock_reddit,
        mock_history,
    ):
        mock_history.side_effect = [pd.DataFrame(), pd.DataFrame({"Close": [100, 110]})]
        mock_reddit.return_value = []
        mock_chart.return_value = b"fake_image_bytes"
        self.set_model_response('{"signal": "HOLD", "confidence": 0.5, "reason": "neutral"}')

        self.analyst.analyze_stock("317330")

        self.assertEqual(
            mock_history.call_args_list,
            [call("317330.KS", period="6mo"), call("317330.KQ", period="6mo")],
        )

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_ticker_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_tries_kr_symbol_candidates_for_alphanumeric_krx_ticker(
        self,
        mock_chart,
        mock_reddit,
        mock_history,
    ):
        mock_history.side_effect = [make_price_history(), pd.DataFrame(), pd.DataFrame()]
        mock_reddit.return_value = []
        mock_chart.return_value = b"fake_image_bytes"
        self.set_model_response('{"signal": "HOLD", "confidence": 0.5, "reason": "neutral"}')

        self.analyst.analyze_stock("0183J0")

        self.assertEqual(mock_history.call_args_list, [call("0183J0.KS", period="6mo")])

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_ticker_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_retries_with_next_kr_candidate_after_exception(
        self,
        mock_chart,
        mock_reddit,
        mock_history,
    ):
        mock_history.side_effect = [RuntimeError("boom"), pd.DataFrame({"Close": [100, 110]})]
        mock_reddit.return_value = []
        mock_chart.return_value = b"fake_image_bytes"
        self.set_model_response('{"signal": "BUY", "confidence": 0.7, "reason": "retry worked"}')

        result = self.analyst.analyze_stock("317330")

        self.assertEqual(result["signal"], "BUY")
        self.assertEqual(
            mock_history.call_args_list,
            [call("317330.KS", period="6mo"), call("317330.KQ", period="6mo")],
        )

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_ticker_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_prompt_includes_indicator_summary(self, mock_chart, mock_reddit, mock_history):
        mock_history.return_value = make_price_history(40)
        mock_reddit.return_value = []
        mock_chart.return_value = b"fake_image_bytes"
        self.set_model_response()

        self.analyst.analyze_stock("005930")

        prompt_text = self.model.generate_content.call_args.args[0][0]
        self.assertIn("RSI(14)", prompt_text)
        self.assertIn("MACD", prompt_text)
        self.assertIn('"key_drivers"', prompt_text)
        self.assertIn('"risk_factors"', prompt_text)

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_ticker_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_returns_default_explanation_lists(self, mock_chart, mock_reddit, mock_history):
        mock_history.return_value = make_price_history()
        mock_reddit.return_value = []
        mock_chart.return_value = b"fake_image_bytes"
        self.set_model_response()

        result = self.analyst.analyze_stock("005930")

        self.assertIn("market_context_summary", result)
        self.assertEqual(result["key_drivers"], [])
        self.assertEqual(result["risk_factors"], [])

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_ticker_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_excludes_social_source_when_reddit_has_no_posts(
        self,
        mock_chart,
        mock_reddit,
        mock_history,
    ):
        mock_history.return_value = make_price_history()
        mock_reddit.return_value = []
        mock_chart.return_value = b"fake_image_bytes"
        self.set_model_response()

        result = self.analyst.analyze_stock("005930")

        self.assertEqual(len(result["analysis_sources"]), 2)
        prompt_text = self.model.generate_content.call_args.args[0][0]
        self.assertIn("Reddit API", prompt_text)

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_ticker_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_includes_social_source_only_when_ticker_posts_exist(
        self,
        mock_chart,
        mock_reddit,
        mock_history,
    ):
        mock_history.return_value = make_price_history()
        mock_reddit.return_value = [
            {
                "ticker": "AAPL",
                "title": "AAPL breakout with strong volume",
                "body": "Raw discussion says valuation is rich but demand still looks resilient.",
                "score": 120,
                "num_comments": 34,
                "url": "https://reddit.com/r/stocks/example",
                "source": "r/stocks",
            }
        ]
        mock_chart.return_value = b"fake_image_bytes"
        self.set_model_response()

        result = self.analyst.analyze_stock("AAPL")

        self.assertEqual(len(result["analysis_sources"]), 3)
        prompt_text = self.model.generate_content.call_args.args[0][0]
        self.assertIn("Reddit", prompt_text)
        self.assertIn("AAPL breakout with strong volume", prompt_text)
        self.assertIn("Raw discussion says valuation is rich", prompt_text)
        self.assertNotIn("sentiment", prompt_text)

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_ticker_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_uses_configured_reddit_subreddit_limit_and_selected_ticker(
        self,
        mock_chart,
        mock_reddit,
        mock_history,
    ):
        mock_history.return_value = make_price_history()
        mock_reddit.return_value = []
        mock_chart.return_value = b"fake_image_bytes"
        self.set_model_response('{"signal": "HOLD", "confidence": 0.5, "reason": "neutral"}')

        with patch("src.analysis.multimodal.Config.REDDIT_SUBREDDIT", "wallstreetbets"), patch(
            "src.analysis.multimodal.Config.REDDIT_POST_LIMIT",
            3,
        ):
            self.analyst.analyze_stock("AAPL")

        mock_reddit.assert_called_once_with("AAPL", "wallstreetbets", limit=3)

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_ticker_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_passes_resolved_kr_ticker_to_reddit_search(
        self,
        mock_chart,
        mock_reddit,
        mock_history,
    ):
        mock_history.side_effect = [pd.DataFrame(), make_price_history()]
        mock_reddit.return_value = []
        mock_chart.return_value = b"fake_image_bytes"
        self.set_model_response('{"signal": "HOLD", "confidence": 0.5, "reason": "neutral"}')

        self.analyst.analyze_stock("317330")

        mock_reddit.assert_called_once_with("317330.KQ", "stocks", limit=5)

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_ticker_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_includes_news_source_only_when_news_exists(
        self,
        mock_chart,
        mock_reddit,
        mock_history,
    ):
        mock_history.return_value = make_price_history()
        mock_reddit.return_value = []
        self.mock_fetch_news.return_value = [
            {
                "title": "Apple shares rise after AI product report",
                "url": "https://m.stock.naver.com/worldstock/news/1",
                "source": "Naver Stock",
                "symbol": "AAPL",
            }
        ]
        mock_chart.return_value = b"fake_image_bytes"
        self.set_model_response()

        result = self.analyst.analyze_stock("AAPL")

        self.assertEqual(len(result["analysis_sources"]), 3)
        prompt_text = self.model.generate_content.call_args.args[0][0]
        self.assertIn("Apple shares rise after AI product report", prompt_text)
        self.assertIn("https://m.stock.naver.com/worldstock/news/1", prompt_text)

    @patch("src.analysis.market_data.MarketDataFetcher.fetch_history")
    @patch("src.data.social.RedditScraper.fetch_ticker_posts")
    @patch("src.analysis.chart.ChartGenerator.generate_chart")
    def test_analyze_stock_uses_configured_news_limit(self, mock_chart, mock_reddit, mock_history):
        mock_history.return_value = make_price_history()
        mock_reddit.return_value = []
        mock_chart.return_value = b"fake_image_bytes"
        self.set_model_response('{"signal": "HOLD", "confidence": 0.5, "reason": "neutral"}')

        with patch("src.analysis.multimodal.Config.DEEP_ANALYSIS_NEWS_LIMIT", 4):
            self.analyst.analyze_stock("AAPL")

        self.mock_fetch_news.assert_called_with("AAPL", limit=4)


if __name__ == "__main__":
    unittest.main()
