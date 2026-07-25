---
phase: 260725-ppf
plan: 01
subsystem: infra
tags: [python, rust, gtk, tmux, sanitization, socket-ipc]

requires: []
provides:
  - "fetch_usage() catches ValueError (UnicodeDecodeError) alongside SubprocessError/OSError"
  - "sess_rows() guards a non-string/null 'dir' from a malformed socket snapshot"
  - "dashboard.py's drawChart() uses a manual reduce instead of Math.min/max.apply, avoiding a call-stack overflow past ~65536 retained history points"
  - "claude-monitor.py's _handle_conn bounds focus-routing field lengths (FOCUS_FIELD_MAX_CHARS=256), matching the Rust client's MAX_ROUTE_CHARS"
  - "claude-send.py's send_event() closes the socket via finally, fixing a documented fd leak on a sendall failure"
  - "Rust Session::id is now kept raw (identity-only) instead of sanitized, fixing a stable_key collision between daemon-distinct ids"
affects: [rust-client-foundation]

tech-stack:
  added: []
  patterns:
    - "Socket send helpers must close via try/finally, not just after the last statement in a try block, or an exception mid-send leaks the fd"
    - "A field used only for identity/keying (never rendered) must stay raw; sanitizing it for 'consistency' can silently destroy uniqueness"

key-files:
  created: []
  modified:
    - claude_monitor/core.py
    - claude_monitor/dashboard.py
    - claude_monitor/test_claude_monitor.py
    - claude-monitor.py
    - claude-send.py
    - rust/src/main.rs
    - rust/src/snapshot.rs
    - rust/tests/fixtures.rs

key-decisions:
  - "Fixed fetch_usage()'s narrow except clause by adding ValueError (UnicodeDecodeError's actual base class) rather than widening to bare except Exception, keeping the existing convention of naming exactly what can happen"
  - "Rejected fixtures/generate.py's hostile-terminal-controls fixtures as NOT a bug: the Rust sanitizer already implements exactly the collapse-whole-sequence behavior the fixtures expect (verified via sanitize.rs's own unit tests and the fixture-driven test suite), so no change was needed there"
  - "Kept Session::id raw instead of sanitized, since it is identity-only and never rendered -- matches the existing 'opaque routing values are never sanitized' posture already established for FocusTarget"
  - "Skipped an unguarded accept() loop in serve() (claude-monitor.py) as out of scope: it was not in the pre-scouted findings, has a very low real-world likelihood (only resource-exhaustion errors like EMFILE), and a real regression test would require refactoring serve() for socket injectability -- an architectural change beyond this task's minimal-diff mandate"

requirements-completed: [QT-260725-ppf]

coverage:
  - id: D1
    description: "fetch_usage() no longer lets a UnicodeDecodeError escape and kill the poll thread"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py::demo (fetch_usage ValueError monkeypatch assert)"
        status: pass
    human_judgment: false
  - id: D2
    description: "sess_rows() no longer TypeErrors on a null/non-string 'dir' from a malformed socket snapshot"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py::demo (sess_rows null-dir assert)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Dashboard usage chart no longer throws 'Maximum call stack size exceeded' on large history"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py::demo (amin/amax presence assert against _DASH_JS source)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Daemon rejects over-long focus-routing values instead of accepting them unbounded"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py::demo (over-long pane focus socket assert)"
        status: pass
    human_judgment: false
  - id: D5
    description: "claude-send.py no longer leaks the socket fd when sendall raises"
    verification:
      - kind: unit
        ref: "claude_monitor/test_claude_monitor.py::demo (send_event fd-close-on-failure assert)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Rust session selection no longer collides when two daemon ids differ only in escape-sequence content"
    verification:
      - kind: unit
        ref: "rust/src/main.rs::tests::stable_key_uses_the_raw_id_not_the_sanitized_display_string"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-07-25
status: complete
---

# Phase 260725 Plan 01: Whole-repo bug sweep Summary

**Six real bugs fixed across the Python daemon and Rust client -- a UnicodeDecodeError poll-thread crash, a null-dir TypeError, a dashboard chart stack overflow, an unbounded focus-routing value, a socket fd leak, and a session-selection collision caused by sanitizing an identity-only field -- each backed by a new/extended assert or `#[test]`.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-07-25
- **Tasks:** 2
- **Files modified:** 8 (5 Python, 3 Rust)

