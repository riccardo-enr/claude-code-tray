# Roadmap: claude-code-tray

## Overview

A GNOME top-bar tray indicator for Claude Code. It shows per-session status and
focuses the originating tmux pane + Ghostty window on click. Three shipped
milestones extended that same single-file helper (`claude-monitor.py`) into a
quota monitor: point-in-time usage, then persisted history and in-menu trends,
then a browsable HTML dashboard.

Constraints that held across all three: stdlib + PyGObject only, X11-only, one
background poll, no new dependencies.

Full phase detail for shipped milestones lives in `.planning/milestones/`;
per-phase artifacts remain under `.planning/phases/`.

## Milestones

- ✅ **v1.0 Usage & Quota Monitoring** — Phase 1 (shipped 2026-07-11)
- ✅ **v1.1 Usage History & Trends** — Phases 2-3 (shipped 2026-07-12)
- ✅ **v1.2 Usage Web Dashboard** — Phase 4 (shipped 2026-07-13) — [archive](./milestones/v1.2-ROADMAP.md)
- 📋 **v1.3** — not yet scoped (`/gsd-new-milestone`)

## Phases

<details>
<summary>✅ v1.0 Usage & Quota Monitoring (Phase 1) — SHIPPED 2026-07-11</summary>

- [x] Phase 1: Usage & Quota Monitoring in the Tray (1/1 plans) — completed 2026-07-11

Background-polled usage rows (tokens/percent, reset countdown, burn rate) plus a
high-usage icon badge, degrading to "usage unavailable" when the CLI call fails.

</details>

<details>
<summary>✅ v1.1 Usage History & Trends (Phases 2-3) — SHIPPED 2026-07-12</summary>

- [x] Phase 2: Usage History Persistence (1/1 plans) — completed 2026-07-12
- [x] Phase 3: Usage Trends in the Tray (1/1 plans) — completed 2026-07-12

Bounded, corruption-tolerant `~/.claude/usage-history.jsonl` written from the
existing poll, then read back as an in-menu sparkline, today/week burn, and peak
usage hour — all computed off the Gtk main thread.

</details>

<details>
<summary>✅ v1.2 Usage Web Dashboard (Phase 4) — SHIPPED 2026-07-13</summary>

- [x] Phase 4: Usage Web Dashboard (1/1 plans) — completed 2026-07-13

Self-contained `file://` HTML dashboard opened from a tray item: usage-% trend
over rolling 24h/7d/All (line broken across data gaps), hour x day heatmap, dark
mode. Delivered beyond original scope: weekly (7-day) cap parsing, display and
badge warning (QUOTA-01, closes SEED-003); reset markers (QUOTA-02); projected
usage at reset (QUOTA-03). Descoped during UAT: DASH-04 burn-rate trend chart
(`ae0691f`) — near-flat raw-throughput numbers the heatmap already showed better.

</details>

### 📋 v1.3 (not yet scoped)

Run `/gsd-new-milestone` to define it. Candidate seeds carried forward:

- SEED-002: predictive quota alerts (surface a forecast + notify)
- SEED-004: desktop notification when a Claude Code session finishes

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Usage & Quota Monitoring in the Tray | v1.0 | 1/1 | Complete | 2026-07-11 |
| 2. Usage History Persistence | v1.1 | 1/1 | Complete | 2026-07-12 |
| 3. Usage Trends in the Tray | v1.1 | 1/1 | Complete | 2026-07-12 |
| 4. Usage Web Dashboard | v1.2 | 1/1 | Complete | 2026-07-13 |
