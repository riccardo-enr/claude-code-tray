---
phase: 08-daemon-socket-query-verb
verified: 2026-07-20T11:56:37Z
status: passed
score: 10/10 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:

  - test: "Disposition WR-01 from 08-REVIEW.md: watch_focus() (claude-monitor.py:705-728) reads self.sessions via an unlocked `list(mon.sessions.values())` and writes `s[\"acked\"] = True` without `mon.sessions_lock`, even though this phase's own new comment on Monitor.sessions_lock (claude-monitor.py:64) now asserts the lock guards 'self.sessions: Gtk-thread mutator + query-thread readers' -- watch_focus is a third, unguarded mutator thread the invariant doesn't actually cover. Decide: fix now (small, mechanical -- reviewer supplied the diff), open a tracked follow-up, or explicitly accept as pre-existing/out-of-scope."
    expected: "A decision recorded (fix / follow-up issue / accepted-risk override) before Phase 9's TUI becomes a second concurrent reader of the same daemon."
    why_human: "Not a failure of any must-have truth or ROADMAP success criterion as literally scoped (all reference the Gtk-thread mutator specifically, which watch_focus is not) -- this is a judgment call about whether the phase's own broader invariant claim should be closed now or tracked."

  - test: "Disposition WR-02 from 08-REVIEW.md: the thread-per-connection refactor (serve()/_handle_conn, claude-monitor.py:573-630) drops the old accept-loop's implicit backpressure with no conn.settimeout(...) -- a connection that never completes a line now leaks one OS thread indefinitely instead of just stalling the single old handler."
    expected: "A decision recorded: this is already the plan's own accepted risk (T-08-03, disposition 'accept', in 08-02-PLAN.md's threat model) -- confirm that acceptance still holds now that the interface answers reads, not just fire-and-forget writes, or add the reviewer-suggested conn.settimeout(5)."
    why_human: "T-08-03 was pre-accepted in the plan's own threat model before code review re-surfaced it with more detail (unbounded thread leak, not just unbounded thread spawn) -- worth a human confirming the original acceptance still applies."

  - test: "Disposition IN-01/IN-02 from 08-REVIEW.md: (a) no automated test exercises the socket wire protocol itself (_handle_conn/serve/query dispatch) -- only the pure build_session_snapshot helper is covered by --selfcheck; (b) build_session_snapshot's six-key shape omits `term`, which handle() now stores per-session and Monitor.focus()/on_click() use to distinguish a Zed session from a tmux session."
    expected: "A decision: add a socket-level integration check (can live outside --selfcheck), and/or add `term` to the snapshot shape now vs. when Phase 9 (or a later click-to-focus feature, currently deferred per REQUIREMENTS.md) actually needs it."
    why_human: "Both are INFO-level, non-blocking per the code review itself, but undispositioned -- surfacing them once here so they don't silently rot."
---

# Phase 08: Daemon Socket Query Verb Verification Report

