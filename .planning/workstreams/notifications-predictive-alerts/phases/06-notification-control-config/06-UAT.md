---
status: testing
phase: 06-notification-control-config
source: [06-VERIFICATION.md]
started: 2026-07-16T12:44:28.790Z
updated: 2026-07-16T12:44:28.790Z
---

## Current Test

number: 1
name: Uncheck "Waiting for input" in the Notifications submenu, then trigger a session entering the waiting state with no restart of the helper.
expected: |
  No popup fires, but the session still appears in the tray menu with a waiting status and its "!" indicator. Re-checking the box and triggering waiting again makes the popup fire (ROADMAP SC1, CFG-01).
awaiting: user response

## Tests

### 1. Uncheck "Waiting for input" in the Notifications submenu, then trigger a session entering the waiting state with no restart of the helper.
expected: No popup fires, but the session still appears in the tray menu with a waiting status and its "!" indicator. Re-checking the box and triggering waiting again makes the popup fire (ROADMAP SC1, CFG-01).
result: [pending]

### 2. Check "Mute all", trigger a waiting or done event, observe the session row / usage rows / icon badge; then uncheck "Mute all" and inspect the four event checkboxes.
expected: No popup fires while muted, but session rows, usage rows, and the icon badge keep updating. Unmuting restores exactly the four event checkboxes' prior states, with no re-sync step (ROADMAP SC2, CFG-02, D-04).
result: [pending]

### 3. Open "Badge threshold", pick a value other than the current one, observe the tray icon's badge on the next poll tick; restart the helper and reopen the menu.
expected: Exactly one radio stays active (no double-select), the badge threshold changes on the next poll, and the picked value is still selected after a restart (ROADMAP SC3 + SC5, CFG-05).
result: [pending]

### 4. Simulate a process kill mid-write of tray-config.json (e.g. SIGKILL the helper between os.fdopen's json.dump and os.replace, or fuzz-inject a crash there) and inspect the resulting file.
expected: The previous tray-config.json (or no file, on a first-ever write) is intact -- never a truncated/partial JSON file (CFG-03 concurrency probe).
result: [pending]

### 5. Have one process call load_config() while another concurrently calls save_config() (racing os.replace()) and confirm the reader never observes a half-written file.
expected: load_config() sees either the whole old file or the whole new file, never a partial one (CFG-04 concurrency probe).
result: [pending]

### 6. Drive poll_loop's thread (notif_allowed reads) concurrently with a Gtk main-thread menu toggle (self.config mutation) under real thread scheduling, and confirm no torn read/write and no observed gate-order violation.
expected: CPython's GIL makes a single dict key read/write atomic; the mute-check-before-per-event-lookup order (Python's `and` short-circuit) holds under concurrent access (CFG-01/CFG-02 concurrency + ordering probe).
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
