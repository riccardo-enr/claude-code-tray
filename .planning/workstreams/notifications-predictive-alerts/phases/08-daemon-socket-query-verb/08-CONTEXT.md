# Phase 08: Daemon Socket Query Verb - Context

**Gathered:** 2026-07-20
**Status:** Ready for planning

<domain>
## Phase Boundary

The daemon's existing unix socket (`SOCK`) gains a read-only **query verb**:
a client sends `{"query": "snapshot"}` and gets back one JSON line containing
the live session table plus the latest polled usage/history state -- without
disrupting or blocking the existing fire-and-forget hook-event path
(SOCK-01..03). This is data-source-only groundwork for Phase 9's TUI; no
rendering happens here.

**In scope:** query message handling on the existing socket, a
threading.Lock around `self.sessions`, thread-per-connection so a stalled/
malformed connection can't block hook events, and the snapshot payload shape.
**Out of scope:** the TUI itself (Phase 9), any write/mutation verb, a second
socket, persisting query results, re-parsing history files on query (uses
already-cached `self.trends`/`self.usage`).

</domain>

<decisions>
## Implementation Decisions

### Thread-safety for `self.sessions` (SOCK-03)
- **D-01:** Add a `threading.Lock` guarding all `self.sessions` access -- both
  the existing Gtk-thread mutator (`handle()`, `_pop_stale()`) and the new
  query-path reader. Superseded an initial "reuse write_dashboard's
  accepted-risk posture" answer once thread-per-connection was decided
  (D-03): with a pool of concurrent query threads instead of one, a GIL-only
  argument is a weaker guarantee to reason about than an explicit lock, and
  SOCK-03's bar ("no torn/partial reads") is stricter than `write_dashboard`'s
  D-08 posture. `write_dashboard`'s own read (poll thread, off Gtk) and
  `reap_stale`'s read (poll thread) should also take the lock for consistency
  -- planner's call on exact scope of lock coverage, but `self.sessions`
  mutation/read call sites should end up consistently guarded.

### Connection handling model (SOCK-02)
- **D-02:** `serve()`'s current single-threaded `accept()` -> `recv()` loop
  has no socket timeout -- a stalled query connection (client connects, never
  sends) would hang `recv()` forever and block every subsequent hook event
  behind it in the OS accept backlog. This is a real gap in the existing loop,
  not just a Phase-8-specific risk.
- **D-03:** Fix: spawn a `threading.Thread` per accepted connection (query or
  hook event) instead of handling connections sequentially in the accept
  loop. A stalled/malformed connection then only blocks its own thread --
  zero stall for everything else, not just a bounded timeout. This is the
  mechanism that makes D-01's lock necessary (previously only the Gtk thread
  and one serial socket thread ever touched `self.sessions`; now multiple
  connection threads can read concurrently with the Gtk mutator).
- Existing per-connection `except Exception` + `conn.close()`-in-`finally`
  precedent (`claude-monitor.py:535-539`) carries over into each spawned
  thread's target function unchanged -- one bad connection still can't kill
  the accept loop or leak an fd.

