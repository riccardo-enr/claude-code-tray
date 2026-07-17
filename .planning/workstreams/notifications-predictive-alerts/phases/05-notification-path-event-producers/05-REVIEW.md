---
phase: 05-notification-path-event-producers
reviewed: 2026-07-16T00:00:00Z
depth: standard
files_reviewed: 1
files_reviewed_list:
  - claude-monitor.py
findings:
  critical: 0
  warning: 4
  info: 1
  total: 5
status: issues_found
---

# Phase 05: Code Review Report

**Reviewed:** 2026-07-16
**Depth:** standard
**Files Reviewed:** 1
**Status:** issues_found

## Summary

Reviewed `claude-monitor.py` at the state it reached after Phase 5's three plans
(05-01 shared notification emit path, 05-02 session waiting/done producer, 05-03
predictive quota alert producer). This is a retroactive gate — the plans are already
merged and manually UAT-verified (5/5 PASS) — so the findings below are about
robustness/quality gaps that a manual pass-fail UAT would not surface, not about
whether the feature works end to end.

The pure-function core (`project`, `hhmm`, `alert_due`, `alert_should_fire`,
`sess_should_notify`) is well designed and thoroughly unit-tested in `demo()`
(`--selfcheck`): the arm/re-arm state machine, the `pct==100.0` boundary, the
`exhaust`-only-above-100 invariant, and clock-skew guards are all explicitly swept
and asserted. `project()`/`hhmm()` never raise on malformed `resets_at_epoch` because
extreme values fall into the `e <= 0.05` early-return branch before reaching
`time.localtime()`.

