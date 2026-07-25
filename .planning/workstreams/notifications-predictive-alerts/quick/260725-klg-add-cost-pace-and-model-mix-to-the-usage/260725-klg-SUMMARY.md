---
phase: 260725-klg
plan: 01
subsystem: usage
tags: [python, rust, ratatui, fixtures, cost-tracking]

requires:
  - phase: 260724-hcm
    provides: TUI usage row rendering and projection column
provides:
  - Six optional cost/pace/model-mix keys on the parsed usage dict (Python and Rust)
  - One shared row formatter (core.usage_extra_row / format::usage_extra_row) rendering
    the trailing usage detail row on every surface (tray menu, socket snapshot, Rust TUI)
  - Two new snapshot fixtures pinning the happy path and the junk-degrades-only-itself
    posture for the new fields
affects: [usage, tray-menu, rust-dashboard, fixture-corpus]

tech-stack:
  added: []
  patterns:
    - "D-05 row-string mirroring: one Python function and one Rust function build the
       exact same joined string; neither surface (tray, TUI) reformats a number itself."

key-files:
  created:
    - fixtures/snapshot/cost-pace-model-mix.json
    - fixtures/snapshot/cost-pace-junk-degrades-only-itself.json
  modified:
    - claude_monitor/core.py
    - claude_monitor/test_claude_monitor.py
    - claude-monitor.py
    - rust/src/snapshot.rs
    - rust/src/format.rs
    - fixtures/generate.py
    - rust/tests/fixtures.rs

key-decisions:
  - "cost_usd renders with two fixed decimals ($113.93); cost_per_hour always rounds to
     whole dollars ($143/hr) -- two different formatters, not one threshold-switching one."
  - "The pace cell only ever appears whole: label plus BOTH pace_used_pct and
     pace_elapsed_pct present together, never a partial pace fragment."
  - "model-mix and pace-label text route through core._safe_cell (reused, not
     reimplemented) and are bounded to EXTRA_TEXT_MAX_CHARS=32, matching Rust's
     MAX_LABEL_CHARS=32 mirror."
  - "Non-finite cost/pace numbers are rejected inside parse_usage itself (math.isfinite),
     not left for the display layer to filter, because a bare Infinity/NaN token in
     json.dumps would fail decoding the WHOLE snapshot for the Rust client (T-klg-02)."

patterns-established:
  - "usage_extra_row(usage) -> Optional[str]/Option<String>: the single row-builder per
     language; tui_usage_rows and Monitor.usage_rows (Python), tui_usage_rows (Rust) all
     append its unmodified result."

requirements-completed: [QT-260725-klg]

duration: 55min
completed: 2026-07-25
status: complete
---

# Quick Task 260725-klg: Add Cost, Pace, and Model Mix to the Usage Row Summary

**parse_usage now keeps `local.cost_usd`, `local.burn_rate_cost_per_hour`, the `pace`
block, and `local.model_distribution` -- fields the daemon already fetched and discarded
-- and surfaces them as one trailing detail row (`$113.93  $143/hr  pace: 27%/16% slow
down  opus 100%`) on the tray menu, the socket snapshot, and the Rust dashboard.**

## Performance

- **Duration:** ~55 min (picked up mid-flow from a prior session's uncommitted, partially
  spec-compliant implementation; this session closed the gaps and committed)
- **Completed:** 2026-07-25
- **Tasks:** 3 (Python core, Rust mirror, fixture corpus)
- **Files modified:** 9 (7 modified, 2 new fixtures)

## Accomplishments

- `parse_usage` carries all six new optional keys (`cost_usd`, `cost_per_hour`,
  `pace_used_pct`, `pace_elapsed_pct`, `pace_label`, `model_mix`); each degrades to
  `None` independently on wrong type, non-finite value, or an absent block, never
  costing the 5h payload (D-04).
- `core.usage_extra_row` is the single row-builder (D-05): `tui_usage_rows` and
  `Monitor.usage_rows` both append its unmodified string as one insensitive row/line.
- `rust/src/format.rs::usage_extra_row` mirrors it cell-for-cell; `rust/src/snapshot.rs`
  normalizes the same six fields with the same degrade-alone posture and sanitizes the
  two text fields at the Rust boundary (T-klg-01).
- Two new fixtures (`cost-pace-model-mix`, `cost-pace-junk-degrades-only-itself`) pin the
  happy path and the junk-degrades-only-itself behavior in the shared corpus (now 24
  files, above the `>= 15` floor).
- `_handle_conn` needed no change: it serializes `mon.usage` wholesale, so the six new
  keys already ride the existing snapshot response.
- `main.rs` needed no change: `usage_panel_height` already derives from `rows.len()` and
  `draw_usage`'s `caps.get(i)` else-branch already renders an uncapped row plain.

## Task Commits

Work was picked up mid-flow: a prior session had already produced a partial,
non-spec-compliant implementation, uncommitted, in the working tree. This session closed
every gap found against the plan's `must_haves.truths` and committed once, per the
explicit single-commit instruction for this quick task.

1. **Tasks 1-3 (Python core, Rust mirror, fixture corpus)** - `3bf5c6c` (`feat`)

