from __future__ import annotations

from typing import Any

from xfeed.models import FeedMode, FeedPage, MediaItem, TweetView
from xfeed.providers.base import FeedProvider, ProviderError

try:
    from twikit import Client
except ImportError:  # pragma: no cover - exercised only when dependency is missing
    Client = None


class TwikitProvider(FeedProvider):
    def __init__(self, cookies: dict[str, str], *, language: str = "en-US") -> None:
        self._cookies = dict(cookies)
        self._language = language
        self._client = None

    async def fetch_home(
        self,
        mode: FeedMode,
        *,
        cursor: str | None,
        count: int,
        seen_tweet_ids: list[str] | None = None,
    ) -> FeedPage:
        client = self._get_client()
        if mode is FeedMode.FOLLOWING:
            result = await client.get_latest_timeline(
                count=count,
                cursor=cursor,
                seen_tweet_ids=seen_tweet_ids,
            )
        else:
            result = await client.get_timeline(
                count=count,
                cursor=cursor,
                seen_tweet_ids=seen_tweet_ids,
            )
        tweets = [self._normalize_tweet(tweet) for tweet in result]
        return FeedPage(tweets=tweets, next_cursor=getattr(result, "next_cursor", None))

    async def fetch_tweet(self, tweet_id: str) -> TweetView:
        client = self._get_client()
        tweet = await client.get_tweet_by_id(tweet_id)
        return self._normalize_tweet(tweet)

    def _get_client(self):
        if Client is None:
            raise ProviderError(
                "twikit is not installed. Install project dependencies first."
            )
        if self._client is None:
            client = Client(language=self._language)
            client.set_cookies(self._cookies, clear_cookies=True)
            self._client = client
        return self._client

    def _normalize_tweet(self, tweet: Any) -> TweetView:
        quoted = getattr(tweet, "quote", None)
        if quoted is None:
            quoted = getattr(tweet, "quoted_tweet", None)
        normalized_quote = self._normalize_tweet(quoted) if quoted is not None else None

        retweeted = getattr(tweet, "retweeted_tweet", None)
        retweeted_by = None
        normalized_target = tweet
        if retweeted is not None:
            normalized_target = retweeted
            user = getattr(tweet, "user", None)
            if user is not None:
                screen_name = str(getattr(user, "screen_name", "")).strip()
                if screen_name:
                    retweeted_by = f"@{screen_name}"

        media_items: list[MediaItem] = []
        for media in getattr(normalized_target, "media", []) or []:
            original_info = getattr(media, "original_info", None) or {}
            media_items.append(
                MediaItem(
                    url=getattr(media, "media_url", "") or getattr(media, "url", ""),
                    kind=str(getattr(media, "type", "unknown")),
                    display_url=getattr(media, "display_url", None),
                    width=original_info.get("width"),
                    height=original_info.get("height"),
                )
            )

        author = getattr(normalized_target, "user", None)
        author_name = getattr(author, "name", "Unknown user")
        author_handle = getattr(author, "screen_name", "unknown")
        tweet_id = str(getattr(normalized_target, "id", ""))
        text = getattr(normalized_target, "text", None)
        if text is None:
            text = getattr(normalized_target, "full_text", "")
        return TweetView(
            id=tweet_id,
            author_name=author_name,
            author_handle=author_handle,
            text=(text or "").strip(),
            created_at=str(getattr(normalized_target, "created_at", "")),
            url=f"https://x.com/{author_handle}/status/{tweet_id}",
            reply_count=int(getattr(normalized_target, "reply_count", 0) or 0),
            retweet_count=int(getattr(normalized_target, "retweet_count", 0) or 0),
            like_count=int(getattr(normalized_target, "favorite_count", 0) or 0),
            quote_count=int(getattr(normalized_target, "quote_count", 0) or 0),
            lang=getattr(normalized_target, "lang", None),
            media=media_items,
            quoted_tweet=normalized_quote,
            retweeted_by=retweeted_by,
            in_reply_to=getattr(normalized_target, "in_reply_to", None),
        )
