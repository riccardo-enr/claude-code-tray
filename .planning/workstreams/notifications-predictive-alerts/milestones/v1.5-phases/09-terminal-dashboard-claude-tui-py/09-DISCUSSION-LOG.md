# Phase 9: Terminal Dashboard (claude-tui.py) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-21
**Phase:** 9-Terminal Dashboard (claude-tui.py)
**Areas discussed:** Screen layout & panels, Trends source & sparkline, Refresh cadence & liveness, Daemon-down behavior (TUI-05)

---

## Screen layout

| Option | Description | Selected |
|--------|-------------|----------|
| Static 3-panel column | Usage fixed top, trends fixed below, sessions takes remaining space and scrolls. No tabs, no navigation. | ✓ |
| Two columns | Usage + trends left, sessions right. Better on wide terminals, cramped under ~100 cols. | |
| Tabbed | Usage / Trends / Sessions tabs, one visible at a time. | |

**User's choice:** Static 3-panel column (with the ASCII mock)
**Notes:** Glanceable-without-a-keypress is the point; tabs work against it.

## Chrome and keys

| Option | Description | Selected |
|--------|-------------|----------|
| Header + footer, `q` only | Title + clock + live/stale indicator; footer `q quit`. One binding. | ✓ |
| Bare, no chrome | Three panels, Ctrl-C to exit. No freshness signal. | |
| Header/footer + q, r, d | Adds manual refresh and dark toggle. | |

**User's choice:** Header + footer, `q` only
**Notes:** Auto-refresh (TUI-04) makes a manual refresh key redundant.

---

## Trends source

| Option | Description | Selected |
|--------|-------------|----------|
| Render daemon's `trends` rows verbatim | Snapshot already carries core.build_trend_rows output. Zero recomputation, cannot diverge from the tray. Sparkline fixed at 24 cols. | ✓ |
| TUI reads usage-history.jsonl and calls core itself | Sparkline could widen to the terminal, but adds a second data source against the socket-only rule. | |
| Both — daemon rows, widen sparkline locally | Half a second data source. | |

**User's choice:** Render the daemon's rows verbatim
**Notes:** Fixed 24-column sparkline accepted as the cost.

## Sparkline glyphs

| Option | Description | Selected |
|--------|-------------|----------|
| Keep Unicode block glyphs | SPARK_GLYPHS already ships in core and renders in the tray menu. | ✓ |
| ASCII variant for the TUI | Honors the ASCII-only house rule but forks the glyph set. | |

**User's choice:** Keep the block glyphs
**Notes:** Deliberate exception to the ASCII-only rule; divergence from the tray was the bigger risk.

---

## Refresh interval

| Option | Description | Selected |
|--------|-------------|----------|
| Match the daemon's poll interval | Never queries faster than usage can change; sessions lag up to one interval. | |
| Fast fixed interval (2s) | Sessions feel live (they change on hook events, not the poll clock); usage rows repeat between polls. | ✓ |
| Two clocks (2s sessions, poll for usage) | Two timers and two partial merges for data the verb returns in one shot. | |

**User's choice:** Fast fixed 2s interval
**Notes:** The live sessions panel is the reason the TUI queries the socket at all, so it sets the cadence.

## Local ticking

| Option | Description | Selected |
|--------|-------------|----------|
| Tick locally every second | Matches the v1.4 web dashboard: `entered` + local clock for running, `frozen` as-is for waiting/done. | ✓ |
| Update only on snapshot | Durations jump by the refresh interval. | |

**User's choice:** Tick locally every second

---

## Daemon-down behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Keep last data + stale banner; takeover only on cold start | Dim last snapshot, header shows "daemon unreachable — last update HH:MM:SS"; centered message only if never connected. Recovers silently. | ✓ |
| Always full-screen takeover | Unambiguous, but a blip wipes good data. | |
| Banner only, never takeover | Cold start shows empty panels plus a banner. | |

**User's choice:** Keep last data + stale banner, takeover only if never connected

## Retry policy

| Option | Description | Selected |
|--------|-------------|----------|
| Retry forever on the same interval | Leave the window open across a daemon restart and it reconnects. | ✓ |
| Backoff capped at ~30s | Cheaper when the daemon is off for hours; adds backoff state. | |
| Exit after N failures | A daemon restart would kill the TUI. | |

**User's choice:** Retry forever

---

## Claude's Discretion

- `textual` widget choice and styling/CSS
- Module split between `claude-tui.py` and any helper; where the socket-query client lives
- `textual` version pin and dependency group placement

## Deferred Ideas

- Click-to-focus a pane from the TUI (deferred at v1.5 planning)
- Standalone no-daemon mode reading `usage-history.jsonl` (deferred at v1.5 planning)
- Terminal-width sparkline (revisit only if 24 columns reads badly on a wide terminal)
- Manual refresh / theme toggle keys
