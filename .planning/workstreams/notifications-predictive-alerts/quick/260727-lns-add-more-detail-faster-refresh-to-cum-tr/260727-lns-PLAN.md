---
phase: 260727-lns
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - claude-monitor.py
  - claude_monitor/core.py
  - claude_monitor/test_claude_monitor.py
  - rust/src/snapshot.rs
  - rust/src/main.rs
  - rust/tests/fixtures.rs
  - fixtures/generate.py
  - fixtures/snapshot/cold-start-null-sections.json
  - fixtures/snapshot/cum-trend-populated.json
  - fixtures/README.md
autonomous: true
requirements: [QT-260727-lns]

must_haves:
  truths:
    - "The whole trends panel (the hourly bar chart AND the cum_trend graph) recomputes once per minute instead of once per five minutes, because TREND_INTERVAL gates both from the same poll_loop call -- POLL_INTERVAL (socket/usage polling) is untouched."
    - "The cum_trend sparkline buckets usage every 5 minutes (60 columns across the 5h window) instead of every 15 minutes (20 columns), so a new column becomes visible roughly every 5 daemon recomputes at the new cadence."
    - "Directly under the cum_trend sparkline, a text line reads 'now NN%  resets in Xh Ym' (or 'resets now'), computed from the newest record's own pct/reset and reusing fmt_countdown verbatim -- giving the current-window percentage and time-to-reset at a glance, the same way the hourly chart already has its own text row below its bars."
    - "The cum_trend graph has a fixed y-axis, ticked at 100% (top), 57% (middle), and 0 (floor) -- the SAME {top, rows//2, floor} tick convention core.trend_axis() already documents and uses for the hourly chart, but expressed as a constant list since this ceiling never varies (unlike trend_axis's locally-observed peak)."
    - "Both pre-existing safety guarantees are unchanged: a malformed/absent cum_trend or cum_trend_axis degrades only the second graph, never usage/heatmap/sessions/the first graph (D-02); no new dependency, no new poll, no new config knob is introduced by any of these four changes."
  artifacts:
    - claude-monitor.py
    - claude_monitor/core.py
    - claude_monitor/test_claude_monitor.py
    - rust/src/snapshot.rs
    - rust/src/main.rs
    - rust/tests/fixtures.rs
    - fixtures/generate.py
    - fixtures/README.md
  key_links:
    - "TREND_INTERVAL (claude-monitor.py poll_loop) is the single gate for BOTH of Monitor.compute_trends()'s outputs (build_trend_rows AND build_cum_trend) -- dropping it from 300s to 60s speeds up the whole trends panel in one place, not two."
    - "core.build_cum_trend(records, now) now returns [sparkline, text] instead of [sparkline] -> Monitor.compute_trends caches both mon.cum_trend (unchanged wire key, no Rust change needed for the text row -- trend_graph_lines already renders trends[1..] verbatim) and the new mon.cum_trend_axis -> _handle_conn's snapshot dict passthrough -> rust Snapshot::from_value's normalize_trend_axis(obj.get('cum_trend_axis')) (REUSED verbatim, the exact function trend_axis already normalizes through) -> Snapshot.cum_trend_axis -> draw_trends's second trend_graph_lines(cum, ...) call, now passed the real axis instead of a hardcoded None."
    - "CUM_TREND_AXIS is a plain module-level constant, not a function like trend_axis(), because its ceiling (100) never varies -- nothing is left to observe or recompute at render time."
---

<objective>
Speed up and enrich the Rust TUI's cumulative-window-usage graph (added by quick task
260727-krn): recompute the whole trends panel every minute instead of every five, bucket
the cum_trend sparkline every 5 minutes instead of every 15, append an inline
"now NN%  resets in Xh Ym" text row under it, and give it a fixed 100/57/0 y-axis matching
the hourly chart's tick convention.

Purpose: the cum_trend graph currently updates too slowly to feel "live" and carries no
axis or point-in-time readout, so a user has to eyeball glyph height against nothing. All
four gaps close by tightening one existing constant, reusing one existing helper
(fmt_countdown), and mirroring one existing pattern (trend_axis) end to end -- no new
dependency, no new poll, no new config knob.

Output: claude-monitor.py polls trends at 60s; core.build_cum_trend returns a two-row
list (sparkline + text); a new core.CUM_TREND_AXIS constant rides the wire as
cum_trend_axis, normalized in Rust by the existing normalize_trend_axis and rendered by
the existing trend_graph_lines, exactly as trend_axis already is for the first graph.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/workstreams/notifications-predictive-alerts/STATE.md

