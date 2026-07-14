---
phase: 04-usage-web-dashboard
reviewed: 2026-07-12T00:00:00Z
depth: standard
files_reviewed: 1
files_reviewed_list:
  - claude-monitor.py
findings:
  critical: 0
  warning: 1
  info: 2
  total: 3
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-07-12
**Depth:** standard
**Files Reviewed:** 1
**Status:** issues_found

## Summary

Reviewed the Phase-4 dashboard additions to `claude-monitor.py` (diff base `c70bca45`):
`_embed_json`, `history_numeric`, `heatmap_buckets`, `burn_series`, `render_dashboard`, the
`DASH_DIR`/`DASH_PATH`/`DASH_INTERVAL` constants, `Monitor.write_dashboard`,
`Monitor.open_dashboard`, `dash_ready`, the `last_dash` throttle, and the "Open Usage Dashboard"
menu item.

**Security headline (T-04-01) verdict: the injection mitigation holds.** I traced every value
that reaches the inline `<script>` payload built in `render_dashboard` (lines 531-537). The
payload is constructed explicitly from `int(r["t"])`, `r["pct"]`, and numeric aggregates out of
`heatmap_buckets`/`burn_series`, plus computed ints (`bounds`, `generated`). The record dict is
never spread, so keys other than `t`/`pct`/`burn` cannot reach the payload. `history_numeric`
runs first (line 527) and `_embed_json` is the single serialization point, escaping `<`, `>`, `&`
so `</script>`, `<!--`, and `<script` can never appear literally. `json.dumps` defaults to
`ensure_ascii=True`, so U+2028/U+2029 JS line-terminators are also escaped away. Both layers are
present and correct; I found no serialization bypass. Off-Gtk-thread discipline is correct
(`open_dashboard` does zero I/O; all history reads live in the poll thread), the temp+`os.replace`
write is atomic and same-filesystem, the broad-except degradation is intentional and sound, and
`pathlib.Path(DASH_PATH).resolve().as_uri()` correctly handles an absolute path with special chars.

The one substantive gap is that the new `history_numeric` validator is incomplete: it accepts
non-finite floats (`NaN`/`Infinity`) and out-of-range timestamps, which the *availability* of the
dashboard (not its injection safety) depends on. Details below.

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: `history_numeric` accepts NaN/Infinity and out-of-range `t`, silently and permanently breaking the dashboard

**File:** `claude-monitor.py:366-378` (interacting with `render_dashboard:517-543`, `write_dashboard:958-993`, `heatmap_buckets:381-396`, `burn_series:399-421`, `prune_history:245-271`)

**Issue:**
`history_numeric`'s `num()` predicate is `isinstance(v, (int, float)) and not isinstance(v, bool)`.
Two numeric-but-pathological classes pass this check, and the phase's own threat model (T-04-01)
declares `~/.claude/usage-history.jsonl` untrusted:

1. **NaN / Infinity.** Python's `json.loads` parses the non-standard tokens `NaN`, `Infinity`,
   `-Infinity` by default, producing `float` values. A tampered line such as
   `{"t": NaN, "pct": 1.0, "burn": 1.0}` survives `parse_history` (numeric `t`) and
   `history_numeric` (NaN/Inf are `float` instances). In `render_dashboard`, the usage payload
   builds `int(r["t"])` (line 532); `int(float("nan"))` raises `ValueError`.
2. **Out-of-range `t`.** A record like `{"t": 1e18, "pct": 1.0, "burn": 1.0}` passes both filters,
   then `heatmap_buckets`/`burn_series`/`local_bounds` call
   `datetime.datetime.fromtimestamp(rec["t"])`, which raises `OverflowError`/`OSError`/`ValueError`
   for an out-of-range epoch.

In both cases the exception is caught by `write_dashboard`'s broad `except Exception` (line 986),
so the poll thread survives — but the dashboard is **not** rewritten this tick, and it stays broken
on every subsequent tick because the poisoned record is never removed:

- A far-future `t` is **never pruned**: `history_keep` (line 204) is
  `rec["t"] >= now - days*86400`, and `1e18 >= now-2592000` is always True. `prune_history` keeps
  it forever, so the dashboard is permanently stuck (menu item stays greyed if the bad record was
  present before the first successful write, since `dash_ready` never flips to True).
- A `NaN` `t` is pruned eventually (`NaN >= x` is False), but only at the 6-hourly `PRUNE_INTERVAL`
  or at startup, so the dashboard is dead for up to ~6h.

Same-root note (out of Phase-4 scope but worth flagging): the identical bad record also flows into
`compute_trends`, whose `try` wraps only the file read (`except OSError`, lines 933-937). The
downstream `trend_peak_hour(records)` -> `datetime.fromtimestamp` overflow is **not** caught and
`compute_trends` is invoked un-wrapped in `poll_loop` (line 1106), so the same untrusted record
would kill the entire poll thread. `history_numeric` was added specifically to sanitize this class
of input for the dashboard; tightening it fixes both paths at the shared boundary.

**Fix:** Reject non-finite floats and clamp `t` to a sane epoch range inside `history_numeric` (the
one validation boundary), so nothing but embeddable, `fromtimestamp`-safe data flows downstream:

```python
import math

# sane epoch window: 2020-01-01 .. 2100-01-01 (fromtimestamp-safe, prunable)
_T_MIN, _T_MAX = 1_577_836_800, 4_102_444_800

def history_numeric(records):
    def num(v):
        return (
            isinstance(v, (int, float))
            and not isinstance(v, bool)
            and math.isfinite(v)
        )
    return [
        r for r in records
        if num(r.get("t")) and _T_MIN <= r["t"] <= _T_MAX
        and num(r.get("pct")) and num(r.get("burn"))
    ]
```

Then route `compute_trends` and `write_dashboard` through `history_numeric` before any
`fromtimestamp`/aggregation call (write_dashboard already does, via `render_dashboard`; add the
same filter in `compute_trends` right after `parse_history`).

## Info

### IN-01: `HISTORY_PATH` is read and parsed twice per poll tick

**File:** `claude-monitor.py:933-935` (`compute_trends`) and `claude-monitor.py:975-977` (`write_dashboard`)

**Issue:** On a tick where both the trend and dashboard throttles elapse (`poll_loop` lines
1105-1113), the full history file is opened, read, and run through `parse_history` twice in the
same thread. Correctness is unaffected (single-threaded, sequential), but it is duplicated I/O and
duplicated parse logic that can drift.

**Fix:** Read+parse once in `poll_loop` and pass the parsed `records` list into both
`compute_trends(records, now)` and `write_dashboard(records, now)`. This also gives a single place
to apply the tightened `history_numeric` filter from WR-01.

### IN-02: `open_dashboard` trusts `dash_ready` without confirming the file still exists

**File:** `claude-monitor.py:821-822`

**Issue:** `dash_ready` flips True on the first successful write and never resets. If
`~/.cache/claude-tray/dashboard.html` is later deleted (cache cleaner, manual `rm`),
`Path(DASH_PATH).resolve().as_uri()` still yields a `file://` URI (`resolve()` is non-strict), and
`webbrowser.open` opens a 404/blank page. Low impact — the file is rewritten on the next throttle
window — but the menu item claims readiness it can't guarantee.

**Fix:** Cheap existence guard before opening, e.g.
`if os.path.exists(DASH_PATH): webbrowser.open(...)` — or accept the current behavior as a known
minor edge (`# ponytail: stale-ready window, rewritten within DASH_INTERVAL`).

---

_Reviewed: 2026-07-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
