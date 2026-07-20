---
status: testing
phase: 08-daemon-socket-query-verb
source: [08-VERIFICATION.md]
started: 2026-07-20T11:56:37Z
updated: 2026-07-20T11:56:37Z
---

## Current Test

number: 1
name: Disposition WR-01 -- watch_focus() reads/mutates self.sessions without sessions_lock
expected: |
  A decision recorded (fix / follow-up issue / accepted-risk override) before Phase 9's TUI
  becomes a second concurrent reader of the same daemon.
awaiting: user response

## Tests

### 1. Disposition WR-01 from 08-REVIEW.md
expected: watch_focus() (claude-monitor.py:705-728) reads self.sessions via an unlocked
  list(mon.sessions.values()) and writes s["acked"] = True without mon.sessions_lock, even
  though this phase's own new comment on Monitor.sessions_lock (claude-monitor.py:64) now
  asserts the lock guards "self.sessions: Gtk-thread mutator + query-thread readers" --
  watch_focus is a third, unguarded mutator thread the invariant doesn't actually cover.
  Decide: fix now (small, mechanical), open a tracked follow-up, or explicitly accept as
  pre-existing/out-of-scope.
result: [pending]

### 2. Disposition WR-02 from 08-REVIEW.md
expected: the thread-per-connection refactor (serve()/_handle_conn, claude-monitor.py:573-630)
  drops the old accept-loop's implicit backpressure with no conn.settimeout(...) -- a connection
  that never completes a line now leaks one OS thread indefinitely. This is already the plan's
  own accepted risk (T-08-03, disposition "accept" in 08-02-PLAN.md's threat model) -- confirm
  that acceptance still holds now that the interface answers reads, not just fire-and-forget
  writes, or add the reviewer-suggested conn.settimeout(5).
result: [pending]

### 3. Disposition IN-01/IN-02 from 08-REVIEW.md
expected: (a) no automated test exercises the socket wire protocol itself (_handle_conn/serve/
  query dispatch) -- only the pure build_session_snapshot helper is covered by --selfcheck;
  (b) build_session_snapshot's six-key shape omits `term`, which handle() now stores per-session
  and Monitor.focus()/on_click() use to distinguish a Zed session from a tmux session. Decide:
  add a socket-level integration check and/or add `term` to the snapshot shape now vs. when a
  later feature actually needs it.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
