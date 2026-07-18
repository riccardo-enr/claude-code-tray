# Roadmap: claude-code-tray

## Overview

A GNOME top-bar tray indicator for Claude Code. It shows per-session status and
focuses the originating tmux pane + Ghostty window on click. Three shipped
milestones extended that same single-file helper (`claude-monitor.py`) into a
quota monitor: point-in-time usage, then persisted history and in-menu trends,
then a browsable HTML dashboard.

v1.3 gives that tray a **push voice**: one notification subsystem, with the
session events and the predictive quota alerts riding it as two producers — so
the user can context-switch away from the top bar and get pulled back only when
a session needs them or quota is about to run out.

Constraints that held across all three shipped milestones, and hold here: stdlib

+ PyGObject only, X11-only, one background poll, no new dependencies.

Full phase detail for shipped milestones lives in `.planning/milestones/`;
per-phase artifacts remain under `.planning/phases/`.

## Milestones

- ✅ **v1.0 Usage & Quota Monitoring** — Phase 1 (shipped 2026-07-11)
- ✅ **v1.1 Usage History & Trends** — Phases 2-3 (shipped 2026-07-12)
- ✅ **v1.2 Usage Web Dashboard** — Phase 4 (shipped 2026-07-13) — [archive](./milestones/v1.2-ROADMAP.md)
- ✅ **v1.3 Notifications & Predictive Alerts** — Phases 5-6 (shipped 2026-07-17)
- 🚧 **v1.4 Session Dashboard** — Phase 7 (executed, live UAT pending)

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

### ✅ v1.3 Notifications & Predictive Alerts (Phases 5-6) — COMPLETE

**Milestone Goal:** One notification subsystem that all tray events route through,
so the user can leave the top bar and still be pulled back when a session needs
them or when a quota cap is projected to run out. Merges SEED-002 + SEED-004.

- [x] **Phase 5: Notification Path & Event Producers** - One shared emit path, with session waiting/done events and predictive 5h/7d quota alerts riding it
- [x] **Phase 6: Notification Control & Config** - Per-event tray toggles, global mute, and a configurable badge threshold, persisted and corruption-tolerant

### 🚧 v1.4 Session Dashboard (Phase 7) — EXECUTED (live UAT pending)

**Milestone Goal:** See all live Claude Code sessions and their status at a glance in
the existing web dashboard, not just in the tray menu. Live-only, extends the v1.2
self-contained dashboard; no new IPC, socket, or persistence.

- [x] **Phase 7: Live Session View in the Dashboard** - Embed the tray's current in-memory session snapshot into the generated dashboard HTML, rendered as a live-refreshing session panel

## Phase Details

### Phase 5: Notification Path & Event Producers

**Goal**: The tray can pull the user back — one shared notification path, de-duped and click-to-focus, with both producers (session events, predictive quota alerts) riding it.
**Depends on**: Phase 4 (QUOTA-03 projection semantics)
**Requirements**: NOTIF-01, NOTIF-02, NOTIF-03, NOTIF-04, SESS-01, SESS-02, ALERT-02, ALERT-03, ALERT-04
**Success Criteria** (what must be TRUE):

  1. When a session starts waiting for input, a desktop notification appears; when it finishes, a done notification appears — once per state transition, never once per tick.
  2. Clicking a session notification focuses that session's tmux pane and raises the terminal window — same outcome as clicking the tray row.
  3. When either cap (5-hour or 7-day) is projected to hit 100% before its window resets, a notification fires once; when the projection says usage coasts to reset, nothing fires.
  4. After a cap's window rolls over, that cap can alert again — a previous warning does not suppress the fresh window.
  5. With the notification daemon absent or failing, the tray keeps polling, rendering, and serving session events — no crash, no dead thread, no stalled menu.

**Plans**: 3/3 plans executed (UAT PASS 2026-07-14)

Plans:
**Wave 1**

