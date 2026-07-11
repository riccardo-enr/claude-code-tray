# Requirements — claude-code-tray usage monitoring

Milestone goal: surface Claude Code token usage and quota-reset info in the
existing tray, sourced from the `claude-monitor` CLI.

## v1 Requirements

### Data (POLL)

- [x] **POLL-01**: The helper polls `claude-monitor --plan max5 --output json --once` on a background thread at a fixed interval, so the Gtk UI never blocks on the multi-second CLI call.
- [x] **POLL-02**: A failed, timed-out, or unparseable `claude-monitor` call degrades gracefully — the usage rows show a "usage unavailable" state and the tray keeps working.

### Usage display (USAGE)

- [x] **USAGE-01**: The tray menu shows current tokens used and percentage of the Max 5x five-hour limit (e.g. "72k / 88k (82%)").
- [x] **USAGE-02**: The tray menu shows time remaining until the five-hour window resets (derived from `resets_at_epoch`).
- [x] **USAGE-03**: The tray menu shows the current burn rate (tokens per hour).

### Alerting (ALERT)

- [x] **ALERT-01**: The top-bar icon shows a badge/label when usage crosses a high threshold (default >80% of limit).

## Future Requirements (deferred)

- **USAGE-F1**: Seven-day / weekly limit display — deferred until the CLI reports non-null seven_day data for this account.
- **ALERT-F1**: Configurable threshold via env var — add if the fixed 80% proves wrong.

## Out of Scope

- Cost/dollar tracking in the tray — usage %, not billing, is the goal.
- Reimplementing rolling-window / plan-limit math — consumed from the CLI, not rebuilt.
- Wayland support — app remains X11-only this milestone.
- Vendoring or replacing the `claude-monitor` CLI — consumed as an external dependency.

## Traceability

| Requirement | Phase |
|-------------|-------|
| POLL-01 | Phase 1 |
| POLL-02 | Phase 1 |
| USAGE-01 | Phase 1 |
| USAGE-02 | Phase 1 |
| USAGE-03 | Phase 1 |
| ALERT-01 | Phase 1 |
