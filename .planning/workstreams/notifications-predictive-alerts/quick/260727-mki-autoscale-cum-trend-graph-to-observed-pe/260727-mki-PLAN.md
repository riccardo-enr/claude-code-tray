---
phase: 260727-mki
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - claude-monitor.py
  - claude_monitor/core.py
  - claude_monitor/test_claude_monitor.py
  - rust/src/main.rs
  - fixtures/generate.py
  - fixtures/snapshot/cum-trend-clipped-keeps-newest.json
  - fixtures/snapshot/cum-trend-populated.json
  - fixtures/README.md
autonomous: true
requirements: [QT-260727-mki]

must_haves:
  truths:
    - "The cum_trend sparkline's own observed peak bucket renders at the TOP row (level 7 of 8), never clamped against a fixed 100% ceiling -- this REVERSES 260727-krn's original 'comparable window over window' design, which pinned even a 30% peak to level 2, indistinguishable from a quiet period. Confirmed empirically: a live daemon snapshot decoded to levels [0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,2,2,2] (max level 2 of 7) under the old fixed scale."
    - "cum_trend_axis(records, now) computes its ticks from the SAME bucket-derived peak build_cum_trend scales against (not the raw despiked series, which can include a sample whose bucket index falls outside the window and never actually renders) -- top/middle/floor ticks always describe the bars actually drawn above them, never a stale-sample value nothing draws."
    - "When the terminal is too narrow to show every column of the cum_trend sparkline, draw_trends keeps the LAST N characters (the newest, rightmost columns) and drops the FIRST ones (the oldest, leftmost) -- verified by an automated ratatui TestBackend render test AND by a live tmux-captured render of a wide synthetic fixture, both before-repro'd and after-fixed."
    - "The original hourly bar chart (trend_sparkline, trend_axis, build_trend_rows, TREND_INTERVAL, CUM_TREND_INTERVAL) is byte-for-byte untouched -- only the cum_trend graph's own scaling function and its own render-time clipping change."
    - "No new dependency, no new poll, no new config knob."
  artifacts:
    - claude-monitor.py
    - claude_monitor/core.py
    - claude_monitor/test_claude_monitor.py
    - rust/src/main.rs
    - fixtures/generate.py
    - fixtures/snapshot/cum-trend-clipped-keeps-newest.json
    - fixtures/README.md
  key_links:
    - "Monitor.compute_trends: self.cum_trend_axis = core.cum_trend_axis(records, now) mirrors self.trend_axis = core.trend_axis(records, now) exactly one line above it -- both independently recompute their own peak from the same records and both return None only in the collecting-state case."
    - "draw_trends computes columns = Layout::split(inner) and fits_beside_heatmap ONCE, before building either graph, so clip_to_newest's graph_width argument (columns[0].width or inner.width) is the exact width the Paragraph renders into later in the SAME function call -- no independently re-derived HEATMAP_WIDTH arithmetic that could silently drift out of sync with the real split."
    - "cum_trend_axis(records, now) fills the SAME idx-range-checked buckets array build_cum_trend fills before taking its peak -- a sample whose bucket index lands outside [0, columns) (a stale/past-reset record) cannot inflate the axis tick beyond what the sparkline actually draws."
---

<objective>
Fix two independent, already-diagnosed bugs in the cum_trend graph (the Rust TUI's
cumulative-window-usage sparkline, added by 260727-krn and sped up/enriched by
260727-lns):

1. **Vertical quantization.** `build_cum_trend` scales against a fixed 0..100% ceiling,
   so at a realistic usage level (e.g. 28%) the graph only ever lights the bottom 2-3 of
   8 rows and reads as a flat plateau, not a trend. Fix: autoscale to the CURRENT
   window's own observed peak, exactly mirroring how `trend_sparkline`/`trend_axis`
   already autoscale the hourly bar chart to ITS own peak. **This deliberately REVERSES
   260727-krn's original design decision** ("a %-of-window bar has to mean the same
   thing every time it is drawn, comparable window over window") because it produces an
   unreadable graph at realistic usage levels -- the user's actual want ("a line or a
   trend") requires the full 8-row vertical range, exactly as `trend_sparkline`'s own
   docstring already argues its OWN scale should not be comparable across renders for
   the same reason. Disclose this reversal in the SUMMARY and the STATE.md quick-task
   row; do not silently override it.

2. **Width-clipping the wrong end.** The cum_trend sparkline can be up to 60 characters
   wide (one per 5-min bucket across the 5h window); at narrow terminal widths the
   `Paragraph` (no `.wrap()`) truncates it from its right/newest end, silently hiding
   the newest ~2h of data while stale history stays visible. Fix: when the sparkline is
   wider than the panel actually renders into, keep only the LAST N characters (the
   newest columns), dropping the OLDEST columns instead.

