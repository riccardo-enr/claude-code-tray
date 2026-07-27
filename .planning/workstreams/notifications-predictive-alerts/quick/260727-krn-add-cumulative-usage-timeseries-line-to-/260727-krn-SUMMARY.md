---
phase: 260727-krn
plan: 01
subsystem: tui
tags: [rust, ratatui, python, sparkline, quota-monitoring]

requires:
  - phase: 260725-tsp
    provides: trend_graph_lines / trend_sparkline / SPARK_GLYPHS / SPARK_GAP rendering path this plan calls a second time
provides:
  - core.build_cum_trend (daemon-side cumulative-window sparkline builder)
  - cum_trend wire key end-to-end (daemon -> socket snapshot -> Rust normalize -> TUI render)
affects: [rust-client-foundation, notifications-predictive-alerts]

tech-stack:
  added: []
  patterns:
    - "Second independent Section<Vec<String>> graph reusing an existing normalize/render function verbatim instead of writing a parallel one"

key-files:
  created:
    - fixtures/snapshot/cum-trend-populated.json
  modified:
    - claude_monitor/core.py
    - claude-monitor.py
    - claude_monitor/test_claude_monitor.py
    - rust/src/snapshot.rs
    - rust/tests/fixtures.rs
    - fixtures/generate.py
    - fixtures/README.md
    - rust/src/main.rs

key-decisions:
  - "CUM_TREND_INTERVAL (900s) is a hardcoded constant next to GAP_MAX/RISE_MAX, not a config knob (YAGNI, per project convention)"
  - "The new sparkline is scaled against a FIXED 0..100% ceiling, unlike trend_sparkline's own-peak scale, so a bar means the same thing window over window"
  - "Window boundary is anchored on the newest record's own `reset` field, not wall-clock now -- the function does not need `now` for its math, only accepts it for call-site symmetry with build_trend_rows/trend_axis"
  - "rust normalize_trends is reused verbatim for cum_trend (no normalize_cum_trend written); check_trends generalized to take a Section + name so one runner proves both keys"
  - "draw_trends calls trend_graph_lines a second time unmodified (axis: None); the function itself was never touched"

patterns-established:
  - "A new Section<Vec<String>> wire key that is shape-identical to an existing one is wired through the SAME normalize function, proven by generalizing the existing fixture-corpus checker rather than writing a parallel one"

requirements-completed: [QT-260727-krn]

coverage:
  - id: D1
    description: "core.build_cum_trend bucketizes pct into 20 15-min columns anchored on the current 5h window, despiked, fixed-100 ceiling, None while collecting"
    requirement: "QT-260727-krn"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py demo() cumulative window trend asserts (just selfcheck)"
        status: pass
    human_judgment: false
  - id: D2
    description: "cum_trend wired onto Monitor.compute_trends and the socket snapshot dict end-to-end"
    requirement: "QT-260727-krn"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py socket-wire _FakeMonitor test (just selfcheck)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Rust Snapshot.cum_trend normalized via the existing normalize_trends (absent/malformed/hostile-controls all covered by fixtures)"
    requirement: "QT-260727-krn"
    verification:
      - kind: integration
        ref: "rust/tests/fixtures.rs corpus runner (just rust-test), fixtures cold-start-null-sections/partial-sections/cum-trend-populated"
        status: pass
    human_judgment: false
  - id: D4
    description: "Second sparkline renders below the existing hourly bar chart, additive only, byte-identical no-op when cum_trend is absent"
    requirement: "QT-260727-krn"
    verification:
      - kind: unit
        ref: "rust/src/main.rs cum_trend_adds_a_second_graph_below_the_hourly_bars, cum_trend_absent_is_a_true_no_op_on_render_and_layout (just rust-test)"
        status: pass
    human_judgment: false

duration: 9min
completed: 2026-07-27
status: complete
---

# Phase 260727-krn: Cumulative usage timeseries line Summary

**A second, independent sparkline in the Rust TUI's trends panel shows cumulative usage within the CURRENT rolling 5h quota window (sampled every 15 min, fixed 0-100% scale), wired daemon-to-terminal by reusing every existing sanitizer/renderer verbatim -- no new normalize function, no new poll, no new config knob.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-07-27T15:12:17+02:00 (plan-dispatch commit)
- **Completed:** 2026-07-27T15:21:10+02:00
- **Tasks:** 3
- **Files modified:** 11 (10 modified, 1 created)

