from xfeed.models import MediaItem, TweetView
from xfeed.render import (
    format_media_summary,
    render_feed_list,
    render_plain_feed,
    render_quote_detail,
    render_reply_detail,
    render_tweet_detail,
)


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

    rendered = render_plain_feed([tweet], heading="following")

    assert "xfeed: following" in rendered
    assert "https://x.com/alice/status/1" in rendered


def test_render_feed_list_shows_multiple_tweets() -> None:
    tweets = [
        TweetView(
            id="1",
            author_name="Alice",
            author_handle="alice",
            text="first",
            created_at="Fri, 13 Mar 2026 12:00:00 +0000",
            url="https://x.com/alice/status/1",
        ),
        TweetView(
            id="2",
            author_name="Bob",
            author_handle="bob",
            text="second",
            created_at="Fri, 13 Mar 2026 12:05:00 +0000",
            url="https://x.com/bob/status/2",
        ),
    ]

    rendered = render_feed_list(tweets, selected_index=1)

    assert "@alice" in rendered
    assert "@bob" in rendered
    assert "›  2." in rendered


def test_render_feed_list_can_limit_to_one_page() -> None:
    tweets = [
        TweetView(
            id="1",
            author_name="Alice",
            author_handle="alice",
            text="first",
            created_at="Fri, 13 Mar 2026 12:00:00 +0000",
            url="https://x.com/alice/status/1",
        ),
        TweetView(
            id="2",
            author_name="Bob",
            author_handle="bob",
            text="second",
            created_at="Fri, 13 Mar 2026 12:05:00 +0000",
            url="https://x.com/bob/status/2",
        ),
        TweetView(
            id="3",
            author_name="Carol",
            author_handle="carol",
            text="third",
            created_at="Fri, 13 Mar 2026 12:10:00 +0000",
            url="https://x.com/carol/status/3",
        ),
    ]

    rendered = render_feed_list(
        tweets,
        selected_index=1,
        start_index=1,
        max_items=2,
    )

    assert "@alice" not in rendered
    assert "@bob" in rendered
    assert "@carol" in rendered


def test_render_feed_list_respects_narrow_width() -> None:
    tweets = [
        TweetView(
            id="1",
            author_name="Alice",
            author_handle="verylonghandleexample",
            text="This is a long tweet summary that should be truncated to fit.",
            created_at="Fri, 13 Mar 2026 12:00:00 +0000",
            url="https://x.com/alice/status/1",
        )
    ]

    rendered = render_feed_list(tweets, selected_index=0, width=24)

    assert all(len(line) <= 24 for line in rendered.splitlines())


def test_render_tweet_detail_renders_embedded_quoted_tweet() -> None:
    quoted = TweetView(
        id="2",
        author_name="Bob",
        author_handle="bob",
        text="Quoted tweet body",
        created_at="Fri, 13 Mar 2026 13:00:00 +0000",
        url="https://x.com/bob/status/2",
        media=[MediaItem(url="https://img/1", kind="photo")],
    )
    tweet = TweetView(
        id="1",
        author_name="Alice",
        author_handle="alice",
        text="Main tweet",
        created_at="Fri, 13 Mar 2026 12:00:00 +0000",
        url="https://x.com/alice/status/1",
        quoted_tweet=quoted,
    )

    rendered = render_tweet_detail(tweet)

    assert "Quoted Tweet" in rendered
    assert "Bob (@bob)" in rendered
    assert "Quoted tweet body" in rendered
    assert "https://x.com/bob/status/2" in rendered


def test_render_tweet_detail_can_toggle_hidden_text() -> None:
    tweet = TweetView(
        id="1",
        author_name="Alice",
        author_handle="alice",
        text="Short preview",
        full_text="Short preview with the hidden continuation.",
        has_hidden_text=True,
        created_at="Fri, 13 Mar 2026 12:00:00 +0000",
        url="https://x.com/alice/status/1",
    )

    collapsed = render_tweet_detail(tweet)
    expanded = render_tweet_detail(tweet, expanded=True)

    assert "Short preview" in collapsed
    assert "hidden continuation" not in collapsed
    assert "m show more" in collapsed
    assert "Short preview with the hidden continuation." in expanded
    assert "m collapse" in expanded


def test_render_reply_detail_includes_header_and_position() -> None:
    source = TweetView(
        id="1",
        author_name="Alice",
        author_handle="alice",
        text="Source tweet",
        created_at="Fri, 13 Mar 2026 12:00:00 +0000",
        url="https://x.com/alice/status/1",
    )
    reply = TweetView(
        id="3",
        author_name="Carol",
        author_handle="carol",
        text="second reply",
        created_at="Fri, 13 Mar 2026 12:10:00 +0000",
        url="https://x.com/carol/status/3",
    )

    rendered = render_reply_detail(
        source,
        reply,
        reply_index=1,
        loaded_reply_count=2,
    )

    assert "Replies to Alice (@alice)" in rendered
    assert "Reply 2 of 2 loaded" in rendered
    assert "@carol" in rendered


def test_render_reply_detail_keeps_full_reply_text() -> None:
    source = TweetView(
        id="1",
        author_name="Alice",
        author_handle="alice",
        text="Source tweet",
        created_at="Fri, 13 Mar 2026 12:00:00 +0000",
        url="https://x.com/alice/status/1",
    )
    reply = TweetView(
        id="2",
        author_name="Bob",
        author_handle="bob",
        text="This reply body is intentionally long enough to wrap onto multiple lines.",
        created_at="Fri, 13 Mar 2026 12:05:00 +0000",
        url="https://x.com/bob/status/2",
    )

    rendered = render_reply_detail(
        source,
        reply,
        reply_index=0,
        loaded_reply_count=1,
    )

    assert reply.text in rendered


def test_render_quote_detail_includes_source_and_quoted_tweet() -> None:
    source = TweetView(
        id="1",
        author_name="Alice",
        author_handle="alice",
        text="Source tweet",
        created_at="Fri, 13 Mar 2026 12:00:00 +0000",
        url="https://x.com/alice/status/1",
    )
    quoted = TweetView(
        id="2",
        author_name="Bob",
        author_handle="bob",
        text="Quoted body",
        created_at="Fri, 13 Mar 2026 12:05:00 +0000",
        url="https://x.com/bob/status/2",
    )

    rendered = render_quote_detail(source, quoted)

    assert "Quote from Alice (@alice)" in rendered
    assert "https://x.com/alice/status/1" in rendered
    assert "Bob (@bob)" in rendered
    assert "Quoted body" in rendered
