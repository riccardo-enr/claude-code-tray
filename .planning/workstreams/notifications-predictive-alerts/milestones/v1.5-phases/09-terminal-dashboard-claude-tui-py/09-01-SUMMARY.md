---
phase: 09-terminal-dashboard-claude-tui-py
plan: 01
subsystem: ui
tags: [textual, tui, unix-socket, af_unix, selfcheck, pure-functions]

# Dependency graph
requires:
  - phase: 08-daemon-socket-query-verb
    provides: the read-only `{"query": "snapshot"}` socket verb and the three-key snapshot shape (sessions/usage/trends) this substrate parses
provides:
  - core.read_line / core.query_snapshot -- an AF_UNIX snapshot client that raises on every failure mode
  - core.tui_usage_rows -- D-01's compact two-row cap block, built only from existing core formatters
  - core.trend_text -- the snapshot's trend rows joined verbatim, never recomputed (D-05)
  - core.sess_rank / sess_elapsed / fmt_elapsed / sess_rows -- the v1.4 dashboard sessions panel translated to Python
  - core.SOCK_PATH / TUI_FETCH_INTERVAL / TUI_TICK_INTERVAL / TUI_SOCK_TIMEOUT / SESS_RANK
  - four banner-delimited assert blocks in demo() covering all of the above
affects: [09-02, claude-tui.py, textual packaging]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure substrate above the textual boundary: every TUI decision that can be asserted lives in core.py, so --selfcheck on /usr/bin/python3 proves it"
    - "read_line takes an already-connected socket so socketpair() can drive it without a filesystem endpoint"
    - "query_snapshot raises rather than returning a sentinel; degraded-mode swallowing belongs at the App's worker boundary"

key-files:
  created: []
  modified:
    - claude_monitor/core.py
    - claude_monitor/test_claude_monitor.py

key-decisions:
  - "query_snapshot raises on every failure mode (FileNotFoundError / ConnectionRefusedError / socket.timeout / JSONDecodeError) -- a sentinel return would make 'no daemon' indistinguishable from 'daemon with no usage yet'"
  - "TUI_SOCK_TIMEOUT (1.5s) is asserted strictly below TUI_FETCH_INTERVAL (2.0s) in --selfcheck, so a hung daemon can never pile up fetch threads (Pitfall 2 / T-09-02)"
  - "The whole TUI substrate landed as one section at the END of core.py rather than splitting constants into the HISTORY_PATH neighbourhood -- constants and the functions that read them stay adjacent"
  - "fmt_elapsed zero-pads the day-tier hours ('3d 02h') per the plan's literal examples; the JS fmtDur it translates emits '3d 2h'. Cosmetic-only, and dashboard.py is untouched"

patterns-established:
  - "Marker comments ('change both' / 'change all three') on every string or path literal duplicated across surfaces, since claude-monitor.py is frozen this phase"
  - "Socket asserts via socket.socketpair() + a writer thread, extending the existing wire-protocol block's harness"

requirements-completed: [TUI-01, TUI-02, TUI-03, TUI-04, TUI-05]

coverage:
  - id: D1
    description: "AF_UNIX snapshot client (read_line, query_snapshot) that bounds a hung daemon and never raises UnicodeDecodeError on a non-utf-8 project dir"
    requirement: "TUI-05"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py#--- tui socket client (TUI-05) ---"
        status: pass
    human_judgment: false
  - id: D2
    description: "tui_usage_rows: D-01's compact 5h/7d cap rows across all three usage None cases and the reset-in-the-past boundaries"
    requirement: "TUI-01"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py#--- tui usage rows (TUI-01) ---"
        status: pass
    human_judgment: false
  - id: D3
    description: "trend_text: the snapshot's trend rows joined verbatim, with the collecting-state string for None/[]"
    requirement: "TUI-02"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py#--- tui trend text (TUI-02) ---"
        status: pass
    human_judgment: false
  - id: D4
    description: "sess_rows / sess_rank / sess_elapsed / fmt_elapsed: waiting->running->done ordering, stable equal-rank order, D-09 running-ticks vs frozen split, empty-state row"
    requirement: "TUI-03"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py#--- tui session rows (TUI-03/TUI-04) ---"
        status: pass
    human_judgment: false
  - id: D5
    description: "Refresh timing constants with TUI_SOCK_TIMEOUT < TUI_FETCH_INTERVAL asserted as a standing guard against fetch-thread pile-up"
    requirement: "TUI-04"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py#assert TUI_SOCK_TIMEOUT < TUI_FETCH_INTERVAL"
        status: pass
    human_judgment: false
  - id: D6
    description: "The whole substrate imports and runs on /usr/bin/python3 with no textual installed -- the load-bearing architectural split of this phase"
    requirement: "TUI-04"
    verification:
      - kind: integration
        ref: "/usr/bin/python3 claude-monitor.py --selfcheck"
        status: pass
      - kind: integration
        ref: "/usr/bin/python3 -c 'from claude_monitor.core import ... ' (13-symbol import)"
        status: pass
    human_judgment: false

