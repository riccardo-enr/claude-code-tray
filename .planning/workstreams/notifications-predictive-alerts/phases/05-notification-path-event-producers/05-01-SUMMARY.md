---
phase: 05-notification-path-event-producers
plan: 01
subsystem: notifications
tags: [dbus, gio, gnome-shell, notifications, threading, hardening]
status: complete

requires: []
provides:
  - "NOTIF_BUS / NOTIF_PATH / URGENCY_NORMAL / URGENCY_CRITICAL module constants"
  - "notif_allowed(kind) -- the Phase 6 mute-gate seam"
  - "Monitor.notif (Gio.DBusProxy or None), Monitor.notif_slots, Monitor.notif_acts"
  - "Monitor.emit_notif(key, kind, title, body, action, urgency) -- the shared emit path"
  - "Monitor.on_notif_signal -- the click dispatcher"
  - "slot keys ('sess', sid) / ('cap', '5h') / ('cap', '7d')"
  - "action tuples ('focus', pane, tmux) / ('dash',)"
  - "serve() with a per-connection except guard"
affects:
  - "claude-monitor.py"

tech-stack:
  added:
    - "gi.repository.Gio (ships with the already-present PyGObject -- NOT a new dependency)"
  patterns:
    - "Route B: raw org.freedesktop.Notifications over Gio.DBusProxy, no Gio.Application, no .desktop"
    - "Async proxy.call() only -- one code path serves both the Gtk main thread and poll_loop"
    - "Broad per-iteration except + traceback.print_exc(), mirroring poll_loop"

key-files:
  created: []
  modified:
    - "claude-monitor.py"

decisions:
  - "Proxy constructed in Monitor.__init__ on the Gtk main thread -- the construction-time main context is what makes ActionInvoked deliverable"
  - "D-02 implemented via the urgency hint (2=CRITICAL sticks, 1=NORMAL expires), never via expire_timeout, which gnome-shell 46 does not read"
  - "on_notif_signal filters on notif_acts -- ActionInvoked is a broadcast (T-05-01)"
  - "Dropped a demo() assertion on notif_allowed: asserting that `return True` returns True is worthless, and it broke the single-choke-point grep"

metrics:
  duration: "~25 min"
  completed: 2026-07-13
  tasks: 3
  commits: 3
  files_changed: 1
---

# Phase 05 Plan 01: Notification Path Summary

The shared notification path exists: one `Gio.DBusProxy` on the Gtk main thread, one
`emit_notif` choke point gated by `notif_allowed`, one click dispatcher that acts only on
notification ids we own, and a `serve()` that a bad connection can no longer kill.

Zero producers call it yet -- that is Plans 02 and 03, by design.

## What Was Built

**Task 1 (`badde8a`)** -- `Gio` added to the existing `gi.repository` import (one name, no
new dependency). Four module constants: `NOTIF_BUS`, `NOTIF_PATH`, `URGENCY_NORMAL=1`,
`URGENCY_CRITICAL=2`. Plus `notif_allowed(kind)` -- the Phase 6 mute-gate seam, open in
Phase 5, marked with a `ponytail:` comment naming its ceiling.

**Task 2 (`440ef0f`)** -- the subsystem proper:
- `Monitor.notif` -- a `Gio.DBusProxy` built inside `__init__`, on the Gtk main thread, so
  the main context it captures at construction is one with a running loop. Wrapped in a
  `try` that leaves it `None` when the session bus itself is unreachable.
- `Monitor.emit_notif(key, kind, title, body, action, urgency)` -- the single shared emit.
  Returns early when the proxy is `None` or the gate says no. Passes `replaces_id` from a
  per-slot dict (D-03), the `urgency` hint (D-02), and `["default", "Focus"]` so a body
  click emits `ActionInvoked`. Uses the async `call()` form, so the same code path is
  correct from both `Monitor.handle` (Gtk main thread) and `poll_loop` (daemon thread) with
  no thread branching and no lock -- the reply callback always lands on the main thread, so
  both dicts are mutated from exactly one thread.
- `Monitor.on_notif_signal` -- dispatches `("focus", pane, tmux)` and `("dash",)`, and drops
  slot/action bookkeeping on `NotificationClosed`.

**Task 3 (`c83b5dc`)** -- `serve()`'s per-connection body wrapped in
`except Exception: traceback.print_exc(); continue`, with `accept()` outside the guard and
the `conn.close()` `finally` nested inside it.

## Landmines Respected

Each of these ships a feature that *looks* fine and is silently broken if ignored. All eight
are in the code, and the acceptance greps pin them:

| Landmine | How it landed |
|----------|---------------|
| Route B only, no `Gio.Application` | `grep -c 'Gio\.Application'` -> 0; bare `Gtk.main()` untouched |
| `expire_timeout` is inert; use `urgency` | `urgency` hint carries D-02; `-1` passed and documented as decoration |
| No `resident` hint | `grep -c '"resident"'` -> 0 |
| Proxy on the Gtk main thread | `grep -c 'new_for_bus_sync'` -> 1, inside `__init__` |
| `ActionInvoked` is a BROADCAST | `notif_acts.get()` returns `None` -> `return`. T-05-01 mitigated. |
| Session-derived strings in the TITLE, never the body | `emit_notif` interpolates nothing; the summary field is not markup-parsed. Enforced at the producers (Plan 02). |
| `serve()` guard INSIDE the `while` | AST-verified: the `While` body contains a `Try`, and its first statement (the `accept()`) is not it. |
| Emit safe from both threads | Async `call()` only; `grep -c 'call_sync'` -> 0 |

Absent daemon degrades to "no popup", never a raise: the failure surface is a catchable
`GLib.Error` at *call* time (guarded in both `emit_notif` and its reply callback), not at
proxy construction.

## Verification

- `python3 claude-monitor.py --selfcheck` exits 0, prints `ok` -- run before each of the
  three commits.
- Every acceptance grep in the plan reads exactly the specified count.
- **Task 3 behavior test (ROADMAP SC5), executed:** loaded the module with a stub `Monitor`,
  started `serve()` on a thread, sent a connection that raises inside the body, then a
  well-formed one. Result: traceback on stderr, **socket thread still alive**, and the
  well-formed session still delivered. Before this task the thread would have died and that
  second session would never have arrived.

  Note the plan's suggested hostile payload (`pane` as a dict) does not raise in a headless
  shell -- `terminal_focused()` returns `False` and short-circuits `looking_at` before the
  dict is ever touched. The raise was forced directly instead, which tests the guard rather
  than the payload. On a real X11 session the original payload reaches `pane_onscreen` and
  raises for real.

## Deviations from Plan

**1. [Rule 1 - Correctness] Removed a `demo()` assertion added mid-Task-1**

- **Found during:** Task 2 acceptance greps
- **Issue:** Task 1's action mentions the pure functions belong in `demo()`, so an
  `assert all(notif_allowed(k) for k in (...))` was added. It pushed
  `grep -c 'notif_allowed('` to 3, breaking Task 2's acceptance criterion of exactly 2
  (one `def`, one call site) -- the grep that enforces the single-choke-point invariant.
- **Fix:** dropped the assertion. Asserting that a body of `return True` returns `True` tests
  nothing; the seam becomes worth asserting in Phase 6 when it grows a real body. Plan 01
  introduces no other pure function -- `sess_should_notify` is Plan 02, `project`/`alert_*`
  are Plan 03 -- so `demo()` is untouched by this plan.
- **Files modified:** claude-monitor.py
- **Commit:** 440ef0f

**2. [Rule 3 - Blocking] Reworded two comments that inflated acceptance greps**

- **Found during:** Task 2 verification
- **Issue:** comments containing the literal tokens `new_for_bus_sync` and `call_sync` made
  `grep -c` return 2 and 1 where the criteria demand 1 and 0. The greps are structural
  assertions ("constructed once", "never sync"); prose mentioning the token defeats them.
- **Fix:** "constructing the proxy does NOT raise..." and "the synchronous call form would
  block...". Same meaning, greps now honest.
- **Commit:** 440ef0f

## Known Stubs

| Stub | File | Why intentional |
|------|------|-----------------|
| `notif_allowed(kind)` returns `True` unconditionally | claude-monitor.py | This is the deliverable, not an oversight: NOTIF-02 asks Phase 5 for the *seam* only. Phase 6 (CFG-01/02) replaces the body with a config lookup and touches zero call sites. Marked with a `ponytail:` comment naming the ceiling and the upgrade path. |
| `emit_notif` has no callers | claude-monitor.py | By design -- the phase thesis is that the path is the product. Plans 02 (SESS) and 03 (ALERT) ride it. |

## Out of Scope, Not Fixed

`claude-monitor.py` carries two **pre-existing** non-ASCII lines, untouched by this plan:
`:46` (an em-dash inside a comment) and `:107` (`SPARK_GLYPHS`, the dashboard's sparkline
block characters -- deliberate, and load-bearing for Phase 3's output). This plan introduced
no new Unicode. The em-dash at `:46` is a one-character cleanup for whoever next edits that
comment; `SPARK_GLYPHS` should stay.

## Self-Check: PASSED

- `claude-monitor.py` exists and parses; all three commits present in `git log`.
- `badde8a`, `440ef0f`, `c83b5dc` all found.
- `python3 claude-monitor.py --selfcheck` -> `ok`, exit 0.
</content>
</invoke>
