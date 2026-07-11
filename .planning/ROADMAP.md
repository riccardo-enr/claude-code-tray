# Roadmap: claude-code-tray usage monitoring

## Overview

The tray already shows per-session Claude Code status. This milestone adds one
coherent capability on top of it: at-a-glance token-usage and quota-reset info,
sourced from the already-installed `claude-monitor` CLI. A background poll feeds
usage rows (tokens/percent, reset countdown, burn rate) into the existing
AppIndicator menu and badges the top-bar icon when usage runs high. It is a
single vertical slice on a small app, so it ships as one phase.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [ ] **Phase 1: Usage & Quota Monitoring in the Tray** - Background-polled usage rows + high-usage icon badge in the existing menu

## Phase Details

### Phase 1: Usage & Quota Monitoring in the Tray
**Goal**: From the top bar, the user sees current Claude Code quota usage, when the rolling 5-hour window resets, and burn rate — with a high-usage warning on the icon — without opening a terminal monitor.
**Mode:** mvp
**Depends on**: Nothing (extends the existing `claude-monitor.py` tray helper)
**Requirements**: POLL-01, POLL-02, USAGE-01, USAGE-02, USAGE-03, ALERT-01
**Success Criteria** (what must be TRUE):
  1. The tray menu shows a usage row like "72k / 88k (82%)" — current tokens used and percentage of the Max 5x five-hour limit. (USAGE-01)
  2. The tray menu shows a reset countdown like "resets in 1h 47m", derived from `resets_at_epoch`. (USAGE-02)
  3. The tray menu shows the current burn rate, e.g. "burn: 12.4k tok/hr". (USAGE-03)
  4. The top-bar icon shows a badge/label when usage crosses the high threshold (default >80%) and clears when it drops back below. (ALERT-01)
  5. Usage refreshes on a background interval and the menu never freezes during the multi-second CLI call; a failed, timed-out, or unparseable call shows a "usage unavailable" state while session status and click-to-focus keep working. (POLL-01, POLL-02)
**Plans**: 1 plan
- [ ] 01-01-PLAN.md — Extend claude-monitor.py: background-polled usage rows (tokens/percent, reset countdown, burn rate), high-usage icon badge, graceful "usage unavailable" degradation
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Usage & Quota Monitoring in the Tray | 0/1 | Not started | - |