# Regions to read before editing (do NOT re-read a range already seen):
@claude-monitor.py              # TREND_INTERVAL line 55 (POLL_INTERVAL line 42 is separate, do not touch); Monitor.__init__ trend-cache fields ~72-76; compute_trends ~379-390; _handle_conn snapshot dict ~662-677
@claude_monitor/core.py         # WIN5/WIN7 ~238-239; SPARK_GLYPHS ~310; fmt_countdown ~477-482 (reuse verbatim); GAP_MAX/RISE_MAX ~995-1002; CUM_TREND_INTERVAL comment+const ~1004-1007; build_cum_trend ~1048-1083; trend_axis ~701-743 (the tick convention CUM_TREND_AXIS mirrors, do not modify this function); tui_usage_rows' own fmt_countdown(reset - now) call ~1347 (the exact pattern to reuse)
@claude_monitor/test_claude_monitor.py  # import list ~18-93; cumulative-window-trend assert block ~618-636; socket-wire _FakeMonitor test ~1061-1099
@rust/src/snapshot.rs           # wire-contract doc ~36-46; struct Snapshot ~246-266; Snapshot::from_value ~280-299; normalize_trends ~444-462; normalize_trend_axis ~464-478 (REUSE this verbatim, do not add a second one)
@rust/src/main.rs               # TREND_ROWS ~67; trend_graph_lines call sites in draw_trends ~919-931 (the first call already passes trend_axis; mirror it for the second call, currently passed None); trends_panel_height ~781-794 (already accounts for cum.len().saturating_sub(1) -- no change needed here)
@rust/tests/fixtures.rs         # check() match arms ~140-151; check_trends ~236-257 (the pattern to mirror for a new check_axis helper, since cum_trend_axis is Option<Vec<String>>, not Section<T>)
@fixtures/generate.py           # F["cold-start-null-sections"] ~50-59; F["cum-trend-populated"] ~170-178; write loop ~259-265
@fixtures/README.md             # Expectations table ~42-48

