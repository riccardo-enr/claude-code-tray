# Phase 4: Usage Web Dashboard - Context

**Gathered:** 2026-07-12
**Status:** Ready for planning

<domain>
## Phase Boundary

From a new tray menu item, open a browsable, self-contained HTML dashboard that
renders the persisted `~/.claude/usage-history.jsonl` (written by Phase 2) as
real charts:

- **DASH-01** — a tray menu item opens the dashboard in the default browser
- **DASH-02** — usage-% trend chart over a longer, selectable range than the tray
  (day / week / full retained history)
- **DASH-03** — peak-usage heatmap: hour-of-day (0-23) x day-of-week
- **DASH-04** — burn-rate trend (daily/weekly aggregates) over the full history
- **DASH-05** — reads only the Phase-2 JSONL (single source, read-only, no new
  polling); refreshes on the existing background poll tick
- **DASH-06** — self-contained output: stdlib only, no new deps, inline CSS/JS,
  charts drawn as SVG/canvas

Read-side consumer only. It never writes/prunes history, never adds a poll, never
adds a dependency. Complements the tray trends (the in-menu sparkline/burn/peak
rows stay). Sibling of Phase 3.

</domain>

<decisions>
## Implementation Decisions

### Delivery shape (SEED-001 — the key open decision)
- **D-01:** Default is a **static self-contained `.html` regenerated in the
  background and opened via `file://`** — no `http.server`, no port, no bind, no
  server thread. This was NOT deep-discussed (user deferred it); it is the lazy
  default and the recommended shape. **The planner may revisit** the static-file
  vs. loopback-`http.server` choice per SEED-001 if a concrete need for live
  serving emerges — but live in-browser auto-refresh is explicitly deferred
  (DASH-F1), which removes the main reason to run a server, so static-`file://`
  should hold unless planning surfaces something new.

### Chart rendering (DASH-02, DASH-06)
- **D-02:** **Embed the history data as JSON + small inline JS that draws the
  charts client-side.** The generator emits `<script>const data = [...]</script>`
  (the relevant fields per record) plus inline JS that draws usage-% trend,
  burn-rate trend, and the heatmap, and handles range switching. Everything is
  inline in the single HTML file — no CDN, no external assets, no JS charting
  library (upholds DASH-06 self-containment).
- **D-03:** **Range selection (DASH-02) is client-side.** The full retained
  history is embedded once; the day / week / full presets are applied by JS
  filtering/redrawing from the embedded data — no per-range pre-render, no
  regeneration to switch range.

### Refresh timing (DASH-05)
- **D-04:** **Generate the HTML in the background `poll_loop`, off the Gtk main
  thread, on a throttle** (mirror Phase 3's `last_trend`/`TREND_INTERVAL` and
  the `last_prune`/`PRUNE_INTERVAL` cadence — ~5 min, compute once immediately at
  startup so the file exists before first open). This upholds the mandatory
  "no file I/O on the Gtk main thread" posture (HIST-03 / POLL-02 / Phase 3 D-05).
- **D-05:** **The menu item does zero file I/O** — it only opens the
  already-written file (stdlib `webbrowser.open()` preferred over shelling
  `xdg-open`, but either is fine; opening a URL is DE-agnostic). "Refreshes on
  the poll tick" = the on-disk HTML is kept current by `poll_loop`; opening (or
  reloading) the page shows the latest. No live in-browser auto-refresh this
  phase (DASH-F1 deferred).

### Heatmap encoding (DASH-03)
- **D-06:** **Cell metric = mean burn rate (tok/hr)** over the samples in each
  (hour-of-day, day-of-week) bucket — `mean(burn) * 60`, converting the RAW
  per-minute `burn` field to per-hour exactly ONCE (same convention as Phase 3's
  `trend_burn` / `trend_peak_hour`). "When do I typically consume fastest,"
  consistent with the in-tray peak-hour view.
- **D-07:** **Color ramp = single-hue light->dark** (e.g. one hue with
  lightness scaled by value: low ~`hsl(210,80%,92%)` -> high ~`hsl(210,80%,30%)`);
  **empty buckets render as a distinct neutral gray**, not the low-value color, so
  "no data" is visually distinct from "low usage" (mirrors Phase 3 D-03's gap
  handling for the sparkline).

### Claude's Discretion
- Output file location — suggest `${XDG_CACHE_HOME:-~/.cache}/claude-tray/dashboard.html`
  (a cache path, not `~/.claude/`, since it is a regenerated derived artifact).
- Exact `DASH_INTERVAL` throttle constant (~5 min; may simply piggyback on the
  same tick as `compute_trends`).
- Browser-open mechanism (`webbrowser.open()` vs `subprocess` `xdg-open`).
- Precise chart dimensions, axis labels, day/week/all preset boundaries
  (reuse Phase 3 `local_bounds` conventions: today = local midnight, week = ISO
  Monday 00:00 local).
- Which record fields to embed in the JSON (at minimum `t`, `pct`, `burn`;
  `tokens_used`/`token_limit` if useful for tooltips).
- Whether the HTML-generation logic lives as module-level pure functions next to
  `parse_history`/`trend_*` (preferred, testable via `demo()`/`--selfcheck`) vs
  methods.
- Empty-history state on the page (e.g. a "collecting history..." message,
  paralleling Phase 3 D-12) when there are too few samples to chart.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope
- `.planning/REQUIREMENTS.md` §"Dashboard (DASH)" — DASH-01..06 exact wording,
  plus deferred DASH-F1/F2/F3 and out-of-scope list.
