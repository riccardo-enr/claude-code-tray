---
status: testing
phase: 07-live-session-view
source: [07-VERIFICATION.md]
started: 2026-07-18T18:05:00.000Z
updated: 2026-07-18T18:05:00.000Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

number: 1
name: Duration counter resets only on real status transition (D-01)
expected: |
  Start a live session so it shows "waiting" in the dashboard panel; trigger another
  "waiting" event for the same session (e.g. a keepalive) and confirm the duration
  counter keeps counting rather than resetting to 0. Then cause the status to actually
  change (e.g. to "running") and confirm the counter DOES reset.
  Expected: counter is monotonic across same-status repeats; resets to 0 only on a
  genuine transition.
awaiting: user response

## Tests

### 1. Duration counter resets only on real status transition (D-01)
expected: |
  Start a live session so it shows "waiting" in the dashboard panel; trigger another
  "waiting" event for the same session (e.g. a keepalive) and confirm the duration
  counter keeps counting rather than resetting to 0. Then cause the status to actually
  change (e.g. to "running") and confirm the counter DOES reset.
  Expected: counter is monotonic across same-status repeats; resets to 0 only on a
  genuine transition.
result: [pending]

### 2. Sessions sort waiting -> running -> done, done rows dimmed (D-04/D-06)
expected: |
  Open the dashboard with sessions in all three statuses simultaneously; visually
  confirm row order is waiting, then running, then done, and that done rows appear
  dimmed (reduced opacity).
result: [pending]

### 3. Duration counter visibly ticks every second (D-02)
expected: |
  Watch the Duration column of an active session row for 5-10 seconds without
  reloading the page. Seconds should visibly increment once per second.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0

## Gaps
