---
phase: 04-usage-web-dashboard
plan: 01
subsystem: ui
tags: [dashboard, svg, html, webbrowser, pathlib, self-contained, tray]

# Dependency graph
requires:
  - phase: 02-usage-history-persistence
    provides: "~/.claude/usage-history.jsonl store, parse_history, history_keep, history_record schema"
  - phase: 03-usage-trends-in-the-tray
    provides: "trend_burn (burn*60-once), local_bounds, off-thread compute + throttle pattern, empty-state cutover"
provides:
  - "Self-contained file:// HTML usage dashboard opened from a new tray menu item"
  - "render_dashboard/heatmap_buckets/burn_series/history_numeric/_embed_json pure functions (demo-tested)"
  - "Monitor.write_dashboard off-thread generator wired into poll_loop; Monitor.open_dashboard menu handler"
affects: [future dashboard features (DASH-F1 live refresh, DASH-F2 export), any read-side history consumer]

# Tech tracking
tech-stack:
  added: []  # stdlib only: webbrowser, pathlib (no new deps, upholds DASH-06)
  patterns:
    - "Static file:// artifact regenerated off the Gtk main thread on a throttle; menu handler does zero I/O"
    - "Embed-once JSON + inline SVG DOM drawing, client-side range filtering (no charting library)"
    - "Drop-then-escape injection mitigation: history_numeric sanitizer + _embed_json escaping"

key-files:
  created: []
  modified:
    - "claude-monitor.py - five pure dashboard fns, DASH_* constants, write_dashboard, open_dashboard, menu item"

key-decisions:
  - "Static self-contained file:// HTML (D-01) regenerated on the poll tick; no server/port/bind"
  - "Embed history once as escaped JSON; day/week/all switching is client-side filtering (D-02/D-03)"
  - "history_numeric drops non-numeric t/pct/burn before charting/embedding; _embed_json escapes as defense-in-depth (T-04-01)"
  - "write_dashboard re-filters via history_keep so 'full retained history' holds even if a prune silently failed (review finding 2)"
  - "open_dashboard builds the file:// URI via pathlib resolve().as_uri() rather than string concat (review finding 3)"

patterns-established:
  - "Pure HTML/aggregation builders live as module-level functions, self-checked via demo()/--selfcheck"
  - "Broad except Exception in the off-thread writer degrades to 'not updated this tick', throttled not hot-retried"

requirements-completed: [DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, DASH-06]

coverage:
  - id: D1
    description: "Pure dashboard-generation functions (_embed_json, history_numeric, heatmap_buckets, burn_series, render_dashboard)"
    requirement: "DASH-02"
    verification:
      - kind: unit
        ref: "python3 claude-monitor.py --selfcheck"
        status: pass
    human_judgment: false
  - id: D2
    description: "Injection-safety + self-containment of rendered HTML (drop-then-escape, one script-close, no external assets)"
    requirement: "DASH-06"
    verification:
      - kind: unit
        ref: "python3 claude-monitor.py --selfcheck (injection + self-containment asserts)"
        status: pass
    human_judgment: false
  - id: D3
    description: "history_numeric numeric sanitizer drops non-numeric t/pct/burn before payload build"
    requirement: "DASH-05"
    verification:
      - kind: unit
        ref: "python3 claude-monitor.py --selfcheck (history_numeric assert)"
        status: pass
    human_judgment: false
  - id: D4
    description: "write_dashboard reads via parse_history off-thread, retention-filters via history_keep, atomic temp+os.replace"
    requirement: "DASH-05"
    verification:
      - kind: integration
        ref: "ad-hoc: exec write_dashboard on synthetic history -> file written, dash_ready True, stale record filtered from payload"
        status: pass
    human_judgment: false
  - id: D5
    description: "Tray 'Open Usage Dashboard' menu item opens the generated dashboard in the default browser (runtime tray behavior)"
    requirement: "DASH-01"
    verification:
      - kind: manual_procedural
        ref: "run the tray; after one poll cycle the item becomes clickable and opens the page"
        status: unknown
    human_judgment: true
    rationale: "GUI Gtk tray + browser open cannot be exercised headless; requires the user to run the tray and click the item."
  - id: D6
    description: "Charts render in the browser: usage-% trend with day/week/all buttons, daily burn trend, hour x day heatmap with single-hue ramp + gray empty cells"
    requirement: "DASH-03"
    verification:
      - kind: manual_procedural
        ref: "open dashboard.html in a browser; verify the three charts and range switching visually"
        status: unknown
    human_judgment: true
    rationale: "Visual chart correctness and interactive range switching require human inspection in a real browser."

