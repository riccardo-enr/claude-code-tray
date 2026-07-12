# Requirements — claude-code-tray v1.2 (Usage Web Dashboard)

Milestone goal: turn the persisted `~/.claude/usage-history.jsonl` history (written
in v1.1) into a browsable HTML dashboard opened from the tray — real charts over
longer ranges than the cramped tray menu can hold. Read-only over the existing
JSONL; no new polling; stdlib + no new dependencies; complements the tray, does
not replace it.

## v1.2 Requirements

### Dashboard (DASH)

- [ ] **DASH-01**: A tray menu item opens the usage dashboard in the user's default browser.
- [ ] **DASH-02**: The dashboard renders a usage-% trend chart over a longer, selectable time range than the tray (e.g. day / week / full retained history).
- [ ] **DASH-03**: The dashboard shows a peak-usage heatmap — hour-of-day (0-23) by day-of-week — derived from history.
- [ ] **DASH-04**: The dashboard renders a burn-rate trend (daily/weekly aggregates) over the full retained history.
- [ ] **DASH-05**: The dashboard reads only the existing `~/.claude/usage-history.jsonl` (single source, read-only, no new polling) and refreshes on the existing background poll tick.
- [ ] **DASH-06**: The dashboard output is self-contained — stdlib only, no new dependencies, inline CSS/JS, charts drawn as SVG/canvas — consistent with the project's X11-only, dependency-light constraints.

## Future Requirements (deferred)

- **DASH-F1**: Live auto-refresh in the browser (e.g. WebSocket / polling) if a static regenerated page proves insufficient.
- **DASH-F2**: Raw data export (CSV/JSON) surfaced from the dashboard (supersedes v1.1's HIST-F1 if pursued here).
- **DASH-F3**: Configurable ranges / aggregation windows beyond the built-in day/week/all presets.

## Out of Scope

- Cost/dollar tracking — usage %, not billing, remains the goal.
- A hosted/remote dashboard — this is a local, single-user page over the local JSONL.
- Auth / multi-user / network exposure — local-only, bound to loopback if a server is used at all.
- Replacing the in-tray trends — the dashboard complements the tray, which keeps its glanceable sparkline/burn/peak rows.
- New polling or a second data source — reuses the Phase-2 JSONL exclusively.
- New runtime dependencies or a JS charting library — stdlib + inline SVG/canvas only.
- Wayland-specific work — app remains X11-only; opening a browser is DE-agnostic.

## Open Questions (settle at phase planning)

- **Delivery shape:** static self-contained `.html` regenerated on the poll tick (opened via `file://`) vs. a tiny stdlib `http.server` bound to loopback serving live data. Seed SEED-001 flags this as the key planning decision.

## Traceability

| Requirement | Phase |
|-------------|-------|
| DASH-01 | TBD |
| DASH-02 | TBD |
| DASH-03 | TBD |
| DASH-04 | TBD |
| DASH-05 | TBD |
| DASH-06 | TBD |
