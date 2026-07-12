---
status: testing
phase: 03-usage-trends-in-the-tray
source: [03-VERIFICATION.md]
started: 2026-07-12T11:32:10Z
updated: 2026-07-12T11:32:10Z
---

## Current Test

number: 1
name: Empty-state row before enough history exists
expected: |
  With less than ~1h of history, opening the tray menu shows a single insensitive
  "trends: collecting history..." row under a separator (below the usage rows).
  Sessions, click-to-focus, and the usage rows all keep working.
awaiting: user response

## Tests

### 1. Empty-state row before enough history exists
expected: Run the tray (python3 claude-monitor.py) with < ~1h of history and open the menu. A single insensitive `trends: collecting history...` row shows under a separator; sessions, click-to-focus, and usage rows keep working. No half-empty sparkline, no partial numbers.
result: [pending]

### 2. Three trend rows render after ~1h of history (TREND-01/02/03)
expected: Let the tray accumulate > ~1h of history spanning multiple hours, then open the menu. The collecting row swaps to three insensitive rows in this order — bare 24-char block sparkline (no label, visible gaps for empty hours), `today <rate>/hr | wk <rate>/hr`, `peak hour: HH:00 (<rate>/hr)`. Overall menu order: sessions, usage rows, SEPARATOR, trend rows, SEPARATOR, Quit.
result: [pending]

### 3. OSError / degradation posture (HIST-03)
expected: Point the history at an unwritable or missing path and run the tray. The tray keeps running; trends fall back to the collecting/last-known state; no crash and no frozen menu. Session status and usage rows keep working.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
