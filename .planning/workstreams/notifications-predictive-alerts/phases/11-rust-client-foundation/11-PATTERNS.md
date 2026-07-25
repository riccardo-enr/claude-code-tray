# Phase 11: Rust Client Foundation - Pattern Map

**Mapped:** 2026-07-25
**Files analyzed:** 12 likely new files/file groups
**Analogs found:** 9 / 12

## Scope Notes

- `11-CONTEXT.md` and `11-UI-SPEC.md` name behavior, not Rust paths. The table
  below uses a minimal root crate layout; the planner may rename modules while
  preserving the assignments.
- No `RESEARCH.md`, Cargo project, Rust source, or repository-local
  `AGENTS.md`/skill directory exists. Rust syntax, dependencies, and workspace
  structure therefore have no in-repository analog.
- Phase 11 is library/foundation work only. Do not add `src/main.rs`, a widget,
  an event loop, installation changes, or edits to the Python daemon/oracle.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `Cargo.toml` | config | batch | `pyproject.toml` | role-match |
| `src/lib.rs` | provider | request-response + transform | `claude_monitor/core.py` | role-match |
| `src/client.rs` | service | request-response + streaming | `claude_monitor/core.py:797-891` | exact behavioral analog |
| `src/error.rs` | model | transform | `claude-tui.py:163-252` | partial; Python has boundaries but not typed codes |
| `src/model.rs` | model | transform | `claude-monitor.py:596-608`, `claude_monitor/core.py:166-185` | exact wire-shape analog |
| `src/normalize.rs` | service | transform | `claude_monitor/core.py:48-66`, `268-309`, `394-410` | role/data-flow match |
| `src/sanitize.rs` | utility | transform | `claude_monitor/core.py:1020-1030` | role-match; Rust contract is stronger |
| `fixtures/protocol/manifest.json` | config | file-I/O + batch | `claude_monitor/test_claude_monitor.py` assertion matrix | partial |
| `fixtures/protocol/input/*.{wire,bin}` | test fixture | file-I/O | none | no analog |
| `fixtures/protocol/expected/*.json` | test fixture | file-I/O + transform | `claude_monitor/test_claude_monitor.py:691-831`, `950-984` | partial |
| `tests/fixture_corpus.rs` | test | file-I/O + batch + transform | `claude_monitor/test_claude_monitor.py` | role-match |
| `tests/socket_client.rs` | test | request-response + streaming | `claude_monitor/test_claude_monitor.py:691-831` | exact behavioral analog |

## Pattern Assignments

### `Cargo.toml` and `src/lib.rs`

**Analogs:** `pyproject.toml:1-7`, `claude_monitor/core.py:1-6`,
`claude-tui.py:17-25`

Keep the foundation independently importable/testable and keep UI dependencies
out of it. The Python package records the same boundary:

```python
# claude_monitor/core.py:2-6
"""Pure usage/config/history logic for the Claude Code tray monitor.

Stdlib only -- no gi/GTK -- so this module imports fast and is exercised end to end
by ``python3 claude-monitor.py --selfcheck`` ...
"""
```

```python
# claude-tui.py:17-25
anything worth asserting belongs in
claude_monitor.core, where --selfcheck can prove it. What is left here is layout, CSS,
two timers, two thread workers and the degraded-mode presentation
...
Snapshot reads go through
core.query_snapshot and session activation goes through core.request_focus
```

Assignment:

- Make `src/lib.rs` the public non-UI boundary and export the client, normalized
  model, failure-code, and focus-result types needed by Phases 12-13.
- Keep terminal renderer dependencies out of `Cargo.toml` in Phase 11.
- Do not copy Python dependency choices. Select Rust dependencies in the plan
  because the repository contains no Rust precedent.

---

### `src/client.rs` (service, request-response + streaming)

**Primary analog:** `claude_monitor/core.py:797-891`

**Constants and socket location** (`core.py:797-805`):

```python
SOCK_PATH = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "claude-monitor.sock")
TUI_FETCH_INTERVAL = 2.0
TUI_TICK_INTERVAL = 1.0
TUI_SOCK_TIMEOUT = 1.5
```

Phase 11 only owns the socket path and operation deadline. Refresh/tick cadence
remains Phase 13.

**Bounded whole-read pattern** (`core.py:809-835`):

```python
def read_line(sock, deadline=None, max_bytes=1 << 20):
    buf = b""
    while not buf.endswith(b"\n"):
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError(...)
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
        if len(buf) > max_bytes:
            raise ValueError(...)
    return buf.decode("utf-8", "replace")
```

