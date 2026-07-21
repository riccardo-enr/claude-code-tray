---
phase: 09-terminal-dashboard-claude-tui-py
reviewed: 2026-07-21T07:15:00Z
depth: deep
files_reviewed: 7
files_reviewed_list:
  - claude-tui.py
  - claude_monitor/core.py
  - claude_monitor/test_claude_monitor.py
  - pyproject.toml
  - install.sh
  - justfile
  - uv.lock
findings:
  critical: 2
  warning: 6
  info: 5
  total: 13
status: issues_found
---

# Phase 09: Code Review Report

**Reviewed:** 2026-07-21T07:15:00Z
**Depth:** deep (cross-file, plus source verification against installed textual 8.2.8 / rich 15.0.0 and headless execution of the App)
**Files Reviewed:** 7
**Status:** issues_found

## Summary

The phase's headline defensive decisions mostly hold, and I verified them by execution
rather than by reading the SUMMARYs. Two defects survived: the sessions table's scroll
position is destroyed once per second, which makes D-01's "scrolls internally when it
overflows" non-functional; and the markup mitigation for the untrusted project `dir`
covers rich console markup but not ANSI escape sequences, leaving a terminal-escape
injection path through the exact trust boundary threat T-09-01 was written for.

Beyond those, the socket read's timeout does not bound what the plan claims it bounds,
the runtime dependency resolution is not covered by the lockfile the threat model cites,
and a render-time failure is presented to the user as a daemon outage.

### What I verified as sound (not findings)

- **Markup injection (T-09-01, Pitfall 3) — mitigated for markup.** Drove the real App
  headless with dirs `[bold]evil` and `[/]`: both render literally, no `MarkupError`, no
  exit. `default_cell_formatter` (`textual/widgets/_data_table.py:207-209`) does take the
  `return obj` renderable-passthrough branch for a `rich.text.Text`. `Static(markup=False)`
  is honoured: `Widget.__init__` stores it at `textual/widget.py:433` and
  `Static.update()` passes `self._render_markup` into `visualize()`.
- **App-exit containment (T-09-04, Pitfall 1) — both doors closed.** `exit_on_error=False`
  on the worker (`claude-tui.py:91`), a blanket `except Exception` in the worker body
  (`:110`), and a second one around the 1s tick (`:153`). Confirmed by source that
  `App.call_from_thread` re-raises the callback's exception into the *worker thread* via
  `future.result()` (`textual/app.py:1837`), so an `apply_snapshot`/`render_all` failure
  lands in the worker's `except`, never in `App._handle_exception`. Reproduced: a
  malformed usage dict produced no app exit.
- **Textual boundary holds.** `/usr/bin/python3 claude-monitor.py --selfcheck` exits 0;
  neither `core.py` nor `test_claude_monitor.py` imports textual or rich.
- **D-05 verbatim trends.** `core.trend_text` (`core.py:760-773`) joins and never indexes,
  never calls a trend function; D-07's collecting string is the tray's verbatim.
- **Timing constants are imported, never re-literalled** (`claude-tui.py:87-88`), and
  `TUI_SOCK_TIMEOUT < TUI_FETCH_INTERVAL` is asserted in `--selfcheck`.
- **The recorded 09-02 deviation is correct.** `opacity = FractionalProperty(children=True)`
  vs `text_opacity = FractionalProperty()` at `textual/css/styles.py:319-321`, and
  `Widget.opacity` multiplies down `ancestors_with_self` at `textual/widget.py:629-636`.
  `text-opacity` on the container really would have left the three panels undimmed.
  Confirmed `#body` picks up the `stale` class in the headless run.
- **Resource handling.** `core.query_snapshot` has the `try/finally: s.close()`
  (`core.py:722-728`) that `claude-send.py:34-41` lacks, and `settimeout` precedes
  `connect`.
- **Packaging consistency.** `install.sh` is idempotent and its `~/.local/bin` guard holds
  under `set -euo pipefail` (ran it twice under a temp `$HOME`, and once with no
  `~/.local/bin`). The extensionless symlink target really works: I ran
  `uv run --quiet --script` against a symlink from `/tmp` and the App started with
  `from claude_monitor import core` resolved. Nothing added textual to `/usr/bin/python3`.
