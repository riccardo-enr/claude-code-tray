---
status: complete
phase: 04-usage-web-dashboard
source: [04-01-SUMMARY.md]
started: 2026-07-12
updated: 2026-07-13
---

## Current Test

[testing complete]

## Tests

### 1. Tray restart and "Open Usage Dashboard" menu item
expected: The tray menu shows an "Open Usage Dashboard" item (near "Quit monitor"), greyed until the first poll writes the file, then clickable.
result: pass
evidence: User restarted the tray and opened the dashboard from the menu repeatedly across the session. Backend condition corroborated automatically each restart (dashboard.html written at startup, which is what flips `dash_ready`).

### 2. Clicking opens the dashboard in the browser
expected: Clicking "Open Usage Dashboard" opens ~/.cache/claude-tray/dashboard.html in the default browser via a file:// URL.
result: pass
evidence: User viewed and screenshotted the rendered page multiple times.

### 3. Usage-% trend chart with working range buttons
expected: A usage-% line chart with working range switching; active button highlighted.
result: pass
evidence: Screenshot shows the chart with 24h / 7d / All (All active). Several defects were found here and FIXED during UAT — see Findings.

### 4. Peak-usage heatmap (ramp, gray cells, tooltips, legend)
expected: hour-of-day x day-of-week heatmap, single-hue ramp, distinct gray for empty cells, hover tooltips, legend.
result: pass
evidence: Screenshot shows the heatmap with ramp, gray empty cells and legend. Metric was changed from raw burn to mean usage % during UAT (see Findings).

## Summary

total: 4
passed: 4
issues: 0 (7 found and fixed in-session — see Findings)
pending: 0
skipped: 0

## Findings raised during UAT (all resolved in-session)

| # | Finding | Resolution |
|---|---------|------------|
| 1 | Line charts had **no axis ticks** — bare polyline + one max label | Added y-gridlines + value labels and x-axis date/time ticks (`c35a69f`) |
| 2 | **"Daily burn rate" chart was near-flat ~30M tok/hr** and duplicated the heatmap's burn data | Chart removed; **DASH-04 descoped** (`ae0691f`) |
| 3 | Ranges reset on **local midnight / Monday**, hiding recent activity right after a roll | Switched to rolling **24h / 7d** (`4c14a58`) |
| 4 | Requested comparison against **global Claude Code usage** | **Not built — no such data exists.** Verified against the Anthropic Economic Index: its downloadable dataset has *no temporal dimension and no burn/token-intensity metric*, and the "Cadences" report publishes only normalized relative frequencies, not data. A fabricated baseline was refused; an interim vs-own-average toggle was built then removed at user request (`64c71f6` → `da1c95e`). |
| 5 | **Trend line interpolated straight across data gaps** — a 13.7h overnight outage rendered as a smooth, steady "decline" that never happened. Chart was actively misleading. | `with_gaps()` breaks the line at gaps > 300s (`2b0d16f`) |
| 6 | Weekly series rendered as a **stray floating dash** (1-2 samples cannot form a line) | Sparse series now drawn with dots (`2b0d16f`) |
| 7 | Redundant **100% "limit" rule** on the chart | Removed; the y-axis already tops out at 100% (`45a5162`) |

## Decisions / Deviations

- **DASH-04 descoped** (burn-rate chart removed) — recorded in REQUIREMENTS.md.
- **DASH-02** delivered as rolling `24h/7d/All` rather than calendar day/week.
- **DASH-03** heatmap metric changed from raw burn to **mean usage %**.
- **Scope grew well past the original plan**: the weekly (7-day) cap, reset persistence + markers, and usage projections were added during UAT and are tracked as new requirements **QUOTA-01..03** (QUOTA-01 closes the long-deferred SEED-003).
- **Refused**: the CLI's `forecast`/`status` fields. Both are token-based and report `"limit hit"` under `--api` (token counts are `null`) — they would have claimed exhaustion at 20% usage. Projections are derived from percentages instead.

## Gaps

[none — all findings resolved in-session]
