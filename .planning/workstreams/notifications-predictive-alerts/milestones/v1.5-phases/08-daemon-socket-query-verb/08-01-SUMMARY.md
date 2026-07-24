---
phase: 08-daemon-socket-query-verb
plan: 01
subsystem: infra
tags: [threading, thread-safety, python, socket-daemon]

# Dependency graph
requires:
  - phase: 07-session-dashboard
    provides: self.sessions single-mutator model, write_dashboard's read-only snapshot posture (D-08)
provides:
  - "Monitor.sessions_lock (threading.Lock) guarding every self.sessions call site"
  - "core.build_session_snapshot(sessions) pure function -- shared dir/status/entered/frozen/pane/tmux payload shape"
affects: [08-daemon-socket-query-verb/08-02, 09-terminal-dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "sessions_lock wraps each self.sessions call site's FULL read-modify-write or snapshot-build as one atomic unit, not individual dict ops"
    - "Lock scope kept narrow around subprocess/D-Bus calls (pane_alive, emit_notif) -- they always run outside the lock"

key-files:
  created: []
  modified:
    - claude_monitor/core.py
    - claude_monitor/test_claude_monitor.py
    - claude-monitor.py

key-decisions:
  - "build_session_snapshot placed after session_stale, before the quota-window constants/project() in core.py, matching the plan's small-pure-function placement convention"
  - "reap_stale()'s lock scope narrowed to just the list(self.sessions.items()) copy -- pane_alive's tmux shell-out and session_stale's heuristic run unlocked (T-08-02)"
  - "rebuild_menu() deliberately left unlocked -- runs exclusively on the Gtk thread via the same callbacks that mutate self.sessions, so it never races a mutation"

patterns-established:
  - "Shared snapshot builder (core.build_session_snapshot) as the single source of truth for the sessions wire/render shape, consumed by write_dashboard now and Plan 08-02's query responder next"

requirements-completed: [SOCK-01, SOCK-03]

coverage:
  - id: D1
    description: "core.build_session_snapshot(sessions) pure function returning six-key dicts (dir/status/entered/frozen/pane/tmux), JSON-serializable, never mutating input"
    requirement: SOCK-01
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py demo() build_session_snapshot assert block (shape, empty list, purity, JSON round-trip)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Monitor.sessions_lock guards all four pre-existing self.sessions call sites (handle, reap_stale, _pop_stale, write_dashboard) as atomic units"
    requirement: SOCK-03
    verification:
      - kind: unit
        ref: "python3 -m py_compile claude-monitor.py && python3 claude-monitor.py --selfcheck"
        status: pass
      - kind: other
        ref: "grep -c 'with self.sessions_lock:' claude-monitor.py == 5; grep -c 'self.sessions_lock = threading.Lock()' == 1"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-07-20
status: complete
---

# Phase 08 Plan 01: Sessions Lock + Shared Snapshot Shape Summary

**threading.Lock guarding all self.sessions call sites plus a pure core.build_session_snapshot(sessions) function establishing the dir/status/entered/frozen/pane/tmux payload shape for the upcoming query verb**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-20T11:19:00Z
- **Completed:** 2026-07-20T11:31:21Z
- **Tasks:** 2 completed
- **Files modified:** 3

## Accomplishments
- `core.build_session_snapshot(sessions)` -- pure function returning one plain six-key dict per session (dir/status/entered/frozen/pane/tmux), the exact shape both `write_dashboard()` and Plan 08-02's query responder now share
- `Monitor.sessions_lock` (threading.Lock) added and wrapped around all four pre-existing `self.sessions` access sites: `handle()`'s end-event pop and full setdefault/baseline-read/update/entered-stamp block (as one atomic unit each), `reap_stale()`'s narrow items()-copy, `_pop_stale()`'s get/pop loop, and `write_dashboard()`'s snapshot build
- `--selfcheck` asserts added for `build_session_snapshot`: running-vs-not `frozen` rule, `.get()`-based defaulting for missing pane/tmux/run_dur, empty-list input, purity/idempotency (two calls never share list identity, input never mutated), and JSON round-trip

## Task Commits

Each task was committed atomically:

1. **Task 1: core.py -- build_session_snapshot pure function + selfcheck asserts** - `6d12b95` (feat)
2. **Task 2: claude-monitor.py -- sessions_lock + wrap all four self.sessions call sites** - `098f170` (feat)

_Note: Task 2's diff also includes the user's own pre-existing uncommitted edits to claude-monitor.py (Zed terminal-focus support), which were already on disk before this plan started and are unrelated to this plan's scope; the plan's `<important_working_tree_note>` explicitly directed staging the whole file since it is listed in the plan's `files_modified`._

## Files Created/Modified
- `claude_monitor/core.py` - added `build_session_snapshot(sessions)` pure function
- `claude_monitor/test_claude_monitor.py` - imported `build_session_snapshot`; added selfcheck assert block covering shape/empty/purity/JSON
- `claude-monitor.py` - added `Monitor.sessions_lock`; wrapped `handle()`, `reap_stale()`, `_pop_stale()`, `write_dashboard()` call sites; `write_dashboard()` now delegates to `core.build_session_snapshot()`

## Decisions Made
- None beyond what the plan specified -- executed as written, including the exact lock-scope boundaries (narrow in `reap_stale()`, full-block in `handle()`/`_pop_stale()`) and the deliberate non-locking of `rebuild_menu()`.

## Deviations from Plan

**1. [Rule 1 - Bug] Comment text collided with the acceptance-criteria grep count**
- **Found during:** Task 2 verification
- **Issue:** The inline comment above the `write_dashboard()` snapshot call originally said "(core.build_session_snapshot)", which made `grep -c "core.build_session_snapshot" claude-monitor.py` return 2 instead of the plan's required 1 (the comment line and the actual call both matched).
- **Fix:** Reworded the comment to "(shared core helper below)" so only the real call site matches the acceptance-criteria grep, without losing the comment's intent.
- **Files modified:** claude-monitor.py
- **Verification:** `grep -c "core.build_session_snapshot" claude-monitor.py` now returns 1; `--selfcheck` still green.
- **Committed in:** 098f170 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug/acceptance-criteria mismatch)
**Impact on plan:** Cosmetic only -- no behavior change, no scope creep.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan 08-02 (thread-per-connection query verb) can now safely read `self.sessions` from a query thread via `sessions_lock` and build its response with `core.build_session_snapshot()`, reusing this plan's shape and locking model without re-deriving either.
- No live-daemon verification was needed for this plan (no observable runtime behavior change); Plan 08-02 will be the first to exercise the lock under real concurrency.

---
*Phase: 08-daemon-socket-query-verb*
*Completed: 2026-07-20*

## Self-Check: PASSED

All created/modified files exist on disk; both task commits (`6d12b95`, `098f170`) verified present in `git log`.