# Metrics
duration: 18min
completed: 2026-07-21
status: complete
---

# Phase 9 Plan 01: Pure TUI Substrate Summary

**Twelve textual-free symbols in `claude_monitor/core.py` -- an AF_UNIX snapshot client, D-01's compact cap rows, verbatim trend text and the v1.4 sessions panel translated to Python -- all provable by `--selfcheck` on the system interpreter that cannot have textual.**

## Performance

- **Duration:** ~18 min
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `read_line` + `query_snapshot` implement the Phase 8 wire contract client-side: `settimeout` before `connect` bounds a hung connect *and* a hung read at 1.5s, the read loop terminates on EOF as well as on the newline, and `finally: s.close()` closes the fd leak that `claude-send.py:34-41` still has.
- `tui_usage_rows` mirrors `Monitor.usage_rows`' three-way `None` branching in D-01's two-row shape, using only `fmt_tokens` / `fmt_countdown` / `fmt_countdown_wk` / `round()` -- no new number formatter, so the TUI's rounding is identical to the tray menu's by construction.
- `trend_text` joins the snapshot's rows and recomputes nothing (D-05), asserted against `build_trend_rows`' own output for a synthetic record set.
- `sess_rank` / `sess_elapsed` / `fmt_elapsed` / `sess_rows` translate `dashboard.py:399-404,468-518` from JavaScript to Python: rank-map ordering with `sorted`'s stability, the running-ticks vs frozen split, the literal dash for neither, and the single empty-state row.
- Four banner blocks in `demo()`, including a socketpair exercise with a split-delivery writer thread, an EOF-mid-line case, a non-utf-8 byte case, and a markup-hostile project dir asserted to come back byte-for-byte unaltered.

## Task Commits

1. **Task 1: Add the pure TUI substrate to claude_monitor/core.py** - `1455a45` (feat)
2. **Task 2: Assert the new substrate in the --selfcheck suite** - `e75a04b` (test)

## Files Created/Modified

- `claude_monitor/core.py` - +166 lines: `socket` import, five TUI constants, and eight new pure functions in one trailing section
- `claude_monitor/test_claude_monitor.py` - +159 lines: eleven new names in the `from .core import (...)` tuple plus four assert blocks in `demo()`

## Decisions Made

- **Placement:** the constants sit with their functions in one trailing "TUI substrate" section rather than in the `HISTORY_PATH` / `TREND_MIN_SPAN` neighbourhood the plan suggested. Adjacency beats the plan's grouping here; the acceptance criteria are placement-agnostic.
- **`fmt_elapsed` day tier renders `3d 02h`** (zero-padded hours) per the plan's literal examples. The JS `fmtDur` it translates emits `3d 2h`. Cosmetic divergence between two independent surfaces, and `dashboard.py` is untouched this phase.
- **Defensive reads on the optional usage keys.** `tui_usage_rows` uses `usage.get(...)` for `tokens_used` / `token_limit` / `seven_day_pct` / `seven_day_reset` (the tray's reference indexes them directly) because the dict crosses a JSON wire from a possibly-older daemon. Behaviour is identical when the keys are present.

## Deviations from Plan

None - plan executed exactly as written (the two items above are stylistic choices inside the plan's stated latitude, not deviation-rule fixes).

## Issues Encountered

- The U+FFFD assert was first written with the literal replacement glyph, which would have broken the ASCII-only house rule. Rewritten as the escape sequence; a whole-file non-ASCII scan now confirms `SPARK_GLYPHS` is the only non-ASCII line in either file (D-06's intended exception).

## Verification

- `just selfcheck` -> exit 0, final line `ok`
- `/usr/bin/python3 claude-monitor.py --selfcheck` -> exit 0 (the textual boundary holds on the PEP 668 system interpreter)
- `just lint` -> exit 0
- `grep -c '# --- tui' claude_monitor/test_claude_monitor.py` -> 4
- `git diff --stat claude-monitor.py` -> empty (the daemon is byte-unchanged, as required)
- **Mutation check:** flipping `sess_rank`'s unknown-status fallback from 99 to 0 turns `just selfcheck` red (exit 1, `AssertionError` at the TUI-03 block); restored immediately. The new asserts have teeth.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 09-02 (`claude-tui.py`) can now be App-class-and-CSS only: every decision it needs is an importable, asserted `core` symbol.
- Carry-over for 09-02: `DataTable.add_row` parses `str` cells as markup with no opt-out (Pitfall 3), so escaping the `dir` cell is 09-02's job -- `sess_rows` deliberately returns it raw.
- Carry-over for 09-02: `query_snapshot` raises by design; the `try/except Exception` that satisfies D-12 must live in the worker body, and `@work` needs `exit_on_error=False`.

## Self-Check: PASSED

- `claude_monitor/core.py` - FOUND (modified)
- `claude_monitor/test_claude_monitor.py` - FOUND (modified)
- Commit `1455a45` - FOUND
- Commit `e75a04b` - FOUND

---
*Phase: 09-terminal-dashboard-claude-tui-py*
*Completed: 2026-07-21*
