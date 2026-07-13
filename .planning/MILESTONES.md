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

## v1.2 — Usage Web Dashboard (shipped 2026-07-13)

**Goal:** Turn the v1.1 JSONL history into a browsable, self-contained HTML dashboard
opened from the tray — real charts over ranges the cramped tray menu cannot hold —
read-only over the existing store, stdlib only, no new polling and no new dependencies.

**Delivered:**

- "Open Usage Dashboard" tray item opens a stdlib-generated, fully self-contained `file://` page (inline CSS/JS, SVG charts, no external fetches — enforced by a `--selfcheck` assertion, not just intended) — DASH-01/06
- Usage-% trend chart over rolling `24h / 7d / All` ranges, with the line **broken across sampling gaps** rather than interpolating a decline that never happened — DASH-02/08
- Hour-of-day x day-of-week peak-usage heatmap, denominated in mean usage % (not raw burn) to match the rest of the page — DASH-03
- Dark-mode toggle defaulting to `prefers-color-scheme`, persisted, with an inverted heatmap ramp so low-usage cells do not glow on a dark page — DASH-07
- Generated off the Gtk main thread on the existing poll tick from `~/.claude/usage-history.jsonl` — no second data source, no new polling — DASH-05
- **Weekly (7-day) cap made visible everywhere** — parsed from `limits.seven_day`, shown in the tray rows and on the dashboard, with the icon badge now warning when *either* cap is hot; a 95%-weekly / 10%-five-hour state previously produced no warning at all — QUOTA-01 *(closes deferred SEED-003)*
- Reset epochs persisted to history, so the trend **marks window resets** — the sawtooth drops now read as "the window rolled", not "usage fell" — QUOTA-02
- Projected usage at reset for both caps, drawn on the chart and in the status card, derived from percentages only — the CLI's own token-based `forecast`/`status` were deliberately not used, since token counts come back `null` under `--api` and would have claimed exhaustion at 20% usage — QUOTA-03

**Descoped:** DASH-04 (burn-rate trend chart) was built as specified, then removed
during UAT (`ae0691f`) — it plotted near-flat ~30M tok/hr raw-throughput numbers and
duplicated what the heatmap already showed more usefully. A scope decision made
against the running artifact, not a failure.

**Verification:** Phase 04 VERIFICATION.md `status: passed` — automated `--selfcheck`,
code review, security audit, UI audit, and human UAT. Requirements 10/11 delivered
(DASH-04 descoped by decision).

**Known deferred items:** 3 (see STATE.md "Deferred Items").

**Phases:** 04-usage-web-dashboard (verified).
