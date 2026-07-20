---
phase: 06-notification-control-config
plan: 02
subsystem: notification-config
tags: [gtk, tray-menu, checkmenuitem, radiomenuitem, config]
status: complete

requires:
  - phase: 06-notification-control-config (Plan 1)
    provides: "self.config, save_config, DEFAULT_CONFIG, THRESHOLD_CHOICES, NOTIF_KEYS, notif_allowed(kind, config)"
provides:
  - "Monitor.on_notif_toggle(item, key) -- CheckMenuItem toggled handler for mute_all + 4 event keys"
  - "Monitor.on_threshold_toggle(item, val) -- RadioMenuItem toggled handler, ignores losing-active fire"
  - "Monitor.notif_submenu() -- Notifications submenu (mute-all + 4 event checkboxes + nested Badge threshold radios)"
  - "Notifications menu item wired into rebuild_menu after the dashboard item"
affects: []

tech-stack:
  added: []
  patterns:
    - "GTK CheckMenuItem/RadioMenuItem set_active() before connect('toggled', ...) to avoid a spurious save+rebuild on initial state sync"
    - "Toggle handlers follow the existing mutate-config -> save_config -> rebuild_menu() sequence already used by apply_usage/handle/on_click"

key-files:
  created: []
  modified:
    - claude-monitor.py

key-decisions:
  - "notif_submenu() built fresh from self.config on every rebuild_menu() call, matching the file's existing full-teardown-and-rebuild idiom -- no incremental widget diffing"
  - "Badge threshold radios iterate THRESHOLD_CHOICES directly (never sorted/reversed) to guarantee the fixed 70/80/90/95 ascending order D-05 requires"

requirements-completed: [CFG-01, CFG-02, CFG-05]

coverage:
  - id: D1
    description: "Notifications submenu: Mute all checkbox + four ordered event checkboxes (waiting, done, 5h, 7d), each independently toggleable, taking effect on the very next event with no restart"
    requirement: "CFG-01"
    verification:
      - kind: unit
        ref: "python3 claude-monitor.py --selfcheck (notif_allowed gate assertions, unchanged from Plan 1)"
        status: pass
      - kind: other
        ref: "AST signature/ordering checks: on_notif_toggle(self,item,key), notif_submenu(self), fixed key order waiting/done/5h/7d"
        status: pass
    human_judgment: true
    rationale: "Live GTK tray interaction (checkbox toggling taking effect on the next real event with no restart) cannot be exercised headlessly in this environment -- needs a human to open the tray menu."
  - id: D2
    description: "Mute all silences every notification while tray rows, usage rows, and icon badge keep updating; unmuting restores exactly the prior per-event states with no re-sync step"
    requirement: "CFG-02"
    verification:
      - kind: other
        ref: "AST check: on_notif_toggle writes exactly one config[Subscript] assignment (D-04 idempotency probe)"
        status: pass
      - kind: other
        ref: "Byte-identical call-site check: notif_allowed(kind, self.config) and build_label(...) call sites unchanged from Plan 1"
        status: pass
    human_judgment: true
    rationale: "Live UAT (mute suppresses popups while rows/badge keep working, unmute restores prior toggle state) requires human observation of the running tray."
  - id: D3
    description: "Badge threshold chosen from four fixed presets (70/80/90/95) via radio items, never free text; selection persists and the badge follows it"
    requirement: "CFG-05"
    verification:
      - kind: other
        ref: "grep: Gtk.Entry count == 0 (no free-text widget); for val in THRESHOLD_CHOICES present, sorted(THRESHOLD_CHOICES) absent (fixed ascending order)"
        status: pass
      - kind: other
        ref: "AST check: on_threshold_toggle(self,item,val), first statement is the double-fire guard 'if not item.get_active(): return'"
        status: pass
    human_judgment: true
    rationale: "Confirming the badge glyph itself changes on the next poll tick after a threshold pick, and that the pick survives a helper restart, requires a human driving the live tray."

duration: 6min
completed: 2026-07-16
status: complete
---

# Phase 6 Plan 2: Notifications tray menu (mute-all, per-event toggles, badge threshold) Summary

Two `Gtk.CheckMenuItem` groups and a nested `Gtk.RadioMenuItem` group wired into a new
"Notifications" submenu, reading and writing the config layer Plan 1 built -- no new state
management idiom, no free-text widget anywhere.

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-16T12:29:15Z
- **Completed:** 2026-07-16T12:34:25Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- "Notifications" submenu: "Mute all" checkbox, separator, then four ordered event
  checkboxes (Waiting for input, Session finished, 5-hour quota alert, 7-day quota alert),
  each bound to its own `self.config` key and independently persisted
- Nested "Badge threshold" submenu inside "Notifications": four `Gtk.RadioMenuItem` presets
  (70%/80%/90%/95%) iterated directly from `THRESHOLD_CHOICES` in fixed ascending order,
  radio-exclusive, defaulting to the persisted `usage_threshold`
- Both submenus wired into `rebuild_menu` immediately after the dashboard item, rebuilt
  fresh from `self.config` on every call

## Task Commits

Each task was committed atomically:

1. **Task 1: Notifications submenu -- mute-all + the four event checkboxes** - `dd3ead2` (feat)
2. **Task 2: Nested "Badge threshold" radio submenu** - `4833ba6` (feat)

## Files Created/Modified
- `claude-monitor.py` - Added `Monitor.on_notif_toggle`, `Monitor.on_threshold_toggle`,
  `Monitor.notif_submenu`; wired a new "Notifications" `Gtk.MenuItem` into `rebuild_menu`

## Decisions Made
None - followed plan as specified.

## Deviations from Plan

None - plan executed exactly as written. `on_threshold_toggle` was written without a
docstring (a one-line comment above the guard instead) to satisfy the plan's own acceptance
criterion that `f.body[0]` is the `ast.If` guard node -- a leading docstring would have made
the guard `body[1]` instead. This is a literal-compliance detail, not a deviation from the
plan's intent.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 6 is now complete (both plans executed): the config data layer (Plan 1) and the tray
menu surface (Plan 2) together close CFG-01, CFG-02, CFG-05. `--selfcheck` exits 0. Live
tray UAT (D1/D2/D3 above) is the remaining human-judgment step to close out the phase's
Success Criteria 1, 2, and 5 end-to-end.

---
*Phase: 06-notification-control-config*
*Completed: 2026-07-16*

## Self-Check: PASSED

- FOUND: `claude-monitor.py`
- FOUND: commit `dd3ead2` (Task 1) in `git log --oneline --all`
- FOUND: commit `4833ba6` (Task 2) in `git log --oneline --all`