### Query protocol / message shape
- **D-04:** Reuse the existing socket entirely -- no second socket file.
  A client sends the same newline-delimited JSON line shape hook events
  already use, but with `{"query": "snapshot"}` instead of an `"event"` key.
  `serve()`'s per-line dispatch checks for `"query"` vs `"event"` and routes
  accordingly (matches SOCK-01's wording: "the daemon's **existing** unix
  socket gains a read-only query verb").
- **D-05:** Response is one JSON line back over the same connection
  (`conn.sendall(...)`), then the connection closes -- a one-shot
  request/response, not a persistent RPC channel. No connection-lifecycle
  state to manage; matches the existing fire-and-forget shape of hook events
  (just with a reply). Phase 9's TUI polls on an interval anyway, so nothing
  needs a long-lived connection.

### Response payload scope
- **D-06:** Payload = `self.sessions` snapshot (dir/status/pane/tmux/entered,
  same shape `write_dashboard` already builds) + `self.usage` (already holds
  both 5h and 7-day fields in one dict -- there is no separate `self.usage7`
  attribute to include) + `self.trends` (cached sparkline/burn/peak-hour rows
  from the last `compute_trends` tick). All three are already-computed,
  in-memory values -- zero file I/O on the query path. No live re-read of
  `usage-history.jsonl`; the query always reflects "as of the last poll
  tick," which is what "last polled usage/history state" in the phase goal
  literally says.

### Claude's Discretion
- Exact snapshot dict field names/shape for the response JSON (planner
  should mirror `write_dashboard`'s existing sessions-snapshot shape at
  `claude-monitor.py:364-369` where reasonable).
- Whether the lock is a single `threading.Lock` or `RLock`, and exact
  granularity (whole-dict vs per-key) -- implementation detail, not a
  user-facing decision.
- Malformed query JSON / unknown query verb handling (e.g. respond with an
  error line, or silently drop like a malformed hook event today) -- follow
  the existing malformed-hook-event precedent (silent skip) unless the
  planner finds a reason to diverge.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope
- `.planning/workstreams/notifications-predictive-alerts/ROADMAP.md` -- Phase 8 section (goal + 4 success criteria)
- `.planning/workstreams/notifications-predictive-alerts/REQUIREMENTS.md` -- SOCK-01..03
- `.planning/workstreams/notifications-predictive-alerts/STATE.md` -- "Blockers/Concerns" v1.5-planning notes: the `serve()` per-connection guard precedent and the `self.sessions` single-mutator/torn-read framing that seeded this discussion

### Prior-phase precedent (same posture questions, prior answers)
- `.planning/workstreams/notifications-predictive-alerts/milestones/v1.4-phases/07-live-session-view/07-CONTEXT.md` -- D-08: the read-only-snapshot-into-plain-dicts pattern `write_dashboard` established; Phase 8 extends (not replaces) it with a lock given the new concurrent-reader shape

### Code being touched
- `claude-monitor.py:523-556` -- `serve()`: the accept/recv loop, per-connection `except Exception` + close-in-finally precedent
- `claude-monitor.py:60-65` -- `class Monitor.__init__`: `self.sessions`, `self.usage`, `self.trends` attribute definitions
- `claude-monitor.py:351-385` -- `write_dashboard()`: existing `self.sessions` snapshot-to-plain-dicts shape to mirror
- `claude-monitor.py:388-460` -- `handle()`, `reap_stale()`, `_pop_stale()`: all current `self.sessions` mutator/reader call sites that need lock coverage

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `write_dashboard`'s sessions-snapshot list comprehension
  (`claude-monitor.py:364-369`) -- the exact dict shape (`dir`, `status`,
  `entered`, `frozen`) to reuse/extend for the query response's sessions
  field.
- The existing per-connection `try/except Exception` + `conn.close()` in
  `finally` in `serve()` -- reuse this shape inside each spawned thread's
  target function.
- `self.usage` and `self.trends` -- already the exact "latest polled state"
  the tray menu and dashboard read; no new computation needed.

### Established Patterns
- **Read-only snapshot into plain dicts, off the Gtk thread** (D-08 from
  Phase 7): the query responder follows the same shape, now with an explicit
  lock instead of the accepted-risk posture, because thread-per-connection
  changes the reader-count assumption that posture relied on.
- **Broad `except Exception` per-connection, not around `accept()`**: `serve()`
  already isolates one bad connection from the whole loop; this phase's
  thread-per-connection change generalizes that isolation from "bad JSON"
  to "bad JSON OR a hang," since each connection now has its own thread.
- **`self.sessions` was single-mutator (Gtk thread only)** before this phase
  (per `reap_stale`'s own docstring, `claude-monitor.py:435-440`). This phase
  is the first to add concurrent *readers* from multiple threads -- the lock
  is new, not a pre-existing pattern being reused.

### Integration Points
- `serve()` -- gains per-line `"query"` vs `"event"` dispatch, and connection
  handling moves from sequential to thread-per-connection.
- `class Monitor` -- gains a `threading.Lock` instance attribute; `handle()`,
  `reap_stale()`/`_pop_stale()`, `write_dashboard()`, and the new query
  responder all acquire it around `self.sessions` access.
- No changes needed in `claude_monitor/core.py` or `claude_monitor/dashboard.py`
  -- this phase is entirely within `claude-monitor.py`'s socket/Monitor layer.

</code_context>

<specifics>
## Specific Ideas

No specific UI/format requirements from the user beyond the protocol/payload
decisions above -- Phase 9 (TUI rendering) is where presentation choices land.

</specifics>

<deferred>
## Deferred Ideas

None new -- discussion stayed within phase scope. (Prior deferred items from
REQUIREMENTS.md "Future Requirements" -- click-to-focus from the TUI,
standalone no-daemon mode -- remain deferred as already recorded there.)

</deferred>

---

*Phase: 08-daemon-socket-query-verb*
*Context gathered: 2026-07-20*