- `.planning/ROADMAP.md` §"Phase 4: Usage Web Dashboard" — goal + success
  criteria + the SEED-001 open-planning-decision note (delivery shape).
- `.planning/seeds/SEED-001-usage-metrics-web-dashboard.md` — origin of this
  phase; frames the static-`file://` vs `http.server` delivery-shape question.

### Prior-phase context (the store this phase reads)
- `.planning/phases/02-usage-history-persistence/02-CONTEXT.md` — JSONL path,
  record schema, and the burn-is-per-minute note.
- `.planning/phases/03-usage-trends-in-the-tray/03-CONTEXT.md` — the sibling
  read-side consumer; reuse its patterns (compute-off-main-thread + throttle,
  burn*60-once, local-calendar bounds, peak-by-mean-burn, empty-state cutover).

### Code (single-file helper)
- `claude-monitor.py` — the whole feature lives here, extended in place:
  - `parse_history()` (lines ~184-207) / `HISTORY_PATH` (line ~57) — REUSE for
    reading; the corruption-tolerance boundary all readers must route through.
  - `history_keep()` (line ~175) — retention predicate; reuse to bound ranges.
  - `history_record()` schema `{t, pct, tokens_used, token_limit, burn}` — `burn`
    is RAW per-minute (lines ~159-172).
  - `trend_burn()` / `trend_peak_hour()` / `local_bounds()` (lines ~251-327) —
    aggregation conventions the dashboard's daily/weekly + heatmap must match.
  - `fmt_tokens()` (line ~128) — REUSE for tok/hr formatting in labels/tooltips.
  - `poll_loop()` (lines ~717-742) — where generate+write belongs; already holds
    `last_prune`/`last_trend` throttles to mirror for the dashboard throttle.
  - `rebuild_menu()` (lines ~509-535) — where the new "Open Usage Dashboard"
    MenuItem is appended (a SENSITIVE item with an `activate` handler, unlike the
    insensitive usage/trend rows).
  - `demo()` / `--selfcheck` (lines ~329-471) — extend with asserts for the new
    pure HTML/aggregation helpers; keep existing asserts green (no regression).

No external specs beyond the above — requirements fully captured in decisions.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `parse_history(text)`: tolerant per-line loader (numeric `t` only) — the single
  read/parse path for all history consumers; the dashboard generator routes
  through it.
- `history_keep(rec, now, days)` + `local_bounds(now)`: retention/calendar
  helpers to slice ranges (day/week/all) consistently with the tray.
- `trend_burn` / `trend_peak_hour`: the burn*60-once and mean-burn-per-bucket
  conventions the dashboard's burn chart + heatmap must reuse (not reinvent).
- `fmt_tokens(n)`: compact `k`/`M` formatter for tok/hr labels.

### Established Patterns
- **All history file I/O off the Gtk main loop** (HIST-03 / POLL-02 / Phase 3
  D-05): generate-and-write in `poll_loop`, main thread only opens the file.
  This is mandatory, not optional — a menu `activate` handler runs on the main
  loop, so it must NOT read history itself.
- **Throttled work in `poll_loop`**: `last_prune`/`PRUNE_INTERVAL` and
  `last_trend`/`TREND_INTERVAL` are the templates for the dashboard-regen throttle
  (compute once immediately at startup, then ~5 min).
- **Pure logic is `demo()`-tested**: the HTML-string builder and any bucketing
  math are pure functions with `--selfcheck` asserts.
- **Sensitive vs insensitive menu items**: usage/trend rows are
  `set_sensitive(False)`; the dashboard item is a normal `MenuItem` with an
  `activate` handler (like the session rows and "Quit monitor").

### Integration Points
- New "Open Usage Dashboard" `Gtk.MenuItem` in `rebuild_menu()`, `activate` ->
  open the pre-written HTML (stdlib `webbrowser.open()`).
- New generate+write step in `poll_loop()` (off main thread, throttled), reading
  via `parse_history` and writing the HTML to a cache path.
- Optionally a cached "dashboard path exists yet?" flag on `Monitor` if the item
  should be insensitive until the first file is written (discretion).

</code_context>

<specifics>
## Specific Ideas

- Chart set to draw (all client-side JS from embedded JSON): usage-% trend
  (selectable day/week/all), burn-rate trend (daily/weekly aggregates over full
  history), and an hour-of-day (0-23) x day-of-week heatmap colored by mean
  burn rate.
- Single-hue light->dark heatmap ramp; empty buckets a distinct neutral gray.
- Self-contained single `.html`: inline `<style>`, inline `<script>` with an
  embedded `const data = [...]` and hand-written SVG/canvas drawing — no CDN,
  no charting library.

</specifics>

<deferred>
## Deferred Ideas

- **DASH-F1** — live in-browser auto-refresh (WebSocket / JS polling). Deferred;
  its absence is the main reason the static-`file://` delivery shape (D-01)
  holds over a loopback `http.server`.
- **DASH-F2** — raw data export (CSV/JSON) surfaced from the dashboard
  (supersedes v1.1's HIST-F1). Out of scope this phase.
- **DASH-F3** — configurable ranges / aggregation windows beyond day/week/all.
  Out of scope; env-configurability deferred.
- Loopback `http.server` delivery shape — considered (D-01) and set aside in
  favor of static `file://`; planner may revisit per SEED-001 if a need appears.

None else — discussion stayed within phase scope.

</deferred>

---

*Phase: 4-usage-web-dashboard*
*Context gathered: 2026-07-12*
