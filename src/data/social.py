import logging
import re
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


def _text_attr(obj: Any, name: str) -> str:
    value = getattr(obj, name, "")
    return value if isinstance(value, str) else ""


def _number_attr(obj: Any, name: str, default: int | float = 0) -> int | float:
    value = getattr(obj, name, default)
    return value if isinstance(value, (int, float)) else default


def _ticker_search_variants(ticker: str) -> list[str]:
    cleaned = (ticker or "").strip().upper()
    if not cleaned:
        return []

    variants = [cleaned]
    base_symbol = cleaned.split(".", 1)[0]
    if base_symbol and base_symbol != cleaned:
        variants.append(base_symbol)
    if base_symbol.isalpha():
        variants.append(f"${base_symbol}")

    deduped = []
    for variant in variants:
        if variant and variant not in deduped:
            deduped.append(variant)
    return deduped


def _contains_ticker_token(text: str, variant: str) -> bool:
    normalized_text = text.upper()
    normalized_variant = variant.upper()

    if normalized_variant.startswith("$"):
        pattern = rf"(?<![A-Z0-9]){re.escape(normalized_variant)}(?![A-Z0-9])"
        return re.search(pattern, normalized_text) is not None

    if normalized_variant.isalpha() and len(normalized_variant) <= 2:
        pattern = rf"(?<![A-Z0-9])\${re.escape(normalized_variant)}(?![A-Z0-9])"
        return re.search(pattern, normalized_text) is not None

    pattern = rf"(?<![A-Z0-9$])\$?{re.escape(normalized_variant)}(?![A-Z0-9])"
    return re.search(pattern, normalized_text) is not None


def _post_matches_ticker(post: Any, variants: list[str]) -> bool:
    haystack = " ".join(
        [
            _text_attr(post, "title"),
            _text_attr(post, "selftext"),
            _text_attr(post, "url"),
            _text_attr(post, "permalink"),
        ]
    )
    return any(_contains_ticker_token(haystack, variant) for variant in variants)


def _post_to_dict(post: Any, subreddit_name: str, ticker: str | None = None) -> Dict[str, Any]:
    url = _text_attr(post, "url")
    permalink = _text_attr(post, "permalink")
    if not url and permalink:
        url = f"https://www.reddit.com{permalink}"

    item = {
        "title": _text_attr(post, "title"),
        "body": _text_attr(post, "selftext"),
        "score": _number_attr(post, "score"),
        "num_comments": _number_attr(post, "num_comments"),
        "url": url,
        "created_utc": _number_attr(post, "created_utc"),
        "source": f"r/{subreddit_name}",
    }
    if ticker is not None:
        item["ticker"] = ticker
    return item


class RedditScraper:
    """Reddit 원문 데이터 수집기"""
    
    def __init__(self, client_id: str = None, client_secret: str = None, user_agent: str = None):
        self.client_id = Config.REDDIT_CLIENT_ID if client_id is None else client_id
        self.client_secret = Config.REDDIT_CLIENT_SECRET if client_secret is None else client_secret
        self.user_agent = Config.REDDIT_USER_AGENT if user_agent is None else user_agent
        
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

    @property
    def is_available(self) -> bool:
        """Reddit API 클라이언트가 실제 수집에 사용할 수 있는 상태인지 반환한다."""
        return self.reddit is not None

    def fetch_hot_posts(self, subreddit_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """특정 서브레딧의 Hot 게시글 수집"""
        if not self.is_available:
            return []
            
        posts = []
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            for post in subreddit.hot(limit=limit):
                posts.append(_post_to_dict(post, subreddit_name))
        except Exception as e:
            logger.error(f"Reddit 수집 실패 ({subreddit_name}): {e}")
            
        return posts

    def fetch_ticker_posts(
        self,
        ticker: str,
        subreddit_name: str,
        limit: int = 10,
        sort: str | None = None,
        time_filter: str | None = None,
    ) -> List[Dict[str, Any]]:
        """Search Reddit for posts that explicitly mention the requested ticker."""
        if not self.is_available:
            return []

        variants = _ticker_search_variants(ticker)
        if not variants:
            return []

        query = " OR ".join(variants)
        search_sort = sort or Config.REDDIT_SEARCH_SORT
        search_time_filter = time_filter or Config.REDDIT_SEARCH_TIME_FILTER

        posts = []
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            for post in subreddit.search(
                query,
                sort=search_sort,
                time_filter=search_time_filter,
                limit=limit,
            ):
                if not _post_matches_ticker(post, variants):
                    continue
                posts.append(
                    _post_to_dict(post, subreddit_name, ticker=(ticker or "").strip().upper())
                )
        except Exception as e:
            logger.error(f"Reddit ticker search failed ({ticker}, {subreddit_name}): {e}")

        return posts


if __name__ == "__main__":
    scraper = RedditScraper()
    print(f"Reddit available: {scraper.is_available}")
