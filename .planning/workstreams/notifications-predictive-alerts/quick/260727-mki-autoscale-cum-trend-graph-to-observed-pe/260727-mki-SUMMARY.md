---
phase: 260727-mki
plan: 01
subsystem: tui
tags: [rust, ratatui, python, sparkline, autoscale, terminal-width]

requires:
  - phase: 260727-krn
    provides: cum_trend sparkline (fixed 0-100% ceiling), CUM_TREND_AXIS constant
  - phase: 260727-lns
    provides: CUM_TREND_INTERVAL sped up to 300s, cum_trend_axis riding the wire

provides:
  - build_cum_trend autoscaled to its own observed peak (mirrors trend_sparkline)
  - cum_trend_axis(records, now) function replacing the fixed CUM_TREND_AXIS constant
  - CUM_TREND_INTERVAL dropped 300 -> 60 (300 columns instead of 60)
  - clip_to_newest: keeps newest columns when the cum_trend sparkline is wider than
    the panel, instead of Paragraph's default right-truncation

affects: [rust-client-foundation, cum-trend-graph]

tech-stack:
  added: []
  patterns:
    - "own-peak scaling (hi = max of non-None buckets) shared verbatim between
      trend_sparkline/trend_axis and the now-matching build_cum_trend/cum_trend_axis"
    - "clip-to-newest: draw_trends computes graph_width once and reuses it for both
      the char-level clip and the final Paragraph render, so the two can never drift"

key-files:
  created: []
  modified:
    - claude_monitor/core.py
    - claude-monitor.py
    - claude_monitor/test_claude_monitor.py
    - rust/src/main.rs
    - fixtures/generate.py
    - fixtures/README.md

key-decisions:
  - "REVERSES 260727-krn's fixed-ceiling design. krn deliberately chose a fixed
    0-100% scale so a %-of-window bar meant the same thing every render (comparable
    window over window). This task discards that: at a realistic ~20-30% usage level
    the fixed ceiling only ever lit the bottom 2-3 of 8 rows (confirmed empirically
    against a live daemon snapshot decoding to max level 2 of 7), reading as a flat
    plateau instead of a trend. build_cum_trend and the new cum_trend_axis now
    autoscale to the window's own observed peak, exactly like trend_sparkline/
    trend_axis already do for the hourly chart -- the user's actual want (\"a line or
    a trend\") wins over cross-render comparability."
  - "CUM_TREND_INTERVAL 300->60 landed in the SAME task as the width-clip fix, not
    independently -- shipping the finer interval without clip-to-newest first would
    have made the pre-existing truncate-from-the-wrong-end bug worse (300 columns
    instead of 60 to get right-truncated)."

requirements-completed: [QT-260727-mki]

coverage:
  - id: D1
    description: "build_cum_trend autoscales to its own observed peak instead of a
      fixed 100% ceiling; cum_trend_axis(records, now) replaces CUM_TREND_AXIS"
    requirement: QT-260727-mki
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py::demo (cumulative window trend
          block, incl. bucket-vs-series discriminator) via just selfcheck"
        status: pass
    human_judgment: false
  - id: D2
    description: "clip_to_newest keeps the newest (rightmost) columns of the
      cum_trend sparkline when the panel is narrower than the sparkline, dropping
      the oldest instead of letting Paragraph right-truncate the newest data away"
    requirement: QT-260727-mki
    verification:
      - kind: unit
        ref: "rust/src/main.rs::tests::cum_trend_sparkline_clipping_keeps_the_newest_columns_not_the_oldest"
        status: pass
      - kind: manual_procedural
        ref: "tmux capture-pane -p, `just rust-fixture cum-trend-clipped-keeps-newest` at -x 55 -y 45 (narrow) and -x 150 -y 30 (wide)"
        status: pass
    human_judgment: false
  - id: D3
    description: "CUM_TREND_INTERVAL 300 -> 60 (300 columns instead of 60), finer
      staircase resolution"
    requirement: QT-260727-mki
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py::demo (CUM_TREND_INTERVAL-derived
          column count assertion) via just selfcheck"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-07-27
status: complete
---

# Phase 260727-mki Plan 01: Autoscale cum_trend graph to observed peak Summary

