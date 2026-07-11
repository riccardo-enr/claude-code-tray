# Milestones

## v1.0 — Usage & Quota Monitoring in the Tray (shipped 2026-07-11)

**Goal:** Surface Claude Code token usage and quota-reset info in the existing tray,
sourced from the `claude-monitor` CLI, without launching a separate terminal monitor.

**Delivered:**
- Background-thread poll of `claude-monitor --output json` (never blocks Gtk) — POLL-01
- Graceful degradation to "usage unavailable" on CLI failure — POLL-02
- Tokens/percent row, live reset countdown, burn-rate row — USAGE-01/02/03
- High-usage icon badge (`!` above 80%) — ALERT-01

**Verification:** Phase 01 UAT passed 4/4. During UAT, a POLL-02 defect (stale-usage
retained forever after a WR-03 fix) was found and fixed with a consecutive-miss counter.

**Phases:** 01-usage-quota-monitoring-in-the-tray (verified).