Both bugs were confirmed directly, not just theorized: decoding a live daemon snapshot's
cum_trend sparkline gave levels topping out at 2 of 7 (the plateau bug), and rendering a
synthetic wide climbing sparkline through the real TUI at narrow tmux widths showed the
graph's top (highest-level, newest) rows going blank first as the terminal narrows,
while the bottom (oldest, left-anchored) rows stayed visible (the clip-wrong-end bug).

Purpose: the graph currently cannot show a trend at all at normal usage levels, and can
silently hide the most recent data at normal terminal widths -- both defeat the entire
point of the feature.

Output: `core.build_cum_trend` autoscales to its own peak; `core.CUM_TREND_AXIS` (a
fixed constant) is replaced by `core.cum_trend_axis(records, now)` (a function, mirroring
`trend_axis`); `draw_trends` clips the cum_trend sparkline to its newest columns before
handing it to the unmodified `trend_graph_lines`.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/workstreams/notifications-predictive-alerts/STATE.md

# Regions to read before editing (do NOT re-read a range already seen):
@claude-monitor.py              # Monitor.__init__ cum_trend_axis cache field, comment only, ~line 75; compute_trends ~380-391 (the exact self.trend_axis = core.trend_axis(records, now) line to mirror is ~389, immediately above the line this task changes)
@claude_monitor/core.py         # WIN5 ~238; SPARK_GLYPHS ~310; trend_sparkline ~677-698 (the own-peak scaling formula to mirror verbatim: hi = max of non-None buckets, hi is None -> gap-fill, hi == 0 -> floor-fill, else round(value/hi*(len(SPARK_GLYPHS)-1))); trend_axis ~701-743 (the tick convention to mirror: rows=len(SPARK_GLYPHS), top=rows-1, ticked={top, rows//2, 0}, label(row) blank unless ticked, row 0 is a bare "0"); despike ~1033-1054 (reuse verbatim, do not modify); CUM_TREND_INTERVAL comment+const ~1004-1007 (DO NOT TOUCH -- already correctly tuned by 260727-lns); CUM_TREND_AXIS comment+const ~1009-1016 (DELETE this whole block); build_cum_trend ~1057-1097 (rescale here)
@claude_monitor/test_claude_monitor.py  # import list ~18-94 (CUM_TREND_AXIS at line 39); cumulative-window-trend assert block ~619-642
@rust/src/main.rs               # HEATMAP_WIDTH const ~92; snapshot_cum_trend ~767-772; trend_graph_lines ~806-856 (do NOT modify -- shared with the untouched hourly chart; its internal axis_width gutter formula at ~823-825 is the exact formula clip_to_newest must reuse); draw_trends ~903-956 (restructure here); test module: buffer_text ~1349-1353, cum_trend_adds_a_second_graph_below_the_hourly_bars ~1356-1409 (hoist its local render_trends_rows closure to a shared fn), cum_trend_absent_is_a_true_no_op_on_render_and_layout ~1412-1425, sessions_app ~1427-1431
@fixtures/generate.py           # F["cum-trend-populated"] ~170-182; write loop ~263-269
@fixtures/README.md             # Expectations table ~42-48 (cum_trend_axis row)

Reuse, do NOT reimplement:
- trend_sparkline's own-peak scaling formula (hi/None/hi==0 three-way branch)  -> mirrored
  verbatim in build_cum_trend's new scaling code
- trend_axis's tick convention (rows/top/ticked={top,rows//2,0}, bare "0" floor) -> mirrored
  in the new cum_trend_axis(records, now)
- despike, history_numeric, WIN5, CUM_TREND_INTERVAL                          -> unchanged,
  reused verbatim in cum_trend_axis exactly as build_cum_trend already uses them
- rust Layout::split / Constraint::Min(10)+Constraint::Length(HEATMAP_WIDTH)   -> computed
  ONCE in draw_trends and reused for both the clip and the final render (no second,
  independently re-derived width calculation)
- trend_graph_lines                                                            -> unmodified

