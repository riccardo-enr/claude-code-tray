# Phase 08: Daemon Socket Query Verb - Pattern Map

**Mapped:** 2026-07-20
**Files analyzed:** 1 (single-file change, no new files)
**Analogs found:** 1 / 1 (self-referential -- modifying `claude-monitor.py` using its own existing patterns)

## File Classification

This phase modifies exactly one file, `claude-monitor.py`, in four distinct
sections. Each section is classified separately since they play different
roles within the same module.

| New/Modified Section | Role | Data Flow | Closest Analog | Match Quality |
|-----------------------|------|-----------|-----------------|---------------|
| `serve()` accept loop -> thread-per-connection + query dispatch | socket handler | request-response | `serve()` itself (`claude-monitor.py:523-556`) | exact (extend in place) |
| New query responder (build snapshot dict, `conn.sendall`) | service/handler | request-response | `write_dashboard()` sessions snapshot (`claude-monitor.py:364-369`) | exact |
| `Monitor.__init__` -> add `threading.Lock` | model/state | CRUD (guarded mutation) | `Monitor.__init__` (`claude-monitor.py:60-70`) | exact (extend in place) |
| `handle()`, `reap_stale()`/`_pop_stale()`, `write_dashboard()` -> wrap `self.sessions` access with lock | controller/model mutators+readers | CRUD | same methods, pre-lock versions | exact (extend in place) |

## Pattern Assignments

### `serve()` -- thread-per-connection + query dispatch (socket handler, request-response)

**Analog:** itself, `claude-monitor.py:523-556` (extend, do not replace shape)

**Current per-connection body to move into a thread target** (lines 533-556):
```python
while True:
    conn, _ = srv.accept()
    try:
        try:
            buf = conn.recv(65536).decode("utf-8", "replace")
        finally:
            conn.close()  # nested: a recv failure must not leak an fd
        for line in buf.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            # Decided here, off the Gtk main thread: looking_at() shells out.
            if msg.get("event") in ("done", "waiting"):
                msg["_onscreen"] = looking_at(
                    msg.get("pane", ""), msg.get("tmux", "")
                )
            GLib.idle_add(mon.handle, msg)
    except Exception:
        traceback.print_exc()  # loud and repeated; the thread survives regardless
        continue
```

**What changes (per D-02/D-03/D-04/D-05):**
- `accept()` stays in the main loop (unchanged: `conn, _ = srv.accept()`).
- The body of the current `try/except Exception` block becomes a thread
  target function (e.g. `_handle_conn(mon, conn)`), spawned via
  `threading.Thread(target=_handle_conn, args=(mon, conn), daemon=True).start()`
  instead of running inline. The existing `except Exception: traceback.print_exc()`
  and the nested `try/finally: conn.close()` move unchanged into that target
  function -- same isolation shape, now per-thread instead of per-loop-iteration.
- Inside the per-line dispatch, branch on `"query"` vs `"event"` key before
  the existing `msg.get("event") in ("done", "waiting")` check:
  ```python
  if "query" in msg:
      # build snapshot dict (see below), conn.sendall(json.dumps(snapshot).encode() + b"\n")
      continue
  ```
- `GLib.idle_add(mon.handle, msg)` remains the hook-event path, untouched.

**Reuse:** `threading` is already imported (line 18) -- `import threading` at
top of file, no new import needed.

---

### Query responder -- snapshot payload (service/handler, request-response)

**Analog:** `write_dashboard()`'s sessions-snapshot comprehension, `claude-monitor.py:364-369`

