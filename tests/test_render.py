from xfeed.models import FeedMode, MediaItem, TweetView
from xfeed.render import format_media_summary, render_plain_feed


def test_format_media_summary_counts_items() -> None:
    tweet = TweetView(
        id="1",
        author_name="Alice",
        author_handle="alice",
        text="hello",
        created_at="Fri, 13 Mar 2026 12:00:00 +0000",
        url="https://x.com/alice/status/1",
        media=[
            MediaItem(url="https://img/1", kind="photo"),
            MediaItem(url="https://img/2", kind="photo"),
            MediaItem(url="https://img/3", kind="video"),
        ],
    )

    assert format_media_summary(tweet) == "🖼 2 🎞 1"


def test_render_plain_feed_includes_mode_and_url() -> None:
    tweet = TweetView(
        id="1",
        author_name="Alice",
        author_handle="alice",
        text="hello from xfeed",
        created_at="Fri, 13 Mar 2026 12:00:00 +0000",
        url="https://x.com/alice/status/1",
    )

    rendered = render_plain_feed([tweet], mode=FeedMode.FOLLOWING)

    assert "xfeed: following" in rendered
    assert "https://x.com/alice/status/1" in rendered
