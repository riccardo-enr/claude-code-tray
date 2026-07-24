---
phase: 09-terminal-dashboard-claude-tui-py
fixed_at: 2026-07-24T00:00:00Z
review_path: .planning/workstreams/notifications-predictive-alerts/phases/09-terminal-dashboard-claude-tui-py/09-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 8
skipped: 0
status: all_fixed
---

# Phase 09: Code Review Fix Report

**Fixed at:** 2026-07-24
**Source review:** 09-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 8 (2 BLOCKER + 6 WARNING; Info out of scope)
- Fixed: 8
- Skipped: 0

**Gates after fixes:**
- `/usr/bin/python3 claude-monitor.py --selfcheck` (run inside the worktree against the
  patched `core.py`/tests): **exit 0**.
- `just selfcheck`: **exit 0** (note: this recipe runs the deployed symlink
  `~/.claude/hooks/claude-monitor.py`, which points at the main working tree, so it
  proves the boundary generally but does not exercise the worktree's patched code; the
  direct in-worktree selfcheck above is the authoritative test of these changes).
- `ruff check .`: **All checks passed!**

## Fixed Issues

### CR-01: 1s render tick reset the sessions table scroll to top (D-01 broken)

**Files modified:** `claude-tui.py`
**Commit:** 64000a4
**Applied fix:** In `render_all`, captured `table.scroll_y` before `table.clear()`
(which zeroes scroll in textual 8.2.8) and restored it after re-adding rows.
`validate_scroll_y` re-clamps if the session list shrank. This is the two-line "lazy"
fix from the review; the larger update-cell-only rebuild was intentionally not taken.

### CR-02: rich.text.Text does not strip ANSI escapes -> terminal-control injection

**Files modified:** `claude_monitor/core.py`, `claude_monitor/test_claude_monitor.py`
**Commit:** 09b26df
**Applied fix:** Added pure `_safe_cell()` to `core.py` that replaces any
non-printable character (ESC, CSI, BEL, etc.) with `?`, and wrapped the `dir` cell in
`sess_rows` with it. Printable markup like `[bold]x[/]` passes through byte-for-byte
(markup injection is still closed at the widget). Updated the selfcheck contract at
`test_claude_monitor.py:768` (which previously asserted byte-for-byte passthrough) with
three `_safe_cell` assertions covering ESC/CSI/BEL/BS stripping and printable-markup
preservation, and added `_safe_cell` to the test imports. Selfcheck exit 0.

### WR-01: TUI_SOCK_TIMEOUT bounds each recv, not the whole read; buffer unbounded

**Files modified:** `claude_monitor/core.py`
**Commit:** 6752ce6
**Applied fix:** Gave `read_line` optional `deadline` (a `time.monotonic()` instant) and
`max_bytes=1<<20` parameters -- raises `TimeoutError` past the deadline and `ValueError`
past the size cap. `query_snapshot` now passes `time.monotonic() + timeout`. The new
kwargs are optional, so the socketpair-driven selfcheck tests (single-arg calls) still
pass unchanged. Selfcheck exit 0.

### WR-02: non-dict JSON re-arms the cold-start predicate under a "live" header

**Files modified:** `claude_monitor/core.py`
**Commit:** 38dca18
**Applied fix:** `query_snapshot` now validates the parsed value with
`isinstance(obj, dict)` and raises `ValueError` for `null`/list/scalar, so a malformed
line becomes a failure the degraded-mode state machine owns rather than binding
`snapshot=None` under a "live" header. Selfcheck exit 0.

### WR-03: render failure mislabelled "daemon unreachable"; half-applied state

**Files modified:** `claude-tui.py`
**Commit:** 50b4a36
**Applied fix:** `apply_snapshot` now renders via `self.tick()` (same guard as the 1s
tick) instead of an unguarded `render_all()`, and commits `sub_title = "live"` only when
the render did not set the "render error" header. A render-time exception now surfaces as
"render error -- frame may be stale" instead of being routed to the worker's except and
mislabelled "daemon unreachable". **Requires human verification:** this is a behavioral
change in error routing in `claude-tui.py`, which is not reachable by `--selfcheck`;
verified only by Tier 1 re-read and `ast.parse`.

### WR-04: command palette still bound -> D-02's "exactly one binding" not enforced

**Files modified:** `claude-tui.py`
**Commit:** 00b55ac
**Applied fix:** Added `ENABLE_COMMAND_PALETTE = False` class attribute, which stops
textual from binding `ctrl+p` / advertising it in the Footer and removes access to
`action_change_theme`. `q` is now genuinely the only binding.

### WR-05: TUI runtime deps not covered by a lockfile (T-09-SC not in force)

**Files modified:** `claude-tui.py`, `claude-tui.py.lock` (new file)
**Commit:** f49a768
**Applied fix:** Ran `uv lock --script claude-tui.py` (uv 0.7.1) to produce
`claude-tui.py.lock` pinning the full transitive set (10 packages) with hashes;
committed it. `uv run --script` picks it up automatically. Added a note to the module
docstring recording that the lock is authoritative and how to regenerate it. New file
creation was required and is intentional (the lock must ship).

### WR-06: tui_usage_rows subscripts three usage keys while .get()-ing the rest

**Files modified:** `claude_monitor/core.py`
**Commit:** 5f40edd
**Applied fix:** `tui_usage_rows` now reads `used_percentage`, `resets_at_epoch` and
`burn_rate_per_min` via `.get()` and returns the existing `["usage unavailable"]`
fallback if any is `None`, matching the `.get()` discipline of every sibling helper and
preventing a false "daemon unreachable" (WR-03) when the cross-socket shape drifts.
Selfcheck exit 0.

## Skipped Issues

None -- all in-scope findings were fixed.

Info findings (IN-01..IN-05) were out of scope (`critical_warning`) and left untouched.

---

_Fixed: 2026-07-24_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
