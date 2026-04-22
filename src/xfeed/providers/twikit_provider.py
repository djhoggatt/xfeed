from __future__ import annotations

import json
import re
from typing import Any

from xfeed.models import FeedMode, FeedPage, MediaItem, TweetView, UserTweetType
from xfeed.providers.base import FeedProvider, ProviderError

_USER_LEGACY_DEFAULTS: dict[str, Any] = {
    "created_at": "",
    "name": "",
    "screen_name": "",
    "profile_image_url_https": "",
    "location": "",
    "description": "",
    "verified": False,
    "possibly_sensitive": False,
    "can_dm": False,
    "can_media_tag": False,
    "want_retweets": False,
    "default_profile": False,
    "default_profile_image": False,
    "has_custom_timelines": False,
    "followers_count": 0,
    "fast_followers_count": 0,
    "normal_followers_count": 0,
    "friends_count": 0,
    "favourites_count": 0,
    "listed_count": 0,
    "media_count": 0,
    "statuses_count": 0,
    "is_translator": False,
    "translator_type": "",
    "withheld_in_countries": [],
    "pinned_tweet_ids_str": [],
}


def _patch_twikit_users() -> None:
    """Patch twikit User constructors to tolerate missing fields in API responses.

    X/Twitter occasionally omits fields from legacy user objects. Twikit uses
    bare dict access for most of them, so we pre-fill defaults before the
    original __init__ runs. This survives pip/pipx reinstalls because it lives
    in xfeed's code rather than in twikit's installed files.
    """
    try:
        import twikit.user as _u
        import twikit.guest.user as _gu
    except ImportError:
        return
    for cls in (_u.User, _gu.User):
        _wrap_user_init(cls)


def _wrap_user_init(cls: Any) -> None:
    original = cls.__init__
    if getattr(original, "_xfeed_patched", False):
        return

    def _safe_init(self: Any, client: Any, data: dict) -> None:
        data = dict(data)
        legacy = dict(data.get("legacy") or {})
        for key, default in _USER_LEGACY_DEFAULTS.items():
            if key not in legacy:
                legacy[key] = default
        entities = dict(legacy.get("entities") or {})
        desc = dict(entities.get("description") or {})
        if "urls" not in desc:
            desc["urls"] = []
        entities["description"] = desc
        legacy["entities"] = entities
        if "is_blue_verified" not in data:
            data["is_blue_verified"] = False
        data["legacy"] = legacy
        original(self, client, data)

    _safe_init._xfeed_patched = True  # type: ignore[attr-defined]
    cls.__init__ = _safe_init


try:
    from twikit import Client
    from twikit.errors import (
        AccountLocked,
        AccountSuspended,
        BadRequest,
        Forbidden,
        NotFound,
        RequestTimeout,
        ServerError,
        TooManyRequests,
        TwitterException,
        Unauthorized,
    )
    from twikit.tweet import tweet_from_data
    from twikit.utils import find_dict
    _patch_twikit_users()
except ImportError:  # pragma: no cover - exercised only when dependency is missing
    Client = None
    AccountLocked = None
    AccountSuspended = None
    BadRequest = None
    Forbidden = None
    NotFound = None
    RequestTimeout = None
    ServerError = None
    TooManyRequests = None
    TwitterException = None
    Unauthorized = None
    tweet_from_data = None
    find_dict = None


STATUS_URL_RE = re.compile(
    r"https?://(?:(?:www\.)?(?:x|twitter)\.com)/[^/\s]+/status/(\d+)",
    re.IGNORECASE,
)
KEY_BYTE_INDICES_ERROR = "Couldn't get KEY_BYTE indices"


def _is_key_byte_indices_error(exc: Exception) -> bool:
    return KEY_BYTE_INDICES_ERROR in str(exc)


def _cookie_mapping_from_jar(client: Any) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for cookie in client.http.cookies.jar:
        cookies[str(cookie.name)] = str(cookie.value)
    return cookies


