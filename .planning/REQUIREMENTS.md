# Requirements — claude-code-tray v1.2 (Usage Web Dashboard)

Milestone goal: turn the persisted `~/.claude/usage-history.jsonl` history (written
in v1.1) into a browsable HTML dashboard opened from the tray — real charts over
longer ranges than the cramped tray menu can hold. Read-only over the existing
JSONL; no new polling; stdlib + no new dependencies; complements the tray, does
not replace it.

## v1.2 Requirements

### Dashboard (DASH)

- [x] **DASH-01**: A tray menu item opens the usage dashboard in the user's default browser.
- [x] **DASH-02**: The dashboard renders a usage-% trend chart over a longer, selectable time range than the tray. *Delivered as rolling `24h / 7d / All` rather than calendar day/week — a window that resets at local midnight (or on Monday) hides the most recent activity right after it rolls, and rolling also mirrors how Claude's own quota windows work.*
- [x] **DASH-03**: The dashboard shows a peak-usage heatmap — hour-of-day (0-23) by day-of-week — derived from history. *Cell metric is mean **usage %**, not raw burn: burn is a per-minute throughput estimate whose tens-of-millions scale is unreadable, and the rest of the dashboard is denominated in percent.*
- [~] **DASH-04**: ~~The dashboard renders a burn-rate trend (daily/weekly aggregates) over the full retained history.~~ **DESCOPED during UAT** (commit `ae0691f`). Built as specified, then removed on user review: it plotted near-flat ~30M tok/hr raw-throughput numbers and duplicated the burn data the heatmap already showed more usefully. The dashboard is deliberately usage-%-denominated. Not a failure — a scope decision made against the running artifact.
- [x] **DASH-05**: The dashboard reads only the existing `~/.claude/usage-history.jsonl` (single source, read-only, no new polling) and refreshes on the existing background poll tick.
- [x] **DASH-06**: The dashboard output is self-contained — stdlib only, no new dependencies, inline CSS/JS, charts drawn as SVG — consistent with the project's X11-only, dependency-light constraints. *Asserted, not just intended: `--selfcheck` fails the build on any `<link`, `src=`, or `https://` in the rendered page.*
- [x] **DASH-07**: Dark-mode toggle — defaults to `prefers-color-scheme`, persists the choice, and inverts the heatmap ramp so low-usage cells do not glow against a dark page.
- [x] **DASH-08**: Data-gap honesty — the trend line **breaks** across sampling gaps rather than interpolating a straight line across an outage (a 13.7h gap was rendering as a smooth "decline" that never happened).

### Quota visibility (QUOTA) — added during v1.2, beyond original scope

Claude Code enforces **two** rolling caps (5-hour and 7-day). Only the 5-hour one was
ever parsed; the weekly was invisible everywhere. Closes the long-deferred SEED-003.

- [x] **QUOTA-01**: The weekly (7-day) cap is parsed from `limits.seven_day`, shown in the tray rows (`week: N% used` + days-aware reset countdown) and on the dashboard. The icon badge now warns when **either** cap is hot — a 95%-weekly / 10%-five-hour state previously produced no warning at all. *(Closes deferred item SEED-003.)*
- [x] **QUOTA-02**: Reset epochs (`reset`, `reset7`) are persisted to history, so the dashboard shows live countdowns and **marks window resets on the trend** — the sawtooth drops mean "the window rolled", not "usage fell", which the chart previously implied.
- [x] **QUOTA-03**: Projected usage at reset, for both caps, drawn on the chart and in the status card ("on track — projected 57% at reset"; "98% by Fri"). Derived **from percentages only**. The CLI's own `forecast`/`status` are deliberately **not** used: they are token-based and report `"limit hit"` under `--api`, where token counts come back `null` — wiring them in would have claimed exhaustion at 20% usage.

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

| Requirement | Phase | Status |
|-------------|-------|--------|
| DASH-01 | Phase 4 | Delivered |
| DASH-02 | Phase 4 | Delivered (rolling 24h/7d/All) |
| DASH-03 | Phase 4 | Delivered (mean usage %, not burn) |
| DASH-04 | Phase 4 | **Descoped during UAT** (`ae0691f`) |
| DASH-05 | Phase 4 | Delivered |
| DASH-06 | Phase 4 | Delivered (assertion-enforced) |
| DASH-07 | Phase 4 | Delivered |
| DASH-08 | Phase 4 | Delivered |
| QUOTA-01 | Phase 4 | Delivered (closes SEED-003) |
| QUOTA-02 | Phase 4 | Delivered |
| QUOTA-03 | Phase 4 | Delivered |
</content>