Do not touch: TREND_INTERVAL, CUM_TREND_INTERVAL, POLL_INTERVAL (refresh/bucket cadence is
already correctly tuned by 260727-lns); trend_sparkline, trend_axis, build_trend_rows (the
hourly chart's own scaling, read-only reference/template); trend_graph_lines (shared,
untouched).
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Autoscale build_cum_trend to its own observed peak; replace the fixed CUM_TREND_AXIS constant with a cum_trend_axis(records, now) function (Python)</name>
  <files>claude-monitor.py, claude_monitor/core.py, claude_monitor/test_claude_monitor.py</files>
  <behavior>
    New/updated asserts in test_claude_monitor.demo (assert style, no pytest):
    - The existing `_cum_recs` wire data (bucket 0 = pct 10.0, bucket 5 = pct 30.0, bucket
      10 = a despiked spike) is left UNCHANGED -- only the assertions against it change,
      from fixed-100-ceiling expectations to peak-relative ones. Bucket 5 (pct 30.0) IS
      the series' own observed peak after despike, so it must now render at
      `SPARK_GLYPHS[len(SPARK_GLYPHS) - 1]` (the top row), not at
      `round(30.0/100.0*7)` (level 2, the old plateau-causing value). Bucket 0 (pct 10.0)
      scales relative to that SAME peak: `SPARK_GLYPHS[round(10.0/30.0*(len(SPARK_GLYPHS)-1))]`.
    - `cum_trend_axis(_cum_recs, now_bt)` returns 8 ticks; index 0 (top) reads "30%",
      index 3 (middle, row `rows//2`) reads `"%d%%" % round(30.0*4/7)` = "17%", and the
      last index (floor) is a bare "0" -- exactly three non-blank ticks, mirroring
      trend_axis's own `{top, rows//2, 0}` convention.
    - `build_cum_trend([], now_bt)` and `cum_trend_axis([], now_bt)` are both None;
      `build_cum_trend(_no_reset, now_bt)` and `cum_trend_axis(_no_reset, now_bt)` are
      both None (collecting state, no numeric reset).
    - A NEW, separate regression case pins the bucket-vs-series discriminator: three
      records -- bucket 0 (pct 10.0), bucket 5 (pct 30.0, the real in-range peak), and a
      THIRD record whose `t` equals the reset epoch itself (`t == _cr`) with pct 50.0.
      That third sample's bucket index is `WIN5 // CUM_TREND_INTERVAL` exactly (i.e.
      `== columns`, one past the last valid index), so despike KEEPS it (rise 20 from
      the ref of 30 is within RISE_MAX) but it must never be written into `buckets` and
      must NOT become the peak either function scales against: `build_cum_trend` must
      still put bucket 5 at the top row, and `cum_trend_axis`'s top tick must still read
      "30%", not "50%".
    - `CUM_TREND_AXIS` is removed from the `from .core import (...)` list; `cum_trend_axis`
      is imported in its place.
  </behavior>
  <action>
    In claude_monitor/core.py:

    1. Delete the `CUM_TREND_AXIS` comment block and constant entirely (the "Fixed
       y-axis for the cum_trend graph..." comment plus `CUM_TREND_AXIS = ["100%", "",
       "", "57%", "", "", "", "0"]`), leaving a single blank line before `def
       with_gaps`. Do not touch the `CUM_TREND_INTERVAL` comment/constant immediately
       above it.

    2. In `build_cum_trend`: rewrite the docstring's closing paragraph ("Scaled against
       a FIXED 0..100% ceiling, unlike trend_sparkline's peak-relative scale...") to
       instead say it scales against the series' own observed peak, exactly like
       `trend_sparkline` does for `hourly_tokens` -- NOT a fixed ceiling. Note this
       REVERSES 260727-krn's original "comparable window over window" rationale: a
       %-of-window bar pinned to a fixed 100 only ever lights the bottom 2-3 of 8 rows
       at a realistic ~20-30% usage level, which reads as a flat plateau rather than a
       trend -- the exact failure `trend_sparkline`'s own docstring already explains its
       own-peak scale avoids. Mention `cum_trend_axis` (defined immediately below) as
       the matching y-axis.

    3. Still in `build_cum_trend`, replace the final glyph-computation block (the `top =
       len(SPARK_GLYPHS) - 1` line through the `chars = [...]` list comprehension) with
       the THREE-WAY branch `trend_sparkline` already uses: compute `hi` as the maximum
       of `max(0.0, v)` over every non-None entry in `buckets` (NOT the raw despiked
       `series` -- a sample whose bucket index falls outside `[0, columns)` must not
       count toward the peak, since it never gets a bar). If `hi is None` (buckets is
       entirely empty, defensive/practically unreachable given the earlier `if not
       series: return None` guard, but matches `trend_sparkline`'s own equally
       unreachable guard), `chars` is `[SPARK_GAP] * columns`. If `hi == 0`, every
       non-None bucket renders at `SPARK_GLYPHS[0]` (the floor) and every None bucket
       stays `SPARK_GAP` -- nothing burned, but the sample still exists. Otherwise, each
       non-None bucket `v` renders at `SPARK_GLYPHS[round(max(0.0, v) / hi * top)]`, and
       None stays `SPARK_GAP`. Drop the old `min(100.0, ...)` upper clamp entirely --
       there is no fixed ceiling left to clamp against; keep the `max(0.0, ...)` floor
       clamp (defensive against a negative garbage value, unrelated to this change).

    4. Immediately after `build_cum_trend` (same relative position `trend_axis` sits
       right after `trend_sparkline`), add a new `cum_trend_axis(records, now)`
       function. Docstring: y-axis tick labels for the cum_trend graph, one per row, TOP
       ROW FIRST, None without data -- the same convention `trend_axis` and
       `build_cum_trend` already share. Scales against the SAME bucket-derived peak
       `build_cum_trend` computes (not the raw despiked series, for the exact
       stale-sample reason above) -- reverses 260727-krn's fixed-ceiling design for the
       same reason `build_cum_trend`'s own docstring now gives. Recomputes the
       windowed/despiked/bucketed series independently of `build_cum_trend` -- add a
       short `ponytail:` comment noting this duplicates `build_cum_trend`'s bucket-fill
       loop rather than sharing state, the SAME duplication `trend_axis` already accepts
       for `hourly_tokens` instead of sharing state with `trend_sparkline`; a shared
       helper is the upgrade path only if a third consumer ever needs this exact shape.
       A tick is a bare `"NN%"` (no tokens to ride alongside, unlike `trend_axis`'s
       "tokens/share" label -- the series already IS a percentage); the floor is a bare
       `"0"`, matching `trend_axis`'s own floor convention.

       Body: call `history_numeric(records)`; return `None` if empty. Find `newest =
       max(records, key=lambda r: r["t"])`; return `None` if `newest.get("reset")` is
       not numeric (via the existing `_is_num` helper, same guard `build_cum_trend`
       uses). Compute `start = newest["reset"] - WIN5` and `columns = WIN5 //
       CUM_TREND_INTERVAL`. Build `series = despike([[r["t"], r["pct"]] for r in
       records if r["t"] >= start])`; return `None` if empty. Fill `buckets = [None] *
       columns`, iterating `series` and writing `buckets[idx] = pct` only when `0 <= idx
       < columns` (idx computed the identical way `build_cum_trend` computes it) --
       THIS is the step that must be duplicated from `build_cum_trend`, not skipped, so
       an out-of-range sample is excluded from the peak the same way it is excluded from
       the sparkline. Compute `hi = max((max(0.0, v) for v in buckets if v is not
       None), default=None)`; return `None` if `hi` is `None` (nothing will render, so
       nothing to label). Then `rows = len(SPARK_GLYPHS)`, `top = rows - 1`, `ticked =
       {top, rows // 2, 0}`, and a `label(row)` closure: `""` if `row not in ticked`;
       bare `"0"` if `row == 0`; otherwise `"%d%%" % round(hi * row / top)`. Return
       `[label(row) for row in reversed(range(rows))]`.

    In claude-monitor.py:

    5. Update the comment on `self.cum_trend_axis = None` in `Monitor.__init__` (~line
       75) from "cached fixed y-axis for cum_trend" to "cached y-axis for cum_trend
       (autoscaled to the window's own observed peak)".

    6. In `compute_trends` (~line 391), change `self.cum_trend_axis = core.CUM_TREND_AXIS
       if self.cum_trend else None` to `self.cum_trend_axis = core.cum_trend_axis(records,
       now)` -- a direct call, no conditional wrapper, exactly mirroring the
       `self.trend_axis = core.trend_axis(records, now)` line immediately above it. The
       function itself returns `None` in the collecting-state case; the caller does not
       need to know why.

    In claude_monitor/test_claude_monitor.py:

    7. In the `from .core import (...)` list (~line 39), replace `CUM_TREND_AXIS,` with
       `cum_trend_axis,` at the same position.

    8. In the cumulative-window-trend assert block (~lines 619-642): leave the `_cr`,
       `_cstart`, and `_cum_recs` wire data completely unchanged. Change
       `_cum[0][0]`'s expected value from `SPARK_GLYPHS[round(10.0 / 100.0 *
       (len(SPARK_GLYPHS) - 1))]` to `SPARK_GLYPHS[round(10.0 / 30.0 *
       (len(SPARK_GLYPHS) - 1))]` (peak is now 30.0, the actual observed bucket-5
       value, not a fixed 100). Change `_cum[0][5]`'s expected value from
       `SPARK_GLYPHS[round(30.0 / 100.0 * (len(SPARK_GLYPHS) - 1))]` to
       `SPARK_GLYPHS[len(SPARK_GLYPHS) - 1]` (the peak bucket now reaches the top row).
       Leave the `_cum[0][10]`, `_cum[0][2]`, and `_cum[1]` (text row) assertions
       exactly as they are. Replace the trailing `assert CUM_TREND_AXIS == [...]` and
       `assert len(CUM_TREND_AXIS) == len(SPARK_GLYPHS)` lines with: `_axis =
       cum_trend_axis(_cum_recs, now_bt)`; `assert _axis is not None and len(_axis) ==
       len(SPARK_GLYPHS)`; `assert _axis[0] == "30%"`; `assert _axis[3] == "%d%%" %
       round(30.0 * 4 / 7)`; `assert _axis[-1] == "0"`; `assert [t for t in _axis if t]
       == [_axis[0], _axis[3], _axis[-1]]` (exactly three ticks). Also add `assert
       build_cum_trend([], now_bt) is None` and `assert cum_trend_axis([], now_bt) is
       None` together near the top of the block (both already-empty-input cases), and
       likewise pair `build_cum_trend(_no_reset, now_bt) is None` with `cum_trend_axis(
       _no_reset, now_bt) is None`.

    9. Immediately after that block, add the bucket-vs-series discriminator case
       described in `<behavior>`: a fresh `_stale_recs` list (bucket 0 pct 10.0, bucket 5
       pct 30.0, and a third record with `"t": _cr, "pct": 50.0, "reset": _cr` -- its
       bucket index is exactly `columns`, one past the valid range). Assert
       `build_cum_trend(_stale_recs, now_bt)[0][5] == SPARK_GLYPHS[len(SPARK_GLYPHS) -
       1]` (bucket 5, the real in-range peak, still reaches the top row) and
       `cum_trend_axis(_stale_recs, now_bt)[0] == "30%"` (the out-of-range pct 50.0
       sample must not become the peak either function scales against).

    Style: codedoc block comments, ASCII only, no new imports, no new dependency, no
    config knob.
  </action>
  <verify>
    <automated>just selfcheck</automated>
  </verify>
  <done>`just selfcheck` exits 0; `build_cum_trend`'s own observed peak bucket renders at
  the top row instead of a fixed-100-relative low level; `cum_trend_axis` returns ticks
  derived from that same peak; the bucket-vs-series discriminator case proves an
  out-of-range sample cannot inflate either the sparkline or the axis past what actually
  renders; `CUM_TREND_AXIS` no longer exists anywhere in the module.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Keep the newest columns when the cum_trend sparkline is wider than the panel (Rust)</name>
  <files>rust/src/main.rs, fixtures/generate.py, fixtures/snapshot/cum-trend-clipped-keeps-newest.json, fixtures/snapshot/cum-trend-populated.json, fixtures/README.md</files>
  <behavior>
    New/updated #[test] coverage in rust/src/main.rs's test module:
    - The existing local `render_trends_rows` closure inside
      `cum_trend_adds_a_second_graph_below_the_hourly_bars` becomes a shared, module-level
      `fn render_trends_rows(app: &App, width: u16) -> Vec<String>` (identical body,
      `TestBackend::new(width, 40)`); both of that test's existing call sites pass `60`
      explicitly and its assertions are otherwise unchanged.
    - A NEW test, `cum_trend_sparkline_clipping_keeps_the_newest_columns_not_the_oldest`:
      renders a wire payload whose `cum_trend[0]` is a 60-character sparkline climbing
      from level 0 to level 7 in 8-column blocks (level 7 reachable ONLY by its last 4
      characters) at a width (40) deliberately narrower than the sparkline plus any axis
      gutter, so clipping is forced. Asserts the cum_trend graph's TOP row (level 7,
      drawn first) has BETWEEN 1 AND 4 filled block-glyph cells -- proof the clip kept
      the TAIL (newest, high-level columns), since the pre-fix right-truncating
      behavior would show 0 filled cells there (the tail is exactly what gets dropped
      when truncating from the right).
    - The pre-existing `cum_trend_adds_a_second_graph_below_the_hourly_bars` and
      `cum_trend_absent_is_a_true_no_op_on_render_and_layout` tests pass unchanged: the
      first uses a 2-character `cum_trend` (never wide enough to clip at width 60), and
      the second never reaches the clip path at all (cum_trend absent).
    - `fixtures/generate.py` gains `F["cum-trend-clipped-keeps-newest"]`, a permanent
      corpus fixture carrying the SAME 60-character climbing sparkline (for `just
      rust-fixture cum-trend-clipped-keeps-newest` / `just rust-states` manual review),
      asserted via the existing `check_trends`/`check_axis` machinery (no fixtures.rs
      changes needed -- pure pass-through, no hostile characters to sanitize).
  </behavior>
  <action>
    In rust/src/main.rs (production code):

    1. Restructure `draw_trends` (~lines 903-956). Immediately after `let heatmap =
       snapshot_heatmap(app);`, compute `let fits_beside_heatmap = heatmap.is_some() &&
       inner.width > HEATMAP_WIDTH + 12;` (the exact condition the final match guard
       already uses) and `let columns = Layout::default().direction(
       Direction::Horizontal).constraints([Constraint::Min(10),
       Constraint::Length(HEATMAP_WIDTH)]).split(inner);` -- moved up from inside the
       match arm to BEFORE either graph is built, so its result is available for the
       clip below. Then `let graph_width = if fits_beside_heatmap { columns[0].width }
       else { inner.width };` -- this is the ACTUAL width the graphs Paragraph will
       render into later in this same function call, not an independently re-derived
       `inner.width - HEATMAP_WIDTH` calculation that could silently drift out of sync
       with it.

       Build the first (`trend_graph_lines(trends, ...)`) graph exactly as today. In the
       `if let Some(cum) = snapshot_cum_trend(app)` block: change the "window usage
       (0-100%)" label text to just "window usage" (the parenthetical is no longer
       accurate once the scale is peak-relative, not 0-100 -- all three existing
       `.contains("window usage")` test assertions match a substring, so this suffix
       change does not break them; confirm all three call sites still use `.contains`,
       not an exact `==`, before editing). Bind `let cum_axis =
       app.snapshot.as_ref().and_then(|s| s.cum_trend_axis.as_deref());` (unchanged),
       then change the `trend_graph_lines(cum, cum_axis)` call to
       `trend_graph_lines(&clip_to_newest(cum, cum_axis, graph_width), cum_axis)`.

       At the end of the function, the `match heatmap { Some(levels) if
       inner.width > HEATMAP_WIDTH + 12 => {...} _ => {...} }` block's guard becomes
       `if fits_beside_heatmap` (reusing the bool computed above instead of
       recomputing the condition) and its body renders into the ALREADY-COMPUTED
       `columns[0]`/`columns[1]` (no second `Layout::split` call inside the match).

    2. Add a new function `clip_to_newest(rows: &[String], axis: Option<&[String]>,
       panel_width: u16) -> Vec<String>` near `draw_trends` (e.g. immediately below
       it). Doc comment: the cum_trend sparkline (row 0) can be up to 60 characters
       wide; a `Paragraph` with no `.wrap()` drops whatever does not fit, and because
       columns run oldest-left / newest-right (`build_cum_trend` appends buckets in
       time order), an unclipped drop silently hides the most RECENT data while stale
       history stays on screen. Keep the LAST `budget` characters instead -- the newest
       columns -- dropping the FIRST ones. Only row 0 is glyph columns; any further
       rows are the already-short text line(s) and pass through untouched.
       `trend_graph_lines` itself stays unmodified (still shared with the untouched
       hourly chart), so the axis-gutter width it will reserve is recomputed here with
       the IDENTICAL formula that function uses internally (widest tick's `.chars()
       .count()` plus 1, or 0 with no axis) -- duplicated deliberately rather than
       shared, to avoid coupling this call site to that function's internals.

       Body: compute `let gutter = axis.map(|ticks| ticks.iter().map(|t|
       t.chars().count()).max().unwrap_or(0) + 1).unwrap_or(0);` (byte-for-byte the same
       expression `trend_graph_lines` computes for its own `axis_width`). Compute `let
       budget = (panel_width as usize).saturating_sub(gutter);`. Clone `rows` into an
       owned `Vec<String>`. If the first element's `.chars().count()` exceeds `budget`,
       replace it with `sparkline.chars().skip(len - budget).collect()` -- slicing by
       CHAR count, never byte index, since the sparkline may contain multi-byte
       Unicode block glyphs. Return the (possibly-modified) owned vec.

    In rust/src/main.rs (test module):

    3. Hoist the local `render_trends_rows` closure out of
       `cum_trend_adds_a_second_graph_below_the_hourly_bars` into a module-level `fn
       render_trends_rows(app: &App, width: u16) -> Vec<String>` (place it near
       `buffer_text`, ~line 1349), identical body to the closure it replaces
       (`TestBackend::new(width, 40)`, chunked by `width`). Update both existing call
       sites inside that test to `render_trends_rows(&app_with, 60)` and
       `render_trends_rows(&app_without, 60)` -- behavior and all existing assertions in
       that test are unchanged.

    4. Add the new test described in `<behavior>`. Use the literal 60-character
       climbing string `"\u{2581}\u{2581}\u{2581}\u{2581}\u{2581}\u{2581}\u{2581}\u{2581}\u{2582}\u{2582}\u{2582}\u{2582}\u{2582}\u{2582}\u{2582}\u{2582}\u{2583}\u{2583}\u{2583}\u{2583}\u{2583}\u{2583}\u{2583}\u{2583}\u{2584}\u{2584}\u{2584}\u{2584}\u{2584}\u{2584}\u{2584}\u{2584}\u{2585}\u{2585}\u{2585}\u{2585}\u{2585}\u{2585}\u{2585}\u{2585}\u{2586}\u{2586}\u{2586}\u{2586}\u{2586}\u{2586}\u{2586}\u{2586}\u{2587}\u{2587}\u{2587}\u{2587}\u{2587}\u{2587}\u{2587}\u{2587}\u{2588}\u{2588}\u{2588}\u{2588}"`
       (already verified: exactly 60 chars, 8-column blocks per level 0..6, 4 columns at
       level 7) -- assert `.chars().count() == 60` as a guard against a transcription
       error. Build the wire JSON via `format!` with `trends: ["\u{2581}\u{2588}","today
       1M/hr"]` and `cum_trend: [<climb>, "now 28%  resets in 3h 34m"]` (no axis, so the
       gutter is 0 and the row-index math below is exact). Build the app via
       `sessions_app`. Render via `render_trends_rows(&app, 40)`.

       Row-index derivation (mirrors the SAME arithmetic the sibling
       `cum_trend_adds_a_second_graph_below_the_hourly_bars` test already uses and
       already passes): row 0 is the panel's top border; rows `1..=TREND_ROWS` are the
       hourly chart's 8 graph rows; the next `trends.len() - 1 = 1` row is its text row
       (`content_rows = TREND_ROWS + trends.len() - 1`, exactly the sibling test's own
       local); the next row is the "window usage" label; the row after THAT is the
       cum_trend graph's own TOP row (level 7, drawn first since `trend_graph_lines`
       iterates `(0..TREND_ROWS).rev()`) -- index `content_rows + 2`. Assert
       `rows[content_rows + 2].matches('\u{2588}').count()` is between 1 and 4 inclusive
       (there are only 4 level-7 characters in the whole string, so a count of exactly 0
       proves the clip kept the head instead of the tail). If this index is off by one
       when actually run, print `rows.join("\n")` once to locate the correct index
       empirically and hardcode it with a comment citing this derivation -- do not guess
       further.

    In fixtures/generate.py:

    5. Add `F["cum-trend-clipped-keeps-newest"]`: `"note"` explains this is a permanent
       regression asset for BOTH the visual autoscale check and the width-clip check --
       a 60-column sparkline climbing from level 0 to level 7 in 8-column blocks (level
       7 reachable only by its last 4 columns); at a narrow `just rust-fixture
       cum-trend-clipped-keeps-newest` terminal width the top row must still show filled
       cells, proving the clip kept the newest (rightmost) columns, not the oldest
       (leftmost). `"wire"`: `{"trends": ["▁█", "today 1M/hr"], "trend_axis":
       ["1M/8%", "", "", "500k/4%", "", "", "", "0"], "cum_trend": [<the same 60-char
       climbing string from step 4>, "now 28%  resets in 3h 34m"], "cum_trend_axis":
       ["28%", "", "", "16%", "", "", "", "0"]}`. `"expect"`: `{"trends": {"rows":
       ["▁█", "today 1M/hr"]}, "cum_trend": {"rows": [<same climbing string>,
       "now 28%  resets in 3h 34m"]}, "cum_trend_axis": {"ticks": ["28%", "", "", "16%",
       "", "", "", "0"]}}` -- verbatim pass-through, no hostile characters, so `rows`/
       `ticks` equal `wire` exactly.

    6. In `F["cum-trend-populated"]` (~lines 170-182), the wire/expect
       `cum_trend_axis` values `["100%", "", "", "57%", "", "", "", "0"]` no longer
       resemble anything the daemon can actually send (that shape was the fixed
       ceiling); change both to `["35%", "", "", "20%", "", "", "", "0"]` (an arbitrary
       but internally plausible peak-relative example -- `round(35*4/7) == 20`) so nothing
       here implies production still emits a fixed 100/57/0. Update the fixture's
       trailing `"note"` sentence from "...covers the fixed axis riding alongside a
       populated cum_trend, normalizing to the same 8-tick list Python's CUM_TREND_AXIS
       produces" to "...covers cum_trend_axis riding alongside a populated cum_trend,
       normalizing to whatever 8-tick list the daemon sends -- now autoscaled to the
       window's own observed peak rather than a fixed ceiling, so these exact values are
       illustrative, not pinned to a constant."

    7. Run `python3 fixtures/generate.py` to write/regenerate the corpus. Confirm with
       `git diff --stat fixtures/snapshot/` (plus `git status` for the new file) that
       ONLY `cum-trend-clipped-keeps-newest.json` (new) and `cum-trend-populated.json`
       (modified) changed.

    In fixtures/README.md:

    8. Update the `cum_trend_axis` row of the Expectations table (~line 47) from
       "fixed y-axis ticks (100%/57%/0), or 'absent'; mirrors trend_axis's shape but
       constant" to "y-axis ticks autoscaled to the cum_trend series' own observed
       peak, or 'absent'; same {top, middle, floor} shape as trend_axis -- no longer a
       fixed ceiling."
  </action>
  <verify>
    <automated>python3 fixtures/generate.py &amp;&amp; just rust-test &amp;&amp; just rust-lint</automated>
  </verify>
  <done>`cargo test` is green including the new clipping-keeps-newest test and the
  hoisted `render_trends_rows` helper's two unchanged call sites; `cargo clippy
  --all-targets -- -D warnings` is clean; `git diff --stat fixtures/snapshot/` plus
  `git status` show exactly the two intended fixture changes (one new, one modified).

  Additionally, run the ACTUAL rendered check (verified working in this exact sandbox
  during planning, not theoretical): from the repo root, `tmux new-session -d -s
  cum-check -x 55 -y 45 "just rust-fixture cum-trend-clipped-keeps-newest"`, then `sleep
  1`, then `tmux capture-pane -p -t cum-check`, then `tmux kill-session -t cum-check`.
  Confirm the captured pane shows the cum_trend graph's TOP one or two rows with
  visible filled glyphs at the panel's right edge (the newest, highest-level columns
  survived the clip) -- not an empty top half with bars only anchored at the left
  (which is what the pre-fix code showed when this exact fixture was rendered at this
  exact width during diagnosis). Also spot-check a wide render (`-x 150 -y 30`) shows
  the full unclipped climb from level 0 to level 7 with no truncation.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|--------------|
| daemon (core.py/claude-monitor.py) -> Rust client (main.rs) via `cum_trend`/`cum_trend_axis` wire keys | JSON values the Rust client must decode; values now vary window-to-window (peak-relative) instead of being drawn from one fixed set |
| cum_trend sparkline string -> `clip_to_newest`'s char-level slicing | an untrusted-origin `String` crossing into `.chars().skip(n).collect()` |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-mki-01 | Tampering | `cum_trend`/`cum_trend_axis` wire values (now window-relative) -> `normalize_trends`/`normalize_trend_axis` | low | mitigate | reuses the existing normalize path verbatim (no new parsing code, so no new attack surface); pinned by the `cum-trend-clipped-keeps-newest` fixture |
| T-mki-02 | Denial of Service | `clip_to_newest` char-slicing a hostile/oversized sparkline string | low | mitigate | slices by CHAR count (`.chars().skip/collect()`), never a byte index, so a malformed multi-byte glyph string cannot split on a non-UTF-8 boundary and panic; `budget` is `saturating_sub`-clamped, never negative |
| T-mki-03 | Information Disclosure | cum_trend_axis's percentages are the daemon's own usage %, already present elsewhere on the same snapshot | low | accept | no new information crosses the trust boundary that was not already present in cum_trend's own text row |
| T-mki-SC | Tampering | npm/pip/cargo installs | low | accept | no new dependency is added by this task |
</threat_model>

<verification>
- `just selfcheck` exits 0 (Task 1's gate: peak-relative scaling, `cum_trend_axis`
  function, bucket-vs-series discriminator).
- `python3 fixtures/generate.py` then `just rust-test` and `just rust-lint` green
  (Task 2's gate: clipping-keeps-newest test, hoisted render helper, fixture corpus).
- `git diff --stat fixtures/snapshot/` plus `git status` show exactly the two intended
  fixture changes.
- Live tmux-captured render of `cum-trend-clipped-keeps-newest` at a narrow width shows
  the top rows filled (newest data visible), not blank (see Task 2 `<done>`).
</verification>

<success_criteria>
- The cum_trend graph's own observed peak reaches the top row instead of being pinned
  low by a fixed 100% ceiling -- it reads as a trend, not a flat plateau, at realistic
  usage levels.
- The cum_trend graph's y-axis ticks always describe the bars actually drawn above
  them (autoscaled to the same peak), never a fixed 100%/57%/0.
- At a narrow terminal width, the cum_trend sparkline keeps its newest (rightmost)
  columns and drops its oldest (leftmost) ones, never the reverse.
- The original hourly bar chart and its cadence constants (TREND_INTERVAL,
  CUM_TREND_INTERVAL) are untouched.
- No new dependency, no new poll, no new config surface.
- The 260727-krn fixed-ceiling design reversal is explicitly disclosed in the
  SUMMARY and the STATE.md quick-task row.
</success_criteria>

<output>
Create `.planning/workstreams/notifications-predictive-alerts/quick/260727-mki-autoscale-cum-trend-graph-to-observed-pe/260727-mki-SUMMARY.md` when done
</output>
