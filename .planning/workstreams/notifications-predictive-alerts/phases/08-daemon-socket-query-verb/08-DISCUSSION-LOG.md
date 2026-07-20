# Phase 08: Daemon Socket Query Verb - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-20
**Phase:** 08-daemon-socket-query-verb
**Areas discussed:** Thread-safety for self.sessions read, Connection handling model, Query protocol / message shape, Response payload scope

---

## Thread-safety for self.sessions read

| Option | Description | Selected |
|--------|-------------|----------|
| Accept write_dashboard's posture | Snapshot self.sessions.values() directly off-thread into plain dicts, same as write_dashboard's D-08. GIL makes a single snapshot atomic in practice. Zero new code. | (initial pick) |
| Marshal through GLib.idle_add | Socket thread requests a snapshot via GLib.idle_add + threading.Event, blocks until the Gtk thread computes it. Strictly stronger, but adds a round-trip. | |

**User's choice:** Accept write_dashboard's posture (initially).

**Notes:** Revisited after the Connection handling model question below — see the follow-up entry.

### Follow-up: does the answer still hold given thread-per-connection?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, still holds | Each dict mutation is still a single GIL-protected op; multiple simultaneous readers are fine without a lock. | |
| No, add a lock now | Given multiple concurrent query threads, add a threading.Lock around self.sessions access (mutator + query readers). | ✓ |

**User's choice:** No, add a lock now.
**Notes:** Superseded the initial "accept the existing posture" answer — final decision (D-01 in CONTEXT.md) is a `threading.Lock`.

---

## Connection handling model

| Option | Description | Selected |
|--------|-------------|----------|
| Per-connection socket timeout | conn.settimeout(N) after accept(); a stalled connection's recv() raises after N seconds instead of hanging forever. One-line change. | |
| Thread per connection | Spawn a threading.Thread per accepted connection; a stalled one only blocks its own thread, zero stall for everything else. More moving parts. | ✓ |

**User's choice:** Thread per connection.
**Notes:** This choice is what made the self.sessions thread-safety follow-up necessary — multiple concurrent query threads can now read while the Gtk thread mutates, not just one serial socket thread.

---

## Query protocol / message shape

### Request shape

| Option | Description | Selected |
|--------|-------------|----------|
| New message shape on same socket | Reuse SOCK entirely: client sends {"query": "snapshot"} as a newline-delimited JSON line, same as hook events but without an "event" key. | ✓ |
| Separate query socket path | A second unix socket file dedicated to queries, fully isolated at the OS level. Two sockets to create/clean up/document. | |

**User's choice:** New message shape on same socket.

### Response shape

| Option | Description | Selected |
|--------|-------------|----------|
| One JSON line back, then close | conn.sendall(json line), then close — one-shot request/response, mirrors the request shape. | ✓ |
| Keep connection open for multiple queries | Persistent RPC-style channel; adds connection-lifecycle complexity for no stated requirement. | |

**User's choice:** One JSON line back, then close.

---

## Response payload scope

| Option | Description | Selected |
|--------|-------------|----------|
| self.usage + self.trends + sessions | Already-computed, in-memory values from the last poll tick. Zero file I/O. self.usage already holds both 5h and 7-day fields (no separate self.usage7). | ✓ |
| Re-read history file live on query | Query handler re-parses usage-history.jsonl itself for freshest-possible trend data. Adds file I/O to the query path, duplicates compute_trends logic. | |

**User's choice:** self.usage + self.trends + sessions.

---

## Claude's Discretion

- Exact snapshot dict field names/shape for the response JSON (mirror `write_dashboard`'s existing shape at `claude-monitor.py:364-369` where reasonable).
- Whether the lock is a `threading.Lock` or `RLock`, and exact granularity.
- Malformed query JSON / unknown query verb handling — follow the existing malformed-hook-event precedent (silent skip) unless the planner finds a reason to diverge.

## Deferred Ideas

None new — discussion stayed within phase scope.
