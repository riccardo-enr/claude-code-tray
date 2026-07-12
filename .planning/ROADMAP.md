# Roadmap: claude-code-tray

## Overview

The tray shows per-session Claude Code status and (v1.0) at-a-glance token-usage
and quota-reset info sourced from the installed `claude-monitor` CLI. This
roadmap spans three milestones on the same single-file helper (`claude-monitor.py`):

- **v1.0 — Usage & Quota Monitoring** (Phase 1, complete): background-polled
  usage rows + high-usage icon badge in the existing menu.

- **v1.1 — Usage History & Trends** (Phases 2-3): persist each poll sample to a
  durable, bounded JSONL store, then surface trends (sparkline, daily/weekly
  burn, peak-usage hours) inside the same tray menu.

- **v1.2 — Usage Web Dashboard** (Phase 4): turn that same JSONL history into a
  browsable, self-contained HTML dashboard opened from a tray menu item — real
  charts (usage-% trend over a selectable range, burn-rate trend, peak-usage
  heatmap) that complement the cramped tray menu, not replace it.

v1.1 and v1.2 reuse the existing background poll — no new polling and no new
dependencies (stdlib + PyGObject only, X11-only). v1.1 split into two natural,
independently-verifiable boundaries: a persistence foundation, then the
read-side trend views that depend on it. v1.2 is a single read-side consumer of
the same store, delivered as one coherent capability.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Usage & Quota Monitoring in the Tray** - Background-polled usage rows + high-usage icon badge in the existing menu (v1.0, completed 2026-07-11)
- [x] **Phase 2: Usage History Persistence** - Append each successful poll to a bounded, corruption-tolerant JSONL history store under `~/.claude/` (v1.1) (completed 2026-07-12)
- [x] **Phase 3: Usage Trends in the Tray** - Sparkline, daily/weekly burn, and peak-usage hours rendered in the existing tray menu from history (v1.1) (completed 2026-07-12)
- [ ] **Phase 4: Usage Web Dashboard** - A tray menu item opens a self-contained HTML dashboard rendering the JSONL history as real charts: selectable-range usage-% trend, burn-rate trend, and a peak-usage heatmap (v1.2)

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

**Plans**: 1/1 plans complete

- [x] 03-01-PLAN.md — Extend claude-monitor.py: pure trend functions (24h sparkline, today/week mean burn, peak hour) + demo asserts, compute+cache in poll_loop off the Gtk main thread, and insensitive trend rows with a collecting-history empty state

**UI hint**: yes

### Phase 4: Usage Web Dashboard

**Goal**: From a tray menu item, the user opens a browsable, self-contained HTML dashboard that renders the persisted `~/.claude/usage-history.jsonl` as real charts — a selectable-range usage-% trend, a burn-rate trend over the full retained history, and an hour-of-day x day-of-week peak-usage heatmap — complementing (not replacing) the cramped tray menu, built read-only with stdlib only.
**Depends on**: Phase 2 (reads the persisted `~/.claude/usage-history.jsonl` via the existing `parse_history`/`history_keep` readers); reuses the existing background poll tick for refresh — no new polling, no second data source. Sibling of Phase 3 (both are read-side consumers of the same store).
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, DASH-06
**Success Criteria** (what must be TRUE):

  1. A new tray menu item (e.g. "Open Usage Dashboard") opens the dashboard in the user's default browser. (DASH-01)
  2. The dashboard renders a usage-% trend chart with a selectable time range (e.g. day / week / full retained history) — a longer range than the tray sparkline holds. (DASH-02)
  3. The dashboard shows a peak-usage heatmap laid out as hour-of-day (0-23) by day-of-week, derived from the history. (DASH-03)
  4. The dashboard renders a burn-rate trend (daily/weekly aggregates) over the full retained history. (DASH-04)
  5. The dashboard reads only `~/.claude/usage-history.jsonl` (no new polling, no second source) and its data refreshes on the existing background poll tick; the page is fully self-contained — stdlib-generated, no new dependencies, inline CSS/JS, charts drawn as SVG/canvas. (DASH-05, DASH-06)

**Plans**: 1 plan

- [ ] 04-01-PLAN.md — Extend claude-monitor.py: pure dashboard generators (render_dashboard, heatmap_buckets, burn_series, script-safe _embed_json) + demo asserts, off-thread generate-and-write in poll_loop to a cache-path static .html, and a sensitive "Open Usage Dashboard" tray item opening it via file://

**UI hint**: yes

> Open planning decision (do NOT resolve in the roadmap; settle at phase planning per SEED-001): delivery shape — a static self-contained `.html` regenerated on the poll tick and opened via `file://`, vs. a tiny stdlib `http.server` bound to loopback serving live data. This choice determines how generation and serving interleave, which is why v1.2 stays a single phase rather than a generation/serving split.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 (done) -> 2 (done) -> 3 (done) -> 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Usage & Quota Monitoring in the Tray | 1/1 | Complete | 2026-07-11 |
| 2. Usage History Persistence | 1/1 | Complete    | 2026-07-12 |
| 3. Usage Trends in the Tray | 1/1 | Complete   | 2026-07-12 |
| 4. Usage Web Dashboard | 0/? | Not started | - |
</content>
</invoke>
