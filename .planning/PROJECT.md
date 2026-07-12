# claude-code-tray

## What This Is

A GNOME top-bar tray indicator for Claude Code. It already shows per-session
status (running / waiting / done) fed by Claude Code hooks over a unix socket,
and focuses the originating tmux pane + Ghostty window on click. v1.0 added
**token-usage and quota-reset monitoring** (current usage vs plan limit, reset
countdown, burn rate). v1.1 added **usage history and trends** on top: persisted
samples, an in-menu sparkline, daily/weekly burn, and peak-usage hours. v1.2 adds
a **browsable HTML usage dashboard** opened from the tray, rendering the same
history as real charts (trends, peak-hour heatmap, longer ranges).

## Core Value

At a glance from the top bar, know **how much Claude Code quota is left and when
it resets** — without launching a separate terminal monitor.

## Context

- **Platform:** Ubuntu GNOME on X11; Python 3 + PyGObject (Gtk3, Ayatana
  AppIndicator3). Single long-lived helper process (`claude-monitor.py`) plus a
  fire-and-forget hook sender (`claude-send.py`).
- **Data source (decided):** shell out to the already-installed `claude-monitor`
  CLI (Claude Code Usage Monitor) with `--plan max5 --output json --once`. It
  parses `~/.claude/projects/**/*.jsonl` and returns `limits.five_hour`
  (`used_percentage`, `tokens_used`, `token_limit`, `resets_at_epoch`) plus
  `local.tokens` and burn rate. Reused rather than reinventing the rolling-window
  + plan-limit math.
- **Naming caution:** the usage tool is *also* called `claude-monitor`; our
  helper is `claude-monitor.py` in `~/.claude/hooks/`. Keep the distinction
  clear (invoke the CLI by absolute path `~/.local/bin/claude-monitor`).
- **Performance constraint:** the CLI takes a few seconds to run, so polling
  must happen on a background thread on an interval, never on the Gtk main loop.

## Current Milestone: v1.2 Usage Web Dashboard

**Goal:** Turn the persisted `~/.claude/usage-history.jsonl` history into a
browsable HTML dashboard opened from the tray — real charts (trends, peak-hour
heatmap, longer ranges) that complement the cramped tray menu, not replace it.

**Target features:**
- A tray menu item that opens a usage dashboard in the browser
- Usage-% and burn-rate trend charts over a longer, selectable range than the tray
- Peak-usage heatmap (hour-of-day x day-of-week)
- Read-only over the existing Phase-2 JSONL; no new polling; refreshed on the existing poll tick
- Self-contained, stdlib-only output (no new deps) matching the project's constraints

## Requirements

### Validated

- checkmark Per-session status in tray menu (running/waiting/done) — existing
- checkmark Click-to-focus tmux pane + raise terminal window — existing
- checkmark Hook -> unix socket event pipeline (`claude-send.py`) — existing
- checkmark Autostart via `~/.config/autostart` + env-configurable icon/WM_CLASS — existing
- checkmark Background-interval `claude-monitor` poll without blocking the UI (POLL-01) — v1.0
- checkmark Graceful degradation to "usage unavailable" on CLI failure (POLL-02) — v1.0
- checkmark Tokens/% of plan limit, reset countdown, burn rate in the tray (USAGE-01/02/03) — v1.0
- checkmark High-usage icon badge above threshold (ALERT-01) — v1.0
- checkmark Persist each successful poll sample to a JSONL history store (HIST-01) — Phase 2
- checkmark Prune history past a retention window, default 30 days env-configurable (HIST-02) — Phase 2
- checkmark Defensive history I/O — never crash/block the helper (HIST-03) — Phase 2
- checkmark In-menu sparkline of usage % over a recent window (TREND-01) — Phase 3
- checkmark Daily / weekly aggregate burn in the menu (TREND-02) — Phase 3
- checkmark Peak-usage hours in the menu (TREND-03) — Phase 3

### Active (v1.2)

- [ ] Open a browsable usage dashboard in the browser from a tray menu item (DASH-01)
- [ ] Usage-% trend chart over a longer, selectable range than the tray (DASH-02)
- [ ] Peak-usage heatmap (hour-of-day x day-of-week) from history (DASH-03)
- [ ] Burn-rate trend over the full retained history (DASH-04)
- [ ] Reads the existing `~/.claude/usage-history.jsonl` (read-only, no new polling); refreshes on the existing poll tick (DASH-05)
- [ ] Self-contained output — stdlib only, no new deps, inline CSS/JS, charts as SVG/canvas (DASH-06)

### Out of Scope

- Data export (CSV/JSON) this milestone — revisit as HIST-F1 if in-tray views prove insufficient
- 7-day / weekly limit display — the CLI reports it as null for this account; revisit if it populates
- Cost/dollar tracking in the tray — usage %, not billing, is the goal
- In-process GTK charting window — v1.2's dashboard is a self-contained HTML page opened in the browser, not a Gtk-drawn chart surface (the tray stays glanceable text/unicode)
- Wayland support — existing app is X11-only; unchanged this milestone
- Bundling/replacing the `claude-monitor` CLI — we consume it, not vendor it

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Consume `claude-monitor --output json` for usage data | Purpose-built, already installed, computes window+limit+burn; avoids reinventing | — Pending |
| Query the CLI's `custom` dynamic limits (P90), not static `max5` | `max5`'s fixed 88k limit mismatched the real ~926k ceiling and inflated % ~10x ("148%" vs real ~15%); `custom` matches the CLI's own TUI. Override via `CLAUDE_TRAY_PLAN` | Corrected in Phase 1 |
| Background-thread polling on an interval | CLI is slow (~seconds); must not block Gtk main loop | — Pending |
| Show tokens+%, reset time, burn rate, high-usage badge | The at-a-glance signals the user wants | Shipped in v1.0 |
| Degrade to "usage unavailable" only after N consecutive poll misses (not the first) | Absorbs transient CLI hiccups (WR-03) while still surfacing sustained failure (POLL-02) | v1.1 baseline (fixed in v1.0 UAT) |
| Persist usage history as append-only JSONL under `~/.claude/`, pruned by retention window | Simplest durable store for a lightweight helper; no DB dependency; reuses the existing poll sample | Shipped in Phase 2 |
| `parse_history` keeps only JSON objects with a numeric `t`; prune reads `errors="replace"` | Corruption tolerance must be total — a valid-JSON-but-wrong-shape or non-UTF8 line must never raise and kill the poll thread (code-review WR-01) | Shipped in Phase 2 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-12 — v1.1 (Usage History & Trends) shipped: HIST-01/02/03 + TREND-01/02/03 validated. Milestone v1.2 (Usage Web Dashboard) started; requirements DASH-01..06 active. Next: roadmap v1.2.*
