import logging
from types import SimpleNamespace
from typing import List, Dict, Any
from src.config import Config

logger = logging.getLogger("SocialScraper")

try:
    import praw
except ImportError:  # pragma: no cover - depends on the local runtime image
    class _MissingPrawReddit:
        def __init__(self, *args, **kwargs):
            raise ImportError("praw is not installed")

    praw = SimpleNamespace(Reddit=_MissingPrawReddit)

class RedditScraper:
    """Reddit 데이터 수집 및 감성 분석기"""
    
    def __init__(self, client_id: str = None, client_secret: str = None, user_agent: str = None):
        self.client_id = client_id or Config.REDDIT_CLIENT_ID
        self.client_secret = client_secret or Config.REDDIT_CLIENT_SECRET
        self.user_agent = user_agent or Config.REDDIT_USER_AGENT
        
        self.reddit = None
        if self.client_id and self.client_secret:
            try:
                self.reddit = praw.Reddit(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    user_agent=self.user_agent
                )
                logger.info("Reddit API 클라이언트 초기화 완료")
            except Exception as e:
                logger.warning(f"Reddit API 초기화 실패: {e}")
        else:
            logger.info("Reddit API 키가 설정되지 않았습니다. 소셜 분석 기능이 제한됩니다.")

    def fetch_hot_posts(self, subreddit_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """특정 서브레딧의 Hot 게시글 수집"""
        if not self.reddit:
            return []
            
        posts = []
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            for post in subreddit.hot(limit=limit):
                posts.append({
                    'title': post.title,
                    'score': post.score,
                    'url': post.url,
                    'created_utc': post.created_utc,
                    'sentiment': self.analyze_sentiment(post.title)
                })
        except Exception as e:
            logger.error(f"Reddit 수집 실패 ({subreddit_name}): {e}")
            
        return posts

    def analyze_sentiment(self, text: str) -> float:
        """간단한 키워드 기반 감성 분석 (MVP)"""
        # 긍정 키워드
        positive_keywords = [
            "moon", "buy", "long", "bull", "calls", "rocket", "gem", 
            "breakout", "high", "profit", "gain", "up", "soar"
        ]
        # 부정 키워드
        negative_keywords = [
            "crash", "sell", "short", "bear", "puts", "drop", "loss", 
            "down", "plummet", "tank", "trash", "scam", "avoid"
        ]
        
        text_lower = text.lower()
        score = 0
        
        for kw in positive_keywords:
            if kw in text_lower:
                score += 1
                
        for kw in negative_keywords:
            if kw in text_lower:
                score -= 1
                
        # Normalize to range -1.0 to 1.0 (approx)
        # Assuming typical max matches around 5
        return max(-1.0, min(1.0, score / 3.0))

if __name__ == "__main__":
    # Test
    scraper = RedditScraper()
    print(scraper.analyze_sentiment("Buy AAPL! It's going to the moon!"))