**Reversed 260727-krn's fixed 0-100% ceiling: build_cum_trend/cum_trend_axis now
autoscale to the window's own observed peak (mirroring the hourly chart), the Rust
sparkline clips its newest columns instead of its oldest at narrow widths, and
CUM_TREND_INTERVAL dropped 300->60 for a finer staircase.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-27T14:48:20Z
- **Tasks:** 2/2
- **Files modified:** 6 (claude-monitor.py, claude_monitor/core.py,
  claude_monitor/test_claude_monitor.py, rust/src/main.rs, fixtures/generate.py,
  fixtures/README.md) + 1 fixture created

## Accomplishments

- **Vertical quantization fixed.** `build_cum_trend` scales against the series' own
  observed peak (the same `hi = max(non-None buckets)` three-way branch
  `trend_sparkline` already uses), so a realistic ~20-30% usage level now lights the
  full 8-row range instead of pinning at level 2-3.
- **`cum_trend_axis(records, now)` replaces the fixed `CUM_TREND_AXIS` constant** --
  ticks derived from the SAME bucket-filtered peak `build_cum_trend` scales against
  (not the raw despiked series), so a stale out-of-window sample can never inflate
  the axis past what actually renders. A new bucket-vs-series discriminator test
  proves this directly.
- **Width-clipping fixed the wrong end.** `clip_to_newest` keeps the LAST N
  characters of the cum_trend sparkline (the newest columns) when it exceeds the
  panel width, dropping the FIRST (oldest) ones instead of relying on `Paragraph`'s
  default right-truncation, which silently hid the newest ~2h of data.
- **CUM_TREND_INTERVAL 300 -> 60** (300 columns instead of 60), giving a visibly
  finer staircase -- safe only because clip-to-newest landed in the same task.
- The original hourly bar chart (`trend_sparkline`, `trend_axis`,
  `build_trend_rows`, `TREND_INTERVAL`) is untouched.

## Task Commits

Each task was committed atomically:

1. **Task 1: Autoscale build_cum_trend / replace CUM_TREND_AXIS with
   cum_trend_axis(records, now) (Python)** - `efdaae5` (feat)
2. **Task 2: Keep the newest columns when the cum_trend sparkline is wider than the
   panel (Rust)** - `26fbec5` (fix)