Copy the whole-operation monotonic deadline, 64 KiB chunking precedent, and
1 MiB cap. Intentionally change EOF-without-newline and lossy UTF-8 behavior to
the Phase 11 contract: invalid framing is `snapshot.framing`; invalid UTF-8 is
`snapshot.decode`.

**One-shot snapshot request** (`core.py:852-866`):

```python
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(timeout)
try:
    s.connect(path)
    s.sendall(b'{"query": "snapshot"}\n')
    obj = json.loads(read_line(s, time.monotonic() + timeout))
    if not isinstance(obj, dict):
        raise ValueError(...)
    return obj
finally:
    s.close()
```

Preserve exact request semantics and close the connection on every result.
Return `Result<NormalizedSnapshot, SnapshotFailure>`; do not accept or mutate a
last-good snapshot.

**Focus request shape and validation** (`core.py:869-891`):

```python
target = {
    "pane": session.get("pane", ""),
    "tmux": session.get("tmux", ""),
    "title": session.get("dir", ""),
    "term": session.get("term", ""),
}
if not all(isinstance(value, str) for value in target.values()):
    raise ValueError(...)
if not target["pane"] and target["term"] != "zed":
    raise ValueError(...)
message = {"action": "focus", **target}
```

Copy the field names and focusability rule exactly. Validate opaque routing
values before opening the socket, enforce 4096 bytes per field, and return an
action-scoped focus result. Do not derive routing values from sanitized or
truncated display text.

**Daemon confirmation** (`claude-monitor.py:596-620`):

```python
if msg.get("query") == "snapshot":
    snapshot = {
        "heatmap": mon.heatmap,
        "sessions": sessions,
        "usage": mon.usage,
        "trends": mon.trends,
    }
    conn.sendall((json.dumps(snapshot) + "\n").encode("utf-8"))
...
if msg.get("action") == "focus":
    target = [
        msg.get("pane", ""),
        msg.get("tmux", ""),
        msg.get("title", ""),
        msg.get("term", ""),
    ]
```

---

### `src/model.rs` (model, transform)

**Analogs:** `claude-monitor.py:602-608`,
`claude_monitor/core.py:166-185`

**Top-level slots**:

```python
# claude-monitor.py:602-608
snapshot = {
    "heatmap": mon.heatmap,
    "sessions": sessions,
    "usage": mon.usage,
    "trends": mon.trends,
}
conn.sendall((json.dumps(snapshot) + "\n").encode("utf-8"))
```

Model all four slots unconditionally as independent
`Available(value) | Unavailable(section.schema)` states. `None`/empty is a
semantic value only where the daemon contract allows it; it must not double as
schema failure.

**Session wire fields and order** (`core.py:166-185`):

```python
return [
    {
        "id": s.get("id", ""),
        "dir": s.get("dir", ""),
        "status": s.get("status", ""),
        "entered": s.get("entered"),
        "frozen": None if s.get("status") == "running" else s.get("run_dur"),
        "pane": s.get("pane", ""),
        "tmux": s.get("tmux", ""),
        "term": s.get("term", ""),
    }
    for s in sessions
]
```

Use distinct fields/types for:

- safe bounded display values;
- opaque focus-routing values;
- ordered valid sessions;
- deterministic `rejected_entry_count`;
- optional versus required values;
- stable semantic failure codes and finite allowlisted context.

Do not embed renderer wording, colors, styles, raw payloads, OS errors, or debug
chains in the public model.

---

### `src/normalize.rs` (service, transform)

**Primary analog:** `claude_monitor/core.py`

**Independent field fallback** (`core.py:48-66`):

```python
try:
    raw = json.loads(text)
except Exception:
    return dict(DEFAULT_CONFIG)
if not isinstance(raw, dict):
    return dict(DEFAULT_CONFIG)
cfg = dict(DEFAULT_CONFIG)
for key in (...):
    if isinstance(raw.get(key), bool):
        cfg[key] = raw[key]
```

Use the narrow-containment shape, not its fallback values: root/framing/decode
failures reject the fetch; after an object root is accepted, normalize each
snapshot section independently.

**Required core with optional sibling degradation** (`core.py:268-309`):

```python
try:
    five = doc["limits"]["five_hour"]
    ...
    seven = doc["limits"].get("seven_day")
    if not isinstance(seven, dict):
        seven = {}
    u = {...}
except Exception:
    return None
...
for k in ("seven_day_pct", "seven_day_reset"):
    if not is_num(u[k]):
        u[k] = None
```

Derive the actual required/optional field table from the shipped daemon shape.
Do not copy Python truthiness, coercion, or blanket `except`; distinguish absent
from wrong type and reject the narrowest owning section/session entry.

**Preserve valid entries in input order** (`core.py:394-410`):

