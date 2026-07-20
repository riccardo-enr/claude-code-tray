---
phase: 07-live-session-view
plan: 02
subsystem: infra
tags: [tmux, threading, session-lifecycle, self-heal, gap-closure]

# Dependency graph
requires:
  - phase: 07-live-session-view (plan 01)
    provides: Monitor.handle() entered stamp + write_dashboard sessions snapshot
provides:
  - core.session_stale(alive, entered, now, max_age) pure reap-decision function
  - core.REAP_MAX_AGE (3600s self-heal ceiling)
  - pane_alive(pane, tmux) tri-state tmux pane-existence check
  - Monitor.reap_stale(now) / Monitor._pop_stale(sids) wired into poll_loop
affects:
  - claude-monitor.py tray menu (self.sessions is the single source both the menu and the dashboard read)
  - claude_monitor/dashboard.py Sessions panel (indirectly -- stale entries never reach write_dashboard's snapshot)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - tri-state liveness check (True/False/None) so "confirmed dead" and "ambiguous" never collapse into the same reap decision
    - poll-thread compute + Gtk-thread mutate via GLib.idle_add, extended from read-only snapshots to a WRITE path for the first time

key-files:
  created: []
  modified:
    - claude_monitor/core.py
    - claude-monitor.py
    - claude_monitor/test_claude_monitor.py

key-decisions:
  - "alive=True and alive=None both fall through to the SAME unconditional age-ceiling check -- alive=True never short-circuits to \"never reap\", because a pane surviving /exit or /clear in the exact same tmux pane is precisely the case pane-liveness alone cannot see (SessionEnd fires for neither)."
  - "REAP_MAX_AGE defaults to 3600s (1 hour) -- aggressive-looking but safe by design: Monitor.handle() re-setdefault()s a fresh dict on a reaped-but-still-alive session's next real event, so it just reappears with a reset duration counter, no data loss."
  - "reap_stale never mutates self.sessions directly; the pop is handed back via GLib.idle_add(self._pop_stale, ...), preserving the single-mutator (Gtk-thread-only) invariant Monitor.handle() already established."

requirements-completed: [SESSVIEW-01, SESSVIEW-03]

coverage:
  - id: D1
    description: "core.session_stale pure reap-decision function covering pane-confirmed-dead (immediate reap), pane-alive/unknown-liveness (age-ceiling fallback), no-entered-stamp (creation-race guard), and the exact age boundary"
    requirement: SESSVIEW-01
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py --selfcheck (session_stale reap decision block)"
        status: pass
    human_judgment: false
  - id: D2
    description: "pane_alive(pane, tmux) tri-state tmux existence check, never raises"
    requirement: SESSVIEW-01
    verification:
      - kind: unit
        ref: "python3 -m py_compile claude-monitor.py && ruff check claude-monitor.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "A session whose tmux pane is killed disappears from the tray menu and dashboard panel within ~1 poll tick, with no SessionEnd required; a genuinely active session is never wrongly reaped"
    requirement: SESSVIEW-03
    verification: []
    human_judgment: true
    rationale: "Requires a live GUI (tray + dashboard) and an actual tmux pane kill to observe end-to-end self-heal timing and confirm no false-positive reap of an active session -- not automatable from this environment."

# Metrics
duration: ~3min
completed: 2026-07-18
status: complete
---

# Phase 07 Plan 02: Session Self-Heal Reap (Gap Closure G-07-2) Summary

Added a local self-heal safeguard -- tmux pane-liveness check for immediate detection plus a universal 1-hour age ceiling -- so `self.sessions` entries no longer freeze forever when Claude Code's upstream-unreliable `SessionEnd` hook never fires (killed pane, `/exit` #17885, `/clear` #6428).

## Performance

- **Duration:** ~3 min (3 task commits, 17:50:35Z -> 17:52:23Z)
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- `core.session_stale(alive, entered, now, max_age)`: pure reap-decision function. `alive=False` reaps immediately (pane confirmed gone); `alive=True`/`None` both fall through to the same unconditional age-ceiling check so the same-pane `/exit`/`/clear` case (pane survives, but the session is dead) still gets caught.
- `pane_alive(pane, tmux)`: tri-state (`True`/`False`/`None`) tmux pane-existence check, sibling to the existing `pane_onscreen`, never raises.
- `Monitor.reap_stale(now)` (poll thread, shells out via `pane_alive`) + `Monitor._pop_stale(sids)` (Gtk thread, the only place `self.sessions.pop()` is called), wired via `GLib.idle_add` -- `self.sessions` stays single-mutator.
- `poll_loop` calls `mon.reap_stale(now)` unconditionally every tick, right after `now = time.time()`.
- `--selfcheck` locks all four `session_stale` behavior cases plus the exact age boundary.

## Task Commits

Each task was committed atomically:

1. **Task 1: core.py -- REAP_MAX_AGE + session_stale** - `621949c` (feat)
2. **Task 2: claude-monitor.py -- pane_alive + Monitor.reap_stale wired into poll_loop** - `bdb3b84` (feat)
3. **Task 3: test_claude_monitor.py -- lock session_stale's reap decision** - `3c9f798` (test)

_Note: Task 1 was marked `tdd="true"` in the plan, but the plan itself structures the assert coverage as a separate Task 3 (after Task 2's wiring) rather than a RED-before-GREEN pair inside Task 1 -- Task 1's own `<verify>` block only specifies compile+ruff, no test run. Executed exactly as the plan's task boundaries specify; see "TDD Gate Compliance" below._

## Files Created/Modified

- `claude_monitor/core.py` - `REAP_MAX_AGE` constant + `session_stale` pure reap-decision function
- `claude-monitor.py` - `pane_alive` tmux check, `Monitor.reap_stale`/`Monitor._pop_stale`, wired into `poll_loop`
- `claude_monitor/test_claude_monitor.py` - `session_stale` import + reap-decision assert block

## Decisions Made

- `alive=True` never short-circuits to "never reap" -- only the unconditional age ceiling catches the same-pane `/exit`/`/clear` case (see key-decisions in frontmatter).
- `REAP_MAX_AGE = 3600` (1 hour): aggressive but safe, since a wrongly-reaped-but-still-alive session simply reappears fresh on its next real hook event (no persistence, no data loss).
- `reap_stale` never mutates `self.sessions` directly -- the actual pop runs exclusively in `Monitor._pop_stale`, invoked via `GLib.idle_add`, extending the existing single-mutator (Gtk-thread-only) invariant to a new WRITE path for the first time (previously only reads crossed the poll-thread/Gtk-thread boundary).

## Deviations from Plan

None - plan executed exactly as written.

## TDD Gate Compliance

Task 1 carries `tdd="true"` in its frontmatter, but the plan's own task structure places the `session_stale` assert coverage in Task 3 (after Task 2's `pane_alive`/wiring work), not inside Task 1 as a RED-before-GREEN pair. Task 1's `<verify>` block explicitly specifies `py_compile` + `ruff` only, no test invocation. Followed the plan's literal task boundaries and verify blocks rather than force a synthetic RED commit that would duplicate Task 3's import/assert additions. Net result is unchanged: a `feat` commit (Task 1, implementation) followed by a `test` commit (Task 3, coverage) both exist in the git log, just not adjacent (Task 2's `feat` sits between them). No gap in coverage -- Task 3's `--selfcheck` block exercises every behavior case from Task 1's `<behavior>` spec plus the exact age boundary.