**Phase Goal:** The daemon's existing unix socket can answer a read-only query for the live session table plus the latest usage/history state, without disrupting or blocking the existing fire-and-forget hook-event path.
**Verified:** 2026-07-20T11:56:37Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria — authoritative contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Connecting with a query message returns a JSON snapshot of every tracked session (dir/status/pane/tmux) plus the last polled usage/history state | VERIFIED | Code: `claude-monitor.py:590-601` (`if "query" in msg:` -> `snapshot = {"sessions": sessions, "usage": mon.usage, "trends": mon.trends}` -> `conn.sendall`). **Live test** (daemon restarted via `just restart`, real socket at `/run/user/1000/claude-monitor.sock`): sent `{"query":"snapshot"}`, got back `{'sessions': [...], 'trends': ..., 'usage': ...}` with a live test session (`sock-verify-test`) correctly present with `dir/status/entered/frozen/pane/tmux` keys. |
| 2 | Hook events (running/waiting/done/end) continue unchanged and un-slowed while query connections are made, including a stalled or malformed one | VERIFIED | Code: `serve()` now spawns `threading.Thread(target=_handle_conn, ...)` per accepted connection (`claude-monitor.py:630`); no shared blocking state between connections. **Live test:** opened a connection that connects and never sends (held 6-8s), then concurrently sent a real hook event over a second connection (`0.057s` round-trip) and it was visible in a concurrent query response while the stalled connection was still open. |
| 3 | A malformed or slow query connection cannot block or corrupt a concurrent session-event write | VERIFIED | Same thread-per-connection isolation as above (Code + Live). **Live test:** sent a non-JSON line (`"not json at all"`) and an unrecognized query value (`{"query":"bogus"}`) over separate connections — daemon did not crash, stayed responsive, and a subsequent snapshot query still returned correct `sessions/usage/trends` keys. |
| 4 | The session snapshot never reflects a torn/partial in-flight mutation of `self.sessions` — a read racing a Gtk-thread update returns before- or after-state, never mixed | VERIFIED | `handle()`'s full setdefault/baseline-read/update/entered-stamp block (`claude-monitor.py:422-452`) and `_pop_stale()`'s loop (`:492-501`) — the only two Gtk-thread mutators — are wrapped in the SAME `self.sessions_lock` object the query responder acquires (`claude-monitor.py:592`) around its `list(mon.sessions.values())` copy + `build_session_snapshot()` call. Python's `threading.Lock` gives a deterministic (not probabilistic) mutual-exclusion guarantee, so no interleaving is possible between these specific paths. Independently confirmed by the phase's own code review (08-REVIEW.md): "The `sessions_lock` critical sections in `handle`, `reap_stale`/`_pop_stale`, `write_dashboard`, and the new socket query handler are all scoped correctly." No dedicated concurrency stress test exists, but the live smoke test above (concurrent hook event + concurrent query) returned correct, non-corrupted state. |

**Score:** 4/4 ROADMAP success criteria verified.

### Plan-Level Must-Haves (08-01, 08-02 frontmatter)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 5 | `sessions_lock` wraps `handle()`'s end-event pop, `handle()`'s full block, `reap_stale()`'s items() snapshot, `_pop_stale()`'s loop, `write_dashboard()`'s snapshot build (5 named call sites) | VERIFIED | `grep -c "with self.sessions_lock:" claude-monitor.py` == 5, matched at lines 410, 422, 475, 492, 386 — read in place, each wraps exactly the documented scope. |
| 6 | `core.build_session_snapshot(sessions)` returns one plain 6-key dict (dir/status/entered/frozen/pane/tmux) per input, JSON-serializable, no live references | VERIFIED | `claude_monitor/core.py:153-171` — exact shape matches. `python3 -c "from claude_monitor.core import build_session_snapshot..."` per plan's acceptance criteria — passes. |
| 7 | `build_session_snapshot` is pure/idempotent — two calls independent, input never mutated | VERIFIED | `claude_monitor/test_claude_monitor.py:458-476` asserts `is not` identity on repeated calls and re-asserts `_snap_in` unchanged after. `--selfcheck` exits 0. |
| 8 | `write_dashboard()` uses the shared helper inside the lock; dashboard payload shape unchanged for existing consumers | VERIFIED | `claude-monitor.py:386-388` — `with self.sessions_lock: sessions = core.build_session_snapshot(...)`; dir/status/entered/frozen subset preserved (superset with pane/tmux). |
| 9 | Query responder is side-effect-free — never mutates `self.sessions`/`usage`/`trends`, never calls `emit_notif` or touches `alert_armed`/`notif_slots` | VERIFIED | `claude-monitor.py:590-601` — query branch only reads (`build_session_snapshot` is pure, confirmed above) and calls `conn.sendall`; no mutation or notification calls present in the branch. |
| 10 | A malformed query line or unrecognized `query` value is silently skipped, no crash, no cross-connection effect | VERIFIED | Code: `claude-monitor.py:586-589` (`try: json.loads / except: continue`) and `:590-602` (unrecognized `query` value falls through the `if` with no action, then `continue`s). **Live test** confirms no crash and continued correct operation after both a non-JSON line and an unrecognized `query` value. |

