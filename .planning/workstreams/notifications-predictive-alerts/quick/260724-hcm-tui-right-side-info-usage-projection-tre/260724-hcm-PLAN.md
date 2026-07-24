---
phase: 260724-hcm
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - claude-tui.py
  - claude-monitor.py
  - claude_monitor/core.py
  - claude_monitor/test_claude_monitor.py
autonomous: true
requirements: [QT-260724-hcm]

must_haves:
  truths:
    - "#usage: to the right of each present cap, a projected usage % at reset ('proj NN% @HH:MM') band-colored via core.band(proj)."
    - "A cap trending over 100% before reset shows an exhaust ETA (core.hhmm) in a warning color instead of the plain @reset time; {early:True} and None degrade to 'proj --'."
    - "#trends: a Mon..Sun hour-by-day heatmap rendered to the right of the existing column graph, colored green->red via core.band, once history exists."
    - "Absolute 5h token usage (X / Y) stays rendered via the existing core.fmt_tokens path -- no second token formatter is introduced (D-05)."
    - "Degraded paths preserved: usage None -> 'usage unavailable'; falsy trends -> collecting message; no/empty heatmap -> no extra column."
  artifacts:
    - claude-tui.py
    - claude-monitor.py
    - claude_monitor/core.py
    - claude_monitor/test_claude_monitor.py
  key_links:
    - "compute_trends feeds core.heatmap_buckets records sanitized via core.history_numeric (a corrupt/missing pct otherwise raises and kills the poll thread -- the 260713-fry crash class)."
    - "snapshot dict 'heatmap' key <-> claude-tui.py snap.get('heatmap')."
    - "core.project(pct, reset, WIN5/WIN7, now) + core.band/core.hhmm <-> #usage right column."
---

<objective>
Fill the empty right side of the claude-tui.py usage and trends panels with informative
content derived entirely from data core already computes: a per-cap usage projection at
reset (with exhaust ETA) beside the usage gauges, and a Mon..Sun hour-by-day heatmap beside
the trends column graph.

Purpose: the TUI panels currently leave dead space on the right; the projection answers
"will I run out before reset?" and the heatmap answers "when do I actually burn quota?" --
both already exist for the desktop dashboard, neither is on the terminal surface yet.

Output: usage projection column (claude-tui.py), a JSON-safe heatmap key on the snapshot
socket verb (claude-monitor.py), one small pure core helper + its assert
(claude_monitor/core.py + test), and the heatmap renderer (claude-tui.py).
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/workstreams/notifications-predictive-alerts/STATE.md

# The three files this plan touches. Read the referenced regions before editing.
@claude-tui.py
@claude_monitor/core.py
@claude-monitor.py

Reuse only -- do NOT reimplement projection or heatmap math:
- core.project(pct, reset, win, now)  (~core.py:181) with core.WIN5 (5h) / core.WIN7 (7d)
- core.band(pct)  (~core.py:764)  ->  "green" | "yellow" | "red" (also a rich style token)
- core.hhmm(epoch)  (~core.py:207)  ->  local "HH:MM"
- core.fmt_tokens(n)  (~core.py:310)  -> the ONE token formatter (already used by tui_usage_rows)
- core.heatmap_buckets(records)  (~core.py:563)  -> 7x24 grid of float|None (dow Mon..Sun x hour)
- core.history_numeric(records)  (~core.py:544)  -> sanitizer that MUST run before heatmap_buckets
- core.tui_usage_rows / _gauge / _cap_row_text  (existing left-side render, keep unchanged)
</context>

<tasks>

