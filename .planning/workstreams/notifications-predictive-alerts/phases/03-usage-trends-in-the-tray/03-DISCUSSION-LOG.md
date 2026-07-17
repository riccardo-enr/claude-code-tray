# Phase 3: Usage Trends in the Tray - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-12
**Phase:** 3-usage-trends-in-the-tray
**Areas discussed:** Sparkline construction, Where trends compute, Burn aggregation, Peak hour, Menu layout + empty state

---

## Sparkline construction

### Bucketing
| Option | Description | Selected |
|--------|-------------|----------|
| 24 hourly buckets, mean | One column per hour (24 chars), mean usage% per hour | ✓ |
| 24 hourly buckets, max | Same columns, per-hour peak instead of mean | |
| Fewer, wider buckets | 12/16 columns, coarser | |

### Scaling
| Option | Description | Selected |
|--------|-------------|----------|
| Auto-scale to data range | Map window min..max across 8 block heights; shows shape at low usage | ✓ |
| Fixed 0-100% | Absolute heights; flat/uninformative at low usage | |

### Gaps
| Option | Description | Selected |
|--------|-------------|----------|
| Gap character | Empty hours render as a distinct char; columns stay time-aligned | ✓ |
| Skip empty buckets | Only data columns, packed | |

**User's choice:** 24 hourly buckets (mean), auto-scale, gap character.
**Notes:** Usage often sits ~15%, so fixed scaling would flatten the line — auto-scale was the deciding factor.

---

## Where trends compute

### Compute placement
| Option | Description | Selected |
|--------|-------------|----------|
| In poll_loop, cache strings | Background thread computes + caches; rebuild_menu reads cached strings; no I/O on Gtk main loop | ✓ |
| Read file in usage_rows() | Simpler wiring but file I/O on the Gtk main thread every tick | |

### Cadence
| Option | Description | Selected |
|--------|-------------|----------|
| Every poll | Recompute each ~15-25s poll | |
| Throttled (~5min) | Recompute on a slower cadence, tracking last-compute time | ✓ |

**User's choice:** Compute in poll_loop + cache; recompute on a ~5min throttle.
**Notes:** Claude flagged that the first poll / startup must compute immediately so trend rows are not blank for the first 5 minutes — recorded as D-06.

---

## Burn aggregation

### Metric
| Option | Description | Selected |
|--------|-------------|----------|
| Mean burn rate | Average stored `burn` over window, shown tok/hr | ✓ |
| Total tokens consumed | Integrate burn over elapsed time; noisy with gaps | |
| You decide | Defer to research/planning | |

### Boundaries
| Option | Description | Selected |
|--------|-------------|----------|
| Local calendar | today = since midnight; week = ISO week (Mon start) | ✓ |
| Rolling windows | today = last 24h; week = last 7d | |

**User's choice:** Mean burn rate (tok/hr), local-calendar boundaries.
**Notes:** `tokens_used` resets every 5h window, so a clean daily total isn't directly available — mean rate is the honest metric for the stored data.

---

## Peak hour

### Metric
| Option | Description | Selected |
|--------|-------------|----------|
| Mean usage % | Rank hours by mean pct | |
| Mean burn rate | Rank hours by mean burn | ✓ |
| You decide | Either; one-line change | |

### Count
| Option | Description | Selected |
|--------|-------------|----------|
| Single peak hour | Top hour only | ✓ |
| Top 2-3 hours | Short ranked list | |

**User's choice:** Rank by mean burn rate, single peak hour.
**Notes:** e.g. `peak hour: 15:00 (14.2k tok/hr)`.

---

## Menu layout + empty state

### Layout
| Option | Description | Selected |
|--------|-------------|----------|
| Inline rows, separator above | Trend rows after usage rows, SeparatorMenuItem between | ✓ |
| Trends submenu | 'Trends >' expands to a submenu | |

### Empty state
| Option | Description | Selected |
|--------|-------------|----------|
| Single 'collecting' row | `trends: collecting history…` until enough data | ✓ |
| Render partial | Show whatever exists early | |
| Hide until ready | No trend rows until enough history | |

### Sparkline row
| Option | Description | Selected |
|--------|-------------|----------|
| Short prefix | e.g. `24h ▁▂▃▅▇` | |
| Bare sparkline | Just the blocks | ✓ |

**User's choice:** Inline rows with separator above; 'collecting' empty-state row; bare sparkline (no prefix).
**Notes:** Sparkline row is bare; the today/week and peak rows still carry labels.

---

## Claude's Discretion

- Exact gap glyph for empty sparkline hours.
- Row wording/format for today/week burn and peak-hour rows.
- Precise throttle constant (~5min) and the "enough data" threshold for the empty-state cutover.
- Whether trend logic lives as module-level helpers (preferred, `demo()`-testable) vs methods.

## Deferred Ideas

- TREND-F1 — configurable sparkline window / aggregation period.
- HIST-F1 — raw data export (CSV/JSON).
- Integrated "total tokens consumed" burn view — considered and deferred in favor of mean rate.
