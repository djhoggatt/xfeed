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
xfeed auth import-cookies ~/Downloads/cookies.json
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

## Keys

- `j` / `k` / `Up` / `Down`: move selection
- `r`: refresh newer tweets
- `n`: fetch older tweets
- `f`: toggle timeline mode
- `i`: display the selected tweet's first image with `kitten icat`
- `o`: open the selected tweet in a browser
- `q`: quit

## Notes

- This project uses unofficial web-session access and may break if X changes its internal behavior.
- Session cookies are stored locally under your XDG config directory.
