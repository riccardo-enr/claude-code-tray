---
phase: 08-daemon-socket-query-verb
reviewed: 2026-07-20T11:47:04Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - claude_monitor/core.py
  - claude_monitor/test_claude_monitor.py
  - claude-monitor.py
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: issues_found
---

# Phase 08: Code Review Report

**Reviewed:** 2026-07-20T11:47:04Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed the phase-08 daemon socket query verb: `Monitor.sessions_lock`, `core.build_session_snapshot`,
the `serve()` thread-per-connection refactor (`_handle_conn`), the `{"query": "snapshot"}` dispatch, and
`os.chmod(SOCK, 0o600)`. Zed-focus and frozen-duration edits present in the same diff were treated as
out of scope per the review brief.

`build_session_snapshot` itself is correct and well covered by `test_claude_monitor.py` (purity,
idempotency, defaults, JSON-serializability). The `sessions_lock` critical sections in `handle`,
`reap_stale`/`_pop_stale`, `write_dashboard`, and the new socket query handler are all scoped
correctly — the lock is held for the full copy-and-snapshot, matching the invariant the code's own
comments claim.

I specifically checked the `os.chmod(SOCK, 0o600)` placement for a TOCTOU race (bind creates the file
with the process umask before the mode is tightened) and verified empirically that `connect()` to an
`AF_UNIX` socket that has been `bind()`-ed but not yet `listen()`-ed fails with `ECONNREFUSED` on Linux —
since the code calls `chmod()` before `listen()`, there is no window where the socket both has loose
permissions and accepts connections. That ordering is correct and not flagged below.

Two real gaps remain: `watch_focus()` was not updated to honor the new `sessions_lock` invariant it
otherwise established file-wide, and the thread-per-connection refactor drops the previous implicit
backpressure (one handler thread at a time) without adding a read timeout or cap, so a connection that
never sends a full line now leaks a thread indefinitely instead of just stalling.

## Warnings

### WR-01: `watch_focus` reads/mutates `self.sessions` without the new `sessions_lock`

**File:** `claude-monitor.py:705-728` (reads: line 715; unguarded write: line 723)
**Issue:** This phase introduces `self.sessions_lock` specifically to guard `self.sessions` against
"Gtk-thread mutator + query-thread readers" (line 64), and updates `handle`, `reap_stale`/`_pop_stale`,
`write_dashboard`, and the new `{"query":"snapshot"}` handler in `_handle_conn` to take it. `watch_focus`
runs on its own daemon thread and was left untouched:

```python
pending = [
    s
    for s in list(mon.sessions.values())          # unlocked read
    if s.get("status") in ("waiting", "done") and not s.get("acked")
]
...
for s in pending:
    if pane_onscreen(s.get("pane", ""), s.get("tmux", "")):
        s["acked"] = True                          # unlocked write
```

`list(mon.sessions.values())` now races directly against the lock-protected Gtk-thread mutations in
`handle()` (`self.sessions.setdefault(...)`) and `_pop_stale()` (`self.sessions.pop(...)`): if a key is
added/removed mid-iteration this raises `RuntimeError: dictionary changed size during iteration`. The
broad `except Exception: continue` around the `watch_focus` loop body swallows that, so it self-heals
every 2s poll — but it's a real race this phase's locking work should have closed, and the unlocked
`s["acked"] = True` can also be silently clobbered by a concurrent `s.update(..., acked=...)` in
`handle()`.
**Fix:**
```python
with mon.sessions_lock:
    pending = [
        s
        for s in mon.sessions.values()
        if s.get("status") in ("waiting", "done") and not s.get("acked")
    ]
...
for s in pending:
    if pane_onscreen(s.get("pane", ""), s.get("tmux", "")):
        with mon.sessions_lock:
            s["acked"] = True
        changed = True
```

### WR-02: Thread-per-connection refactor drops backpressure without adding a recv timeout or cap

**File:** `claude-monitor.py:573-630` (recv: line 581; unbounded thread spawn: line 630)
**Issue:** `serve()` now spawns a fresh `threading.Thread` for every accepted connection, and
`_handle_conn` calls `conn.recv(65536)` exactly once with no `conn.settimeout(...)` set anywhere on the
accepted socket. A connection that is accepted but never completes a line (or never writes anything)
parks its thread in `recv()` forever. Under the previous single-threaded accept loop this only stalled
the one handler (new connections still queued in the backlog); now every stalled connection permanently
leaks one more OS thread with no cap and no timeout-based reclaim — an unbounded-growth resource-exhaustion
path introduced by this refactor. `os.chmod(SOCK, 0o600)` limits the practical blast radius to the owning
user (self-DoS only), but it's still a real robustness regression worth closing given the interface is
now used for reads, not just fire-and-forget hook events.
**Fix:** set a short timeout on the accepted socket before handing it to the thread, and/or cap
concurrent handler threads:
```python
conn, _ = srv.accept()
conn.settimeout(5)
threading.Thread(target=_handle_conn, args=(mon, conn), daemon=True).start()
```

## Info

### IN-01: New socket dispatch path (`_handle_conn`, `serve`, `{"query":"snapshot"}`) has no automated test

**File:** `claude-monitor.py:573-630` vs `claude_monitor/test_claude_monitor.py` (whole file)
**Issue:** `test_claude_monitor.py` (the `--selfcheck` gate) only exercises the pure
`core.build_session_snapshot` helper. Nothing in the suite opens `SOCK`, sends
`{"query": "snapshot"}\n`, or asserts on the JSON response shape
(`{"sessions": [...], "usage": ..., "trends": ...}`), the unknown-query silent no-op path, or the
accept-loop-spawns-a-thread-per-connection behavior. The wire-level plumbing this phase adds is
unverified by the automated gate — only its pure ingredient function is.
**Fix:** add a small integration check (can live outside `--selfcheck` if `gi`/GTK import makes that
awkward) that starts `serve()` against a temp socket path, connects, sends the query line, and asserts
the decoded reply has the three expected top-level keys and a well-shaped `sessions` list.

### IN-02: `build_session_snapshot`'s "superset" omits the new `term` field

**File:** `claude_monitor/core.py:153-171` vs `claude-monitor.py:439`
**Issue:** `handle()` now stores `term` on every session dict (`s.update(..., term=term, ...)`,
`claude-monitor.py:439`), and `Monitor.focus()` / `on_click()` / the notification action tuple all branch
on `term == "zed"` to decide whether to raise the session via tmux or via `wmctrl -a <title>`.
`build_session_snapshot`'s docstring describes its shape as a "superset... shared with Plan 08-02's query
responder," but it does not include `term`:
```python
return [
    {
        "dir": s.get("dir", ""),
        "status": s.get("status", ""),
        "entered": s.get("entered"),
        "frozen": None if s.get("status") == "running" else s.get("run_dur"),
        "pane": s.get("pane", ""),
        "tmux": s.get("tmux", ""),
    }
    for s in sessions
]
```
Any future consumer of the `{"query": "snapshot"}` socket response that wants to replicate the daemon's
own focus logic (the stated purpose of exposing `pane`/`tmux`) cannot distinguish a Zed session from a
tmux session purely from the snapshot it receives.
**Fix:** add `"term": s.get("term", "")` alongside the other five default-on-missing fields.

---

_Reviewed: 2026-07-20T11:47:04Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
