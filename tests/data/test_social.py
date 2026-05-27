import unittest
from unittest.mock import MagicMock, patch
from src.data.social import RedditScraper

class TestRedditScraper(unittest.TestCase):
    def setUp(self):
        # Patch praw.Reddit class to avoid real network calls
        self.patcher = patch('src.data.social.praw.Reddit')
        self.MockReddit = self.patcher.start()
        self.scraper = RedditScraper(client_id="dummy", client_secret="dummy")

    def tearDown(self):
        self.patcher.stop()

    def test_initialization(self):
        """초기화 테스트"""
        self.assertIsNotNone(self.scraper.reddit)
        self.assertTrue(self.scraper.is_available)

    def test_unconfigured_scraper_does_not_create_reddit_client(self):
        """API 키가 없으면 Reddit 클라이언트를 만들지 않고 빈 결과만 반환해야 한다."""
        scraper = RedditScraper(client_id="", client_secret="")

        self.MockReddit.assert_called_once()
        self.assertFalse(scraper.is_available)
        self.assertIsNone(scraper.reddit)
        self.assertEqual(scraper.fetch_hot_posts("stocks", limit=1), [])
        self.assertEqual(scraper.fetch_ticker_posts("AAPL", "stocks", limit=1), [])
        
    def test_fetch_posts(self):
        """게시글 수집 테스트"""
        # Mock subreddit and posts
        mock_subreddit = MagicMock()
        mock_post = MagicMock()
        mock_post.title = "Apple is going to the moon! AAPL buy buy buy"
        mock_post.selftext = "I am watching the next earnings call and unusual options volume."
        mock_post.score = 100
        mock_post.num_comments = 25
        mock_post.created_utc = 1700000000
        mock_post.url = "http://reddit.com/r/stocks/1"
        
        # Configure mock chain
        # self.scraper.reddit is the Mock object created by patch
        self.scraper.reddit.subreddit.return_value = mock_subreddit
        mock_subreddit.hot.return_value = [mock_post]
        
        posts = self.scraper.fetch_hot_posts("stocks", limit=1)
        self.assertEqual(len(posts), 1)
        self.assertIn("Apple", posts[0]['title'])
        self.assertIn("earnings call", posts[0]["body"])
        self.assertEqual(posts[0]["num_comments"], 25)
        self.assertEqual(posts[0]["source"], "r/stocks")
        self.assertNotIn("sentiment", posts[0])

    def test_fetch_ticker_posts_searches_for_ticker_and_filters_unrelated_posts(self):
        mock_subreddit = MagicMock()
        related_post = MagicMock()
        related_post.title = "AAPL breakout after earnings"
        related_post.selftext = "Options traders are debating $AAPL valuation."
        related_post.score = 120
        related_post.num_comments = 32
        related_post.created_utc = 1700000000
        related_post.url = "https://reddit.com/r/stocks/related"

        unrelated_post = MagicMock()
        unrelated_post.title = "Broad market rotation into energy"
        unrelated_post.selftext = "Discussion is about XOM and CVX only."
        unrelated_post.score = 80
        unrelated_post.num_comments = 18
        unrelated_post.created_utc = 1700000100
        unrelated_post.url = "https://reddit.com/r/stocks/unrelated"

        self.scraper.reddit.subreddit.return_value = mock_subreddit
        mock_subreddit.search.return_value = [related_post, unrelated_post]

        posts = self.scraper.fetch_ticker_posts("AAPL", "stocks", limit=5)

        mock_subreddit.search.assert_called_once()
        query = mock_subreddit.search.call_args.args[0]
        self.assertIn("AAPL", query)
        self.assertIn("$AAPL", query)
        self.assertEqual(mock_subreddit.search.call_args.kwargs["limit"], 5)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["title"], "AAPL breakout after earnings")
        self.assertEqual(posts[0]["ticker"], "AAPL")
        self.assertEqual(posts[0]["source"], "r/stocks")

    def test_fetch_ticker_posts_uses_symbol_without_exchange_suffix_as_search_variant(self):
        mock_subreddit = MagicMock()
        mock_post = MagicMock()
        mock_post.title = "005930.KS earnings discussion"
        mock_post.selftext = "Samsung Electronics investors are watching memory prices."
        mock_post.score = 90
        mock_post.num_comments = 11
        mock_post.created_utc = 1700000200
        mock_post.url = "https://reddit.com/r/stocks/samsung"

        self.scraper.reddit.subreddit.return_value = mock_subreddit
        mock_subreddit.search.return_value = [mock_post]

        posts = self.scraper.fetch_ticker_posts("005930.KS", "stocks", limit=3)

        query = mock_subreddit.search.call_args.args[0]
        self.assertIn("005930.KS", query)
        self.assertIn("005930", query)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["ticker"], "005930.KS")

    def test_scraper_has_no_keyword_sentiment_analyzer(self):
        """소셜 감성 판단은 키워드 규칙이 아니라 리포트 생성 단계에서 수행한다."""
        self.assertFalse(hasattr(self.scraper, "analyze_sentiment"))

if __name__ == '__main__':
    unittest.main()
