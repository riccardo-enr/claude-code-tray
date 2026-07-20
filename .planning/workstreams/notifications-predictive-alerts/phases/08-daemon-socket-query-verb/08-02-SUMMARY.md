---
phase: 08-daemon-socket-query-verb
plan: 02
subsystem: infra
tags: [threading, unix-socket, ipc, python, socket-daemon]

# Dependency graph
requires:
  - phase: 08-daemon-socket-query-verb/08-01
    provides: Monitor.sessions_lock, core.build_session_snapshot(sessions) shared shape
provides:
  - "_handle_conn(mon, conn) module-level thread-target function -- per-connection recv/dispatch/send/close body"
  - "serve() thread-per-connection accept loop (threading.Thread(target=_handle_conn), daemon=True)"
  - "{\"query\": \"snapshot\"} socket protocol answering sessions/usage/trends on the same connection"
  - "SOCK chmod 0600 hardening"
affects: [09-terminal-dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Thread-per-connection isolation: a stalled/malformed connection blocks only its own daemon thread, never the accept loop or sibling connections"
    - "Query responder builds its snapshot under mon.sessions_lock, then reads mon.usage/mon.trends OUTSIDE the lock as single-reference rebinds (same no-lock posture compute_trends already uses)"

key-files:
  created: []
  modified:
    - claude-monitor.py

key-decisions:
  - "Split the single logical diff into two atomic task commits (thread refactor, then query dispatch) by temporarily removing Task 2's lines, verifying+committing Task 1 in isolation, then re-adding them for Task 2 -- preserves the plan's atomic-commit-per-task contract"
  - "Reformatted core.build_session_snapshot(list(mon.sessions.values())) onto one line (not the initially-written 3-line wrap) to match the plan's exact acceptance-criteria grep pattern"

requirements-completed: [SOCK-01, SOCK-02, SOCK-03]

coverage:
  - id: D1
    description: "serve()'s per-connection body moved into module-level _handle_conn(mon, conn); serve() spawns threading.Thread(target=_handle_conn, daemon=True) per accepted connection instead of handling inline"
    requirement: SOCK-02
    verification:
      - kind: unit
        ref: "python3 -m py_compile claude-monitor.py && python3 claude-monitor.py --selfcheck && ruff check claude-monitor.py"
        status: pass
      - kind: other
        ref: "grep -c 'def _handle_conn' == 1; grep -c 'threading.Thread(target=_handle_conn' == 1; grep -c 'conn, _ = srv.accept()' == 1"
        status: pass
    human_judgment: true
  - id: D2
    description: "{\"query\": \"snapshot\"} dispatch branch builds sessions/usage/trends under mon.sessions_lock and replies with one JSON line on the same connection before close; unrecognized query values silently skipped"
    requirement: SOCK-01
    verification:
      - kind: unit
        ref: "python3 -m py_compile claude-monitor.py && python3 claude-monitor.py --selfcheck && ruff check claude-monitor.py"
        status: pass
      - kind: other
        ref: "grep -c 'if \"query\" in msg:' == 1; grep -c 'with mon.sessions_lock:' == 1; grep -c 'core.build_session_snapshot' == 2; grep -c 'os.chmod(SOCK' == 1"
        status: pass
    human_judgment: true
  - id: D3
    description: "Query snapshot build (list(mon.sessions.values()) + build_session_snapshot) runs entirely inside mon.sessions_lock, matching Plan 08-01's lock discipline, so no torn/partial read is possible against a concurrent Gtk-thread mutation"
    requirement: SOCK-03
    verification:
      - kind: unit
        ref: "Structural: with mon.sessions_lock: wraps the exact list(mon.sessions.values()) copy + build_session_snapshot() call as one atomic unit; matches 08-01's established pattern"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-07-20
status: complete
---

# Phase 8 Plan 02: Daemon Socket Query Verb Summary

**Thread-per-connection serve() plus a `{"query": "snapshot"}` socket verb answering sessions/usage/trends under the shared sessions_lock, with the socket file hardened to 0600**

## Performance

- **Duration:** ~5 min
- **Completed:** 2026-07-20
- **Tasks:** 2 completed
- **Files modified:** 1

## Accomplishments

- `_handle_conn(mon, conn)` -- new module-level thread-target function containing the full recv/dispatch/send body that `serve()`'s accept loop used to run inline; `conn.close()` now wraps the whole body in one `finally` (moved from wrapping just `recv()`), so a query response can be sent before the connection closes (D-05).
- `serve()`'s accept loop now spawns `threading.Thread(target=_handle_conn, args=(mon, conn), daemon=True).start()` per accepted connection instead of handling it inline -- a stalled or malformed connection now only ever blocks its own thread (D-02/D-03, SOCK-02). No `conn.settimeout()` added, per the plan's explicit instruction: thread isolation is the fix, not a bounded timeout.
- `if "query" in msg:` dispatch branch added before the existing hook-event check. For `msg.get("query") == "snapshot"`: builds `sessions = core.build_session_snapshot(list(mon.sessions.values()))` inside `with mon.sessions_lock:` (SOCK-03), then constructs `{"sessions": sessions, "usage": mon.usage, "trends": mon.trends}` outside the lock (single-reference rebinds), and sends it as one JSON line via `conn.sendall(...)`. Any other query value is silently skipped (matches the malformed-hook-event precedent); either way the line loop `continue`s so a query is never also treated as a hook event.
- `os.chmod(SOCK, 0o600)` added immediately after `srv.bind(SOCK)` in `serve()` (T-08-04): the socket now answers reads (session dirs, usage%), not just accepts fire-and-forget writes, so it is restricted to the owning user regardless of the parent directory's mode (relevant to the `/tmp` fallback when `XDG_RUNTIME_DIR` is unset).

## Task Commits

Each task was committed atomically:

1. **Task 1: serve() -- thread-per-connection refactor (D-02/D-03)** - `970b6f3` (feat)
2. **Task 2: query dispatch (D-04/D-05/D-06) + socket hardening** - `8d05332` (feat)

## Files Created/Modified
- `claude-monitor.py` - added `_handle_conn(mon, conn)`, converted `serve()`'s accept loop to thread-per-connection, added the `"query": "snapshot"` dispatch branch, added `os.chmod(SOCK, 0o600)` after bind.

## Decisions Made
- Split what the plan wrote as one logical diff (Task 1's refactor and Task 2's additions land in the same function body) into two truly atomic commits: wrote the full combined edit first while implementing, then temporarily stripped Task 2's query branch and chmod line back out, verified Task 1's acceptance criteria in isolation, committed, then re-added Task 2's lines, verified again, and committed separately. This preserves the plan's one-commit-per-task contract without re-deriving the code twice.
- Reformatted the `core.build_session_snapshot(...)` call from an initially-written 3-line wrap onto a single line, matching the plan's exact acceptance-criteria regex (`core.build_session_snapshot\(list\(mon.sessions.values\(\)\)\)`), which requires the full call on one line.

## Deviations from Plan

None beyond the two items above (both routine execution/formatting adjustments, no scope or behavior change; not tracked as Rule 1-4 deviations since neither fixed a bug or added functionality -- they were needed purely to satisfy the plan's own literal acceptance-criteria grep patterns and its atomic-commit contract).

## Verification Status

**Automated (all pass):**
- `python3 -m py_compile claude-monitor.py` -- succeeds
- `python3 claude-monitor.py --selfcheck` -- exits 0
- `ruff check claude-monitor.py` -- clean
- All structural `grep -c` / `rg -q` acceptance criteria from both tasks -- pass (see `coverage` above)

**Human UAT -- NOT RUN, deferred:**
This subagent session has no GUI/DISPLAY session available, so Task 2's `<human-check>` live-tray verification (restart the tray via `just restart`, open a stalled connection, send a concurrent hook event and confirm it reaches the tray menu un-delayed, then query the socket and confirm a prompt `sessions`/`usage`/`trends` response) was **not performed**. This is explicitly deferred to the user for manual confirmation after this plan completes -- it is not silently claimed as passed. To verify:
1. `just restart`
2. In a second terminal: `python3 -c "import socket,os,time; s=socket.socket(socket.AF_UNIX); s.connect(os.path.join(os.environ.get('XDG_RUNTIME_DIR','/tmp'),'claude-monitor.sock')); time.sleep(10)" &`
3. While that's running, send a hook event and confirm it appears in the tray menu within ~1s, not delayed behind the stalled connection.
4. Query the socket with `{"query": "snapshot"}` and confirm a prompt response containing `sessions`/`usage`/`trends` keys.

## Issues Encountered
None.

## User Setup Required
None -- no external service configuration required. Human UAT above is the only outstanding manual step.

## Next Phase Readiness
- Phase 9 (Terminal Dashboard / TUI) now has a working query verb (`{"query": "snapshot"}` over the existing unix socket) returning the live sessions/usage/trends payload it needs, with thread-per-connection isolation guaranteeing a slow/misbehaving TUI client cannot stall hook-event delivery to the tray.
- The live human-check deferred above should be run once before Phase 9 begins consuming the socket in anger, to catch anything the automated checks can't (actual concurrent-connection behavior, actual socket permissions in the deployed environment).

---
*Phase: 08-daemon-socket-query-verb*
*Completed: 2026-07-20*

## Self-Check: PASSED
