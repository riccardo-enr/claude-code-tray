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
5-hour one, with projections of where each cap lands at reset.

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

**Shipped:** v1.2 (Usage Web Dashboard), 2026-07-13. Three milestones, four
phases, all verified. `claude-monitor.py` is ~1.8k lines of stdlib + PyGObject.

The tray now covers the full quota picture: both rolling caps (5-hour and 7-day),
where each is projected to land at reset, 30 days of persisted history, in-menu
trends, and a self-contained browser dashboard over the same store.

**Next milestone:** v1.3 (Notifications & Predictive Alerts) — see below. It merges
the two live seeds, SEED-002 (predictive quota alerts) and SEED-004 (session-finished
notification), which converge on the same shared notification path.

## Current Milestones (two parallel workstreams)

Planning is split across two workstreams (`.planning/workstreams/`). Both are open;
both write `claude-monitor.py`, so keep their edits small and disjoint.

| Workstream | Milestone | Status |
|------------|-----------|--------|
| `notifications-predictive-alerts` | v1.3 Notifications & Predictive Alerts | Phase 05 done; Phase 06 (config) unplanned |
| `vscode` | v1.4 VS Code Usage Surface | Roadmapping |

### v1.3 Notifications & Predictive Alerts (workstream `notifications-predictive-alerts`)

**Goal:** Give the tray a push voice — one notification subsystem that pulls the user
back to Claude Code when a session needs them or when quota is about to run out, so
they can context-switch away from the top bar entirely.

**Target features:**

- Shared notification path (`Gio.Notification` via PyGObject) with per-event de-dupe —
  an event fires once per state transition, never once per poll — and click-to-focus
  reusing the existing tmux-pane + Ghostty-window action
- Session **waiting-for-input** notification, fed by the existing hook -> unix socket
  status pipeline
- Session **finished (done)** notification, same pipeline
- **Predictive quota alert:** warn when either cap (5-hour or 7-day) is *projected* to
  hit 100% before its window resets — reusing v1.2's QUOTA-03 percentage projection
- Tray menu toggles for which events fire, persisted to a small JSON config under
  `~/.claude/`
- Simple global mute toggle (no quiet-hours scheduling)

**Key context:**

- SEED-002's original EWMA / `tokens_remaining` forecast plan is **obsolete**: the poll
  now runs `--api` (quick task `260712-ndo`), where token counts come back `null`. All
  projection stays percentage-denominated — the forecaster already exists as QUOTA-03.
- Hard-threshold pushes (>90%) are **not** in scope — the existing >80% icon badge
  (ALERT-01) stays the reactive signal; this milestone adds the *predictive* one.
- Closes SEED-002 and SEED-004; the config surface also absorbs the deferred
  "configurable alert threshold" item.

### v1.4 VS Code Usage Surface (workstream `vscode`)

**Goal:** Put the tray's quota and session picture inside VS Code, so usage is visible
in the same field as the code — no GNOME top bar in peripheral vision, and no separate
terminal monitor. Second frontend over the same data, not a second data pipeline.

**Target features:**

- A **VS Code extension** (TypeScript) — a genuinely new deployment target: package,
  activation events, install story. No precedent in this repo, which is Python +
  PyGObject today.
- **Status bar item** — usage % + reset countdown. The direct analogue of the tray icon.
- **Hover detail** — both caps (5-hour, 7-day), burn rate, projected usage at reset.
- **Webview dashboard** — the v1.2 self-contained HTML page in a VS Code tab. Nearly
  free: DASH-06 already forbids external refs, so it drops into a webview as-is.
- **Session status + in-editor notifications** — running / waiting / done.
- **Predictive quota alert** in-editor, off a TypeScript port of `project()`.

**Key context:**

- **Data source: read `~/.claude/usage-history.jsonl` directly.** No new IPC, no second
  poll of the slow CLI, no listening socket — upholds the SEED-001 precedent that made
  the dashboard a static `file://` page. Accepted cost: VS Code sees usage only while
  the tray is running and polling.
- **One change to the tray:** `self.sessions` (`claude-monitor.py:1554`) is an in-memory
  dict today, so nothing outside the process can see session status. Mirror it to
  `~/.claude/sessions.json` on each transition. Keeps the extension file-based and
  consistent with the JSONL choice; ~10 lines.
- **`project()` gets a third copy** (TypeScript, alongside the Python poll-thread port
  and the dashboard's JS). Consistent with the duplication already accepted deliberately
  in v1.3 — the JS copy stays because it recomputes against a live browser clock.
- **Cross-workstream conflict:** `claude-monitor.py` is written by both v1.3 (Phase 06
  config toggles) and v1.4 (session mirror). Keep the v1.4 edit to the session mirror
  alone so the merge stays trivial.
- Closes SEED-005.

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

### Active

**v1.3 (Notifications & Predictive Alerts)** — REQ-IDs in
`workstreams/notifications-predictive-alerts/REQUIREMENTS.md`: shared notification path
with de-dupe and click-to-focus (NOTIF-*), session waiting/done events (SESS-*),
predictive quota alert off the QUOTA-03 projection (ALERT-*), menu-toggle config with
global mute (CFG-*).

**v1.4 (VS Code Usage Surface)** — REQ-IDs in `workstreams/vscode/REQUIREMENTS.md`:
extension scaffold and packaging (EXT-*), status bar + hover (VSC-*), webview dashboard
(VSCD-*), session mirror and in-editor session/quota notifications (VSCN-*).

Still deferred, in neither: raw data export (HIST-F1 / DASH-F2), configurable
ranges (TREND-F1 / DASH-F3).

### Out of Scope

- Burn-rate trend chart (DASH-04) — built in v1.2, then removed on review: raw per-minute throughput plots near-flat at ~30M tok/hr and the heatmap already conveyed it. The whole dashboard is deliberately usage-%-denominated.
- Cost/dollar tracking in the tray — usage %, not billing, is the goal
- The CLI's token-based `forecast` / `status` outputs — under `--api` the token counts come back `null` and those commands report "limit hit" at 20% real usage; all projection math is derived from percentages instead
- In-process GTK charting window — the dashboard is a self-contained HTML page in the browser, not a Gtk-drawn chart surface (the tray stays glanceable text/unicode)
- Hosted / multi-user / network-exposed dashboard — local, single-user, `file://` over the local JSONL
- Wayland support — the app is X11-only
- Bundling/replacing the `claude-monitor` CLI — we consume it, not vendor it

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
*Last updated: 2026-07-14 — milestone v1.4 (VS Code Usage Surface) started in the new
`vscode` workstream, in parallel with v1.3 (Phase 06 still open in
`notifications-predictive-alerts`). Planning split into workstreams; PROJECT.md,
MILESTONES.md and seeds/ remain shared. v1.4 closes SEED-005: a second frontend over the
existing JSONL, not a second data pipeline. Both workstreams write `claude-monitor.py` —
keep their edits disjoint.*
