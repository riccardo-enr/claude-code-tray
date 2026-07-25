---
id: SEED-008
status: dormant
planted: 2026-07-25
planted_during: unknown
trigger_when: when relevant
scope: unknown
---

# SEED-008: tmux/powerline statusline segment showing Claude Code usage (current usage against plan limit) on the left side of the prompt

## Why This Matters

_To be filled in. Run `/gsd-capture --seed --enrich SEED-008` to add context._

## When to Surface

**Trigger:** when relevant

This seed will surface during `/gsd-new-milestone` when the milestone scope matches.

## Scope Estimate

**Unknown** — run `/gsd-capture --seed --enrich SEED-008` to estimate effort.

## Breadcrumbs

- `claude_monitor/core.py` — pure-stdlib display computations (usage, countdown,
  history) already reused by `claude-monitor.py` (tray) and `dashboard.py`
  (HTML); a statusline renderer would be a third consumer of `core`, same shape
  as [[SEED-007]] (TUI dashboard).
- `claude-send.py` — precedent for a second, non-daemon root script that talks
  to the tray via IPC (tmux pane focus), similar shape to what a statusline
  script polling usage would need.
- `claude-monitor.py` — daemon; unix socket (`SOCK`) is currently receive-only,
  same open question as SEED-007 if the statusline needs live session data
  rather than just usage/quota numbers from `core.fetch_usage()` /
  `~/.claude/usage-history.jsonl`.

## Notes

_Captured via one-shot seed capture. Enrich with trigger, why, and scope at your convenience._
