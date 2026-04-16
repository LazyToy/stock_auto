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
        
    def test_fetch_posts(self):
        """게시글 수집 테스트"""
        # Mock subreddit and posts
        mock_subreddit = MagicMock()
        mock_post = MagicMock()
        mock_post.title = "Apple is going to the moon! AAPL buy buy buy"
        mock_post.score = 100
        mock_post.created_utc = 1700000000
        mock_post.url = "http://reddit.com/r/stocks/1"
        
        # Configure mock chain
        # self.scraper.reddit is the Mock object created by patch
        self.scraper.reddit.subreddit.return_value = mock_subreddit
        mock_subreddit.hot.return_value = [mock_post]
        
        posts = self.scraper.fetch_hot_posts("stocks", limit=1)
        self.assertEqual(len(posts), 1)
        self.assertIn("Apple", posts[0]['title'])

    def test_sentiment_analysis(self):
        """간단한 감성 분석 테스트"""
        text = "This stock is trash, selling everything. Crash coming."
        score = self.scraper.analyze_sentiment(text)
        self.assertLess(score, 0) # Should be negative
        
        text2 = "Amazing earnings! To the moon! Buy!"
        score2 = self.scraper.analyze_sentiment(text2)
        self.assertGreater(score2, 0) # Should be positive

if __name__ == '__main__':
    unittest.main()
