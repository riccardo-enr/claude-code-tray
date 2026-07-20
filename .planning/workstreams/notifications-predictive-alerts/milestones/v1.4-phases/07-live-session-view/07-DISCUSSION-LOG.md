# Phase 07 Discussion Log

**Date:** 2026-07-18 | Mode: discuss (standard)

Human-reference only. Decisions live in `07-CONTEXT.md`.

## Areas selected

All four presented gray areas were selected for discussion.

## Decisions (one question per area)

| Area | Options presented | Chosen |
|------|-------------------|--------|
| Duration freshness | JS live-tick (rec) / static text | **JS live-tick** -> D-01, D-02 |
| Panel layout | Table waiting-first (rec) / cards / table by-dir | **Table, waiting-first** -> D-03, D-04, D-05 |
| Which sessions shown | All tracked, done dimmed (rec) / only active | **All tracked, done dimmed** -> D-06 |
| Empty state | Keep panel + message (rec) / hide panel | **Keep panel + message** -> D-07 |

All four resolved to the recommended default.

## Grounding surfaced during discussion

- `self.sessions` (claude-monitor.py:60) stores `{dir,status,pane,tmux,cwd,acked}` --
  **no timestamp**, so SESSVIEW-02 requires adding an `entered` epoch in `handle()`
  on status change (D-01). This was SEED-005's flagged open question.
- `dashboard.py` is pure/no-GTK post-restructure; `Monitor` must snapshot sessions
  and pass them in (D-08 architecture note).
- Markup-safety (D-08) reuses the notifier's T-05-04 lesson: JSON payload +
  client-side `textContent`, never server-side HTML interpolation of `dir`.

## Deferred

- Click-to-focus a pane from the browser (needs IPC; browser can't focus tmux).
- Per-session token/usage detail (no data source).

## Scope creep

None -- discussion stayed within the SESSVIEW-01..05 boundary.