- **Frozen files.** `git diff --name-status 1455a45~1..HEAD` confirms `claude-monitor.py`,
  `claude-send.py` and `claude_monitor/dashboard.py` are byte-unchanged.
- **Gates green.** `just lint` and `/usr/bin/python3 claude-monitor.py --selfcheck` both
  exit 0.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: The 1s render tick resets the sessions table's scroll position to the top — D-01's internal scrolling does not work

**Severity:** BLOCKER
**File:** `claude-tui.py:169` (`table.clear()` inside `render_all`, reached from `tick()` every second)

**Issue:** `DataTable.clear()` in textual 8.2.8 unconditionally resets the viewport:

```python
# textual/widgets/_data_table.py:1600-1606
self.refresh()
self.scroll_x = 0
self.scroll_y = 0
self.scroll_target_x = 0
self.scroll_target_y = 0
```

`render_all()` calls `clear()` then re-adds every row, and `tick()` calls `render_all()`
on `TUI_TICK_INTERVAL` (1.0s). So any scroll the user performs is undone within one
second. Reproduced headlessly with 60 sessions on an 80x24 screen
(`max_scroll_y == 43`): `scroll_y` set to `20`, one `tick()`, `scroll_y == 0`.

This breaks D-01 verbatim: *"sessions table takes all remaining space and scrolls
internally when it overflows"*. With more sessions than fit, everything below the first
screenful is unreachable. 09-RESEARCH.md rejected `recompose=True` for the sessions panel
precisely because it "loses scroll position" — the chosen `clear()` + re-add has the
identical outcome, so the pitfall was avoided in form but not in substance.

**Fix (smallest correct change):** preserve and restore the offset around the rebuild.

```python
table = self.query_one("#sessions", DataTable)
scroll_y = table.scroll_y  # DataTable.clear() zeroes scroll_x/scroll_y (8.2.8)
table.clear()
for status, proj, elapsed in core.sess_rows(snap.get("sessions") or [], now):
    table.add_row(Text(status), Text(proj), Text(elapsed))
table.scroll_y = scroll_y  # clamped by validate_scroll_y if the list shrank
```

A better long-run shape is to rebuild only when the session identity list changes and
update only the `time` column via `update_cell_at` on a plain tick, but the two-line
restore is the lazy fix that makes D-01 true.

---

### CR-02: `rich.text.Text` does not strip ANSI escapes — a project directory name can inject control sequences into the user's terminal

**Severity:** BLOCKER
**File:** `claude-tui.py:177` (`table.add_row(Text(status), Text(proj), Text(elapsed))`);
originates at `claude_monitor/core.py:807-826` (`sess_rows` returns `dir` raw, by design)

**Issue:** Threat T-09-01 is registered **high** and its mitigation is stated as "the
single `add_row` call site wraps every cell in `rich.text.Text`, taking the
renderable-passthrough branch". That closes *markup* injection. It does not close
*terminal control* injection.

`rich.text.Text.__init__` sanitizes via `strip_control_codes` (`rich/text.py:156`), but
that function only removes five codepoints (`rich/control.py:9-15`):

```python
STRIP_CONTROL_CODES: Final = [7, 8, 11, 12, 13]  # BEL, BS, VT, FF, CR
```

`ESC` (0x1b) is not among them. I confirmed the escape survives all the way into the
composited output: rendering a snapshot with `dir = "A\x1b[2JB"` and asserting
`"\x1b[2J" in "".join(seg.text for strip in app.screen._compositor.render_strips() for seg in strip)`
returned `True`. Textual writes segment text verbatim to the driver, so the sequence
reaches the terminal.

Trigger: any directory whose name contains an ESC byte (legal on Linux) in which a
Claude Code session is started — e.g. a hostile repo that ships a subdirectory named
`$'\e]52;c;<base64>\a'` (OSC 52 clipboard write on terminals that support it) or
`$'\e[2J'`. This is the same "untrusted content in a trusted envelope" boundary the plan's
own threat model names, and it is the terminal analogue of the Pango (T-05-04) and
`textContent` (T-07-01) lessons.

**Fix:** sanitize where it is pure and assertable — in `core.sess_rows`, so the fix is
covered by `--selfcheck` and any future widget also benefits:

```python
def _safe_cell(s):
    """Strip C0/C1 control characters from an arbitrary filesystem path. Pure.
    rich.text.Text only strips BEL/BS/VT/FF/CR, so ESC-based sequences would otherwise
    reach the terminal verbatim (T-09-01, control-sequence half).
    """
    return "".join(c if c.isprintable() or c == " " else "?" for c in s)
```

then `s.get("dir", "")` becomes `_safe_cell(s.get("dir", ""))` at `core.py:822`. Note
that the existing selfcheck assertion at `test_claude_monitor.py:766-780` encodes the
opposite contract ("`sess_rows` must return it byte-for-byte"); that assertion needs to
change with the fix, and the markup-hostile `[bold]myrepo[/]` case must keep passing
through untouched (it is printable).

## Warnings

### WR-01: `TUI_SOCK_TIMEOUT` bounds each `recv`, not the whole read — the thread pile-up guard is weaker than asserted, and the buffer is unbounded

**Severity:** WARNING
**File:** `claude_monitor/core.py:697-704` (`read_line`)

**Issue:** `socket.settimeout(1.5)` applies per blocking call. `read_line` loops
`sock.recv(65536)` until a newline, so a peer that emits one byte every 1.4s keeps the
worker blocked indefinitely while the 2s `set_interval` keeps firing. `exclusive=True`
marks the previous worker cancelled but cannot interrupt a blocked thread (09-RESEARCH
Pitfall 2 says exactly this). The `--selfcheck` assertion
`TUI_SOCK_TIMEOUT < TUI_FETCH_INTERVAL` and the plan truth *"at most one fetch is ever in
flight"* therefore over-claim: the invariant they encode is about a single `recv`, not
about the function.

Separately, `buf` grows without limit; a daemon that streams without ever sending `\n`
grows the TUI's RSS until OOM. Same-user trust boundary keeps the severity down, but the
threat register lists this under T-09-02 "Denial of Service / mitigate".

**Fix:** give `read_line` a wall-clock deadline and a size cap.

```python
def read_line(sock, deadline=None, max_bytes=1 << 20):
    buf = b""
    while not buf.endswith(b"\n"):
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError("snapshot read exceeded %ss" % TUI_SOCK_TIMEOUT)
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
        if len(buf) > max_bytes:
            raise ValueError("snapshot response exceeded %d bytes" % max_bytes)
    return buf.decode("utf-8", "replace")
```

and in `query_snapshot`: `return json.loads(read_line(s, time.monotonic() + timeout))`.

---

### WR-02: `query_snapshot` / `apply_snapshot` accept a non-dict JSON value, silently re-arming the cold-start predicate under a "live" header

**Severity:** WARNING
**File:** `claude_monitor/core.py:722-728` (`query_snapshot`), `claude-tui.py:113-127`
(`apply_snapshot`)

**Issue:** `json.loads` succeeds for `null`, `[]`, `3` and `"x"`. If the daemon ever
writes a bare `null\n`, `query_snapshot` returns `None` and `apply_snapshot(None)` runs
its whole happy path: `self.snapshot = None`, `last_ok = time.time()`, `#coldstart`
hidden, `.stale` cleared, `sub_title = "live"`, and then `render_all()` returns
immediately at `:162-163`. Result: the previous frame stays on screen labelled **live**,
and the D-11 cold-start predicate (`self.snapshot is None`) is now true again, so the
next failure will wipe good data to the cold-start message instead of dimming it.

That is precisely the state Plan 09-02's first prohibition forbids ("MUST NOT present
stale data as if it were live"). A list value instead produces `AttributeError` on
`snap.get` — contained, but then `self.snapshot` is a non-dict for the rest of the
session.

**Fix:** validate at the parse boundary, where `--selfcheck` can assert it.

```python
    obj = json.loads(read_line(s))
    if not isinstance(obj, dict):
        raise ValueError("snapshot response was %s, not an object" % type(obj).__name__)
    return obj
```

---

### WR-03: A render failure is reported to the user as "daemon unreachable", and `apply_snapshot` leaves half-applied state

**Severity:** WARNING
**File:** `claude-tui.py:120-127` (`apply_snapshot`), `:107-111` (`fetch`)

