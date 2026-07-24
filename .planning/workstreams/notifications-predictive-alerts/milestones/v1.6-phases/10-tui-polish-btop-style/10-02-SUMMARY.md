---
phase: 10-tui-polish-btop-style
plan: 02
subsystem: ui
tags: [tui, textual, rich, btop, ansi-dark, trends, sparkline, spark-levels]

# Dependency graph
requires:
  - phase: 10-tui-polish-btop-style
    plan: 01
    provides: "core.band green->red ramp reused to color the trends graph by height"
  - phase: 09-terminal-dashboard-claude-tui-py
    provides: "build_trend_rows / trend_sparkline output (the 24-char SPARK_GLYPHS sparkline) + claude-tui.py render_all #trends seam"
provides:
  - "core.spark_levels(sparkline): pure inverse of the SPARK_GLYPHS mapping (glyph -> level 0..7, gap/unknown -> None)"
  - "claude-tui.py trends panel: TREND_ROWS-tall decoded height-colored block column graph, band-colored green->red, above the unchanged today/wk/peak text rows"
affects: [10-03, sessions-table, tui-polish]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Assertable-in-core / render-only-in-claude-tui.py split reused: spark_levels proven by --selfcheck, the colored column graph drawn in the textual file"
    - "The decoded level IS the column height -- no separate height function; band(level/7*100) colors the whole column by its own height along the shared ramp"
    - "None columns (SPARK_GAP or malformed byte) stay blank, preserving the time-aligned gaps and never indexing past the ramp (T-10-03)"

key-files:
  created: []
  modified:
    - claude_monitor/core.py
    - claude_monitor/test_claude_monitor.py
    - claude-tui.py

key-decisions:
  - "spark_levels is a one-line dict-inverse lookup (_SPARK_LEVEL = {g:i}); .get returns None for SPARK_GAP and any unknown char, so it is total and tolerant with no try/except (D-06)"
  - "TREND_ROWS=8: a decoded level L fills rows 0..L from the bottom (L+1 cells), so level 7 fills the full column and level 0 shows the single lowest block -- a low-but-present hour never looks blank like a real gap (reading of D-05/D-06 that keeps level-0 visually distinct from a None gap)"
  - "Each column colored by its own height band(level/7*100), not per-row, so a tall column reads red top-to-bottom and a short one green -- btop height-graph, one shared palette with the usage gauge (10-01)"
  - "Falsy trends preserved verbatim: _trends_renderable returns core.trend_text(trends) ('trends: collecting history...') and never calls spark_levels (D-07)"

patterns-established:
  - "core.spark_levels is the reusable decode seam for any future decoded-sparkline visual; the block-column render helper (_trends_renderable) mirrors 10-01's _usage_renderable"

requirements-completed: [TUI-08]

coverage:
  - id: D1
    description: "core.spark_levels round-trips all 8 SPARK_GLYPHS levels, decodes SPARK_GAP and unknown chars to None, and a real trend_sparkline output to 24 ints-0..7-or-None"
    requirement: "TUI-08"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py# --- tui spark levels (TUI-08) --- (via just selfcheck)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Trends panel renders a taller, height-colored (green->red) multi-row block column graph decoded from trends[0], with the today/wk/peak text rows unchanged below; empty history shows the collecting message and does not crash"
    requirement: "TUI-08"
    verification:
      - kind: manual_procedural
        ref: "just tui with history built up: taller colored column graph (green->red by column height) above the today/wk/peak lines; fresh/empty history shows 'trends: collecting history...' and does not crash"
        status: unknown
    human_judgment: true
    rationale: "Whether the decoded column graph reads correctly (height coloring, gaps, taller layout) against the terminal's inherited ANSI-16 palette is a visual judgment; no daemon/desktop is reachable from the executor to run just tui. Shares 10-01 D3's deferred palette check."

# Metrics
duration: 5min
completed: 2026-07-24
status: complete
---

# Phase 10 Plan 02: Richer Trends Graph (TUI-08) Summary

**core.spark_levels inverts the SPARK_GLYPHS ramp (glyph -> level 0..7, gap/unknown -> None), and claude-tui.py draws the decoded levels as an 8-row block column graph colored green->red by column height -- a btop-style taller trends graph with zero new trend data, sharing 10-01's usage-gauge palette.**

## Performance

