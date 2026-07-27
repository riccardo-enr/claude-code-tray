---
phase: 260727-lns
plan: 01
subsystem: ui
tags: [rust, ratatui, python, socket-wire, sparkline]

requires:
  - phase: 260727-krn
    provides: cum_trend (cumulative-window sparkline) and its Rust rendering path
provides:
  - TREND_INTERVAL cut from 5min to 1min (both trend graphs recompute together)
  - CUM_TREND_INTERVAL cut from 900s to 300s (60 sparkline columns, up from 20)
  - build_cum_trend two-row return: [sparkline, "now NN%  resets in Xh Ym"]
  - core.CUM_TREND_AXIS fixed 100%/57%/0 constant, wired end to end as cum_trend_axis
  - Rust Snapshot.cum_trend_axis, normalized via the existing normalize_trend_axis
  - draw_trends' second graph now renders a real axis instead of a hardcoded None
affects: [rust-client-foundation]

tech-stack:
  added: []
  patterns:
    - "Fixed-ceiling axis as a plain module constant (CUM_TREND_AXIS), not a function like trend_axis() -- nothing to recompute when the ceiling never varies"
    - "Text row appended to a Section<Vec<String>>'s existing wire key (cum_trend[1]) rather than adding a new wire key, since trend_graph_lines already renders trends[1..] verbatim"

key-files:
  created: []
  modified:
    - claude-monitor.py
    - claude_monitor/core.py
    - claude_monitor/test_claude_monitor.py
    - rust/src/snapshot.rs
    - rust/src/main.rs
    - rust/tests/fixtures.rs
    - fixtures/generate.py
    - fixtures/snapshot/cold-start-null-sections.json
    - fixtures/snapshot/cum-trend-populated.json
    - fixtures/README.md

key-decisions:
  - "CUM_TREND_AXIS is a plain constant, not a trend_axis()-style function, because its ceiling (100) never varies"
  - "The text row rides inside the existing cum_trend Section<Vec<String>> as element [1] rather than a new wire key -- trend_graph_lines already renders any row past index 0 verbatim"
  - "Text row reads the newest record's RAW pct (pre-despike), proven by using the spike sample as the newest record in the test -- the text always reflects the true latest sample even when despike() drops it from the sparkline"

patterns-established: []

requirements-completed: [QT-260727-lns]

