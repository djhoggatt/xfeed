from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class FeedMode(StrEnum):
    FOLLOWING = "following"
    FOR_YOU = "for-you"

    @classmethod
    def from_cli(cls, value: str) -> "FeedMode":
        normalized = value.strip().lower()
        if normalized == cls.FOLLOWING.value:
            return cls.FOLLOWING
        if normalized == cls.FOR_YOU.value:
            return cls.FOR_YOU
        raise ValueError(f"Unsupported feed mode: {value}")


@dataclass(slots=True)
class MediaItem:
    url: str
    kind: str
    display_url: str | None = None
    width: int | None = None
    height: int | None = None


@dataclass(slots=True)
class TweetView:
    id: str
    author_name: str
    author_handle: str
    text: str
    created_at: str
    url: str
    reply_count: int = 0
    retweet_count: int = 0
    like_count: int = 0
    quote_count: int = 0
    lang: str | None = None
    media: list[MediaItem] = field(default_factory=list)
    quoted_tweet: "TweetView | None" = None
    retweeted_by: str | None = None
    in_reply_to: str | None = None


@dataclass(slots=True)
class FeedPage:
    tweets: list[TweetView]
    next_cursor: str | None = None
