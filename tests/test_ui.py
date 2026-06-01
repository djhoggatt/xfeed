from __future__ import annotations

import asyncio

import pytest

from xfeed.models import FeedPage, TweetView

pytest.importorskip("textual")

from xfeed.ui import FeedApp


def widget_text(app: FeedApp, selector: str) -> str:
    return str(app.query_one(selector).content)


class FakeController:
    def __init__(self, tweet_count: int = 30) -> None:
        self.title = "test"
        self.status_label = "test"
        self.toggle_label = "mode"
        self.tweets = [
            TweetView(
                id=str(index),
                author_name="Author",
                author_handle=f"user{index}",
                text=f"tweet {index}",
                created_at="Fri, 13 Mar 2026 12:00:00 +0000",
                url=f"https://x.com/user{index}/status/{index}",
            )
            for index in range(tweet_count)
        ]
        self._tweet_details = {
            tweet.id: TweetView(
                id=tweet.id,
                author_name=tweet.author_name,
                author_handle=tweet.author_handle,
                text=tweet.text,
                created_at=tweet.created_at,
                url=tweet.url,
                full_text=tweet.full_text,
                has_hidden_text=tweet.has_hidden_text,
                reply_count=tweet.reply_count,
                retweet_count=tweet.retweet_count,
                like_count=tweet.like_count,
                quote_count=tweet.quote_count,
                lang=tweet.lang,
                media=list(tweet.media),
                quoted_tweet=tweet.quoted_tweet,
                retweeted_by=tweet.retweeted_by,
                in_reply_to=tweet.in_reply_to,
            )
            for tweet in self.tweets
        }
        self.load_more_calls = 0
        self.reply_calls: list[tuple[str, str | None]] = []

    async def load_initial(self):
        return self.tweets

    async def load_more(self) -> int:
        self.load_more_calls += 1
        return 0

    async def refresh(self) -> int:
        return 0

    async def toggle_view(self) -> str:
        return "mode"

    async def fetch_tweet(self, tweet_id: str) -> TweetView:
        return self._tweet_details[tweet_id]

    async def fetch_replies(self, tweet_id: str, *, cursor: str | None = None) -> FeedPage:
        self.reply_calls.append((tweet_id, cursor))
        if cursor is None:
            return FeedPage(
                tweets=[
                    TweetView(
                        id=f"{tweet_id}-reply-{index}",
                        author_name=f"Reply {index}",
                        author_handle=f"reply{index}",
                        text=f"reply {index}",
                        created_at="Fri, 13 Mar 2026 12:00:00 +0000",
                        url=f"https://x.com/reply{index}/status/{tweet_id}-reply-{index}",
                    )
                    for index in range(3)
                ],
                next_cursor="reply-next",
            )
        return FeedPage(
            tweets=[
                TweetView(
                    id=f"{tweet_id}-reply-{index}",
                    author_name=f"Reply {index}",
                    author_handle=f"reply{index}",
                    text=f"reply {index}",
                    created_at="Fri, 13 Mar 2026 12:00:00 +0000",
                    url=f"https://x.com/reply{index}/status/{tweet_id}-reply-{index}",
                )
                for index in range(3, 6)
            ],
            next_cursor=None,
        )


class NoReplyController(FakeController):
    async def fetch_replies(self, tweet_id: str, *, cursor: str | None = None) -> FeedPage:
        self.reply_calls.append((tweet_id, cursor))
        return FeedPage(tweets=[], next_cursor=None)


def test_feed_list_pages_older_and_newer() -> None:
    async def scenario() -> None:
        controller = FakeController()
        app = FeedApp(controller)
        async with app.run_test(size=(100, 20)) as pilot:
            await pilot.pause()
            await pilot.pause()

            page_size = app._page_size()
            assert page_size > 0
            assert app.selected_index == 0

            for _ in range(page_size - 1):
                await pilot.press("j")
                await pilot.pause()

            assert app.selected_index == page_size - 1

            await pilot.press("j")
            await pilot.pause()
            assert app.selected_index == page_size - 1

            await pilot.press("n")
            await pilot.pause()
            assert app.selected_index == page_size

            rendered_text = widget_text(app, "#feed-list")
            assert "@user0" not in rendered_text
            assert f"@user{page_size}" in rendered_text

            await pilot.press("p")
            await pilot.pause()
            assert app.selected_index == 0
            assert controller.load_more_calls == 0

    asyncio.run(scenario())


