---
quick_id: 260725-rrc
description: Fix focus() opening the wrong claude session (tmux switch-client)
date: 2026-07-25
mode: quick
---

# Quick Task 260725-rrc: focus() opens the wrong claude session

## Problem

Pressing Enter in the TUI (and clicking a tray menu row, and clicking a
notification) focuses the wrong Claude session whenever the target lives in a
tmux session other than the one the user is attached to.

`ClaudeIndicator.focus()` (`claude-monitor.py:122-134`) ran:

```
tmux select-window -t <pane>
tmux select-pane   -t <pane>
wmctrl -x -a com.mitchellh.ghostty
```

with `TMUX` exported from the session record. Two independent defects:

1. `select-window` only changes the *current window of the pane's own tmux
   session*. It never moves the user's attached client. With two tmux sessions
   (one per Ghostty window), the client the user is looking at stays put and
   nothing visible happens.
2. `wmctrl -x -a <class>` then raises an arbitrary Ghostty window -- both
   windows share one PID and one WM_CLASS -- so the *other* Claude ends up on
   screen.

All three entry points (TUI Enter, tray menu, notification action) route
through `focus()`, so one fix covers them.

## Tasks

### 1. Add `core.focus_tmux_cmds(pane, tmux)`

- files: `claude_monitor/core.py`
- action: pure helper returning the argv sequence
  `switch-client` -> `select-window` -> `select-pane`, each `-t <pane>`, with
  the server addressed via `-S <socket>` (first field of the session's `TMUX`
  value) instead of an exported `TMUX` env var. Exporting `TMUX` names a
  current session, which makes tmux resolve the default client to one already
  attached *there* -- exactly the client that does not need moving.
- verify: `just selfcheck`
- done: helper exists, is pure, and is import-clean.

### 2. Use it in `focus()` and stop the blind raise

- files: `claude-monitor.py`
- action: drive the tmux calls from `focus_tmux_cmds`; skip the
  `wmctrl -x -a GHOSTTY_CLASS` raise when `terminal_focused()` is already true,
  since that raise can yank the other Ghostty window and undo the switch. Leave
  a `ponytail:` comment recording the residual ambiguity (tray click with the
  terminal unfocused still cannot tell which X window hosts which tmux client;
  upgrade path is tmux `set-titles on` + title-based wmctrl matching).
- verify: `just selfcheck`, `just lint`, `just restart`, then Enter on a
  session in the other tmux session.
- done: the attached client moves to the target session/window/pane.

### 3. Cover the argv in the selfcheck suite

- files: `claude_monitor/test_claude_monitor.py`
- action: assert the verb order, the `-S <socket>` prefix, the `-t <pane>`
  suffix, and the no-`TMUX` fallback.
- verify: `just selfcheck` exits 0.
- done: a regression that drops `switch-client` fails the gate.

## Out of scope

Mapping an X window to the tmux client it hosts. Ghostty serves every window
from a single process, so neither PID nor WM_CLASS distinguishes them; the only
reliable handle is the window title, which needs `set-titles on` in the user's
tmux.conf. Recorded as the upgrade path in the `ponytail:` comment.
