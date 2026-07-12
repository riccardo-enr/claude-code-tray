---
status: complete
phase: 03-usage-trends-in-the-tray
source: [03-VERIFICATION.md]
started: 2026-07-12T11:32:10Z
updated: 2026-07-12T11:48:41Z
---

## Current Test

[testing complete]

## Tests

### 1. Empty-state row before enough history exists
expected: Run the tray with < ~1h of history and open the menu. A single insensitive `trends: collecting history...` row shows under a separator; sessions, click-to-focus, and usage rows keep working.
result: skipped
reason: Not reproducible during this session — usage-history.jsonl already spans ~1.6h (>1h threshold), so the tray renders populated rows instead of the empty state. Would require clearing history to observe. Empty-state logic statically verified in 03-VERIFICATION.md (compute_trends sets self.trends=None below TREND_MIN_SPAN; trend_rows returns the collecting row).

### 2. Three trend rows render after ~1h of history (TREND-01/02/03)
expected: Collecting row swaps to three insensitive rows — bare block sparkline, `today <rate>/hr | wk <rate>/hr`, `peak hour: HH:00 (<rate>/hr)` — under a separator, below the usage rows.
result: pass
note: User confirmed via screenshot after restarting the tray on the new code (PID 1781808). All three rendered — sparkline (sparse, ~2 filled columns for ~1.6h of data, gaps elsewhere, as designed), `today 19.7M/hr | wk 19.7M/hr`, `peak hour: 13:00 (20.6M/hr)`. TREND-02 mean consistent with the v1.0 burn row (x60 conversion correct). Menu order correct: sessions, usage rows, separator, trend rows, Quit.

### 3. OSError / degradation posture (HIST-03)
expected: Point history at an unwritable/missing path and run the tray — it keeps running, trends fall back to collecting/last-known, no crash or frozen menu.
result: skipped
reason: Destructive to exercise live; the OSError-degradation path was verified statically in 03-VERIFICATION.md (all history reads route through parse_history inside compute_trends on the poll thread, wrapped in `except OSError`; no history I/O on the Gtk main thread). Not manually exercised.

## Summary

total: 3
passed: 1
issues: 0
pending: 0
skipped: 2
blocked: 0

## Gaps

[none]