## Accomplishments
- `core.build_cum_trend(records, now)`: bucketizes the current window's `pct` samples into `WIN5 // CUM_TREND_INTERVAL` (20) 15-minute columns, despiked via the existing `despike()`, scaled against a fixed 0..100% ceiling (not the window's own peak like `trend_sparkline`), `None` while collecting -- returns the same one-element `Section<Vec<String>>` shape `trends` already has.
- Wired onto the existing daemon path with zero new plumbing: `Monitor.cum_trend` computed in `compute_trends` alongside `trend_axis`, passed through `_handle_conn`'s snapshot dict unchanged.
- Rust `Snapshot.cum_trend: Section<Vec<String>>` normalized by the EXISTING `normalize_trends` verbatim (no `normalize_cum_trend` written); `check_trends` generalized from a `Snapshot`-typed helper to a `Section` + name helper so the shared fixture-corpus runner proves both `trends` and `cum_trend` with one function.
- Three fixture cases: `cold-start-null-sections` (null -> absent), `partial-sections` (`[42]` -> malformed, alongside surviving usage/heatmap/sessions -- D-02 proof), and new `cum-trend-populated` (a real row survives verbatim; an OSC-52 clipboard-write + BEL row comes back with its control characters replaced).
- Rust renderer: `snapshot_cum_trend` mirrors `snapshot_trends`; `trends_panel_height` grows by `1 + TREND_ROWS + cum.len() - 1` only when cum_trend is present; `draw_trends` pushes a dim "window usage (0-100%)" label then calls the UNMODIFIED `trend_graph_lines` a second time (`axis: None`). Both additions are strictly additive and proven so: the existing bar chart's rows render byte-identically with or without `cum_trend`, and the pre-existing height formula (`TREND_ROWS + trends.len() - 1 + 2`) holds exactly when it is absent.

## Task Commits

Each task was committed atomically:

1. **Task 1: Daemon computes the cumulative-window sparkline and puts it on the wire** - `5f932e1` (feat)
2. **Task 2: Rust normalizes cum_trend through the existing trends path, plus fixtures** - `4cc5bb5` (feat)
3. **Task 3: Render cum_trend as a second graph under the existing bar chart** - `f66f8cb` (feat)

_No separate TDD RED/GREEN/REFACTOR commits were made -- each task's new asserts/tests were written and verified green in the same commit as the implementation (behavior + verification landed atomically per the task's `<verify>` gate)._

## Files Created/Modified
- `claude_monitor/core.py` - `CUM_TREND_INTERVAL` constant + `build_cum_trend()` (right after `despike()`, before `usage7_series`)
- `claude-monitor.py` - `Monitor.cum_trend` cache field, computed in `compute_trends`, exposed in `_handle_conn`'s snapshot dict
- `claude_monitor/test_claude_monitor.py` - new asserts for `build_cum_trend` (empty, no-reset, bucketing/last-wins, despike rejection, before-window exclusion) + socket-wire `cum_trend` coverage
- `rust/src/snapshot.rs` - wire-contract doc, `Snapshot.cum_trend: Section<Vec<String>>`, normalized via existing `normalize_trends`
- `rust/tests/fixtures.rs` - `check_trends` generalized to `(section, expected, name)`; `"cum_trend"` match arm added
- `fixtures/generate.py` - `cum_trend` added to `cold-start-null-sections` and `partial-sections`; new `cum-trend-populated` fixture
- `fixtures/snapshot/cold-start-null-sections.json`, `fixtures/snapshot/partial-sections.json` - regenerated
- `fixtures/snapshot/cum-trend-populated.json` - new fixture (created)
- `fixtures/README.md` - `cum_trend` row added to the Expectations table
- `rust/src/main.rs` - `snapshot_cum_trend`, `trends_panel_height` additive growth, `draw_trends` second-graph push, two new render tests

## Decisions Made
- `CUM_TREND_INTERVAL = 900` is a fixed constant beside `GAP_MAX`/`RISE_MAX`, deliberately not a config surface (ponytail note in code names the upgrade path).
- Fixed 0..100% ceiling instead of a peak-relative scale, so the bar is comparable window over window (docstring states why, mirroring the plan's rationale).
- The function accepts `now` for call-site symmetry with `build_trend_rows`/`trend_axis` but does not use it -- the window boundary comes from the newest record's own `reset`, not wall-clock time.
- Test 1 in Task 3 verifies additivity by comparing the rendered row text of the shared bar-chart region (not raw sparkline glyph characters, since `trend_graph_lines` redraws sparkline levels as a colored block grid rather than echoing the daemon's glyphs verbatim) -- this is a more faithful proof of "byte-identical when cum_trend is absent" than a literal-glyph substring check.

## Deviations from Plan

None - plan executed exactly as written. One test-authoring correction made during Task 1 (pct rise sized so the middle sample is kept, not rejected by `despike()`, before deliberately spiking the third sample past `RISE_MAX`) and one during Task 3 (assert on rendered row equality rather than literal sparkline glyph substrings, since the renderer decodes glyphs to levels and redraws them as blocks) -- both are test-construction fixes within the same task, not scope changes, and required no re-planning.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The `cum_trend` wire key, Rust `Section<Vec<String>>` field, and rendered second graph are all live and covered by `just selfcheck` + `just rust-test` + `just rust-lint`.
- Run `just restart` (user's manual step, not run by this task) to see the new sparkline live once a poll has landed at least one sample inside the current window.

---
*Phase: 260727-krn*
*Completed: 2026-07-27*

## Self-Check: PASSED

All 9 modified/created files and all 3 task commits (5f932e1, 4cc5bb5, f66f8cb) verified present.
