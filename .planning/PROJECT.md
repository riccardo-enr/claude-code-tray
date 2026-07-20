# claude-code-tray

## What This Is

A GNOME top-bar tray indicator for Claude Code. It already shows per-session
status (running / waiting / done) fed by Claude Code hooks over a unix socket,
and focuses the originating tmux pane + Ghostty window on click. v1.0 added
**token-usage and quota-reset monitoring** (current usage vs plan limit, reset
countdown, burn rate). v1.1 added **usage history and trends** on top: persisted
samples, an in-menu sparkline, daily/weekly burn, and peak-usage hours. v1.2
added a **browsable HTML usage dashboard** opened from the tray — the same
history as real charts (usage-% trend over rolling ranges, hour x day heatmap,
dark mode) — and made the **weekly (7-day) quota cap** visible alongside the
5-hour one, with projections of where each cap lands at reset. v1.3 gave the
tray a **push voice**: one shared desktop-notification path for session
waiting/done events and predictive 5h/7d quota alerts, with per-event toggles
and a global mute. v1.4 put a **live sessions panel** in that same dashboard —
every tracked session with status/dir/duration, self-healing off the list when
a tmux pane dies with no hook event required.

## Core Value

At a glance from the top bar, know **how much Claude Code quota is left and when
it resets** — without launching a separate terminal monitor.

## Context

- **Platform:** Ubuntu GNOME on X11; Python 3 + PyGObject (Gtk3, Ayatana
  AppIndicator3). Single long-lived helper process (`claude-monitor.py`) plus a
  fire-and-forget hook sender (`claude-send.py`).
- **Data source (decided):** shell out to the already-installed `claude-monitor`
  CLI (Claude Code Usage Monitor) with `--plan max5 --output json --once`. It
  parses `~/.claude/projects/**/*.jsonl` and returns `limits.five_hour`
  (`used_percentage`, `tokens_used`, `token_limit`, `resets_at_epoch`) plus
  `local.tokens` and burn rate. Reused rather than reinventing the rolling-window
  + plan-limit math.
- **Naming caution:** the usage tool is *also* called `claude-monitor`; our
  helper is `claude-monitor.py` in `~/.claude/hooks/`. Keep the distinction
  clear (invoke the CLI by absolute path `~/.local/bin/claude-monitor`).
- **Performance constraint:** the CLI takes a few seconds to run, so polling
  must happen on a background thread on an interval, never on the Gtk main loop.

## Current State

**Shipped:** v1.4 (Session Dashboard), 2026-07-20 — bundled with v1.3's formal
close-out (Notifications & Predictive Alerts, features live since 2026-07-17).
Five milestones, seven phases, all implemented and reviewed. `claude-monitor.py`
was restructured into a `claude_monitor/` package (`core.py` + `dashboard.py` +
entry script) during v1.3/v1.4.

The tray now covers the full quota picture (both rolling caps, projected reset,
30 days of persisted history, in-menu trends, a self-contained browser dashboard),
pushes the user back via desktop notifications (session waiting/done, predictive
5h/7d quota alerts, per-event toggles, global mute), and shows every live session
— status, project dir, time-in-state — directly in that same dashboard, self-healing
off the list when a tmux pane dies with no hook event required.

**Next milestone:** none yet — planning next via `/gsd-new-milestone`.

## Current Milestone

No workstream is currently open. `notifications-predictive-alerts` shipped v1.4
2026-07-20 (tag `v1.4`) and is archived under
`workstreams/notifications-predictive-alerts/milestones/`.

## Requirements

### Validated

