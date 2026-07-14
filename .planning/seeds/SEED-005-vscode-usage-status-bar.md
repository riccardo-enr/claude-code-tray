---
id: SEED-005
status: dormant
planted: 2026-07-14
planted_during: v1.3 / Phase 05 notification-path
trigger_when: next milestone after v1.3 (v1.4)
scope: large
---

# SEED-005: See Claude Code usage inside VS Code, not just the GNOME top bar

## Why This Matters

The tray icon gets used constantly, but it lives in the top bar — a glance away from
where the work actually happens. When VS Code is fullscreen (or on a machine without
a GNOME tray at all), the quota picture disappears. A status bar item inside the editor
puts usage % and reset countdown in the same visual field as the code.

## When to Surface

**Trigger:** next milestone after v1.3 ships (the notification subsystem is finished).

Not before: v1.3 is mid-flight (Phase 06 config still unplanned), and a second frontend
should not be started while the first one is still growing a new subsystem.

## Scope Estimate

**Large** — a full milestone, and a new *deployment target*, not another feature on
`claude-monitor.py`. It means a TypeScript VS Code extension: package, activation events,
status bar item, publish/install story. None of that exists in this repo today.

## The Load-Bearing Open Question: where do the numbers come from?

Three routes, unresolved — decide this before anything else:

1. **Read `~/.claude/usage-history.jsonl` directly.** Zero new IPC, no changes to
   `claude-monitor.py`. But VS Code only sees usage *while the tray is running and
   polling* — the extension has no data of its own on a machine without the tray.
2. **Extension shells out to the `claude-monitor` CLI itself.** Fully independent of the
   tray. Cost: reimplementing the projection / window / cap math in TypeScript, and a
   second poll of a slow CLI. Duplicates ~everything the last three milestones built.
3. **Tray exposes current usage over a socket or loopback endpoint.** Reuses all existing
   Python math, single poll. Cost: adds a listening surface — the exact thing SEED-001
   deliberately avoided when the dashboard was made a static `file://` page.

Route 1 is the laziest and probably right for a first cut; route 3 is where it ends up if
the extension ever needs to work standalone.

## Breadcrumbs

- `claude-monitor.py` — the poll tick, the projection math (`project()`), both caps, the JSONL writer. Everything a VS Code surface would want to show already exists here.
- `~/.claude/usage-history.jsonl` — the persisted store (HIST-01/02/03, v1.1). Already append-only and corruption-tolerant; a reader is cheap.
- The v1.2 dashboard is already a self-contained HTML page — it could be dropped into a VS Code webview panel nearly as-is, which is a much cheaper second surface than the status bar item.

## Notes

Asked 2026-07-14 during v1.3. Planted rather than scoped as a milestone because v1.3's
Phase 06 is still open. The webview-of-the-existing-dashboard variant is the cheap slice
if a full extension proves too much — it reuses the v1.2 generator with no new math.
