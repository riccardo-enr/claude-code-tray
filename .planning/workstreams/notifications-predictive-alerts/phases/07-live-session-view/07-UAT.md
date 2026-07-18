---
status: diagnosed
phase: 07-live-session-view
source: [07-VERIFICATION.md]
started: 2026-07-18T18:05:00.000Z
updated: 2026-07-18T18:20:00.000Z
---

## Current Test

[testing complete]

## Tests

### 1. Duration counter resets only on real status transition (D-01)
expected: |
  Start a live session so it shows "waiting" in the dashboard panel; trigger another
  "waiting" event for the same session (e.g. a keepalive) and confirm the duration
  counter keeps counting rather than resetting to 0. Then cause the status to actually
  change (e.g. to "running") and confirm the counter DOES reset.
  Expected: counter is monotonic across same-status repeats; resets to 0 only on a
  genuine transition.
result: pass

### 2. Sessions sort waiting -> running -> done, done rows dimmed (D-04/D-06)
expected: |
  Open the dashboard with sessions in all three statuses simultaneously; visually
  confirm row order is waiting, then running, then done, and that done rows appear
  dimmed (reduced opacity).
result: issue
reported: "Now I have two running session when I know one is done. Also the progress is still increasing when waiting dude."
severity: major

### 3. Duration counter visibly ticks every second (D-02)
expected: |
  Watch the Duration column of an active session row for 5-10 seconds without
  reloading the page. Seconds should visibly increment once per second.
result: pass
note: "Ticking confirmed (increases once per second). User again noted the stuck-running status bug -- same root cause as G-07-2, not a new gap."

## Summary

total: 3
passed: 2
issues: 1
pending: 0
skipped: 0

## Gaps

- gap_id: G-07-2
  truth: "Sessions sort waiting -> running -> done, done rows dimmed (D-04/D-06)"
  status: failed
  reason: "User reported: Now I have two running session when I know one is done. Also the progress is still increasing when waiting dude."
  severity: major
  test: 2
  root_cause: "self.sessions has no liveness/expiry mechanism. The only removal path is the 'end' socket event fired by Claude Code's SessionEnd hook, which is upstream-unreliable: it does not fire on /exit (anthropics/claude-code#17885) or /clear (anthropics/claude-code#6428), and cannot fire when the pane/process is killed externally. When 'end' never arrives, the session entry freezes at whatever status it last received (running/waiting/done) and write_dashboard() snapshots it verbatim forever, while the client-side ticker keeps counting duration up with no liveness signal. Broader than 07-REVIEW.md's WR-03 (which only considered stale 'done' rows) -- the frozen status can be any of the three depending on when the hook chain was interrupted."
  artifacts:
    - path: "claude-monitor.py"
      issue: "Monitor.handle()/Monitor.write_dashboard(): no TTL, no last-seen expiry, no pid/pane liveness check on self.sessions entries"
    - path: "claude_monitor/dashboard.py"
      issue: "sessDur()/renderSessions(): unbounded now-entered ticker with no liveness signal"
  missing:
    - "A local staleness/liveness safeguard that doesn't depend on SessionEnd firing"
    - "e.g. a max-age reap on self.sessions entries, and/or a tmux pane-liveness check (reusing the existing pane_onscreen-style query) to detect a session whose pane no longer exists and treat it as ended locally"
  debug_session: .planning/debug/stale-session-status-stuck.md
