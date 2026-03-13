from pathlib import Path

from xfeed.cookies import load_cookie_mapping


def test_load_cookie_mapping_from_json_list(tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text(
        '[{"name": "auth_token", "value": "abc"}, {"name": "ct0", "value": "def"}]',
        encoding="utf-8",
    )

    parsed = load_cookie_mapping(cookie_file)

    assert parsed == {"auth_token": "abc", "ct0": "def"}


def test_load_cookie_mapping_from_netscape(tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(
        "\n".join(
            [
                "# Netscape HTTP Cookie File",
                ".x.com\tTRUE\t/\tTRUE\t0\tauth_token\tabc",
                ".x.com\tTRUE\t/\tTRUE\t0\tct0\tdef",
            ]
        ),
        encoding="utf-8",
    )

    parsed = load_cookie_mapping(cookie_file)

    assert parsed == {"auth_token": "abc", "ct0": "def"}
