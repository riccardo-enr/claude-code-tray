# Requirements — claude-code-tray v1.5 (TUI Dashboard)

Milestone goal: surface usage/quota/trends and live sessions in a terminal UI, so
people who live in the terminal get the tray's data without a browser round-trip.
Closes SEED-007. A new `claude-tui.py` entry point becomes a third consumer of
`claude_monitor.core` alongside `claude-monitor.py` and `dashboard.py`.

Constraints: X11 host only (the tray it queries is X11-only), no new polling —
the TUI queries the existing daemon rather than shelling out to the usage CLI
itself. `textual` is the one exception to the project's stdlib+PyGObject-only
rule, scoped to this entry point.

## v1.5 Requirements

### TUI (terminal rendering)

- [ ] **TUI-01**: `claude-tui.py` shows current usage (%, tokens, reset countdown, burn rate) for both the 5-hour and 7-day caps.
- [ ] **TUI-02**: Shows trends — sparkline, daily/weekly burn, peak-usage hour — reusing `claude_monitor.core`'s existing trend functions, not reimplementing them.
- [ ] **TUI-03**: Shows a live sessions panel — project dir, status, time-in-state — sorted waiting -> running -> done, matching the v1.4 dashboard panel's semantics.
- [ ] **TUI-04**: Refreshes automatically on an interval; no manual re-run or keypress needed to see new data.
- [ ] **TUI-05**: Degrades cleanly when the daemon isn't running or the socket is unreachable — a clear message, never a crash or an unhandled traceback to the terminal.

### Socket query verb (SOCK)

- [x] **SOCK-01**: The daemon's existing unix socket gains a read-only query verb that returns a JSON snapshot of `self.sessions` plus the last polled usage/history state.
- [ ] **SOCK-02**: The query path shares the socket without disrupting the existing fire-and-forget hook-event path — a stalled or malformed query connection cannot block or corrupt a session-event write.
- [x] **SOCK-03**: The query responder reads `self.sessions` safely against the Gtk-main-thread mutator — no torn/partial reads of an in-flight session update.

## Future Requirements (deferred)

- Click-to-focus a pane from the TUI (reusing `pane`/`tmux` fields) — deferred; the tray remains the click-to-focus surface for v1.
- Standalone (no-daemon) mode reading `usage-history.jsonl` directly — deferred; shared-socket was chosen over it to get live sessions in v1 scope, but a fallback mode could still be added later.

## Out of Scope

- Any TUI-side write/mutation of daemon state (mute toggles, config changes) — read-only for v1.
- `curses` as the rendering layer — decided against at scoping in favor of `textual`.
- Wayland support — the tray itself remains X11-only; the TUI's data source is that tray.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| TUI-01 | Phase 9 | Planned |
| TUI-02 | Phase 9 | Planned |
| TUI-03 | Phase 9 | Planned |
| TUI-04 | Phase 9 | Planned |
| TUI-05 | Phase 9 | Planned |
| SOCK-01 | Phase 8 | Planned |
| SOCK-02 | Phase 8 | Planned |
| SOCK-03 | Phase 8 | Planned |
