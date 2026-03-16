from __future__ import annotations

import time
import webbrowser
from dataclasses import dataclass
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
from xfeed.render import render_feed_list, render_reply_detail, render_tweet_detail

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal
    from textual.widgets import Static
except ImportError as exc:  # pragma: no cover - exercised only when dependency is missing
    raise RuntimeError(
        "textual is not installed. Install project dependencies first."
    ) from exc


@dataclass(slots=True)
class ReplyContext:
    source_tweet: TweetView
    replies: list[TweetView]
    index: int


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
        Binding("enter", "toggle_replies", "Replies", show=False),
        Binding("backspace", "reply_back", "Back", show=False),
        Binding("escape", "exit_reply_mode", "Exit", show=False),
        Binding("left", "previous_reply", "Previous reply", show=False),
        Binding("right", "next_reply", "Next reply", show=False),
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
        self._reply_mode = False
        self._reply_source_tweet: TweetView | None = None
        self._reply_tweets: list[TweetView] = []
        self._reply_index = 0
        self._reply_stack: list[ReplyContext] = []

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
        if self._reply_mode:
            return
        if self.selected_index < self._page_end_index():
            self.selected_index += 1
            self._render()

    def action_move_up(self) -> None:
        if self._reply_mode:
            return
        if self.selected_index > self._page_start:
            self.selected_index -= 1
            self._render()

    async def action_load_more(self) -> None:
        if self._reply_mode:
            self._status = self._status_line("Use Left/Right to navigate replies.")
            self._render()
            return
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
        if self._reply_mode:
            self._status = self._status_line("Use Left/Right to navigate replies.")
            self._render()
            return
        page_size = self._page_size()
        if self._page_start <= 0:
            self._status = self._status_line("No newer tweets available.")
        else:
            self._page_start = max(0, self._page_start - page_size)
            self.selected_index = self._page_start
            self._status = self._status_line("Showing newer tweets.")
        self._render()

    async def action_refresh_feed(self) -> None:
        if self._reply_mode:
            self._status = self._status_line("Exit reply mode to refresh the feed.")
            self._render()
            return
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
        if self._reply_mode:
            self._status = self._status_line(
                f"Exit reply mode to switch {self.controller.toggle_label}."
            )
            self._render()
            return
        try:
            next_value = await self.controller.toggle_view()
            self._page_start = 0
            self.selected_index = 0
            self._status = self._status_line(f"Switched to {next_value}.")
        except Exception as exc:  # pragma: no cover - runtime dependency path
            self._status = f"Error: {exc}"
        self._render()

    async def action_toggle_replies(self) -> None:
        tweet = self._active_tweet()
        if tweet is None:
            return
        try:
            await self._enter_reply_context(tweet)
        except Exception as exc:  # pragma: no cover - runtime dependency path
            self._status = f"Error: {exc}"
        self._render()

    def action_reply_back(self) -> None:
        if not self._reply_mode:
            return
        if self._reply_stack:
            context = self._reply_stack.pop()
            self._reply_source_tweet = context.source_tweet
            self._reply_tweets = context.replies
            self._reply_index = context.index
            self._status = self._status_line(
                f"Back to reply {self._reply_index + 1} of {len(self._reply_tweets)}."
            )
            self._render()
            return
        self.action_exit_reply_mode()

    def action_exit_reply_mode(self) -> None:
        if not self._reply_mode:
            return
        self._reply_mode = False
        self._reply_source_tweet = None
        self._reply_tweets = []
        self._reply_index = 0
        self._reply_stack.clear()
        self._status = self._status_line("Exited reply mode.")
        self._render()

    def action_previous_reply(self) -> None:
        if not self._reply_mode:
            return
        if self._reply_index <= 0:
            return
        self._reply_index -= 1
        self._status = self._status_line(
            f"Showing reply {self._reply_index + 1} of {len(self._reply_tweets)}."
        )
        self._render()

    async def action_next_reply(self) -> None:
        if not self._reply_mode:
            return
        if self._reply_index + 1 >= len(self._reply_tweets):
            return
        self._reply_index += 1
        self._status = self._status_line(
            f"Showing reply {self._reply_index + 1} of {len(self._reply_tweets)}."
        )
        self._render()

    def action_open_tweet(self) -> None:
        tweet = self._active_tweet()
        if tweet is None:
            return
        webbrowser.open(tweet.url)
        self._status = self._status_line(f"Opened {tweet.url}")
        self._render()

    def action_show_images(self) -> None:
        if time.monotonic() < self._image_view_cooldown_until:
            return
        tweet = self._active_tweet()
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
            "xfeed"
            f"  ·  {self.controller.title}"
            f"  ·  {len(self.controller.tweets)} tweets"
            + (
                f"  ·  replies {len(self._reply_tweets)}"
                f"  ·  depth {len(self._reply_stack) + 1}"
                if self._reply_mode
                else ""
            )
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
        if self._reply_mode:
            source_tweet = self._reply_source_tweet or self._current_feed_tweet()
            reply = self._current_reply_tweet()
            detail_widget.update(
                render_reply_detail(
                    source_tweet,
                    reply,
                    reply_index=self._reply_index,
                    loaded_reply_count=len(self._reply_tweets),
                )
                if source_tweet is not None
                else "No tweet selected."
            )
        else:
            tweet = self._current_feed_tweet()
            detail_widget.update(
                render_tweet_detail(tweet) if tweet is not None else "No tweet selected."
            )
        status_widget.update(self._status)
        if self._reply_mode:
            helpbar_widget.update(
                "left prev  right next  enter replies  backspace up  esc exit  i images  o open  q quit"
            )
        else:
            helpbar_widget.update(
                "j/k move  p newer  n older  r refresh  "
                f"f {self.controller.toggle_label}  enter replies  i images  o open  q quit"
            )

    def _active_tweet(self) -> TweetView | None:
        if self._reply_mode:
            if self._reply_tweets:
                self._reply_index = self._clamp_reply_index(self._reply_index)
                return self._reply_tweets[self._reply_index]
            if self._reply_source_tweet is not None:
                return self._reply_source_tweet
        return self._current_feed_tweet()

    def _current_reply_tweet(self) -> TweetView | None:
        if not self._reply_tweets:
            return None
        self._reply_index = self._clamp_reply_index(self._reply_index)
        return self._reply_tweets[self._reply_index]

    def _current_feed_tweet(self) -> TweetView | None:
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

    async def _load_initial_replies(self, tweet: TweetView) -> None:
        page = await self.controller.fetch_replies(tweet.id)
        replies = [reply for reply in page.tweets if reply.id != tweet.id]
        seen_ids: set[str] = set()
        unique_replies: list[TweetView] = []
        for reply in replies:
            if reply.id in seen_ids:
                continue
            seen_ids.add(reply.id)
            unique_replies.append(reply)
        self._reply_source_tweet = tweet
        self._reply_tweets = unique_replies
        self._reply_index = 0

    async def _enter_reply_context(self, tweet: TweetView) -> None:
        previous_context = None
        if self._reply_mode and self._reply_source_tweet is not None:
            previous_context = ReplyContext(
                source_tweet=self._reply_source_tweet,
                replies=self._reply_tweets.copy(),
                index=self._reply_index,
            )
        await self._load_initial_replies(tweet)
        if not self._reply_tweets:
            self._status = self._status_line(
                f"No replies found for @{tweet.author_handle}."
            )
            if previous_context is not None:
                self._reply_source_tweet = previous_context.source_tweet
                self._reply_tweets = previous_context.replies
                self._reply_index = previous_context.index
            return
        if previous_context is not None:
            self._reply_stack.append(previous_context)
        self._reply_mode = True
        self._status = self._status_line(
            f"Showing reply 1 of {len(self._reply_tweets)} for @{tweet.author_handle}."
        )

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

    def _clamp_reply_index(self, selected_index: int) -> int:
        if not self._reply_tweets:
            return 0
        return max(0, min(selected_index, len(self._reply_tweets) - 1))
