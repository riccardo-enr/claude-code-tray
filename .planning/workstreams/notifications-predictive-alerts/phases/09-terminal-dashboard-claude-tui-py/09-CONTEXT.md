# Phase 9: Terminal Dashboard (claude-tui.py) - Context

**Gathered:** 2026-07-21
**Status:** Ready for planning

<domain>
## Phase Boundary

A new `claude-tui.py` entry point at the repo root renders the tray's full
usage/quota, trends, and live-sessions picture as a `textual` TUI, fed entirely by
Phase 8's read-only socket verb (`{"query": "snapshot"}`). It becomes the third
consumer of `claude_monitor.core`, alongside `claude-monitor.py` (the daemon) and
`claude_monitor/dashboard.py` (the HTML renderer).

In scope: the renderer, its refresh loop, its degraded-mode behavior, and packaging
the one new runtime dependency (`textual`) into `pyproject.toml` / `install.sh`.

Out of scope: any change to the daemon's query verb or snapshot shape (Phase 8 is
shipped and verified), click-to-focus from the TUI, and a standalone no-daemon mode
reading `usage-history.jsonl` directly -- both explicitly deferred at v1.5 planning.

</domain>

<decisions>
## Implementation Decisions

### Screen layout
- **D-01:** Static three-panel single column, no tabs and no navigation. Usage block
  fixed at top, trends block fixed below it, sessions table takes all remaining space
  and scrolls internally when it overflows. The screen is glanceable like the tray
  menu -- everything visible without a keypress. Approved shape:

  ```
  +----------------------------------------+
  | claude-tui            14:32  * live    |
  +----------------------------------------+
  | 5h   62%  1.2M tok  resets 1h04  380/m |
  | 7d   41%  8.9M tok  resets 3d02   210/m|
  +----------------------------------------+
  | trends                                 |
  |  _..-=#=-._..--=##=-.._                |
  |  today 410k/hr | wk 260k/hr            |
  |  peak hour: 15:00 (720k/hr)            |
  +----------------------------------------+
  | SESSIONS                               |
  | waiting  claude-code-tray      2m14s   |
  | running  phd                   11m03s  |
  | done     dotfiles              1h22m   |
  +----------------------------------------+
  | q quit                                 |
  +----------------------------------------+
  ```

- **D-02:** Header (title + clock + a live/stale indicator) and footer (`q quit`).
  Exactly one key binding: `q`. No manual-refresh key, no theme toggle -- the refresh
  is automatic (TUI-04) so a manual one has nothing to add.
- **D-03:** Sessions sort order is waiting -> running -> done, matching the v1.4
  dashboard panel's semantics (TUI-03). Columns: status, project dir, time-in-state.

### Data source and trends
- **D-04:** The socket snapshot is the *only* data source. The TUI never opens
  `usage-history.jsonl` and never runs `claude` itself.
- **D-05:** Trends are rendered from the snapshot's `trends` field **verbatim** -- those
  are already the exact row strings `core.build_trend_rows` produced for the tray menu.
  The TUI does not recompute them and does not call the trend functions itself. This
  satisfies TUI-02 ("reusing core's existing trend functions, not reimplementing them")
  by construction and guarantees the TUI and the tray menu can never disagree.
  Consequence, accepted: the sparkline is fixed at the tray's 24 columns and does not
  widen with the terminal.
- **D-06:** Keep core's existing Unicode block `SPARK_GLYPHS`. No ASCII variant, no
  second glyph set -- a divergence from the tray's rendering is the thing to avoid.
  (Deliberate exception to the ASCII-only house rule; the glyphs already ship in
  `claude_monitor/core.py` and already render in the tray menu.)
- **D-07:** `trends` is `None` while history spans less than `TREND_MIN_SPAN`
  (`build_trend_rows` returns `None` in the collecting state). The trends panel must
  render a "collecting" message for that case, not an empty box or a crash.

### Refresh and liveness
- **D-08:** Query the socket on a fixed 2-second interval, *not* the daemon's poll
  interval. Rationale: sessions change on hook events, not on the daemon's usage-poll
  clock, so matching the poll interval would make the live sessions panel laggy -- the
  panel is the reason the TUI queries the socket rather than reading a file. Repeated
  identical usage rows between daemon polls are the accepted cost.
- **D-09:** Running sessions tick locally every second between snapshots -- derive
  elapsed from `entered` + the local clock, exactly as the v1.4 web dashboard does.
  Waiting/done sessions show the snapshot's `frozen` value as-is, so a stopped session's
  counter stops climbing. Two timers: 2s fetch, 1s re-render.

### Degraded mode (TUI-05)
- **D-10:** If at least one snapshot has ever been received, a failed query keeps the
  last data on screen (dimmed) and flips the header indicator to
  `daemon unreachable -- last update HH:MM:SS`. It never wipes good data off the screen
  for a one-off blip, and it clears itself silently when the socket comes back.
- **D-11:** On cold start with no daemon ever reached, show a single clear centered
  message instead of empty panels. Never a traceback to the terminal.
- **D-12:** Retry forever on the same 2s interval. No backoff, no failure cap, no exit.
  The TUI is a long-lived window; leaving it open across a `just restart` must Just Work.

### Claude's Discretion
- Widget choice within `textual` (Static/DataTable/custom), styling/CSS, and the exact
  module split between `claude-tui.py` and any helper -- planner's call.
