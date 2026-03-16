from __future__ import annotations

import asyncio

import pytest

from xfeed.models import TweetView

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

    async def load_initial(self):
        return self.tweets

    async def load_more(self) -> int:
        self.load_more_calls += 1
        return 0

    async def refresh(self) -> int:
        return 0

    async def toggle_view(self) -> str:
        return "mode"


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
