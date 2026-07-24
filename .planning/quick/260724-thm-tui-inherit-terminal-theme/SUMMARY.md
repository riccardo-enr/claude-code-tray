---
slug: tui-inherit-terminal-theme
completed: 2026-07-24
status: complete
---

# Summary: claude-tui inherits the terminal theme

Set `self.theme = "ansi-dark"` in `ClaudeTui.on_mount`. The TUI now renders in the
host terminal's ANSI palette (Ghostty/Catppuccin Mocha for this user) rather than
textual's fixed `textual-dark`, and follows any later terminal-theme change.

## Decision

- Approach chosen via AskUserQuestion: **inherit terminal (`ansi-dark`)** over the
  exact `catppuccin-mocha` built-in theme. Intent was inheritance, not a hardcoded
  flavor. Accepted tradeoff: 16-color palette, so `#body.stale`'s opacity dim has no
  RGB to blend and reads flatter -- acceptable for a degraded-mode signal.

## Files

- `claude-tui.py` -- one line in `on_mount` + explanatory comment.

## Verification

- Headless `App.run_test()` (stubbed snapshot): `app.theme == "ansi-dark"`, panels mount. Pass.
- `just selfcheck` exit 0 -- textual boundary intact (change confined to claude-tui.py).
- `just lint` clean.

Not committed to ROADMAP.md -- quick task tracked in STATE.md.