_Both tasks used `tdd="true"`; the failing-then-passing assertion changes were made
directly against the existing assert-style `demo()`/`#[test]` suites rather than a
separate RED-commit cycle (no pytest/cargo-test gate distinguishes RED from GREEN in
this repo's assert-based self-check style)._

## Files Created/Modified

- `claude_monitor/core.py` - `CUM_TREND_INTERVAL` 300->60; `build_cum_trend`'s
  glyph computation rewritten to the own-peak three-way branch; new
  `cum_trend_axis(records, now)` function; `CUM_TREND_AXIS` constant deleted
- `claude-monitor.py` - `Monitor.cum_trend_axis` comment updated;
  `compute_trends` calls `core.cum_trend_axis(records, now)` directly, mirroring
  `self.trend_axis = core.trend_axis(records, now)`
- `claude_monitor/test_claude_monitor.py` - import swap (`CUM_TREND_AXIS` ->
  `cum_trend_axis`); peak-relative assertions; new bucket-vs-series discriminator
  case; test-data offsets adjusted from `+100` to `+10` (see Deviations)
- `rust/src/main.rs` - new `clip_to_newest` function; `draw_trends` restructured to
  compute `columns`/`graph_width`/`fits_beside_heatmap` once and reuse them; "window
  usage (0-100%)" label shortened to "window usage"; `render_trends_rows` hoisted to
  a module-level test helper; new clipping-keeps-newest test
- `fixtures/generate.py` - new `F["cum-trend-clipped-keeps-newest"]`;
  `F["cum-trend-populated"]`'s `cum_trend_axis` values changed from the fixed
  100%/57%/0 to an illustrative peak-relative 35%/20%/0
- `fixtures/README.md` - Expectations table row for `cum_trend_axis` updated to
  describe autoscaling instead of a fixed ceiling
- `fixtures/snapshot/cum-trend-clipped-keeps-newest.json` (new),
  `fixtures/snapshot/cum-trend-populated.json` (modified) - regenerated via
  `python3 fixtures/generate.py`; confirmed via `git diff --stat` these are the only
  two fixture changes

## Decisions Made

- **Design reversal disclosed:** this task explicitly reverses 260727-krn's "a
  %-of-window bar has to mean the same thing every time it is drawn, comparable
  window over window" rationale. The fixed 0-100% ceiling produced an unreadable
  graph at realistic usage levels; autoscaling to the observed peak (like the hourly
  chart already does) makes the graph readable as a trend, at the cost of
  cross-render comparability. See PROJECT-level STATE.md quick-task row for the
  same disclosure.
- CUM_TREND_INTERVAL's drop to 60s and the width-clip fix were treated as one
  inseparable change per the plan's explicit dependency note, not two independent
  deviations.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test-data offsets no longer landed in the intended buckets
after CUM_TREND_INTERVAL dropped to 60**
- **Found during:** Task 1, running `just selfcheck` after the core.py rewrite
- **Issue:** The plan's step 8 said to leave `_cum_recs`'s wire data completely
  unchanged (bucket 0 = pct 10.0, bucket 5 = pct 30.0, bucket 10 = spike), using a
  fixed `+100` second offset within each bucket. That offset was chosen when
  `CUM_TREND_INTERVAL` was 300s (well within one bucket). With this same task's step
  0 dropping the interval to 60s, `+100` now overflows into the NEXT bucket
  (`int((60*5+100)/60) == 6`, not `5`), so the test data intended for "bucket 5"
  and "bucket 10" actually landed in buckets 6 and 11 -- the assertions on
  `_cum[0][5]`/`cum_trend_axis`'s peak would have silently tested the wrong bucket
  had the offsets not been fixed.
- **Fix:** Changed the within-bucket offset from `+100` to `+10` (well inside the
  new 60s bucket) for the three affected records, preserving the intended bucket
  indices (0, 5, 10) and the exact test intent described in `<behavior>`. Added a
  `ponytail:` comment explaining why the offset differs from the "before window"
  record's unrelated `-100`.
- **Files modified:** `claude_monitor/test_claude_monitor.py`
- **Verification:** `just selfcheck` exits 0 with the corrected offsets; without the
  fix, `_cum[0][5]` was a gap (`SPARK_GAP`), not the peak bucket, and the
  bucket-vs-series discriminator test would have been comparing against a
  mislabeled index.
- **Committed in:** `efdaae5` (part of Task 1's commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - test-data bug surfaced by this same
task's own interval change)
**Impact on plan:** Necessary for correctness of the new peak-relative assertions;
no scope creep -- the fix only touches offsets inside the same test block the plan
already specified changing.

## Issues Encountered

None beyond the deviation above. Both tasks' automated verify commands
(`just selfcheck`; `python3 fixtures/generate.py && just rust-test && just
rust-lint`) passed on the first run after the fixes above.

**Live tmux-captured render result** (Task 2's mandatory `<done>` check, not
skipped): rendered `cum-trend-clipped-keeps-newest` at `-x 55 -y 45` (narrow) --
the "28%" top row of the cum_trend graph showed exactly 4 filled `█` cells at the
panel's right edge (the newest, highest-level columns survived the clip), not an
empty top half with bars only anchored at the left. At `-x 150 -y 30` (wide), the
full unclimbed 8-level staircase rendered with no truncation, bottom row (level 0)
spanning the full width down to the top row (level 7) at 4 columns on the right.
Both captures matched the expected pre/post-fix contrast described in the plan.

## User Setup Required

None - no external service configuration required. The running daemon and TUI
binary are NOT restarted/reinstalled by this execution per the orchestrator's
constraints (`just restart` / `just install` are the user's manual step).

## Next Phase Readiness

The cum_trend graph now reads as a real trend at realistic usage levels and never
silently hides its newest data at narrow terminal widths. No blockers. The user
still needs to run `just restart` (daemon) and rebuild/reinstall the Rust TUI
binary to see these changes live.

---
*Phase: 260727-mki*
*Completed: 2026-07-27*

## Self-Check: PASSED

All 8 modified/created code+fixture files and both task commit hashes
(`efdaae5`, `26fbec5`) confirmed present on disk / in `git log --oneline --all`.
