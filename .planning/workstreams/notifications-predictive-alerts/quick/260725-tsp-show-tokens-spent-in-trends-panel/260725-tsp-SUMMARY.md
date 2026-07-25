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
  - "trend_sparkline columns are tokens burned per clock hour, not quota % added, scaled 0..peak"
  - "hourly_tokens(records, now) -- the 24 hourly buckets both the graph and its axis label read"
  - "core.trend_scale + snapshot key trend_scale: pre-formatted y-axis top label"
  - "Rust Snapshot.trend_scale: Option<String>, drawn as a left gutter beside the graph"
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

## Follow-up: the graph itself (commit a21ad20)

The text row alone was not what was asked for -- the 24-column graph should show the
tokens. `trend_sparkline` plotted quota-% added per clock hour; it now buckets what
`trend_spent` sums, so a column IS tokens burned in that hour.

Both now attribute an interval to the sample ENDING it, because `burn` is a trailing
rate estimate. Gap/floor semantics unchanged: > `GAP_MAX` contributes 0, an unsampled
hour stays blank (`SPARK_GAP`), a sampled zero-usage hour renders at floor. The
`pct`-specific `RISE_MAX` spike guard is no longer needed here (`burn` is not a
cumulative counter) and stays in `heatmap_buckets` / `despike`, its other two callers.

Alternatives rejected: a second graph below the first (+8 rows, squeezes the sessions
list for a signal that tracks the first closely), and annotating the existing bars
while leaving them meaning quota %.

## Follow-up: the y-axis (commit d7c631a)

A graph with no scale makes a column height mean nothing absolute. The daemon now
sends `trend_scale` -- the tallest hour's tokens, formatted by `fmt_tokens` -- and the
TUI draws it in a left gutter with `0` at the floor.

For that axis to be honest the sparkline had to move from min..max to **0..peak**
scaling. Under min..max the quietest sampled hour always rendered at the floor
(indistinguishable from an idle one) and the bottom of the axis was a value nobody
could see. `hourly_tokens` is split out of `trend_sparkline` so the graph and its label
come from one bucketing, not two.

`trend_scale` is `Option<String>` on the Rust side, not a `Section`: a missing label
costs a label, not a panel. It is sanitized and length-bounded like every other
daemon-built string, and `--once` prints it as `trends: present (y-axis 0..60.0M)`.

## Panel now reads

```
60.0M                    #
      _/_        __/_/#/_//_/_
    0 ##########################
      today 22.8M/hr | wk 18.0M/hr
      spent today 221.0M | wk 888.3M
      peak hour: 14:00 (33.9M/hr)
```

## Verification

- `just selfcheck` — exit 0
- `just lint` — clean
- `just rust-test` — 112 pass (new: trend_scale normalization, the gutter)
- `just rust-lint` — clean
- `just restart` — daemon relaunched on the new code; live snapshot carries
  `trend_scale: 60.0M`

No Rust change: `draw_trends` renders whatever rows the daemon sends and
`trends_panel_height` sizes to content.
