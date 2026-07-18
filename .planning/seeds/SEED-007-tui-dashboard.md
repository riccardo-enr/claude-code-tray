---
id: SEED-007
status: planted
sprouted_into:
planted: 2026-07-18
planted_during: v1.4 Phase 7 execution (user asked, terminal-only dashboard)
trigger_when: after v1.4 ships / next milestone consideration
scope: medium
---

# SEED-007: TUI Dashboard

## Why This Matters

Usage, quota-reset, trends and live sessions are surfaced two ways today: the
GNOME tray menu (`rebuild_menu`) and a self-contained HTML dashboard opened in a
browser via `file://` (`claude-monitor.py:111`,
`webbrowser.open(pathlib.Path(dashboard.DASH_PATH).resolve().as_uri())`). Both
cost a context switch -- the top bar or a browser tab. The user wants the same
data in the terminal, no browser.

**Why now:** the `260718-hz5` restructure already did the hard part. Every
display computation now lives in `claude_monitor/core.py`, a pure stdlib module
with NO gi/GTK import -- verified: `python3 -c "import claude_monitor.core"`
loads with `gi` absent from `sys.modules` (no display needed). A TUI is mostly a
new renderer over functions that already exist and are already covered by
`--selfcheck`:

- usage now: `parse_usage` / `fetch_usage`, `build_label`, `fmt_tokens`,
  `fmt_countdown` / `fmt_countdown_wk`
- reset/exhaust math: `project`, `alert_due`, `hhmm`
- history + trends: `parse_history`, `history_numeric`, `latest_state`,
  `build_trend_rows`, `trend_sparkline`, `trend_burn`, `trend_peak_hour`
- chart series (if the TUI plots): `despike`, `with_gaps`, `usage7_series`,
  `reset_marks`, `heatmap_buckets`
- config: `load_config` / `parse_config`

`dashboard.py` (`render_dashboard`) is also GTK-free but emits HTML, so a curses
UI cannot reuse it -- the reuse surface is `core.py`, not `dashboard.py`. That is
the whole point: a TUI becomes a third consumer of `core`, exactly as
`dashboard.py` and `claude-monitor.py` already are. Precedent for a second entry
point exists: `claude-send.py` is a root script that is NOT the daemon and talks
to the daemon's socket. A `claude-tui.py` root script importing
`claude_monitor.core` mirrors how `claude-monitor.py` imports `core` + `dashboard`.

## When to Surface

**Trigger:** after v1.4 (Session Dashboard) ships, as a next-milestone
candidate. Not urgent -- the tray menu and browser dashboard already deliver the
data; this is an ergonomics alternative for people who live in the terminal.
Raise it when the browser round-trip starts to grate, or when scoping the
milestone after v1.4.

## Scope Estimate

**Medium** -- a new renderer, but two genuinely-open decisions (below) swing the
effort. The lazy first version is small: a standalone `curses` screen that reads
the history JSONL the daemon already writes and renders `latest_state` +
`build_trend_rows` + a `project`-based reset countdown. No daemon changes, no new
IPC, no live sessions -- roughly a `dashboard.py`-sized module that ships the
"usage/quota/trends without a browser" 80%. Live sessions and richer plotting are
the expensive tail, gated on the open questions.

## Open Questions (decide at discuss time)

1. **Data source (the load-bearing one).** Two ways to feed the TUI, each with an
   honest cost -- do NOT pre-decide:
   - **(a) Standalone.** TUI reads `~/.claude/usage-history.jsonl` directly
     (`core.parse_history`) and/or calls `core.fetch_usage()` itself. No daemon
     needed, laziest by far -- but it does NOT see live session state:
     `self.sessions` lives only in the running tray process (`Monitor`,
     `claude-monitor.py:60`), never on disk. And `fetch_usage()` shells out to the
     CLI, so a polling TUI is a *second poller* of the same source, in tension
     with the "no new polling / no second data source" standing constraint
     (STATE.md). Reading only the JSONL the daemon already maintains sidesteps
     that -- fresh to the daemon's poll interval, zero extra polling. That
     read-only-history variant is the true lazy MVP.
   - **(b) Shared.** TUI queries the running daemon over its existing unix socket
     (`SOCK`, `claude-monitor.py:33`). Sees live sessions. But the socket is
     RECEIVE-ONLY today: `serve()` does `conn.recv()` then `conn.close()` with no
     send-back (`claude-monitor.py:461-467`) -- there is no request/response
     protocol. This option means ADDING a query verb to `serve()` (respond with a
     JSON snapshot of `self.sessions` + last usage, then close). New IPC surface
     on the daemon, plus the thread-safety around `self.sessions` (mutated on the
     Gtk main thread) becomes the TUI's problem too.

   Standalone-reads-history is the lazy MVP; shared-socket is the only way to get
   live sessions. Whether live sessions are in v1 scope decides this.

2. **Rendering: stdlib `curses` vs. relax the no-deps rule.** Project constraint
   is stdlib + PyGObject only, zero pip deps (`pyproject.toml` `dependencies =
   []`). That means `curses` -- not rich/textual/blessed. `curses` is enough for
   panels, a sparkline (`core` already emits block glyphs via `SPARK_GLYPHS`), and
   a live countdown, but it is more code and fiddlier than textual. This
   materially changes effort and polish, so it is a real decision: keep the
   no-deps rule (`curses`) or make the TUI the one place a dependency is allowed
   (textual). Lean `curses` -- a dependency-free root script matches every other
   piece of this project.

3. **Refresh + focus parity.** A curses loop redraws on its own timer (re-read the
   JSONL every N seconds, or watch its mtime) -- cheap, but decide it so the loop
   is not an accidental busy-poll. If shared-socket wins, `self.sessions` is
   `session_id -> {dir, status, pane, tmux, cwd, entered}` (the `entered` epoch was
   added during Phase 7); only `dir`/`status`/`entered` are needed to render a
   session panel (exactly what `write_dashboard` snapshots,
   `claude-monitor.py:350`). The `pane`/`tmux` fields would enable click-to-focus
   parity with the tray -- but focusing a pane from inside a terminal UI is its own
   question.
