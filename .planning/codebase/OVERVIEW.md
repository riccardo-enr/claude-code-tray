# Codebase Overview — claude-code-tray

_Mapped: 2026-07-11 — 2 Python files (~168 lines) + install/docs. Single-doc map (repo is trivially small)._

A GNOME top-bar tray indicator for Claude Code sessions. Claude Code hooks push
per-session status events to a long-lived helper over a unix socket; the helper
renders them in an AppIndicator tray menu and focuses the originating tmux
pane + terminal window on click.

## Stack

- **Language/runtime:** Python 3 (stdlib only for logic: `os`, `json`, `socket`,
  `threading`, `subprocess`).
- **GUI:** PyGObject (`gi`) with `Gtk 3.0` and `AyatanaAppIndicator3 0.1` typelibs.
- **No package manager / deps file:** relies on system-provided PyGObject +
  typelibs (`gir1.2-ayatanaappindicator3-0.1`). No `requirements.txt`/`pyproject`.
- **External commands:** `tmux` (pane switch), `wmctrl` (X11 window raise).
- **Platform assumptions:** GNOME on X11, AppIndicator extension active.

## Architecture

Two decoupled processes, one direction of data flow:

```
Claude Code hook ──JSON line──> unix socket ──> claude-monitor.py (long-lived)
  claude-send.py {running|waiting|done|end}        tray menu; click -> focus
```

- **`claude-monitor.py`** — long-lived helper. `Monitor` class owns the tray
  indicator and a `sessions` dict keyed by `session_id`. A daemon thread
  (`serve`) accepts socket connections, parses newline-delimited JSON, and
  marshals each event onto the Gtk main thread via `GLib.idle_add(mon.handle)`.
  `handle` updates session state; `rebuild_menu` redraws the menu and sets a
  `N!` label when sessions are `waiting`. `focus` runs `tmux select-window/
  select-pane` then `wmctrl -x -a <WM_CLASS>`.
- **`claude-send.py`** — fire-and-forget sender invoked by each hook. Reads the
  hook JSON on stdin, tags it with `TMUX_PANE`/`TMUX` from the environment,
  connects to the socket with a 0.5s timeout, sends one line, exits. Silent on
  any failure so it never blocks a hook.

**Why split this way:** hook processes are too short-lived to own a tray or
handle a click; the socket lets them be stateless and instant while a single
persistent process holds all UI state.

## Structure

| Path | Role |
|------|------|
| `claude-monitor.py` | Long-lived tray helper (installed to `~/.claude/hooks/`) |
| `claude-send.py` | Non-blocking hook -> socket sender |
| `install.sh` | Copies scripts to `~/.claude/hooks/`, writes autostart `.desktop`, prints hook config |
| `settings.hooks.json` | The 4 hooks to merge into `~/.claude/settings.json` |
| `README.md` | Rationale, requirements, install, config table |
| `LICENSE` | MIT |

Runtime install targets (not in repo): `~/.claude/hooks/claude-monitor.py`,
`~/.claude/hooks/claude-send.py`, `~/.config/autostart/claude-monitor.desktop`.

## Conventions

- Codedoc-style module docstrings (triple-quoted prose header per user CLAUDE.md).
- Config via env vars with sensible defaults: `CLAUDE_TRAY_ICON`,
  `CLAUDE_TRAY_WM_CLASS`; socket at `$XDG_RUNTIME_DIR/claude-monitor.sock`.
- Defensive by default: sender swallows all exceptions; `focus` sends errors to
  `/dev/null`; unknown/garbage socket lines are skipped.
- ASCII-only, minimal inline comments, stdlib-first.

## Integrations

- **Claude Code hooks** (the producer): `UserPromptSubmit`->running,
  `Notification`->waiting, `Stop`->done, `SessionEnd`->end.
- **tmux** — pane targeting via pane id + `TMUX` socket path from the event.
- **wmctrl** — raises the terminal window by `WM_CLASS` (X11 only).
- **GNOME AppIndicator/Ayatana** — the tray surface.

## Concerns / Notes

- **Testing:** none. No test files, no CI. Acceptable at this size; a smoke test
  that boots the monitor and asserts the socket binds would be the first add.
- **X11-only focus:** `wmctrl` window-raise won't work on Wayland (tmux pane
  switch still would). Not guarded/detected.
- **Icon fallback is documented but not implemented:** the comment in
  `claude-monitor.py:24` says it "falls back to a generic terminal icon," but
  there's no actual fallback — a missing `claude-desktop` icon just renders blank.
- **Dead field:** the socket message still carries `message` (used by the removed
  notification path); `claude-send.py` sends it and `handle` ignores it. Harmless.
- **In-memory state:** sessions live only in the running process; a monitor
  restart forgets active sessions until their next hook fires. By design.
- **Single-instance socket:** `serve` unlinks and rebinds the socket on start, so
  a second monitor silently steals it from the first. Fine for autostart; noted.
