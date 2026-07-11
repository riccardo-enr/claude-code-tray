# claude-code-tray

A GNOME top-bar tray indicator for [Claude Code](https://claude.com/claude-code).
At a glance from the top bar it shows:

- **Per-session status** (`running` / `waiting` / `done`); on click it jumps to
  the tmux pane that fired the session and raises the terminal window.
- **Token usage & quota** for the rolling 5-hour window — tokens used vs. limit
  and percent, time until reset, and burn rate — read from the `claude-monitor`
  usage CLI.
- **A `!` attention badge** whenever a session is waiting on you or has just
  finished, plus a usage-percent badge that flags high usage.

Built for Ubuntu GNOME on X11 with tmux + Ghostty, but the terminal is
configurable.

## Why

Claude Code hook processes are short-lived, so a per-hook `notify-send` can't
reliably handle a notification click (the process exits before the click
arrives). A single long-lived helper owns the tray and does the focusing;
hooks just push events at it over a unix socket.

## How it works

```
Claude Code hook ──(JSON over unix socket)──> claude-monitor.py ──> tray menu
  claude-send.py {running|waiting|done|end}        (long-lived)      click -> focus
```

- `claude-monitor.py` — long-lived helper: draws the AppIndicator tray menu,
  tracks sessions by `session_id`, focuses on click, and polls the
  `claude-monitor` usage CLI on a background thread (so the multi-second CLI
  call never blocks the UI).
- `claude-send.py` — tiny non-blocking hook sender; silent if the helper is down.

### The icon badge

The top-bar label combines two signals (ASCII, so it works in any theme):

| Label | Meaning |
|-------|---------|
| `16%` | Current 5-hour usage (always shown when available) |
| `83%!` | Usage above the high threshold (default 80%) |
| `16% 2!` | Usage, plus 2 sessions that need you (waiting or just finished) |

The `!` attention count clears when you **switch to that session's pane**
(auto, within ~2s), **click** its menu row, or **reply** in it (it goes back to
`running`). If you're already looking at the pane when a session finishes, no
`!` is raised.

### Usage rows

The menu shows three rows from the `claude-monitor` CLI, for example:

```
149k / 926k (16%)     tokens used / limit (percent of the 5-hour limit)
resets in 2h 11m      time until the rolling window resets
burn: 12.4k tok/hr    current burn rate
```

The percent can exceed 100% — that just means you are over the (estimated)
window limit; it is not clamped. If the CLI is missing, slow, or returns junk,
these degrade to a single `usage unavailable` row while session status and
click-to-focus keep working.

## Requirements

- GNOME with the AppIndicator extension (`gnome-shell-extension-appindicator`,
  active by default on Ubuntu).
- `python3` + PyGObject with `Gtk 3.0` and `AyatanaAppIndicator3 0.1` typelibs
  (`gir1.2-ayatanaappindicator3-0.1`).
- The `claude-monitor` usage CLI (Claude Code Usage Monitor) installed at
  `~/.local/bin/claude-monitor` — e.g. `uv tool install claude-monitor`. Only
  needed for the usage rows/badge; without it they show `usage unavailable`.
- `tmux` (pane switching) and `wmctrl` (X11 window raise). Both optional —
  click-to-focus degrades gracefully without them.
- `xprop` (X11) — optional; used to detect when you are already looking at a
  session's pane so its `!` is suppressed / auto-cleared.

## Install

```sh
./install.sh
```

Then merge `settings.hooks.json` into the `hooks` object of
`~/.claude/settings.json`, and start the helper (the installer prints the
exact command). It auto-starts on future logins via the installed
`~/.config/autostart/claude-monitor.desktop`.

## Config (env vars)

| Var | Default | Purpose |
|-----|---------|---------|
| `CLAUDE_TRAY_ICON` | `claude-desktop` | Tray icon name from your theme |
| `CLAUDE_TRAY_WM_CLASS` | `com.mitchellh.ghostty` | Terminal WM_CLASS to raise on click |
| `CLAUDE_TRAY_PLAN` | `custom` | `claude-monitor` plan to query. `custom` = session-based dynamic (P90) limits, matching the CLI's own default; also `max5` / `max20` / `pro`; empty = the CLI's saved default (not recommended — it drifts) |
| `CLAUDE_TRAY_POLL_INTERVAL` | `15` | Seconds between usage polls. The CLI itself takes ~5-10s, so that is the practical floor |

Set these in the autostart `.desktop`'s `Exec=` line to make them persist.

## Honesty

This project is heavily vibe-coded — built interactively with Claude Code in a
single session, then organized with the [Get Shit Done (GSD)](https://github.com/opengsd/gsd-core)
framework. It works on my setup (Ubuntu GNOME / X11 / tmux / Ghostty) but hasn't
been battle-tested elsewhere. No CI; the only test is the pure parse/format
self-check (`python3 claude-monitor.py --selfcheck`). PRs and bug reports welcome.

## License

MIT
