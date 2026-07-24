# Phase 10: TUI Polish (btop-style) - Context

**Gathered:** 2026-07-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Turn the v1.5 plain-text `claude-tui.py` into a btop-inspired terminal dashboard:
threshold-colored usage rows, per-cell gradient gauge meters, a richer (taller,
colored) trends graph, a status-colored striped sessions table, and titled rounded
bordered panels. **Same data, same `{"query": "snapshot"}` socket verb, same
`textual` dependency.** Pure presentation.

The load-bearing architecture is already locked by ROADMAP + REQUIREMENTS and is NOT
re-opened here:
- **Anything assertable lives in `claude_monitor.core`** where `--selfcheck` on stock
  `/usr/bin/python3` (PEP 668) proves it: threshold band logic (TUI-06/09), gauge
  fill-cell math (TUI-07), sparkline-level decode for the graph (TUI-08). `core` must
  never import `textual`/`rich`.
- **Color/gauge glyphs/borders/striping/CSS stay in `claude-tui.py`** — the only file
  that imports `textual`.
- **D-05 parity holds:** `core` stays the single source of every formatted value; no
  new number/string formatter is introduced in `claude-tui.py`.
- This is a **plan-level split within one phase** (core substrate + `--selfcheck`
  asserts, then textual wiring), mirroring v1.5's 09-01/09-02 — NOT a phase boundary.

Out of scope (locked, do not reopen): no new data source, no new polling, **no
IPC/snapshot-shape change**, no new runtime dependency; TUI click-to-focus and
standalone no-daemon mode stay deferred. See REQUIREMENTS.md "Out of Scope".

</domain>

<decisions>
## Implementation Decisions

