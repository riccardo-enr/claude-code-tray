---
phase: 07-live-session-view
reviewed: 2026-07-18T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - claude-monitor.py
  - claude_monitor/core.py
  - claude_monitor/dashboard.py
  - claude_monitor/test_claude_monitor.py
findings:
  critical: 1
  warning: 6
  info: 3
  total: 10
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-07-18T00:00:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

This supersedes the prior `07-REVIEW.md` (which only covered the 07-01 sessions-panel
diff, before `core.py` and the 07-02 gap-closure reap mechanism existed). All four files
were re-read in full, with emphasis on the threading discipline the phase context calls
out: `self.sessions` must stay single-mutator (Gtk main thread only, via
`GLib.idle_add`), and `Monitor.reap_stale` (poll thread) must never call
`.pop()`/`.update()` on it directly.

The single-mutator invariant for `self.sessions` itself is respected: `reap_stale` only
reads (`list(self.sessions.items())`) and shells out to `pane_alive`; the actual removal
happens in `_pop_stale`, invoked exclusively via `GLib.idle_add`. That part of T-07-03's
disposition is correct.

What is not solid: the age-ceiling reap policy (`REAP_MAX_AGE = 3600`, applied
uniformly regardless of status) interacts badly with the existing
`sess_should_notify`/`Monitor.handle` transition logic — a session that is genuinely
still `waiting` or `running` past one hour gets silently dropped and, on its very next
routine hook resend, is treated as a *brand-new* session (`old` reads `None` again),
which re-fires a real `URGENCY_CRITICAL` "Waiting for input" popup for something the user
already saw and (possibly) acknowledged. The phase's own threat register (T-07-05)
accepts the age-ceiling false-positive as merely "cosmetic... temporary disappearance,"
but that disposition does not account for this notification-re-fire side effect, which is
materially more user-visible than a quiet blip in the tray/dashboard.

One item from the prior review is now resolved by this phase: WR-03 ("done" sessions
grow an unbounded, unrelated duration forever) is fixed as a side effect of
`reap_stale`'s unconditional age ceiling — a `done` session with no `end` event is now
reaped within `REAP_MAX_AGE` regardless of pane state, so it no longer accumulates
duration forever. No action needed there.

`just selfcheck` passes on the current tree; the new `session_stale` asserts are correct
in isolation, but they only test the pure decision function, not its consequences once
wired through `Monitor.handle`/`sess_should_notify` (see WR-06).

## Critical Issues

### CR-01: Age-based reap silently re-triggers a critical notification for sessions that never actually changed state

**File:** `claude_monitor/core.py:119-137` (`session_stale`), `claude-monitor.py:410-432` (`reap_stale`/`_pop_stale`), `claude-monitor.py:373-408` (`Monitor.handle`, `sess_should_notify` call site)
**Issue:** `session_stale` reaps *any* session — regardless of `status` — once
`now - entered > REAP_MAX_AGE` (1 hour), and `alive=True` does **not** block this (by
design, to catch the same-pane `/exit`/`/clear` case). `entered` is only re-stamped on a
real status *transition* (`claude-monitor.py:395-396`), so a session that has been
legitimately sitting in `"waiting"` (or a single long `"running"` tool call) for over an
hour without transitioning gets popped by `_pop_stale` even though `pane_alive` confirmed
it is still alive.

`sess_should_notify`'s own docstring (`claude_monitor/core.py:108-113`) states as an
established fact that "a session sitting in 'waiting' re-sends it on every hook event;
only a transition passes" — i.e. the CLI/hook keeps re-sending the same `"waiting"` event
while nothing has changed, and the existing `old_status != new_status` guard is precisely
what suppresses a duplicate notification on every such resend.

Once `_pop_stale` removes the entry, `Monitor.handle`'s next `setdefault(sid, {})`
(`claude-monitor.py:385`) creates a **fresh** dict; `old = s.get("status")` reads `None`
again (`claude-monitor.py:386`). The very next routine `"waiting"` resend then satisfies
`sess_should_notify(None, "waiting") == True`, so `emit_notif` fires a fresh
`URGENCY_CRITICAL` "Waiting for input" popup (`claude-monitor.py:398-406`) — for a session
the user has already seen, possibly already acknowledged (`acked` is also reset to
`False` on the fresh dict, re-arming the tray "!" badge too). This will recur roughly
every `REAP_MAX_AGE` for any session that idles in `waiting` (e.g. the user is away from
the keyboard, in a meeting, or overnight) longer than an hour.