## Files Created/Modified

- `claude_monitor/core.py` - `model_mix` helper (reuses `_safe_cell`), extended
  `parse_usage` with the six new keys plus `math.isfinite` rejection, and
  `usage_extra_row` as the single row-builder.
- `claude-monitor.py` - `Monitor.usage_rows` appends `core.usage_extra_row(u)` as one row.
- `claude_monitor/test_claude_monitor.py` - Asserts for population, degrade-alone,
  non-finite rejection, hostile-text sanitization/bounding, and `usage_extra_row`/
  `tui_usage_rows` shape (unchanged row count without the new fields).
- `rust/src/snapshot.rs` - `Usage` struct gained the six fields; `normalize_usage`
  extracts and sanitizes them with the weekly block's degrade-alone posture;
  `MAX_LABEL_CHARS` corrected to 32 to match the Python ceiling.
- `rust/src/format.rs` - `usage_extra_row(&Usage) -> Option<String>` mirrors the Python
  helper; `tui_usage_rows` appends it as the trailing row.
- `rust/tests/fixtures.rs` - `check_usage` match arms for all six new fields
  (`check_optional_number` for the numerics, a new `check_optional_string` sibling for
  the two text fields).
- `fixtures/generate.py` - Two new `F[...]` entries for the happy path and the junk case.
- `fixtures/snapshot/cost-pace-model-mix.json`, `cost-pace-junk-degrades-only-itself.json`
  - Generated fixtures for the two new entries.

## Decisions Made

See `key-decisions` in frontmatter.

## Deviations from Plan

### Auto-fixed Issues

The implementation found in the working tree at session start deviated from the plan's
`must_haves.truths` in several ways that were closed as part of this quick task (no
re-planning, per the task instructions):

**1. [Rule 2 - Missing Critical] `pace_used_pct` was entirely absent**
- **Found during:** Comparing the existing diff against `must_haws.truths` #1 (six keys).
- **Issue:** Only five of the six required keys existed (`pace_used_pct` was never parsed
  or stored), so the target row text's `27%/16%` pace format was unreachable.
- **Fix:** Added `pace_used_pct` end to end: Python `parse_usage`, Rust `Usage` struct/
  `normalize_usage`, fixtures.rs match arm, both fixtures.
- **Files modified:** `claude_monitor/core.py`, `rust/src/snapshot.rs`,
  `rust/tests/fixtures.rs`, both new fixture files.
- **Committed in:** `3bf5c6c`

**2. [Rule 1 - Bug] Non-finite numbers were not rejected (T-klg-02)**
- **Found during:** Re-reading the local `is_num` closure in `parse_usage` against the
  plan's non-finite behavior requirement.
- **Issue:** The existing degrade loop checked `is_num` (type only), not
  `math.isfinite`; `float("inf")`/`float("nan")` passed through untouched and would have
  reached `json.dumps` as a bare `Infinity`/`NaN` token, which is a whole-fetch decode
  failure for the Rust client (`serde_json` rejects it), not a cosmetic glitch.
- **Fix:** Added `math.isfinite` to the degrade check for `cost_usd`, `cost_per_hour`,
  `pace_used_pct`, `pace_elapsed_pct`; added a self-check assert with `float("inf")` and
  `float("nan")` confirming `json.dumps` never emits a bare Infinity/NaN token.
- **Files modified:** `claude_monitor/core.py`, `claude_monitor/test_claude_monitor.py`.
- **Committed in:** `3bf5c6c`

**3. [Rule 2 - Missing Critical] D-05 row-mirroring was broken**
- **Found during:** Comparing `Monitor.usage_rows`/`tui_usage_rows` against
  `must_haves.truths` #3 ("both append the SAME string").
- **Issue:** The prior implementation had `usage_extra_cells` return a `Vec`/`list` of
  cells; `tui_usage_rows` joined them into one row, but `Monitor.usage_rows` instead
  `extend`-ed the tray menu with one row PER CELL (4 separate insensitive menu rows
  instead of 1 combined detail row) -- a real behavioral divergence between surfaces,
  the exact drift D-05 exists to prevent.
- **Fix:** Renamed to `usage_extra_row`/`usage_extra_row`, returning a single joined
  string (or `None`) in both languages; `Monitor.usage_rows` now appends it as one row.
- **Files modified:** `claude_monitor/core.py`, `claude-monitor.py`, `rust/src/format.rs`.
- **Committed in:** `3bf5c6c`

**4. [Rule 1 - Bug] Row-cell formatting did not match the plan's target row text**
- **Found during:** Comparing rendered output against the plan context's exact target
  string (`$113.93  $143/hr  pace: 27%/16% slow down  opus 100%`).
- **Issue:** `cost_usd` and `cost_per_hour` shared one `fmt_cost` that switched to whole
  dollars at `>= 100` for both (`$114` instead of `$113.93`); the pace cell rendered as
  `pace: {label} ({elapsed}% elapsed)` instead of `pace: {used}%/{elapsed}% {label}`; the
  cost cell carried an extraneous `"cost: "` prefix not in the plan's target text.
