from __future__ import annotations

import argparse
import asyncio
import sys

from xfeed.config import SessionStore
from xfeed.cookies import load_cookie_mapping
from xfeed.feed import FeedController
from xfeed.media import (
    clear_kitty_images,
    download_image,
    select_image,
    select_images,
    show_images_with_kitty,
    wait_for_enter,
)
from xfeed.models import FeedMode
from xfeed.providers import TwikitProvider
from xfeed.render import render_plain_feed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xfeed",
        description="A simple terminal-first X feed reader.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_parser = subparsers.add_parser("auth", help="Manage the local X session.")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command", required=True)
    auth_import = auth_subparsers.add_parser(
        "import-cookies",
        help="Import browser-exported cookies into the local session store.",
    )
    auth_import.add_argument("path", help="Path to a cookie export file.")

    home = subparsers.add_parser("home", help="Read the home timeline.")
    home.add_argument(
        "--mode",
        choices=[FeedMode.FOLLOWING.value, FeedMode.FOR_YOU.value],
        default=FeedMode.FOLLOWING.value,
        help="Timeline mode to read.",
    )
    home.add_argument(
        "--count",
        type=int,
        default=20,
        help="Number of tweets to fetch per page.",
    )
    home.add_argument(
        "--plain",
        action="store_true",
        help="Print a plain terminal snapshot instead of launching the TUI.",
    )

    show_image = subparsers.add_parser(
        "show-image",
        help="Display tweet images with kitten icat.",
    )
    show_image.add_argument("tweet_id", help="The tweet id to display media for.")
    show_image.add_argument(
        "--index",
        type=int,
        default=-1,
        help="Zero-based image index to display, or omit to show all images.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return dispatch(args)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def dispatch(args: argparse.Namespace) -> int:
    if args.command == "auth" and args.auth_command == "import-cookies":
        cookies = load_cookie_mapping(args.path)
        session_path = SessionStore().save_cookies(cookies)
        print(f"Saved {len(cookies)} cookies to {session_path}")
        return 0

    if args.command == "home":
        mode = FeedMode.from_cli(args.mode)
        if args.plain:
            return asyncio.run(run_plain_home(mode=mode, count=args.count))
        return run_tui_home(mode=mode, count=args.count)

    if args.command == "show-image":
        return asyncio.run(run_show_image(tweet_id=args.tweet_id, index=args.index))

    raise RuntimeError(f"Unsupported command: {args.command}")


async def run_plain_home(*, mode: FeedMode, count: int) -> int:
    controller = build_controller(mode=mode, count=count)
    tweets = await controller.load_initial()
    print(render_plain_feed(tweets, mode=mode))
    return 0


def run_tui_home(*, mode: FeedMode, count: int) -> int:
    from xfeed.ui import FeedApp

    controller = build_controller(mode=mode, count=count)
    app = FeedApp(controller)
    app.run()
    return 0


async def run_show_image(*, tweet_id: str, index: int) -> int:
    controller = build_controller(mode=FeedMode.FOLLOWING, count=20)
    tweet = await controller.fetch_tweet(tweet_id)
    if index >= 0:
        image_urls = [select_image(tweet, index=index)]
    else:
        image_urls = select_images(tweet)
    image_paths = [download_image(image_url) for image_url in image_urls]
    try:
        show_images_with_kitty(image_paths)
        wait_for_enter("Press Enter to return...")
    finally:
        clear_kitty_images()
        for image_path in image_paths:
            image_path.unlink(missing_ok=True)
    return 0


def build_controller(*, mode: FeedMode, count: int) -> FeedController:
    cookies = SessionStore().load_cookies()
    provider = TwikitProvider(cookies)
    return FeedController(provider, mode=mode, page_size=count)


if __name__ == "__main__":
    raise SystemExit(main())