- **Duration:** ~5 min
- **Completed:** 2026-07-24
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- `core.spark_levels(sparkline)` -- pure inverse of the exact `SPARK_GLYPHS` mapping `trend_sparkline` uses: each glyph decodes to its index 0..7, `SPARK_GAP` and any unrecognized/hostile character decode to `None`. One-line dict lookup (`_SPARK_LEVEL.get(ch)`), total and tolerant, never raises or indexes past the ramp (T-10-03). No new trend math, no new series, no new snapshot field (D-06). Stdlib-only, core gained no textual/rich import.
- `--selfcheck` asserts under a new `# --- tui spark levels (TUI-08) ---` block: full-ramp round-trip `spark_levels(SPARK_GLYPHS) == [0,1,2,3,4,5,6,7]`, `SPARK_GAP -> [None]`, unknown-char `-> [None]`, and a real `trend_sparkline` output decoding to 24 elements each `int 0..7 or None` (level 0 / 7 / None positions cross-checked against the existing spark asserts).
- `claude-tui.py` trends panel now renders a `TREND_ROWS`-tall (8-row) decoded block column graph: column i filled from the bottom up to its decoded level, each filled cell colored by that column's height along the same green->red `core.band` ramp as the usage gauge; `None` columns stay blank, preserving the time-aligned gaps. The `today/wk` and `peak hour` text rows (`trends[1:]`) render below unchanged (D-05).
- Degraded/collecting state preserved: `_trends_renderable` returns `core.trend_text(trends)` ("trends: collecting history...") whenever `trends` is falsy and never calls `spark_levels` (D-07).
- `just selfcheck` exits 0 on stock `/usr/bin/python3`; `just lint` clean; `claude-tui.py` byte-compiles.

## Task Commits

Each task committed atomically (test asserts + implementation together, so the green gate never committed a red state):

1. **Task 1: core.spark_levels decode + selfcheck asserts** - `500761e` (feat)
2. **Task 2: decoded height-colored trends column graph** - `cfa2654` (feat)

**Plan metadata:** see final `docs(10-02)` commit.

## Files Created/Modified
- `claude_monitor/core.py` - Added `_SPARK_LEVEL` inverse map and pure `spark_levels(sparkline)` next to `trend_sparkline`, above the textual boundary; stdlib-only.
- `claude_monitor/test_claude_monitor.py` - Imported `spark_levels`; new `# --- tui spark levels (TUI-08) ---` assert block under `demo()`.
- `claude-tui.py` - `TREND_ROWS=8` constant; `_trends_renderable` helper decoding `trends[0]` into the colored block column graph; `render_all` pushes the Text renderable to `#trends`.

## Decisions Made
- `TREND_ROWS=8`, level L fills rows 0..L (L+1 cells): level 7 fills the full column, level 0 shows the single lowest block. This keeps a low-but-present hour visually distinct from a real `None` gap (which stays blank), mirroring `SPARK_GLYPHS[0]="▁"` vs `SPARK_GAP=" "`.
- Each column colored by its own height `band(level/7*100)` (not per-row position, unlike the gauge which colors by bar position) -- height coloring is the honest signal for a graph column; both share the one green->red palette so the dashboard reads as one system.
- Block glyph `U+2588` used directly, consistent with 10-01's gauge and the existing `SPARK_GLYPHS` block ramp. (Global ASCII-only rule targets prose/math symbols; the block glyph IS the requested visual deliverable.)
- No CSS added: `#trends` is `height:auto` and grows to fit the taller graph; band tokens are ANSI style names resolved under `self.theme=ansi-dark`, no class map needed.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None. Both gates (`just selfcheck` exit 0, `just lint` clean) passed on the first run after each task; `claude-tui.py` byte-compiles. The graph algorithm was sanity-checked headlessly against a real `trend_sparkline` output (core only, no textual): level-0 column drew one bottom cell, level-7 drew the full 8-cell column, interior gap stayed blank.

## Known Stubs
None.

## Deferred Human-Check
Coverage **D2** (`human_judgment: true`): the live-TUI read of the decoded column graph -- height coloring, taller layout, gap preservation, and the collecting message on empty history -- requires `just tui` with the daemon running inside a desktop session, which the executor cannot run (directed not to `just restart`). Confirm via `/gsd-verify-work`. Shares 10-01 D3's deferred ANSI-16 palette check; do both together.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `core.spark_levels` and `_trends_renderable` join 10-01's `band`/`_gauge` seam as the reusable btop-visual toolkit; 10-03 (sessions table / panels, TUI-09/10) reuses the same `core.band` palette.
- Open item: the D2 live-TUI graph read (deferred human-check above), bundled with 10-01's D3 palette check.

## Self-Check: PASSED
- Files verified present: claude_monitor/core.py, claude-tui.py, 10-02-SUMMARY.md
- Commits verified in history: 500761e (Task 1), cfa2654 (Task 2)

---
*Phase: 10-tui-polish-btop-style*
*Completed: 2026-07-24*
