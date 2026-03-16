from __future__ import annotations

import re
from typing import Any

from xfeed.models import FeedMode, FeedPage, MediaItem, TweetView, UserTweetType
from xfeed.providers.base import FeedProvider, ProviderError

try:
    from twikit import Client
except ImportError:  # pragma: no cover - exercised only when dependency is missing
    Client = None


STATUS_URL_RE = re.compile(
    r"https?://(?:(?:www\.)?(?:x|twitter)\.com)/[^/\s]+/status/(\d+)",
    re.IGNORECASE,
)


class TwikitProvider(FeedProvider):
    def __init__(self, cookies: dict[str, str], *, language: str = "en-US") -> None:
        self._cookies = dict(cookies)
        self._language = language
        self._client = None
        self._user_cache: dict[str, Any] = {}

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
        tweets = [await self._normalize_tweet(tweet, client=client) for tweet in result]
        return FeedPage(tweets=tweets, next_cursor=getattr(result, "next_cursor", None))

    async def fetch_tweet(self, tweet_id: str) -> TweetView:
        client = self._get_client()
        tweet = await client.get_tweet_by_id(tweet_id)
        return await self._normalize_tweet(tweet, client=client)

    async def fetch_user_timeline(
        self,
        screen_name: str,
        tweet_type: UserTweetType,
        *,
        cursor: str | None,
        count: int,
    ) -> FeedPage:
        client = self._get_client()
        user = await self._get_user_by_screen_name(screen_name, client=client)
        result = await client.get_user_tweets(
            str(getattr(user, "id")),
            tweet_type=tweet_type.to_twikit_type(),
            count=count,
            cursor=cursor,
        )
        tweets = [await self._normalize_tweet(tweet, client=client) for tweet in result]
        return FeedPage(tweets=tweets, next_cursor=getattr(result, "next_cursor", None))

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

    async def _get_user_by_screen_name(self, screen_name: str, *, client: Any) -> Any:
        normalized = screen_name.strip().lstrip("@").lower()
        if not normalized:
            raise ProviderError("User screen name cannot be empty.")
        cached = self._user_cache.get(normalized)
        if cached is not None:
            return cached
        user = await client.get_user_by_screen_name(normalized)
        self._user_cache[normalized] = user
        return user

    async def _normalize_tweet(
        self,
        tweet: Any,
        *,
        client: Any | None,
        seen_ids: set[str] | None = None,
    ) -> TweetView:
        seen_ids = set() if seen_ids is None else set(seen_ids)
        quoted = getattr(tweet, "quote", None)
        if quoted is None:
            quoted = getattr(tweet, "quoted_tweet", None)

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
        next_seen_ids = seen_ids | ({tweet_id} if tweet_id else set())
        normalized_quote = None
        if quoted is not None:
            quote_id = str(getattr(quoted, "id", ""))
            if not quote_id or quote_id not in seen_ids:
                normalized_quote = await self._normalize_tweet(
                    quoted,
                    client=client,
                    seen_ids=next_seen_ids,
                )
        elif client is not None:
            linked_quote_id = self._extract_linked_quote_id(tweet, normalized_target)
            if linked_quote_id and linked_quote_id not in next_seen_ids:
                try:
                    linked_quote = await client.get_tweet_by_id(linked_quote_id)
                except Exception:
                    linked_quote = None
                if linked_quote is not None:
                    normalized_quote = await self._normalize_tweet(
                        linked_quote,
                        client=client,
                        seen_ids=next_seen_ids,
                    )
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

    def _extract_linked_quote_id(self, *tweet_candidates: Any) -> str | None:
        seen_objects: set[int] = set()
        for candidate in tweet_candidates:
            match = self._find_status_id(candidate, seen_objects, depth=0)
            if match is not None:
                return match
        return None

    def _find_status_id(
        self,
        value: Any,
        seen_objects: set[int],
        *,
        depth: int,
    ) -> str | None:
        if value is None or depth > 10:
            return None
        if isinstance(value, str):
            match = STATUS_URL_RE.search(value)
            return match.group(1) if match is not None else None
        if isinstance(value, (int, float, bool, bytes)):
            return None

        object_id = id(value)
        if object_id in seen_objects:
            return None
        seen_objects.add(object_id)

        if isinstance(value, dict):
            for key in ("expanded_url", "url", "display_url"):
                match = self._find_status_id(value.get(key), seen_objects, depth=depth + 1)
                if match is not None:
                    return match
            for item in value.values():
                match = self._find_status_id(item, seen_objects, depth=depth + 1)
                if match is not None:
                    return match
            return None
        if isinstance(value, (list, tuple, set)):
            for item in value:
                match = self._find_status_id(item, seen_objects, depth=depth + 1)
                if match is not None:
                    return match
            return None

        for attr in (
            "expanded_url",
            "url",
            "display_url",
            "entities",
            "urls",
            "note_tweet",
            "quoted_status_permalink",
            "legacy",
            "binding_values",
            "text",
            "full_text",
        ):
            match = self._find_status_id(
                getattr(value, attr, None),
                seen_objects,
                depth=depth + 1,
            )
            if match is not None:
                return match

        try:
            members = vars(value)
        except TypeError:
            return None
        for item in members.values():
            match = self._find_status_id(item, seen_objects, depth=depth + 1)
            if match is not None:
                return match
        return None
