---
phase: 10-tui-polish-btop-style
plan: 03
subsystem: ui
tags: [tui, textual, rich, btop, ansi-dark, sessions, zebra, panels, border]

# Dependency graph
requires:
  - phase: 10-tui-polish-btop-style
    plan: 01
    provides: "core.band palette + ansi-dark static-color convention the sessions colors and static borders read against"
  - phase: 10-tui-polish-btop-style
    plan: 02
    provides: "the render-only-in-claude-tui.py split; #trends/#usage panel seams the borders wrap"
  - phase: 09-terminal-dashboard-claude-tui-py
    provides: "core.sess_rows + the Text(...)-per-cell markup mitigation (claude-tui.py:199, T-09-01) the restyle preserves"
provides:
  - "core.sess_status_band(status): fixed D-07 status->style token (waiting->yellow, running->green, done->dim, unknown/None->default), total like sess_rank"
  - "claude-tui.py sessions DataTable: per-cell status coloring via rich.Text style + zebra_stripes (TUI-09)"
  - "claude-tui.py: three titled rounded static-bordered panels (usage/trends/sessions) via CSS 'border: round $panel' + border_title (TUI-10)"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Assertable-in-core / render-only-in-claude-tui.py split reused a third time: sess_status_band proven by --selfcheck, the coloring/striping/borders drawn in the textual file"
    - "Status color is a rich.Text STYLE argument, never a markup string -- the T-09-01 Text-per-cell mitigation survives the restyle (a hostile project dir still passes through defused, never parsed)"
    - "Panel borders are static theme chrome (border: round $panel): D-08 keeps the threshold signal in the row text + gauge fill, never on the border"

key-files:
  created: []
  modified:
    - claude_monitor/core.py
    - claude_monitor/test_claude_monitor.py
    - claude-tui.py

key-decisions:
  - "sess_status_band is a one-line dict lookup (SESS_STATUS_BAND.get(status, 'default')) mirroring sess_rank: unknown/empty/None -> 'default' (the terminal's own foreground), total and tolerant, no try/except (D-07)"
  - "The status token doubles as a rich style name so claude-tui.py needs no translation table -- same shape as core.band; 'yellow'/'green'/'dim'/'default' all resolve under self.theme=ansi-dark"
  - "Color applied via Text(cell, style=band) on each of the three cells, never a markup string, so the :199 T-09-01 mitigation (str cell -> markup parser -> MarkupError -> app exit) is preserved verbatim"
  - "Border color is $panel (static, theme-derived), NOT band-coupled (D-08): 'border: round $panel' replaces the old 'border-bottom: solid $panel' on all three panels; border_title set once in on_mount"

patterns-established:
  - "sess_status_band joins band/gauge_fill/spark_levels as the fourth pure btop-visual helper in core; the whole phase-10 palette (bands, gauge gradient, height coloring, status colors) now lives above the textual boundary"

requirements-completed: [TUI-09, TUI-10]

coverage:
  - id: D1
    description: "core.sess_status_band maps the fixed D-07 palette (waiting->yellow, running->green, done->dim) and returns 'default' for empty/unknown/None, never raising"
    requirement: "TUI-09"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py# --- tui session band (TUI-09) --- (via just selfcheck)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Live sessions table renders status-colored rows (waiting yellow / running green / done dim) with zebra striping, cells still rich.Text; a hostile project dir renders defused, never crashes"
    requirement: "TUI-09"
    verification:
      - kind: manual_procedural
        ref: "just tui with live sessions: waiting yellow, running green, done dim, subtle zebra striping; a dir named [bold] or containing a control byte renders literally, no crash"
        status: unknown
    human_judgment: true
    rationale: "Whether the status colors and zebra striping read correctly against the terminal's inherited ANSI-16 palette is a visual judgment; no daemon/desktop is reachable from the executor to run just tui. Headless run_test confirmed the render path builds Text-styled cells without crashing."
  - id: D3
    description: "Each of the three panels (usage/trends/sessions) is a titled, rounded, bordered box with a static (non-threshold-tinted) border"
    requirement: "TUI-10"
    verification:
      - kind: manual_procedural
        ref: "just tui: usage/trends/sessions each a titled rounded box; borders a static color that does not change with usage level"
        status: unknown
    human_judgment: true
    rationale: "The btop paneled look (rounded borders + titles) against the ansi-dark palette is a visual judgment requiring just tui in a desktop session. Headless run_test confirmed border_title is set on all three panels and on_mount does not crash."

# Metrics
duration: 6min
completed: 2026-07-24
status: complete
---

# Phase 10 Plan 03: Status-Colored Sessions + Titled Panels (TUI-09/TUI-10) Summary

**core.sess_status_band adds the fixed D-07 status->style palette (waiting yellow / running green / done dim, unknown->default) proven by --selfcheck; claude-tui.py colors each sessions cell by it via a rich.Text style with zebra striping, and wraps all three panels in titled rounded static-bordered boxes -- the btop paneled finish, with the T-09-01 Text-per-cell mitigation and D-08 static borders intact.**

## Performance

