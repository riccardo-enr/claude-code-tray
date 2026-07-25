---
phase: 260725-tsp
plan: 01
status: complete
subsystem: tui
tags: [python, trends, tokens]

requires: []
provides:
  - "trend_spent(records, start, end) integrates burn over sub-GAP_MAX intervals"
  - "build_trend_rows emits a 'spent today <n> | wk <n>' row"
  - "fmt_tokens has a G tier for counts past 1e9"
affects: []

tech-stack:
  added: []
  patterns:
    - "tokens_used is None on every record since the --api switch (260712-ndo) -- burn (tok/min) is the only surviving token signal, so absolute spend must be integrated from it"
    - "Integrating a rate across a > GAP_MAX hole invents usage: skip the interval so the total stays a floor, not an extrapolation"

key-files:
  created: []
  modified:
    - claude_monitor/core.py
    - claude_monitor/test_claude_monitor.py
---

# Quick Task 260725-tsp: Show tokens spent in the trends panel

## What changed

`claude_monitor/core.py`:
- `trend_spent(records, start, end)` — tokens consumed in a window, integrated from
  `burn` (tok/min) across consecutive samples. Intervals wider than `GAP_MAX` are
  daemon outages, not idle time, and contribute 0. `None` when no interval is
  measurable.
- `build_trend_rows` appends the row between the burn-rate row and the peak hour.
- `fmt_tokens` gains a `G` tier — weekly spend is currently 876M and climbing.

`claude_monitor/test_claude_monitor.py`: asserts on the integration arithmetic, the
gap skip, the single-sample case, the `G` tier, and the new row's position.

## The dead-end worth recording

First implementation summed positive rises in `tokens_used`, mirroring how
`heatmap_buckets` handles the cumulative `pct`. Against the live history it printed
`spent today 0k | wk 2k` next to `today 23.2M/hr` — because quick task 260712-ndo's
`--api` switch dropped absolute token counts: 15907 of 18590 records have
`tokens_used: None`, and the last non-None one predates it. `burn` is the only
token signal still populated.

## Panel now reads

```
today 23.2M/hr | wk 18.0M/hr
spent today 209.8M | wk 876.0M
peak hour: 14:00 (33.9M/hr)
```

## Verification

- `just selfcheck` — exit 0
- `just lint` — clean
- `just restart` — daemon relaunched (pid 1267494) on the new code

No Rust change: `draw_trends` renders whatever rows the daemon sends and
`trends_panel_height` sizes to content.
