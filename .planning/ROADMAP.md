# Roadmap: claude-code-tray

## Overview

The tray shows per-session Claude Code status and (v1.0) at-a-glance token-usage
and quota-reset info sourced from the installed `claude-monitor` CLI. This
roadmap spans two milestones on the same single-file helper (`claude-monitor.py`):

- **v1.0 — Usage & Quota Monitoring** (Phase 1, complete): background-polled
  usage rows + high-usage icon badge in the existing menu.

- **v1.1 — Usage History & Trends** (Phases 2-3): persist each poll sample to a
  durable, bounded JSONL store, then surface trends (sparkline, daily/weekly
  burn, peak-usage hours) inside the same tray menu.

v1.1 reuses the existing background poll — no new polling and no new
dependencies (stdlib + PyGObject only, X11-only). It splits into two natural,
independently-verifiable boundaries: a persistence foundation, then the
read-side trend views that depend on it.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Usage & Quota Monitoring in the Tray** - Background-polled usage rows + high-usage icon badge in the existing menu (v1.0, completed 2026-07-11)
- [x] **Phase 2: Usage History Persistence** - Append each successful poll to a bounded, corruption-tolerant JSONL history store under `~/.claude/` (v1.1) (completed 2026-07-12)
- [ ] **Phase 3: Usage Trends in the Tray** - Sparkline, daily/weekly burn, and peak-usage hours rendered in the existing tray menu from history (v1.1)

## Phase Details

### Phase 1: Usage & Quota Monitoring in the Tray

**Goal**: From the top bar, the user sees current Claude Code quota usage, when the rolling 5-hour window resets, and burn rate — with a high-usage warning on the icon — without opening a terminal monitor.
**Mode:** mvp
**Depends on**: Nothing (extends the existing `claude-monitor.py` tray helper)
**Requirements**: POLL-01, POLL-02, USAGE-01, USAGE-02, USAGE-03, ALERT-01
**Success Criteria** (what must be TRUE):

  1. The tray menu shows a usage row like "72k / 88k (82%)" — current tokens used and percentage of the five-hour limit. (USAGE-01)
  2. The tray menu shows a reset countdown like "resets in 1h 47m", derived from `resets_at_epoch`. (USAGE-02)
  3. The tray menu shows the current burn rate, e.g. "burn: 12.4k tok/hr". (USAGE-03)
  4. The top-bar icon shows a badge/label when usage crosses the high threshold (default >80%) and clears when it drops back below. (ALERT-01)
  5. Usage refreshes on a background interval and the menu never freezes during the multi-second CLI call; a failed, timed-out, or unparseable call shows a "usage unavailable" state while session status and click-to-focus keep working. (POLL-01, POLL-02)

**Plans**: 1/1 plans complete

- [x] 01-01-PLAN.md — Extend claude-monitor.py: background-polled usage rows (tokens/percent, reset countdown, burn rate), high-usage icon badge, graceful "usage unavailable" degradation

**UI hint**: yes

### Phase 2: Usage History Persistence

**Goal**: Every successful usage poll is durably recorded to a bounded, corruption-tolerant history store under `~/.claude/`, reusing the existing background poll and never destabilizing the tray.
**Depends on**: Phase 1 (reuses the background poll thread and the parsed usage sample)
**Requirements**: HIST-01, HIST-02, HIST-03
**Success Criteria** (what must be TRUE):

  1. After the tray runs through several poll cycles, `~/.claude/usage-history.jsonl` contains one JSON line per successful poll (timestamp + used_percentage + tokens_used + token_limit + burn rate); failed or degraded polls add no line. (HIST-01)
  2. Samples older than the retention window (default 30 days, env-configurable via `CLAUDE_TRAY_HISTORY_DAYS`) are pruned on startup and periodically, so the file stays bounded instead of growing without limit. (HIST-02)
  3. A missing, unwritable, or partially-corrupt history file never crashes or freezes the tray — writes happen off the Gtk main loop and the reader skips bad lines; usage rows and session status keep working in every failure mode. (HIST-03)

**Plans**: 1/1 plans complete

- [ ] 02-PLAN.md

- [x] 02-01-PLAN.md — Extend claude-monitor.py: append each successful poll to ~/.claude/usage-history.jsonl, prune past the retention window atomically at startup + periodically, with defensive OSError-swallowing I/O and a corruption-tolerant reader

### Phase 3: Usage Trends in the Tray

**Goal**: The user sees usage history turned into trends inside the existing tray menu — a sparkline, daily and weekly burn, and peak-usage hours — with no separate window or charting GUI.
**Depends on**: Phase 2 (reads the persisted JSONL history)
**Requirements**: TREND-01, TREND-02, TREND-03
**Success Criteria** (what must be TRUE):

  1. The tray menu shows a sparkline of usage % over a recent window (default last 24h), rendered from history using unicode block characters. (TREND-01)
  2. The tray menu shows aggregate burn for today and for the current week, derived from history. (TREND-02)
  3. The tray menu surfaces the peak-usage hour(s) — the hour-of-day with the highest mean usage/burn over the retained history. (TREND-03)

**Plans**: TBD

**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 (done) -> 2 -> 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Usage & Quota Monitoring in the Tray | 1/1 | Complete | 2026-07-11 |
| 2. Usage History Persistence | 1/1 | Complete   | 2026-07-12 |
| 3. Usage Trends in the Tray | 0/0 | Not started | - |