Reuse, do NOT reimplement:
- core.fmt_countdown             -> already produces "resets in Xh Ym" / "resets now"; used verbatim for the new text row, same as tui_usage_rows already does
- core.trend_axis's tick convention (rows = len(SPARK_GLYPHS) = 8, ticked = {top, rows//2, 0}) -> CUM_TREND_AXIS is the same shape, precomputed as a constant because its ceiling never varies
- rust normalize_trend_axis       -> reused verbatim for the new "cum_trend_axis" wire key, identical to how trend_axis is normalized
- rust trend_graph_lines          -> unmodified; already renders any Vec<String> length >= 1 and any Option<&[String]> axis
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Faster refresh, inline countdown text, and a fixed axis constant (Python)</name>
  <files>claude-monitor.py, claude_monitor/core.py, claude_monitor/test_claude_monitor.py</files>
  <behavior>
    New/updated asserts in test_claude_monitor.demo (assert style, no pytest):
    - The two hardcoded `900 * 5` / `900 * 10` sample offsets in the cumulative-window-trend
      block become `CUM_TREND_INTERVAL * 5` / `CUM_TREND_INTERVAL * 10`, so the test still
      places samples in buckets 5 and 10 regardless of the interval's value.
    - `build_cum_trend(_cum_recs, now_bt)` now returns a TWO-element list (was one); the
      sparkline-shape assertions (`_cum[0][...]`) are unchanged, and a new assertion checks
      `_cum[1]` equals `"now %d%%  %s" % (round(30.0 + RISE_MAX + 1), fmt_countdown(_cr -
      now_bt))` -- `30.0 + RISE_MAX + 1` is the newest record's raw (non-despiked) pct,
      derived from `RISE_MAX` (already imported) rather than its numeric value hardcoded,
      proving the text row reads the newest sample independent of whether despike()
      dropped its own bucket from the sparkline.
    - `CUM_TREND_AXIS == ["100%", "", "", "57%", "", "", "", "0"]` and
      `len(CUM_TREND_AXIS) == len(SPARK_GLYPHS)`.
    - The socket-wire `_FakeMonitor` test gains `self.cum_trend_axis` on the fake,
      `"cum_trend_axis"` in the `set(_snapshot.keys())` assertion, and
      `assert _snapshot["cum_trend_axis"] == _mon.cum_trend_axis`.
  </behavior>
  <action>
    In claude-monitor.py:

    1. Change `TREND_INTERVAL = 5 * 60` (line ~55) to `TREND_INTERVAL = 60`, updating the
       trailing comment to say "1 minute". Do not touch POLL_INTERVAL (line ~42, default
       15s) -- it gates usage polling, not trend recompute, and is unrelated to this change.

    2. In Monitor.__init__ (~line 74), add `self.cum_trend_axis = None  # cached fixed
       y-axis for cum_trend, or None (collecting state)` immediately after the existing
       `self.cum_trend = None` line.

    3. In compute_trends (~line 389), immediately after the existing
       `self.cum_trend = core.build_cum_trend(records, now)` line, add
       `self.cum_trend_axis = core.CUM_TREND_AXIS if self.cum_trend else None` -- same
       collecting-state convention self.trend_axis/self.cum_trend already share: the axis
       never appears without data.

    4. In _handle_conn's snapshot dict (~line 674), add `"cum_trend_axis":
       mon.cum_trend_axis,` immediately after the existing `"cum_trend": mon.cum_trend,`
       entry.

    In claude_monitor/core.py:

    5. Update the ponytail comment above CUM_TREND_INTERVAL (~lines 1004-1006): change
       "fixed 15-minute sampling interval" to "fixed 5-minute sampling interval" and
       "WIN5 // CUM_TREND_INTERVAL == 20 columns" to "== 60 columns". Change
       `CUM_TREND_INTERVAL = 900  # seconds; 15 minutes` to
       `CUM_TREND_INTERVAL = 300  # seconds; 5 minutes`.

    6. Immediately after the CUM_TREND_INTERVAL definition (before `def with_gaps`), add
       the module-level constant `CUM_TREND_AXIS = ["100%", "", "", "57%", "", "", "",
       "0"]`, with a comment explaining: ticks at rows {7, 4, 0} (top/middle/floor), the
       exact convention trend_axis() documents and uses (rows = len(SPARK_GLYPHS) == 8,
       ticked = {top, rows // 2, 0}); 57% is round(100 * 4 / 7), the honest value for row 4
       -- do not write "50%", which would mislabel which row is drawn where, exactly the
       mislabeling trend_axis's own docstring says it avoids. Note this is a plain
       constant rather than a function like trend_axis(), because the ceiling here is a
       FIXED 100, never a locally observed peak, so there is nothing to recompute at
       render time.

    7. In build_cum_trend (~lines 1048-1083): update the docstring's opening line from
       "One-element Section<Vec<String>> row" to "Two-element Section<Vec<String>> row:
       [sparkline, text]", adding a sentence describing the appended text row (reads the
       newest record's own pct/reset via fmt_countdown, the same pattern tui_usage_rows'
       own `fmt_countdown(reset - now)` call already uses). Change the final
       `return ["".join(chars)]` to first compute `pct = max(0.0, min(100.0,
       newest["pct"]))` (the identical clamp already applied per-bucket above, applied
       here to the newest record's own pct) and `text = "now %d%%  %s" % (round(pct),
       fmt_countdown(newest["reset"] - now))`, then `return ["".join(chars), text]`.
       Reuse fmt_countdown verbatim -- do not reimplement countdown formatting.

    In claude_monitor/test_claude_monitor.py:

    8. Add `CUM_TREND_AXIS,` to the `from .core import (...)` list (~line 39), next to the
       existing `CUM_TREND_INTERVAL,` entry.

    9. In the cumulative-window-trend assert block (~lines 618-636): replace both literal
       `900 * 5` and `900 * 10` sample-offset expressions with `CUM_TREND_INTERVAL * 5`
       and `CUM_TREND_INTERVAL * 10` (self-documenting against future interval changes,
       matching the existing `len(_cum[0]) == WIN5 // CUM_TREND_INTERVAL` assertion's
       style). Change `assert _cum is not None and len(_cum) == 1` to `== 2`. After the
       existing sparkline-shape assertions, add `assert _cum[1] == "now 56%  %s" %
       fmt_countdown(_cr - now_bt)`. After that, add
       `assert CUM_TREND_AXIS == ["100%", "", "", "57%", "", "", "", "0"]` and
       `assert len(CUM_TREND_AXIS) == len(SPARK_GLYPHS)`.

    10. In the socket-wire-protocol test block (~lines 1061-1099): add
        `self.cum_trend_axis = ["100%", "", "", "57%", "", "", "", "0"]` to
        `_FakeMonitor.__init__`, next to `self.cum_trend = ["cum1"]`; add
        `"cum_trend_axis"` to the `set(_snapshot.keys())` tuple; add
        `assert _snapshot["cum_trend_axis"] == _mon.cum_trend_axis` next to the existing
        `_snapshot["cum_trend"]` assertion.

    Style: codedoc block comments, ASCII only, no new imports, no new dependency, no
    config knob for either interval.
  </action>
  <verify>
    <automated>just selfcheck</automated>
  </verify>
  <done>`just selfcheck` exits 0; build_cum_trend returns a two-element list end to end
  with the new text row content verified; CUM_TREND_AXIS matches the exact 8-string shape
  Rust's normalize_trend_axis expects.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire cum_trend_axis into the Rust client and fixture corpus</name>
  <files>rust/src/snapshot.rs, rust/src/main.rs, rust/tests/fixtures.rs, fixtures/generate.py, fixtures/snapshot/cold-start-null-sections.json, fixtures/snapshot/cum-trend-populated.json, fixtures/README.md</files>
  <behavior>
    New/updated #[test] coverage:
    - fixtures.rs's shared corpus runner gains a "cum_trend_axis" expectation key, checked
      by a new `check_axis` helper against `Option<Vec<String>>` (there is no "malformed"
      state to assert here -- normalize_trend_axis collapses any bad shape straight to
      `None`, so only "absent" or a populated tick list are ever observable).
    - `cold-start-null-sections` gains a `cum_trend_axis: null` -> "absent" pair, alongside
      the existing `cum_trend: null` -> "absent" case.
    - `cum-trend-populated` gains a `cum_trend_axis` wire value alongside its existing
      `cum_trend` rows, asserting the axis normalizes to the same 8-tick list Python's
      CUM_TREND_AXIS produces.
    - The existing `cum_trend_adds_a_second_graph_below_the_hourly_bars` and
      `cum_trend_absent_is_a_true_no_op_on_render_and_layout` main.rs tests (whose wire
      strings carry no `cum_trend_axis` key) still pass unchanged: normalize_trend_axis(None)
      still yields None there, so draw_trends's second graph renders exactly as before.
  </behavior>
  <action>
    In rust/src/snapshot.rs:

    1. Update the wire-contract doc comment (~lines 36-46): add
       `"cum_trend_axis": [string] | null` immediately after the existing
       `"cum_trend": [string] | null` line.

    2. Add `pub cum_trend_axis: Option<Vec<String>>,` to `struct Snapshot` (~line 263),
       immediately after `pub cum_trend: Section<Vec<String>>,`, with a doc comment: the
       cum_trend graph's fixed y-axis, mirroring trend_axis exactly (same
       Option<Vec<String>>, same normalize_trend_axis path) -- a missing axis costs
       labels on the SECOND graph only, never the graph itself.

    3. In `Snapshot::from_value` (~line 295), add `cum_trend_axis:
       normalize_trend_axis(obj.get("cum_trend_axis")),` immediately after the
       `cum_trend: normalize_trends(...)` line. Reuse the EXISTING `normalize_trend_axis`
       function verbatim -- do not add a second one.

    In rust/src/main.rs:

    4. In `draw_trends` (~line 931), change `graph.extend(trend_graph_lines(cum,
       None));` to `graph.extend(trend_graph_lines(cum, app.snapshot.as_ref().and_then(|s|
       s.cum_trend_axis.as_deref())));` -- mirrors exactly how the FIRST
       `trend_graph_lines` call (~line 921) already passes
       `app.snapshot.as_ref().and_then(|s| s.trend_axis.as_deref())`. Do not modify
       `trend_graph_lines` itself.

    In rust/tests/fixtures.rs:

    5. Add a new `check_axis(got: &Option<Vec<String>>, expected: &Value, name: &str) ->
       Result<(), String>` function (place it near `check_trends`, ~line 257): if
       `expected.as_str() == Some("absent")`, assert `got.is_none()` (error otherwise);
       else read `expected.get("ticks").and_then(Value::as_array)` as the wanted tick
       list and assert `got` is `Some` with the identical length and per-index string
       values, using the same positional-mismatch error style `check_trends` already
       uses. Add `"cum_trend_axis" => check_axis(&snapshot.cum_trend_axis, expected,
       "cum_trend_axis")?,` to `check()`'s match arms (~line 147), next to the existing
       `"cum_trend"` arm.

    In fixtures/generate.py:

    6. In `F["cold-start-null-sections"]` (~lines 50-59), add `"cum_trend_axis": None` to
       `wire` and `"cum_trend_axis": "absent"` to `expect`, alongside the existing
       `cum_trend` absent pair.

    7. In `F["cum-trend-populated"]` (~lines 170-178), add `"cum_trend_axis": ["100%", "",
       "", "57%", "", "", "", "0"]` to `wire` and `"cum_trend_axis": {"ticks": ["100%",
       "", "", "57%", "", "", "", "0"]}` to `expect`. Update the fixture's `note` to
       mention it now also covers the fixed axis riding alongside a populated cum_trend.

    8. Run `python3 fixtures/generate.py` to regenerate the corpus. Confirm with
       `git diff --stat fixtures/snapshot/` that ONLY `cold-start-null-sections.json` and
       `cum-trend-populated.json` changed.

    In fixtures/README.md:

    9. Add a `cum_trend_axis` row to the Expectations table (~lines 42-48):
       `{"ticks": ["..."]}` -- fixed y-axis ticks (100%/57%/0), or "absent"; mirrors
       trend_axis's shape but constant.
  </action>
  <verify>
    <automated>python3 fixtures/generate.py &amp;&amp; just rust-test &amp;&amp; just rust-lint</automated>
  </verify>
  <done>`cargo test` is green including the two new cum_trend_axis fixture assertions;
  `cargo clippy --all-targets -- -D warnings` is clean; `git diff --stat
  fixtures/snapshot/` shows exactly the two intended files changed; the pre-existing
  cum_trend render tests in main.rs still pass unchanged. Additionally: the 60-column
  sparkline (up from 24) needs roughly `60 + len("100%") + 1` = 65 terminal columns beside
  its gutter to render un-truncated, versus ~34 for the existing hourly chart -- `Paragraph`
  without `.wrap()` truncates the sparkline's right (newest) end first, since columns are
  oldest-left / newest-right. This is not a regression to fix (the 300s/60-column interval
  is a locked decision, and the hourly chart already clips below its own width), but check
  actual terminal width against `HEATMAP_WIDTH` (`grep -n "HEATMAP_WIDTH" rust/src/main.rs`)
  before closing this task, and report the observed width if the newest buckets clip in the
  normal (non-test) terminal, rather than silently shipping a graph missing its most recent
  data.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|--------------|