The gaps are concentrated in the D-Bus notification plumbing that wraps that pure
core: it is the one part of this phase with no automated coverage, it doesn't reuse
a signal the codebase already computes for exactly this purpose, and it breaks the
file's own established "cross-thread work goes through `GLib.idle_add`" discipline
in one spot. None of these are correctness bugs in the shipped predicate logic; all
are robustness/UX/maintainability gaps worth fixing before this path grows further
(e.g. before 05-04's mute-gate seam gets filled in).

## Warnings

### WR-01: Notifications fire even when the user is already looking at the pane

**File:** `claude-monitor.py:1685-1715` (`Monitor.handle`), see also `looking_at`/`pane_onscreen` at `claude-monitor.py:1735-1756`

**Issue:** `serve()` already computes `_onscreen` (via `looking_at()`, which checks
both `terminal_focused()` and `pane_onscreen()`) specifically so `handle()` can
pre-acknowledge the "!" tray badge when the user is already watching the pane that
just went `waiting`/`done` (`acked=bool(msg.get("_onscreen"))` at line ~1702). But
`sess_should_notify(old, event)` (line 1705) — the gate for firing a desktop
popup — ignores that same signal entirely, by design per its own docstring: "Takes
no on-screen argument by design -- that gates the '!' badge, not this." The
`docstring` documents the choice, but the result is that a `URGENCY_CRITICAL`
("no dismiss timer; sticks until clicked") popup still appears for "Waiting for
input" even when the user's focused window is literally that exact tmux pane —
the one case where `looking_at()` was built to detect and suppress redundant
alerting. Since the signal is already computed and already threaded into the same
message, this is a straightforward, low-risk improvement, not a redesign.

**Fix:**
```python
if sess_should_notify(old, event) and not msg.get("_onscreen"):
    self.emit_notif(...)
```
(or thread `_onscreen` into `sess_should_notify` as an explicit second gate, if the
badge-vs-popup distinction needs to stay visible in the predicate's name).

### WR-02: `self.notif_slots` / `self.notif_acts` are read and written across threads without going through `idle_add`

**File:** `claude-monitor.py:1495-1533` (`Monitor.emit_notif`), called directly (not via `GLib.idle_add`) from `claude-monitor.py:1794-1847` (`poll_loop`) at line 1821

**Issue:** Every other piece of `Monitor` state that crosses threads in this file is
funneled through `GLib.idle_add` on purpose — `serve()` calls `GLib.idle_add(mon.handle, msg)`,
`poll_loop` calls `GLib.idle_add(mon.apply_usage, usage)`, and `compute_trends`/
`write_dashboard` are explicitly commented as reading history "off the Gtk main
thread" while the redraw stays on it. `emit_notif`, however, is called directly
from `poll_loop`'s background thread for cap alerts (`mon.emit_notif(("cap", cap), ...)`
at line 1821), and its body reads `self.notif_slots.get(key, 0)` (line 1505) on
whichever thread called it, while the async `done()` completion callback and
`on_notif_signal` (line 1536, both dispatched on the GLib default main context, i.e.
the Gtk thread) write to the same two plain `dict`s. CPython's GIL means this can't
corrupt the dict, but it is a genuine, unsynchronized reader/writer pattern the rest
of the file deliberately avoids, and the failure mode is concrete: a stale read of
`notif_slots.get(key, 0)` returns `0` (no previous id) when a previous popup for
that slot is actually still live, so `replaces_id=0` creates a brand-new stacked
notification instead of replacing the old one — the exact "stacking" bug the
`emit_notif` docstring is otherwise careful to avoid ("Re-store on EVERY reply...
keeping the dead one stacks popups").

**Fix:** Route the `poll_loop` alert-firing call through `GLib.idle_add(mon.emit_notif, ...)`
like every other cross-thread call in this file, so all reads/writes of
`notif_slots`/`notif_acts` happen on the Gtk main thread only.

### WR-03: `Monitor.handle()`'s new notify call has no exception guard, unlike its `poll_loop` sibling

**File:** `claude-monitor.py:1685-1715` (`Monitor.handle`)

**Issue:** The cap-alert call to `mon.emit_notif(...)` in `poll_loop` (line 1821) is
inside that function's own `try: ... except Exception: traceback.print_exc()`
(lines 1806-1846), so any exception raised while building/marshaling the
`GLib.Variant` in `emit_notif` degrades to "one poll didn't alert" rather than
killing anything. The session-notification call added in `Monitor.handle()`
(`self.emit_notif(...)` at line 1706) has no equivalent protection: `handle()`
itself is not wrapped in a `try/except`, and it runs via `GLib.idle_add(mon.handle, msg)`
from `serve()`, decoupled from `serve()`'s own per-connection `try/except`
(the one added by 05-01's `c83b5dc` hardening commit only covers `serve()`'s own
call stack, not code that executes later via `idle_add`). Nothing in the *current*
call sites can actually trigger this (title/body are always plain strings today),
so this isn't presently reachable, but it's an asymmetry worth closing before this
path gains more branches — the file's stated philosophy elsewhere is "a raise here
can kill the signal source" (see `on_notif_signal`'s own comment) and every other
GLib-callback entry point in the file (`on_notif_signal`, `watch_focus`, `poll_loop`,
`serve()`'s per-connection loop) is wrapped for exactly that reason; `handle()` is
the one exception.

**Fix:**
```python
def handle(self, msg):
    try:
        ...  # existing body
    except Exception:
        traceback.print_exc()
    return False
```

### WR-04: The notification emit/dispatch path has zero automated coverage

**File:** `claude-monitor.py:999-1436` (`demo()`), vs. `claude-monitor.py:1495-1557` (`emit_notif`, `on_notif_signal`) and `1685-1715` (`handle`'s notify wiring)

**Issue:** `demo()` (run via `--selfcheck`) thoroughly covers the pure predicates
this phase added — `sess_should_notify`, `project`, `alert_due`, `alert_should_fire`
all have dedicated assertion blocks, including boundary sweeps. None of that
coverage extends to the actual notification plumbing: `emit_notif`'s D-Bus `Variant`
construction/marshaling, the `replaces_id` bookkeeping, `on_notif_signal`'s click
dispatch, or `handle()`'s `sess_should_notify(...)` -> `emit_notif(...)` wiring. This
is understandably hard to unit test headlessly (it needs a running notification
daemon), but right now a regression in any of that glue (e.g. a typo in the
`"(susssasa{sv}i)"` type string, or a broken `key` in the `notif_slots` bookkeeping)
would only be caught by a human clicking through notifications by hand, not by
`--selfcheck`.

**Fix:** Not a blocker for this phase, but worth a follow-up: at minimum, fake/stub
out `self.notif` (e.g. a recording double instead of a real `Gio.DBusProxy`) so
`emit_notif`'s replaces_id logic and `on_notif_signal`'s id-based cleanup can be
exercised by `--selfcheck` without a real D-Bus session.

## Info

### IN-01: A very fast quota burn can produce zero alerts for that window

**File:** `claude-monitor.py:113-132` (`alert_due`, `alert_should_fire`), `claude-monitor.py:79` (`ALERT_LEAD`)

**Issue:** `alert_should_fire` only fires once the projected exhaustion is at least
`ALERT_LEAD` (15 min) in the future, and arms per-window (no re-fire once armed).
If a burst of usage pushes the projected exhaustion from "not yet exhausting" to
"exhausting in under 15 minutes" between two 15s polls, the window can pass through
the actionable range without ever landing inside it, and the user gets no alert for
that entire 5h/7d window despite blowing through the cap. This is already flagged
in-code as a known, deliberate simplification (`# ponytail: no lead-step re-fires
("30m left"); add a second armed threshold if needed.` at line 131), so this is
purely a confirmation that the documented ceiling is real, not a new finding —
included here for completeness since it is the one place the predictive-alert
producer can silently under-deliver on its stated goal.

**Fix:** None needed now; the ponytail comment already names the upgrade path
(a second, closer-in armed threshold) if this is ever observed in practice.

---

_Reviewed: 2026-07-16_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
