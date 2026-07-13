---
gsd_state_version: 1.0
milestone: v1.3
milestone_name: Notifications & Predictive Alerts
current_phase: 5
status: planning
stopped_at: Phase 5 context gathered
last_updated: "2026-07-13T11:38:00.806Z"
last_activity: 2026-07-13
last_activity_desc: v1.3 roadmap created (2 phases, 14/14 requirements mapped)
progress:
  total_phases: 2
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-13)

**Core value:** At a glance from the top bar, know how much Claude Code quota is left and when it resets — without launching a separate terminal monitor.
**Current focus:** v1.3 roadmapped (Phases 5-6) — ready to plan Phase 5

## Current Position

Phase: 5 — Notification Path & Event Producers (not started)
Plan: —
Status: Roadmap created, awaiting `/gsd-plan-phase 5`
Last activity: 2026-07-13 — v1.3 roadmap created (2 phases, 14/14 requirements mapped)

## Performance Metrics

**Velocity:**

- Total plans completed: 4
- Average duration: - min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 1 | 2 min | 2 min |
| 02 | 1 | 2 min | 2 min |
| 03 | 1 | 1 session | - |
| 04 | 1 | 12 min | 12 min |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- v1.3 is **2 phases** (5: notification path + both producers; 6: config/control). Coarse granularity, and the project precedent is 1-2 phases per milestone (v1.2 shipped 11 requirements in one phase).
- **Both producers (SESS-* and ALERT-*) land in Phase 5, not separate phases.** The deliverable is the shared emit path (de-dupe, mute hook, click-to-focus); building it against one producer and bolting the second on later is how it grows two heads — the exact failure SEED-004 called out.
- **Config (CFG-*) comes last (Phase 6)** because CFG-01 enumerates all four event types — they must exist before they can be toggled.
- ALERT-* reuses v1.2's QUOTA-03 **percentage** projection. It is not a new forecaster; SEED-002's token-based EWMA plan is superseded (token counts are `null` under `--api`, quick task `260712-ndo`).

### Pending Todos

None yet.

### Blockers/Concerns

Verified against `claude-monitor.py` during roadmapping — carry into Phase 5 planning:

- **`project()` (QUOTA-03) is JavaScript-only.** It lives at `claude-monitor.py:931`, inside the dashboard HTML. There is **no Python-side projection**; `poll_loop` never computes one. ALERT-02/03 must evaluate it on the poll thread, so Phase 5 **ports** that ~15-line formula to Python (elapsed-fraction extrapolation, `e<=0.05` early guard, exhaust-time when `proj>100`) and asserts it in `--selfcheck`. Mechanical, not modeling — but do not plan it as "read an existing Python value", because that value does not exist. The JS copy must stay (it recomputes against a live browser clock).
- **There is no `Gio.Application`** — `claude-monitor.py:1817` is a bare `Gtk.main()`. `Gio.Notification.send_notification` requires one, and notification *click actions* (NOTIF-03) additionally need an app id with a matching `.desktop`. Alternative: `org.freedesktop.Notifications.Notify` via `Gio.DBusProxy`, which supports `actions` + `ActionInvoked` with no app-id plumbing. **This is Phase 5's load-bearing decision** — settle it at plan time. NOTIF-01's "`Gio.Notification`" reads as intent (PyGObject, no new dependency), not a binding mandate.
- **`serve()` is unguarded.** `poll_loop` gained a blanket `except` + traceback in `260713-fry`, so the alert producer inherits it. `serve()` (`claude-monitor.py:1705`) did not — a raise in its loop kills the socket thread and every session event, permanently. The session producer rides that thread. This is what NOTIF-04 is actually protecting.
- Session transitions reach `Monitor.handle` via `GLib.idle_add` — i.e. on the **Gtk main thread**. The emit path must be non-blocking there (async D-Bus is; a `subprocess` shell-out is not).
- Standing constraints: no new polling, no second data source, no new runtime dependencies, X11 only.

### Quick Tasks Completed

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| 260712-ndo | Poll claude-monitor with --api for official /usage numbers (drops absolute token counts) | 2026-07-12 | 04b45d7 | Verified | [260712-ndo-api-official-usage](./quick/260712-ndo-api-official-usage/) |
| 260713-fry | Fix compute_trends corrupt-record crash — sanitize via history_numeric + guard poll_loop so the daemon thread cannot die | 2026-07-13 | 6d0ec43 | Verified | [260713-fry-fix-compute-trends-corrupt-record-crash](./quick/260713-fry-fix-compute-trends-corrupt-record-crash/) |

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Usage | ~~7-day / weekly limit display — SEED-003~~ | **DONE 2026-07-13** (QUOTA-01) | 2026-07-11 |
| Dashboard | ~~Live in-browser auto-refresh — DASH-F1~~ | **DONE 2026-07-13** (`ea00509`) | 2026-07-12 |
| Alerting | ~~Configurable threshold via env var~~ | **ACTIVE in v1.3** as CFG-05 (Phase 6) | 2026-07-11 |
| Seed | ~~SEED-002 — predictive quota alerts~~ | **ACTIVE in v1.3** as ALERT-02/03/04 (Phase 5); token-based forecaster superseded | 2026-07-13 |
| Seed | ~~SEED-004 — desktop notification when a session finishes~~ | **ACTIVE in v1.3** as SESS-01/02 + NOTIF-* (Phase 5) | 2026-07-13 |
| History | Raw data export (CSV/JSON dump) — HIST-F1 / DASH-F2 | Deferred | 2026-07-11 |
| Trends | Configurable sparkline window / aggregation period — TREND-F1 / DASH-F3 | Deferred | 2026-07-11 |
| Notifications | Quiet hours — NOTIF-F1 | Deferred (global mute CFG-02 ships the value; GNOME has its own DND) | 2026-07-13 |
| Notifications | Per-event sound / urgency — NOTIF-F2 | Deferred | 2026-07-13 |
| Alerting | Hard-threshold push (>90%) — ALERT-F1 | Deferred (the ALERT-01 icon badge stays the reactive signal) | 2026-07-13 |
| UAT | Phase 01 flagged by pre-close audit; 01-UAT.md is `[passed]` with 0 pending scenarios — audit-format false positive, no real gap | Acknowledged | 2026-07-13 |

## Session Continuity

Last session: 2026-07-13T11:38:00.800Z
Stopped at: Phase 5 context gathered
Resume file: .planning/phases/05-notification-path-event-producers/05-CONTEXT.md

## Operator Next Steps

- Plan the first phase with `/gsd-plan-phase 5`
- Phase 5 must settle the notification-binding decision (`Gio.Application` + app id/.desktop vs. `Gio.DBusProxy` to `org.freedesktop.Notifications`) — NOTIF-03's click-to-focus depends on it
