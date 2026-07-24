---
phase: 10-tui-polish-btop-style
reviewed: 2026-07-24T00:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - claude_monitor/core.py
  - claude_monitor/test_claude_monitor.py
  - claude-tui.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-07-24T00:00:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Phase 10 adds four pure helpers to `claude_monitor/core.py` (`band`, `gauge_fill`,
`spark_levels`, `sess_status_band`), their assert blocks in `test_claude_monitor.py`, and
their consumption in `claude-tui.py` (gradient gauges, decoded column-graph trends,
status-colored sessions table, titled rounded panels).

The numeric core is genuinely defensive and I could not surface a correctness BLOCKER:

- **`band`** is total over any real number (verified `band(-5)`, `band(473.5)`, and even
  `band(nan)` all classify without raising).
- **`gauge_fill`** clamps `pct` to 0..100 and never returns past `width`; the monotonicity
  and clamp invariants hold and are swept by the test (`_walk == sorted(_walk)`,
  `min==0`, `max==width`).
- **`spark_levels`** is the exact inverse of `SPARK_GLYPHS`; gap/unknown chars decode to
  `None` via `.get`.
- **`sess_status_band`** mirrors `sess_rank` unknown-tolerance (unknown -> `"default"`).
- **T-09-01 invariant preserved:** every `DataTable` cell in the restyled sessions table is
  a `rich.Text` (`Text(status, style=band)`, etc.), never a bare `str`.
- **Selfcheck gate intact:** `core.py` imports only stdlib (`datetime, json, math, os,
  socket, subprocess, tempfile, time`) -- no `textual`/`rich`.

All render paths (`_usage_renderable`, `_trends_renderable`, `_gauge`, `_cap_row_text`) are
reached only through `render_all`, which is called only from `tick()` -- and `tick()` wraps
`render_all` in a `try/except` that surfaces `"render error"` instead of exiting the app.
That guard is what contains every malformed-snapshot path below. In normal operation
(`parse_usage` output over the socket) none of the new helpers receive a `None`/non-numeric
value, so nothing raises.

The findings are all robustness / maintainability, not correctness.

## Warnings

### WR-01: `spark_levels` docstring claims it "cannot raise" but raises `TypeError` on a non-string `trends[0]`

**File:** `claude_monitor/core.py:471-480`, consumed at `claude-tui.py:265`
**Issue:** The docstring states "a malformed/hostile `trends[0]` (T-10-03) cannot raise."
That holds only for a *string* input. `spark_levels` does `for ch in sparkline`, so a
non-iterable (e.g. an `int`) input raises `TypeError` (confirmed: `spark_levels(123)` ->
`TypeError`). `_trends_renderable` calls `core.spark_levels(trends[0])` where `trends`
comes straight from `snap.get("trends")` -- an untrusted JSON payload off the socket that
`query_snapshot` validates only as far as "the top level is a dict." A daemon that emits
`"trends": [123, ...]` (or `[null, ...]`) makes `spark_levels` raise.

In practice this is contained by the `tick()` guard (surfaces `"render error -- frame may be
stale"` rather than crashing), and the socket is a same-user unix socket, so the trust
boundary is weak. But the stated invariant is stronger than the code delivers.
**Fix:** Either coerce/guard the input, or soften the docstring to state the contract is
"tolerant of any *string*; non-string input is caught by the caller's render guard." Minimal
guard:
```python
def spark_levels(sparkline):
    if not isinstance(sparkline, str):
        return []
    return [_SPARK_LEVEL.get(ch) for ch in sparkline]
```

### WR-02: `_usage_renderable` couples to the exact `"usage unavailable"` sentinel by list equality (third copy of the string)

**File:** `claude-tui.py:235-243` (guard), `claude_monitor/core.py:802,811`
**Issue:** After the guard `if usage is None or rows == ["usage unavailable"]`, the code
subscripts `usage["used_percentage"]` (and `usage["seven_day_pct"]`) directly, trusting that
any surviving `rows` came from a usage dict with non-`None` numerics. That trust rests on an
exact string/list-equality match against `tui_usage_rows`' sentinel. If the sentinel string
ever changes in `core.py` (it already exists in two places -- `core.py:802` and the tray's
`claude-monitor.py:320`, now a third coupling here), the guard silently fails: `rows ==
["usage unavailable"]` becomes `False`, execution falls through to `usage["used_percentage"]`
which is `None`, and `band(None)` raises `TypeError: '<' not supported between NoneType and
int`. That is caught by `tick()` but mislabels a data-shape mismatch as `"render error"`.
**Fix:** Gate on the data rather than the rendered sentinel, so the two functions are not
string-coupled:
```python
rows = core.tui_usage_rows(usage, now)
pct = None if usage is None else usage.get("used_percentage")
if pct is None:
    return Text("\n".join(rows))
```

## Info

### IN-01: local variable `band` in `render_all` shadows the conceptual `core.band`

**File:** `claude-tui.py:302-303`
**Issue:** `band = core.sess_status_band(status)` names a *status* band `band`, while
`core.band` (the proximity-to-cap function) is used under its qualified name throughout the
rest of the file (`_gauge`, `_cap_row_text`, `_trends_renderable`). No live conflict today --
`render_all` never calls the bare name `band` -- but the reuse of the name for a different
concept invites a future edit to reach for `band(...)` expecting proximity coloring.
**Fix:** Rename to `style` or `sband`: `sband = core.sess_status_band(status)`.

### IN-02: `gauge_fill` behavior for `width <= 0` is undocumented and unguarded

**File:** `claude_monitor/core.py:780-788`
**Issue:** The docstring documents the `pct` clamp (0..100) but says nothing about `width`.
`gauge_fill(50, 0)` returns `0` and `gauge_fill(50, -5)` returns `-2` (a negative cell
count). Currently unreachable -- the only call site passes the constant `GAUGE_WIDTH = 20` --
so this is not a live defect, but the prompt called out `width <= 0` as an edge case and
there is no test pinning it.
**Fix:** Either add a one-line note ("`width` is assumed positive; the sole caller passes
`GAUGE_WIDTH`") or clamp defensively: `return max(0, round(pct / 100 * max(0, width)))`.

### IN-03: gauge color gradient is position-based, so a low-fill gauge is entirely green regardless of a high 7d/5h severity

**File:** `claude-tui.py:199-212`
**Issue:** `_gauge` colors each *filled* cell by its position (`core.band(i / GAUGE_WIDTH *
100)`), not by the actual usage percent. A gauge at 30% usage (n=6 cells) shows 6 green
cells even though the *value* the row text bands may be nearing a cap on the 7d row. This is
the documented btop-meter design (D-03: severity is carried by fill length plus the
band-colored row text), so it is intentional, not a bug -- flagged only to confirm it was a
deliberate choice and reads correctly against the "gradient gauge" intent. No change
recommended.

---

_Reviewed: 2026-07-24T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