## Accomplishments

- Read every Python source file (`claude_monitor/core.py`, `dashboard.py`, `claude-monitor.py`, `claude-send.py`, `claude-status.py`) and every Rust source file (`main.rs`, `format.rs`, `snapshot.rs`, `sanitize.rs`, `client.rs`, `error.rs`, `lib.rs`) plus `install.sh` and both tmux scripts end to end, tracing real control flow rather than isolated functions.
- Fixed 5 genuine Python bugs (crash, TypeError, JS stack overflow, missing length bound, fd leak) and 1 genuine Rust bug (session-selection collision from over-sanitizing an identity field).
- Every fix carries a regression check that fails without the fix.
- `just selfcheck`, `just lint`, `just rust-test`, and `just rust-lint` are all green.
- The pre-existing uncommitted tmux-powerline usage-segment work landed in a separate concurrent commit (`e793d75`, outside this task) and was never touched by this sweep.

## Task Commits

1. **Task 1: Audit and fix bugs in the Python daemon and install script** - `f65fcc8` (fix)
2. **Task 2: Audit and fix bugs in the Rust client and the tmux status segment script** - `d73db91` (fix)

## Files Created/Modified

- `claude_monitor/core.py` - `fetch_usage()` catches `ValueError` too; `sess_rows()` guards a non-string `dir`
- `claude_monitor/dashboard.py` - `drawChart()`'s embedded JS uses manual `amin`/`amax` reduce helpers instead of `Math.min/max.apply(null, arr)`
- `claude_monitor/test_claude_monitor.py` - new/extended asserts for all 5 Python fixes
- `claude-monitor.py` - `_handle_conn`'s focus branch bounds routing-field lengths to `FOCUS_FIELD_MAX_CHARS` (256)
- `claude-send.py` - `send_event()` extracted with a `try/finally` close, fixing the fd leak `core.query_snapshot`'s own docstring named
- `rust/src/main.rs` - new regression test for `stable_key`'s raw-id fix
- `rust/src/snapshot.rs` - `Session::id` kept raw (not run through `sanitize_display`)
- `rust/tests/fixtures.rs` - the corpus-wide escape-byte scan no longer includes `id` (it is identity-only, never rendered)

## Decisions Made

- Added `ValueError` to `fetch_usage()`'s except clause rather than widening to a bare `except Exception`, preserving the file's convention of naming exactly which failure modes are expected.
- Investigated the plan's flagged `fixtures/generate.py` "collapse-whole-sequence" fixtures against the Rust sanitizer (`sanitize.rs`) and its own passing unit test suite -- the sanitizer already implements exactly that contract, so this was not a real bug and nothing was changed there.
- Kept `Session::id` raw instead of sanitized: it is never rendered (confirmed via `grep` across `main.rs`), only used for `stable_key` identity, so sanitizing it destroyed uniqueness for zero display benefit -- matches the existing "opaque routing values are never sanitized" posture already established for `FocusTarget`.
- Deliberately did NOT guard `serve()`'s unguarded `accept()` loop in `claude-monitor.py` even though it is a real (if very low-probability) gap in the daemon's established "every thread loop survives a bad iteration" convention: it was not in the pre-scouted findings, and writing a real regression test for it would require refactoring `serve()` to accept an injectable socket -- an architectural change beyond this task's minimal-diff mandate. Left as a candidate for a future task if it ever matters.

## Deviations from Plan

None beyond what the pre-scouted findings already anticipated -- this task's whole nature is "investigation IS the deliverable." All 6 fixes below were pre-scouted by parallel investigation before execution began; each was independently re-verified against the actual code before being fixed.

### Auto-fixed Issues

**1. [Rule 1 - Bug] `fetch_usage()` could crash the poll thread on a locale-invalid byte**
- **Found during:** Task 1
- **Issue:** `subprocess.run(..., text=True)` can raise `UnicodeDecodeError` (a `ValueError` subclass), which the `except (subprocess.SubprocessError, OSError)` clause does not catch -- violating the module's "daemon poll thread can never die" contract.
- **Fix:** Added `ValueError` to the except tuple.
- **Files modified:** `claude_monitor/core.py`, `claude_monitor/test_claude_monitor.py`
- **Committed in:** `f65fcc8`