- checkmark Per-session status in tray menu (running/waiting/done) — existing
- checkmark Click-to-focus tmux pane + raise terminal window — existing
- checkmark Hook -> unix socket event pipeline (`claude-send.py`) — existing
- checkmark Autostart via `~/.config/autostart` + env-configurable icon/WM_CLASS — existing
- checkmark Background-interval `claude-monitor` poll without blocking the UI (POLL-01) — v1.0
- checkmark Graceful degradation to "usage unavailable" on CLI failure (POLL-02) — v1.0
- checkmark Tokens/% of plan limit, reset countdown, burn rate in the tray (USAGE-01/02/03) — v1.0
- checkmark High-usage icon badge above threshold (ALERT-01) — v1.0
- checkmark Persist each successful poll sample to a JSONL history store (HIST-01) — Phase 2
- checkmark Prune history past a retention window, default 30 days env-configurable (HIST-02) — Phase 2
- checkmark Defensive history I/O — never crash/block the helper (HIST-03) — Phase 2
- checkmark In-menu sparkline of usage % over a recent window (TREND-01) — Phase 3
- checkmark Daily / weekly aggregate burn in the menu (TREND-02) — Phase 3
- checkmark Peak-usage hours in the menu (TREND-03) — Phase 3
- checkmark Dashboard opened in the browser from a tray menu item (DASH-01) — v1.2
- checkmark Usage-% trend over rolling 24h/7d/All, broken across data gaps (DASH-02/08) — v1.2
- checkmark Hour-of-day x day-of-week peak-usage heatmap (DASH-03) — v1.2
- checkmark Read-only over the existing JSONL, refreshed on the existing poll tick (DASH-05) — v1.2
- checkmark Self-contained stdlib-only output, assertion-enforced (DASH-06) — v1.2
- checkmark Dark-mode toggle with inverted heatmap ramp (DASH-07) — v1.2
- checkmark Weekly (7-day) cap in tray rows, badge, and dashboard (QUOTA-01) — v1.2
- checkmark Reset epochs persisted; window resets marked on the trend (QUOTA-02) — v1.2
- checkmark Projected usage at reset for both caps (QUOTA-03) — v1.2
- checkmark Live in-browser auto-refresh of the dashboard (DASH-F1) — v1.2 (`ea00509`)
- checkmark Shared notification path with de-dupe + click-to-focus (NOTIF-01..04) — v1.3
- checkmark Session waiting/done desktop notifications (SESS-01/02) — v1.3
- checkmark Predictive 5h/7d quota alert off the QUOTA-03 projection (ALERT-02/03/04) — v1.3
- checkmark Per-event tray toggles, global mute, configurable badge threshold, persisted + corruption-tolerant (CFG-01..05) — v1.3
- checkmark Live sessions panel in the dashboard, status/dir/time-in-state (SESSVIEW-01/02) — v1.4
- checkmark Live in-memory reflect on existing meta-refresh, no new IPC/socket/persistence (SESSVIEW-03) — v1.4
- checkmark Clean empty state with no active sessions (SESSVIEW-04) — v1.4
- checkmark Dashboard stays self-contained with the sessions panel added (SESSVIEW-05) — v1.4

### Active

None yet — planning next milestone via `/gsd-new-milestone`.

Still deferred: raw data export (HIST-F1 / DASH-F2), configurable
ranges (TREND-F1 / DASH-F3), quiet hours (NOTIF-F1), per-event sound/urgency
(NOTIF-F2), hard-threshold push (ALERT-F1). See
`workstreams/notifications-predictive-alerts/STATE.md` "Deferred Items" for the
full table with dates and reasoning.

### Out of Scope

- Burn-rate trend chart (DASH-04) — built in v1.2, then removed on review: raw per-minute throughput plots near-flat at ~30M tok/hr and the heatmap already conveyed it. The whole dashboard is deliberately usage-%-denominated.
- Cost/dollar tracking in the tray — usage %, not billing, is the goal
- The CLI's token-based `forecast` / `status` outputs — under `--api` the token counts come back `null` and those commands report "limit hit" at 20% real usage; all projection math is derived from percentages instead
- In-process GTK charting window — the dashboard is a self-contained HTML page in the browser, not a Gtk-drawn chart surface (the tray stays glanceable text/unicode)
- Hosted / multi-user / network-exposed dashboard — local, single-user, `file://` over the local JSONL
- Wayland support — the app is X11-only
- Bundling/replacing the `claude-monitor` CLI — we consume it, not vendor it
- **A VS Code extension surface (former v1.4, SEED-005)** — planned as a status bar item, webview dashboard, and in-editor notifications, then dropped before any code was written: the user no longer works in VS Code, so the whole milestone served a frontend nobody would open. The tray remains the only frontend besides the browser dashboard.