### TUI-06 Threshold color bands
- **D-01:** **Fixed btop-style bands, independent of the badge threshold**, shared by
  the 5h and 7d caps: e.g. `< 70 green / 70-90 yellow / >= 90 red` (exact cutoffs are
  planner/UI-spec's to finalize; the shape is fixed three-band). Rationale: the
  configurable `USAGE_THRESHOLD` (default 80, choices 70/80/90/95) is the user's
  personal "warn me" line for the tray badge — a different concept from btop's
  proximity-to-cap coloring. Colors here mean "how close to the cap" regardless of the
  mutable badge config, so they never move when the user retunes the badge.
- **D-02:** The band applies to the usage %, burn rate, and reset countdown of a given
  cap (all three colored by that cap's proximity, per TUI-06). Lives in `core` as a
  pure `band(pct) -> {green|yellow|red}` (or equivalent) function, asserted in
  `--selfcheck`. `claude-tui.py` maps the band name to a color/CSS class only.
  — **Reversibility:** reversible — a pure core function + a CSS class map, local.

### TUI-07 Gauge / meter
- **D-03:** Each 5h/7d row renders as a **per-cell gradient progress bar** — filled
  cells colored along the green->yellow->red ramp by their position in the bar (btop's
  signature meter), replacing the plain "N% of limit" text. The bar shows proximity to
  cap as a sweep; it coexists with D-01's band coloring of the row text (band = "which
  zone", gradient = "the sweep"). Both share one palette.
- **D-04:** The fill math (percent -> number of filled cells at a given bar width) is a
  **pure function in `core`**, asserted in `--selfcheck`; `claude-tui.py` applies the
  glyphs and per-cell colors. Glyph mechanism (custom block-char string vs a
  rich/textual bar widget) is planner's discretion **provided the fill-cell count is
  computed in `core`, not inside a render widget** (keeps D-05 parity and assertability).

### TUI-08 Richer trends graph
- **D-05:** Constraint-driven: the snapshot shape is fixed, so the graph carries **no
  new trend data** — it re-renders the existing 24-level `SPARK_GLYPHS` sparkline the
  snapshot already delivers. Chosen direction: **taller decoded bars** — decode each
  sparkline glyph back to its level (0-7) and render a taller multi-row block/braille
  column graph, colored by height along the same green->red ramp as D-03.
- **D-06:** The glyph->level decode + column-height derivation is a **pure function in
  `core`** ("no new trend math" — it inverts the existing `SPARK_GLYPHS` mapping,
  reusing `build_trend_rows`/`trend_sparkline` output), asserted in `--selfcheck`.
  `claude-tui.py` renders the decoded heights as colored rows. The collecting-state
  message (`trends` is None/empty, D-07 from Phase 9) must still render, not crash.

### TUI-09 / TUI-10 Sessions table & panels
- **D-07:** Sessions rows are **status-colored with zebra striping**: waiting = yellow,
  running = green, done = dim/gray (exact palette is UI-spec's; mapping is fixed), plus
  subtle zebra striping for scan-ability. Sort order (waiting -> running -> done) and
  columns (status/project/time) are unchanged from Phase 9.
- **D-08:** Panels use **static rounded, titled borders** — no threshold tint on the
  borders. The three panels (usage, trends, sessions) each become a titled rounded box
  (btop paneled layout). Border coloring is static; the threshold signal lives in the
  row text (D-01) and gauge fill (D-03), not in the panel chrome.

### Claude's Discretion
- Exact band cutoff numbers (within the fixed three-band shape), the exact color hex /
  textual theme-var mapping, gauge bar width, glyph set for gauge and decoded graph,
  and the CSS for borders/striping/titles — planner + UI-spec's call.
- Gauge glyph mechanism (custom string vs widget) **as long as** the fill-cell count is
  a pure `core` function proven by `--selfcheck`.
- Whether the band/gauge/decode helpers are one function each or share a small module —
  planner's call; they all belong above the textual boundary in `core`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The surface being reworked (Phase 9, shipped)
- `claude-tui.py` — the whole v1.5 TUI: `ClaudeTui` App, CSS block, `render_all`
  (calls `core.tui_usage_rows`, `core.trend_text`, `core.sess_rows`), the two timers,
  the fetch worker, and degraded-mode presentation. The textual boundary; every string
  it renders was already formatted by `core`.
- `.planning/workstreams/notifications-predictive-alerts/phases/09-terminal-dashboard-claude-tui-py/09-CONTEXT.md`
  (archived under `milestones/v1.5-phases/`) — Phase 9's locked decisions D-01..D-12
  (layout, D-05 verbatim-trends parity, D-09 tick model, D-10/11/12 degraded mode).

### The `core` values to color/gauge/decode (single source of truth — D-05)
- `claude_monitor/core.py:747` (`tui_usage_rows`) — the 5h/7d row builder TUI-06/07
  rework; every numeric already goes through an existing core formatter.
- `claude_monitor/core.py:786` (`trend_text`), `:490` (`build_trend_rows`),
  `:439` (`trend_sparkline`), `:243` (`SPARK_GLYPHS = "▁▂▃▄▅▆▇█"`) — the trend data
  and glyph mapping TUI-08 re-renders (decode the levels; no new trend math).
- `claude_monitor/core.py:846` (`sess_rows`), `:806` (`fmt_elapsed`), `:833`
  (`_safe_cell`) — the sessions cells TUI-09 styles. Note `Text(...)`-per-cell markup
  mitigation in `claude-tui.py:199` must survive any restyle.
- `claude_monitor/core.py:310-334` (`fmt_tokens`, `fmt_countdown`, `fmt_countdown_wk`)
  — existing formatters; reuse, never re-implement.
- `claude_monitor/core.py:29` (`USAGE_THRESHOLD = 80`), `:34`
  (`THRESHOLD_CHOICES = (70,80,90,95)`) — the badge threshold, kept SEPARATE from the
  TUI-06 fixed bands (D-01).

### Project rules & gates
- `.planning/workstreams/notifications-predictive-alerts/ROADMAP.md` §Phase 10 — goal,
  five success criteria, and the "Constraints & boundary" block plan-phase must respect.
- `.planning/workstreams/notifications-predictive-alerts/REQUIREMENTS.md` — TUI-06..TUI-10,
  the core-vs-`claude-tui.py` architecture rule, the btop design reference, Out of Scope.
- `justfile` — `just selfcheck` is the green-gate every change must keep passing;
  `just restart` after any code change; `just tui` to view.
- `claude_monitor/test_claude_monitor.py` — the `--selfcheck` assert suite; every pure
  band/gauge/decode helper this phase adds gets its asserts here.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `claude_monitor/core.py` is `gi`-free and pure — the natural, and required, home for
  the band/gauge-fill/glyph-decode helpers so `--selfcheck` on `/usr/bin/python3` proves
  them without importing textual/rich.
- `SPARK_GLYPHS` (`core.py:243`) is an 8-level block ramp already shipping in the tray
  and the TUI; TUI-08 decodes it (glyph -> index 0-7) rather than inventing a new ramp.
- The v1.5 render path (`render_all` in `claude-tui.py`) already funnels every panel
  through `core.tui_usage_rows` / `core.trend_text` / `core.sess_rows` — the seams where
  color/gauge/graph slot in without touching the fetch loop or the snapshot.

### Established Patterns
- Assertable-in-core / render-only-in-`claude-tui.py` split is the v1.5 precedent
  (09-01 substrate then 09-02 textual wiring); Phase 10 repeats it as a plan-level split.
- Every DataTable cell is a `rich.text.Text`, never a `str` (`claude-tui.py:199`) — the
  markup/control-char injection mitigation (T-09-01). Any sessions restyle keeps this.
- Terminal-palette inheritance: `self.theme = "ansi-dark"` (`claude-tui.py:95`, quick
  task `260724-thm`) renders through the terminal's 16 ANSI colors. **Coloring choices
  should read correctly against an inherited ANSI-16 palette**, not assume fixed RGB —
  the stale-dim `opacity` already reads flatter under 16-color (noted ponytail comment).

### Integration Points
- No new integration: read-only client of the same socket, same snapshot shape. All new
  code is (a) pure helpers in `core` + their `--selfcheck` asserts, and (b) CSS/render
  changes in `claude-tui.py`. `claude-monitor.py` (the daemon) does not change.
- `--selfcheck` must stay green on stock `/usr/bin/python3`; the new helpers must not
  pull `textual`/`rich` into that interpreter.

</code_context>

<specifics>
## Specific Ideas

- btop (`https://github.com/aristocratos/btop`) is the visual north star: rounded titled
  panels, gradient green->yellow->red meters, dense colored graphs. Take the look, not
  the architecture.
- One shared palette across the three visuals: the TUI-06 bands, the TUI-07 per-cell
  gauge gradient, and the TUI-08 height coloring all use the same green->yellow->red
  ramp so the dashboard reads as one system.
- The band color and the gauge fill are two honest signals that agree — band text says
  "which zone", the gradient bar shows "the sweep toward the cap".

</specifics>

<deferred>
## Deferred Ideas

- **Threshold-tinted panel borders** (usage box border colored by the worst 5h/7d band)
  — considered under TUI-10, rejected for this phase (D-08 keeps borders static; the
  threshold signal lives in row text + gauge). Revisit only if the static border reads
  flat next to the colored content.
- **Terminal-width / taller sparkline fed by real numeric series** — would need a
  snapshot-shape change (new numeric trend field), which is out of scope this milestone.
  The taller graph (D-05) is bounded to decoding the existing 24-level glyphs.
- Carried from v1.5, still deferred: **TUI click-to-focus a pane** (tray stays the focus
  surface) and **standalone no-daemon mode** reading `usage-history.jsonl` directly.

</deferred>

---

*Phase: 10-TUI Polish (btop-style)*
*Context gathered: 2026-07-24*
