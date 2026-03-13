from __future__ import annotations

import shutil
import subprocess
import tempfile
import urllib.request
import sys
import select
import termios
import tty
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from xfeed.models import TweetView


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/134.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://x.com/",
}


def ensure_kitty_available() -> None:
    if shutil.which("kitten") is None:
        raise RuntimeError("Could not find 'kitten' in PATH.")


def select_image(tweet: TweetView, index: int = 0) -> str:
    images = select_images(tweet)
    if not images:
        raise RuntimeError("The selected tweet does not contain an image.")
    if index < 0 or index >= len(images):
        raise RuntimeError(
            f"Image index {index} is out of range for this tweet ({len(images)} images)."
        )
    return images[index]


def select_images(tweet: TweetView) -> list[str]:
    return [
        media.url
        for media in tweet.media
        if media.kind.lower() in {"photo", "image"} and media.url
    ]


def download_image(url: str) -> Path:
    resolved_url = normalize_image_url(url)
    suffix = infer_image_suffix(resolved_url)
    with tempfile.NamedTemporaryFile(prefix="xfeed-", suffix=suffix, delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        request = build_image_request(resolved_url)
        with urllib.request.urlopen(request, timeout=30) as response:
            temp_path.write_bytes(response.read())
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def show_image_with_kitty(image_path: Path) -> None:
    ensure_kitty_available()
    _run_kitty_icat([str(image_path)])


def show_images_with_kitty(image_paths: list[Path]) -> None:
    ensure_kitty_available()
    if not image_paths:
        raise RuntimeError("No images to display.")

    columns, lines = shutil.get_terminal_size(fallback=(120, 40))
    top_margin = 2
    bottom_margin = 4
    gap = 1
    available_height = max(lines - top_margin - bottom_margin, 8)
    slots = len(image_paths)
    per_image_height = max((available_height - (slots - 1) * gap) // slots, 2)
    width = max(columns - 2, 20)

    clear_kitty_images()
    for index, image_path in enumerate(image_paths):
        top = top_margin + index * (per_image_height + gap)
        place = f"{width}x{per_image_height}@1x{top}"
        _run_kitty_icat(
            [
                "--align",
                "left",
                "--place",
                place,
                str(image_path),
            ]
        )


def clear_kitty_images() -> None:
    ensure_kitty_available()
    _run_kitty_icat(["--clear"])


def wait_for_enter(prompt: str) -> None:
    _wait_for_key(prompt, enter_only=True)


def wait_for_keypress(prompt: str) -> None:
    _wait_for_key(prompt, enter_only=False)


def _wait_for_key(prompt: str, *, enter_only: bool) -> None:
    print(prompt, end="", flush=True)
    if not sys.stdin.isatty():
        sys.stdin.readline()
        return

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        termios.tcflush(fd, termios.TCIFLUSH)
        tty.setcbreak(fd)
        while True:
            ready, _, _ = select.select([fd], [], [])
            if not ready:
                continue
            char = sys.stdin.read(1)
            if not enter_only or char in {"\n", "\r"}:
                print()
                return
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _run_kitty_icat(args: list[str]) -> None:
    command = ["kitten", "icat", "--stdin=no", *args]
    try:
        with open("/dev/tty", "rb+", buffering=0) as tty_handle:
            subprocess.run(
                command,
                check=False,
                stdin=tty_handle,
                stdout=tty_handle,
                stderr=tty_handle,
            )
    except OSError:
        subprocess.run(command, check=False)


def build_image_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers=BROWSER_HEADERS)


def normalize_image_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc.endswith("twimg.com"):
        return url

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if parsed.netloc == "pbs.twimg.com":
        if "name" not in query:
            query["name"] = "large"
        if "format" in query and Path(parsed.path).suffix == "":
            parsed = parsed._replace(path=f"{parsed.path}.{query['format']}")
    return urlunparse(parsed._replace(query=urlencode(query)))


def infer_image_suffix(url: str) -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix
    if suffix:
        return suffix

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    image_format = query.get("format", "").strip().lower()
    if image_format:
        return f".{image_format}"
    return ".img"
