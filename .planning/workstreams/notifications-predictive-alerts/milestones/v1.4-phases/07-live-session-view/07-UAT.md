---
status: complete
phase: 07-live-session-view
source: [07-VERIFICATION.md]
started: 2026-07-18T21:35:00.000Z
updated: 2026-07-18T22:10:00.000Z
---

## Current Test

[testing complete]

## Tests

### 1. Killed-pane self-heal + live CR-01 confirmation (no spurious re-notify)
expected: |
  Restart the tray (`just restart`). Start a session in a tmux pane, confirm it
  shows in tray + dashboard. Run `tmux kill-pane -t <pane>` directly (bypassing
  SessionEnd) and confirm the session disappears from BOTH the tray menu and the
  dashboard panel within ~1 poll tick (~15s), no manual tray refresh (dashboard
  uses its existing meta-refresh/reload). Separately confirm a genuinely active
  session (pane alive, real events arriving) is never wrongly reaped -- and when a
  reaped-then-alive session resends its SAME status, NO new "Waiting for input"
  popup fires and the `!` badge does not re-arm (the live CR-01 confirmation). A
  genuine-change resurrection (e.g. waiting -> done across a reap) should show
  exactly one notification.
result: pass
note: "07-02 D3 + 07-03 D5. Deterministic proof already passes via --selfcheck (session_stale + sess_notify_baseline blocks); this is the live GTK-tray + real-tmux end-to-end confirmation."

### 2. Sessions sort waiting -> running -> done, done rows dimmed (D-04/D-06) -- clean re-run
expected: |
  Open the dashboard with sessions in all three statuses simultaneously (now that
  G-07-2 no longer produces stuck/duplicate rows and CR-01 no longer re-fires
  notifications). Visually confirm row order is waiting, then running, then done,
  and that done rows render visibly dimmed (.sess-done{opacity:.5}). This separates
  "sort/dim logic is correct" from "the stale-session bug was masking it" -- the
  only prior attempt (07-UAT.md Test 2, now superseded) returned "issue" purely
  because of the since-fixed G-07-2 stale rows.
result: pass

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
