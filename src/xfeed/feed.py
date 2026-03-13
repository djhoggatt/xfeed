from __future__ import annotations

from xfeed.models import FeedMode, TweetView
from xfeed.providers.base import FeedProvider


class FeedController:
    def __init__(
        self,
        provider: FeedProvider,
        *,
        mode: FeedMode = FeedMode.FOLLOWING,
        page_size: int = 20,
    ) -> None:
        self.provider = provider
        self.mode = mode
        self.page_size = page_size
        self.tweets: list[TweetView] = []
        self._tweet_ids: set[str] = set()
        self._seen_tweet_ids: list[str] = []
        self.next_cursor: str | None = None

    async def load_initial(self) -> list[TweetView]:
        if self.tweets:
            return self.tweets
        await self._load_page(reset=True)
        return self.tweets

    async def load_more(self) -> int:
        if self.next_cursor is None and self.tweets:
            return 0
        before = len(self.tweets)
        await self._load_page(reset=False)
        return len(self.tweets) - before

    async def refresh(self) -> int:
        page = await self.provider.fetch_home(
            self.mode,
            cursor=None,
            count=self.page_size,
            seen_tweet_ids=self._recent_seen_ids(),
        )
        new_items = [tweet for tweet in page.tweets if tweet.id not in self._tweet_ids]
        if not new_items:
            return 0
        for tweet in reversed(new_items):
            self._remember(tweet)
        self.tweets = new_items + self.tweets
        return len(new_items)

    async def switch_mode(self, mode: FeedMode) -> None:
        self.mode = mode
        self.reset()
        await self.load_initial()

    def reset(self) -> None:
        self.tweets.clear()
        self._tweet_ids.clear()
        self._seen_tweet_ids.clear()
        self.next_cursor = None

    async def fetch_tweet(self, tweet_id: str) -> TweetView:
        return await self.provider.fetch_tweet(tweet_id)

    async def _load_page(self, *, reset: bool) -> None:
        page = await self.provider.fetch_home(
            self.mode,
            cursor=None if reset else self.next_cursor,
            count=self.page_size,
            seen_tweet_ids=self._recent_seen_ids(),
        )
        if reset:
            self.reset()
        new_items = [tweet for tweet in page.tweets if tweet.id not in self._tweet_ids]
        for tweet in new_items:
            self._remember(tweet)
        self.tweets.extend(new_items)
        self.next_cursor = page.next_cursor

    def _remember(self, tweet: TweetView) -> None:
        if tweet.id in self._tweet_ids:
            return
        self._tweet_ids.add(tweet.id)
        self._seen_tweet_ids.append(tweet.id)

    def _recent_seen_ids(self) -> list[str]:
        return self._seen_tweet_ids[-200:]