- **Fix:** `cost_usd` always renders with two decimals; `cost_per_hour` always rounds to
  whole dollars; the pace cell only appears when label and both percentages are present,
  formatted as `pace: {used}%/{elapsed}% {label}`; no `cost:` prefix.
- **Files modified:** `claude_monitor/core.py`, `rust/src/format.rs`.
- **Committed in:** `3bf5c6c`

**5. [Rule 3 - Blocking] `model_mix` reimplemented `_safe_cell` instead of reusing it**
- **Found during:** Checking the plan's explicit "Reuse, do NOT reimplement:
  `core._safe_cell(s)`" instruction against the working-tree `clean_text` helper.
- **Issue:** `clean_text` filtered to printable ASCII only (dropping all non-ASCII
  rather than the `_safe_cell` convention of replacing non-printable characters with
  `?`), diverging from the threat register's named mitigation (T-klg-01: "`_safe_cell` +
  length bound at parse").
- **Fix:** Removed `clean_text`; `model_mix` and `pace_label` now route through
  `_safe_cell` (existing helper) plus a length bound, matching the threat model exactly.
- **Files modified:** `claude_monitor/core.py`, `claude_monitor/test_claude_monitor.py`.
- **Committed in:** `3bf5c6c`

**6. [Rule 2 - Missing Critical] Field naming and Rust `MAX_LABEL_CHARS` drift**
- **Found during:** Cross-checking the Rust `Usage` struct's `models` field and
  `MAX_LABEL_CHARS = 48` against the plan's `model_mix` key name and "matching the
  Python text ceiling" instruction (Python was 32).
- **Issue:** Rust's field was named `models` (not `model_mix`, the name the plan uses
  throughout and the name fixtures/generate.py needs); `MAX_LABEL_CHARS` (48) did not
  match Python's `EXTRA_TEXT_MAX_CHARS` (32).
- **Fix:** Renamed the Rust field to `model_mix`; corrected `MAX_LABEL_CHARS` to 32.
- **Files modified:** `rust/src/snapshot.rs`, `rust/src/format.rs`, `rust/tests/fixtures.rs`.
- **Committed in:** `3bf5c6c`

**7. [Rule 2 - Missing Critical] Task 3 (fixture corpus) had not been started**
- **Found during:** Checking `fixtures/generate.py` for `F["cost-pace-model-mix"]`/
  `F["cost-pace-junk-degrades-only-itself"]` entries named in the plan.
- **Issue:** `fixtures/generate.py` was unmodified; an untracked, hand-written stray
  fixture (`usage-extras-degrade-independently.json`) existed instead, using the old
  `models` field name and not wired through the generator, so it would have broken once
  the field rename above landed.
- **Fix:** Deleted the stray fixture; added the two plan-named `F[...]` entries to
  `fixtures/generate.py` and regenerated the corpus (24 files total).
- **Files modified:** `fixtures/generate.py`; created
  `fixtures/snapshot/cost-pace-model-mix.json`,
  `fixtures/snapshot/cost-pace-junk-degrades-only-itself.json`; deleted
  `fixtures/snapshot/usage-extras-degrade-independently.json` (untracked, never committed).
- **Committed in:** `3bf5c6c`

---

**Total deviations:** 7 auto-fixed (2 Rule 1 bugs, 4 Rule 2 missing-critical, 1 Rule 3
blocking-reimplementation cleanup)
**Impact on plan:** All fixes bring the implementation into compliance with the plan's
`must_haves.truths`, the D-05 row-mirroring invariant, and the T-klg-01/02 threat
mitigations. No scope creep beyond what the plan specified.

## Issues Encountered

None beyond the deviations documented above.

## Verification

- `python3 claude-monitor.py --selfcheck` - passed (ok)
- `ruff check .` (`just lint`) - passed (All checks passed!)
- `cd rust && cargo test` (`just rust-test`) - passed (90 + 15 + 4 = 109 tests)
- `cd rust && cargo clippy --all-targets -- -D warnings` (`just rust-lint`) - passed
- `just check` (selfcheck + rust-test combined) - passed
- `just rust-fixture cost-pace-model-mix -- --once` - renders
  `$113.93  $143/hr  pace: 27%/16% slow down  opus 72% sonnet 28%` exactly matching the
  plan's target row text
- `just rust-fixture missing-optional-fields -- --once` - byte-identical to its
  pre-change single-row output (no extras row, no silent growth)
- `just restart` - tray daemon restarted cleanly on the new code

## Known Stubs

None.

## User Setup Required

None - no dependency or configuration changes; field-passthrough only.

## Next Phase Readiness

- Cost, pace, and model-mix data now flow end to end (tray menu, socket snapshot, Rust
  dashboard) with no new polling, data source, or dependency.
- No blockers or follow-up work identified.

## Self-Check: PASSED

- All 9 files (7 modified, 2 new fixtures) exist and match the diff described above.
- Code commit `3bf5c6c` exists in `git log`.
- `just check`, `just lint`, `just rust-lint` all green after the commit.

---
*Quick task: 260725-klg*
*Completed: 2026-07-25*
