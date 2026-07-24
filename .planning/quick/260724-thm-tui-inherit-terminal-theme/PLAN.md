---
slug: tui-inherit-terminal-theme
created: 2026-07-24
type: quick
---

# Quick Task: claude-tui inherits the terminal theme

## Goal

Make `claude-tui.py` render in the host terminal's palette (user's Ghostty is
Catppuccin Mocha) instead of textual's fixed `textual-dark` theme.

## Approach

Textual's built-in `ansi-dark` theme renders through the terminal's own 16 ANSI
colors + default fg/bg, so the TUI inherits whatever the terminal is themed with
and follows any later change -- the literal "same theme as my terminal" the user
asked for. Chosen over the exact `catppuccin-mocha` theme (via AskUserQuestion)
because inheritance was the intent; tradeoff accepted is a 16-color palette, so
the `#body.stale` opacity dim reads flatter.

## Change

- `claude-tui.py` `on_mount`: `self.theme = "ansi-dark"` (one line + comment).
  No CSS change needed -- `$panel` and the rest resolve against the active theme.

## Verification

- Headless `App.run_test()` with a stubbed `core.query_snapshot`: `app.theme == "ansi-dark"`, panels mount.
- `just selfcheck` exit 0 (textual boundary holds -- change is confined to claude-tui.py).
- `just lint` clean.
