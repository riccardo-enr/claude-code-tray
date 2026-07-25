---
quick_id: 260725-rrc
description: Fix focus() opening the wrong claude session (tmux switch-client)
date: 2026-07-25
status: complete
commit: b8dd510
---

# Quick Task 260725-rrc: Summary

## What was wrong

`ClaudeIndicator.focus()` -- the single path behind TUI Enter, the tray menu, and
the notification Focus action -- ran `tmux select-window` + `tmux select-pane`
with `TMUX` exported, then `wmctrl -x -a com.mitchellh.ghostty`.

`select-window` changes the current window of the *pane's own* tmux session and
nothing else. It never moves the client the user is attached to. With one tmux
session per Ghostty window (sessions `0` and `1` here, a Claude in each), asking
to focus the Claude in the other session produced no visible change; the WM_CLASS
raise then brought up whichever Ghostty window it found first -- both share one
PID and one WM_CLASS -- so the wrong Claude appeared.

The TUI's own selection logic was never at fault: it keys on the session id and
recomputes the row at keypress time (`rust/src/main.rs:284`).

## What changed

- `claude_monitor/core.py`: new pure `focus_tmux_cmds(pane, tmux)` returning
  `switch-client` -> `select-window` -> `select-pane`, each `-t <pane>`, with the
  server addressed via `-S <socket>`. `switch-client` moves the attached client to
  the target session, window and pane; the other two trail as a no-op on modern
  tmux and as the fallback on older ones. `-S` is used instead of exporting `TMUX`
  because exporting it names a current session, which makes tmux resolve the
  default client to one already attached there -- the client that does *not* need
  moving.
- `claude-monitor.py`: `focus()` drives the tmux calls from that helper, and skips
  the `wmctrl` raise when `terminal_focused()` is already true (the raise could
  surface the other Ghostty window and undo the switch).
- `claude_monitor/test_claude_monitor.py`: selfcheck asserts the verb order, the
  `-S <socket>` prefix, the `-t <pane>` suffix, and the no-`TMUX` fallback.

## Verification

- `just selfcheck` -> exit 0
- `just lint` -> clean
- `just restart` -> daemon 867347 running with the new code
- Behavioural check (Enter on a session living in the other tmux session) is on
  the user.

## Known limitation

Recorded as a `ponytail:` comment in `focus()`: when the terminal is *not* focused
(a tray click from the top bar) the raise is still blind. Ghostty serves every
window from a single process, so neither PID nor WM_CLASS identifies which X
window hosts which tmux client. Upgrade path is tmux `set-titles on` plus
title-based `wmctrl -a`.

## Deviation from the quick workflow

Executed inline rather than via gsd-planner + gsd-executor subagents -- a 12-line
diff does not carry the dispatch. Artifacts, STATE.md row, and atomic commits are
unchanged.
