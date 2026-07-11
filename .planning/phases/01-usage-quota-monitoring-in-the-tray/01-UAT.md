---
gsd_uat_version: 1.0
phase: 01-usage-quota-monitoring-in-the-tray
status: passed
total_tests: 4
passed: 4
failed: 0
current_test: done
last_updated: 2026-07-11
---

# Phase 01 UAT — Usage & Quota Monitoring in the Tray

Automated checks (selfcheck, symbols, parse, no-shell=True) all passed before manual testing.

## Result: PASSED (4/4)

During testing, Test 4 surfaced a defect: the earlier WR-03 fix retained last-good
usage on ANY failed poll, so after the first successful poll the tray never returned
to "usage unavailable" — a dead CLI showed stale quota forever, violating POLL-02.

Fix applied (commit on main): consecutive-miss counter (`USAGE_MISS_LIMIT = 2`) in
`Monitor.apply_usage` — absorbs transient failures (WR-03) but drops to "usage
unavailable" after sustained failure (POLL-02), resetting on a successful poll.
Verified headlessly: fetch_usage->None when CLI gone; miss1 retains, miss2 blanks,
good poll recovers.

## Test Results

| # | Test | Status | Notes |
|---|------|--------|-------|
| 1 | Usage rows render (USAGE-01/02/03) | pass | User confirmed all three rows visible |
| 2 | Icon label leads with usage %, `!` above 80% (ALERT-01) | pass | User confirmed |
| 3 | Session rows still focus tmux pane + Ghostty on click | pass | User confirmed regression-free |
| 4 | CLI failure -> single "usage unavailable", sessions intact (POLL-02) | pass | Defect found + fixed (miss-counter); verified headlessly |