def test_reply_mode_flips_detail_pane_and_steps_replies() -> None:
    async def scenario() -> None:
        controller = FakeController()
        app = FeedApp(controller)
        async with app.run_test(size=(100, 14)) as pilot:
            await pilot.pause()
            await pilot.pause()

            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()

            assert app._reply_mode is True
            assert controller.reply_calls == [("0", None)]
            rendered = widget_text(app, "#tweet-detail")
            assert "Replies to Author (@user0)" in rendered
            assert "Reply 1 of 3 loaded" in rendered
            assert "Reply 0 (@reply0)" in rendered

            await pilot.press("right")
            await pilot.pause()
            assert app._reply_index == 1
            rendered = widget_text(app, "#tweet-detail")
            assert "Reply 1 (@reply1)" in rendered

            await pilot.press("right")
            await pilot.pause()
            assert app._reply_index == 2

            await pilot.press("right")
            await pilot.pause()
            assert controller.reply_calls == [("0", None)]
            assert app._reply_index == 2
            rendered = widget_text(app, "#tweet-detail")
            assert "Reply 2 (@reply2)" in rendered

            await pilot.press("left")
            await pilot.pause()
            assert app._reply_index == 1
            rendered = widget_text(app, "#tweet-detail")
            assert "Reply 1 (@reply1)" in rendered

            await pilot.press("left")
            await pilot.pause()
            await pilot.press("left")
            await pilot.pause()
            assert app._reply_index == 0

            await pilot.press("backspace")
            await pilot.pause()

            assert app._reply_mode is False
            rendered = widget_text(app, "#tweet-detail")
            assert "tweet 0" in rendered

    asyncio.run(scenario())


def test_enter_on_reply_drills_into_nested_replies_and_escape_pops_stack() -> None:
    async def scenario() -> None:
        controller = FakeController()
        app = FeedApp(controller)
        async with app.run_test(size=(100, 14)) as pilot:
            await pilot.pause()
            await pilot.pause()

            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()

            await pilot.press("right")
            await pilot.pause()

            assert app._reply_index == 1

            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()

            assert controller.reply_calls == [("0", None), ("0-reply-1", None)]
            assert app._reply_mode is True
            assert len(app._reply_stack) == 1
            rendered = widget_text(app, "#tweet-detail")
            assert "Replies to Reply 1 (@reply1)" in rendered
            assert "Reply 1 of 3 loaded" in rendered
            assert "Reply 0 (@reply0)" in rendered

            await pilot.press("backspace")
            await pilot.pause()

            assert app._reply_mode is True
            assert len(app._reply_stack) == 0
            assert app._reply_index == 1
            rendered = widget_text(app, "#tweet-detail")
            assert "Replies to Author (@user0)" in rendered
            assert "Reply 1 (@reply1)" in rendered

    asyncio.run(scenario())


def test_escape_exits_reply_mode_entirely_from_nested_reply() -> None:
    async def scenario() -> None:
        controller = FakeController()
        app = FeedApp(controller)
        async with app.run_test(size=(100, 14)) as pilot:
            await pilot.pause()
            await pilot.pause()

            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()

            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()

            assert app._reply_mode is True
            assert len(app._reply_stack) == 1

            await pilot.press("escape")
            await pilot.pause()

            assert app._reply_mode is False
            assert len(app._reply_stack) == 0
            rendered = widget_text(app, "#tweet-detail")
            assert "tweet 0" in rendered

    asyncio.run(scenario())


def test_enter_without_replies_does_not_enter_reply_mode() -> None:
    async def scenario() -> None:
        controller = NoReplyController()
        app = FeedApp(controller)
        async with app.run_test(size=(100, 14)) as pilot:
            await pilot.pause()
            await pilot.pause()

            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()

            assert controller.reply_calls == [("0", None)]
            assert app._reply_mode is False
            assert app._status.endswith("No replies found for @user0.")

    asyncio.run(scenario())


