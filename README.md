# xfeed

`xfeed` is an X (previously known as twitter) timeline reader built around an authenticated web session using twikit instead of X api.

## What it does

- Reads your `Following` or `For You` home timeline.
- Shows tweets in a simple split-pane TUI.
- Displays images only when you explicitly request them (requires kitty supported terminal).

## Install

Install virtual environment and dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

To install system-wide use pipx
```bash
pipx install .
```

## Import cookies

Log into X on a browser, and export the cookies using a browser extension.

Import them:

```bash
xfeed import-cookies ~/Downloads/cookies.json
```

Supported import formats:

- `twikit` cookie JSON (`{"auth_token": "...", ...}`)
- Browser-exported JSON cookie lists
- Netscape cookie jar files

## Read your feed

Launch the interactive TUI:

```bash
xfeed home
```

Read a plain terminal dump:

```bash
xfeed home --plain
```

Switch timeline mode:

```bash
xfeed home --mode for-you
```

Read a specific user's timeline:

```bash
xfeed user elonmusk
```

Choose which user feed to load:

```bash
xfeed user jack --feed replies
xfeed user nasa --feed media --plain
```

## Keys

- `j` / `k` / `Up` / `Down`: move selection
- `p`: show the previous page of newer tweets
- `n`: show the next page of older tweets
- `r`: refresh newer tweets
- `f`: toggle timeline mode or user feed type
- `Enter`: enter reply mode for the selected tweet or reply
- `Left` / `Right`: move between loaded replies while in reply mode
- `Backspace`: go back one reply level
- `Esc`: exit reply mode entirely
- `m`: expand or collapse hidden tweet text when available
- `i`: display the selected tweet's first image with `kitten icat`
- `o`: open the selected tweet in a browser
- `q`: quit

## Notes

- This project uses unofficial web-session access and may break if X changes its internal behavior.
- Session cookies are stored locally under your XDG config directory.
