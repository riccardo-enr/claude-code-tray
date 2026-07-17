# Phase 3: Usage Trends in the Tray - Context

**Gathered:** 2026-07-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Turn the persisted `~/.claude/usage-history.jsonl` store (written by Phase 2)
into three read-side trend views inside the existing GTK tray menu:

- **TREND-01** — a sparkline of usage % over the last 24h (unicode block chars)
- **TREND-02** — aggregate burn for today and the current week
- **TREND-03** — the peak-usage hour-of-day

This is the read half of v1.1. It only READS and RENDERS history; it never
writes, prunes, or changes the poll. No separate window, no charting GUI.
Stdlib + existing PyGObject only, X11 unchanged.

</domain>

<decisions>
## Implementation Decisions

### Sparkline (TREND-01)
- **D-01:** 24 fixed columns, one per hour of the 24h window (24 chars wide).
  Each column is the **mean** `pct` of the samples that fall in that hour.
- **D-02:** **Auto-scale** the block heights to the window's own min..max `pct`
  (not fixed 0-100%). Usage typically sits low (~15%), so a fixed scale renders
  a near-flat line; auto-scaling shows the shape. Map min..max across the 8
  block glyphs `▁▂▃▄▅▆▇█`.
- **D-03:** Hours with **no samples** render as a distinct **gap character**
  (e.g. a space) so columns stay time-aligned and gaps are visible — not packed
  out. Planner picks the exact gap glyph.
- **D-04:** The sparkline menu row is **bare blocks, no prefix/label**
  (e.g. `▁▂▃▅▇▆▄▂▁`). (Note: the today/week and peak rows below DO carry labels;
  only the sparkline is bare.)

### Compute placement & cadence
- **D-05:** Trends are computed in the **background `poll_loop`** (off the Gtk
  main loop) and cached as ready-to-render strings on the `Monitor` (mirroring
  `self.usage`). `rebuild_menu()` / `usage_rows()` only read the cached strings
  — **no file I/O on the Gtk main thread** (upholds the Phase 2 / HIST-03/POLL
  posture). Do NOT read history from `usage_rows()`.
- **D-06:** Recompute on a **~5 min throttle** (track last-compute time in
  `poll_loop`, like the existing prune cadence), NOT every poll. **But compute
  once immediately on the first poll / at startup** so trend rows are not blank
  for the first 5 minutes.
- **D-07:** Reads route through the existing corruption-tolerant
  `parse_history()` (single read of `HISTORY_PATH`, wrapped so any `OSError`
  degrades gracefully — same defensive posture as Phase 2).

### Burn aggregation (TREND-02)
- **D-08:** The figure is a **mean burn RATE**, not a total: average the stored
  `burn` field over the in-window samples, shown as **tok/hr** (raw per-minute
  value ×60 — the Phase 2 store keeps burn per-minute; convert to per-hour
  exactly ONCE here). Chosen over integrated "total tokens consumed" because
  the mean rate is directly available and robust to poll gaps / tray downtime
  (integration would be noisy). Reuse `fmt_tokens()` for display.
- **D-09:** Boundaries are **local-calendar**: today = since local midnight;
  week = current ISO week (Monday 00:00 local start). Aligns with the
  hour-of-day peak view and how a person reads "today".

### Peak-usage hour (TREND-03)
- **D-10:** Group all retained history by **hour-of-day (0-23, local time)**;
  rank hours by **mean `burn`** (the hour you typically consume fastest). Show
  the **single** busiest hour, e.g. `peak hour: 15:00 (14.2k tok/hr)`.

