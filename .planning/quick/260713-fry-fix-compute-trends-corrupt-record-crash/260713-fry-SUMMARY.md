---
phase: quick-260713-fry
plan: 01
subsystem: usage-monitor
tags: [bugfix, robustness, trends, poll-thread]
status: complete
requires: []
provides:
  - build_trend_rows(records, now) -- pure, Gtk-free trend row builder
  - poll_loop per-iteration exception guard
affects:
  - claude-monitor.py
tech-stack:
  added: []
  patterns:
    - "history_numeric as the single sanitizer choke point for ALL history consumers"
    - "broad except Exception + traceback.print_exc() on the poll thread (observable degradation)"
key-files:
  created: []
  modified:
    - claude-monitor.py
decisions:
  - "Sanitize inside build_trend_rows (shared choke point) rather than guarding each trend_* helper -- one line fixes all three callers."
  - "traceback.print_exc() rather than a silent swallow: a persistent failure must stay loud in the journal."
  - "time.sleep kept OUTSIDE the try so a failing iteration still throttles and cannot hot-spin."
metrics:
  duration: ~12m
  tasks: 2
  files: 1
  commits: 2
completed: 2026-07-13
---

# Quick 260713-fry: Fix compute_trends Corrupt-Record Crash Summary

One corrupt line in `~/.claude/usage-history.jsonl` permanently killed the tray's poll
thread; trend history now routes through the same `history_numeric` sanitizer the
dashboard already used, and `poll_loop` survives any per-iteration raise.

## What Was Built

### Task 1 -- Route trend history through `history_numeric` (root cause)
Commit `586596c`

`Monitor.compute_trends` fed `parse_history` output straight into `trend_sparkline` /
`trend_burn` / `trend_peak_hour`. `parse_history` validates a numeric `t` only, so `pct`
and `burn` were untrusted: a string `burn` raised `TypeError` inside `trend_burn`'s
`sum(vals)`, a NaN `burn` silently rendered `"nan/hr"`, and `t: 1e18` raised `OSError`
inside `datetime.fromtimestamp`. The existing `try/except OSError` wrapped only the file
read, so the raise escaped.

Extracted the pure tail of `compute_trends` into a module-level
`build_trend_rows(records, now)` (placed after `trend_peak_hour`, before `_embed_json`).
Its first statement is `records = history_numeric(records)` -- the SAME choke point
`render_dashboard` already uses. Existing logic kept intact: the `TREND_MIN_SPAN` span
check (now on sanitized records, so a far-future `t` can no longer inflate the span), the
sparkline row, the `today X/hr | wk Y/hr` row, and the optional peak-hour row. Returns
`None`/`rows` instead of assigning `self.trends`.

`compute_trends` keeps its `try/except OSError` around the file read (missing/unwritable
file still degrades to last-known trends) then assigns `self.trends = build_trend_rows(...)`.
The function was split out specifically so it is Gtk-free and `demo()` can exercise the
real path without instantiating `Monitor`.

`history_numeric`, `trend_burn`, `trend_peak_hour`, `trend_sparkline` and `history_keep`
were NOT modified.

### Task 2 -- Guard `poll_loop`
Commit `f4e00bf`

Added `import traceback`. Wrapped the entire `poll_loop` while-body (`fetch_usage`,
`append_history`, the `compute_trends` and `write_dashboard` throttles, the `GLib.idle_add`,
the `prune_history` throttle) in `try/except Exception: traceback.print_exc()`.
`time.sleep(POLL_INTERVAL)` stays OUTSIDE the try as the last statement, so a failing
iteration is still throttled and cannot hot-spin. The startup `prune_history` call and the
`last_*` initializers stay outside the loop, unchanged.

The blanket-swallow tension is addressed in a `ponytail:` comment mirroring
`write_dashboard`'s voice: the degradation is made observable rather than silent --
`traceback.print_exc()` writes the full traceback to stderr (the journal) on EVERY failing
iteration, so a persistent failure is loud and repeated while a transient one costs one
poll. Upgrade path noted: surface it in the tray label if a real bug ever hides there.

## Verification

- `python3 claude-monitor.py --selfcheck` prints `ok`. No pre-existing assert (v1.0 /
  Phase-2 / Phase-3 / Phase-4) was removed or weakened.
- AST guard check prints `guard ok`: the `poll_loop` while-body contains a `try` and the
  trailing `time.sleep` sits outside it.
- **The new asserts genuinely fail without the fix.** Reverting only the
  `records = history_numeric(records)` line reproduces the exact reported crash:
  `TypeError: unsupported operand type(s) for +: 'float' and 'str'` in `trend_burn`.
- Manual sanity on a synthetic history file containing a string `burn`, a NaN `burn`, a
  `t` of `1e18`, and a garbage non-JSON line: `build_trend_rows` returns real rows
  (`['...▁▅█', 'today 9k/hr | wk 9k/hr', 'peak hour: 11:00 (18k/hr)']`), raises nothing,
  and no `nan` appears.
- ASCII-only: zero non-ASCII characters in any added line (the two file-level hits are
  pre-existing -- an em-dash comment at line 46 and `SPARK_GLYPHS` at line 82).
- Stdlib only, single source file touched.

### New demo() coverage
In the Phase-3 trend section, a `build_trend_rows` block asserting:
- `build_trend_rows(clean, now)` returns 3 real rows with no `nan`
- `build_trend_rows(clean + corrupt, now) == build_trend_rows(clean, now)` -- the
  regression guard; this is the assert that fails without the fix
- `build_trend_rows(only_corrupt, now) is None` (all dropped -> collecting state)
- `build_trend_rows([], now) is None`
- no call raises

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- `claude-monitor.py` modified: FOUND
- Commit `586596c`: FOUND
- Commit `f4e00bf`: FOUND
- `--selfcheck` prints `ok`: CONFIRMED