async def _request_without_transaction(
    client: Any,
    method: str,
    url: str,
    *,
    auto_unlock: bool,
    raise_exception: bool,
    **kwargs: Any,
) -> tuple[dict[str, Any] | Any, Any]:
    headers = kwargs.pop("headers", {})
    cookies_backup = _cookie_mapping_from_jar(client)
    response = await client.http.request(method, url, headers=headers, **kwargs)
    client._remove_duplicate_ct0_cookie()

    try:
        response_data = response.json()
    except json.decoder.JSONDecodeError:
        response_data = response.text

    if isinstance(response_data, dict) and response_data.get("errors"):
        error_code = response_data["errors"][0].get("code")
        error_message = response_data["errors"][0].get("message")
        if error_code in (37, 64):
            raise AccountSuspended(error_message)

        if error_code == 326:
            if client.captcha_solver is None:
                raise AccountLocked(
                    "Your account is locked. Visit "
                    "https://x.com/account/access to unlock it."
                )
            if auto_unlock:
                await client.unlock()
                client.set_cookies(cookies_backup, clear_cookies=True)
                response = await client.http.request(method, url, **kwargs)
                client._remove_duplicate_ct0_cookie()
                try:
                    response_data = response.json()
                except json.decoder.JSONDecodeError:
                    response_data = response.text

    status_code = response.status_code
    if status_code >= 400 and raise_exception:
        message = f'status: {status_code}, message: "{response.text}"'
        if status_code == 400:
            raise BadRequest(message, headers=response.headers)
        if status_code == 401:
            raise Unauthorized(message, headers=response.headers)
        if status_code == 403:
            raise Forbidden(message, headers=response.headers)
        if status_code == 404:
            raise NotFound(message, headers=response.headers)
        if status_code == 408:
            raise RequestTimeout(message, headers=response.headers)
        if status_code == 429:
            if await client._get_user_state() == "suspended":
                raise AccountSuspended(message, headers=response.headers)
            raise TooManyRequests(message, headers=response.headers)
        if 500 <= status_code < 600:
            raise ServerError(message, headers=response.headers)
        raise TwitterException(message, headers=response.headers)

    if status_code == 200:
        return response_data, response
    return response_data, response


