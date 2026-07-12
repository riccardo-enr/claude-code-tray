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

## v1.1 — Usage History & Trends (shipped 2026-07-12)

**Goal:** Persist usage samples over time and surface trends in the tray, turning
v1.0's point-in-time readout into history — without new polling or new dependencies.

**Delivered:**
- Append each successful poll to a bounded, corruption-tolerant `~/.claude/usage-history.jsonl` store, pruned past a 30-day retention window (env `CLAUDE_TRAY_HISTORY_DAYS`) — HIST-01/02/03
- In-menu 24h auto-scaled unicode-block sparkline of usage % — TREND-01
- Today / current-ISO-week mean burn rate in the menu — TREND-02
- Peak usage hour-of-day (by mean burn) in the menu — TREND-03
- All trend compute off the Gtk main thread (cached in `poll_loop`, ~5min throttle); no history I/O on the UI loop (upholds HIST-03/POLL-02)

**Verification:** Phase 02 UAT 3/3 passed + security review; Phase 03 automated
`--selfcheck` green (all new + prior asserts), goal-backward verification passed,
live-tray UAT confirmed the three trend rows render.

**Phases:** 02-usage-history-persistence (verified), 03-usage-trends-in-the-tray (verified).