# Metrics
duration: 12min
completed: 2026-07-12
status: complete
---

# Phase 04 Plan 01: Usage Web Dashboard Summary

**Self-contained file:// HTML dashboard (usage-% trend with day/week/all switching, daily burn trend, hour x day burn heatmap) generated off-thread from the Phase-2 JSONL and opened from a new tray menu item, stdlib-only.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 3
- **Files modified:** 1 (`claude-monitor.py`)

## Accomplishments
- Five module-level pure functions (`_embed_json`, `history_numeric`, `heatmap_buckets`, `burn_series`, `render_dashboard`) that build a fully self-contained HTML page with inline CSS + inline SVG-drawing JS and one embedded escaped-JSON payload; all demo-tested.
- `Monitor.write_dashboard` generates and atomically writes the page off the Gtk main thread on a ~5min throttle in `poll_loop` (immediate at startup), reading history via `parse_history` and re-filtering through `history_keep` before render.
- New sensitive "Open Usage Dashboard" tray menu item gated on `dash_ready`, opening the pre-written file via `pathlib` `resolve().as_uri()` with zero history I/O on the main thread.
- Injection + self-containment asserts baked into `--selfcheck`: bad records are dropped (not just escaped), exactly one script-closing sequence, no `<link`/`src=`/`https://`, `http://` only the SVG namespace.

## Task Commits

Each task was committed atomically:

1. **Task 1: Pure dashboard-generation functions + demo asserts** - `9572241` (feat)
2. **Task 2: Cache-path constants + off-thread generate-and-write in poll_loop** - `deca9d6` (feat)
3. **Task 3: "Open Usage Dashboard" menu item + browser open** - `c918a1e` (feat)

**Plan metadata:** docs commit (this SUMMARY + STATE/ROADMAP/REQUIREMENTS)

## Files Created/Modified
- `claude-monitor.py` - added `_embed_json`, `history_numeric`, `heatmap_buckets`, `burn_series`, `render_dashboard`, `_DASH_*` HTML/JS template constants, `DASH_DIR`/`DASH_PATH`/`DASH_INTERVAL`, `Monitor.dash_ready`, `Monitor.write_dashboard`, `Monitor.open_dashboard`, the tray menu item, `webbrowser`/`pathlib` imports, and new `demo()` asserts.

## Decisions Made
- Kept the delivery shape as the D-01 static `file://` artifact (no `http.server`); DASH-F1 live refresh stays deferred so there is no reason to run a server.
- Reused `trend_burn` inside `burn_series` so the burn*60-once convention is not duplicated.
- Embedded the local day/week `bounds` in the payload so the client filters ranges by a timestamp compare instead of reimplementing calendar math in JS.

## Deviations from Plan

None - plan executed exactly as written. (Two commit-message retries were needed to satisfy the repo's commitlint hook: a >100-char body line on Task 2 and a title-case subject on Task 3. No code impact.)

## Issues Encountered
- The repo's `commit-msg` commitlint hook rejected two initial commit messages (body-max-line-length, subject-case); both were reworded and re-committed with no change to the staged code.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All DASH-01..06 requirements implemented; `--selfcheck` prints `ok` with the numeric-sanitizer, injection, and self-containment asserts passing.
- **Runtime-observable checks need user confirmation** (this is a GUI Gtk tray app; the Gtk loop and browser open cannot be exercised headless): run the tray, confirm the "Open Usage Dashboard" item appears and becomes clickable after one poll cycle, and that `${XDG_CACHE_HOME:-~/.cache}/claude-tray/dashboard.html` opens showing the three charts with working day/week/all buttons, a light->dark single-hue heatmap ramp, and gray empty cells.

## Self-Check: PASSED

- SUMMARY.md exists; commits 9572241, deca9d6, c918a1e, 52f110d all present in git log.
- `python3 claude-monitor.py --selfcheck` prints `ok`.
- Pre-existing unrelated changes to `claude-send.py` and `.planning/config.json` left untouched.

---
*Phase: 04-usage-web-dashboard*
*Completed: 2026-07-12*
