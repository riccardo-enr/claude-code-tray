---
phase: 07-live-session-view
reviewed: 2026-07-18T16:49:55Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - claude-monitor.py
  - claude_monitor/dashboard.py
  - claude_monitor/test_claude_monitor.py
findings:
  critical: 0
  warning: 4
  info: 1
  total: 5
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-07-18T16:49:55Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed the sessions-panel diff (`c722b45^..HEAD`): the `entered`-on-change stamp in
`Monitor.handle`, the `sessions` snapshot threaded through `write_dashboard` ->
`render_dashboard`, the new `"sessions"` payload key, the inline table markup/CSS, and
the client-side `renderSessions()` 1s ticker in `_DASH_JS`.

The XSS-sensitive path this phase called out (D-08: untrusted project-dir string into
the DOM) is implemented correctly — the table only ever uses `textContent` /
`createTextNode` for `s.dir` and `s.status`, never `innerHTML`, and the hostile-dir
selfcheck (`<b>x</b>` round-tripping through `_embed_json` without producing raw
markup) passes. No injection bug was found in that path.

What is not solid: the sort comparator keys a plain JS object with an
attacker/local-process-influenced `status` string (prototype-chain lookup hazard); the
new session snapshot reads a live, concurrently-mutated dict field-by-field instead of
atomically, which can produce a torn read that the code's own comment does not account
for; "done" sessions that never receive an `end` event grow an unbounded, increasingly
misleading duration with no cleanup path; and the phase's actual behavioral change (the
stamp-on-transition guard in `Monitor.handle`) has zero test coverage, unlike its sibling
`sess_should_notify`, which is fully covered in `core.py`/`test_claude_monitor.py`.

`just selfcheck` (`python3 claude-monitor.py --selfcheck`) passes on the current tree.

## Warnings

### WR-01: Session status used as an unguarded object-literal lookup key (prototype hazard)

**File:** `claude_monitor/dashboard.py:470,484-486`
**Issue:** `SESS_RANK` is a plain object literal:
```js
var SESS_RANK={waiting:0,running:1,done:2};
...
list.sort(function(a,b){
  var ra=SESS_RANK[a.status];if(ra===undefined)ra=99;
  var rb=SESS_RANK[b.status];if(rb===undefined)rb=99;
  return ra-rb;
});
```
`s.status` comes from `msg.get("event", "done")` in `claude-monitor.py:handle`, which is
an arbitrary string taken verbatim from a JSON message on the unix socket (any local
process holding a connection can send any `event` value — not restricted to
`running`/`waiting`/`done`). If `status` happens to collide with an inherited
`Object.prototype` member name (`"constructor"`, `"hasOwnProperty"`, `"toString"`,
`"__proto__"`, ...), `SESS_RANK[a.status]` resolves to that inherited function/object
instead of `undefined`, so the `ra===undefined` guard never fires. `ra-rb` then
evaluates to `NaN`, and the comparator silently produces unspecified sort order (V8 does
not throw, but the table stops honoring the intended waiting-first/done-last ordering).
Low real-world impact (local trust boundary, no code execution, no data leak), but it is
exactly the kind of unguarded-map lookup bug this review is meant to catch, and it is
easy to make immune to it.
**Fix:**
```js
var SESS_RANK=Object.create(null);
SESS_RANK.waiting=0;SESS_RANK.running=1;SESS_RANK.done=2;
// or: var ra=Object.prototype.hasOwnProperty.call(SESS_RANK,a.status)?SESS_RANK[a.status]:99;
```

### WR-02: Torn read of live session dicts in `write_dashboard` contradicts its own safety comment