**2. [Rule 1 - Bug] `sess_rows()` TypeErrors on a null `dir` from a malformed socket snapshot**
- **Found during:** Task 1
- **Issue:** `s.get("dir", "")` only defaults when the key is missing, not when it is present but `None`/non-string; `_safe_cell` then does `for c in s`, raising `TypeError: 'NoneType' object is not iterable`.
- **Fix:** Guard the value's type before passing to `_safe_cell`, defaulting to `""`.
- **Files modified:** `claude_monitor/core.py`, `claude_monitor/test_claude_monitor.py`
- **Committed in:** `f65fcc8`

**3. [Rule 1 - Bug] Dashboard usage chart throws past ~11 days of default-interval history**
- **Found during:** Task 1
- **Issue:** `Math.min.apply(null, xs)` / `Math.max.apply(null, xs/ys)` pass the whole retained-history array as call arguments; past a JS-engine argument-count ceiling (V8's is 65536) this throws `RangeError: Maximum call stack size exceeded`, breaking the default "All" range view with no fallback.
- **Fix:** Replaced with `amin`/`amax` manual-reduce helpers.
- **Files modified:** `claude_monitor/dashboard.py`, `claude_monitor/test_claude_monitor.py`
- **Committed in:** `f65fcc8`

**4. [Rule 2 - Missing Critical] Focus-routing values had no length bound on the Python daemon side**
- **Found during:** Task 1
- **Issue:** `_handle_conn`'s focus branch only checked `isinstance(value, str)`, no length bound, while `fixtures/generate.py`'s `focus-routing-value-over-bound` fixture (and the Rust client's `MAX_ROUTE_CHARS`) documents and expects rejection of an over-long routing value.
- **Fix:** Added `FOCUS_FIELD_MAX_CHARS = 256` and bound the check.
- **Files modified:** `claude-monitor.py`, `claude_monitor/test_claude_monitor.py`
- **Committed in:** `f65fcc8`

**5. [Rule 1 - Bug] `claude-send.py` leaks the socket fd when `sendall` raises**
- **Found during:** Task 1
- **Issue:** `s.close()` sat as the last statement inside the `try` block, so an exception from `connect()`/`sendall()` skipped it entirely -- a leak already called out by name in `core.query_snapshot`'s own docstring ("claude-send.py:34-41 omits it and leaks the fd when sendall raises").
- **Fix:** Extracted `send_event()` with a `try/finally` close.
- **Files modified:** `claude-send.py`, `claude_monitor/test_claude_monitor.py`
- **Committed in:** `f65fcc8`

**6. [Rule 1 - Bug] Rust session selection collides when two ids differ only in escape-sequence content**
- **Found during:** Task 2
- **Issue:** `Session::id` was sanitized like a display string, but `stable_key` (its only reader) never renders it -- `sanitize_display` collapses any complete escape sequence to one `?` marker, so two daemon-distinct ids (e.g. `"a\x1b[2Jsame"` and `"a\x1b[31msame"`) both sanitized to `"a?same"`. `selected_index`'s `position()` then always resolved to the first match, permanently blocking selection of the second session.
- **Fix:** Kept `id` raw in `normalize_session`; updated the fixture-corpus escape-byte scan to stop treating `id` as a display string.
- **Files modified:** `rust/src/snapshot.rs`, `rust/src/main.rs`, `rust/tests/fixtures.rs`
- **Committed in:** `d73db91`

---

**Total deviations:** 0 (all fixes were the plan's stated deliverable, not deviations from it)
**Impact on plan:** None -- this task's entire scope was "find and fix real bugs," and all 6 fixes are exactly that.

## Issues Encountered

None. The pre-scouted findings from four parallel investigation agents matched the actual code on re-verification in all 6 cases, and one additional candidate ("hostile-terminal-controls" fixture mismatch) was investigated and confirmed to be a non-issue rather than fixed speculatively.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All four verification gates (`just selfcheck`, `just lint`, `just rust-test`, `just rust-lint`) are green.
- No architectural changes; no new dependencies.
- The Rust client foundation (Phase 11) is unaffected in shape -- `Session::id`'s type is unchanged (`String`), only its normalization no longer sanitizes it.

---
*Phase: 260725-ppf*
*Completed: 2026-07-25*

## Self-Check: PASSED

All 9 files (5 Python, 3 Rust, this SUMMARY) verified present on disk; both commit hashes (`f65fcc8`, `d73db91`) verified present in `git log --all`.
