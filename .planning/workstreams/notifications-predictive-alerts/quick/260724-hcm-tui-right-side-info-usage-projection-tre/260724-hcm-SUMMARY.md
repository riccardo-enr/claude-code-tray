---
phase: 260724-hcm
plan: 01
subsystem: ui
tags: [textual, rich, quota, projection, heatmap]

requires:
  - phase: 10-tui-polish-btop-style
    provides: btop-style usage gauges, decoded trend graph, and panel layout
provides:
  - Per-cap projected usage or exhaust time beside TUI gauges
  - Sanitized 7x24 usage heatmap on the daemon snapshot
  - Compact Mon-Sun active-hour heatmap beside the TUI trend graph
affects: [tui, daemon-snapshot, trend-rendering]

tech-stack:
  added: []
  patterns:
    - Core computes projection and heatmap values; the TUI only lays out and colors them
    - Optional snapshot fields degrade to the existing single-column presentation

key-files:
  created: []
  modified:
    - claude-tui.py
    - claude-monitor.py
    - claude_monitor/core.py
    - claude_monitor/test_claude_monitor.py

key-decisions:
  - "Reuse core.project, core.hhmm, and core.band for projections instead of adding TUI-specific quota math."
  - "Send the existing heatmap_buckets output over the snapshot and collapse only empty edge hours in the renderer."

patterns-established:
  - "Side-by-side TUI detail: Rich Table.grid keeps the existing left renderable and adds optional right-side context."
  - "Snapshot robustness: malformed optional heatmap and trend values degrade without exiting the Textual render tick."

requirements-completed: [QT-260724-hcm]

coverage:
  - id: D1
    description: Each present cap shows a band-colored projection or exhaust ETA beside its existing gauge.
    requirement: QT-260724-hcm
    verification:
      - kind: integration
        ref: "headless Rich render command: usage projection and exhaust assertions"
        status: pass
      - kind: other
        ref: just selfcheck
        status: pass
    human_judgment: false
  - id: D2
    description: The daemon snapshot carries a sanitized 7x24 heatmap with tested active-hour bounds.
    requirement: QT-260724-hcm
    verification:
      - kind: integration
        ref: "claude_monitor/test_claude_monitor.py#socket wire protocol"
        status: pass
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py#heatmap_active_span assertions"
        status: pass
    human_judgment: false
  - id: D3
    description: The trends panel shows a compact Mon-Sun active-hour heatmap beside the existing graph.
    requirement: QT-260724-hcm
    verification:
      - kind: integration
        ref: "headless Rich render command: weekday and active-hour assertions"
        status: pass
    human_judgment: true
    rationale: Final spacing, color readability, and fit require viewing the TUI in the operator's real terminal.

duration: 14min
completed: 2026-07-24
status: complete
---

# Quick Task 260724-hcm: TUI Right-Side Projections and Heatmap Summary

**Quota projections and a weekly usage heatmap now fill the TUI's right-side space using existing core calculations.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-07-24T10:55:23Z
- **Completed:** 2026-07-24T11:09:22Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Added per-cap projected usage at reset, switching to an exhaust ETA when projected usage exceeds 100%.
- Added a sanitized 7x24 heatmap to the daemon's existing snapshot response with tested active-hour bounds.
- Rendered a compact Mon-Sun heatmap beside the existing trend graph while preserving collecting and no-data states.

## Task Commits

1. **Task 1: Usage-panel projections** - `5fcb364`
2. **Task 2: Heatmap data path** - `c604416`
3. **Task 3: Trends-panel heatmap** - `14d5cf1`

## Files Created/Modified

- `claude-tui.py` - Side-by-side quota projections and weekly heatmap rendering.
- `claude-monitor.py` - Cached heatmap and snapshot response field.
- `claude_monitor/core.py` - Active-hour span helper and malformed trend/heatmap guards.
- `claude_monitor/test_claude_monitor.py` - Helper and snapshot wire-protocol assertions.

## Decisions Made

- Kept projection and heatmap math in `core`; the TUI applies only layout, glyphs, and styles.
- Used the existing percentage band palette for both projections and heatmap cells.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed rendered-sentinel coupling from unavailable usage**
- **Found during:** Task 1
- **Issue:** The TUI compared against the exact `"usage unavailable"` string before reading percentages.
- **Fix:** Gate on `usage.get("used_percentage")` and return core's rendered rows when absent.
- **Verification:** `just selfcheck`, `just lint`, headless render command.
- **Committed in:** `5fcb364`

**2. [Rule 1 - Bug] Made sparkline decoding honor its non-raising contract**
- **Found during:** Task 2
- **Issue:** `spark_levels` raised on a non-string socket value despite documenting malformed-input tolerance.
- **Fix:** Return an empty level list for non-string values and add an assertion.
- **Verification:** `just selfcheck`.
- **Committed in:** `c604416`

**Total deviations:** 2 auto-fixed bugs. **Impact:** Both are narrow robustness fixes from the Phase 10 review; no architecture or scope changed.

## Issues Encountered

- The socket selfcheck fixture lacked the new `heatmap` field. It was updated to assert the field round-trips.
- The environment's `apply_patch` helper failed with a `bwrap` loopback error, so equivalent scoped edits used `git apply` and `ed`, followed by diff and test verification.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Usage projections appear on the next `just tui` without restarting the daemon.
- The live heatmap requires `just restart` before `just tui` because Task 2 changed the daemon snapshot.
- Phase 10 remains ready for conversational UAT and milestone closeout after visual verification.

## Self-Check: PASSED

`just lint`, `just selfcheck`, branch diff checks, and the headless Rich render smoke test all passed.

## Post-Mortem

> [!warning]
> The first TUI heatmap applied quota bands at 70/90, transposed the grid, and collapsed empty edge hours. The dashboard instead renders Mon-Sun rows by all 24 hour columns and scales intensity relative to the dataset maximum. `core.heatmap_levels` now carries that dashboard normalization into the terminal renderer, with density glyphs standing in for the dashboard's continuous blue ramp.

---
*Quick task: 260724-hcm*
*Completed: 2026-07-24*