The phase's threat register (07-02-PLAN.md, T-07-05) disposes of the false-reap case as
"a cosmetic, self-correcting miss... No user-visible harm beyond a temporary
disappearance," which does not account for this concrete, reproducible notification
re-fire. This is a functional regression in the exact area (notifications) this
milestone workstream targets — a user who dismissed a "waiting" alert an hour ago will
get interrupted again by an identical alert for a session that never changed.
**Fix:** Suppress the false "transition" only for notification purposes when the
"resurrection" is caused by a self-heal reap, not a real gap. E.g. remember the reaped
session's last status briefly and seed the new dict's baseline from it instead of
treating it as brand-new:
```python
# Monitor._pop_stale
def _pop_stale(self, sids):
    for sid in sids:
        s = self.sessions.pop(sid, None)
        if s is not None:
            self._reaped_status[sid] = s.get("status")  # short-lived memory only
    self.rebuild_menu()
    return False

# Monitor.handle
s = self.sessions.setdefault(sid, {})
old = s.get("status") or self._reaped_status.pop(sid, None)
```
This keeps the reap's cleanup behavior (stale rows still disappear from the tray/
dashboard within a poll tick) while preventing a same-status resurrection from being
read as a real transition. Alternatively, narrow the unconditional age ceiling so it does
not apply to `"waiting"`/`"running"` sessions when `alive is True` (only fall back to
age for `alive in (False, None)`), accepting that the same-pane `/exit`/`/clear` case for
an actively-displayed pane takes longer to self-heal.

## Warnings

### WR-01: `reap_stale`'s decision and `_pop_stale`'s enactment are split across an unsynchronized time gap (TOCTOU)

**File:** `claude-monitor.py:410-432`
**Issue:** `reap_stale` (poll thread) computes the `stale` list from a snapshot taken at
time T, then hands it to `GLib.idle_add(self._pop_stale, stale)`, which runs at some
later time T+delta on the Gtk main loop. If a genuine hook event arrives for one of those
session ids in the interim (e.g. `Monitor.handle` updates `entered`/`status` because the
session is not actually stale), `_pop_stale` still unconditionally pops it — the
staleness decision is never re-validated at enactment time. In practice the window is
usually small (one Gtk main-loop iteration), but under load (e.g. the Gtk thread busy
redrawing menus, or a burst of hook events) it can widen, discarding a session that "un-staled"
itself between the check and the pop.
**Fix:** Re-check staleness inside `_pop_stale` before popping, using the live dict (now
safely on the Gtk thread):
```python
def _pop_stale(self, sids):
    now = time.time()
    for sid in sids:
        s = self.sessions.get(sid)
        if s is not None and core.session_stale(
            pane_alive(s.get("pane", ""), s.get("tmux", "")), s.get("entered"), now, core.REAP_MAX_AGE
        ):
            self.sessions.pop(sid, None)
    self.rebuild_menu()
    return False
```
(Note this reintroduces a `pane_alive` shell-out on the Gtk thread, which the design
explicitly avoids — so the cheaper fix is just re-checking `entered`/`now` age without
re-shelling to tmux, accepting a slightly staler liveness signal.)

### WR-02: `watch_focus` mutates live session dicts from a non-Gtk thread

