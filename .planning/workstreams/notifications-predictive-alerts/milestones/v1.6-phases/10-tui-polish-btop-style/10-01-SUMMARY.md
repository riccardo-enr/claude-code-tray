---
phase: 10-tui-polish-btop-style
plan: 01
subsystem: ui
tags: [tui, textual, rich, btop, ansi-dark, gauge, threshold-bands]

# Dependency graph
requires:
  - phase: 09-terminal-dashboard-claude-tui-py
    provides: claude-tui.py render_all + core.tui_usage_rows single-source-of-truth formatters
provides:
  - "core.band(pct): fixed three-band proximity classifier (green/yellow/red), pure and total"
  - "core.gauge_fill(pct, width): clamped filled-cell count for a gradient gauge bar"
  - "claude-tui.py usage panel: per-cell green->yellow->red gradient gauge + band-colored %/burn/countdown for the 5h and 7d caps"
affects: [10-02, trends-graph, sessions-table, tui-polish]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Assertable-in-core / render-only-in-claude-tui.py split (band+gauge_fill proven by --selfcheck; glyphs/colors applied in the textual file)"
    - "Band token doubles as a rich/ANSI style name so the render side needs no translation table (reads under self.theme=ansi-dark 16-color palette)"
    - "Pre-formatted core row strings are split back into cells for per-segment coloring rather than reformatted (preserves D-05 single-source-of-truth)"

key-files:
  created: []
  modified:
    - claude_monitor/core.py
    - claude_monitor/test_claude_monitor.py
    - claude-tui.py

key-decisions:
  - "band cutoffs are literals (<70/70-<90/>=90), deliberately separate from the mutable badge USAGE_THRESHOLD (D-01)"
  - "gauge width fixed at GAUGE_WIDTH=20 cells (module constant in claude-tui.py); fill count computed in core.gauge_fill (D-04)"
  - "gauge cells colored by POSITION (band(cell/width*100)) so the bar always sweeps green->yellow->red regardless of fill level (btop meter, D-03)"
  - "filled block glyph U+2588, empty track U+2591 dim -- consistent with existing core.SPARK_GLYPHS block ramp"

patterns-established:
  - "Gauge/band render helpers (_gauge, _cap_row_text, _usage_renderable) are the reusable seam for the remaining TUI-08/09/10 visuals"

requirements-completed: [TUI-06, TUI-07]

coverage:
  - id: D1
    description: "core.band(pct) three-band proximity classifier with literal cutoffs, total over out-of-range input"
    requirement: "TUI-06"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py# --- tui band (TUI-06) --- (via just selfcheck)"
        status: pass
    human_judgment: false
  - id: D2
    description: "core.gauge_fill(pct, width) clamped, monotonic filled-cell count (0 at 0%, width at 100%, no overflow >100%)"
    requirement: "TUI-07"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py# --- tui gauge fill (TUI-07) --- (via just selfcheck)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Usage panel renders a per-cell green->yellow->red gradient gauge for the 5h and 7d rows with %/burn/countdown text band-colored by cap proximity, under ansi-dark"
    requirement: "TUI-06"
    verification:
      - kind: manual_procedural
        ref: "just tui with the daemon running: both rows show a gradient gauge whose fill tracks the percent; %/burn/countdown are band-colored; colors read as terminal ANSI, not washed-out RGB"
        status: unknown
    human_judgment: true
    rationale: "Whether the per-cell gradient reads correctly against the terminal's inherited ANSI-16 palette is a visual judgment; no daemon/desktop is reachable from the executor to run just tui. This is the phase tracer's de-risking check."

# Metrics
duration: 3min
completed: 2026-07-24
status: complete
---

# Phase 10 Plan 01: Usage Panel btop Signals Summary

