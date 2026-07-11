---
phase: 01-usage-quota-monitoring-in-the-tray
fixed_at: 2026-07-11T00:00:00Z
review_path: .planning/phases/01-usage-quota-monitoring-in-the-tray/01-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 1
skipped: 2
status: partial
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-07-11
**Source review:** .planning/phases/01-usage-quota-monitoring-in-the-tray/01-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (WR-01, WR-02, WR-03; Info findings out of scope)
- Fixed: 1
- Skipped: 2 (already applied in source before this run)

## Fixed Issues

### WR-03: a single transient poll failure blanks the usage display for the whole interval

**Files modified:** `claude-monitor.py`
**Commit:** 13add2d
**Applied fix:** `Monitor.apply_usage` assigned `self.usage = usage` unconditionally, so a
transient `None` (e.g. one CLI invocation exceeding the 15s timeout) wiped the last-good
usage and showed "usage unavailable" until the next successful poll. Guarded the assignment
with `if usage is not None:` so a momentary hiccup shows slightly-stale data instead of an
empty readout. "usage unavailable" now only appears at startup before the first successful
poll. Matches the review's suggested fix; behavior change worth a manual confirm.

## Skipped Issues

### WR-01: parse_usage validates structure but not value types

**File:** `claude-monitor.py:48-62` (per review)
**Reason:** already applied in source. The type-rejection guard the review requested is
present at `claude-monitor.py:77-84` (`if not all(isinstance(v, (int, float)) and not
isinstance(v, bool) for v in u.values()): return None`), and the matching demo() asserts
for `used_percentage: None` and a non-numeric `resets_at_epoch` are present at lines
158-192. No further change needed.
**Original issue:** null/string but structurally-valid CLI fields would pass parse and then
crash the Gtk main thread in `round()`/epoch math inside a GLib callback, killing the
countdown timer.

### WR-02: fetch_usage catches only two exception types

**File:** `claude-monitor.py:71-77` (per review)
**Reason:** already applied in source. The catch is broadened to
`except (subprocess.SubprocessError, OSError)` at `claude-monitor.py:100`, which covers
`TimeoutExpired` (SubprocessError) plus `FileNotFoundError`/`PermissionError` and other
`OSError` subclasses — the review's "and/or" fix is satisfied by the broadened catch, so the
poll thread can no longer die on a present-but-not-executable CLI. No further change needed.
**Original issue:** a `PermissionError`/`OSError` from `subprocess.run` propagated into the
unguarded `poll_loop`, permanently killing the daemon poll thread.

---

_Fixed: 2026-07-11_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
