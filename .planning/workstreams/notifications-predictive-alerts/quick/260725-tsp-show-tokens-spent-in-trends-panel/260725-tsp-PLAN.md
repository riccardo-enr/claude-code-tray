---
phase: 260725-tsp
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - claude_monitor/core.py
  - claude_monitor/test_claude_monitor.py
---

# Quick Task 260725-tsp: Show tokens spent in the trends panel

## Goal

The TUI trends panel shows only *rates* (`today 23.8M/hr | wk 18.1M/hr`, `peak hour`).
Add the absolute tokens consumed today and this week.

## Approach

The obvious source, `tokens_used`, is dead: since quick task 260712-ndo switched
polling to `--api`, every record carries `tokens_used: None` (15907 of 18590 records
in the live history). A cumulative-counter reading would report ~0 forever.

Integrate `burn` (tok/min, always present — `history_numeric` requires it) over the
interval between consecutive samples instead. Intervals wider than `GAP_MAX` are
daemon outages, not idle time, and are skipped, so the figure is "tokens seen
burned" — a floor, never an extrapolation across a gap.

## Tasks

1. `trend_spent(records, start, end)` in `core.py` — burn integrated over
   sub-`GAP_MAX` intervals in the window; `None` when no interval is measurable.
2. `build_trend_rows` appends `spent today <n> | wk <n>` between the burn-rate row
   and the peak-hour row.
3. `fmt_tokens` gains a `G` tier — weekly spend runs past 1000M.
4. Assertions in `test_claude_monitor.demo()` covering the gap skip, the
   single-sample case, the `G` tier, and the new row's presence/position.

No Rust change: `draw_trends` renders whatever rows the daemon sends and
`trends_panel_height` sizes to content.

## Verify

`just selfcheck` exits 0, `just lint` clean, `just restart` and the row appears.
