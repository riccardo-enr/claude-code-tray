---
id: SEED-004
status: implemented
implemented_in: v1.3 (Phase 05 — session waiting/done desktop notifications on the shared path)
planted: 2026-07-13
planted_during: v1.2 / Phase 04 usage-web-dashboard
trigger_when: next milestone (v1.3)
scope: large
---

# SEED-004: Tray pings me when a Claude Code session finishes, so I get notified there's a new update

## Why This Matters

It enables true multi-tasking. Today you have to keep the top bar in your peripheral
vision to know when a session is done — which means you never really leave the loop.
A desktop notification lets you context-switch away from Claude Code entirely and get
pulled back only when there is actually something to review.

## When to Surface

**Trigger:** next milestone (v1.3)

Pick this up right after the usage web dashboard (v1.2) ships. It is the natural next
tray capability and does not depend on anything the dashboard leaves unfinished.

## Scope Estimate

**Large** — a full milestone. Not just "fire a notification on done": the intent is a
general notification subsystem the whole tray routes through — session completion,
waiting-for-input, and quota events (see [[SEED-002]] predictive quota alerts) all
emitting through one path, with config for what fires, do-not-disturb, sound, and
click-to-focus reusing the existing tmux/Ghostty focus action.

## Breadcrumbs

- `claude-monitor.py` — tray indicator; already tracks per-session status (running / waiting / done) via the hook socket. The done transition is the natural emit point.
- `claude-send.py` — hook client that pushes session events over the unix socket.
- Existing click-to-focus (tmux pane + Ghostty window) is the obvious notification default action.
- SEED-002 (predictive quota alerts) is a second producer for the same subsystem — plan them together.

## Notes

Enriched 2026-07-13. Scope deliberately called Large because the value is the shared
notification path, not the single session-done ping. If the milestone needs a quick win
first, the session-done ping alone is a few hours of work on top of the existing status
transition.
