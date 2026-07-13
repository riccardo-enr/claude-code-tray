---
id: SEED-004
status: dormant
planted: 2026-07-13
planted_during: v1.2 / Phase 04 usage-web-dashboard
trigger_when: when relevant
scope: unknown
---

# SEED-004: Tray pings me when a Claude Code session finishes, so I get notified there's a new update

## Why This Matters

_To be filled in. Run `/gsd-capture --seed --enrich SEED-004` to add context._

## When to Surface

**Trigger:** when relevant

This seed will surface during `/gsd-new-milestone` when the milestone scope matches.

## Scope Estimate

**Unknown** — run `/gsd-capture --seed --enrich SEED-004` to estimate effort.

## Breadcrumbs

- `claude-monitor.py` — tray indicator; already tracks per-session status (running / waiting / done) via the hook socket. The done transition is the natural notification hook point.
- `claude-send.py` — hook client that pushes session events over the unix socket.

## Notes

_Captured via one-shot seed capture. Enrich with trigger, why, and scope at your convenience._
