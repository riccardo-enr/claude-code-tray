---
id: SEED-005
status: planted
sprouted_into:
planted: 2026-07-17
planted_during: v1.4 Phase 7 discuss-phase (deferred to next session)
trigger_when: next work session; discuss + plan Phase 7 (Live Session View)
scope: small-medium
---

# SEED-005: Live Session View in the Dashboard

## Why This Matters

The tray menu already lists every tracked Claude Code session as `dir [status]`,
but you have to open the menu to see it. The v1.2 dashboard is the natural place
to show all live sessions at a glance without touching the top bar. This is
Phase 7 of v1.4 (SESSVIEW-01..05) -- read-side only, extends the existing
self-contained dashboard, no new IPC/socket/persistence.

## When to Surface

**Trigger:** next work session. Resume with `/gsd-discuss-phase 07` on workstream
`notifications-predictive-alerts`, then `/gsd-plan-phase 07`. Discussion was
started 2026-07-17 and deferred before any CONTEXT.md was written.

## Scope Estimate

**Small-medium** -- one phase. Snapshot `self.sessions` into the payload that
`render_dashboard` already builds, add a session panel to the HTML/CSS/JS. The
only new state is a per-session "entered current status at" epoch (SESSVIEW-02).

## Open Questions (decide at discuss time)

These are the gray areas surfaced during scouting -- each genuinely can go more
than one way:

1. **Duration freshness (SESSVIEW-02).** "Time in current state" needs an
   entered-at epoch stored per session (not tracked today). Static snapshot
   ("waiting 3m") computed at generation time goes stale until the next 5-min
   refresh, vs. embedding the entered-at epoch and letting the page's own JS
   tick a live counter (stays accurate between refreshes, still self-contained).
   Leaning: embed epoch + client-side tick -- cheap and matches "live".

2. **Live-write trigger.** The dashboard file is only rewritten on the 5-min
   `write_dashboard` throttle in `poll_loop`. Session state changes fast
   (waiting appears/clears in seconds) but don't currently trigger a rewrite, so
   a change can be up to ~5 min stale on disk *before* meta-refresh even runs.
   Regenerate immediately on a session state change (still in-process, no new
   IPC -- SESSVIEW-03 stays satisfied) vs. keep the plain 5-min throttle.

3. **Panel layout & placement.** Where the panel sits (top, above the usage
   charts, vs a section below) and how each session renders (compact tray-style
   row / table / card). Reuse existing dashboard CSS.

4. **Which sessions & ordering.** Show `done` sessions (they linger in
   `self.sessions` until the `end` event) or only running/waiting? Sort order
   (waiting-first / most-recent / by dir), per-status color coding, and the
   empty-state text (SESSVIEW-04).

## Breadcrumbs

- `claude-monitor.py`
  - `self.sessions` (~L1535): `session_id -> {dir, status, pane, tmux, cwd, acked}`.
    Lives on the Gtk main thread; `write_dashboard` runs on the poll thread ->
    snapshot safely (thread-safety is a planner concern, not a gray area).
  - `handle()` (~L1840): where session state transitions happen -- the place to
    stamp an entered-at epoch, and the natural hook for an on-change dash rewrite.
  - `render_dashboard(records, now)` (~L1046): builds the JSON payload + the
    self-contained HTML; extend the payload with a `sessions` array here.
  - `write_dashboard(now)` (~L1812) and `poll_loop` throttle (~L1993, `DASH_INTERVAL`).
  - `rebuild_menu()` (~L1724): current tray rendering of sessions, for parity.
  - `_DASH_META_REFRESH` (~L230): the existing 5-min meta-refresh mechanism.
- Requirements: `SESSVIEW-01..05` in
  `.planning/workstreams/notifications-predictive-alerts/REQUIREMENTS.md`.
- Roadmap: Phase 7 detail in the same workstream's `ROADMAP.md`.
- Constraint: DASH-06 -- panel must stay self-contained (no external references).

## Notes

Captured mid-discussion (user deferred to next session). No CONTEXT.md written
yet -- start from `/gsd-discuss-phase 07` and these four gray areas.
