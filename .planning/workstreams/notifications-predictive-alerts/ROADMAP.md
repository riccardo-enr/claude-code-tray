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

Constraints that held across all four shipped milestones: stdlib + PyGObject
only, X11-only, one background poll, no new dependencies. v1.5 takes the first
exception — `textual` as a runtime dependency, scoped to the one new entry point.

Full phase detail for shipped milestones lives in `.planning/workstreams/notifications-predictive-alerts/milestones/`;
archived phase artifacts live under `.planning/workstreams/notifications-predictive-alerts/milestones/v1.4-phases/`.

## Milestones

- ✅ **v1.0 Usage & Quota Monitoring** — Phase 1 (shipped 2026-07-11)
- ✅ **v1.1 Usage History & Trends** — Phases 2-3 (shipped 2026-07-12)
- ✅ **v1.2 Usage Web Dashboard** — Phase 4 (shipped 2026-07-13) — [archive](./milestones/v1.2-ROADMAP.md)
- ✅ **v1.3 Notifications & Predictive Alerts** — Phases 5-6 (shipped 2026-07-17) — [archive](./milestones/v1.4-ROADMAP.md)
- ✅ **v1.4 Session Dashboard** — Phase 7 (shipped 2026-07-20) — [archive](./milestones/v1.4-ROADMAP.md)
- ✅ **v1.5 TUI Dashboard** — Phases 8-9 (shipped 2026-07-24) — [archive](./milestones/v1.5-ROADMAP.md)

## Phases

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
| 8. Daemon Socket Query Verb              | v1.5      | 2/2 | Complete    | 2026-07-20 |
| 9. Terminal Dashboard (claude-tui.py)    | v1.5      | 2/2             | Complete    | 2026-07-24 |
