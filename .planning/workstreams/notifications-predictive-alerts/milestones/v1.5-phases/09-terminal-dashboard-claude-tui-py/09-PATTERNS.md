# Phase 9: Terminal Dashboard (claude-tui.py) - Pattern Map

**Mapped:** 2026-07-21
**Files analyzed:** 6 (1 new, 5 modified)
**Analogs found:** 6 / 6

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `claude-tui.py` (NEW) | entry script / renderer | request-response (poll socket) + timer-driven render | `claude_monitor/dashboard.py` (second surface over core's data) + `claude-send.py` (root entry script, socket client) | role-match (no textual precedent exists) |
| `claude_monitor/core.py` (MOD) | utility / pure helpers | transform | itself: `build_session_snapshot` (:153-172), `build_trend_rows` (:489-511), `fmt_*` (:309-334) | exact |
| `claude_monitor/test_claude_monitor.py` (MOD) | test | batch asserts | itself: `build_session_snapshot` block (:462-480), socket wire block (:599-638) | exact |
| `pyproject.toml` (MOD) | config | -- | itself (`[project]`, `[tool.pyright]`, `[tool.ruff...]` with per-key rationale comments) | exact |
| `install.sh` (MOD) | config / install | file-I/O | `install.sh:11-13` (`ln -sf` block) | exact |
| `justfile` (MOD) | config / task runner | -- | `justfile:44-46` (`dashboard` recipe) | exact |

Note: the sessions-panel logic being lifted lives in **JavaScript** inside
`dashboard.py:468-518` (the `_DASH_JS` string). It is a semantics analog, not a Python
one -- the new pure helpers translate it to Python and land in `core.py`.

## Pattern Assignments

### `claude-tui.py` (NEW -- entry script, request-response)

**Analogs:** `claude-send.py` (whole file, 41 lines -- root entry script + AF_UNIX client),
`claude_monitor/dashboard.py:1-6` (module docstring posture for a second render surface).

**Module docstring pattern** (`dashboard.py:1-6`) -- state the no-`gi` boundary and the
`--selfcheck` relationship explicitly:
```python
#!/usr/bin/env python3
"""Self-contained usage-dashboard renderer (inline CSS/JS/SVG, no CDN/deps).

No gi/GTK: pulls its pure inputs from core and returns an HTML string that
claude-monitor.py atomic-writes to DASH_PATH. Exercised by --selfcheck.
"""
```
For `claude-tui.py` the inverse must be stated: *this is the only file that imports
textual; nothing importable by `/usr/bin/python3` may import it.*

**Socket-path + client pattern** (`claude-send.py:17,34-41`) -- the existing client is
the shape to copy, including `XDG_RUNTIME_DIR` fallback and `settimeout` before `connect`:
```python
sock = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "claude-monitor.sock")
...
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(0.5)
    s.connect(sock)
    s.sendall((json.dumps(msg) + "\n").encode())
    s.close()
except Exception:
    pass
```
Deltas for the TUI's `query_snapshot`: `settimeout(1.5)` (Pitfall 2), a `finally: s.close()`
(claude-send.py leaks the fd on a mid-send raise; do not copy that), and it must **raise**
rather than swallow -- the swallowing belongs one level up in the worker (see next pattern).

**Blanket-except-at-the-loop-boundary pattern** (`claude-monitor.py:610-613`, also
`compute_trends` at `:363-367`) -- the house posture the fetch worker inherits:
```python
    except Exception:
        traceback.print_exc()  # loud and repeated; the thread survives regardless
    finally:
        conn.close()  # whole body's finally: a response must send before close (D-05)
```
The TUI variant must NOT `traceback.print_exc()` (it would corrupt the terminal under
textual) -- convert to `mark_stale()` instead. `compute_trends` is the closer analog for
that "swallow and keep last-known state" behaviour:
```python
        except OSError:
            return  # keep last-known trends; never crash the poll thread
```

**`ponytail:` comment pattern for a deliberate shortcut** (`core.py:229`, `claude-monitor.py:368`,
`dashboard.py:30-31`) -- name the ceiling and the upgrade path:
```python
        # ponytail: single list rebind, read-only in the Gtk redraw -- no lock.
```

---

### `claude_monitor/core.py` (MOD -- pure helpers: `sess_rank`, `sess_elapsed`, `fmt_elapsed`, `trend_text`, `query_snapshot`)

**Analog:** `core.py` itself. Every new function must match these three properties of the
existing ones: (1) docstring says "Pure.", (2) `None`/degenerate inputs are handled inline
with the reason stated, (3) no `gi`, no `textual`, no file I/O.

**Pure-transform docstring + total-function pattern** (`core.py:153-172`):
```python
def build_session_snapshot(sessions):
    """Snapshot a list of session dicts into plain, JSON-serializable primitives. Pure.
    ...this function does no locking, no I/O, and never mutates its input...
    """
    return [
        {
            "dir": s.get("dir", ""),
            "status": s.get("status", ""),
            "entered": s.get("entered"),
            "frozen": None if s.get("status") == "running" else s.get("run_dur"),
```
Note `s.get(key, default)` everywhere -- never `s[key]`. The new `sess_rank` / `sess_elapsed`
copy this defensive-read discipline verbatim.

**Formatter pattern** (`core.py:309-333`) -- the exact shape `fmt_elapsed` must match
(short docstring with a worked example, `%`-formatting, clamp at the top):
```python
def fmt_countdown(secs):
    """Reset countdown: 7380 -> 'resets in 2h 3m'; <= 0 -> 'resets now'."""
    secs = max(0, int(secs))
    if secs <= 0:
        return "resets now"
    return "resets in %dh %dm" % (secs // 3600, (secs % 3600) // 60)
```
`fmt_elapsed` translates `dashboard.py:471-477` (`sessDur`) into this style:
```javascript
function sessDur(s){
  // Under an hour show m+s so the counter visibly ticks each second (D-02); past an
  // hour fall to the coarser fmtDur -- a stale session does not need second precision.
  s=Math.max(0,Math.floor(s));
  if(s>=3600)return fmtDur(s);
  return Math.floor(s/60)+"m "+two(s%60)+"s";
}
```

**Row-builder pattern for `usage`'s three `None` cases** -- `Monitor.usage_rows`
(`claude-monitor.py:316-339`) is the reference rendering the TUI must not diverge from:
```python
    def usage_rows(self):
        """Menu-row strings from self.usage: 'unavailable', else used/countdown/burn."""
        u = self.usage
        if u is None:
            return ["usage unavailable"]
        # --api carries no token counts -> "% used"; the P90 path has them -> "72k / 88k".
        if u["tokens_used"] is not None and u["token_limit"] is not None:
            used = "%s / %s (%d%%)" % (...)
        else:
            used = "%d%% used" % round(u["used_percentage"])
        rows = [used, core.fmt_countdown(...), "burn: %s tok/hr" % ...]
        if u.get("seven_day_pct") is not None:
            rows.append("week: %d%% used" % round(u["seven_day_pct"]))
            if u.get("seven_day_reset") is not None:
                rows.append(core.fmt_countdown_wk(u["seven_day_reset"] - time.time()))
        return rows
```
This is a `Monitor` method (gi-bound file) and is therefore **not importable** by the TUI.
The lazy move: lift it to a pure `core.usage_rows(usage, now)` and have `Monitor.usage_rows`
call it -- one function, two surfaces, guaranteed agreement. Same argument D-05 makes for
trends. If the planner does not lift it, it is duplicated logic that will drift.

**Collecting-state string** (`claude-monitor.py:341-345`) -- `trend_text` reuses it verbatim
per D-07, and the same lift-to-core argument applies:
```python
    def trend_rows(self):
        """Trend rows from the self.trends cache (no file I/O), or the collecting row."""
        if self.trends is None:
            return ["trends: collecting history..."]
        return self.trends
```

**Sort-rank source of truth** (`dashboard.py:470,483-487`) -- what `sess_rank` mirrors:
```javascript
var SESS_RANK={waiting:0,running:1,done:2};
  list.sort(function(a,b){
    var ra=SESS_RANK[a.status];if(ra===undefined)ra=99;
```

---

### `claude_monitor/test_claude_monitor.py` (MOD -- assert suite)

**Analog:** its own `build_session_snapshot` block (`:462-480`) and socket block (`:599-638`).

**Import pattern** (`:16-54`): one alphabetized `from .core import (...)` tuple. New helpers
get appended into that same sorted list. **Never** import textual here (`justfile:38` runs this
on `/usr/bin/python3`).

**Section-header + assert-block pattern** (`:462-480`) -- a `# --- name (REQ-ID) ---` banner,
literal expected values, then explicit purity/idempotency asserts:
```python
    # --- build_session_snapshot (SOCK-01 shape groundwork, SOCK-03 idempotency) ---
    _snap_in = [
        {"dir": "proj-a", "status": "running", "entered": 100.0, "pane": "%1", "tmux": "/tmp/x"},
        {"dir": "proj-b", "status": "done", "entered": 90.0, "run_dur": 12.5},
    ]
    _snap_out = build_session_snapshot(_snap_in)
    assert _snap_out == [...]
    assert build_session_snapshot([]) == []
    # purity: calling twice yields independent lists, input untouched.
    assert build_session_snapshot(_snap_in) == _snap_out
    assert build_session_snapshot(_snap_in) is not build_session_snapshot(_snap_in)
```

**Underscore-prefixed locals**: everything in the newer blocks uses `_name` (`_snap_in`,
`_mon`, `_resp`) to avoid collision inside the one long `demo()` body. Follow it.

**Stub-server harness for `query_snapshot`** (`:599-634`) -- the existing socket test already
builds both ends; the client test reuses it from the other side:
```python
    class _FakeMonitor:
        def __init__(self):
            self.sessions = {...}
            self.sessions_lock = threading.Lock()
            self.usage = {"used_percentage": 42}
            self.trends = ["line1"]

    _mon = _FakeMonitor()
    _server_sock, _client_sock = socket.socketpair()
    _client_sock.settimeout(5)
    _thread = threading.Thread(target=_daemon._handle_conn, args=(_mon, _server_sock), daemon=True)
    _thread.start()
    _client_sock.sendall(b'{"query": "snapshot"}\n')
```
`socket.socketpair()` here means `query_snapshot` cannot be tested through it as-is (it does
its own `connect(path)`). Two options, planner's call: (a) factor `query_snapshot` into
`_read_line(sock)` + a thin `connect` wrapper and assert on `_read_line` against the pair, or
(b) bind a real `AF_UNIX` listener on a tmpdir path. (a) is the smaller diff and needs no
filesystem.

**Deferred-note pattern** (`:635-638`) -- this phase is explicitly named in an existing
comment; if the TUI still does not need `term`, leave the assert and the note alone:
```python
    # IN-02, deferred: the wire shape carries no `term` key yet ... -- add it when a query-side
    # consumer (e.g. Phase 9's TUI) actually needs to tell a Zed session from a tmux one.
    assert "term" not in _snapshot["sessions"][0]
```

---

### `pyproject.toml` (MOD)

**Analog:** itself. Every non-obvious key carries a multi-line `#` rationale. A bare
`optional-dependencies` line with no comment would be the odd one out.

**Existing shape to extend** (`:1-6`, `:32-37`):
```toml
[project]
requires-python = ">=3.11"
dependencies = []

[tool.ruff.lint.per-file-ignores]
# gi.repository imports MUST follow gi.require_version(); the lambda/one-liner are deliberate.
"claude-monitor.py" = ["E402", "E731", "E701"]
```
`dependencies = []` is load-bearing prose ("stdlib+PyGObject only") -- keep it empty and add
`[project.optional-dependencies] tui = ["textual>=8,<9"]` with a comment saying runtime
resolution comes from the PEP 723 block and this entry exists for basedpyright + `uv sync --extra tui`.

`[tool.pyright] extraPaths = ["."]` (`:17-21`) already covers `claude-tui.py`'s
`import claude_monitor` -- no change needed there. A `per-file-ignores` entry for
`claude-tui.py` follows the existing pattern if the PEP 723 header trips E265/E402.

---

### `install.sh` (MOD)

**Analog:** `install.sh:11-13`.
```bash
mkdir -p "$HOOKS" "$AUTOSTART"
ln -sf "$SRC/claude-monitor.py" "$HOOKS/claude-monitor.py"
ln -sf "$SRC/claude-send.py"    "$HOOKS/claude-send.py"
```
Plus the echo-back block (`:26-29`) -- every installed path is echoed. A `claude-tui` symlink
must appear in both places. Script runs under `set -euo pipefail` (`:5`), so a guarded target
needs an explicit `|| true` or an `if [ -d ... ]` wrapper (Research Open Question 1).

---

### `justfile` (MOD)

**Analog:** `justfile:44-46`.
```make
# Open the generated dashboard in the browser.
dashboard:
    xdg-open "{{dash}}"
```
Every recipe has a one-line `#` doc comment above it (it renders in `just --list`). The `just tui`
recipe must run the repo copy attached to the terminal -- no `@` prefix games that redirect
(Research Pitfall 6). Do **not** touch `restart`/`start`/`selfcheck`: they hardcode
`/usr/bin/python3` (`:19,24,38`), the interpreter that must never have textual.

## Shared Patterns

### Untrusted-`dir` escaping (applies to: sessions rendering in `claude-tui.py`)
**Source:** `dashboard.py:468-469` + its assert at `test_claude_monitor.py:443-457`
```javascript
// Sessions panel. Rows are built client-side via textContent from D.sessions so an
// untrusted project dir (arbitrary repo path) can never inject markup (D-08, T-07-01).
```
The TUI's equivalent of `textContent` is `rich.text.Text(...)` for `DataTable` cells and
`markup=False` for `Static`. The test-side equivalent already exists:
```python
    hostile_dir = "<b>x</b>"  # planner-discipline-allow: <b>x</b>
    ...
    assert hostile_dir not in spage  # escaped -> no raw markup, no server-side interp
```
A `[bold]x` variant of `hostile_dir` asserted against the pure row-builder is the direct
translation. Note the `# planner-discipline-allow:` marker convention on the literal.

### Never-crash-the-loop (applies to: fetch worker, render tick)
**Source:** `claude-monitor.py:610-613` (`_handle_conn`), `:363-367` (`compute_trends`)
Broad `except Exception` at every thread/timer boundary; a failure is a state change, never a
raised traceback. See excerpts above.

### Constants with inline rationale (applies to: `FETCH_INTERVAL`, `TICK_INTERVAL`, `SOCK_TIMEOUT`)
**Source:** `dashboard.py:29-32`, `core.py:174-177`, `claude-monitor.py:347`
```python
DASH_INTERVAL = 5 * 60  # dashboard-regen throttle in poll_loop (seconds)
```
```python
WIN5 = 18000  # 5 hours
ALERT_LEAD = 15 * 60  # an exhaust nearer than this is not actionable -> no alert
```
```python
    USAGE_MISS_LIMIT = 2  # failed polls tolerated before showing "unavailable"
```
`SOCK_TIMEOUT = 1.5` in particular needs the "< FETCH_INTERVAL so at most one fetch is ever in
flight" reason on the same line.

### Duplicate-logic warning (applies to: any computation `claude-tui.py` is tempted to add)
**Source:** `core.py:183-185`, `:174`
```python
    The JS copy in _DASH_JS is a deliberate duplicate (it recomputes against a live
    browser clock as the static page ages); change both.
```
```python
# Quota-window lengths (seconds). The dashboard JS carries the same literals; move both.
```
The codebase already carries two "change both" markers and treats them as debt. The TUI is the
third surface: prefer lifting to `core.py` over a third copy, and if a duplicate is unavoidable,
carry the same explicit marker.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `claude-tui.py` textual layer specifically (App class, CSS, `@work`/`set_interval` wiring, widget composition) | component | event-driven | No textual and no async/event-loop UI code exists in this repo; the tray is GTK/GLib. Use RESEARCH.md Patterns 1-6 for this layer. The repo analogs above cover the entry-script skeleton, socket client, docstring posture, and error posture only |

## Metadata

**Analog search scope:** repo root (`claude-monitor.py`, `claude-send.py`, `install.sh`,
`justfile`, `pyproject.toml`), `claude_monitor/` (`core.py`, `dashboard.py`,
`test_claude_monitor.py`)
**Files scanned:** 8 (the repo's entire Python surface)
**Pattern extraction date:** 2026-07-21
