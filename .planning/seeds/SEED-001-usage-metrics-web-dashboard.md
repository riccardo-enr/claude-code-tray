---
id: SEED-001
status: dormant
planted: 2026-07-12
planted_during: v1.1 Phase 3 (Usage Trends in the Tray)
trigger_when: after v1.1 ships (Phase 3 verified); next milestone (v1.2)
scope: medium
---

# SEED-001: Web page rendering usage metrics from the JSONL history store

## Why This Matters

The tray menu is glanceable but cramped — a sparkline and a couple of burn
numbers is all it can hold. The same `~/.claude/usage-history.jsonl` written in
Phase 2 has far more in it (per-poll % / tokens / burn over the full retention
window). A browsable HTML dashboard turns that history into real charts —
daily/weekly trends, peak-hour heatmap, longer time ranges — without cramming
them into a GTK menu. Complements the tray rather than replacing it.

## When to Surface

**Trigger:** after v1.1 ships — surface during `/gsd-new-milestone` once Phase 3
is verified and v1.1 is complete. Candidate scope for v1.2.

## Scope Estimate

**Medium** — a phase or two. Read side only; no new polling. Reuses the Phase 2
JSONL as the single data source.

Likely lazy shape (stdlib + no new deps, matching the project's constraints):
- A stdlib-only static HTML generator that reads the JSONL and emits one
  self-contained `.html` (inline CSS/JS, charts as SVG or unicode), regenerated
  on the existing poll tick; open via a tray menu item. OR
- A tiny `http.server` serving the same, if live-refresh is wanted.
- Open question to settle at planning time: static-file-per-poll vs. local
  server; whether it replaces or sits alongside the tray trends.

## Breadcrumbs

- `claude-monitor.py` — single-file tray helper; Phase 2 added the JSONL writer.
- `~/.claude/usage-history.jsonl` — data source (timestamp, used_percentage,
  tokens_used, token_limit, burn rate per successful poll).
- ROADMAP.md Phase 2 (persistence) / Phase 3 (in-tray trends) — this seed is the
  web-surface counterpart to Phase 3.

## Notes

Captured via seed capture. Trigger/why/scope filled in at capture time.
