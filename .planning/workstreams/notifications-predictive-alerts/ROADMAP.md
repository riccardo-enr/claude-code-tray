# Roadmap: claude-code-tray

## Overview

A GNOME top-bar tray indicator for Claude Code. It shows per-session status and
focuses the originating tmux pane + Ghostty window on click. Four shipped
milestones extended that same single-file helper (`claude-monitor.py`) into a
quota monitor with a push voice and a live session view: point-in-time usage,
then persisted history and in-menu trends, then a browsable HTML dashboard,
then desktop notifications, then a live sessions panel in that dashboard.

v1.5 gives that same data a terminal home: a new `claude-tui.py` entry point
renders usage/quota/trends and live sessions as a `textual` TUI, fed by a new
read-only query verb on the daemon's existing unix socket, for people who live
in the terminal and don't want a browser round-trip.

v1.6 makes that TUI look the part. The v1.5 renderer shows the right data but as
flat, uncolored text; v1.6 turns it btop-inspired — threshold coloring, gradient
progress-bar gauges, a richer trends graph, a styled sessions table, and titled
rounded bordered panels. Pure presentation: no new data source, no new polling,
no IPC change, no new runtime dependency.

Constraints that held across all four shipped milestones: stdlib + PyGObject
only, X11-only, one background poll, no new dependencies. v1.5 takes the first
exception — `textual` as a runtime dependency, scoped to the one new entry point;
v1.6 adds nothing to that.

Full phase detail for shipped milestones lives in `.planning/workstreams/notifications-predictive-alerts/milestones/`;
archived phase artifacts live under `.planning/workstreams/notifications-predictive-alerts/milestones/v1.4-phases/`.

## Milestones

- ✅ **v1.0 Usage & Quota Monitoring** — Phase 1 (shipped 2026-07-11)
- ✅ **v1.1 Usage History & Trends** — Phases 2-3 (shipped 2026-07-12)
- ✅ **v1.2 Usage Web Dashboard** — Phase 4 (shipped 2026-07-13) — [archive](./milestones/v1.2-ROADMAP.md)
- ✅ **v1.3 Notifications & Predictive Alerts** — Phases 5-6 (shipped 2026-07-17) — [archive](./milestones/v1.4-ROADMAP.md)
- ✅ **v1.4 Session Dashboard** — Phase 7 (shipped 2026-07-20) — [archive](./milestones/v1.4-ROADMAP.md)
- ✅ **v1.5 TUI Dashboard** — Phases 8-9 (shipped 2026-07-24) — [archive](./milestones/v1.5-ROADMAP.md)
- 🚧 **v1.6 TUI Polish** — Phase 10 (planning)

## Phases

### 🚧 v1.6 TUI Polish (Phase 10) — ACTIVE

- [ ] **Phase 10: TUI Polish (btop-style)** — color/gauge/graph/border the v1.5 `claude-tui.py`, same data, same socket

