from __future__ import annotations

from email.utils import parsedate_to_datetime
from textwrap import shorten

from xfeed.models import FeedMode, TweetView


def render_plain_feed(tweets: list[TweetView], *, mode: FeedMode) -> str:
    lines = [f"xfeed: {mode.value}", ""]
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


def render_feed_list(tweets: list[TweetView], *, selected_index: int, width: int = 48) -> str:
    if not tweets:
        return "No tweets loaded yet."
    lines: list[str] = []
    body_width = max(width - 16, 20)
    for index, tweet in enumerate(tweets):
        marker = "›" if index == selected_index else " "
        handle = f"@{tweet.author_handle}"
        summary = shorten(_single_line(tweet.text), width=body_width, placeholder="...")
        lines.append(f"{marker} {index + 1:>2}. {handle:<18} {summary}")
        meta = f"{format_timestamp(tweet.created_at)}  {format_media_summary(tweet)}"
        lines.append(f"    {shorten(meta, width=max(width - 4, 20), placeholder='...')}")
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
        lines.append(
            f"@{tweet.quoted_tweet.author_handle}: "
            f"{shorten(_single_line(tweet.quoted_tweet.text), width=120, placeholder='...')}"
        )
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
