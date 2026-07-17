---
gsd_state_version: 1.0
milestone: v1.4
milestone_name: Session Dashboard
current_phase: 07
current_phase_name: live-session-view
status: planning
stopped_at: v1.4 milestone defined; Phase 07 not yet planned
last_updated: "2026-07-17T18:00:00.000Z"
last_activity: 2026-07-17
last_activity_desc: v1.4 Session Dashboard milestone started
progress:
  total_phases: 1
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-13)

**Core value:** At a glance from the top bar, know how much Claude Code quota is left and when it resets — without launching a separate terminal monitor.
**Current focus:** Phase 06 — notification-control-config

## Current Position

Phase: 07 (live-session-view) — PLANNING
Plan: not yet planned
Status: v1.4 Session Dashboard defined; ready for /gsd-plan-phase 07
Last activity: 2026-07-17 — v1.4 milestone started (v1.3 shipped, tag v1.3)

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
| Phase 05 P02 | 15 min | 2 tasks | 1 files |
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 06 P01 | 8 min | 3 tasks | 1 files |
| Phase 06 P02 | 6min | 2 tasks | 1 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- v1.3 is **2 phases** (5: notification path + both producers; 6: config/control). Coarse granularity, and the project precedent is 1-2 phases per milestone (v1.2 shipped 11 requirements in one phase).
- **Both producers (SESS-* and ALERT-*) land in Phase 5, not separate phases.** The deliverable is the shared emit path (de-dupe, mute hook, click-to-focus); building it against one producer and bolting the second on later is how it grows two heads — the exact failure SEED-004 called out.
- **Config (CFG-*) comes last (Phase 6)** because CFG-01 enumerates all four event types — they must exist before they can be toggled.
- ALERT-* reuses v1.2's QUOTA-03 **percentage** projection. It is not a new forecaster; SEED-002's token-based EWMA plan is superseded (token counts are `null` under `--api`, quick task `260712-ndo`).
- [Phase 05]: SESS de-dupe is one pure expression: notifiable state AND a change from the previous status -- no timestamps, no seen-set (NOTIF-02, D-03)
- [Phase 05]: Structural greps/AST checks over claude-monitor.py are defeated by prose naming the symbol they forbid (docstrings are in ast.dump) -- second occurrence this phase
- [Phase 06]: notif_allowed(kind, config) short-circuits on mute_all before the per-event lookup (D-04) -- mute wins, never OR-merges with the per-event flag
- [Phase 06]: on_notif_toggle/on_threshold_toggle follow set_active-before-connect ordering on every new widget to avoid a spurious save+rebuild on menu construction

### Pending Todos

None yet.

### Blockers/Concerns

**The binding is SETTLED — Route B.** Phase 5's load-bearing decision is closed. `05-RESEARCH.md` settled it against gnome-shell 46.0's actual source (extracted from `/usr/lib/gnome-shell/libshell-14.so`) plus live D-Bus probes on the running session bus. Verdict: **`org.freedesktop.Notifications.Notify` over `Gio.DBusProxy`.** Route A (`Gio.Application` + `Gio.Notification`) is not merely costlier, it is *impossible* here — gnome-shell does `lookup_app(appId + '.desktop')`, throws `InvalidAppError`, and drops the notification silently. This is a single-file script with no install step and no `.desktop`.

Execution landmines — each one, if ignored, ships a silently broken feature. All are encoded as acceptance criteria in the plans:

- **gnome-shell ignores `expire_timeout` entirely.** It destructures it as `timeout_` (the deliberately-unused convention) and never reads it; banner life is a hardcoded `NOTIFICATION_TIMEOUT = 4000`. D-02 ("`waiting` sticks, `done` expires") must be implemented via the **`urgency` hint** — `2`/CRITICAL never arms the dismiss timer, `1`/NORMAL gets 4s then falls to the notification list. An `expire_timeout=0` vs `-1` implementation wires a knob to nothing.
- **Do not use the `resident` hint.** It means "survive being *clicked*", not "survive on screen". D-02's own parenthetical in CONTEXT.md invites this exact mistake.
- **`ActionInvoked` is a broadcast signal** — we receive *every* application's notification clicks. The handler must filter on notification ids we own, or clicking an unrelated Slack notification yanks a tmux pane into focus. Correctness *and* security (threat T-05-01).
- **The `Gio.DBusProxy` must be constructed on the Gtk main thread** (in `Monitor.__init__`, before `Gtk.main()`). Signals are delivered to the `GMainContext` the proxy was built on; construct it in `poll_loop` and clicks silently never fire.
- **Keep the project `dir` in the notification title (summary), never the body.** The body is parsed as Pango markup unconditionally (`useBodyMarkup: true`); the summary is not. D-01's shape is accidentally the secure one — a repo named `<b>x</b>` is markup injection the moment it moves into an unescaped body (threat T-05-04).
- **D-05's operative predicate is `"exhaust" in p and p["exhaust"] - now >= 900`**, not `proj >= 100` — the JS sets `exhaust` only when `proj > 100` *strictly*, so `proj >= 100` would `KeyError` at exactly 100.0. This predicate also delivers D-07 for free, confirming its "no special case, no code" claim.
- **`serve()` is unguarded** (`claude-monitor.py:1699`) — a raise in its loop kills the socket thread and every session event, permanently. `poll_loop` gained a blanket `except` + traceback in `260713-fry`; `serve()` did not. The guard goes **inside the `while`, around the per-connection body** — not around the `accept()` loop, which would swallow the shutdown path. Success Criterion 5 is exactly this.
- **`project()` (QUOTA-03) is JavaScript-only** at `claude-monitor.py:931`, inside the dashboard HTML. Phase 5 ports the ~15-line formula to Python for the poll thread and asserts it in `--selfcheck`. The JS copy **stays** — it recomputes against a live browser clock. The duplication is deliberate.
- Standing constraints: no new polling, no second data source, no new runtime dependencies, X11 only, ASCII-only in code.

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

Last session: 2026-07-16T12:35:33.829Z
Stopped at: Completed 06-02-PLAN.md
Resume file: None

## Operator Next Steps

- Phase 5 is complete (3/3 plans, UAT PASS 5/5, `05-03-SUMMARY.md` backfilled 2026-07-16) — next up is `/gsd-plan-phase 6`
- Phase 6 (Notification Control & Config) context is already gathered and marked ready for planning — see `06-CONTEXT.md`