<task type="tracer">
  <name>Task 1: Usage-panel right side -- per-cap projection at reset</name>
  <files>claude-tui.py</files>
  <action>
  In _usage_renderable (~L228) add a right-hand projection column beside each present cap.
  Keep the existing left content unchanged: the gauge from _gauge plus the band-colored row
  text from _cap_row_text over core.tui_usage_rows. Lay the two columns side by side with a
  padless rich.table.Table(box=None) (or rich.columns.Columns) returned through the same
  markup=False Static path -- the panel renders only trusted core-computed numbers, so no
  untrusted string reaches a markup parser (the untrusted dir-name path lives in the sessions
  DataTable and is not touched here).

  For each present cap compute the projection with core.project, reading every field via .get:
  the 5h cap uses core.WIN5 with used_percentage / resets_at_epoch; the 7d cap (only when the
  7d row is present) uses core.WIN7 with seven_day_pct / seven_day_reset. Render the result:
  on a {"proj": p} result show "proj NN% @HH:MM" where NN is round(p["proj"]) and HH:MM is
  core.hhmm(reset_epoch), styled core.band(p["proj"]); when the result also carries an
  "exhaust" key (project() sets it only when proj strictly exceeds 100), show the exhaust ETA
  "out ~HH:MM" via core.hhmm(p["exhaust"]) in a warning style INSTEAD of the plain @reset;
  a {"early": True} result shows "proj -- (early)"; a None result shows "proj --".

  Absolute 5h token usage already renders in the left row via core.tui_usage_rows /
  core.fmt_tokens (correctly absent under --api, where token counts are null) -- do not
  re-render or reformat it, and do not add a second token formatter (that divergence is
  exactly what D-05 exists to prevent). No daemon or core change in this task.
  </action>
  <verify>
    <automated>just lint</automated>
    <automated>just selfcheck</automated>
  </verify>
  <done>Each present cap shows a band-colored projection on the right; a cap trending over 100% shows a warning-colored exhaust ETA; early/None projections show "proj --"; the usage-unavailable path is unchanged; no new number formatter was added. lint clean and selfcheck exits 0. (Confirm visually with `just tui` -- the usage half needs no restart.)</done>
</task>

<task type="auto">
  <name>Task 2: Heatmap data path -- core row-span helper + daemon snapshot key</name>
  <files>claude_monitor/core.py, claude_monitor/test_claude_monitor.py, claude-monitor.py</files>
  <action>
  Add a pure, stdlib-only helper core.heatmap_active_span(grid) that returns the (lo, hi)
  inclusive hour-index bounds where any of the 7 weekday columns is non-None, or None when the
  whole 7x24 grid is empty. This lets the renderer collapse empty leading/trailing hours while
  keeping interior gaps time-aligned (same intent as SPARK_GAP). Place it near heatmap_buckets.
  core.py stays third-party-free (stdlib only, no textual/rich).

  Add an assert block to test_claude_monitor.demo() next to the existing heatmap_buckets asserts
  (~L328), and add heatmap_active_span to the module import list (~L40): an all-None 7x24 grid
  returns None; a grid with data only at hours 9 and 14 returns (9, 14); a single active hour h
  returns (h, h).

  In the daemon cache the grid alongside trends: add "self.heatmap = None" beside
  "self.trends = None" in Monitor.__init__ (~L67), and in compute_trends (~L361) set
  self.heatmap = core.heatmap_buckets(core.history_numeric(records)) from the SAME records
  already read for trends. Running history_numeric first is load-bearing: heatmap_buckets reads
  rec["pct"] and subtracts consecutive values, so a corrupt or missing pct would raise and kill
  the poll thread -- the exact 260713-fry crash class (build_trend_rows and render_dashboard both
  sanitize before the heatmap for this reason). Add "heatmap": mon.heatmap to the snapshot dict
  in _handle_conn (~L597), beside "trends": mon.trends. No serialization shim is needed:
  heatmap_buckets already returns a plain list-of-lists of float|None, which is JSON-safe.
  </action>
  <verify>
    <automated>just selfcheck</automated>
    <automated>just lint</automated>
  </verify>
  <done>core.heatmap_active_span exists with passing asserts; the snapshot query response carries a "heatmap" key holding a 7x24 float|None grid built from history_numeric-sanitized records; core.py imports clean on /usr/bin/python3 (no textual/rich); selfcheck exits 0 and lint clean.</done>
</task>

