---
phase: 07-live-session-view
plan: 03
subsystem: ui
tags: [notifications, session-lifecycle, threading, self-heal, gap-closure]

# Dependency graph
requires:
  - phase: 07-live-session-view (plan 02)
    provides: session self-heal reap (session_stale, reap_stale, _pop_stale)
  - phase: 05 (NOTIF-02)
    provides: sess_should_notify de-dupe guarantee
provides:
  - core.sess_notify_baseline pure notification-baseline fn (live-then-reaped fallback)
  - Monitor._reaped_status short-lived reaped-status memory
  - --selfcheck asserts locking reap-then-resurrect behavior (closes WR-06)
affects: [notifications, live-session-view, session-lifecycle]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure decision fn paired with its baseline resolver (sess_should_notify + sess_notify_baseline)"
    - "One-shot pop-on-resurrection memory dict, Gtk-thread single-mutator"

key-files:
  created: []
  modified:
    - claude_monitor/core.py
    - claude-monitor.py
    - claude_monitor/test_claude_monitor.py

key-decisions:
  - "Reaped-status memory + pure baseline resolver, NOT excluding alive=True from age reap (the rejected trap that would re-break 07-02 same-pane self-heal)"
  - "_reaped_status left unbounded (pop-on-resurrection), matching accepted notif_slots/notif_acts leak profile (IN-02) -- no expiry over-engineering"
  - "Explicit `is not None` test (not truthiness) in sess_notify_baseline to keep the contract exact"

patterns-established:
  - "Baseline-resolver pattern: a pure fn that computes the `old` argument another pure decision fn consumes, so the reap/resurrect boundary is testable without threading"

requirements-completed: [SESSVIEW-01, SESSVIEW-03, NOTIF-02]

coverage:
  - id: D1
    description: "sess_notify_baseline resolves handle's notification baseline as live-then-reaped fallback"
    requirement: "NOTIF-02"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py#sess_notify_baseline resurrection block"
        status: pass
    human_judgment: false
  - id: D2
    description: "Same-status reap-then-resurrect does NOT re-notify or re-arm the ! badge (CR-01 closed)"
    requirement: "NOTIF-02"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py#sess_should_notify(sess_notify_baseline(None,'waiting'),'waiting') is False"
        status: pass
    human_judgment: false
  - id: D3
    description: "Genuine-change resurrection (waiting -> done across a reap) still fires exactly one notification"
    requirement: "NOTIF-02"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py#sess_should_notify(sess_notify_baseline(None,'waiting'),'done') is True"
        status: pass
    human_judgment: false
  - id: D4
    description: "07-02 self-heal paths preserved (session_stale/reap_stale/pane_alive byte-for-byte unchanged)"
    requirement: "SESSVIEW-01"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py#session_stale reap decision (G-07-2 self-heal) block"
        status: pass
    human_judgment: false
  - id: D5
    description: "Live tray: reaped-then-resurrected same-status session reappears with no popup / no badge re-arm; killed-pane self-heal still removes within ~1 poll tick"
    requirement: "SESSVIEW-03"
    verification: []
    human_judgment: true
    rationale: "Requires a live GNOME tray session and a real ~1h idle (or observing badge/popup behavior); the deterministic proof is the --selfcheck block (D1-D4)."

# Metrics
duration: 2min
completed: 2026-07-18
status: complete
---

# Phase 7 Plan 03: Close CR-01 (reap-resurrection re-notify) Summary

**core.sess_notify_baseline seeds handle's notification baseline from a short-lived Monitor._reaped_status memory, so a genuinely-alive session reaped after 1h idle and resuming its same-status hook event reads as "no transition" instead of re-firing a "Waiting for input" popup -- restoring the NOTIF-02 de-dupe guarantee without touching session_stale.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-07-18T18:54:44Z
- **Completed:** 2026-07-18T18:57:07Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- `core.sess_notify_baseline(live_status, reaped_status)` pure fn: returns live status when present, else the reaped-status fallback (explicit `is not None`).
- `Monitor._reaped_status` dict: written in `_pop_stale` (remember-before-pop, tolerant of a concurrent `end`), consumed one-shot via `.pop(sid, None)` in `handle`.
- `handle`'s `old` now flows through `sess_notify_baseline`, correcting both the `entered`-stamp guard and the `sess_should_notify` guard -- so a same-status resurrection re-stamps neither nor re-fires the popup.
- `--selfcheck` resurrection assert block (5 cases) locks the behavior deterministically (closes WR-06).

## Task Commits

Each task was committed atomically:

1. **Task 1: core.py sess_notify_baseline pure fn** - `66d7f24` (feat)
2. **Task 2: claude-monitor.py _reaped_status wired into _pop_stale + handle** - `393aec6` (fix)
3. **Task 3: test_claude_monitor.py resurrection asserts (WR-06)** - `02c6498` (test)

## Files Created/Modified
- `claude_monitor/core.py` - Added `sess_notify_baseline` directly after `sess_should_notify`; `session_stale`/`sess_should_notify` untouched.
- `claude-monitor.py` - Added `self._reaped_status = {}` in `__init__`; remember-before-pop in `_pop_stale`; baseline seed in `handle`. `reap_stale`/`session_stale`/`pane_alive` untouched.
- `claude_monitor/test_claude_monitor.py` - Imported `sess_notify_baseline` (sorted position); added resurrection assert block after the `session_stale` block.

## Decisions Made
- Implemented the reaped-status memory approach; explicitly did NOT implement the rejected trap of excluding `alive=True` from the age reap (that would re-break the 07-02 same-pane `/exit`//`clear` self-heal, must_haves.truths[1]).
- Left `_reaped_status` unbounded with pop-on-resurrection, matching the already-accepted `notif_slots`/`notif_acts` leak profile (IN-02) -- marked with a `ponytail:` comment naming the bound; no expiry added.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- CR-01 closed and locked by `--selfcheck` (WR-06). `session_stale`/`reap_stale`/`pane_alive` byte-for-byte unchanged, so both 07-02 self-heal paths carry forward.
- Optional live-tray human verification (D5) remains for a real reap-then-resurrect observation; the deterministic proof (D1-D4) already passes.

## Self-Check: PASSED

---
*Phase: 07-live-session-view*
*Completed: 2026-07-18*
