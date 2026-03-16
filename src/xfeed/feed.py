from __future__ import annotations

from xfeed.models import FeedMode, TweetView, UserTweetType
from xfeed.providers.base import FeedProvider


class FeedController:
    def __init__(
        self,
        provider: FeedProvider,
        *,
        mode: FeedMode | None = FeedMode.FOLLOWING,
        user_screen_name: str | None = None,
        user_tweet_type: UserTweetType = UserTweetType.POSTS,
        page_size: int = 20,
    ) -> None:
        if (mode is None) == (user_screen_name is None):
            raise ValueError("Specify either a home mode or a user timeline target.")
        self.provider = provider
        self.mode = mode
        self.user_screen_name = (
            self._normalize_screen_name(user_screen_name)
            if user_screen_name is not None
            else None
        )
        self.user_tweet_type = user_tweet_type
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
        page = await self._fetch_page(cursor=None, seen_tweet_ids=self._recent_seen_ids())
        new_items = [tweet for tweet in page.tweets if tweet.id not in self._tweet_ids]
        if not new_items:
            return 0
        for tweet in reversed(new_items):
            self._remember(tweet)
        self.tweets = new_items + self.tweets
        return len(new_items)

    async def switch_mode(self, mode: FeedMode) -> None:
        if not self.is_home_timeline:
            raise ValueError("Home mode is only available for the home timeline.")
        self.mode = mode
        self.reset()
        await self.load_initial()

    async def switch_user_tweet_type(self, tweet_type: UserTweetType) -> None:
        if self.is_home_timeline:
            raise ValueError("User feed types are only available for user timelines.")
        self.user_tweet_type = tweet_type
        self.reset()
        await self.load_initial()

    async def toggle_view(self) -> str:
        if self.is_home_timeline:
            next_mode = (
                FeedMode.FOR_YOU
                if self.mode is FeedMode.FOLLOWING
                else FeedMode.FOLLOWING
            )
            await self.switch_mode(next_mode)
            return next_mode.value
        next_tweet_type = self.user_tweet_type.next()
        await self.switch_user_tweet_type(next_tweet_type)
        return next_tweet_type.value

    def reset(self) -> None:
        self.tweets.clear()
        self._tweet_ids.clear()
        self._seen_tweet_ids.clear()
        self.next_cursor = None

    async def fetch_tweet(self, tweet_id: str) -> TweetView:
        return await self.provider.fetch_tweet(tweet_id)

    async def _load_page(self, *, reset: bool) -> None:
        page = await self._fetch_page(
            cursor=None if reset else self.next_cursor,
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

    async def _fetch_page(
        self,
        *,
        cursor: str | None,
        seen_tweet_ids: list[str] | None,
    ):
        if self.is_home_timeline:
            return await self.provider.fetch_home(
                self.mode,
                cursor=cursor,
                count=self.page_size,
                seen_tweet_ids=seen_tweet_ids,
            )
        return await self.provider.fetch_user_timeline(
            self.user_screen_name or "",
            self.user_tweet_type,
            cursor=cursor,
            count=self.page_size,
        )

    @property
    def is_home_timeline(self) -> bool:
        return self.mode is not None

    @property
    def title(self) -> str:
        if self.is_home_timeline:
            return self.mode.value
        return f"@{self.user_screen_name} · {self.user_tweet_type.value}"

    @property
    def status_label(self) -> str:
        if self.is_home_timeline:
            return self.mode.value
        return f"@{self.user_screen_name} {self.user_tweet_type.value}"

    @property
    def toggle_label(self) -> str:
        return "mode" if self.is_home_timeline else "feed"

    def _normalize_screen_name(self, value: str | None) -> str:
        normalized = (value or "").strip()
        if normalized.startswith("@"):
            normalized = normalized[1:]
        if not normalized:
            raise ValueError("User screen name cannot be empty.")
        return normalized
