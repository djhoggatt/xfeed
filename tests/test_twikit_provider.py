from __future__ import annotations

import asyncio
from types import SimpleNamespace

from xfeed.models import FeedMode
from xfeed.models import UserTweetType
from xfeed.providers.twikit_provider import TwikitProvider


class FakeTimeline(list):
    def __init__(self, tweets):
        super().__init__(tweets)
        self.next_cursor = "next"


class FakeClient:
    def __init__(self, timeline_tweets, tweet_by_id):
        self._timeline = FakeTimeline(timeline_tweets)
        self._tweet_by_id = tweet_by_id
        self.requested_ids: list[str] = []
        self.reply_calls: list[tuple[str, int, str | None]] = []
        self.user_lookup_calls: list[str] = []
        self.user_tweet_calls: list[tuple[str, str, int, str | None]] = []

    async def get_timeline(self, *, count, cursor, seen_tweet_ids):
        return self._timeline

    async def get_latest_timeline(self, *, count, cursor, seen_tweet_ids):
        return self._timeline

    async def get_tweet_by_id(self, tweet_id):
        self.requested_ids.append(str(tweet_id))
        return self._tweet_by_id[str(tweet_id)]

    async def get_tweet_replies(self, tweet_id, *, count, cursor):
        self.reply_calls.append((str(tweet_id), count, cursor))
        return self._timeline

    async def get_user_by_screen_name(self, screen_name):
        self.user_lookup_calls.append(screen_name)
        return SimpleNamespace(id="42", screen_name=screen_name, name=screen_name.title())

    async def get_user_tweets(self, user_id, *, tweet_type, count, cursor):
        self.user_tweet_calls.append((str(user_id), tweet_type, count, cursor))
        return self._timeline


class FakeGqlClient:
    def __init__(self, response):
        self.response = response
        self.calls: list[tuple[str, str | None]] = []

    async def tweet_detail(self, tweet_id, cursor):
        self.calls.append((str(tweet_id), cursor))
        return self.response, None


def _make_tweet(tweet_id: int, *, author: str, text: str, entities=None):
    return SimpleNamespace(
        id=tweet_id,
        text=text,
        full_text=text,
        created_at="Fri, 13 Mar 2026 12:00:00 +0000",
        user=SimpleNamespace(name=author.title(), screen_name=author),
        reply_count=1,
        retweet_count=2,
        favorite_count=3,
        quote_count=4,
        media=[],
        entities=entities or {},
    )


def _entry(tweet_id: int, author: str, text: str) -> dict:
    return {
        "entryId": f"tweet-{tweet_id}",
        "content": {"itemContent": {"tweet_results": {"result": {}}}},
        "_tweet": _make_tweet(tweet_id, author=author, text=text),
    }


def test_fetch_home_fetches_linked_quote_when_quote_object_is_missing() -> None:
    quoted = _make_tweet(99, author="bob", text="Quoted body")
    tweet = _make_tweet(
        1,
        author="alice",
        text="Look at this https://t.co/quoted",
        entities={
            "urls": [
                {
                    "expanded_url": "https://x.com/bob/status/99",
                    "url": "https://t.co/quoted",
                }
            ]
        },
    )
    client = FakeClient([tweet], {"99": quoted})
    provider = TwikitProvider({})
    provider._get_client = lambda: client  # type: ignore[method-assign]

    page = asyncio.run(
        provider.fetch_home(
            FeedMode.FOR_YOU,
            cursor=None,
            count=20,
        )
    )

    assert client.requested_ids == ["99"]
    assert page.next_cursor == "next"
    assert page.tweets[0].quoted_tweet is not None
    assert page.tweets[0].quoted_tweet.author_handle == "bob"
    assert page.tweets[0].quoted_tweet.text == "Quoted body"


def test_fetch_user_timeline_looks_up_user_and_uses_twikit_tweet_type() -> None:
    tweet = _make_tweet(1, author="alice", text="post body")
    client = FakeClient([tweet], {})
    provider = TwikitProvider({})
    provider._get_client = lambda: client  # type: ignore[method-assign]

    page = asyncio.run(
        provider.fetch_user_timeline(
            "@alice",
            UserTweetType.REPLIES,
            cursor="cursor-1",
            count=15,
        )
    )

    assert client.user_lookup_calls == ["alice"]
    assert client.user_tweet_calls == [("42", "Replies", 15, "cursor-1")]
    assert page.tweets[0].author_handle == "alice"


def test_fetch_home_finds_linked_quote_in_nested_tweet_data() -> None:
    quoted = _make_tweet(77, author="bob", text="Nested quoted body")
    tweet = _make_tweet(
        1,
        author="alice",
        text="Look at this https://t.co/nested",
    )
    tweet.note_tweet = SimpleNamespace(
        note_tweet_results=SimpleNamespace(
            result={
                "entity_set": {
                    "urls": [
                        {
                            "url": "https://t.co/nested",
                            "expanded_url": "https://x.com/bob/status/77",
                        }
                    ]
                }
            }
        )
    )
    client = FakeClient([tweet], {"77": quoted})
    provider = TwikitProvider({})
    provider._get_client = lambda: client  # type: ignore[method-assign]

    page = asyncio.run(provider.fetch_home(FeedMode.FOR_YOU, cursor=None, count=20))

    assert client.requested_ids == ["77"]
    assert page.tweets[0].quoted_tweet is not None
    assert page.tweets[0].quoted_tweet.text == "Nested quoted body"


def test_fetch_replies_uses_client_reply_endpoint_and_skips_parent_tweet() -> None:
    parent = _make_tweet(1, author="alice", text="parent")
    reply = _make_tweet(2, author="bob", text="reply")
    client = FakeClient([parent, reply], {"1": parent})
    provider = TwikitProvider({})
    provider._get_client = lambda: client  # type: ignore[method-assign]

    page = asyncio.run(provider.fetch_replies("1", cursor="cursor-1", count=15))

    assert client.reply_calls == [("1", 15, "cursor-1")]
    assert [tweet.id for tweet in page.tweets] == ["2"]


def test_fetch_replies_falls_back_to_gql_detail_without_get_tweet_by_id() -> None:
    response = {
        "entries": [
            _entry(1, "alice", "parent"),
            {
                "entryId": "conversationthread-1",
                "content": {
                    "items": [
                        {"entryId": "label-1"},
                        _entry(2, "bob", "reply one"),
                        {"entryId": "cursor-showmorethreads-1", "content": {"value": "ignored"}},
                    ]
                },
            },
            {
                "entryId": "cursor-bottom-1",
                "content": {"value": "cursor-2"},
            },
        ]
    }
    client = SimpleNamespace(gql=FakeGqlClient(response))
    provider = TwikitProvider({})
    provider._get_client = lambda: client  # type: ignore[method-assign]

    from xfeed.providers import twikit_provider as module

    saved_tweet_from_data = module.tweet_from_data
    saved_find_dict = module.find_dict
    module.tweet_from_data = lambda _client, item: item.get("_tweet")  # type: ignore[assignment]
    module.find_dict = lambda data, key, find_one=True: [data[key]] if key in data else []  # type: ignore[assignment]
    try:
        page = asyncio.run(provider.fetch_replies("1", cursor=None, count=20))
    finally:
        module.tweet_from_data = saved_tweet_from_data  # type: ignore[assignment]
        module.find_dict = saved_find_dict  # type: ignore[assignment]

    assert client.gql.calls == [("1", None)]
    assert [tweet.id for tweet in page.tweets] == ["2"]
    assert page.next_cursor == "cursor-2"
