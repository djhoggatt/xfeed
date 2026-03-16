from __future__ import annotations

import asyncio

from xfeed.feed import FeedController
from xfeed.models import FeedMode, FeedPage, TweetView, UserTweetType


class FakeProvider:
    def __init__(self) -> None:
        self.home_calls: list[tuple[FeedMode, str | None, int, list[str] | None]] = []
        self.user_calls: list[tuple[str, UserTweetType, str | None, int]] = []

    async def fetch_home(
        self,
        mode: FeedMode,
        *,
        cursor: str | None,
        count: int,
        seen_tweet_ids: list[str] | None = None,
    ) -> FeedPage:
        self.home_calls.append((mode, cursor, count, seen_tweet_ids))
        return FeedPage(
            tweets=[_make_tweet("1", "alice", "home")],
            next_cursor="home-next",
        )

    async def fetch_user_timeline(
        self,
        screen_name: str,
        tweet_type: UserTweetType,
        *,
        cursor: str | None,
        count: int,
    ) -> FeedPage:
        self.user_calls.append((screen_name, tweet_type, cursor, count))
        return FeedPage(
            tweets=[_make_tweet("2", screen_name, tweet_type.value)],
            next_cursor="user-next",
        )

    async def fetch_tweet(self, tweet_id: str) -> TweetView:
        return _make_tweet(tweet_id, "alice", "single")


def _make_tweet(tweet_id: str, handle: str, text: str) -> TweetView:
    return TweetView(
        id=tweet_id,
        author_name=handle.title(),
        author_handle=handle,
        text=text,
        created_at="Fri, 13 Mar 2026 12:00:00 +0000",
        url=f"https://x.com/{handle}/status/{tweet_id}",
    )


def test_user_controller_loads_user_timeline_and_cycles_feed_type() -> None:
    provider = FakeProvider()
    controller = FeedController(
        provider,
        mode=None,
        user_screen_name="@alice",
        user_tweet_type=UserTweetType.POSTS,
        page_size=15,
    )

    tweets = asyncio.run(controller.load_initial())

    assert tweets[0].text == "posts"
    assert provider.user_calls == [("alice", UserTweetType.POSTS, None, 15)]
    assert controller.title == "@alice · posts"
    assert controller.status_label == "@alice posts"
    assert controller.toggle_label == "feed"

    next_value = asyncio.run(controller.toggle_view())

    assert next_value == "replies"
    assert provider.user_calls[-1] == ("alice", UserTweetType.REPLIES, None, 15)
    assert controller.user_tweet_type is UserTweetType.REPLIES


def test_home_controller_toggle_switches_between_modes() -> None:
    provider = FakeProvider()
    controller = FeedController(provider, mode=FeedMode.FOLLOWING, page_size=10)

    asyncio.run(controller.load_initial())
    next_value = asyncio.run(controller.toggle_view())

    assert next_value == "for-you"
    assert provider.home_calls[0][0] is FeedMode.FOLLOWING
    assert provider.home_calls[-1][0] is FeedMode.FOR_YOU
