---
phase: 260727-nlo
plan: 01
subsystem: ui
tags: [rust, ratatui, sparkline, tui]

requires:
  - phase: 260727-mki
    provides: clip_to_newest (kept-newest-columns clipping, wrong slicing base)
provides:
  - clip_to_newest now clips within the real (non-blank) prefix of the cum_trend sparkline, never the whole raw string
affects: [rust-client-foundation]

tech-stack:
  added: []
  patterns:
    - "Find the real-data boundary (rposition of last non-space char) before slicing, rather than slicing the raw whole-array length -- needed whenever an array spans a fixed window that extends past 'now' into not-yet-sampled future buckets"

key-files:
  created: []
  modified:
    - rust/src/main.rs
    - fixtures/generate.py
    - fixtures/snapshot/cum-trend-clipped-keeps-newest.json

key-decisions:
  - "Root cause: build_cum_trend's array spans the WHOLE window through reset (not just up to now), so every index past (now - start) // CUM_TREND_INTERVAL is a genuine unsampled FUTURE bucket rendered as a literal SPARK_GAP space -- this is correct and intentional. The bug was clip_to_newest slicing by raw whole-string length, which could keep nothing but that trailing blank run. Fix: find the end of the real (non-blank) prefix via rposition first, then slice within [0, real_len) unconditionally, dropping the trailing blank run even when the real prefix already fits budget."

requirements-completed: [QT-260727-nlo]

coverage:
  - id: D1
    description: "clip_to_newest clips within the real (non-blank) prefix of the cum_trend sparkline, dropping the trailing future-blank run unconditionally, in both the fits-within-budget and clips-within-real-prefix cases"
    requirement: "QT-260727-nlo"
    verification:
      - kind: unit
        ref: "rust/src/main.rs#clip_to_newest_drops_the_trailing_future_blank_run_not_the_real_data"
        status: pass
      - kind: unit
        ref: "rust/src/main.rs#cum_trend_sparkline_clipping_keeps_the_newest_columns_not_the_oldest"
        status: pass
      - kind: manual_procedural
        ref: "tmux new-session -x 55 -y 45 'just rust-fixture cum-trend-clipped-keeps-newest' + capture-pane"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-07-27
status: complete
---

# Phase 260727-nlo: Fix clip_to_newest clipping the wrong region Summary

**clip_to_newest now finds the end of the real (non-blank) prefix in the cum_trend sparkline via `rposition`, and slices within that prefix -- fixing a same-session regression where a raw whole-string clip could keep nothing but the trailing not-yet-sampled blank run, rendering a genuinely climbing series as a totally empty graph.**

## Performance

- **Duration:** 12 min
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- Root-caused and fixed `clip_to_newest` (rust/src/main.rs): `build_cum_trend`'s array spans the WHOLE window through `reset`, not just up to "now" -- every bucket index past `(now - start) // CUM_TREND_INTERVAL` is a genuine, not-yet-sampled FUTURE bucket rendered as a literal `SPARK_GAP` space by design. The pre-fix clip kept the last `budget` raw characters of the *whole* string, which for a wide-enough future-blank run could be entirely inside that blank run -- confirmed live: a 300-char row (~124 real chars + 176 literal spaces), `graph_width` 136, pre-fix output 132 chars, all spaces.
- New logic: collect the row's chars, find `real_len` via `chars.iter().rposition(|&c| c != ' ').map(|i| i + 1).unwrap_or(0)`, then `start = real_len.saturating_sub(budget)`, then slice `chars[start..real_len]` unconditionally (no `if len > budget` guard) -- always drops the trailing blank run, even when the real prefix already fits budget.
- New unit test `clip_to_newest_drops_the_trailing_future_blank_run_not_the_real_data` covers BOTH branches: the fits-within-budget case (`budget(15) > real_len(10)`, exactly mirroring the live bug's own relationship) asserting the full real prefix `"0123456789"` survives unpadded and blank-tail-free; and the clips-within-real-prefix case (`budget(6) < real_len(10)`) asserting `"456789"` (newest 6 real chars).
- The existing `cum_trend_sparkline_clipping_keeps_the_newest_columns_not_the_oldest` test (pure 60-char climb, no trailing spaces) passes unchanged -- `real_len == total_len` there, so the new real-prefix-relative slicing is byte-identical to the old whole-string-relative slicing for that shape.
- `fixtures/generate.py`'s `cum-trend-clipped-keeps-newest` fixture (the SAME asset the live tmux check renders) now carries `_CUM_CLIMB + (" " * 60)` (120 chars: 60 real + 60 trailing blank), so its own manual/live render check actually exercises this regression going forward. `git diff --stat fixtures/snapshot/` confirms exactly one fixture changed.
- Live tmux-captured render at `-x 55 -y 45` of the regenerated fixture shows a full staircase of filled glyphs in the cum_trend graph (level 0 at the axis floor climbing to full blocks `█` at the top), not blank space -- direct proof the fix works against the actual regression shape, not just the unit test.

## Task Commits

Each task was committed atomically:

1. **Task 1: clip_to_newest clips within the real (non-blank) prefix, not the whole array** - `82b32d4` (fix)

**Plan metadata:** committed separately by the orchestrator (docs commit).

## Files Created/Modified
- `rust/src/main.rs` - `clip_to_newest`'s doc comment and body rewritten to find the real (non-blank) prefix via `rposition` before slicing; new unit test added near the existing clip regression test
- `fixtures/generate.py` - `_CUM_FUTURE_BLANK` (60 trailing spaces) and `_CUM_SPARKLINE` (`_CUM_CLIMB + _CUM_FUTURE_BLANK`) added; `cum-trend-clipped-keeps-newest`'s `wire`/`expect`/`note` updated to use `_CUM_SPARKLINE`
- `fixtures/snapshot/cum-trend-clipped-keeps-newest.json` - regenerated via `python3 fixtures/generate.py`; the only fixture file that changed

## Decisions Made
- Root cause named explicitly (per plan requirement): `build_cum_trend`'s array spans the whole window through `reset`, so a genuine trailing future-blank region is real and by design -- the bug was clipping by raw whole-string length instead of within the real (non-blank) prefix. This must not be "fixed" again in the direction of shrinking or removing the trailing blank region itself.
- Clippy flagged `clip_to_newest(&[sparkline.clone()], ...)` in the new test as `cloned_ref_to_slice_refs`; fixed to `clip_to_newest(std::slice::from_ref(&sparkline), ...)` -- a pure lint cleanup within the new test code, no behavior change (Rule 1, auto-fixed inline before commit).

## Deviations from Plan

None beyond the one clippy auto-fix documented above (Rule 1 - the new test's own `.clone()` triggered a lint the plan didn't anticipate; fixed inline, verified green, included in the single task commit).

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- cum_trend graph now correctly shows real data at any terminal width, including the common case (window not yet finished) where the array's tail is genuinely blank.
- No blockers for continued work on Phase 11 (Rust Client Foundation planning).

## Self-Check: PASSED

- FOUND: rust/src/main.rs, fixtures/generate.py, fixtures/snapshot/cum-trend-clipped-keeps-newest.json (all present on disk)
- FOUND: commit 82b32d4 in git log

---
*Phase: 260727-nlo*
*Completed: 2026-07-27*