**File:** `claude-monitor.py:350-354` (reader), `claude-monitor.py:388-396` (writer)
**Issue:** `write_dashboard` runs on the poll thread and builds the session snapshot by
calling three separate `.get()` calls per session **on the same mutable dict objects**
that `Monitor.handle` (Gtk main thread) mutates in place — it does not copy the dict
first:
```python
sessions = [
    {"dir": s.get("dir", ""), "status": s.get("status", ""),
     "entered": s.get("entered")}
    for s in list(self.sessions.values())
]
```
`Monitor.handle` performs the update as two separate statements on the same dict:
```python
s.update(dir=d, status=event, pane=pane, tmux=tmux, cwd=cwd, acked=...)
if old != event:
    s["entered"] = time.time()
```
If the poll thread's `.get("status", ...)` / `.get("entered")` calls interleave with the
Gtk thread between those two statements, the snapshot can capture the *new* `status` but
the *stale* `entered` (or any other partially-applied combination), producing an
internally inconsistent row: e.g. a session shown as freshly transitioned into `"done"`
but with a duration computed from the previous state's `entered` timestamp. The comment
at `claude-monitor.py:348-349` asserts this "degrades to the except-Exception skip
below," but that framing only covers the `RuntimeError` from `list(self.sessions.values())`
racing a key insert/delete — it does not cover this quieter torn-field read, which
raises nothing and just ships wrong data into one dashboard-regen cycle. Narrow window
(the whole `handle()` call is a handful of bytecodes), self-heals on the next 5-minute
regen, so this is not release-blocking, but the comment overstates the safety margin and
the fix is essentially free.
**Fix:** snapshot each session in one shot instead of three separate reads, e.g.
`dict(s)` (or `s.copy()`) before pulling fields out, and/or fold the two-statement update
in `handle()` into the single `s.update(...)` call (compute `entered` before the call):
```python
entered = time.time() if old != event else s.get("entered")
s.update(dir=d, status=event, pane=pane, tmux=tmux, cwd=cwd,
          acked=bool(msg.get("_onscreen")), entered=entered)
```

### WR-03: "done" sessions with no `end` event grow an unbounded, misleading duration forever

**File:** `claude-monitor.py:373-379` (only removal path), `claude_monitor/dashboard.py:471-509` (`sessDur`/`renderSessions`)
**Issue:** `self.sessions[sid]` is only ever removed on an explicit `event == "end"`
message (`claude-monitor.py:376-379`). If a Claude Code process is killed, the hook
never fires, or the socket write is dropped, the session dict lingers indefinitely with
`status: "done"` and its original `entered` timestamp. Before this phase that stale
entry was cosmetic (just an inert row in the tray dropdown); now it actively renders a
ticking duration (`sessDur(now - s.entered)`, ticked every second via
`setInterval(renderSessions,1000)`) that grows without bound — a session that actually
finished in two minutes will show `"3d 14h"` a few days later, presented with the same
visual weight as genuinely long-running sessions, with no way for the dashboard to tell
the difference or age the row out.
**Fix:** either prune sessions whose `status == "done"` and `entered` is older than some
TTL (e.g. in `rebuild_menu`/`poll_loop`, alongside the existing history prune cadence),
or cap/relabel the displayed duration once it exceeds a sane ceiling (e.g. show "stale"
past a few hours in `done` state) so a missed `end` event degrades visibly instead of
silently misleading the viewer.

### WR-04: The phase's core behavioral change (`entered` stamp-on-transition) has no test coverage

**File:** `claude-monitor.py:392-396`; absent from `claude_monitor/test_claude_monitor.py`
**Issue:** D-01 ("stamp `entered` only on a real transition, not on every keepalive in
the same status") is the actual new logic this phase introduces in `Monitor.handle`, but
it lives inline in a GTK-dependent method and is never exercised by `--selfcheck`. Every
session-panel assertion in `test_claude_monitor.py` (`SESSVIEW-01..05`) fabricates
`sessions` dicts directly and only exercises `render_dashboard`'s rendering/escaping —
none of them exercise the stamp-on-transition guard itself. Contrast with
`sess_should_notify`, the sibling piece of transition logic, which was extracted into
`core.py` specifically so it could be unit-tested (and is, extensively, at
`test_claude_monitor.py:456-462`). A regression here (e.g. someone "simplifies" the
`if old != event:` guard away, resetting the dashboard counter on every keepalive as the
comment explicitly warns against) would ship silently past the verification gate.
**Fix:** extract the stamp decision into a small pure function in `core.py` (mirroring
`sess_should_notify`), e.g. `def session_entered(old_status, new_status, prev_entered, now)`,
call it from `Monitor.handle`, and add the same style of assertions used for
`sess_should_notify` to `test_claude_monitor.py`.

## Info

### IN-01: Hardcoded `colspan="3"` tied to table header column count

**File:** `claude_monitor/dashboard.py:490`
**Issue:** The empty-state row hardcodes `etd.setAttribute("colspan","3")`, matching the
three `<th>` columns in `_DASH_BODY` (`dashboard.py:192`). If a column is ever added to
the sessions table, this literal has to be remembered and updated separately with no
compiler/test tie between the two.
**Fix:** derive the count from the header at render time
(`document.querySelectorAll("#sess-tbl thead th").length`) or leave a comment at both
sites cross-referencing the other, so a future column addition can't silently desync
them.

---

_Reviewed: 2026-07-18T16:49:55Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