- Where the socket-query helper lives (a small function in `claude-tui.py` vs. a
  `claude_monitor.core` addition). Note that `core.py` is deliberately `gi`-free; the
  query client is `gi`-free too, so either home is viable.
- Exact `textual` version pin and whether it lands in `dependencies` or an optional
  extra, provided a plain `./claude-tui.py` works after `install.sh`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The data contract (Phase 8, shipped)
- `claude-monitor.py:573-614` (`_handle_conn`) -- the query verb. Request is one line of
  JSON `{"query": "snapshot"}`; response is one line of JSON
  `{"sessions": [...], "usage": ..., "trends": ...}` followed by `\n`, then the daemon
  closes the connection. 5-second server-side timeout.
- `claude-monitor.py:32` -- `SOCK` path: `$XDG_RUNTIME_DIR/claude-monitor.sock`, mode 0600.
- `claude_monitor/core.py:153-172` (`build_session_snapshot`) -- the six per-session keys
  the TUI receives: `dir`, `status`, `entered`, `frozen`, `pane`, `tmux`.
- `.planning/workstreams/notifications-predictive-alerts/phases/08-daemon-socket-query-verb/08-CONTEXT.md`
  -- Phase 8's locked decisions (lock discipline, thread-per-connection, snapshot shape).

### What to render
- `claude_monitor/core.py:489-512` (`build_trend_rows`) -- produces the `trends` row
  strings the TUI prints verbatim, and returns `None` in the collecting state (D-07).
- `claude_monitor/core.py:438-462` (`trend_sparkline`), `:309-334` (`fmt_tokens`,
  `fmt_countdown`, `fmt_countdown_wk`) -- the formatters whose output the TUI must match.
- `claude_monitor/dashboard.py:468-520` -- the v1.4 sessions panel: sort order, the
  running-ticks / frozen-duration split (D-09), and the empty-state string
  "No active Claude Code sessions". The TUI mirrors these semantics (D-03).

### Project rules
- `.planning/workstreams/notifications-predictive-alerts/ROADMAP.md` -- Phase 9 goal and
  the five success criteria.
- `.planning/workstreams/notifications-predictive-alerts/REQUIREMENTS.md:17-21` -- TUI-01..05.
- `justfile` -- `just selfcheck` is the green-gate every change must keep passing.
- `install.sh`, `pyproject.toml` -- where `textual` has to land (packaging is Phase 9's job).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `claude_monitor/core.py` is `gi`-free and pure -- every formatter (`fmt_tokens`,
  `fmt_countdown`, `fmt_countdown_wk`, `hhmm`) imports cleanly into a non-GTK process.
  The TUI is the third consumer and should import, never copy.
- `claude_monitor/dashboard.py` is the working precedent for "render core's data in a
  second surface without touching the daemon" -- same posture, different output medium.

### Established Patterns
- The daemon precomputes and caches: `mon.usage` and `mon.trends` are single-reference
  rebinds read without a lock. The snapshot hands the TUI finished values, so the TUI's
  job is layout, not computation.
- Broad `except Exception` at every thread/loop boundary is the house posture for keeping
  a long-lived surface alive (`poll_loop`, `serve`, `_handle_conn`). The TUI's fetch
  timer inherits it -- a failed query is a state change (D-10), never a raised traceback.
- Entry scripts live at the repo root and import the first-party `claude_monitor`
  package beside them (`sys.path[0]` at runtime; `pyright.extraPaths` for the checker).
  `claude-tui.py` follows that layout.

### Integration Points
- Read-only client of the unix socket at `SOCK`. Nothing in `claude-monitor.py` changes.
- `install.sh` symlinks hook scripts (`ln -sf`, quick task `260719-pzd`); `claude-tui.py`
  needs whatever install step makes it runnable, plus `textual` available to it.
- `--selfcheck` (`claude_monitor/test_claude_monitor.py`) is the assert suite; anything
  pure that the TUI adds (e.g. session sort key, elapsed formatting) belongs there.

</code_context>

<specifics>
## Specific Ideas

- The approved layout mock in D-01 is the visual target -- match its information order
  and density, not necessarily its exact characters.
- "5h" and "7d" rows sit together in one usage block; both caps are always visible,
  never behind a toggle (TUI-01).
- The header's live/stale indicator is the single place freshness is communicated. It is
  what makes D-10's "keep stale data on screen" honest rather than misleading.

</specifics>

<deferred>
## Deferred Ideas

- **Click-to-focus a pane from the TUI** (the `pane`/`tmux` fields are in the snapshot,
  unused here) -- deferred at v1.5 planning; the tray stays the focus surface.
- **Standalone no-daemon mode** reading `usage-history.jsonl` directly -- deferred at
  v1.5 planning; shared-socket was chosen to get live sessions into v1.5 scope.
- **Terminal-width sparkline** -- rejected for this phase as the cost of D-05. Revisit
  only if the fixed 24 columns actually reads badly on a wide terminal.
- **Manual refresh / theme toggle keys** -- rejected under D-02; auto-refresh makes the
  first redundant and the second is not a v1.5 problem.

</deferred>

---

*Phase: 9-Terminal Dashboard (claude-tui.py)*
*Context gathered: 2026-07-21*
