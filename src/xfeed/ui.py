from __future__ import annotations

import time
import webbrowser
from pathlib import Path

from xfeed.feed import FeedController
from xfeed.media import (
    clear_kitty_images,
    download_image,
    select_images,
    show_images_with_kitty,
    wait_for_keypress,
)
from xfeed.models import TweetView
from xfeed.render import render_feed_list, render_tweet_detail

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal
    from textual.widgets import Static
except ImportError as exc:  # pragma: no cover - exercised only when dependency is missing
    raise RuntimeError(
        "textual is not installed. Install project dependencies first."
    ) from exc


class FeedApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
        background: transparent;
        color: auto;
    }

    #body {
        height: 1fr;
    }

    .bar {
        height: auto;
        padding: 0 1;
        background: transparent;
        color: auto;
    }

    #feed-list {
        width: 44%;
        height: 1fr;
        padding: 1;
        border-right: solid $boost;
        background: transparent;
        overflow: auto auto;
    }

    #tweet-detail {
        width: 56%;
        height: 1fr;
        padding: 1;
        background: transparent;
        overflow: auto auto;
    }

    #status {
        height: 1;
        padding: 0 1;
        background: transparent;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("j", "move_down", "Down", show=False),
        Binding("k", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("up", "move_up", "Up", show=False),
        Binding("n", "load_more", "Older"),
        Binding("p", "load_previous", "Newer"),
        Binding("r", "refresh_feed", "Refresh"),
        Binding("f", "toggle_mode", "Mode"),
        Binding("i", "show_images", "Images"),
        Binding("o", "open_tweet", "Open"),
    ]

    def __init__(self, controller: FeedController) -> None:
        super().__init__(ansi_color=True)
        self.controller = controller
        self.selected_index = 0
        self._page_start = 0
        self._status = "Loading feed..."
        self._image_view_cooldown_until = 0.0

    def compose(self) -> ComposeResult:
        yield Static(id="topbar", classes="bar")
        with Horizontal(id="body"):
            yield Static(id="feed-list")
            yield Static(id="tweet-detail")
        yield Static(id="status")
        yield Static(id="helpbar", classes="bar")

    async def on_mount(self) -> None:
        try:
            await self.controller.load_initial()
            self._status = self._status_line("Loaded initial timeline.")
        except Exception as exc:  # pragma: no cover - runtime dependency path
            self._status = f"Error: {exc}"
        self._render()

    def action_move_down(self) -> None:
        if self.selected_index < self._page_end_index():
            self.selected_index += 1
            self._render()

    def action_move_up(self) -> None:
        if self.selected_index > self._page_start:
            self.selected_index -= 1
            self._render()

    async def action_load_more(self) -> None:
        page_size = self._page_size()
        target_start = self._page_start + page_size
        try:
            loaded = 0
            while target_start >= len(self.controller.tweets):
                added = await self.controller.load_more()
                loaded += added
                if added == 0:
                    break
            if target_start >= len(self.controller.tweets):
                self._status = self._status_line("No older tweets available.")
            else:
                self._page_start = target_start
                self.selected_index = self._page_start
                if loaded > 0:
                    self._status = self._status_line(
                        f"Loaded {loaded} older tweets."
                    )
                else:
                    self._status = self._status_line("Showing older tweets.")
        except Exception as exc:  # pragma: no cover - runtime dependency path
            self._status = f"Error: {exc}"
        self._render()

    def action_load_previous(self) -> None:
        page_size = self._page_size()
        if self._page_start <= 0:
            self._status = self._status_line("No newer tweets available.")
        else:
            self._page_start = max(0, self._page_start - page_size)
            self.selected_index = self._page_start
            self._status = self._status_line("Showing newer tweets.")
        self._render()

    async def action_refresh_feed(self) -> None:
        try:
            added = await self.controller.refresh()
            if added == 0:
                self._status = self._status_line("No new tweets.")
            else:
                self._page_start = 0
                self.selected_index = 0
                self._status = self._status_line(f"Loaded {added} new tweets.")
        except Exception as exc:  # pragma: no cover - runtime dependency path
            self._status = f"Error: {exc}"
        self._render()

    async def action_toggle_mode(self) -> None:
        try:
            next_value = await self.controller.toggle_view()
            self._page_start = 0
            self.selected_index = 0
            self._status = self._status_line(f"Switched to {next_value}.")
        except Exception as exc:  # pragma: no cover - runtime dependency path
            self._status = f"Error: {exc}"
        self._render()

    def action_open_tweet(self) -> None:
        tweet = self._current_tweet()
        if tweet is None:
            return
        webbrowser.open(tweet.url)
        self._status = self._status_line(f"Opened {tweet.url}")
        self._render()

    def action_show_images(self) -> None:
        if time.monotonic() < self._image_view_cooldown_until:
            return
        tweet = self._current_tweet()
        if tweet is None:
            return
        image_paths: list[Path] = []
        try:
            image_urls = select_images(tweet)
            if not image_urls:
                raise RuntimeError("The selected tweet does not contain images.")
            image_paths = [download_image(url) for url in image_urls]
            with self.suspend():
                show_images_with_kitty(image_paths)
                wait_for_keypress("Press any key to return to xfeed...")
                clear_kitty_images()
            self._image_view_cooldown_until = time.monotonic() + 0.35
            self._status = self._status_line(
                f"Displayed {len(image_paths)} image{'s' if len(image_paths) != 1 else ''}."
            )
            self._render()
        except Exception as exc:  # pragma: no cover - runtime dependency path
            self._status = f"Error: {exc}"
            self._render()
        finally:
            self._image_view_cooldown_until = time.monotonic() + 0.35
            for image_path in image_paths:
                image_path.unlink(missing_ok=True)

    def _render(self) -> None:
        topbar_widget = self.query_one("#topbar", Static)
        list_widget = self.query_one("#feed-list", Static)
        detail_widget = self.query_one("#tweet-detail", Static)
        status_widget = self.query_one("#status", Static)
        helpbar_widget = self.query_one("#helpbar", Static)
        topbar_widget.update(
            f"xfeed  ·  {self.controller.title}  ·  {len(self.controller.tweets)} tweets"
        )
        self._page_start = min(self._page_start, self._max_page_start())
        self.selected_index = self._clamp_selected_index(self.selected_index)
        page_size = self._page_size()
        list_width = max(list_widget.content_region.width, 20)
        list_widget.update(
            render_feed_list(
                self.controller.tweets,
                selected_index=self.selected_index,
                width=list_width,
                start_index=self._page_start,
                max_items=page_size,
            )
        )
        tweet = self._current_tweet()
        detail_widget.update(
            render_tweet_detail(tweet) if tweet is not None else "No tweet selected."
        )
        status_widget.update(self._status)
        helpbar_widget.update(
            f"j/k move  p newer  n older  r refresh  f {self.controller.toggle_label}  i images  o open  q quit"
        )

    def _current_tweet(self) -> TweetView | None:
        if not self.controller.tweets:
            return None
        self.selected_index = self._clamp_selected_index(self.selected_index)
        return self.controller.tweets[self.selected_index]

    def _status_line(self, message: str) -> str:
        return f"{self.controller.status_label} | {len(self.controller.tweets)} tweets | {message}"

    def _page_size(self) -> int:
        list_widget = self.query_one("#feed-list", Static)
        visible_lines = max(list_widget.size.height - 2, 2)
        return max(visible_lines // 2, 1)

    def _page_end_index(self) -> int:
        if not self.controller.tweets:
            return 0
        return min(
            self._page_start + self._page_size(),
            len(self.controller.tweets),
        ) - 1

    def _max_page_start(self) -> int:
        tweet_count = len(self.controller.tweets)
        if tweet_count <= 0:
            return 0
        return max(tweet_count - self._page_size(), 0)

    def _clamp_selected_index(self, selected_index: int) -> int:
        if not self.controller.tweets:
            return 0
        return max(self._page_start, min(selected_index, self._page_end_index()))