*(Removed from Out of Scope: "7-day / weekly limit display — the CLI reports it
as null for this account". It does populate under `limits.seven_day`; delivered
as QUOTA-01 in v1.2.)*

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Consume `claude-monitor --output json` for usage data | Purpose-built, already installed, computes window+limit+burn; avoids reinventing | ✓ Good — held across three milestones |
| Query the CLI's `custom` dynamic limits (P90), not static `max5` | `max5`'s fixed 88k limit mismatched the real ~926k ceiling and inflated % ~10x ("148%" vs real ~15%); `custom` matches the CLI's own TUI. Override via `CLAUDE_TRAY_PLAN` | Corrected in Phase 1 |
| Background-thread polling on an interval | CLI is slow (~seconds); must not block Gtk main loop | ✓ Good — every later feature (history, trends, dashboard) hangs off this one tick |
| Show tokens+%, reset time, burn rate, high-usage badge | The at-a-glance signals the user wants | Shipped in v1.0 |
| Degrade to "usage unavailable" only after N consecutive poll misses (not the first) | Absorbs transient CLI hiccups (WR-03) while still surfacing sustained failure (POLL-02) | v1.1 baseline (fixed in v1.0 UAT) |
| Persist usage history as append-only JSONL under `~/.claude/`, pruned by retention window | Simplest durable store for a lightweight helper; no DB dependency; reuses the existing poll sample | Shipped in Phase 2 |
| `parse_history` keeps only JSON objects with a numeric `t`; prune reads `errors="replace"` | Corruption tolerance must be total — a valid-JSON-but-wrong-shape or non-UTF8 line must never raise and kill the poll thread (code-review WR-01) | ⚠️ Revisit — not total enough: a corrupt record still crashed `compute_trends` post-v1.2 (quick task `260713-fry`). Fixed by routing trends through `history_numeric` **and** guarding `poll_loop` so the daemon thread cannot die |
| Dashboard is a static self-contained `file://` page regenerated on the poll tick — no server, no port | The open SEED-001 question (static file vs. loopback `http.server`); static avoids a listening socket, a port, and a serving lifecycle for a single-user local page | ✓ Good — DASH-06 self-containment became assertable (`--selfcheck` fails the build on any external ref) |
| Dashboard ranges are rolling (24h / 7d / All), not calendar day/week | A calendar window that resets at local midnight (or Monday) hides the most recent activity right after it rolls; rolling also mirrors how Claude's own quota windows work | ✓ Good |
| All projection/forecast math derives from percentages, never the CLI's token-based `forecast`/`status` | Under `--api` token counts come back `null` and those commands report "limit hit" — wiring them in would have claimed exhaustion at 20% real usage | ✓ Good — caught before shipping |
| Trend line breaks across sampling gaps instead of interpolating | A 13.7h outage was rendering as a smooth "decline" that never happened — the chart was asserting data it did not have | ✓ Good |
| Cut DASH-04 (burn-rate chart) during UAT rather than ship it | It plotted near-flat ~30M tok/hr raw throughput and duplicated the heatmap; the dashboard is deliberately usage-%-denominated | ✓ Good — scope decision made against the running artifact |
| v1.3 predictive alerts reuse the existing QUOTA-03 percentage projection instead of building SEED-002's EWMA / `tokens_remaining` forecaster | SEED-002 was written before the `--api` switch (`260712-ndo`) made token counts `null`. A token-denominated forecaster cannot be built on the data we now poll, and the percentage projection that *can* already ships | Decided at v1.3 scoping — SEED-002's "Better Than Upstream" section is superseded |
| One notification subsystem, two producers (session events + quota alerts), rather than a one-off "session done" ping | SEED-004 called this out explicitly: the value is the shared path (de-dupe, mute, click-to-focus), not the single ping. Two one-offs would duplicate all of it | Decided at v1.3 scoping |
| Notification binding: `org.freedesktop.Notifications.Notify` via `Gio.DBusProxy`, not `Gio.Notification` | The helper has no `Gio.Application`; gnome-shell's `GtkNotificationDaemonAppSource` looks up `appId + '.desktop'` and silently drops the notification when absent — a single-file script with no install step can't satisfy that. Verified against gnome-shell 46.0 source + live D-Bus probes | ✓ Good — Phase 5 |
| `urgency` hint drives notification lifetime (D-02), not `expire_timeout` | gnome-shell destructures `expire_timeout` as `timeout_` and never reads it; banner life is a hardcoded 4000ms. Only `urgency=2/CRITICAL` skips the auto-dismiss timer | ✓ Good — Phase 5 |
| `Monitor._reaped_status` + pure `core.sess_notify_baseline` seed the notification de-dupe baseline across a reap/resurrect | CR-01: a genuinely-alive session reaped past `REAP_MAX_AGE` and resuming the same status re-fired a spurious "Waiting for input" popup, regressing NOTIF-02. Fixed with a one-shot Gtk-thread-only memory, not by excluding `alive=True` from the age reap (would have broken the same-pane `/exit` self-heal) | ✓ Good — Phase 7-03, closed CR-01/WR-06 |
| v1.3 was never run through `/gsd-complete-milestone` on its own; closed out bundled with v1.4 | Phase 5 had no VERIFICATION.md (missing, not failed) despite shipping live 2026-07-17 with a passing REVIEW.md and UAT.md. Re-verifying weeks-old shipped code was judged lower value than accepting a recorded closeout override | Acknowledged override — see `workstreams/.../STATE.md` Deferred Items |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-20 — after v1.4 (Session Dashboard) milestone completion,
bundled with v1.3's (Notifications & Predictive Alerts) formal close-out. No
workstream is currently open; next milestone starts via `/gsd-new-milestone`.*
