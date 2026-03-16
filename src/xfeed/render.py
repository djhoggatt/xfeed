from __future__ import annotations

from email.utils import parsedate_to_datetime
from textwrap import shorten

from rich.cells import set_cell_size

from xfeed.models import TweetView


def render_plain_feed(tweets: list[TweetView], *, heading: str) -> str:
    lines = [f"xfeed: {heading}", ""]
    for index, tweet in enumerate(tweets, start=1):
        summary = shorten(_single_line(tweet.text), width=88, placeholder="...")
        lines.append(
            f"{index:>2}. @{tweet.author_handle}  {summary}"
        )
        lines.append(
            "    "
            f"{format_timestamp(tweet.created_at)}  "
            f"{_format_counts(tweet)}  "
            f"{format_media_summary(tweet)}"
        )
        lines.append(f"    {tweet.url}")
        lines.append("")
    return "\n".join(lines).rstrip()


def render_feed_list(
    tweets: list[TweetView],
    *,
    selected_index: int,
    width: int = 48,
    start_index: int = 0,
    max_items: int | None = None,
) -> str:
    if not tweets:
        return "No tweets loaded yet."
    lines: list[str] = []
    available_width = max(width, 20)
    end_index = len(tweets) if max_items is None else start_index + max_items
    for index, tweet in enumerate(tweets[start_index:end_index], start=start_index):
        marker = "›" if index == selected_index else " "
        prefix = f"{marker} {index + 1:>2}. "
        body_width = max(available_width - len(prefix), 12)
        handle_width = min(18, max(body_width // 3, 8))
        summary_width = max(body_width - handle_width - 1, 4)
        handle = set_cell_size(f"@{tweet.author_handle}", handle_width)
        summary = set_cell_size(
            shorten(_single_line(tweet.text), width=summary_width, placeholder="..."),
            summary_width,
        )
        lines.append(f"{prefix}{handle} {summary}")
        meta = f"{format_timestamp(tweet.created_at)}  {format_media_summary(tweet)}"
        meta_width = max(available_width - 4, 8)
        lines.append(
            "    "
            + set_cell_size(
                shorten(meta, width=meta_width, placeholder="..."),
                meta_width,
            )
        )
    return "\n".join(lines)


def render_tweet_detail(tweet: TweetView) -> str:
    lines = [
        f"{tweet.author_name} (@{tweet.author_handle})",
        format_timestamp(tweet.created_at),
        tweet.url,
        "",
    ]
    if tweet.retweeted_by:
        lines.append(f"Retweeted by {tweet.retweeted_by}")
        lines.append("")
    if tweet.in_reply_to:
        lines.append(f"Replying to {tweet.in_reply_to}")
        lines.append("")
    lines.append(tweet.text or "[no text]")
    lines.append("")
    lines.append(_format_counts(tweet))
    if tweet.media:
        lines.append("")
        lines.append("Media")
        for index, media in enumerate(tweet.media, start=1):
            size = ""
            if media.width and media.height:
                size = f" ({media.width}x{media.height})"
            lines.append(f"{index}. {media_kind_label(media.kind)}{size}")
            lines.append(f"   {media.url}")
    if tweet.quoted_tweet is not None:
        lines.append("")
        lines.append("Quoted Tweet")
        lines.extend(_render_embedded_tweet(tweet.quoted_tweet))
    return "\n".join(lines)


def render_reply_detail(
    source_tweet: TweetView,
    reply: TweetView | None,
    *,
    reply_index: int = 0,
    loaded_reply_count: int = 0,
) -> str:
    lines = [
        f"Replies to {source_tweet.author_name} (@{source_tweet.author_handle})",
        source_tweet.url,
    ]
    if reply is None:
        lines.extend(["", "No replies loaded."])
        return "\n".join(lines)

    lines.append(f"Reply {reply_index + 1} of {max(loaded_reply_count, reply_index + 1)} loaded")
    lines.append("")
    lines.append(render_tweet_detail(reply))
    return "\n".join(lines)


def format_media_summary(tweet: TweetView) -> str:
    if not tweet.media:
        return "·"
    counts: dict[str, int] = {}
    for media in tweet.media:
        key = media_kind_bucket(media.kind)
        counts[key] = counts.get(key, 0) + 1
    parts = [f"{media_kind_icon(kind)}{count}" for kind, count in sorted(counts.items())]
    return " ".join(parts)


def format_timestamp(raw: str) -> str:
    if not raw:
        return "unknown time"
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        return raw
    if parsed.tzinfo is None:
        return parsed.isoformat(sep=" ", timespec="minutes")
    local = parsed.astimezone()
    return local.strftime("%Y-%m-%d %H:%M")


def _format_counts(tweet: TweetView) -> str:
    return (
        f"💬 {tweet.reply_count}  "
        f"🔁 {tweet.retweet_count}  "
        f"♥ {tweet.like_count}  "
        f"❝ {tweet.quote_count}"
    )


def _single_line(value: str) -> str:
    return " ".join(value.split())


def _render_embedded_tweet(tweet: TweetView) -> list[str]:
    lines = [
        f"  {tweet.author_name} (@{tweet.author_handle})",
        f"  {format_timestamp(tweet.created_at)}",
        f"  {tweet.url}",
        "",
    ]
    lines.extend(f"  {line}" if line else "" for line in (tweet.text or "[no text]").splitlines())
    if tweet.media:
        lines.append("")
        lines.append(f"  Media: {format_media_summary(tweet)}")
    return lines


def media_kind_icon(kind: str) -> str:
    normalized = media_kind_bucket(kind)
    if normalized in {"photo", "image"}:
        return "🖼 "
    if normalized == "video":
        return "🎞 "
    if normalized == "animated_gif":
        return "🎬 "
    return "📎 "


def media_kind_label(kind: str) -> str:
    normalized = media_kind_bucket(kind)
    if normalized in {"photo", "image"}:
        return "🖼 image"
    if normalized == "video":
        return "🎞 video"
    if normalized == "animated_gif":
        return "🎬 gif"
    return f"📎 {kind}"


def media_kind_bucket(kind: str) -> str:
    normalized = kind.lower()
    if normalized in {"photo", "image"}:
        return "image"
    return normalized
