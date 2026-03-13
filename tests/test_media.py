from xfeed.media import (
    BROWSER_HEADERS,
    build_image_request,
    infer_image_suffix,
    normalize_image_url,
    select_images,
)
from xfeed.models import MediaItem, TweetView


def test_normalize_image_url_sets_large_name_and_suffix_for_pbs() -> None:
    url = "https://pbs.twimg.com/media/AbCdEf?format=jpg"

    normalized = normalize_image_url(url)

    assert normalized == "https://pbs.twimg.com/media/AbCdEf.jpg?format=jpg&name=large"


def test_infer_image_suffix_uses_query_format_when_path_has_none() -> None:
    url = "https://pbs.twimg.com/media/AbCdEf?format=png&name=small"

    assert infer_image_suffix(url) == ".png"


def test_build_image_request_uses_browser_headers() -> None:
    request = build_image_request("https://pbs.twimg.com/media/AbCdEf.jpg")

    assert request.full_url == "https://pbs.twimg.com/media/AbCdEf.jpg"
    assert request.get_header("User-agent") == BROWSER_HEADERS["User-Agent"]
    assert request.get_header("Referer") == BROWSER_HEADERS["Referer"]


def test_select_images_returns_only_image_media() -> None:
    tweet = TweetView(
        id="1",
        author_name="Alice",
        author_handle="alice",
        text="hello",
        created_at="Fri, 13 Mar 2026 12:00:00 +0000",
        url="https://x.com/alice/status/1",
        media=[
            MediaItem(url="https://img/1.jpg", kind="photo"),
            MediaItem(url="https://img/2.mp4", kind="video"),
            MediaItem(url="https://img/3.png", kind="image"),
        ],
    )

    assert select_images(tweet) == ["https://img/1.jpg", "https://img/3.png"]