def _configure_key_byte_fallback(client: Any) -> Any:
    if getattr(client, "_xfeed_key_byte_fallback_installed", False):
        return client

    client.get_cookies = lambda: _cookie_mapping_from_jar(client)
    original_request = client.request
    client._xfeed_key_byte_fallback_disabled = False

    async def request_with_key_byte_fallback(
        method: str,
        url: str,
        auto_unlock: bool = True,
        raise_exception: bool = True,
        **kwargs: Any,
    ) -> tuple[dict[str, Any] | Any, Any]:
        if client._xfeed_key_byte_fallback_disabled:
            return await _request_without_transaction(
                client,
                method,
                url,
                auto_unlock=auto_unlock,
                raise_exception=raise_exception,
                **kwargs,
            )

        try:
            return await original_request(
                method,
                url,
                auto_unlock=auto_unlock,
                raise_exception=raise_exception,
                **kwargs,
            )
        except Exception as exc:
            if not _is_key_byte_indices_error(exc):
                raise
            client._xfeed_key_byte_fallback_disabled = True
            return await _request_without_transaction(
                client,
                method,
                url,
                auto_unlock=auto_unlock,
                raise_exception=raise_exception,
                **kwargs,
            )

    client.request = request_with_key_byte_fallback
    client._xfeed_key_byte_fallback_installed = True
    return client


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

    async def fetch_replies(
        self,
        tweet_id: str,
        *,
        cursor: str | None,
        count: int,
    ) -> FeedPage:
        client = self._get_client()
        tweets: list[TweetView]
        next_cursor: str | None

        client_fetcher = getattr(client, "get_tweet_replies", None)
        if callable(client_fetcher):
            result = await client_fetcher(tweet_id, count=count, cursor=cursor)
            tweets = [
                await self._normalize_tweet(tweet, client=client)
                for tweet in self._result_items(result)
                if str(getattr(tweet, "id", "")) != str(tweet_id)
            ]
            next_cursor = getattr(result, "next_cursor", None)
        else:
            tweets, next_cursor = await self._fetch_replies_from_detail(
                tweet_id,
                client=client,
                cursor=cursor,
            )
        return FeedPage(tweets=tweets[:count], next_cursor=next_cursor)

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

    async def _fetch_replies_from_detail(
        self,
        tweet_id: str,
        *,
        client: Any,
        cursor: str | None,
    ) -> tuple[list[TweetView], str | None]:
        if tweet_from_data is None or find_dict is None:
            raise ProviderError("twikit is not installed. Install project dependencies first.")

        response, _ = await client.gql.tweet_detail(tweet_id, cursor)
        entries_matches = find_dict(response, "entries", find_one=True)
        if not entries_matches:
            return [], None
        entries = entries_matches[0]
        replies: list[TweetView] = []
        seen_ids: set[str] = set()

        for entry in entries:
            entry_id = str(entry.get("entryId", ""))
            if entry_id.startswith("cursor"):
                continue

            entry_reply_tweets = self._tweet_candidates_from_entry(client, entry)
            for tweet in entry_reply_tweets:
                normalized = await self._normalize_tweet(tweet, client=client)
                if normalized.id == str(tweet_id) or normalized.id in seen_ids:
                    continue
                seen_ids.add(normalized.id)
                replies.append(normalized)

        return replies, self._extract_reply_cursor(entries)

    def _result_items(self, result: Any) -> list[Any]:
        tweets = getattr(result, "tweets", None)
        if tweets is not None:
            return list(tweets)
        return list(result)

    def _tweet_candidates_from_entry(self, client: Any, entry: dict[str, Any]) -> list[Any]:
        direct_tweet = tweet_from_data(client, entry)
        if direct_tweet is not None:
            return [direct_tweet]

        content = entry.get("content")
        if not isinstance(content, dict):
            return []
        items = content.get("items")
        if not isinstance(items, list):
            return []

        tweets: list[Any] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            item_entry_id = str(item.get("entryId", ""))
            if "tweet" not in item_entry_id:
                nested = item.get("item")
                if isinstance(nested, dict):
                    item = nested
                    item_entry_id = str(item.get("entryId", ""))
            if "tweet" not in item_entry_id:
                continue
            tweet = tweet_from_data(client, item)
            if tweet is not None:
                tweets.append(tweet)
        return tweets

    def _extract_reply_cursor(self, entries: list[dict[str, Any]]) -> str | None:
        for entry in reversed(entries):
            entry_id = str(entry.get("entryId", ""))
            if not entry_id.startswith("cursor"):
                continue
            content = entry.get("content")
            if not isinstance(content, dict):
                continue
            item_content = content.get("itemContent")
            if isinstance(item_content, dict):
                value = item_content.get("value")
                if value:
                    return str(value)
            value = content.get("value")
            if value:
                return str(value)
        return None

    def _get_client(self):
        if Client is None:
            raise ProviderError(
                "twikit is not installed. Install project dependencies first."
            )
        if self._client is None:
            client = Client(language=self._language)
            client.set_cookies(self._cookies, clear_cookies=True)
            self._client = _configure_key_byte_fallback(client)
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
        visible_text = self._extract_visible_text(normalized_target)
        full_text = self._extract_full_text(tweet, normalized_target)
        display_text = visible_text or full_text
        normalized_full_text = full_text if full_text and full_text != display_text else None
        return TweetView(
            id=tweet_id,
            author_name=author_name,
            author_handle=author_handle,
            text=display_text,
            created_at=str(getattr(normalized_target, "created_at", "")),
            url=f"https://x.com/{author_handle}/status/{tweet_id}",
            full_text=normalized_full_text,
            has_hidden_text=normalized_full_text is not None,
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

    def _extract_visible_text(self, tweet: Any) -> str:
        text = getattr(tweet, "text", None)
        if text is None:
            text = getattr(tweet, "full_text", "")
        return (text or "").strip()

    def _extract_full_text(self, *tweet_candidates: Any) -> str:
        note_tweet_text = self._extract_note_tweet_text(*tweet_candidates)
        if note_tweet_text:
            return note_tweet_text
        for candidate in tweet_candidates:
            text = self._extract_visible_text(candidate)
            if text:
                return text
        return ""

    def _extract_note_tweet_text(self, *tweet_candidates: Any) -> str | None:
        for candidate in tweet_candidates:
            for root in self._note_tweet_roots(candidate):
                text = self._find_note_tweet_text(root, set(), depth=0)
                if text:
                    return text
        return None

    def _note_tweet_roots(self, candidate: Any) -> list[Any]:
        if candidate is None:
            return []
        roots: list[Any] = []
        if isinstance(candidate, dict):
            for key in ("note_tweet", "note_tweet_results"):
                value = candidate.get(key)
                if value is not None:
                    roots.append(value)
            legacy = candidate.get("legacy")
        else:
            for attr in ("note_tweet", "note_tweet_results"):
                value = getattr(candidate, attr, None)
                if value is not None:
                    roots.append(value)
            legacy = getattr(candidate, "legacy", None)
        if legacy is not None:
            roots.extend(self._note_tweet_roots(legacy))
        return roots

    def _find_note_tweet_text(
        self,
        value: Any,
        seen_objects: set[int],
        *,
        depth: int,
    ) -> str | None:
        if value is None or depth > 12:
            return None
        if isinstance(value, str):
            return None
        if isinstance(value, (int, float, bool, bytes)):
            return None

        object_id = id(value)
        if object_id in seen_objects:
            return None
        seen_objects.add(object_id)

        if isinstance(value, dict):
            direct_text = value.get("text")
            if isinstance(direct_text, str) and direct_text.strip():
                return direct_text.strip()
            for key in ("result", "note_tweet_results", "note_tweet", "legacy"):
                match = self._find_note_tweet_text(
                    value.get(key),
                    seen_objects,
                    depth=depth + 1,
                )
                if match is not None:
                    return match
            for item in value.values():
                match = self._find_note_tweet_text(item, seen_objects, depth=depth + 1)
                if match is not None:
                    return match
            return None

        if isinstance(value, (list, tuple, set)):
            for item in value:
                match = self._find_note_tweet_text(item, seen_objects, depth=depth + 1)
                if match is not None:
                    return match
            return None

        direct_text = getattr(value, "text", None)
        if isinstance(direct_text, str) and direct_text.strip():
            return direct_text.strip()
        for attr in ("result", "note_tweet_results", "note_tweet", "legacy"):
            match = self._find_note_tweet_text(
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
            match = self._find_note_tweet_text(item, seen_objects, depth=depth + 1)
            if match is not None:
                return match
        return None