```python
out = []
for line in text.splitlines():
    ...
    try:
        rec = json.loads(line)
    except Exception:
        continue
    if isinstance(rec, dict) and isinstance(rec.get("t"), (int, float)):
        out.append(rec)
return out
```

Apply this skip-and-preserve-order shape to `sessions`, incrementing
`rejected_entry_count` for each rejected element. Unknown fields are ignored;
numeric strings and arbitrary values are never coerced.

Normalization must be a pure function of response bytes plus an injected/frozen
clock. It returns a new accepted snapshot or one failure and never mutates prior
state.

---

### `src/sanitize.rs` (utility, transform)

**Analogs:** `claude_monitor/core.py:1020-1030`,
`claude-tui.py:423-438`

**Trust-boundary precedent**:

```python
# core.py:1020-1030
def _safe_cell(s):
    """Strip C0/C1 control characters from an arbitrary filesystem path. Pure."""
    return "".join(c if c.isprintable() or c == " " else "?" for c in s)
```

The Rust implementation must strengthen this analog:

- collapse each complete CSI, OSC (BEL or ST terminated), ESC, or C1 sequence to
  one `U+FFFD`;
- collapse a lone/incomplete escape sequence to one `U+FFFD`;
- replace each remaining C0/C1 control with one `U+FFFD`;
- preserve printable Unicode and printable markup-like text literally;
- cap display strings at 256 Unicode scalar values as 255 scalars plus `…`.

**Defense-in-depth renderer precedent** (`claude-tui.py:423-438`):

```python
table.add_row(
    Text(status, style=status_style),
    Text(proj, style=status_style),
    Text(elapsed, style=status_style),
    key=row_key,
)
```

Phase 12 must still use non-markup/plain text APIs. Sanitization must not strip
printable brackets to compensate for an unsafe renderer.

---

### `src/error.rs` (model, transform)

**Boundary analogs:** `claude_monitor/core.py:838-866`,
`claude-tui.py:163-191`, `244-252`

The current client deliberately propagates low-level failures:

```python
# core.py:841-846
RAISES on every failure mode -- FileNotFoundError (...),
ConnectionRefusedError (...), socket.timeout (...),
json.JSONDecodeError (...).
...
The swallowing belongs at that boundary.
```

The application boundary keeps snapshot and focus failures separate:

```python
# claude-tui.py:179-191
try:
    snap = core.query_snapshot()
    self.call_from_thread(self.apply_snapshot, snap)
except Exception:
    self.call_from_thread(self.mark_stale)

try:
    core.request_focus(session)
except Exception:
    return
```

Preserve that separation, but replace raw exception classes/strings with the
fixed serialized codes from `11-UI-SPEC.md`:

`snapshot.transport`, `snapshot.timeout`, `snapshot.framing`,
`snapshot.too_large`, `snapshot.decode`, `snapshot.root_schema`,
`section.schema`, `render.failed`, `focus.invalid_target`,
`focus.transport`, and `focus.timeout`.

Context must be typed and allowlisted (operation, deadline/cap, framing reason,
JSON kind/offset, section/field path). Never store raw payloads, paths, routing
values, session titles, terminal controls, or source/debug chains. No `unwrap`,
`expect`, indexing, or panic may be reachable from untrusted wire input.

---

### `fixtures/protocol/*` and `tests/fixture_corpus.rs`

**Primary analog:** `claude_monitor/test_claude_monitor.py`

The existing suite uses deterministic table-like inputs and exact semantic
assertions:

```python
# test_claude_monitor.py:94-99
u = parse_usage(json.dumps(sample))
assert u is not None and u["used_percentage"] == 473.5
assert parse_usage("") is None
assert parse_usage("not json") is None
assert parse_usage(json.dumps({"limits": {}})) is None
```

```python
# test_claude_monitor.py:950-969
assert sess_rows([], _unow) == [("", "No active Claude Code sessions", "")]
assert _safe_cell("[bold]myrepo[/]") == "[bold]myrepo[/]"
assert _safe_cell("A\x1b[2JB") == "A?[2JB"
...
assert sess_rows(_srows_in, _unow) == [
    ("waiting", "wait-proj", "1m 14s"),
    ("running", _hostile, "2m 14s"),
    ("done", "done-proj", "1h 22m"),
    ("zombie", "odd-proj", "-"),
]
```

Use a language-neutral manifest whose cases point to raw input bytes and
expected semantic JSON. Keep inputs in separate `.wire`/`.bin` files so invalid
UTF-8, truncation, and the exact 1 MiB boundary are testable without JSON string
escaping or lossy decoding. Expected files assert only normalized values,
availability, rejected counts, safe strings, request bytes, and stable codes.

