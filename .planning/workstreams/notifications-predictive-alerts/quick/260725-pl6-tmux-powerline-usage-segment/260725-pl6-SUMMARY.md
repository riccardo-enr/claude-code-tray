---
id: 260725-pl6
slug: tmux-powerline-usage-segment
status: complete
seed: SEED-008
completed: 2026-07-25
commits:
  - 54c5c42 feat(statusline): tmux-powerline segment for Claude Code quota
  - a6f4848 docs(statusline): record why click-to-close is not implementable
---

# Summary: tmux-powerline usage segment

Shipped. The left tmux status line now carries `CC 40% 21m` -- 5h usage percent and
time until that window resets -- sourced from the tray daemon that was already
running. No new poller, no second source of truth.

## What was built

| File | Change |
|---|---|
| `claude_monitor/core.py` | `fmt_countdown_short`, `statusline_text` (both pure, both under `--selfcheck`) |
| `claude_monitor/test_claude_monitor.py` | 19 asserts incl. the None / absent-reset / band-edge branches |
| `claude-status.py` | new root script: socket first, history file fallback, tmux colour + click range |
| `tmux/claude_usage.sh` | new tmux-powerline segment (`run_segment()` contract) |
| `install.sh` | symlinks the script; installs the segment only if a tmux-powerline segments dir exists |

Display is percent + reset only. Burn rate, cost and model mix stay in the tray
dropdown and the dashboard, which already show them.

## Verified

- `just selfcheck` green, `just lint` clean, `shellcheck` clean on both shell files.
- All three data paths exercised live: socket (`CC 29% 40m`), history fallback with the
  socket removed (`CC 29% 39m`, one poll staler as expected), and no-data -> no output,
  exit 1 -> segment hides.
- Cross-checked against `claude-tui --once`: both reported the same 5h percent.
- Rendered through the real `powerline.sh left`, separators drawn by the framework.
- ~56ms per invocation against a 2s `status-interval`; no cache needed.

## Decisions

- **Segment, not `status-left`.** `status-left` is owned by `erikw/tmux-powerline`
  (`tmux.conf:107`); overriding it would have deleted the user's whole powerline.
- **Dark chip.** First wired as `claude_usage 115 235` (teal). Wrong: the theme args are
  `bg fg`, so a light chip would have rendered the peach/red overrides at poor contrast.
  Changed to `238 189`, matching `git_status`, the other dynamically-coloured segment.
- **`band()` thresholds, not `USAGE_THRESHOLD`.** The badge threshold is the user's
  "warn me" setting; the segment wants the fixed proximity-to-cap meaning the TUI's
  colour bands already carry, so glyph and colour cannot disagree.
- **No cache, no `fetch_usage()`.** The latter shells out to the CLI for 5-10s and stays
  the daemon's alone.

## Click-to-close: closed as not implementable

The segment is a click target (`#[range=user|claude_usage]`) and opens the popup. Making
a second click close it was attempted twice and abandoned on evidence:

1. First with a `pgrep`/`pkill` toggle -- blunt, could not tell a popup instance from a
   `claude-tui` in an ordinary pane.
2. Then with the popup-session pattern (`tmux-floax` / `tmux-toggle-popup` style,
   dedicated session name as the handle). Along the way three real tmux gotchas surfaced
   and are worth remembering: `set-option` rejects the `=NAME` exact-match target,
   `display-message -t` takes a target-PANE so a session name yields an empty string
   (`list-sessions -F` is the dependable ask), and `run-shell` needs `-b` or the server
   blocks.

Neither worked, because the premise is false. tmux's `popup_key_cb()` bounds-checks the
pointer and returns 0 ("handled, do nothing") for any click outside the popup rect, before
the key tables are consulted -- byte-identical across 3.2 to 3.6, confirmed by driving
synthetic SGR mouse events at a real pty client. With `-E`, keyboard bindings do not fire
from inside a popup either, re-issuing `display-popup` while one is open is a silent no-op,
and no format exposes popup state, so tmux config cannot branch on it.

Reverted to plain open-on-click; `q` closes. The reasoning is recorded in
`tmux/claude_usage.sh` so it is not rediscovered.

## Outside this repo

The user's dotfiles (`~/.dotfiles`, stow-managed) were edited and are left uncommitted
for them to review:

- `tmux/.config/tmux-powerline/themes/riccardo.sh` -- added `"claude_usage 238 189"`.
- `tmux/.config/tmux/tmux.conf` -- click-to-open branch on the existing
  `MouseDown1Status` binding.
- `tmux/.config/tmux-powerline/segments/claude_usage.sh` -- a symlink into this repo's
  checkout. Machine-specific by nature; `install.sh` recreates it.

## Follow-up worth a seed

Claude Code ships a native `statusLine` hook that pipes `rate_limits` (5h/7d percent and
`resets_at`) from Anthropic on stdin. It could replace the daemon's CLI shell-out entirely.
Noted in SEED-008; not in this task's scope.
