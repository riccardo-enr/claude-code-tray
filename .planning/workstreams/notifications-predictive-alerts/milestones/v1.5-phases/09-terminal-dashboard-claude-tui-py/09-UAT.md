---
status: passed
phase: 09-terminal-dashboard-claude-tui-py
source:
  - 09-01-SUMMARY.md
  - 09-02-SUMMARY.md
started: 2026-07-24T00:00:00Z
updated: 2026-07-24T00:00:00Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

number: -
name: -
expected: |
  All tests complete.
awaiting: none -- session complete

## Tests

### 1. Launch the TUI
expected: `just tui` opens a full-screen terminal app with three panels (usage 5h/7d, trends, sessions), live data, no traceback.
result: pass

### 2. Usage numbers match the tray menu
expected: The 5h and 7d rows (percent, tokens, reset countdown, burn rate) match what the GNOME tray menu shows for the same moment.
result: pass

### 3. Sessions table scroll stays put (CR-01 fix)
expected: With more sessions than fit on screen, scroll down inside the sessions table. The view stays where you put it -- it does NOT snap back to the top every second when the display refreshes. (Skip if you have too few sessions to scroll.)
result: skipped
reason: Only 3-4 concurrent sessions during UAT -- table never overflowed, so scroll could not be exercised. CR-01 fix (scroll_y preserved across the 1s render tick) lives in claude-tui.py, outside --selfcheck's textual-free boundary; verified by code re-read only. Re-check with a tall session list.

### 4. Daemon outage dims, then recovers (D5 + WR-03 fix)
expected: While the TUI is running, restart the daemon (`just restart` in another terminal). The panels dim and the header honestly reads "daemon unreachable -- last update HH:MM:SS" (NOT "render error", NOT a crash/exit). When the daemon is back, it returns to a "live" header with fresh data on its own.
result: skipped
reason: User opted not to restart the live daemon during UAT. D5 outage/recovery path and WR-03 error-routing fix ("daemon unreachable" not "render error") remain verified by headless run_test + code re-read only, not by a live outage.

### 5. Quit with q
expected: Pressing `q` exits cleanly back to the shell. No other key triggers a manual refresh (refresh is automatic).
result: pass

## Summary

total: 5
passed: 3
issues: 0
pending: 0
skipped: 2

## Gaps

No functional gaps -- zero issues found across executed tests. Two tests were
skipped for lack of a live reproduction opportunity, not failures:

- Test 3 (CR-01 scroll retention): never had enough concurrent sessions to
  overflow the table. Fix verified by code re-read only (lives in claude-tui.py,
  outside --selfcheck's textual-free boundary).
- Test 4 (D5 outage/recovery + WR-03 error routing): user opted not to restart
  the live daemon. Verified by headless run_test + code re-read only.

Both residuals are low-risk and re-checkable ad hoc; neither blocks the phase.

## Auto-covered (not presented -- passing tests)

- 09-01 D1-D6: socket client, usage rows, trend text, session rows, timing-constant guard, textual-free `--selfcheck` boundary -- all unit/integration pass.
- 09-02 D3 (session ordering), D6 (markup-hostile dir names render literally / CR-02), D7 (`./claude-tui.py` self-resolves textual from foreign cwd), D8 (no half-applied frame) -- headless run_test + static checks pass.