## Issues Encountered

None - all automated verification passed on first attempt (compile, ruff, `--selfcheck` all green after each task).

## User Setup Required

None - no external service configuration required.

## Human Verification Pending

The plan's Task 2 `<verify>` includes a `human-check` step that requires a live tray + tmux session: kill a tracked session's pane directly (bypassing `SessionEnd`) and confirm it disappears from both the tray menu and the dashboard Sessions panel within ~1 poll tick (~15s), while a genuinely active session is never wrongly reaped. This plan contains no `checkpoint:*` task (all three tasks are `type="auto"`, `autonomous: true`), so per the executor's Pattern A (fully autonomous) this was not a blocking gate -- it is recorded here as **D3** in the coverage block (`human_judgment: true`) for the phase's UAT pass, consistent with how 07-01's human verification items were persisted as UAT.

The tray was restarted (`just restart`) after all three commits so the running daemon loads the new reap logic; `just selfcheck` and `just lint` both pass post-restart.

## Next Phase Readiness

- G-07-2 closed: `self.sessions` now self-heals off both `SessionEnd`-unreliable exit paths (killed pane -> immediate pane-confirmed-dead reap; `/exit`/`/clear` same-pane -> 1-hour age-ceiling reap) without any new thread, IPC, or persistence.
- Live UAT (D3 above) still needs a human pass with the tray actually running and a real tmux pane killed -- recommended before closing out phase 07's UAT gap tracking.
- No blockers for phase completion; this was the sole incomplete plan in phase 07.

---
*Phase: 07-live-session-view*
*Completed: 2026-07-18*

## Self-Check: PASSED

- FOUND: claude_monitor/core.py (session_stale + REAP_MAX_AGE present)
- FOUND: claude-monitor.py (pane_alive + Monitor.reap_stale present)
- FOUND: claude_monitor/test_claude_monitor.py (session_stale imported and asserted)
- FOUND: 07-02-SUMMARY.md
- FOUND commit: 621949c
- FOUND commit: bdb3b84
- FOUND commit: 3c9f798
