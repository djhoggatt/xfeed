from __future__ import annotations

from abc import ABC, abstractmethod

from xfeed.models import FeedMode, FeedPage, TweetView


class ProviderError(RuntimeError):
    """Raised when the underlying X provider fails."""


class FeedProvider(ABC):
    @abstractmethod
    async def fetch_home(
        self,
        mode: FeedMode,
        *,
        cursor: str | None,
        count: int,
        seen_tweet_ids: list[str] | None = None,
    ) -> FeedPage:
        raise NotImplementedError

    @abstractmethod
    async def fetch_tweet(self, tweet_id: str) -> TweetView:
        raise NotImplementedError
