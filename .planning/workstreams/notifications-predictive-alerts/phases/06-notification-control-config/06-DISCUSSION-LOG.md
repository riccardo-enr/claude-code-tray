# Phase 6: Notification Control & Config - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-16
**Phase:** 6-Notification Control & Config
**Areas discussed:** Config file scope, Tray menu shape, Mute-all interaction, Badge threshold config, Config file name

---

## Config file scope (CFG-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Env stays default, config overrides | CLAUDE_TRAY_* env vars keep working as today's defaults; the new JSON config is a separate, additive layer read on top. | ✓ |
| Config subsumes env vars | Fold everything into the one config file; env vars become legacy/removed. | |
| Config is notification-only, no relation to env | New config file covers only CFG-01..05; existing env vars untouched and unrelated. | |

**User's choice:** Env stays default, config overrides (recommended option).
**Notes:** None.

---

## Tray menu shape (CFG-01, CFG-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Notifications submenu | One 'Notifications' submenu with 4 checkboxes + mute-all checkbox. | ✓ |
| Flat checkboxes in main menu | 5 Gtk.CheckMenuItem rows directly in the top-level menu. | |

**User's choice:** Notifications submenu (recommended option).
**Notes:** None.

---

## Mute-all interaction (CFG-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Independent state, mute wins at runtime | Per-event toggles keep their state while muted; gate ANDs mute with per-event flag. | ✓ |
| Mute disables (greys out) per-event toggles | While muted, the 4 event checkboxes become insensitive. | |

**User's choice:** Independent state, mute wins at runtime (recommended option).
**Notes:** None.

---

## Badge threshold config (CFG-05)

| Option | Description | Selected |
|--------|-------------|----------|
| Preset steps as radio items | Small submenu of fixed choices (70/80/90/95%) as Gtk.RadioMenuItem. | ✓ |
| Config-file-only, no tray UI for the number | Threshold only editable by hand-editing the JSON file. | |

**User's choice:** Preset steps as radio items (recommended option).
**Notes:** None.

---

## Config file name

| Option | Description | Selected |
|--------|-------------|----------|
| ~/.claude/tray-config.json | Matches the 'tray' prefix used by CLAUDE_TRAY_* env vars. | ✓ |
| ~/.claude/notifications-config.json | Named after the feature it configures. | |

**User's choice:** ~/.claude/tray-config.json (recommended option).
**Notes:** None.

---

## Claude's Discretion

- Exact preset values for the badge threshold submenu (70/80/90/95 suggested).
- Whether the badge-threshold submenu nests inside "Notifications" or sits as its own top-level submenu.
- JSON schema/key names inside `tray-config.json`.
- Where in-memory config state lives and how/when it's read.
- Corrupt-config fallback mechanics (mirror `parse_history`'s pattern).

## Deferred Ideas

- Migrating existing `CLAUDE_TRAY_*` env vars into the config file — rejected for this phase.
- Free-text/arbitrary numeric entry for the badge threshold — rejected in favor of preset radio steps.