The manifest must cover every row in the UI-SPEC fixture matrix, including
zero/one/many sessions and `render.failed`. Tests use a frozen clock and must
not depend on a daemon, machine paths, private usage, live timestamps, map
iteration order, debug wording, or enum `Debug` output.

---

### `tests/socket_client.rs` (test, request-response + streaming)

**Primary analog:** `claude_monitor/test_claude_monitor.py:691-831`

**Real socket pair, exact request, split delivery, EOF, and focus shape**:

```python
_server_sock, _client_sock = socket.socketpair()
_thread = threading.Thread(target=_daemon._handle_conn, args=(_mon, _server_sock))
_thread.start()
_client_sock.sendall(b'{"query": "snapshot"}\n')
...
assert set(_snapshot.keys()) == {"heatmap", "sessions", "usage", "trends"}
```

```python
def _split_writer():
    _split_b.sendall(b'{"part": ')
    time.sleep(0.05)
    _split_b.sendall(b"1}\n")

assert read_line(_split_a) == '{"part": 1}\n'
```

```python
assert _received == [{
    "action": "focus",
    "pane": "%3",
    "tmux": "/tmp/tmux",
    "title": "proj",
    "term": "ghostty",
}]
```

Copy the socket-pair strategy so protocol tests do not need the daemon. Extend
it for whole-operation timeout, missing newline, extra framed content, exact
cap/over-cap behavior, invalid UTF-8, connection/send/receive failures, and
proof that invalid focus targets send no bytes/open no connection.

## Shared Patterns

### Pure core, thin boundary

**Source:** `claude_monitor/core.py:788-795`,
`claude-tui.py:17-25`

Apply to `model.rs`, `normalize.rs`, `sanitize.rs`, and fixture tests. Socket I/O
ends at `client.rs`; normalized state contains no socket handles, UI framework
types, styling, or mutable last-good state.

### Exact one-shot protocol

**Source:** `claude_monitor/core.py:852-891`,
`claude-monitor.py:596-620`

Snapshot sends exactly one newline-delimited `{"query":"snapshot"}` object and
reads exactly one framed object. Focus sends the existing `action`, `pane`,
`tmux`, `title`, and `term` fields. Do not add negotiation, acknowledgements,
verbs, or daemon edits.

### Narrow failure containment

**Source:** `claude_monitor/core.py:48-66`, `268-309`, `394-410`

Reject wire/root failures wholesale; after root acceptance, isolate section
failures; inside sessions, isolate entries while preserving valid daemon order.
No accepted data from a failed fetch is merged with earlier state.

### Last-good and action isolation

**Source:** `claude-tui.py:179-240`

The current UI replaces `snapshot` only after a successful fetch and handles
focus in a separate worker. Phase 11 should make this easier to preserve by
returning failures separately and exposing no API that mutates last-good state.
A focus failure never affects snapshot freshness.

### Untrusted text

**Source:** `claude_monitor/core.py:1020-1030`,
`claude-tui.py:423-438`

Sanitize display text at normalization, retain routing values separately, and
still require plain/non-markup renderer APIs.

### Deterministic verification

**Source:** `claude_monitor/test_claude_monitor.py:691-831`, `950-984`

Favor pure exact-value assertions and Unix socket pairs. Freeze time and inspect
semantic state/request bytes, never human wording or live daemon output.

## No Direct Analog Found

| File/Concern | Role | Data Flow | Planner Guidance |
|---|---|---|---|
| `Cargo.toml` dependency choices and Rust module wiring | config/provider | batch | Use Rust official/library research; repository only supplies the pure-core boundary, not Rust syntax. |
| `src/error.rs` typed stable code model | model | transform | Python uses broad exception boundaries. Implement the UI-SPEC code/context allowlist directly rather than copying exception strings. |
| Complete terminal-sequence parser in `src/sanitize.rs` | utility | transform | `_safe_cell` only replaces individual controls. Implement CSI/OSC/ESC/C1 sequence recognition and exact marker cardinality from UI-SPEC fixtures. |
| `fixtures/protocol/input/*.{wire,bin}` corpus format | test fixture | file-I/O | No fixture corpus exists. Keep raw bytes separate from semantic JSON expectations, especially for invalid UTF-8 and oversized inputs. |

## Metadata

**Analog search scope:** repository root Python package/entry points, phase
context/UI contract, roadmap, requirements, and project architecture

**Primary analog files read:** 5 (`claude_monitor/core.py`,
`claude-monitor.py`, `claude-tui.py`,
`claude_monitor/test_claude_monitor.py`, `claude_monitor/test_tui.py`)

**Additional config files read:** `pyproject.toml`, `justfile`,
`claude_monitor/__init__.py`

**Pattern extraction date:** 2026-07-25