### Menu layout & empty state
- **D-11:** **Inline insensitive rows**, appended after the existing 3 usage
  rows, with a `SeparatorMenuItem` between the usage block and the trend block.
  Everything visible at a glance; reuses the `usage_rows()` insensitive-row
  pattern. (No submenu.) Suggested block:
  ```
  72k / 88k (82%)
  resets in 1h 47m
  burn: 12.4k tok/hr
  ────────────────
  ▁▂▃▅▇▆▄▂▁
  today 12.4k/hr · wk 9.8k/hr
  peak hour: 15:00 (14.2k/hr)
  ```
  (Exact today/week/peak row copy is planner's discretion; keep it compact.)
- **D-12:** **Empty state** = a single insensitive row `trends: collecting
  history…` shown until there is enough data (≳1h of samples), then swapped for
  the real rows. No half-empty sparkline, no partial/misleading early numbers.

### Claude's Discretion
- Exact gap glyph for empty sparkline hours (D-03).
- Exact row wording/format for today/week burn and peak-hour rows (D-08/D-10/D-11).
- The precise throttle constant (~5 min) and "enough data" threshold for the
  empty-state cutover (D-06/D-12).
- Whether the 4 pure trend functions live as module-level helpers next to
  `history_record`/`history_keep`/`parse_history` (preferred, testable via
  `demo()`) vs methods.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope
- `.planning/REQUIREMENTS.md` §"Trends display (TREND)" — TREND-01/02/03 exact wording.
- `.planning/ROADMAP.md` §"Phase 3: Usage Trends in the Tray" — goal + success criteria.
- `.planning/phases/02-usage-history-persistence/02-CONTEXT.md` — the store this
  phase reads: JSONL path, record schema, and the burn-is-per-minute note.

### Code (single-file helper)
- `claude-monitor.py` — the whole feature lives here, extended in place:
  - `parse_history()` / `history_keep()` (lines ~166-197) — REUSE for reading;
    the corruption-tolerance boundary all readers must route through.
  - `history_record()` schema `{t, pct, tokens_used, token_limit, burn}` — burn
    is RAW per-minute (line ~150-163).
  - `Monitor.usage_rows()` / `rebuild_menu()` (lines ~381-427) — the
    insensitive-row + separator + `show_all()` pattern trend rows plug into.
  - `poll_loop()` (lines ~540-559) — where compute+cache belongs; already holds
    `last_prune` throttling to mirror for the trend throttle.
  - `fmt_tokens()` (line ~119) — REUSE for tok/hr formatting.
  - `demo()` / `--selfcheck` (lines ~242-342) — extend with asserts for the new
    pure trend functions; keep existing asserts green (no v1.0/Phase-2 regression).

No external specs beyond the above — requirements fully captured in decisions.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `parse_history(text)`: tolerant per-line loader returning records with numeric
  `t`; the single read/parse path for all history consumers.
- `history_keep(rec, now, days)`: retention predicate — reuse to slice the last
  24h for the sparkline and to bound "week".
- `fmt_tokens(n)`: compact `k`/`M` formatter for the burn rows.
- `usage_rows()` + `rebuild_menu()`: insensitive-row pattern + separator +
  `menu.show_all()` — trend rows are appended the same way.

### Established Patterns
- **All file I/O off the Gtk main loop** (Phase 2 HIST-03 / v1.0 POLL-02): the
  cache-in-`poll_loop`, read-cached-in-`rebuild_menu` split (D-05) is mandatory,
  not optional.
- **Throttled work in `poll_loop`**: `last_prune` + `PRUNE_INTERVAL` is the
  template for the ~5min trend throttle (D-06).
- **Pure logic is `demo()`-tested**: sparkline bucketing, burn averaging,
  peak-hour selection are pure functions with `--selfcheck` asserts.
- **Guarded env-int constants**: `POLL_INTERVAL`/`HISTORY_DAYS` show the
  `int(...)`/`except ValueError -> default` idiom if any trend constant becomes
  env-configurable (not required this phase — see deferred TREND-F1).

### Integration Points
- New cached fields on `Monitor.__init__` (e.g. `self.trends = None`), populated
  from `poll_loop`, consumed by `rebuild_menu`/`usage_rows`.
- One `SeparatorMenuItem` inserted between usage rows and trend rows.

</code_context>

<specifics>
## Specific Ideas

- Menu mockup the user endorsed (bare sparkline, separator above trends):
  ```
  72k / 88k (82%)
  resets in 1h 47m
  burn: 12.4k tok/hr
  ────────────────
  ▁▂▃▅▇▆▄▂▁
  today 12.4k/hr · wk 9.8k/hr
  peak hour: 15:00 (14.2k/hr)
  ```
- Block glyph ramp for auto-scaled sparkline: `▁▂▃▄▅▆▇█`.

</specifics>

<deferred>
## Deferred Ideas

- **TREND-F1** — configurable sparkline window / aggregation period beyond the
  24h/today/week defaults. Out of scope this phase (env-configurability deferred).
- **HIST-F1** — raw data export (CSV/JSON). Out of scope; revisit if in-tray
  views prove insufficient.
- Integrated "total tokens consumed" burn view — considered (D-08) and rejected
  for this phase in favor of mean rate; could return if a total is wanted later.

None else — discussion stayed within phase scope.

</deferred>

---

*Phase: 3-usage-trends-in-the-tray*
*Context gathered: 2026-07-12*