**Score:** 10/10 must-haves verified (0 present-but-behavior-unverified — all confirmed via live daemon testing this session, not left to a deferred human-check).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `claude_monitor/core.py: build_session_snapshot` | pure 6-key snapshot function | VERIFIED | Present, matches must-have #6/#7 exactly. |
| `claude_monitor/test_claude_monitor.py` | `--selfcheck` asserts for shape/frozen/empty/JSON/purity | VERIFIED | Lines 458-476; `--selfcheck` exits 0. |
| `claude-monitor.py: Monitor.sessions_lock` | `threading.Lock()` instance attr | VERIFIED | Line 64. |
| `claude-monitor.py: handle/reap_stale/_pop_stale/write_dashboard` locked | 5 `with self.sessions_lock:` blocks | VERIFIED | Confirmed by grep + read. |
| `claude-monitor.py: _handle_conn(mon, conn)` | module-level thread-target | VERIFIED | Lines 573-612. |
| `claude-monitor.py: serve()` thread-per-connection | `threading.Thread(target=_handle_conn, ...)` per accept | VERIFIED | Line 630. |
| `claude-monitor.py: query dispatch branch` | `if "query" in msg:` before event check | VERIFIED | Line 590. |
| `claude-monitor.py: os.chmod(SOCK, 0o600)` | after `srv.bind(SOCK)` | VERIFIED | Line 624. **Live test:** socket file permission confirmed `600` after `just restart` (was stale `775` from a pre-phase-8 process before the restart). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `write_dashboard()` | `core.build_session_snapshot()` | direct call inside `sessions_lock` | WIRED | `claude-monitor.py:387` |
| `_handle_conn`'s query branch | `core.build_session_snapshot()` | direct call inside `mon.sessions_lock` | WIRED | `claude-monitor.py:593`; `grep -c "core.build_session_snapshot"` == 2 (both call sites) |
| `_handle_conn`'s query branch | `mon.usage` / `mon.trends` | single-reference rebind, read outside the lock | WIRED | `claude-monitor.py:596-600` |
| `serve()` | `_handle_conn` | `threading.Thread(target=_handle_conn, args=(mon, conn), daemon=True).start()` | WIRED | `claude-monitor.py:630` |
| `handle()` / `_pop_stale()` mutations | query responder's read | same `Lock` object (`mon.sessions_lock` is `self.sessions_lock` of the one `Monitor` instance) | WIRED | Confirmed same-instance same-attribute; mutual exclusion holds. |

### Behavioral Spot-Checks / Live Verification

The phase's own `08-02-SUMMARY.md` explicitly deferred the plan's `<human-check>` (live tray restart + concurrency test) because the executing subagent had no GUI/DISPLAY session. This verification session DID have `DISPLAY=:1` and an already-running tray, so the deferred check was run for real rather than left outstanding:

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Restart picks up phase-8 code (socket perms flip from stale `775` to `600`) | `just restart`, then `stat -c '%a' $SOCK` | `775` -> `600` | PASS |
| Query returns `sessions`/`usage`/`trends` with live session data | `{"query": "snapshot"}` over the socket | top-level keys exactly `['sessions','trends','usage']`; test session's `dir/status/entered/frozen/pane/tmux` correct | PASS |
| Stalled connection does not block a concurrent hook event | open a connect-and-never-send connection, then send a real hook event on a second connection | hook event write returned in `0.057s`; event's session appeared in a concurrent query response while stall connection was still open | PASS |
| Stalled connection does not block a concurrent query | same stall connection open, query on a third connection | query latency `0.0s` (rounded) | PASS |
| Malformed / unrecognized query does not crash the daemon | non-JSON line, then `{"query":"bogus"}` | daemon PID unchanged and still alive; subsequent query still correct | PASS |
| `end` event correctly removes a session (cleanup, confirms mutation path still works post-refactor) | sent `{"session_id":"sock-verify-test","event":"end"}`, re-queried | test session no longer present | PASS |

