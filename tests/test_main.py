from io import StringIO

from xfeed.main import build_parser, reset_terminal_display


def test_user_command_parses_screen_name_and_feed() -> None:
    parser = build_parser()

    args = parser.parse_args(["user", "@alice", "--feed", "replies", "--count", "25"])

    assert args.command == "user"
    assert args.screen_name == "@alice"
    assert args.feed == "replies"
    assert args.count == 25
    assert args.plain is False


def test_reset_terminal_display_writes_clear_escape_sequence() -> None:
    stream = StringIO()

    reset_terminal_display(stream)

    assert stream.getvalue() == "\033[2J\033[3J\033[H"