**core.band proximity classifier + core.gauge_fill cell-count, wired into a per-cell green->yellow->red gradient gauge and band-colored %/burn/countdown for the 5h and 7d caps -- the phase tracer proving the core -> --selfcheck -> ansi-dark render pipeline.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-07-24T09:56:36Z
- **Completed:** 2026-07-24T09:59:37Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- `core.band(pct)` -- fixed btop three-band classifier (<70 green / 70-<90 yellow / >=90 red), pure, total over out-of-range/negative input, cutoffs are literals kept separate from the mutable badge `USAGE_THRESHOLD` (D-01).
- `core.gauge_fill(pct, width)` -- clamps pct to 0..100 then rounds to a filled-cell count: 0 at 0%, `width` at 100%, monotonic, never overflows past `width` on an over-limit percent (D-04, T-10-01 mitigation).
- Usage panel now renders each cap (5h, 7d) as a per-cell gradient gauge headline (colored by cell position, D-03) followed by band-colored %/reset-countdown/burn text (D-02), as a `rich.Text` renderable through the `markup=False` Static.
- `just selfcheck` stays green on stock `/usr/bin/python3` (core gained no textual/rich import); `just lint` clean.

## Task Commits

Each task was committed atomically (test asserts + implementation together, so the green gate never committed a red state):

1. **Task 1: core.band + color the 5h usage % (tracer)** - `2fef6e9` (feat)
2. **Task 2: core.gauge_fill + full gradient gauge and band-colored panel** - `1f1395d` (feat)

**Plan metadata:** see final `docs(10-01)` commit.

## Files Created/Modified
- `claude_monitor/core.py` - Added pure `band(pct)` and `gauge_fill(pct, width)` above the textual boundary; stdlib-only.
- `claude_monitor/test_claude_monitor.py` - New `# --- tui band (TUI-06) ---` and `# --- tui gauge fill (TUI-07) ---` assert blocks under demo(); imported `band`, `gauge_fill`.
- `claude-tui.py` - `GAUGE_WIDTH=20` constant; `_gauge`, `_cap_row_text`, `_usage_renderable` render helpers; `render_all` now pushes the Text renderable to `#usage`.

## Decisions Made
- Gauge cells colored by position along the bar (not by fill level) so the bar always sweeps green->yellow->red, btop's signature meter (D-03).
- Reused `core.tui_usage_rows` strings and split them back into cells for per-segment coloring rather than adding any new formatter to claude-tui.py (D-05 parity preserved).
- Glyphs `U+2588` (filled) / `U+2591` (dim empty track) -- consistent with the existing `core.SPARK_GLYPHS` block ramp already shipping in the tray/TUI. (Global ASCII-only rule is for prose/math symbols like +/-; the block glyph IS the requested visual deliverable here, matching established SPARK_GLYPHS usage.)
- No CSS added: band tokens are rich/ANSI style names applied inline on the Text and resolve under `self.theme=ansi-dark`, so no CSS class map was needed (the CSS hook was optional per the plan).

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None. Both gates (`just selfcheck` exit 0, `just lint` clean) passed on the first run after each task; `claude-tui.py` byte-compiles.

## Tracer Feedback Gate (deferred human-check)
The tracer's automated verify (`just selfcheck`) passed and gated both commits. The tracer's live-TUI human-check -- confirming the per-cell gradient reads correctly against the terminal's inherited ANSI-16 palette (the phase's riskiest unknown) -- could NOT be run by the executor: it requires `just tui` with the daemon running inside a desktop session, and the executor was directed not to run `just restart`. This visual check is captured as coverage deliverable **D3** (`human_judgment: true`) for `/gsd-verify-work`. Do it before building the trends/sessions visuals on the same color approach.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `core.band` and `_gauge`/`_cap_row_text`/`_usage_renderable` are the reusable seam for the remaining btop visuals (TUI-08 trends height coloring, TUI-09 sessions status colors, TUI-10 panels) on the same green->yellow->red ramp.
- One open item: the D3 live-TUI palette read (deferred human-check above) should be confirmed before the trends/sessions visuals reuse the color approach.

## Self-Check: PASSED
- Files verified present: claude_monitor/core.py, claude-tui.py, 10-01-SUMMARY.md
- Commits verified in history: 2fef6e9 (Task 1), 1f1395d (Task 2)

---
*Phase: 10-tui-polish-btop-style*
*Completed: 2026-07-24*