Full detail below under [Phase Details](#phase-details).

<details>
<summary>✅ v1.0 Usage & Quota Monitoring (Phase 1) — SHIPPED 2026-07-11</summary>

- [x] Phase 1: Usage & Quota Monitoring in the Tray (1/1 plans) — completed 2026-07-11

Background-polled usage rows (tokens/percent, reset countdown, burn rate) plus a
high-usage icon badge, degrading to "usage unavailable" when the CLI call fails.

</details>

<details>
<summary>✅ v1.1 Usage History & Trends (Phases 2-3) — SHIPPED 2026-07-12</summary>

- [x] Phase 2: Usage History Persistence (1/1 plans) — completed 2026-07-12
- [x] Phase 3: Usage Trends in the Tray (1/1 plans) — completed 2026-07-12

Bounded, corruption-tolerant `~/.claude/usage-history.jsonl` written from the
existing poll, then read back as an in-menu sparkline, today/week burn, and peak
usage hour — all computed off the Gtk main thread.

</details>

<details>
<summary>✅ v1.2 Usage Web Dashboard (Phase 4) — SHIPPED 2026-07-13</summary>

- [x] Phase 4: Usage Web Dashboard (1/1 plans) — completed 2026-07-13

Self-contained `file://` HTML dashboard opened from a tray item: usage-% trend
over rolling 24h/7d/All (line broken across data gaps), hour x day heatmap, dark
mode. Delivered beyond original scope: weekly (7-day) cap parsing, display and
badge warning (QUOTA-01, closes SEED-003); reset markers (QUOTA-02); projected
usage at reset (QUOTA-03). Descoped during UAT: DASH-04 burn-rate trend chart
(`ae0691f`) — near-flat raw-throughput numbers the heatmap already showed better.

</details>

<details>
<summary>✅ v1.3 Notifications & Predictive Alerts (Phases 5-6) — SHIPPED 2026-07-17</summary>

- [x] Phase 5: Notification Path & Event Producers (3/3 plans) — completed 2026-07-14
- [x] Phase 6: Notification Control & Config (2/2 plans) — completed 2026-07-17

One shared notification path (`Gio.DBusProxy` to `org.freedesktop.Notifications`)
that all tray events route through: session waiting/done events and predictive
5h/7d quota alerts as two producers, plus per-event tray toggles, a global mute,
and a configurable badge threshold. Merged SEED-002 + SEED-004.

</details>

<details>
<summary>✅ v1.4 Session Dashboard (Phase 7) — SHIPPED 2026-07-20</summary>

- [x] Phase 7: Live Session View in the Dashboard (3/3 plans) — completed 2026-07-18

Live sessions panel embedded in the existing web dashboard: every tracked
session with status/dir/duration, sorted waiting -> running -> done, self-healing
off the panel when a tmux pane dies with no `SessionEnd` hook required. Gap
closure CR-01 restored the NOTIF-02 de-dupe guarantee across a reap/resurrect.

</details>

<details>
<summary>✅ v1.5 TUI Dashboard (Phases 8-9) — SHIPPED 2026-07-24</summary>

- [x] Phase 8: Daemon Socket Query Verb (2/2 plans) — completed 2026-07-20
- [x] Phase 9: Terminal Dashboard (claude-tui.py) (2/2 plans) — completed 2026-07-24

Read-only `{"query": "snapshot"}` verb on the daemon's existing unix socket
(thread-per-connection, `sessions_lock` for torn-read safety, chmod 0600), feeding
a new `textual`-rendered `claude-tui.py`: 5h/7d usage rows, trends reused verbatim
from `core`, a live sessions panel sorted waiting -> running -> done, auto-refresh,
and clean degradation when the daemon is unreachable. `textual` is the project's
first runtime-dependency exception, scoped to the one entry point via PEP 723 + an
optional `tui` extra. Full detail: [archive](./milestones/v1.5-ROADMAP.md).

</details>

## Phase Details

### Phase 10: TUI Polish (btop-style)
**Goal**: The v1.5 plain-text `claude-tui.py` becomes a btop-inspired terminal dashboard — threshold-colored, gauged, richer-graphed, styled sessions, bordered panels — showing the same data from the same snapshot socket, with `claude_monitor.core` still the single source of every formatted value.
**Depends on**: Phase 9 (the v1.5 `claude-tui.py` this polishes; its `core` substrate and CSS-only App are the surface being reworked)
**Requirements**: TUI-06, TUI-07, TUI-08, TUI-09, TUI-10
**Success Criteria** (what must be TRUE):
  1. Usage %, burn rate, and reset countdown are colored green / yellow / red by proximity to the cap for both the 5h and 7d caps — a near-full cap reads red at a glance, a low one green (TUI-06).
  2. Each of the 5h and 7d usage rows renders as a gradient progress-bar gauge (green->yellow->red fill), replacing the plain "N% of limit" text (TUI-07).
  3. The trends panel shows a richer usage graph — taller and/or colored/braille — than the reused tray sparkline, drawn from `core`'s existing trend data with no new trend math (TUI-08).
  4. The live sessions table shows status-colored rows with improved spacing / borders / striping, over the current plain DataTable (TUI-09).
  5. Each of the three panels (usage, trends, sessions) appears as a titled, rounded, bordered box — the btop-style paneled layout (TUI-10).
**Plans**: 3 plans
- [ ] 10-01-PLAN.md — Usage panel: threshold color bands + gradient gauge (TUI-06, TUI-07) [tracer]
- [ ] 10-02-PLAN.md — Richer trends graph: decoded height-colored column graph (TUI-08)
- [ ] 10-03-PLAN.md — Status-colored striped sessions + titled rounded bordered panels (TUI-09, TUI-10)
**UI hint**: yes

**Constraints & boundary (for plan-phase to respect):**
- **Core-vs-TUI boundary is the central gray area, and it runs INSIDE each requirement, not between them.** Threshold-band decisions (TUI-06/09), gauge fill math (TUI-07), and any graph data expressible as plain values/strings (TUI-08) belong in `claude_monitor.core`, proven by `--selfcheck` on stock `/usr/bin/python3` (PEP 668 — must never import textual/rich). The visual application of color, gauge glyphs, borders, striping, and CSS stays in `claude-tui.py`. TUI-10 is almost entirely CSS with little-to-no core surface. Because the assertable half and the render-only half of TUI-06..TUI-09 live in one requirement each, this is a **plan-level split within this one phase** — mirroring v1.5's 09-01 (core substrate + `--selfcheck` asserts) then 09-02 (textual wiring) — NOT a phase boundary.
- **D-05 parity holds:** `claude_monitor.core` stays the single source of truth for every formatted value, so the tray and TUI can never disagree; no new number/string formatter is introduced in `claude-tui.py`.
- **No new data source, no new polling, no IPC/socket change, no new runtime dependency.** Same `{"query": "snapshot"}` verb; `textual` stays the only third-party dep, scoped to `claude-tui.py` via its PEP 723 block. Deferred: TUI click-to-focus, no-daemon standalone mode.

## Progress

| Phase                                    | Milestone | Plans Complete | Status      | Completed  |
| ----------------------------------------- | --------- | --------------- | ----------- | ---------- |
| 1. Usage & Quota Monitoring in the Tray  | v1.0      | 1/1             | Complete    | 2026-07-11 |
| 2. Usage History Persistence             | v1.1      | 1/1             | Complete    | 2026-07-12 |
| 3. Usage Trends in the Tray              | v1.1      | 1/1             | Complete    | 2026-07-12 |
| 4. Usage Web Dashboard                   | v1.2      | 1/1             | Complete    | 2026-07-13 |
| 5. Notification Path & Event Producers   | v1.3      | 3/3             | Complete    | 2026-07-14 |
| 6. Notification Control & Config         | v1.3      | 2/2             | Complete    | 2026-07-17 |
| 7. Live Session View in the Dashboard    | v1.4      | 3/3             | Complete    | 2026-07-18 |
| 8. Daemon Socket Query Verb              | v1.5      | 2/2             | Complete    | 2026-07-20 |
| 9. Terminal Dashboard (claude-tui.py)    | v1.5      | 2/2             | Complete    | 2026-07-24 |
| 10. TUI Polish (btop-style)              | v1.6      | 0/3             | Not started | -          |
</content>
</invoke>