All test traffic (`sock-verify-test`) was cleaned up via an `end` event before concluding; confirmed absent from a final query.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SOCK-01 | 08-01, 08-02 | Read-only query verb returns JSON snapshot of sessions + latest usage/history | SATISFIED | ROADMAP SC1, must-haves #1, #6, #8; live test. |
| SOCK-02 | 08-02 | Query path shares the socket without disrupting the fire-and-forget hook-event path | SATISFIED | ROADMAP SC2/SC3, must-haves #2, #3, #10; live test. |
| SOCK-03 | 08-01, 08-02 | Query responder reads `self.sessions` safely against the Gtk-main-thread mutator | SATISFIED | ROADMAP SC4, must-haves #4, #5, #9; code + independent review concurrence + live smoke test. No orphaned requirements — all three phase-8 IDs (SOCK-01/02/03) appear in REQUIREMENTS.md's Phase 8 traceability row and in both plans' `requirements` frontmatter. |

### Anti-Patterns Found

No debt markers (`TBD`/`FIXME`/`XXX`) in any file touched by this phase. All `ponytail:` comments are the project's sanctioned named-ceiling annotations, not unresolved debt.

**Unresolved code-review findings (08-REVIEW.md, status: `issues_found`, dated same day, no follow-up fix commit in `git log` afterward):**

| File | Line | Finding | Severity | Impact |
|------|------|---------|----------|--------|
| `claude-monitor.py` | 705-728 (`watch_focus`) | WR-01: reads/mutates `self.sessions` without the new `sessions_lock` — a third, unguarded mutator thread the phase's own new lock-guard comment (line 64) doesn't actually cover | Warning | Doesn't corrupt the query verb's own 6-key response (query never reads `acked`, and the query's read IS correctly locked against the two Gtk-thread mutators) — but falsifies the completeness of "every self.sessions call site is now guarded," and can raise a self-caught `RuntimeError` in `watch_focus`'s own iteration (pre-existing race, not introduced by this phase, but not closed by it either). |
| `claude-monitor.py` | 573-630 (`serve`/`_handle_conn`) | WR-02: thread-per-connection drops old implicit backpressure; no `conn.settimeout(...)`, so a connection that never completes a line leaks a thread indefinitely | Warning | Already pre-accepted in 08-02-PLAN.md's own threat model (T-08-03, disposition "accept"), but the review's framing (unbounded *leak*, not just unbounded *spawn*) is more specific than what was originally accepted — worth a human re-confirming. |
| `claude-monitor.py` vs `claude_monitor/test_claude_monitor.py` | n/a | IN-01: no automated test exercises the socket wire protocol (`_handle_conn`/`serve`/query dispatch) — only the pure `build_session_snapshot` helper is in `--selfcheck` | Info | This verification session closed the gap for THIS review cycle via live manual testing, but no regression test exists in-repo to catch a future break. |
| `claude_monitor/core.py:153-171` | n/a | IN-02: `build_session_snapshot`'s shape omits `term`, which `handle()` now stores and `Monitor.focus()`/`on_click()` use to distinguish Zed vs. tmux sessions | Info | Not required by ROADMAP SC1 or current Phase 9 scope (click-to-focus from the TUI is explicitly deferred per REQUIREMENTS.md's "Future Requirements") — noted for whoever picks that up later. |

### Human Verification Required

See the `human_verification` frontmatter block above — three decision points (WR-01, WR-02, IN-01/IN-02 disposition), none of which invalidate a must-have truth or ROADMAP success criterion as literally scoped, but all three are unresolved code-review findings sitting undispositioned in this phase's own `08-REVIEW.md`.

### Gaps Summary

No must-have truth, artifact, or key link failed. All 4 ROADMAP success criteria and all 10 plan-level must-haves are verified — with live daemon testing (not just static grep) covering the query verb, thread isolation, and malformed-input resilience that 08-02-SUMMARY.md had explicitly deferred to a human.

The reason this report is `human_needed` rather than `passed` is entirely the three unresolved code-review disposition items above. None of them contradict this phase's stated goal or ROADMAP contract, but WR-01 in particular directly undercuts the completeness of the sessions-locking invariant this phase set out to establish ("guards self.sessions: Gtk-thread mutator + query-thread readers") — a third thread (`watch_focus`) still touches `self.sessions` unguarded. Recommend explicitly deciding fix-now / follow-up-issue / accept-as-is for all three before Phase 9 adds a second live consumer of this same daemon.

---

_Verified: 2026-07-20T11:56:37Z_
_Verifier: Claude (gsd-verifier)_