**Issue:** `apply_snapshot` calls `render_all()` unguarded. Because `call_from_thread`
re-raises into the worker thread (`textual/app.py:1837`), any render exception is caught
by the worker's blanket `except Exception` at `:110` and routed to `mark_stale()`. I
reproduced this: a usage dict missing `resets_at_epoch` raised `KeyError` out of
`apply_snapshot`, and the UI then showed
`daemon unreachable -- last update HH:MM:SS` with the data dimmed — while the daemon was
perfectly healthy. That is a wrong diagnosis pointing the user at `just start`.

It also falsifies the plan's `verification: backstop` truth in a narrow sense: the
*snapshot binding* is a single assignment, but `self.snapshot`, `self.last_ok` and
`sub_title = "live"` are all committed **before** `render_all()`, so a partial failure
leaves new state bound with old panels on screen and a "live" header until `mark_stale`
overwrites it.

**Fix:** guard the render and commit the header only after it succeeds.

```python
    def apply_snapshot(self, snap) -> None:
        self.snapshot = snap
        self.last_ok = time.time()
        self.query_one("#coldstart").display = False
        body = self.query_one("#body")
        body.display = True
        body.set_class(False, "stale")
        self.tick()          # renders under the same guard as the 1s tick
        if self.sub_title != "render error -- frame may be stale":
            self.sub_title = "live"
```

---

### WR-04: The command palette is still bound — D-02's "exactly one key binding, no theme toggle" is not enforced

**Severity:** WARNING
**File:** `claude-tui.py:66` (`BINDINGS`), missing `ENABLE_COMMAND_PALETTE = False`

**Issue:** `App.ENABLE_COMMAND_PALETTE` defaults to `True`, so textual binds `ctrl+p` and
`Footer()` advertises it. Running the real app confirms the footer renders
`q quit` **and** `^p palette`. The palette exposes `action_change_theme` (`App.action_change_theme`,
`textual/app.py:1840`) among other commands — the theme toggle D-02 explicitly rejected.
Plan 09-02's acceptance criterion (`grep -c 'BINDINGS'` == 1 and `grep -c '"q"'` == 1)
passes vacuously because it only counts *declared* bindings, not inherited ones.

**Fix:** one class attribute next to `TITLE`:

```python
    ENABLE_COMMAND_PALETTE = False  # D-02: exactly one binding, and no theme toggle
```

---

### WR-05: The runtime dependency resolution is not covered by `uv.lock` — the T-09-SC supply-chain mitigation is not actually in force

**Severity:** WARNING
**File:** `claude-tui.py:2-5` (PEP 723 block), `pyproject.toml:8-20`, `uv.lock`

**Issue:** Plan 09-02's threat register states the mitigation for `textual` and its 9
transitives as *"`uv.lock` pins the full transitive set with hashes"*. That lockfile
governs `uv sync --extra tui` (the checker/dev environment) only. `uv run --script`
resolves a PEP 723 block **standalone** and consults `<script>.lock`, which does not
exist here (`ls claude-tui.py.lock` -> no such file). So the interpreter that actually
runs the TUI resolves `textual>=8,<9` freshly against PyPI on any machine with a cold uv
cache, with no pinned versions and no hashes. The stated mitigation is asserted, not
implemented.

**Fix:** uv 0.7.1 already supports it (`uv lock --script <SCRIPT>`):

```bash
uv lock --script claude-tui.py   # produces claude-tui.py.lock -- commit it
```

`uv run --script` picks the lock up automatically; add a note to the PEP 723 comment
block and a line to `install.sh`'s docs if the lock must ship.

---

### WR-06: `tui_usage_rows` subscripts three usage keys while using `.get()` for the rest — an unenforced coupling across the socket

**Severity:** WARNING
**File:** `claude_monitor/core.py:742`, `:748`, `:749`

**Issue:** `usage["used_percentage"]`, `usage["resets_at_epoch"]` and
`usage["burn_rate_per_min"]` are direct subscripts, while `tokens_used`, `token_limit`,
`seven_day_pct` and `seven_day_reset` use `.get()`. This is safe *today* only because
`parse_usage` (`core.py:279-281`) returns `None` wholesale unless all three are numeric —
a guarantee that lives in a different process, crosses a JSON socket, and is enforced by
nothing on the reading side. Every sibling helper in the same block
(`sess_elapsed`, `sess_rows`) uses `.get()` and documents "a short session dict never
raises"; the usage path silently opts out of that discipline. When it does fire, WR-03
turns it into a false "daemon unreachable".