- **Duration:** ~6 min
- **Completed:** 2026-07-24
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- `core.sess_status_band(status)` -- pure, total status->style lookup (`SESS_STATUS_BAND.get(status, "default")`): `waiting`->`yellow`, `running`->`green`, `done`->`dim`, and any unknown/empty/`None` status -> `default` (the terminal's own foreground). One-line dict lookup mirroring `sess_rank`'s unknown-tolerance; never raises. The token doubles as a rich style name so the render side needs no translation table (same shape as `core.band`). Stdlib-only, core gained no textual/rich import.
- `--selfcheck` asserts under a new `# --- tui session band (TUI-09) ---` block: the three known statuses to their fixed colors, plus `""`/`"zombie"`/`None` all to `"default"`.
- `claude-tui.py` sessions DataTable: `zebra_stripes = True` set in `on_mount`, and `render_all`'s `sess_rows` loop now colors each cell by `core.sess_status_band(status)` -- applied as `Text(cell, style=band)`, NEVER a markup string, so every cell stays a `rich.Text` (the T-09-01 `:199` mitigation survives: a hostile project dir like `[bold]x` or `[/]` takes the renderable passthrough, never the markup parser).
- `claude-tui.py` panels: CSS `border: round $panel` on `#usage`/`#trends`/`#sessions` (replacing the old `border-bottom: solid $panel`), and `border_title` ("usage"/"trends"/"sessions") set on each in `on_mount`. Border color is static `$panel` (theme-derived, D-08) -- the threshold signal stays in the row text and gauge fill, never on the chrome. Existing layout (`#usage`/`#trends` height:auto, `#sessions` height:1fr, `#body.stale` dim, `#coldstart` sibling) unchanged.
- `just selfcheck` exits 0 on stock `/usr/bin/python3`; `just lint` clean; `claude-tui.py` byte-compiles; headless `run_test` mounts without crashing (titles set on all three panels, zebra enabled).

## Task Commits

Each task committed atomically (Task 1's test asserts + implementation together, so the green gate never committed a red state):

1. **Task 1: core.sess_status_band + colored zebra-striped sessions** - `6827796` (feat)
2. **Task 2: titled rounded bordered panels** - `c19f9af` (feat)

**Plan metadata:** see final `docs(10-03)` commit.

## Files Created/Modified
- `claude_monitor/core.py` - Added `SESS_STATUS_BAND` map + pure `sess_status_band(status)` next to `sess_rank`, above the textual boundary; stdlib-only.
- `claude_monitor/test_claude_monitor.py` - Imported `sess_status_band`; new `# --- tui session band (TUI-09) ---` assert block under `demo()`.
- `claude-tui.py` - `zebra_stripes` + per-cell `Text(..., style=band)` coloring in the sessions loop; `border: round $panel` CSS + `border_title` on the three panels.

## Decisions Made
- `sess_status_band` returns `"default"` (not a raise, not a color) for any unknown status, mirroring `sess_rank`'s rank-99 tolerance -- a `zombie`/`None`/`""` status renders in the terminal's own foreground rather than crashing a timer callback or forcing a color it does not have a meaning for.
- Color is applied strictly as a `Text` `style` argument, never by wrapping the value in a markup string -- this is the single load-bearing choice that keeps the T-09-01 mitigation alive under the restyle. A `Text(status, style="yellow")` cell still takes DataTable's renderable-passthrough branch; the markup parser (and its `MarkupError`-inside-a-timer app-exit) is never reached.
- Borders use `$panel` (a theme var, static across usage levels), satisfying D-08 without hardcoding an RGB that would not track the inherited ansi-dark palette. `round` is textual's built-in rounded box; `border_title` renders the title inline on the top border (btop paneled look).
- No new formatter, no new data source, no snapshot-shape change, no new dependency (D-05 / phase boundary): the only new symbol is the pure `sess_status_band`; everything else is CSS/render.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None. Both gates (`just selfcheck` exit 0, `just lint` clean) passed on the first run after each task; `claude-tui.py` byte-compiles; a headless `run_test` mount confirmed `border_title` is set on all three panels, `zebra_stripes` is enabled, and `on_mount` does not crash.

## Known Stubs
None.

## Deferred Human-Check
Coverage **D2** and **D3** (`human_judgment: true`): the live-TUI read of the status colors + zebra striping (D2) and the titled rounded static borders (D3) requires `just tui` with the daemon running inside a desktop session, which the executor cannot run (directed not to `just restart`). Confirm via `/gsd-verify-work`. Bundle with the still-open 10-01 D3 (usage-gauge palette) and 10-02 D2 (trends graph) deferred ANSI-16 palette checks -- one live `just tui` pass covers all four.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 10 is code-complete: all three plans (10-01 bands+gauge, 10-02 trends graph, 10-03 sessions+panels) executed. The btop restyle (TUI-06..TUI-10) is fully wired; `core` now carries the whole pure palette toolkit (`band`, `gauge_fill`, `spark_levels`, `sess_status_band`) above the textual boundary.
- Open item: the deferred live-TUI palette reads (10-01 D3, 10-02 D2, 10-03 D2/D3) -- one `just tui` pass in a desktop session closes all of them.

## Self-Check: PASSED
- Files verified present: claude_monitor/core.py, claude_monitor/test_claude_monitor.py, claude-tui.py, 10-03-SUMMARY.md
- Commits verified in history: 6827796 (Task 1), c19f9af (Task 2)

---
*Phase: 10-tui-polish-btop-style*
*Completed: 2026-07-24*