def test_v_opens_quoted_tweet_and_backspace_returns_to_feed_tweet() -> None:
    async def scenario() -> None:
        controller = FakeController()
        quoted = TweetView(
            id="quoted-1",
            author_name="Quoted Author",
            author_handle="quoted",
            text="quoted tweet body",
            created_at="Fri, 13 Mar 2026 12:05:00 +0000",
            url="https://x.com/quoted/status/quoted-1",
        )
        controller.tweets[0].quoted_tweet = quoted
        controller._tweet_details["0"].quoted_tweet = quoted
        app = FeedApp(controller)
        async with app.run_test(size=(100, 14)) as pilot:
            await pilot.pause()
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()

            assert app._quote_mode is True
            rendered = widget_text(app, "#tweet-detail")
            assert "Quote from Author (@user0)" in rendered
            assert "Quoted Author (@quoted)" in rendered
            assert "quoted tweet body" in rendered

            await pilot.press("backspace")
            await pilot.pause()

            assert app._quote_mode is False
            rendered = widget_text(app, "#tweet-detail")
            assert "tweet 0" in rendered
            assert "Quote from Author (@user0)" not in rendered

    asyncio.run(scenario())


def test_v_fetches_tweet_detail_when_quote_is_not_loaded_yet() -> None:
    async def scenario() -> None:
        controller = FakeController()
        quoted = TweetView(
            id="quoted-1",
            author_name="Quoted Author",
            author_handle="quoted",
            text="quoted tweet body",
            created_at="Fri, 13 Mar 2026 12:05:00 +0000",
            url="https://x.com/quoted/status/quoted-1",
        )
        controller._tweet_details["0"].quoted_tweet = quoted
        app = FeedApp(controller)
        async with app.run_test(size=(100, 14)) as pilot:
            await pilot.pause()
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()

            assert app._quote_mode is True
            assert controller.tweets[0].quoted_tweet is quoted
            rendered = widget_text(app, "#tweet-detail")
            assert "Quoted Author (@quoted)" in rendered

    asyncio.run(scenario())


def test_v_renders_quoted_tweet_text_with_markup_characters_literally() -> None:
    async def scenario() -> None:
        controller = FakeController()
        quoted = TweetView(
            id="quoted-1",
            author_name="Quoted Author",
            author_handle="quoted",
            text="quoted [bold]not rich markup[/bold] body",
            created_at="Fri, 13 Mar 2026 12:05:00 +0000",
            url="https://x.com/quoted/status/quoted-1",
        )
        controller.tweets[0].quoted_tweet = quoted
        controller._tweet_details["0"].quoted_tweet = quoted
        app = FeedApp(controller)
        async with app.run_test(size=(100, 14)) as pilot:
            await pilot.pause()
            await pilot.pause()

            await pilot.press("v")
            await pilot.pause()

            assert app._quote_mode is True
            rendered = widget_text(app, "#tweet-detail")
            assert "[bold]not rich markup[/bold]" in rendered

    asyncio.run(scenario())


def test_m_expands_hidden_text_after_fetching_tweet_detail() -> None:
    async def scenario() -> None:
        controller = FakeController()
        controller.tweets[0] = TweetView(
            id="0",
            author_name="Author",
            author_handle="user0",
            text="Short preview",
            created_at="Fri, 13 Mar 2026 12:00:00 +0000",
            url="https://x.com/user0/status/0",
        )
        controller._tweet_details["0"] = TweetView(
            id="0",
            author_name="Author",
            author_handle="user0",
            text="Short preview",
            full_text="Short preview with the hidden continuation.",
            has_hidden_text=True,
            created_at="Fri, 13 Mar 2026 12:00:00 +0000",
            url="https://x.com/user0/status/0",
        )
        app = FeedApp(controller)
        async with app.run_test(size=(100, 14)) as pilot:
            await pilot.pause()
            await pilot.pause()

            rendered = widget_text(app, "#tweet-detail")
            assert "hidden continuation" not in rendered

            await pilot.press("m")
            await pilot.pause()

            rendered = widget_text(app, "#tweet-detail")
            assert "Short preview with the hidden continuation." in rendered
            assert "m collapse" in rendered

            await pilot.press("m")
            await pilot.pause()

            rendered = widget_text(app, "#tweet-detail")
            assert "hidden continuation" not in rendered
            assert "m show more" in rendered

    asyncio.run(scenario())
