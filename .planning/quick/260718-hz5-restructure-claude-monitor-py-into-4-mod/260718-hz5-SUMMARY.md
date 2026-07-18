---
phase: 260718-hz5-restructure
plan: 01
subsystem: claude-code-tray
status: complete
tags: [refactor, modularization, pure-move]
requires: []
provides: [core.py, dashboard.py, test_claude_monitor.py]
affects: [claude-monitor.py]
key-files:
  created:
    - core.py
    - dashboard.py
    - test_claude_monitor.py
  modified:
    - claude-monitor.py
    - pyproject.toml
decisions:
  - "Separate import lines (not `import a, b, c`) to satisfy ruff 0.15.8 default E401"
  - "Added per-file-ignore E731 for test_claude_monitor.py (byte-identical demo() lambda)"
  - "Assembled new files from exact source line-ranges to guarantee byte-identical bodies"
metrics:
  duration: ~15m
  completed: 2026-07-18
  tasks: 4
  files: 5
---

# Phase 260718-hz5 Plan 01: Restructure claude-monitor.py into 4 modules Summary

Pure MOVE refactor split the 2081-line `claude-monitor.py` into 4 flat sibling files
(`core.py`, `dashboard.py`, `test_claude_monitor.py`, slimmed `claude-monitor.py`) with
byte-identical moved bodies; only added imports and `core.`/`dashboard.` prefixes differ.

## What was done

- **core.py** (604 lines) - 34 pure-logic/config functions + 18 owning constants, stdlib
  only (`datetime, json, math, os, subprocess, tempfile, time`), no gi/GTK, no local import.
- **dashboard.py** (480 lines) - `_brand_icon_uri` + `render_dashboard` + the full `_DASH_*`
  HTML/CSS/JS blob + `DASH_DIR/DASH_PATH/DASH_INTERVAL/_DASH_META_REFRESH`; `import base64, os`
  + `from core import (...)` (8 symbols). The `_DASH_JS` string (JS `project`/`hhmm`/`WIN5`/
  `WIN7`) moved verbatim, never prefixed.
- **test_claude_monitor.py** (510 lines) - the `demo()` assert oracle verbatim, `import
  datetime, json, time` + explicit `from core import (...)` (34 symbols) + `from dashboard
  import render_dashboard`.
- **claude-monitor.py** (580 lines) - slim GTK entry point: 10 owned constants, `class
  Monitor`, `terminal_focused/pane_onscreen/looking_at/serve/poll_loop/watch_focus/main`,
  keeps the gi block, `import core`/`import dashboard`, all moved refs qualified
  `core.X`/`dashboard.X`; `--selfcheck` now imports `test_claude_monitor` and calls its
  `demo()`.
- **pyproject.toml** - added scoped `"test_claude_monitor.py" = ["E731"]` per-file-ignore
  (the byte-identical `ep = lambda` inside the moved `demo()`).

Import DAG (acyclic): core -> (none); dashboard -> core; test -> core, dashboard;
claude-monitor -> core, dashboard.

## Final per-file line counts

| File                     | Lines |
| ------------------------ | ----- |
| core.py                  | 604   |
| dashboard.py             | 480   |
| test_claude_monitor.py   | 510   |
| claude-monitor.py        | 580   |
| **total**                | 2174  |

(Original single file: 2081 lines; +93 from 4 module headers/import blocks.)

## Verification results (all 7 gates pass)

1. `python3 claude-monitor.py --selfcheck` -> printed `ok`, **exit 0**.
2. `ast.parse` of all four files -> **`ast ok`**.
3. `python3 -c "import sys, core, dashboard; assert 'gi' not in sys.modules"` ->
   **`core+dashboard ok, gi not loaded`** (proves no GTK leaked into the pure modules).
4. `python3 -m py_compile claude-monitor.py core.py dashboard.py test_claude_monitor.py`
   -> **`py_compile ok`**.
5. `grep -nE "gi\.repository|gi\.require_version|import gi" core.py dashboard.py
   test_claude_monitor.py` -> **empty** (grep exit 1). The gi block appears **only** in
   claude-monitor.py (lines 25-28).
6. `ruff check .` -> **`All checks passed!`** (exit 0) after adding the test E731 ignore.
7. def-count preservation: `git show HEAD:claude-monitor.py | grep -c "def "` = **64**;
   sum of `grep -c "def "` across the 4 files = **64**. No function lost or duplicated.

Extra structural checks:
- DAG acyclic: `python3 -c "import core, dashboard, test_claude_monitor"` -> clean.
- Reference audit: regex scan for bare occurrences of all 68 moved symbols in
  claude-monitor.py found only **3 prose hits** (comment `# latest parse_usage() dict`,
  docstring `Re-applies history_keep in ...`, comment `# ... (the project dir)`). Zero bare
  **code** references - every real reference is `core.X`/`dashboard.X`.
- Non-ASCII: only `core.py` line 184 (`SPARK_GLYPHS`) carries non-ASCII, moved verbatim;
  no new non-ASCII introduced.
- Byte-identity spot-check vs `git HEAD`: `parse_usage`, `heatmap_buckets`, SPARK block,
  `render_dashboard`, the full `_DASH_JS` blob, and `demo()` all confirmed verbatim.

## Deviations from Plan

- **[Rule 3 - Blocking] Import style + E731 ignore.** The plan suggested a single
  `import datetime, json, math, os, subprocess, tempfile, time` line, but ruff 0.15.8's
  default rule set includes E401 (multiple imports on one line), which would fail gate 6.
  Used separate `import` lines instead (matching the original file's style; imports are the
  explicitly-allowed edit). The moved `demo()` contains `ep = lambda ...` (E731) that must
  stay byte-identical, so added `"test_claude_monitor.py" = ["E731"]` per-file-ignore,
  consistent with the existing `claude-monitor.py` entry. Both anticipated by the plan's
  ruff guidance. Committed in 02aef11.

## Deployment note

The `~/.claude/hooks/claude-monitor.py` symlink and its `python3 script.py` launch are
**unchanged** - `sys.path[0]` = repo dir resolves `core`/`dashboard` through the symlink.
**The running tray must be restarted (kill + relaunch) to load the new module layout;**
the symlink itself is not touched.

## Deliverable commit

`02aef11` - `refactor: split claude-monitor.py into core/dashboard/test modules`
(files: claude-monitor.py, core.py, dashboard.py, test_claude_monitor.py, pyproject.toml).

## Self-Check: PASSED
- core.py, dashboard.py, test_claude_monitor.py exist; claude-monitor.py, pyproject.toml modified.
- Commit 02aef11 present in git log.
- `--selfcheck` exits 0 post-commit.