**File:** `claude-monitor.py:588-611` (`watch_focus`), specifically line 606 (`s["acked"] = True`)
**Issue:** `watch_focus` runs as its own daemon thread (`threading.Thread(target=watch_focus, ...)`,
`claude-monitor.py:618`), not the Gtk main thread. It builds `pending` from
`list(mon.sessions.values())` — a list of the *same* dict objects stored in
`self.sessions`, not copies — and then does `s["acked"] = True` directly on them
(`claude-monitor.py:606`), bypassing `GLib.idle_add` entirely. This directly contradicts
the single-mutator posture the phase document calls out for `self.sessions` (`reap_stale`/
`_pop_stale` were built specifically to avoid this pattern). `Monitor.handle` (Gtk
thread) can be mid-`s.update(...)` on the exact same dict at the exact same time,
racing on the same object. CPython's GIL prevents memory corruption, but this is still an
unsynchronized concurrent write to state the Gtk thread's `rebuild_menu()` reads, and it
is exactly the kind of pattern this phase's own documentation says must not happen. This
predates 07-02 but is in-scope since `claude-monitor.py` was reviewed in full.
**Fix:** Route the ack through the same `idle_add` pattern as everything else:
```python
if changed:
    GLib.idle_add(mon._ack_sessions, [s for s in pending if pane_onscreen(...)])
# Monitor._ack_sessions(self, sessions):
#     for s in sessions: s["acked"] = True
#     self.rebuild_menu(); return False
```
or simply compute the sid list on the watch thread and mutate via a small Gtk-thread-only
helper, mirroring `_pop_stale`.

### WR-03: `write_dashboard`'s session snapshot can read a torn/partially-updated dict

