# claude-code-tray

A GNOME top-bar tray indicator for
[Claude Code](https://claude.com/claude-code). At a glance from the top bar it
shows:

- **Per-session status** (`running` / `waiting` / `done`); on click it jumps to
  the tmux pane that fired the session and raises the terminal window.
- **Token usage & quota** for the rolling 5-hour *and* 7-day windows — tokens
  used vs. limit and percent, time until reset, burn rate, and a projection of
  where you will land at reset — read from the `claude-monitor` usage CLI.
- **A `!` attention badge** whenever a session is waiting on you or has just
  finished, plus a usage-percent badge that flags high usage on either cap.
- **Usage history and trends** — every poll is appended to a bounded JSONL
  store, surfaced as an in-menu sparkline, a browsable HTML dashboard, and a
  terminal dashboard.
- **Desktop notifications** when a session needs you or a quota is about to run
  out.

Built for Ubuntu GNOME on X11 with tmux + Ghostty, but the terminal is
configurable.

## Why

Claude Code hook processes are short-lived, so a per-hook `notify-send` can't
reliably handle a notification click (the process exits before the click
arrives). A single long-lived helper owns the tray and does the focusing; hooks
just push events at it over a unix socket.

## How it works

```
Claude Code hook ──(JSON over unix socket)──> claude-monitor.py ──> tray menu
  claude-send.py {running|waiting|done|end}        (long-lived)      click -> focus
                                                        │
                        {"query":"snapshot"} ───────────┤──> claude-tui      (terminal)
                        one line out, one back          └──> dashboard.html  (browser)
```

- `claude-monitor.py` — long-lived helper: draws the AppIndicator tray menu,
  tracks sessions by `session_id`, focuses on click, and polls the
  `claude-monitor` usage CLI on a background thread (so the multi-second CLI
  call never blocks the UI). It is the only process that talks to the CLI or
  touches the history store.
- `claude-send.py` — tiny non-blocking hook sender; silent if the helper is
  down.
- The daemon also answers a **read-only `{"query":"snapshot"}`** verb on the
  same socket. Every other surface is a client of that one verb, which is why
  they can never disagree about a number: none of them recompute anything.

### The icon badge

The top-bar label combines two signals (ASCII, so it works in any theme):

| Label    | Meaning                                                         |
| -------- | --------------------------------------------------------------- |
| `16%`    | Current 5-hour usage (always shown when available)              |
| `83%!`   | Usage above the high threshold (default 80%)                    |
| `16% 2!` | Usage, plus 2 sessions that need you (waiting or just finished) |

The `!` attention count clears when you **switch to that session's pane** (auto,
within ~2s), **click** its menu row, or **reply** in it (it goes back to
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

## Dashboards

Beyond the tray menu there are three views of the same snapshot.

### Terminal (`claude-tui`)

Three stacked panels — usage, trends, sessions — driven off the snapshot verb at
a 2s refresh, with a 1s local tick so countdowns and running-session timers move
between fetches.

```
 claude-tui live                                              14:07:52
╭ usage ────────────────────────────────────────────────────────────────╮
│ ████████░░░░░░░░░░░░  5h   42%  417k / 880k  resets in 2h 3m       proj 61% @16:11 │
│ ███░░░░░░░░░░░░░░░░░  7d   15%  week resets in 5d 22h              proj 99% @Fri 12:59 │
╰───────────────────────────────────────────────────────────────────────╯
╭ trends ───────────────────────────────────────────────────────────────╮
│      ▄█                            00  03  06  09  12  15  18  21     │
│     ▄██  ▄                     Mon ····················░▒····         │
│  ▄▄▄███▄▄█▄                    Tue ··········░▒░░░▒▒░▒█·····          │
│ today 13.8M/hr | wk 16.5M/hr   Wed ··········▒▒░░▒░░░▒▒·····          │
│ peak hour: 14:00 (29.3M/hr)    ...                                    │
╰───────────────────────────────────────────────────────────────────────╯
╭ sessions ─────────────────────────────────────────────────────────────╮
│ > waiting  i_mppi_uav                                        6m 25s   │
│   running  claude-code-tray                                 14m 58s   │
╰───────────────────────────────────────────────────────────────────────╯
 up/down select   enter focus   q quit
```

| Key          | Action                                              |
| ------------ | --------------------------------------------------- |
| `up` / `k`   | Select the previous session                         |
| `down` / `j` | Select the next session                             |
| `home`/`end` | Jump to the first / last session                    |
| `enter`      | Focus that session's pane and raise its window      |
| `q`          | Quit                                                |

The selection is keyed to the session, not the row, so it follows its session
when a status change reorders the list — pressing `enter` always focuses what is
highlighted, never whatever slid into that slot. It renders through the
terminal's own 16 ANSI colours, so it inherits your terminal theme rather than
imposing one.

It is a standalone Rust binary: no Python, no `uv`, no Textual at runtime, and
it starts instantly. The Python/Textual TUI it replaced is in
[`archive/`](archive/README.md).

#### In a tmux popup

```sh
just popup     # from inside tmux
```

or bind it to `prefix` + `u` in `~/.tmux.conf`:

```tmux
bind-key u popup -E -w 90% -h 85% -T ' claude-tui ' claude-tui
```

`-E` closes the popup when the command exits, so `q` dismisses it. Needs tmux
3.2+. Because the popup runs the *installed* `claude-tui`, this is also the
quickest check that `./install.sh` deployed what you expect.

### Browser (`just dashboard`)

A self-contained `file://` page — inline CSS/JS, SVG charts, no external
requests — regenerated on the poll tick from the history store. It holds what
the tray menu cannot: usage over `24h / 7d / All`, a weekday-by-hour heatmap,
projections, and window-reset markers so a sawtooth drop reads as "the window
rolled" rather than "usage fell".

## Requirements

- GNOME with the AppIndicator extension (`gnome-shell-extension-appindicator`,
  active by default on Ubuntu).
- `python3` + PyGObject with `Gtk 3.0` and `AyatanaAppIndicator3 0.1` typelibs
  (`gir1.2-ayatanaappindicator3-0.1`).
- The `claude-monitor` usage CLI (Claude Code Usage Monitor) installed at
  `~/.local/bin/claude-monitor` — e.g. `uv tool install claude-monitor`. Only
  needed for the usage rows/badge; without it they show `usage unavailable`.
- `tmux` (pane switching) and `wmctrl` (X11 window raise). Both optional —
  click-to-focus degrades gracefully without them. Add `set -g set-titles on` to
  your `tmux.conf` if you run more than one terminal window: a terminal serves
  every window from one process, so PID and WM_CLASS cannot tell them apart and
  the session name in the title is what lets focus raise the window that already
  hosts the session — switching to its workspace — instead of picking one at
  random. Without it, focus falls back to raising an arbitrary window.
- `xprop` (X11) — optional; used to detect when you are already looking at a
  session's pane so its `!` is suppressed / auto-cleared.

Optional, per dashboard:

- A Rust toolchain (1.90+) — to build `claude-tui`. Without it the tray still
  installs and works; you just get no terminal dashboard. The daemon itself
  never needs it.
- `tmux` 3.2+ — for `just popup`.

## Install

```sh
./install.sh
```

This builds the terminal dashboard and installs `claude-tui` into
`~/.local/bin`, symlinks the daemon and hook sender into `~/.claude/hooks`, and
registers the autostart entry.

Then merge `settings.hooks.json` into the `hooks` object of
`~/.claude/settings.json`, and start the helper (the installer prints the exact
command). It auto-starts on future logins via the installed
`~/.config/autostart/claude-monitor.desktop`.

The hooks map to statuses like this:

| Hook               | Status    | Why                                                          |
| ------------------ | --------- | ------------------------------------------------------------ |
| `UserPromptSubmit` | `running` | you sent a new prompt                                        |
| `PreToolUse`       | `running` | a tool is being dispatched, so the agent is working           |
| `Notification`     | `waiting` | a permission prompt or `AskUserQuestion` needs you           |
| `Stop`             | `done`    | the turn finished                                            |
| `SessionEnd`       | (removed) | the session ended                                            |

`PreToolUse` is registered for **every** tool, deliberately. Answering an
in-turn prompt (a permission dialog or `AskUserQuestion`) does **not** fire
`UserPromptSubmit` — that only fires for a fresh prompt typed at the main
input — so without a hook that fires mid-turn, `waiting` would latch for the
whole rest of the turn while the agent kept working. A long subagent is the
most visible case: the tray would say `waiting` for minutes while a `Task` ran.
Tool calls made *inside* a subagent carry the parent's `session_id`, so they
keep refreshing the parent row for the subagent's full duration.

The cost is ~50 ms per tool call (`PreToolUse` hooks block the call). If that
ever matters, narrow the matcher to `Task|Agent|Bash|Edit|Write|MultiEdit` —
it loses coverage of read-only-only continuations but keeps the common cases.

Re-run `./install.sh` after changing the Rust source: the binary is copied, not
symlinked, so that `cargo clean` cannot uninstall your tool.

## Config (env vars)

| Var                         | Default                 | Purpose                                                                                                                                                                                                     |
| --------------------------- | ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CLAUDE_TRAY_ICON`          | `claude-desktop`        | Tray icon name from your theme                                                                                                                                                                              |
| `CLAUDE_TRAY_WM_CLASS`      | `com.mitchellh.ghostty` | Terminal WM_CLASS to raise on click                                                                                                                                                                         |
| `CLAUDE_TRAY_PLAN`          | `custom`                | `claude-monitor` plan to query. `custom` = session-based dynamic (P90) limits, matching the CLI's own default; also `max5` / `max20` / `pro`; empty = the CLI's saved default (not recommended — it drifts) |
| `CLAUDE_TRAY_POLL_INTERVAL` | `15`                    | Seconds between usage polls. The CLI itself takes ~5-10s, so that is the practical floor                                                                                                                    |

Set these in the autostart `.desktop`'s `Exec=` line to make them persist.

## Development

Use the `just` recipes — the deployed `~/.claude/hooks/claude-monitor.py` is a
symlink into this repo, and Python does not hot-reload, so an edit is on disk
while the running daemon still holds the old code.

| Recipe                 | What it does                                          |
| ---------------------- | ----------------------------------------------------- |
| `just restart`         | Kill and relaunch the daemon — run after any change    |
| `just check`           | Both verification gates (Python self-check + Rust)     |
| `just selfcheck`       | Assert suite for the Python core                       |
| `just rust-test`       | Rust suite: unit, fixture corpus, and render tests     |
| `just rust-lint`       | `cargo clippy -D warnings`                             |
| `just install`         | Build and install everything, Rust dashboard as default|
| `just rust-tui`        | Run the dashboard from the build tree                  |
| `just popup`           | Open the installed dashboard in a tmux popup           |
| `just dashboard`       | Open the generated HTML page                           |

Run them from inside the desktop session so the GUI daemon inherits `DISPLAY`
and `DBUS_SESSION_BUS_ADDRESS`.

### Debugging the dashboard

A working daemon only ever produces healthy data, so the states most likely to
render wrong — a malformed section, a rejected session, a directory name full of
terminal escape sequences, a cold start — never appear on a working machine. The
Rust TUI can replay any fixture through the real renderer instead:

```sh
just rust-states                                # every state, as plain text
just rust-fixture partial-sections              # one state, in the TUI
just rust-fixture hostile-terminal-controls --once
```

`fixtures/snapshot/` holds those inputs paired with the semantic state a correct
client must produce. The format is language-neutral, so the archived Python
implementation can be checked against the same files if it is ever restored.

### Caveats

This project is heavily vibe-coded — built interactively with Claude Code, then
organized with the [Get Shit Done (GSD)](https://github.com/opengsd/gsd-core)
framework. It works on my setup (Ubuntu GNOME / X11 / tmux / Ghostty) but hasn't
been battle-tested elsewhere, and there is no CI. PRs and bug reports welcome.

## License

MIT