**Fix:** read defensively and fall back to the string the branch already owns.

```python
    pct = usage.get("used_percentage")
    reset = usage.get("resets_at_epoch")
    burn = usage.get("burn_rate_per_min")
    if pct is None or reset is None or burn is None:
        return ["usage unavailable"]
```

## Info

### IN-01: `fmt_elapsed`'s day tier diverges from the v1.4 dashboard's `fmtDur`

**Severity:** INFO
**File:** `claude_monitor/core.py:786-787` vs `claude_monitor/dashboard.py:400-401`

**Issue:** JS `fmtDur` renders `Math.floor(s/86400)+"d "+Math.floor((s%86400)/3600)+"h"`
= `"3d 2h"`. `fmt_elapsed` renders `"%dd %02dh"` = `"3d 02h"`. The hour/minute and
minute/second tiers match exactly. 09-01-PLAN Task 1 said the function "mirrors `sessDur`
+ `fmtDur` exactly"; it does not, for sessions at or past 24h. The docstring records the
padded form so this reads as intentional, but the two surfaces now disagree for that tier.

**Fix:** drop the `%02d` to `%d`, or record the divergence as a decision.

---

### IN-02: The first frame shows three empty panels before the first fetch resolves

**Severity:** INFO
**File:** `claude-tui.py:62` (`#coldstart { display: none; }`), `:81-89` (`on_mount`)

**Issue:** D-11 says a cold start shows "a single clear centered message instead of empty
panels". `#coldstart` starts hidden and `#body` starts visible, so between `on_mount` and
the first worker result the screen is an empty usage Static, an empty trends Static and an
empty table under `sub_title = "connecting..."`. I saw this in a live run. The window is
milliseconds when the socket file is absent (`FileNotFoundError` is immediate) but up to
`TUI_SOCK_TIMEOUT` (1.5s) against a hung daemon.

**Fix:** invert the initial state in `compose`/CSS — `#body { display: none; }` and
`#coldstart` visible with the connecting message; `apply_snapshot` already flips both.

---

### IN-03: `just selfcheck` no longer proves the textual boundary on its own

**Severity:** INFO
**File:** `justfile:36-38`

**Issue:** the recipe is `python3 {{entry}} --selfcheck` — bare `python3`, resolved
through `PATH`. The repo's `.venv` now contains textual/rich (`uv sync --extra tui`), so
inside an activated venv `just selfcheck` runs on an interpreter that *does* have textual
and would happily pass even if `core.py` grew a textual import. Only
`/usr/bin/python3 claude-monitor.py --selfcheck` — which the plans ran manually and which
I ran here — actually proves the boundary. The recipe is out of the phase's edit scope,
but the guarantee the phase depends on now rests on it.

**Fix:** pin the recipe to `/usr/bin/python3`, matching `restart`/`start` (justfile:19,24).

---

### IN-04: `Text(...)` cells are constructed without the `no_wrap`/`end` settings DataTable applies to its own string path

**Severity:** INFO
**File:** `claude-tui.py:177`

**Issue:** `default_cell_formatter` builds `Text.from_markup(content, end="")` and sets
`text.no_wrap = not wrap` (`textual/widgets/_data_table.py:220-223`). The passthrough
branch returns the caller's `Text` untouched, so these cells carry `end="\n"` and default
wrapping. Rows are added with the default `height=1` so the extra line is cropped, but a
long path (or a `dir` containing a literal newline, which is legal on Linux) will lay out
differently from any cell DataTable formats itself.

**Fix:** `Text(proj, no_wrap=True, end="")` at the single call site.

---

### IN-05: `SOCK_PATH` is now the third copy of the socket path expression

**Severity:** INFO
**File:** `claude_monitor/core.py:675-677`

**Issue:** the same `os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "claude-monitor.sock")`
now lives at `claude-monitor.py:32`, `claude-send.py:17` and `core.py:677`. The
"change all three" marker comment is present and honest, and both other files were frozen
by the phase scope fence, so this is correctly-recorded debt rather than an oversight.
Worth noting that `core.py` is importable by both of the other two, so the debt is now
one-line-retirable.

**Fix:** in a follow-up, have `claude-monitor.py` and `claude-send.py` import
`core.SOCK_PATH` and delete their copies.

---

_Reviewed: 2026-07-21T07:15:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