**Pattern to mirror for the `sessions` field of the response payload:**
```python
sessions = [
    {"dir": s.get("dir", ""), "status": s.get("status", ""),
     "entered": s.get("entered"),
     "frozen": None if s.get("status") == "running" else s.get("run_dur")}
    for s in list(self.sessions.values())
]
```
Per D-06, extend/reuse this shape (or a superset with `pane`/`tmux` per
CONTEXT's "dir/status/pane/tmux/entered") for the query response's
`sessions` key, then add `self.usage` and `self.trends` verbatim (already
plain dicts/lists -- no further snapshotting needed, per D-06: "zero file
I/O on the query path").

**Response send pattern (D-05), modeled on existing `conn.recv`/`close` shape:**
```python
conn.sendall((json.dumps(snapshot) + "\n").encode("utf-8"))
```
placed inside the same nested `try/finally: conn.close()` block already
used for `recv` (lines 535-539) -- one connection, one shot, closes after.

---

### `Monitor.__init__` -- add lock (model/state init)

**Analog:** itself, `claude-monitor.py:60-70`

**Existing attribute-init block to extend:**
```python
self.sessions = {}  # session_id -> {dir,status,pane,tmux,cwd}
self.usage = None  # latest parse_usage() dict, or None if unavailable
self.usage_misses = 0  # consecutive failed polls; >= threshold -> unavailable
self.trends = None  # cached trend row strings, or None (collecting state)
```
Add one line following the same inline-comment convention, e.g.:
```python
self.sessions_lock = threading.Lock()  # guards self.sessions: Gtk mutator + query-thread readers (D-01)
```

---

### `self.sessions` access sites -- add lock coverage (controller/model, CRUD)

**Analog:** the four existing call sites themselves, `claude-monitor.py:388-460`

Per D-01, wrap each read/mutate of `self.sessions` with
`with self.sessions_lock:`. Concrete existing sites and their current shape
(mutation shape to preserve, only add the `with` wrapper around it):

- `handle()` (line 388-433): `self.sessions.setdefault(sid, {})` (line 401)
  and the `.pop(sid, None)` early-return branch (line 392) -- both need the
  lock.
- `reap_stale()` (line 442-448): `list(self.sessions.items())` read inside
  the list comprehension -- needs the lock around the snapshot-into-list
  step (the `pane_alive`/`session_stale` calls that follow can stay outside
  the lock since they don't touch `self.sessions`).
- `_pop_stale()` (line 452-460): `self.sessions.get(sid)` and
  `self.sessions.pop(sid, None)` -- needs the lock.
- `write_dashboard()` (line 364-369): `list(self.sessions.values())` --
  needs the lock (this is the one D-01 explicitly calls out as currently
  lock-free/accepted-risk, now brought under the same lock for consistency).
- New query responder: needs the lock around its own `list(self.sessions.values())` snapshot, same as `write_dashboard()`.

**Note:** `threading.Lock` (not `RLock`) is fine since none of these call
sites call back into another lock-acquiring method while already holding
the lock (each acquires, snapshots/mutates, releases, in a flat block) --
per CONTEXT's Claude's Discretion, this is planner/implementer's call but a
plain `Lock` matches the existing flat, no-reentrancy call shape.

---

## Shared Patterns

### Broad `except Exception` per unit of isolation
**Source:** `claude-monitor.py:535-539` (nested `try/finally: conn.close()`) and `:554-556` (outer `except Exception: traceback.print_exc()`)
**Apply to:** the new per-connection thread target function -- same two-layer shape (inner `try/finally` for the fd, outer `except Exception` for anything else), just now inside a thread instead of the accept loop body.

### Read-only snapshot into plain dicts, off the Gtk thread (D-08 lineage)
**Source:** `write_dashboard()`, `claude-monitor.py:361-369`
**Apply to:** the query responder's snapshot-building code -- copy `self.sessions` values into plain dicts before sending, never hand out live `Monitor` state or mutate during snapshot.

### Inline comment convention for `ponytail:`-style rationale
**Source:** throughout `claude-monitor.py` (e.g. lines 348, 354, 401-406, 436-440)
**Apply to:** the new lock-acquisition sites and the thread-per-connection change -- a one-line comment explaining *why* the lock/thread exists at each site, consistent with the file's existing self-documentation style.

## No Analog Found

None -- every piece of this phase is an in-place extension of existing code in the same file; no new files or genuinely new subsystems are introduced.

## Metadata

**Analog search scope:** `claude-monitor.py` only (per CONTEXT's Integration Points: "No changes needed in `claude_monitor/core.py` or `claude_monitor/dashboard.py`")
**Files scanned:** 1 (`claude-monitor.py`, ~70 + ~220 lines read directly, sections 1-70 and 345-565)
**Pattern extraction date:** 2026-07-20
