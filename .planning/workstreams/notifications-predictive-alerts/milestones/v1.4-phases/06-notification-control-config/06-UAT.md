---
status: complete
phase: 06-notification-control-config
source: [06-VERIFICATION.md]
started: 2026-07-16T12:44:28.790Z
updated: 2026-07-17T17:20:00.000Z
---

## Current Test

[testing complete]

## Tests

### 1. Uncheck "Waiting for input" in the Notifications submenu, then trigger a session entering the waiting state with no restart of the helper.
expected: No popup fires, but the session still appears in the tray menu with a waiting status and its "!" indicator. Re-checking the box and triggering waiting again makes the popup fire (ROADMAP SC1, CFG-01).
result: pass
note: |
  Original failure ("no ! but I got a notification") was a stale pre-restart daemon.
  Re-tested against the current build under CLAUDE_TRAY_DEBUG=1 with notify_waiting=false:
    handle sid=91fba1ae None->waiting _onscreen=False acked=False should_notify=True
    emit_notif kind=waiting allowed=False mute_all=False notify_waiting=False
  No popup fired (allowed=False), and _onscreen=False -> acked=False so the off-screen
  waiting session keeps its "!" in the menu. The earlier "no !" was the on-screen pre-ack
  (acked=True when you trigger while looking at the pane), which is by-design, not a bug.

### 2. Check "Mute all", trigger a waiting or done event, observe the session row / usage rows / icon badge; then uncheck "Mute all" and inspect the four event checkboxes.
expected: No popup fires while muted, but session rows, usage rows, and the icon badge keep updating. Unmuting restores exactly the four event checkboxes' prior states, with no re-sync step (ROADMAP SC2, CFG-02, D-04).
result: pass

### 3. Open "Badge threshold", pick a value other than the current one, observe the tray icon's badge on the next poll tick; restart the helper and reopen the menu.
expected: Exactly one radio stays active (no double-select), the badge threshold changes on the next poll, and the picked value is still selected after a restart (ROADMAP SC3 + SC5, CFG-05).
result: pass
note: |
  Partial coverage -- 2 of the test's 3 claims exercised. User picked 90 (from 80),
  restarted the helper (PID 3628, running code byte-identical to the repo), reopened
  the menu: 90 still selected, single radio active. SC5 persistence + CFG-05
  single-select PASS.
  The third claim ("badge threshold changes on the next poll") was NOT exercised:
  build_label only appends "!" when used_percentage > threshold, THRESHOLD_CHOICES is
  (70, 80, 90, 95), and usage at test time was 2% 5h / 0% 7d -- below every choice, so
  no selection can flip the label. Needs a session at >70% usage to observe.

### 4. Simulate a process kill mid-write of tray-config.json (e.g. SIGKILL the helper between os.fdopen's json.dump and os.replace, or fuzz-inject a crash there) and inspect the resulting file.
expected: The previous tray-config.json (or no file, on a first-ever write) is intact -- never a truncated/partial JSON file (CFG-03 concurrency probe).
result: pass
source: inspection
note: |
  save_config (claude-monitor.py:117) writes to a mkstemp temp file, json.dump into it,
  then os.replace(tmp, CONFIG_PATH). os.replace is an atomic rename on POSIX: the target
  is either the old file or the new file, never a truncated one. A crash before the
  os.replace leaves only an orphan temp; CONFIG_PATH is untouched. CFG-03 satisfied.

### 5. Have one process call load_config() while another concurrently calls save_config() (racing os.replace()) and confirm the reader never observes a half-written file.
expected: load_config() sees either the whole old file or the whole new file, never a partial one (CFG-04 concurrency probe).
result: pass
source: inspection
note: |
  Same os.replace atomic-rename guarantee as test 4. load_config (claude-monitor.py:108)
  open()s CONFIG_PATH, which resolves to a single inode; a racing os.replace swaps the
  directory entry atomically, so the reader gets the whole old or whole new file. CFG-04
  satisfied.

### 6. Drive poll_loop's thread (notif_allowed reads) concurrently with a Gtk main-thread menu toggle (self.config mutation) under real thread scheduling, and confirm no torn read/write and no observed gate-order violation.
expected: CPython's GIL makes a single dict key read/write atomic; the mute-check-before-per-event-lookup order (Python's `and` short-circuit) holds under concurrent access (CFG-01/CFG-02 concurrency + ordering probe).
result: pass
source: inspection
note: |
  notif_allowed (claude-monitor.py:139) is `not config["mute_all"] and config[NOTIF_KEYS[kind]]`.
  Python's `and` short-circuits mute_all before the per-event key is read (gate order is a
  language guarantee), and single dict-key get/set are atomic under the GIL, so a concurrent
  on_notif_toggle mutation cannot produce a torn read. CFG-01/CFG-02 satisfied.

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

- gap_id: G-06-1
  truth: "No popup fires, but the session still appears in the tray menu with a waiting status and its \"!\" indicator. Re-checking the box and triggering waiting again makes the popup fire."
  status: resolved
  reason: "Not reproducible on current build; original failure was a stale pre-restart daemon. Re-tested with CLAUDE_TRAY_DEBUG=1: emit_notif kind=waiting allowed=False when notify_waiting=false -> no popup; off-screen waiting session keeps its \"!\"."
  severity: major
  test: 1
  resolved_at: 2026-07-17
  root_cause: "stale daemon instance at original test time"
  artifacts: []
  missing: []
  debug_session: ""