- [x] 05-01-PLAN.md — The shared notification path: `Gio.DBusProxy` to `org.freedesktop.Notifications`, one `emit_notif` choke point with the mute-gate seam and replace-in-place slots, an id-filtered `ActionInvoked` click dispatcher, and a hardened `serve()`

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 05-02-PLAN.md — SESS producer: `sess_should_notify` de-dupe + `Monitor.handle` emits `waiting` (sticky) / `done` (expiring) notifications that click through to the tmux pane

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 05-03-PLAN.md — ALERT producer: Python port of the QUOTA-03 `project()` formula plus the lead-time and arm/re-arm predicates, driving one predictive 5h/7d quota alert per window from `poll_loop`

**Binding settled at plan time** (was the phase's open load-bearing decision):
Route B — `org.freedesktop.Notifications.Notify` over `Gio.DBusProxy`. Route A
(`Gio.Application` + `Gio.Notification`) is not merely costlier but *impossible* here:
gnome-shell's `GtkNotificationDaemonAppSource` looks up `appId + '.desktop'` and **drops the
notification entirely** when it is absent, and this app is a single-file script with no
install step. Verified against gnome-shell 46.0's own source and live D-Bus probes
(`05-RESEARCH.md`). Two consequences the plans encode: D-02's divergent lifetimes ride the
`urgency` hint (2 = critical/sticky, 1 = normal/expiring), **not** `expire_timeout`, which
this daemon destructures and never reads; and `ActionInvoked` is a **broadcast**, so the
click handler must filter on notification ids we own or a click on any other app's
notification would drive `Monitor.focus()`.

**Why both producers land in one phase:** the deliverable is the *shared path*
(emit + de-dupe + mute hook + click-to-focus), not either ping. Building the path
against one producer and bolting the second on later is how it grows two heads —
the failure mode SEED-004 explicitly called out. Both producers in one phase means
the path generalizes by construction.

**Grounding (verified against `claude-monitor.py`, read before planning):**

- **`project()` is JS-only today.** QUOTA-03's projection lives at
  `claude-monitor.py:931` as JavaScript *inside the dashboard HTML*. There is no
  Python-side projection — `poll_loop` never computes one. ALERT-02/03 must
  evaluate it on the poll thread, so this phase **ports** that ~15-line formula
  (elapsed-fraction linear extrapolation, `e<=0.05` early guard, exhaust-time when
  `proj>100`) into Python. Fixed, known arithmetic — assert it in `--selfcheck`
  against the same cases. **Not** modeling work, and **not** a new forecaster.
  The JS copy necessarily stays (it recomputes against a live browser clock); that
  duplication is deliberate and should be noted where it lands.

- **There is no `Gio.Application`.** `claude-monitor.py:1817` is a bare
  `Gtk.main()`. `Gio.Notification` + `send_notification` needs a `Gio.Application`
  (and, for notification *actions* to route back — NOTIF-03 — an app id with a
  matching `.desktop`). The alternative is `org.freedesktop.Notifications.Notify`
  over `Gio.DBusProxy`, which carries `actions` + an `ActionInvoked` signal with no
  app-id/.desktop plumbing. **This is the phase's load-bearing decision** — settle
  it in `/gsd-plan-phase 5`, not here. NOTIF-01's "`Gio.Notification`" is intent
  ("PyGObject, no new dependency"), not a binding choice.

- **`serve()` is unguarded.** `poll_loop` got a blanket `except` + traceback from
  quick task `260713-fry`, so the alert producer inherits that protection.
  `serve()` (`claude-monitor.py:1705`) did **not** — a raise in its loop kills the
  socket thread and *all* session events, permanently. The session producer rides
  that thread. NOTIF-04 has real teeth here.

- Session state transitions land in `Monitor.handle` via `GLib.idle_add`, i.e. on
  the Gtk main thread. Whatever emit path is chosen must be non-blocking there
  (D-Bus notify is async; a `subprocess` shell-out is not).

**Verification:** `--selfcheck` asserts (projection port, de-dupe/arm state as pure
functions) + human UAT on the live tray.

### Phase 6: Notification Control & Config

**Goal**: The user decides what fires — per-event toggles, one global mute, and a configurable badge threshold, persisted across restarts and safe against a corrupt config.
**Depends on**: Phase 5 (all four event types must exist to be toggled)
**Requirements**: CFG-01, CFG-02, CFG-03, CFG-04, CFG-05
**Success Criteria** (what must be TRUE):

  1. Each of the four event types (waiting / done / 5h alert / 7d alert) can be switched on and off from the tray menu, and the next event honors the change with no restart.
  2. A single "mute all" tray toggle silences every notification while the tray rows and icon badge keep working.
  3. Toggle states survive a restart of the helper.
  4. A missing, unreadable, or malformed config file leaves the tray running on defaults — never a crash, matching the history store's total-tolerance bar.
  5. The high-usage badge threshold is configurable rather than a hard-coded 80%, and the badge follows the configured value.

**Plans**: 2/2 plans executed

Plans:
**Wave 1**

- [x] 06-01-PLAN.md — Config data layer: tolerant `parse_config`/atomic `save_config` for `~/.claude/tray-config.json`, a config-driven `notif_allowed(kind, config)` (mute wins, D-04), and a configurable `build_label` threshold

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 06-02-PLAN.md — Tray menu UI: "Notifications" submenu (mute-all + four event checkboxes, D-03) and a nested "Badge threshold" radio submenu (D-05), both persisting through Plan 1's config layer

**Notes:**

- CFG-04's bar is set by precedent, not aspiration: a corrupt *history* record
  already killed the poll thread once (`260713-fry`). Config reads must be as
  total-tolerant as `parse_history` — malformed JSON, wrong shape, non-UTF8, and
  missing file all fall back to defaults.

- CFG-05 closes the deferred "Alerting: configurable threshold" item and retires
  the fixed 80% constant used by the badge (both caps).

- Open question carried from REQUIREMENTS.md: whether the config file subsumes the
  existing `CLAUDE_TRAY_*` env vars or layers over them (lean: env as default, menu
  as override). Settle at plan time.

### Phase 7: Live Session View in the Dashboard

**Goal**: See all currently-tracked Claude Code sessions and their status at a glance in the existing web dashboard, refreshed live, without leaving the top bar or opening the tray menu.
**Depends on**: Phase 4 (the self-contained dashboard + its regeneration/refresh path)
**Requirements**: SESSVIEW-01, SESSVIEW-02, SESSVIEW-03, SESSVIEW-04, SESSVIEW-05
**Success Criteria** (what must be TRUE):

  1. The dashboard shows every session the tray currently tracks, each with its status (running / waiting / done).
  2. Each session row shows its project directory and how long it has been in its current state.
  3. The session panel reflects the tray's live in-memory session state and updates on the dashboard's existing meta-refresh cadence — no new IPC, socket, or persistence is introduced.
  4. With no active sessions, the panel shows a clean empty state instead of breaking or rendering blank.
  5. The dashboard remains fully self-contained (no external references), consistent with DASH-06.

**Plans**: 3/3 plans executed

Plans:

- [x] 07-02-PLAN.md
- [x] 07-03-PLAN.md — Gap closure CR-01: reaped-status memory (`core.sess_notify_baseline` + `Monitor._reaped_status`) so a genuinely-alive session reaped past REAP_MAX_AGE and resumed does not re-fire a notification (restores NOTIF-02), with a `--selfcheck` assert locking the resurrection behavior (WR-06); `session_stale` left untouched so both 07-02 self-heal paths hold

**Wave 1**

- [x] 07-01-PLAN.md — Session panel: `entered`-on-change stamp in handle(), sessions snapshot threaded into render_dashboard, `"sessions"` payload key, inline table + dot CSS + 1s client-side live-ticker (textContent rows, dir kept inert), and locking --selfcheck asserts

## Progress

**Execution Order:** Phases execute in numeric order: 5 → 6 → 7

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Usage & Quota Monitoring in the Tray | v1.0 | 1/1 | Complete | 2026-07-11 |
| 2. Usage History Persistence | v1.1 | 1/1 | Complete | 2026-07-12 |
| 3. Usage Trends in the Tray | v1.1 | 1/1 | Complete | 2026-07-12 |
| 4. Usage Web Dashboard | v1.2 | 1/1 | Complete | 2026-07-13 |
| 5. Notification Path & Event Producers | v1.3 | 3/3 | Complete | 2026-07-14 |
| 6. Notification Control & Config | v1.3 | 2/2 | Complete | 2026-07-17 |
| 7. Live Session View in the Dashboard | v1.4 | 3/3 | In Progress|  |
