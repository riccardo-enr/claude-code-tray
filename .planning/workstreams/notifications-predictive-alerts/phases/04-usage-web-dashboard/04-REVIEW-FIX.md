---
phase: 04-usage-web-dashboard
fixed_at: 2026-07-12T00:00:00Z
review_path: .planning/phases/04-usage-web-dashboard/04-REVIEW.md
iteration: 1
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 04: Code Review Fix Report

**Fixed at:** 2026-07-12
**Source review:** .planning/phases/04-usage-web-dashboard/04-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 1 (WR-01; Info findings IN-01/IN-02 out of scope for critical_warning)
- Fixed: 1
- Skipped: 0

## Fixed Issues

### WR-01: `history_numeric` accepts NaN/Infinity and out-of-range `t`, silently and permanently breaking the dashboard

**Files modified:** `claude-monitor.py`
**Commit:** 2fdb913
**Applied fix:** Tightened `history_numeric` (the single sanitizer choke point) so pathological-but-numeric records are dropped at the one validation boundary:

- Added `import math` to the stdlib import block (alphabetical, between `json` and `os`).
- Extended the inner `num(v)` predicate with `math.isfinite(v)` so `NaN`/`Infinity`/`-Infinity` (which `json.loads` accepts by default) are rejected for `t`, `pct`, AND `burn`.
- Bounded `t` to a plausible epoch window (`0 < r["t"] < 4102444800`, i.e. before 2100-01-01 UTC) so `int(t)` / `datetime.fromtimestamp(t)` downstream can never overflow, and so a far-future record -- which `history_keep` never prunes -- cannot permanently break dashboard regeneration.
- Added `demo()`/`--selfcheck` asserts proving that records with `t=NaN`, `pct=inf`, `burn=inf`, and `t=1e18` are ALL dropped by `history_numeric` while a normal record survives, and that `render_dashboard` on a list whose only record carries such a value returns the empty-state ("Collecting usage history") page. No existing assert was weakened.

Verified: `python3 claude-monitor.py --selfcheck` prints `ok`. Source remains ASCII-only.

**Out-of-scope note:** The review flagged a shared-root-cause path in `compute_trends` (Phase-3 code) that would benefit from routing through `history_numeric`. Per the fix-pass scope (WR-01 only), `compute_trends` was deliberately left untouched.

---

_Fixed: 2026-07-12_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
