---
phase: 02-usage-history-persistence
plan: 01
subsystem: persistence
tags: [jsonl, history, retention, atomic-write, tempfile, gtk, tray]

# Dependency graph
requires:
  - phase: 01-usage-monitoring
    provides: parse_usage normalized dict (tokens_used, token_limit, used_percentage, resets_at_epoch, burn_rate_per_min); poll_loop daemon thread
provides:
  - Append-only JSONL usage history at ~/.claude/usage-history.jsonl (one record per successful poll)
  - Bounded retention (default 30d, env CLAUDE_TRAY_HISTORY_DAYS) pruned atomically at startup and every PRUNE_INTERVAL
  - Pure, reusable history logic: history_record(), history_keep() (retention predicate), parse_history() (tolerant loader)
  - Defensive OSError-swallowing I/O that never crashes or blocks the tray
affects: [03-trends, phase-03-sparkline, phase-03-burn-rate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Atomic rewrite: survivors -> tempfile.mkstemp in same dir -> os.replace (never truncate-in-place)"
    - "Tolerant JSONL read: per-line json.loads in try/except, skip empties + unparseable"
    - "Defensive I/O: every file op wrapped in try/except OSError, degrade to non-persistence"
    - "All history I/O confined to the poll_loop daemon thread, off the Gtk main loop"

key-files:
  created: []
  modified:
    - claude-monitor.py

key-decisions:
  - "PRUNE_INTERVAL = 6*3600 (6h) as the opportunistic-prune cadence (planner-picked, CONTEXT said >= 6h)"
  - "burn stored RAW per-minute (unconverted); Phase 03 converts to per-hour once to avoid double-conversion"
  - "t pinned to int(time.time()) of the poll, never resets_at_epoch"
  - "prune_history uses os.fdopen(fd) from mkstemp + a finally-block temp cleanup if os.replace did not run"

patterns-established:
  - "Atomic file rewrite via tempfile.mkstemp(dir=same) + os.replace"
  - "Per-line tolerant JSONL parsing for corruption/partial-write resilience"

requirements-completed: [HIST-01, HIST-02, HIST-03]

coverage:
  - id: D1
    description: "history_record builds compact {t,pct,tokens_used,token_limit,burn} with t=int(now) and raw per-minute burn (HIST-01 record shape)"
    requirement: "HIST-01"
    verification:
      - kind: unit
        ref: "claude-monitor.py::demo() history_record assert; command: python3 claude-monitor.py --selfcheck"
        status: pass
    human_judgment: false
  - id: D2
    description: "history_keep retention predicate drops now-40d, keeps now-1d at days=30 (HIST-02 retention rule)"
    requirement: "HIST-02"
    verification:
      - kind: unit
        ref: "claude-monitor.py::demo() history_keep asserts; command: python3 claude-monitor.py --selfcheck"
        status: pass
    human_judgment: false
  - id: D3
    description: "parse_history skips a corrupt middle line and returns the two well-formed records in order (HIST-03 tolerant read)"
    requirement: "HIST-03"
    verification:
      - kind: unit
        ref: "claude-monitor.py::demo() parse_history assert; command: python3 claude-monitor.py --selfcheck"
        status: pass
    human_judgment: false
  - id: D4
    description: "append-on-success + startup/opportunistic atomic prune wired into poll_loop; append guarded by usage is not None; all I/O off the Gtk main loop"
    requirement: "HIST-01"
    verification:
      - kind: integration
        ref: "manual append/prune round-trip: old record pruned, two fresh kept, missing-file prune no-op (scratchpad harness); grep confirms calls in poll_loop only"
        status: pass
    human_judgment: true
    rationale: "Live-tray behavior (one line per real poll, degraded polls add nothing, chmod-000/unwritable-dir keeps tray running) needs the human-check in the plan's <human-check> block; headless env cannot import GTK to run the real poll_loop."
  - id: D5
    description: "Defensive OSError-swallowing I/O: missing/unwritable/corrupt file never crashes or blocks the tray (HIST-03)"
    requirement: "HIST-03"
    verification:
      - kind: manual_procedural
        ref: "plan <human-check>: chmod 000 the file / unwritable dir, confirm tray keeps running and usage rows update"
        status: unknown
    human_judgment: true
    rationale: "Failure-mode resilience under a live long-lived GTK tray requires manual observation; automated round-trip covers the code paths but not the running-tray guarantee."

# Metrics
duration: 2min
completed: 2026-07-12
status: complete
---

# Phase 02 Plan 01: Usage History Persistence Summary

**Append-only JSONL usage history at ~/.claude/usage-history.jsonl with 30-day env-tunable retention, pruned atomically via tempfile+os.replace, and fully OSError-defensive I/O confined to the poll_loop daemon thread.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-07-12T09:49:15Z
- **Completed:** 2026-07-12T09:51:12Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- Pure history logic added to `claude-monitor.py`: `history_record()` (compact `{t,pct,tokens_used,token_limit,burn}`, `t=int(now)`, raw per-minute burn), `history_keep()` (retention predicate reused by prune and Phase 03), `parse_history()` (per-line tolerant loader).
- Three config constants: `HISTORY_PATH`, `HISTORY_DAYS` (env `CLAUDE_TRAY_HISTORY_DAYS`, guarded int/except like POLL_INTERVAL), `PRUNE_INTERVAL = 6*3600`.
- Defensive I/O: `append_history()` (OSError-swallowing JSONL append) and `prune_history()` (atomic tempfile.mkstemp + os.replace, never truncate-in-place, temp cleanup on failure).
- `poll_loop` wiring: startup prune before the loop, append-on-success before `GLib.idle_add`, opportunistic prune via in-process `last_prune` timer. No history I/O added to `apply_usage` or `main` (both on the Gtk main thread).
- `--selfcheck` extended with record/retention/tolerant-parse asserts; every v1.0 assert intact; still prints "ok" once.

## Task Commits

Each task was committed atomically:

1. **Task 1: Pure history logic + self-check** - `d333371` (feat)
2. **Task 2: Wire history into poll_loop, defensive atomic I/O** - `899bf72` (feat)

## Files Created/Modified
- `claude-monitor.py` - added HISTORY_* constants, `history_record`/`history_keep`/`parse_history`/`append_history`/`prune_history`, `import tempfile`, poll_loop append+prune wiring, extended demo() asserts.

## Decisions Made
- `PRUNE_INTERVAL = 6*3600` (6h) — CONTEXT specified ">= 6h", planner picked the exact constant.
- `burn` stored RAW per-minute (unconverted) per LOCKED CONTEXT; Phase 03 converts to per-hour once.
- `t` pinned to `int(time.time())` of the poll, never `resets_at_epoch`.
- `prune_history` uses a `finally` block to remove the temp file only when `os.replace` did not run (set `tmp=None` on success), so a failed rewrite never leaks a temp file and never touches the original.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Headless verification could not `exec` the full module (GTK/`gi` unavailable in the sandbox). Resolved by (a) running `python3 claude-monitor.py --selfcheck` which exercises all pure logic without importing GTK past the guard, and (b) a standalone round-trip harness replicating `append_history`/`prune_history`/`parse_history` to confirm the atomic prune drops a 40-day record, keeps fresh ones, and no-ops on a missing file. The live-tray human-check (D4/D5) remains for the user.

## User Setup Required
None - no external service configuration required. History file is auto-created under the existing `~/.claude` home; no env vars required (CLAUDE_TRAY_HISTORY_DAYS is optional).

## Next Phase Readiness
- Phase 03 (trends) can read `~/.claude/usage-history.jsonl` via the shared `parse_history()` and `history_keep()`; `burn` is raw per-minute (convert once to per-hour).
- Open human-check (D4/D5): run the tray a few cycles and confirm one line per successful poll, none on degraded polls, an old seeded record pruned at startup, and chmod-000/unwritable-dir leaves the tray running.

## Self-Check: PASSED
- FOUND: claude-monitor.py
- FOUND: 02-01-SUMMARY.md
- FOUND commit d333371 (Task 1)
- FOUND commit 899bf72 (Task 2)

---
*Phase: 02-usage-history-persistence*
*Completed: 2026-07-12*
