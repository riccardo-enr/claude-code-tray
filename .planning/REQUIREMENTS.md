# Requirements — claude-code-tray v1.1 (Usage History & Trends)

Milestone goal: persist usage samples over time and surface trends in the tray —
a sparkline, daily/weekly burn, and peak-usage hours — building on v1.0's
point-in-time usage monitoring. Reuses the existing background poll; no new polling.

## v1.1 Requirements

### Persistence (HIST)

- [x] **HIST-01**: Each successful usage poll appends one sample (timestamp + used_percentage + tokens_used + token_limit + burn rate) as a single JSON line to a history store under `~/.claude/` (e.g. `usage-history.jsonl`). Failed/degraded polls are not recorded.
- [x] **HIST-02**: On startup and periodically, samples older than the retention window (default 30 days, env-configurable via `CLAUDE_TRAY_HISTORY_DAYS`) are pruned so the file stays bounded.
- [x] **HIST-03**: History I/O is defensive — a missing file, unwritable path, or corrupt/partial line never crashes or blocks the helper. Writes happen off the Gtk main loop; the reader tolerantly skips bad lines.

### Trends display (TREND)

- [x] **TREND-01**: The tray menu shows a sparkline of usage % over a recent window (default last 24h) rendered from history.
- [x] **TREND-02**: The tray menu shows aggregate burn for today and the current week, derived from history.
- [x] **TREND-03**: The tray menu surfaces peak-usage hour(s) — the hour-of-day with the highest mean usage/burn over the retained history.

## Future Requirements (deferred)

- **HIST-F1**: Raw data export (CSV/JSON dump) for external analysis — deferred; add if the in-tray views prove insufficient.
- **TREND-F1**: Configurable sparkline window / aggregation period beyond the default.

## Out of Scope

- Cost/dollar tracking — usage %, not billing, remains the goal.
- Data export (CSV/JSON) this milestone — see HIST-F1.
- Charting GUI / separate window — trends live inside the existing tray menu.
- 7-day / weekly *limit* display — still null from the CLI for this account (v1.0 deferral stands).
- Wayland support — app remains X11-only.
- Replacing/vendoring the `claude-monitor` CLI — consumed, not rebuilt.

## Traceability

| Requirement | Phase |
|-------------|-------|
| HIST-01 | Phase 2 |
| HIST-02 | Phase 2 |
| HIST-03 | Phase 2 |
| TREND-01 | Phase 3 |
| TREND-02 | Phase 3 |
| TREND-03 | Phase 3 |
