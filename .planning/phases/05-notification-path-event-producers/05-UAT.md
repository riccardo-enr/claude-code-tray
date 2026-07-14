# Phase 05 UAT — Notification Path & Event Producers

**Date:** 2026-07-14
**Verified against:** `86164c3` (clean tree; the local tray-ping/mute experiment was stashed
so the phase was tested as specified, not as locally preferred)
**Result:** PASS (5/5 success criteria)

## Success Criteria

| # | Criterion | Method | Result |
|---|-----------|--------|--------|
| 1 | Session `waiting` / `done` raises a desktop notification, once per transition, never per tick | Live: `Stop` hook fired `done` -> banner titled with the project dir. Dedupe half pinned by `sess_should_notify` asserts in `--selfcheck` | PASS (user-confirmed) |
| 2 | Clicking a session notification focuses its tmux pane and raises the terminal window | Live: user clicked the banner | PASS (user-confirmed) |
| 3 | A cap projected to hit 100% before reset alerts once; a cap coasting to reset stays silent | `--selfcheck` asserts on `project()` / `alert_should_fire()`, incl. the coast, already-exhausted (D-07) and lead-time (D-05) cases | PASS |
| 4 | After a window rolls over, that cap can alert again | `--selfcheck` assert: changed `resets_at_epoch` re-arms `alert_armed[cap]` (ALERT-04 / D-06) | PASS |
| 5 | With the notification daemon absent, the tray keeps polling, rendering, and serving session events | `self.notif = None` fallback; every `emit_notif` becomes a no-op (NOTIF-04) | PASS (structural) |

## Notes

- SC5 was verified structurally (the guard exists and every emit path is gated on it), not by
  killing the notification daemon on a live desktop. If that bar matters, the honest test is
  to stop the daemon and confirm the tray still ticks.
- The 7-day block is absent on older CLIs; `project()`'s `_is_num` guard degrades that to
  silence rather than a crash, asserted in `--selfcheck`.

## Follow-ups (not defects — Phase 6 scope)

- Session popups fire on every waiting/done transition regardless of whether the user is
  looking at the pane (D-04, by design). The user wants tray-only pings for session events;
  that is CFG-01/CFG-02 in Phase 6, not a Phase 5 bug.
- A tray-icon attention flip (`IndicatorStatus.ATTENTION`) was prototyped during this phase
  and stashed. Whether GNOME's `ubuntu-appindicators` extension actually renders the
  attention icon is UNVERIFIED — D-Bus reports `NeedsAttention` correctly, but that was
  never confirmed visually. Settle before building on it.
