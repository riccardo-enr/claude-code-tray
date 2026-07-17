---
phase: 03-usage-trends-in-the-tray
plan: 01
subsystem: tray-trends
tags: [gtk, trends, sparkline, burn-rate, read-only]
requires: [HIST-01, HIST-03]
provides: [TREND-01, TREND-02, TREND-03]
affects: [claude-monitor.py]
tech-stack:
  added: [datetime]
  patterns: [pure-fn-demo-tested, compute-in-poll-loop-read-cached-in-menu, corruption-tolerant-read-boundary]
key-files:
  created: []
  modified: [claude-monitor.py]
decisions:
  - "Sparkline auto-scales to the window's own non-empty min..max (D-02); flat window renders all floor glyph, empty input all gaps -- both guarded and demo-asserted (no ZeroDivisionError)."
  - "Burn shown as mean RATE tok/hr (raw per-minute burn x60 exactly once, D-08), never a total; None windows render a literal '-'."
  - "Trends computed only in poll_loop via compute_trends (the single history read boundary), cached on Monitor.trends, read-only in rebuild_menu -- zero file I/O on the Gtk main thread (D-05)."
  - "Empty-state cutover: Monitor.trends stays None until retained history spans TREND_MIN_SPAN (1h), showing one 'trends: collecting history...' row (D-12)."
metrics:
  tasks: 3
  files-changed: 1
  completed: 2026-07-12
status: complete
---

# Phase 3 Plan 01: Usage Trends in the Tray Summary

24h auto-scaled block sparkline, today/week mean burn rate (tok/hr), and peak usage hour-of-day, computed off the Gtk main thread in `poll_loop` and rendered as insensitive rows below the existing usage block in `claude-monitor.py`.

## What Was Built

- **Four pure, demo-tested trend functions** (module-level, stdlib `datetime` only): `local_bounds` (local midnight / ISO-week Monday 00:00), `trend_sparkline` (24-char auto-scaled block glyphs, gap for empty hours), `trend_burn` (mean per-minute burn x60 -> tok/hr, or None), `trend_peak_hour` (busiest local hour by mean burn, ties -> lowest hour).
- **Four constants**: `SPARK_GLYPHS = "▁▂▃▄▅▆▇█"`, `SPARK_GAP = " "`, `TREND_INTERVAL = 5*60`, `TREND_MIN_SPAN = 3600`.
- **`Monitor.compute_trends(now)`** — the single history-read boundary: reads `HISTORY_PATH` once through the corruption-tolerant `parse_history`, `OSError`-guarded, and caches ready-to-render row strings on `Monitor.trends` (or `None` for the collecting/empty state).
- **`poll_loop` wiring** — `last_trend = 0.0` before the loop forces a first-poll compute (no 5-min blank window); thereafter throttled by `TREND_INTERVAL`. Runs AFTER the history append (fresh record included) and BEFORE `idle_add` (same poll's redraw sees it).
- **`Monitor.trend_rows()` + `rebuild_menu`** — reads only the cache (no I/O); menu order is now sessions, usage rows, SEPARATOR, trend rows, SEPARATOR, Quit.

## Key Decisions

See frontmatter `decisions`. All twelve CONTEXT decisions (D-01..D-12) honored; Claude's-discretion picks: gap glyph = single space, throttle = 5 min, empty-state threshold = 1h span, `-` for None burn windows, `today %s/hr | wk %s/hr` and `peak hour: HH:00 (%s/hr)` row wording (ASCII pipe separator, not the unicode middot).

## Verification

- `python3 claude-monitor.py --selfcheck` prints `ok` after every task (all new trend asserts + all v1.0/Phase-2 asserts green, zero regression).
- `python3 -c "import ast; ast.parse(...)"` exits 0 after every task.
- Source asserts confirmed: 4 trend defs, 1 `import datetime`, 1 `SPARK_GLYPHS =`, 1 `compute_trends`, 1 `trend_rows`, 2 `SeparatorMenuItem`, `except OSError` inside `compute_trends`.
- No stray unicode (`·`/`…`) introduced; the only non-ASCII is the endorsed `SPARK_GLYPHS` ramp + `SPARK_GAP`.
- Not exercised here (manual X11 tray, per plan's observable section): live menu rendering of the sparkline / collecting row.

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- claude-monitor.py: FOUND (modified)
- .planning/phases/03-usage-trends-in-the-tray/03-01-SUMMARY.md: FOUND
- Commit d0ed008 (Task 1): FOUND
- Commit d0d6a8a (Task 2): FOUND
- Commit 2a8a95a (Task 3): FOUND
