from __future__ import annotations

import asyncio

import pytest

from xfeed.models import FeedPage, TweetView

pytest.importorskip("textual")

from xfeed.ui import FeedApp


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

            rendered = app.query_one("#feed-list").renderable
            rendered_text = str(rendered)
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
            rendered = str(app.query_one("#tweet-detail").renderable)
            assert "Replies to Author (@user0)" in rendered
            assert "Reply 1 of 3 loaded" in rendered
            assert "Reply 0 (@reply0)" in rendered

            await pilot.press("right")
            await pilot.pause()
            assert app._reply_index == 1
            rendered = str(app.query_one("#tweet-detail").renderable)
            assert "Reply 1 (@reply1)" in rendered

            await pilot.press("right")
            await pilot.pause()
            assert app._reply_index == 2

            await pilot.press("right")
            await pilot.pause()
            assert controller.reply_calls == [("0", None)]
            assert app._reply_index == 2
            rendered = str(app.query_one("#tweet-detail").renderable)
            assert "Reply 2 (@reply2)" in rendered

            await pilot.press("left")
            await pilot.pause()
            assert app._reply_index == 1
            rendered = str(app.query_one("#tweet-detail").renderable)
            assert "Reply 1 (@reply1)" in rendered

            await pilot.press("left")
            await pilot.pause()
            await pilot.press("left")
            await pilot.pause()
            assert app._reply_index == 0

            await pilot.press("backspace")
            await pilot.pause()

            assert app._reply_mode is False
            rendered = str(app.query_one("#tweet-detail").renderable)
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
            rendered = str(app.query_one("#tweet-detail").renderable)
            assert "Replies to Reply 1 (@reply1)" in rendered
            assert "Reply 1 of 3 loaded" in rendered
            assert "Reply 0 (@reply0)" in rendered

            await pilot.press("backspace")
            await pilot.pause()

            assert app._reply_mode is True
            assert len(app._reply_stack) == 0
            assert app._reply_index == 1
            rendered = str(app.query_one("#tweet-detail").renderable)
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
            rendered = str(app.query_one("#tweet-detail").renderable)
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