coverage:
  - id: D1
    description: "Trends panel (both graphs) recomputes every 60s instead of every 300s via one TREND_INTERVAL constant"
    requirement: "QT-260727-lns"
    verification:
      - kind: unit
        ref: "just selfcheck (claude_monitor/test_claude_monitor.py::demo, TREND_INTERVAL value read via daemon module load)"
        status: pass
    human_judgment: false
  - id: D2
    description: "cum_trend sparkline buckets every 5 minutes (60 columns) instead of 15 (20 columns)"
    requirement: "QT-260727-lns"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py demo() cumulative-window-trend assert block (len(_cum[0]) == WIN5 // CUM_TREND_INTERVAL == 60)"
        status: pass
    human_judgment: false
  - id: D3
    description: "'now NN%  resets in Xh Ym' text row appears under the cum_trend sparkline, built from the newest record's raw pct/reset via fmt_countdown"
    requirement: "QT-260727-lns"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py demo() assert _cum[1] == 'now %d%%  %s' % (...)"
        status: pass
    human_judgment: false
  - id: D4
    description: "cum_trend graph has a fixed 100%/57%/0 y-axis (CUM_TREND_AXIS), wired through the daemon socket and normalized in Rust by the existing normalize_trend_axis, rendered by the existing trend_graph_lines"
    requirement: "QT-260727-lns"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py demo() CUM_TREND_AXIS asserts + socket-wire _FakeMonitor test"
        status: pass
      - kind: integration
        ref: "rust/tests/fixtures.rs::every_fixture_produces_its_expected_semantic_state (cum-trend-populated + cold-start-null-sections cum_trend_axis cases)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Both pre-existing safety guarantees hold: a malformed/absent cum_trend or cum_trend_axis degrades only the second graph (D-02); no new dependency/poll/config knob"
    requirement: "QT-260727-lns"
    verification:
      - kind: unit
        ref: "rust cargo test (91+19+4 passing, including pre-existing cum_trend_adds_a_second_graph_below_the_hourly_bars and cum_trend_absent_is_a_true_no_op_on_render_and_layout in main.rs)"
        status: pass
      - kind: other
        ref: "cargo clippy --all-targets -- -D warnings (just rust-lint)"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-07-27
status: complete
---

# Phase 260727-lns: Faster cum_trend refresh, inline countdown text, fixed axis Summary

**Trends panel now recomputes every 60s (was 300s); the cum_trend sparkline buckets every 5min (60 columns, was 15min/20 columns) and gained an inline "now NN%  resets in Xh Ym" text row plus a fixed 100%/57%/0 y-axis, matching the hourly chart's own tick convention end to end through the Rust client.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 2/2 completed
- **Files modified:** 10

## Accomplishments
- `TREND_INTERVAL` dropped from `5 * 60` to `60`, so both `build_trend_rows` and `build_cum_trend` recompute once a minute from the same `poll_loop` gate (`POLL_INTERVAL`, socket/usage polling, untouched).
- `CUM_TREND_INTERVAL` dropped from 900s to 300s: the cum_trend sparkline is now 60 columns across the 5h window (was 20).
- `build_cum_trend` returns a two-element list `[sparkline, text]`; the text row reads the newest record's own (pre-despike) pct/reset via `fmt_countdown` verbatim, the same pattern `tui_usage_rows` already uses.
- New `core.CUM_TREND_AXIS = ["100%", "", "", "57%", "", "", "", "0"]` constant mirrors `trend_axis`'s tick convention (rows = 8, ticked = {top, rows//2, 0}) as a fixed constant, since the ceiling never varies. Cached as `Monitor.cum_trend_axis` and added to the socket snapshot dict.
- Rust `Snapshot` gained `cum_trend_axis: Option<Vec<String>>`, normalized by the existing `normalize_trend_axis` (reused verbatim). `draw_trends`' second `trend_graph_lines` call now passes the real axis instead of a hardcoded `None`, mirroring the first call exactly.
- Fixture corpus extended: `cold-start-null-sections` gains a `cum_trend_axis: null -> absent` pair; `cum-trend-populated` gains a populated `cum_trend_axis` alongside its existing `cum_trend` rows. `rust/tests/fixtures.rs` gained a `check_axis` helper (`Option<Vec<String>>`, no "malformed" state since `normalize_trend_axis` collapses any bad shape straight to `None`).

## Task Commits

Each task was committed atomically:

1. **Task 1: Faster refresh, inline countdown text, and a fixed axis constant (Python)** - `c77efc1` (feat)
2. **Task 2: Wire cum_trend_axis into the Rust client and fixture corpus** - `fcbee4b` (feat)

**Plan metadata:** pending (this SUMMARY + STATE.md commit, made by the orchestrator)

## Files Created/Modified
- `claude-monitor.py` - `TREND_INTERVAL = 60`; `Monitor.cum_trend_axis` field; `compute_trends` populates it; snapshot dict carries `cum_trend_axis`
- `claude_monitor/core.py` - `CUM_TREND_INTERVAL = 300`; new `CUM_TREND_AXIS` constant; `build_cum_trend` returns `[sparkline, text]`
- `claude_monitor/test_claude_monitor.py` - updated cumulative-window-trend assert block (interval-relative offsets, 2-element return, text row, `CUM_TREND_AXIS` shape); socket-wire `_FakeMonitor` gains `cum_trend_axis`
- `rust/src/snapshot.rs` - `Snapshot.cum_trend_axis: Option<Vec<String>>`; `from_value` normalizes it via `normalize_trend_axis`; wire-contract doc updated
- `rust/src/main.rs` - `draw_trends`' second `trend_graph_lines` call now passes `app.snapshot.as_ref().and_then(|s| s.cum_trend_axis.as_deref())`
- `rust/tests/fixtures.rs` - new `check_axis` helper; `"cum_trend_axis"` match arm in `check()`
- `fixtures/generate.py` - `cum_trend_axis` wire/expect pairs added to `cold-start-null-sections` and `cum-trend-populated`
- `fixtures/snapshot/cold-start-null-sections.json`, `fixtures/snapshot/cum-trend-populated.json` - regenerated via `python3 fixtures/generate.py`
- `fixtures/README.md` - `cum_trend_axis` row added to the Expectations table

## Decisions Made
- `CUM_TREND_AXIS` is a plain module-level constant, not a `trend_axis()`-style function, because its ceiling (100) never varies -- there is nothing to recompute at render time (matches plan's stated rationale).
- The text row rides inside the existing `cum_trend` `Section<Vec<String>>` as element `[1]` rather than a new wire key, since `trend_graph_lines` already renders any row past index 0 verbatim -- no Rust change needed for the text itself.
- Text row reads the newest record's RAW pct (pre-despike): the test's newest sample is deliberately the despiked-out spike record, proving the text always reflects the true latest sample independent of whether despike() dropped its own bucket from the sparkline.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Terminal Width Finding (required check, Task 2 `<done>`)

Per the plan's done criteria, I checked the graph area's actual available width against `HEATMAP_WIDTH` (52, from `rust/src/main.rs:92`) rather than silently shipping a graph that might clip its newest columns.

- `HEATMAP_WIDTH + 12 = 64` is the side-by-side threshold (`draw_trends`, `rust/src/main.rs:941`); above it the heatmap renders beside the graph, splitting the trends panel's inner width via `[Constraint::Min(10), Constraint::Length(52)]`.
- The cum_trend graph's gutter width is `len("100%") + 1 = 5` (from `trend_graph_lines`'s `axis_width` calc), so the 60-column sparkline needs `60 + 5 = 65` columns in the left (`Min(10)`) column to render fully un-truncated -- matching the plan's `<done>` math exactly.
- I could not query the user's live interactive Ghostty terminal directly (this execution runs in a non-interactive shell), so I measured the actual tmux panes currently open on this machine as the best available proxy: `tmux list-panes -a` reports pane widths of 95, 119 (the most common, 6 of 10 panes), and 143 columns.
- Panel borders (`Borders::ALL`) cost 2 columns, so `inner.width = pane_width - 2`:
  - **119-col panes (most common):** `inner = 117` -> heatmap shown side-by-side (117 > 64) -> left column = `117 - 52 = 65` columns. This is **exactly** the 65 columns required -- right at the boundary. Any additional per-cell rendering overhead (none observed in the code, but this is a tight fit with zero margin) would clip the newest column.
  - **95-col panes:** `inner = 93` -> still shows heatmap (93 > 64) -> left column = `93 - 52 = 41` columns, well short of 65. The sparkline's rightmost (newest) ~24 columns (roughly the most recent 2 hours of the 5h window) would be truncated by `Paragraph` without `.wrap()`.
  - **143-col panes:** `inner = 141` -> left column = `141 - 52 = 89` columns, comfortably fits.
- **Conclusion:** in the narrower panes actually observed on this machine (95 cols), the newest ~24 columns of the cum_trend sparkline clip. In the most common width (119 cols), the fit is exact with no margin. This is not a regression to fix per the plan (the 300s/60-column interval is a locked decision, and the hourly chart already clips below its own width at these same panel widths) -- flagging it here as the plan's `<done>` section requires, rather than silently shipping a graph that may be missing its most recent data in narrower panes.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- The cum_trend graph is feature-complete for this quick task: faster cadence, inline countdown text, fixed axis, all proven end to end (Python `--selfcheck` + Rust fixture corpus + `cargo clippy`).
- No blockers. The terminal-width finding above is informational, not an open defect against this task's scope.

## Self-Check: PASSED

All 10 modified/created source files and the SUMMARY.md itself confirmed present on disk. Both task commits (`c77efc1`, `fcbee4b`) confirmed present in `git log`. `just selfcheck`, `just lint`, `just rust-test`, and `just rust-lint` all re-run green immediately before this SUMMARY was written.

---
*Phase: 260727-lns*
*Completed: 2026-07-27*
