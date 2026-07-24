# Requirements — claude-code-tray v1.6 (TUI Polish)

**Status:** 🚧 ROADMAPPED — Phase 10

Milestone goal: turn the v1.5 plain-text `claude-tui.py` into a btop-inspired
terminal dashboard — colored, gauged, and bordered — without changing what data it
shows or how it is fed. The v1.5 TUI works but renders every value as flat,
uncolored text; this milestone is purely presentation.

Constraints held (carried from v1.5): no new data source, no new polling, no IPC
change, no new runtime dependency. The TUI still reads the daemon's read-only
snapshot socket verb and nothing else, and `claude_monitor.core` remains the single
source of truth for every formatted value (D-05 tray/TUI parity). `textual` stays
the only third-party dependency, scoped to `claude-tui.py` via its PEP 723 block.

**Architecture rule (load-bearing):** anything assertable lives in
`claude_monitor.core`, where `--selfcheck` on stock `/usr/bin/python3` can prove it
— that interpreter is PEP 668 and must never gain `textual`/`rich`. Color/gauge/
graph rendering that genuinely needs `rich` or `textual` stays in `claude-tui.py`;
threshold decisions, gauge fill math, and graph data expressible as plain
values/strings belong in `core`. This is the main gray area for plan-phase.

## v1.6 Requirements

### TUI (terminal rendering polish)

- [x] **TUI-06**: Usage %, burn rate, and reset countdown are colored by proximity to the cap — green / yellow / red thresholds — for both the 5-hour and 7-day caps.
- [x] **TUI-07**: The 5h and 7d usage each render as a gradient progress-bar gauge (btop-style meter), replacing the plain "N% of limit" text rows.
- [ ] **TUI-08**: The trends panel renders a richer usage graph than the reused tray sparkline — taller and/or colored/braille-style — still sourcing its data from `core`'s existing trend functions (no new trend math).
- [ ] **TUI-09**: The live sessions table is styled — status-colored rows and improved spacing/borders/striping — over the current plain DataTable.
- [ ] **TUI-10**: Each panel (usage, trends, sessions) is wrapped in a titled, rounded bordered box, giving the btop-style paneled layout.

## Design reference

btop (`https://github.com/aristocratos/btop`) is the visual north star: rounded
bordered panels with titles, gradient-colored meters (green→yellow→red), and dense
braille/block graphs. Take inspiration from its look, not its architecture.

## Deferred (to future milestones)

- Click-to-focus a pane from the TUI (reusing the snapshot's `pane`/`tmux` fields) — the tray remains the click-to-focus surface.
- Standalone (no-daemon) mode reading `usage-history.jsonl` directly.

## Out of Scope

- **tmux `prefix + t` launcher / any launch tooling in the repo** — the user's binding is personal config; v1.6 is TUI visuals only.
- Any TUI-side write/mutation of daemon state (mute toggles, config changes) — read-only, unchanged from v1.5.
- New data, new polling, a second data source, or a new IPC/socket verb — presentation only, same snapshot.
- New runtime dependency beyond `textual` (already the sole exception).
- `curses` as the rendering layer — `textual` stays.
- Wayland support — the app remains X11-only.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| TUI-06 | Phase 10 | Complete |
| TUI-07 | Phase 10 | Complete |
| TUI-08 | Phase 10 | Pending |
| TUI-09 | Phase 10 | Pending |
| TUI-10 | Phase 10 | Pending |