**File:** `claude-monitor.py:350-354` (reader), `claude-monitor.py:388-396` (writer)
**Issue:** `write_dashboard` (poll thread) builds its session snapshot with three
separate `.get()` calls per live session dict:
```python
sessions = [
    {"dir": s.get("dir", ""), "status": s.get("status", ""),
     "entered": s.get("entered")}
    for s in list(self.sessions.values())
]
```
`Monitor.handle` (Gtk thread) updates the same dict in two separate steps —
`s.update(dir=d, status=event, ...)` then, conditionally, `s["entered"] = time.time()`
two lines later. If the poll thread's reads interleave between those two steps, the
snapshot can capture the *new* status with the *stale* `entered`, producing an
internally-inconsistent dashboard row (e.g. a row that looks freshly transitioned into
`"done"` but whose duration is computed from the previous state's timestamp). The
inline comment ("A concurrent Gtk-thread mutation degrades to the except-Exception skip
below") only covers a `RuntimeError` from the dict changing size during `list(...)`, not
this quieter torn-field read, which raises nothing.
**Fix:** Snapshot the whole dict in one shot before pulling fields, and/or fold
`handle`'s two-statement update into one:
```python
sessions = [dict(s) for s in list(self.sessions.values())]
...
entered = time.time() if old != event else s.get("entered")
s.update(dir=d, status=event, pane=pane, tmux=tmux, cwd=cwd,
          acked=bool(msg.get("_onscreen")), entered=entered)
```

### WR-04: `SESS_RANK` lookup in the dashboard sort comparator is an unguarded object literal

**File:** `claude_monitor/dashboard.py:470,483-487`
**Issue:**
```js
var SESS_RANK={waiting:0,running:1,done:2};
...
var ra=SESS_RANK[a.status];if(ra===undefined)ra=99;
```
`s.status` is `msg.get("event", "done")` from `claude-monitor.py:handle` — an arbitrary
string taken verbatim from any local process's JSON message on the unix socket, not
restricted to `running`/`waiting`/`done`. If `status` collides with an inherited
`Object.prototype` member (`"constructor"`, `"toString"`, `"__proto__"`, ...),
`SESS_RANK[a.status]` resolves to that inherited value instead of `undefined`, so the
`ra===undefined` guard never fires and `ra-rb` becomes `NaN`, silently breaking the
intended sort order. Low real-world impact (local trust boundary only, no code
execution), but a one-line fix.
**Fix:**
```js
var SESS_RANK=Object.create(null);
SESS_RANK.waiting=0;SESS_RANK.running=1;SESS_RANK.done=2;
```

### WR-05: `notif_slots`/`notif_acts` are read on the poll thread and written on the Gtk thread without coordination

**File:** `claude-monitor.py:114-153` (`emit_notif`), `claude-monitor.py:559-570` (direct `poll_loop` call, not via `idle_add`)
**Issue:** `poll_loop` calls `mon.emit_notif(...)` directly (not wrapped in
`GLib.idle_add`) for the 5h/7d cap alerts, so `prev = self.notif_slots.get(key, 0)`
(`claude-monitor.py:124`) executes on the poll thread, while the async D-Bus `done`
callback (`claude-monitor.py:140-148`) writes `self.notif_slots[key] = nid` and
`self.notif_acts[nid] = action` on the Gtk thread (the proxy's captured main context).
This is a cross-thread read/write on shared dicts with no lock. GIL prevents corruption,
but it is unsynchronized state shared across the same boundary the phase explicitly
hardens for `self.sessions`. Collisions are rare in practice (session vs. cap keys rarely
overlap), so this is lower-priority than CR-01/WR-01-03, but it is the same category of
bug and predates this phase without ever being fixed.
**Fix:** Route the `poll_loop` cap-alert `emit_notif` calls through `GLib.idle_add` like
every other cross-thread call in this file, or give `notif_slots`/`notif_acts` a
`threading.Lock`.

### WR-06: The reap wiring and the `entered`-stamp-on-transition logic have no test coverage beyond the pure `session_stale` function

**File:** `claude-monitor.py:373-408` (`Monitor.handle`), `claude-monitor.py:410-432` (`reap_stale`/`_pop_stale`); absent from `claude_monitor/test_claude_monitor.py`
**Issue:** `--selfcheck` thoroughly covers `core.session_stale` in isolation
(`test_claude_monitor.py:465-486`), but nothing exercises the actual interaction CR-01
depends on: that a reaped-and-resurrected session re-triggers `sess_should_notify`. The
`if old != event: s["entered"] = time.time()` stamp (`claude-monitor.py:395-396`) and the
`reap_stale`/`_pop_stale` wiring both live inline in GTK-dependent `Monitor` methods and
are untestable by the current Gtk-free `--selfcheck` harness. A regression here (e.g.
someone "fixes" CR-01 incorrectly, or breaks the stamp-on-transition guard) would ship
silently past the verification gate.
**Fix:** Extract the notification-relevant parts into pure, testable functions in
`core.py`, mirroring `sess_should_notify`/`session_stale` — e.g. a
`session_entered(old_status, new_status, prev_entered, now)` helper for the stamp logic,
and (once CR-01 is fixed) a pure helper for "does this resurrection count as a real
transition" that `Monitor.handle` calls, so the interaction can be asserted directly in
`--selfcheck` the way `alert_should_fire`'s arm/re-arm state machine already is.

## Info

### IN-01: Hardcoded `colspan="3"` tied to table header column count

**File:** `claude_monitor/dashboard.py:490`
**Issue:** The empty-state row hardcodes `etd.setAttribute("colspan","3")`, matching the
three `<th>` columns in `_DASH_BODY` (`dashboard.py:192`), with no compiler/test tie
between the two if a column is ever added.
**Fix:** Derive the count at render time
(`document.querySelectorAll("#sess-tbl thead th").length`) or leave cross-referencing
comments at both sites.

### IN-02: Reaped session ids leave orphaned entries in `notif_slots`/`notif_acts`/`alert_armed`

**File:** `claude-monitor.py:427-432` (`_pop_stale`), `claude-monitor.py:66-68` (dicts)
**Issue:** `_pop_stale` removes the session from `self.sessions` but never clears any
`("sess", sid)` entry from `self.notif_slots`/`self.notif_acts` for that id. These
dicts grow unbounded over the life of the tray process as sessions churn (one stale entry
per reaped/ended session whose id is never reused). Small, slow leak, not a correctness
bug, but worth a one-line cleanup while touching this code path.
**Fix:** In `_pop_stale`, also `self.notif_slots.pop(("sess", sid), None)`.

### IN-03: `event`/`status` values are never validated against the known set

**File:** `claude-monitor.py:373-375` (`Monitor.handle`)
**Issue:** `event = msg.get("event", "done")` accepts any string from any local process
connected to the unix socket, with no validation against `{"running", "waiting", "done",
"end"}`. This is what makes WR-04 possible and lets an unexpected value silently render
as an unstyled dot/label in the dashboard/tray rather than being rejected. Not exploitable
(local trust boundary, textContent-only rendering), but cheap hygiene.
**Fix:** `if event not in ("running", "waiting", "done", "end"): event = "done"` (or log
and drop) near the top of `handle`.

---

_Reviewed: 2026-07-18T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