<task type="auto">
  <name>Task 3: Trends-panel right side -- render the heatmap grid</name>
  <files>claude-tui.py</files>
  <action>
  Extend _trends_renderable (~L253) to take the heatmap grid and render it to the RIGHT of the
  existing decoded column graph + today/wk/peak text, using the same padless side-by-side rich
  renderable as Task 1 (rich.table.Table(box=None)) through the markup=False Static path.
  render_all (~L278) passes snap.get("heatmap") into it.

  Preserve every degraded path: a falsy trends still returns core.trend_text(trends) verbatim
  (the collecting message) and renders no heatmap; a present-trends-but-heatmap-None/empty (or an
  all-None grid) renders only the existing left side, no right column. Otherwise build a compact
  grid: call core.heatmap_active_span(grid) for the (lo, hi) hour rows; render one row per hour
  lo..hi with 7 columns Mon..Sun (grid[dow][hour]); each non-None cell is a shaded block styled
  core.band(value) (green->red), None cells blank/dim so an interior gap stays distinct from a
  genuine 0%. A Mon..Sun column header and a leading hour label per row are optional chrome.
  Every value rendered is a core-computed float -- no untrusted string reaches markup; the
  sessions DataTable's untrusted dir-name path (T-09-01 Text-per-cell) is not touched here.
  </action>
  <verify>
    <automated>just lint</automated>
    <automated>just selfcheck</automated>
  </verify>
  <done>With history present the trends panel shows a Mon..Sun hour heatmap to the right of the column graph, band-colored green->red, empty leading/trailing hours collapsed; the collecting and no-heatmap states render unchanged; lint clean and selfcheck exits 0. (Daemon changed in Task 2 -> the live heatmap needs `just restart` then `just tui`, run by the operator in a desktop session -- do NOT run restart here.)</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| daemon socket -> TUI | Snapshot JSON: usage/trends/heatmap fields are core-computed numerics (trusted). |
| filesystem -> TUI | Session dir names are untrusted -- rendered only in the sessions DataTable, NOT touched by this plan. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-QT-01 | Tampering | usage/trends side-by-side renderables | low | accept | Panels stay markup=False and render only core-computed numbers (percentages, epochs, token counts via core.fmt_tokens, heatmap floats). No filesystem path is routed through markup; the untrusted dir-name path (sessions DataTable) keeps its unchanged T-09-01 Text-per-cell mitigation. |
| T-QT-02 | Denial of Service | compute_trends heatmap compute | medium | mitigate | Feed core.heatmap_buckets records via core.history_numeric so a corrupt/missing pct cannot raise and kill the poll thread (260713-fry class); compute_trends already runs under the poll thread's blanket except. |
| T-QT-03 | Info disclosure | (no new surface) | low | accept | No new data source, no new socket message type, no new runtime dependency -- only one added key on the existing snapshot response. |
</threat_model>

<verification>
- `just selfcheck` exits 0 (core stays third-party-free; heatmap_active_span asserts pass).
- `just lint` clean (ruff).
- Manual (operator, desktop session): `just tui` shows the usage projection immediately; after
  `just restart` the trends heatmap renders live (daemon changed in Task 2).
</verification>

<success_criteria>
- Usage panel: each present cap shows a band-colored "proj NN% @HH:MM"; over-100% caps show a
  warning-colored exhaust ETA; early/None -> "proj --". No new token formatter.
- Trends panel: Mon..Sun hour heatmap to the right of the column graph, green->red via core.band,
  leading/trailing empty hours collapsed; degraded/collecting states unchanged.
- No new runtime dependency; core.project / heatmap_buckets / band / hhmm / fmt_tokens reused.
- `just selfcheck` and `just lint` green.
</success_criteria>

<output>
Create `.planning/workstreams/notifications-predictive-alerts/quick/260724-hcm-tui-right-side-info-usage-projection-tre/260724-hcm-SUMMARY.md` when done.

The SUMMARY MUST note: the trends heatmap requires `just restart` (Task 2 changed the daemon) to
appear live; the usage projection (Task 1) shows on the next `just tui` with no restart.
</output>