| daemon socket line -> Rust client | JSON the Rust client must decode wholesale; extended by one more optional key (`cum_trend_axis`) and one more row inside the existing `cum_trend` array |
| cum_trend text row -> terminal | daemon-built "now NN%  resets in Xh Ym" string reaching a real TTY via the existing `cum_trend` array |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-lns-01 | Tampering | "cum_trend_axis" wire key -> Rust normalize -> terminal | low | mitigate | reuses `normalize_trend_axis`'s existing sanitize/bound path verbatim (no new parsing code, so no new attack surface); pinned by the `cum-trend-populated` fixture's axis assertion (Task 2) |
| T-lns-02 | Tampering | new "now NN% ..." row inside "cum_trend" -> terminal | low | mitigate | crosses through the SAME `normalize_trends`/`sanitize_display` path every existing `cum_trend` row already crosses -- no new code, already covered by the existing hostile-controls-in-trend-rows fixture pattern |
| T-lns-03 | Denial of Service | malformed/absent cum_trend_axis blanking other sections | low | mitigate | `Option<Vec<String>>` (not `Section<T>`) independence: a bad axis costs only the second graph's labels, never the graph, the panel, or any other section; pinned by `cold-start-null-sections`'s absent case (Task 2) |
| T-lns-SC | Tampering | npm/pip/cargo installs | low | accept | no new dependency is added by this task |
</threat_model>

<verification>
- `just selfcheck` exits 0 (Task 1's gate: cadence, text row, and CUM_TREND_AXIS shape).
- `python3 fixtures/generate.py` then `just rust-test` and `just rust-lint` green (Task 2's
  gate: cum_trend_axis normalization + fixtures + clippy).
- `git diff --stat fixtures/snapshot/` shows exactly the two intended fixture files
  changed.
</verification>

<success_criteria>
- The trends panel (both graphs) recomputes every minute instead of every five.
- The cum_trend sparkline buckets every 5 minutes (60 columns) instead of 15 (20 columns).
- A "now NN%  resets in Xh Ym" text row appears under the cum_trend sparkline.
- The cum_trend graph shows a fixed 100% / 57% / 0 y-axis, matching the hourly chart's
  tick convention.
- No new dependency, no new poll, no new config surface.
</success_criteria>

<output>
Create `.planning/workstreams/notifications-predictive-alerts/quick/260727-lns-add-more-detail-faster-refresh-to-cum-tr/260727-lns-SUMMARY.md` when done
</output>
