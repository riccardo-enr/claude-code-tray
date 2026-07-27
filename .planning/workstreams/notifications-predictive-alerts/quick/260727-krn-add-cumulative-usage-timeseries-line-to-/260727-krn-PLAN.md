---
phase: 260727-krn
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - claude_monitor/core.py
  - claude-monitor.py
  - claude_monitor/test_claude_monitor.py
  - rust/src/snapshot.rs
  - rust/tests/fixtures.rs
  - fixtures/generate.py
  - fixtures/snapshot/cold-start-null-sections.json
  - fixtures/snapshot/partial-sections.json
  - fixtures/snapshot/cum-trend-populated.json
  - fixtures/README.md
  - rust/src/main.rs
autonomous: true
requirements: [QT-260727-krn]

must_haves:
  truths:
    - "The existing hourly tok/hr bar chart (trend_sparkline, trend_axis, trend_graph_lines, draw_trends) renders byte-identically to before this change whenever cum_trend has no data yet -- it is never replaced or restructured."
    - "A second sparkline appears below the bar chart, in the same trends panel, once at least one sample has landed inside the CURRENT rolling 5h quota window."
    - "The second sparkline is scaled against a FIXED 0..100% ceiling, not its own observed peak, so a bar's height always means the same thing window over window."
    - "The sparkline is anchored on the CURRENT window only: records timestamped before reset - WIN5 never contribute a column, so it can never show a stale prior window's shape."
    - "The known upstream pct=100 pin/spike bug cannot paint a false full column in the new graph -- despike() (already used by dashboard.py's HTML line chart) rejects it, reused rather than reimplemented."
    - "A malformed or absent cum_trend from an old or misbehaving daemon degrades ONLY the new second graph (it silently disappears) and never blanks usage, the existing trends rows, heatmap, or sessions (D-02 section independence)."
    - "No new runtime dependency, no new poll, no new config knob: the sampling interval is a hardcoded constant next to GAP_MAX/RISE_MAX."
  artifacts:
    - claude_monitor/core.py
    - claude-monitor.py
    - claude_monitor/test_claude_monitor.py
    - rust/src/snapshot.rs
    - rust/tests/fixtures.rs
    - fixtures/generate.py
    - fixtures/README.md
    - rust/src/main.rs
  key_links:
    - "core.build_cum_trend(records, now) -> Monitor.compute_trends -> mon.cum_trend -> _handle_conn snapshot['cum_trend'] (whole-dict wire passthrough, zero extra daemon plumbing needed) -> rust Snapshot::from_value's normalize_trends(obj.get('cum_trend')) -> Snapshot.cum_trend -> main.rs snapshot_cum_trend() -> draw_trends's SECOND trend_graph_lines call."
    - "despike() is the one shared RISE_MAX sanitizer: dashboard.py's HTML line chart and the new TUI sparkline both call it; no second despike implementation exists."
    - "rust normalize_trends is reused verbatim for both wire keys 'trends' and 'cum_trend' (identical Section<Vec<String>> shape) -- proven by generalizing fixtures.rs's check_trends helper, not by writing a new normalize_cum_trend."
---

<objective>
Add a second, independent sparkline to the Rust TUI's "trends" panel: cumulative usage
within the CURRENT rolling 5h quota window, sampled every 15 minutes. The existing hourly
tok/hr bar chart (trend_sparkline / trend_axis / trend_graph_lines / draw_trends) is left
completely untouched -- this is a new series rendered below it, not a modification of it.

Purpose: the existing chart answers "which hours were heavy"; this answers "how close am
I to exhausting the CURRENT window, right now" -- a different question the daemon already
has every input for (`pct` is already the CLI's own cumulative-within-window percentage;
no new data collection, just a new sampling/rendering path for data already on disk).

Output: one new Python helper (`core.build_cum_trend`) wired onto the existing daemon ->
socket -> Rust normalize -> Rust render pipeline exactly the way `trends`/`trend_axis`
already are, plus fixture corpus coverage for presence, absence, malformed input, and
hostile control characters.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/workstreams/notifications-predictive-alerts/STATE.md

# Regions to read before editing (do NOT re-read a range already seen):
@claude_monitor/core.py         # WIN5 ~238; SPARK_GLYPHS/SPARK_GAP ~310-311; history_numeric ~859-875; _is_num ~984-985; GAP_MAX/RISE_MAX ~995-1002; with_gaps ~1005-1016; despike ~1019-1041 (build_cum_trend goes right after this, before usage7_series)
@claude-monitor.py              # Monitor.__init__ trend-cache fields ~72-74; compute_trends ~378-388; _handle_conn snapshot dict ~660-673
@claude_monitor/test_claude_monitor.py  # import list ~18-91; trend-logic assert block ~472-615 (insert before "# --- dashboard logic ---" at ~616); socket-wire _FakeMonitor test ~1031-1090
@rust/src/snapshot.rs           # wire-contract doc ~36-46; struct Snapshot ~245-260; Snapshot::from_value ~274-292; normalize_trends ~437-455 (REUSE this verbatim, do not add a second one)
@rust/tests/fixtures.rs         # check() match arms ~140-148; check_trends ~235-256 (generalize to take a Section + name, not a whole Snapshot)
@fixtures/generate.py           # ESC/BEL constants ~14-17; F["cold-start-null-sections"] ~50-57; F["partial-sections"] ~68-79; write loop ~245-251
@fixtures/README.md             # Expectations table ~40-48
@rust/src/main.rs               # TREND_ROWS ~67; snapshot_trends ~757-762; snapshot_heatmap ~764-769; trends_panel_height ~771-780; trend_graph_lines ~792-842 (call again, do not modify); draw_trends ~889-929; existing render test ~1281-1320

Reuse, do NOT reimplement:
- core.history_numeric / core._is_num  -> the same numeric-sanitization gate every trend helper already uses
- core.despike                          -> the exact RISE_MAX spike rejection dashboard.py's HTML line chart already relies on
- core.SPARK_GLYPHS / core.SPARK_GAP    -> the same 8-level ramp and gap glyph trend_sparkline uses
- core.WIN5                             -> the 18000s window-length constant `project()` already anchors against
- rust snapshot::normalize_trends       -> array-of-strings normalization, identical shape for `trends` and `cum_trend`
- rust main::trend_graph_lines          -> the graph-drawing function itself; called a SECOND time, never edited
</context>

<tasks>

<task type="tracer" tdd="true">
  <name>Task 1: Daemon computes the cumulative-window sparkline and puts it on the wire</name>
  <files>claude_monitor/core.py, claude-monitor.py, claude_monitor/test_claude_monitor.py</files>
  <behavior>
    New asserts in test_claude_monitor.demo (assert style, no pytest, no fixtures), inserted
    right after the existing `assert hourly_pct(_rolled, _hour + 1200)[23] == 3.0` line and
    before "# --- dashboard logic ---":
    - build_cum_trend([], now) is None, and build_cum_trend([<a record with no numeric
      "reset">], now) is None -- same "collecting" convention build_trend_rows/trend_axis
      already use.
    - Given records inside a window (numeric "reset" present) spaced across a few
      CUM_TREND_INTERVAL-second buckets, build_cum_trend returns a ONE-element list whose
      string has length WIN5 // CUM_TREND_INTERVAL; the bucket holding the last (highest-t)
      sample reflects THAT sample's pct (last-sample-in-bucket wins, since pct is already
      cumulative -- no summing); an untouched bucket in between renders as SPARK_GAP.
    - A pct that spikes past the previous kept sample by more than RISE_MAX is rejected by
      despike() before bucketing, so that bucket stays a gap rather than painting near-full
      -- mirroring the exact scenario already asserted for heatmap_buckets/hourly_pct.
    - A record timestamped before `reset - WIN5` contributes no bucket at all.
    - The socket-wire end-to-end test (the _FakeMonitor / _handle_conn test around line
      ~1031) gains `self.cum_trend` on _FakeMonitor, "cum_trend" in the
      `set(_snapshot.keys())` assertion, and `assert _snapshot["cum_trend"] ==
      _mon.cum_trend`.
  </behavior>
  <action>
    In claude_monitor/core.py:

    1. Add `CUM_TREND_INTERVAL = 900` (seconds; 15 minutes -- WIN5 // CUM_TREND_INTERVAL ==
       20 columns) immediately after the RISE_MAX definition (~line 1002), next to
       GAP_MAX/RISE_MAX per the project's existing "fixed constant, not a config knob"
       convention. Add a one-line ponytail note: fixed constant deliberately, upgrade path
       is a config surface if a different interval is ever wanted, YAGNI until then.

    2. Add `build_cum_trend(records, now)` immediately after despike() (~line 1041), before
       usage7_series. Sanitize via history_numeric(records) first; return None if the
       result is empty or if the newest record's "reset" key is not numeric (_is_num) --
       the same "not enough to draw yet" convention build_trend_rows/trend_axis already
       use. Compute `start = reset - WIN5` from the newest record's reset and
       `columns = WIN5 // CUM_TREND_INTERVAL`. Build the windowed, despiked series as
       `despike([[r["t"], r["pct"]] for r in records if r["t"] >= start])` -- this is the
       exact same despike() call dashboard.py's render_dashboard already makes for the HTML
       line chart, reused verbatim so the same RISE_MAX spike rejection applies with no new
       logic. Return None if that list is empty. Walk it in order, computing
       `idx = int((t - start) // CUM_TREND_INTERVAL)` per point and, for 0 <= idx <
       columns, overwriting a `columns`-length buckets list at that index with the pct (the
       series is already time-ordered, so the last write per bucket is the last sample in
       it -- no explicit "last wins" branch needed). Render each bucket to one character:
       SPARK_GAP where the bucket was never written, else the SPARK_GLYPHS index computed
       by the exact same formula trend_sparkline uses (`round(value_over_hi * (len(
       SPARK_GLYPHS) - 1))`), except `hi` is the FIXED ceiling 100.0 here (clamp pct to
       [0, 100] first -- upstream can round-trip a hair over 100) rather than a locally
       observed peak. Return `["".join(chars)]` -- a one-element list, the exact
       Section<Vec<String>> shape `trends` already has, so the SAME Rust normalize function
       can read it unmodified. Docstring must state WHY the ceiling is fixed at 100 rather
       than scaled to the window's own peak like trend_sparkline: a %-of-window bar has to
       mean the same thing every time it is drawn to be comparable across windows, whereas
       trend_sparkline's peak-relative scale is deliberately NOT comparable across days.

    In claude-monitor.py:

    3. Add `self.cum_trend = None  # cached cumulative-window-usage sparkline, or None
       (collecting state)` next to the existing `self.trend_axis` init (~line 73).

    4. In compute_trends (~line 386-388), add `self.cum_trend = core.build_cum_trend(
       records, now)` immediately after the existing `self.trend_axis = ...` line -- same
       tick, same records variable, no new file read.

    5. In _handle_conn's snapshot dict (~line 666-672), add `"cum_trend": mon.cum_trend,`
       immediately after the existing `"trend_axis": mon.trend_axis,` entry.

    In claude_monitor/test_claude_monitor.py:

    6. Add `build_cum_trend` and `CUM_TREND_INTERVAL` to the `from .core import (...)` list
       (~line 18-91), alongside the existing `build_trend_rows` / `WIN5` entries.

    7. Insert the new asserts from <behavior> right after the existing
       `assert hourly_pct(_rolled, _hour + 1200)[23] == 3.0` line (~line 614), under a new
       "# --- cumulative window trend ---" comment, before "# --- dashboard logic ---".

    8. In the socket-wire-protocol test block (~line 1039-1074): add
       `self.cum_trend = ["cum1"]` to `_FakeMonitor.__init__`; add `"cum_trend"` to the
       `set(_snapshot.keys())` tuple; add `assert _snapshot["cum_trend"] == _mon.cum_trend`
       next to the existing `_snapshot["trend_axis"]` assertion.

    Style: codedoc block/docstring comments, ASCII only, no new imports, no new dependency,
    no config knob for the sampling interval.
  </action>
  <verify>
    <automated>just selfcheck</automated>
  </verify>
  <done>`just selfcheck` exits 0 with the new asserts in place; grep confirms exactly one
  definition of build_cum_trend, called from compute_trends and from the test file only.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Rust normalizes cum_trend through the existing trends path, plus fixtures</name>
  <files>rust/src/snapshot.rs, rust/tests/fixtures.rs, fixtures/generate.py, fixtures/snapshot/cold-start-null-sections.json, fixtures/snapshot/partial-sections.json, fixtures/snapshot/cum-trend-populated.json, fixtures/README.md</files>
  <behavior>
    New/updated #[test] coverage:
    - fixtures.rs's shared corpus runner gains a "cum_trend" expectation key that reads
      Snapshot.cum_trend exactly like "trends" reads Snapshot.trends (same rows/state
      assertions), proven by three fixtures:
      - cold-start-null-sections: cum_trend null -> "absent", alongside the other sections
        that already assert "absent" there (D-02: legitimate pre-first-poll absence).
      - partial-sections: cum_trend: [42] -> "malformed", alongside the existing
        trends: [42] -> "malformed" case, proving a bad cum_trend costs only itself, never
        usage/heatmap/sessions.
      - cum-trend-populated (new): a real sparkline row survives verbatim, and a row
        containing an OSC-52 clipboard-write control sequence + BEL comes back with its
        control characters replaced -- the exact hostile-controls-in-trend-rows scenario,
        proven again for the new key via the SAME shared normalize function.
    - `cargo test` (the corpus runner) is the automated proof; no new Rust unit test
      function is needed since normalize_trends itself is unmodified and already covered.
  </behavior>
  <action>
    In rust/src/snapshot.rs:

    1. Update the wire-contract doc comment (~lines 36-46) to add
       `"cum_trend": [string] | null` alongside the existing `"trends": [string] | null`
       line.

    2. Add `pub cum_trend: Section<Vec<String>>,` to `struct Snapshot` (~line 252), with a
       doc comment stating this is the cumulative-usage-in-window series: a second,
       independent graph from `trends`, normalized through the identical array-of-strings
       path because the wire shape is identical.

    3. In `Snapshot::from_value` (~line 285-291), add
       `cum_trend: normalize_trends(obj.get("cum_trend")),` -- call the EXISTING
       `normalize_trends` function verbatim. Do not add a `normalize_cum_trend` function;
       the sanitization and shape rules are identical to `trends`.

    In rust/tests/fixtures.rs:

    4. Generalize `check_trends` (~line 235) from
       `fn check_trends(snapshot: &Snapshot, expected: &Value) -> Result<(), String>` to
       `fn check_trends(section: &Section<Vec<String>>, expected: &Value, name: &str) ->
       Result<(), String>`, replacing its internal `&snapshot.trends`/"trends" references
       with the new `section`/`name` parameters.

    5. Update the two call sites in `check()`'s match (~line 143): keep
       `"trends" => check_trends(&snapshot.trends, expected, "trends")?,` and add
       `"cum_trend" => check_trends(&snapshot.cum_trend, expected, "cum_trend")?,`.

    In fixtures/generate.py:

    6. In `F["cold-start-null-sections"]` (~line 50-57), add `"cum_trend": None` to `wire`
       and `"cum_trend": "absent"` to `expect`.

    7. In `F["partial-sections"]` (~line 68-79), add `"cum_trend": [42]` to `wire` (the same
       shape the existing `"trends": [42]` entry there uses) and `"cum_trend": "malformed"`
       to `expect`.

    8. Add a new `F["cum-trend-populated"]` entry (place it near the other
       hostile-controls-in-trend-rows entry, ~line 159-164, for locality): wire carries
       `"cum_trend": ["▁▂▃█", "peak " + ESC + "]52;c;x" + BEL +
       "hour"]"` (reuse the module's existing ESC/BEL constants, do not hand-type control
       bytes); expect asserts
       `"cum_trend": {"rows": ["▁▂▃█", "peak ?hour"]}`. Give it a note
       field stating it proves the new key crosses the same trust boundary as `trends` via
       the shared normalize function, covering a populated sparkline and a hostile-control
       row in one fixture.

    9. Run `python3 fixtures/generate.py` to regenerate the corpus. It rewrites every
       generator-sourced file; confirm with `git diff --stat fixtures/snapshot/` that only
       cold-start-null-sections.json, partial-sections.json, and the new
       cum-trend-populated.json actually changed.

    In fixtures/README.md:

    10. Add a `cum_trend` row to the Expectations table (~line 40-48), same object form as
        `trends`: `{"rows": ["..."]}`.
  </action>
  <verify>
    <automated>python3 fixtures/generate.py &amp;&amp; just rust-test</automated>
  </verify>
  <done>`cargo test` is green including the three cum_trend fixtures; `git diff --stat
  fixtures/snapshot/` shows exactly the three intended files changed; fixtures/README.md
  documents the new key.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Render cum_trend as a second graph under the existing bar chart</name>
  <files>rust/src/main.rs</files>
  <behavior>
    New #[test] functions in the existing `mod tests` block (~line 1164):
    - A wire carrying both `"trends": [<sparkline>, "today 1M/hr"]` and
      `"cum_trend": [<sparkline2>]` renders, at a wide TestBackend, a buffer containing BOTH
      the original trends sparkline glyphs unchanged AND a "window usage" label string, and
      `trends_panel_height` for that App is STRICTLY GREATER than the no-cum_trend case --
      proving the second graph is additive, never a replacement.
    - The SAME wire with the `"cum_trend"` key removed renders WITHOUT the "window usage"
      text anywhere in the buffer, and `trends_panel_height` equals
      `TREND_ROWS + trends.len() - 1 + 2` exactly (the pre-existing formula) -- the
      regression guard proving the absent case is a true no-op on both rendering and
      layout.
  </behavior>
  <action>
    1. Add `fn snapshot_cum_trend(app: &App) -> Option<&Vec<String>>` immediately after
       `snapshot_trends` (~line 762), mirroring it exactly:
       `match app.snapshot.as_ref().map(|s| &s.cum_trend) { Some(Section::Present(rows)) if
       !rows.is_empty() => Some(rows), _ => None }`.

    2. In `trends_panel_height` (~line 771-780), after the existing `let left = TREND_ROWS +
       trends.len().saturating_sub(1);` line, add: when `snapshot_cum_trend(app)` returns
       `Some(cum)`, add `1 + TREND_ROWS + cum.len().saturating_sub(1)` to `left` (the
       leading `1` is the one label row separating the two graphs). Leave the `right`
       (heatmap) branch and the final `(left.max(right) as u16) + 2` untouched.

    3. In `draw_trends` (~line 889-929), change `let graph = trend_graph_lines(...)` to
       `let mut graph = trend_graph_lines(...)` (unchanged arguments). Immediately after
       that line and before `let heatmap = snapshot_heatmap(app);`, add: when
       `snapshot_cum_trend(app)` returns `Some(cum)`, push one
       `Line::from(Span::styled("window usage (0-100%)", Style::default().add_modifier(
       Modifier::DIM)))` onto `graph`, then `graph.extend(trend_graph_lines(cum, None));`.
       Everything below (the heatmap side-by-side layout match) already renders whatever
       `graph` holds, so it needs no further edit. Do NOT modify `trend_graph_lines` itself
       -- it is called a second time with `axis: None`, unchanged.

    4. Add the two tests from <behavior> to `mod tests`, following the existing
       `sessions_app(wire: &str) -> App` helper pattern (~line 1322) to build an App from a
       hand-written wire string via `Source::Fixture`, then `terminal.draw(|frame| draw(
       frame, &app))` against a `TestBackend` sized at least 40 columns wide (the "window
       usage (0-100%)" label is 22 chars) before scanning
       `terminal.backend().buffer().content()` for the expected substrings.
  </action>
  <verify>
    <automated>just rust-test &amp;&amp; just rust-lint</automated>
  </verify>
  <done>`cargo test` and `cargo clippy --all-targets -- -D warnings` are both green; the two
  new tests pass; `every_fixture_renders_at_every_size_without_panicking` still passes for
  every existing fixture (none of which carry cum_trend yet, so this is the no-op-when-
  absent guarantee exercised at scale).</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| daemon socket line -> Rust client | JSON the Rust client must decode wholesale; extended by one more optional key |
| cum_trend row string -> terminal | daemon-built text reaching a real TTY; must not carry live control sequences |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-krn-01 | Tampering | "cum_trend" wire key -> Rust normalize -> terminal | medium | mitigate | reuses normalize_trends's sanitize_display path verbatim (no new parsing code, so no new attack surface); pinned by the cum-trend-populated fixture's hostile-control-character row (Task 2) |
| T-krn-02 | Denial of Service | malformed/absent cum_trend blanking other sections | low | mitigate | Section<T> independence (D-02); pinned by partial-sections.json's cum_trend: [42] -> malformed alongside surviving usage/heatmap/sessions (Task 2) |
| T-krn-SC | Tampering | npm/pip/cargo installs | low | accept | no new dependency is added by this task |
</threat_model>

<verification>
- `just selfcheck` exits 0 (Task 1's mandated gate).
- `python3 fixtures/generate.py` then `just rust-test` green (Task 2's fixtures + corpus).
- `just rust-test` and `just rust-lint` green (Task 3's rendering).
- The existing hourly bar chart fixtures render byte-identically to before this change.
</verification>

<success_criteria>
- The trends panel shows the existing hourly bar chart unchanged, plus a second sparkline
  of cumulative usage within the current 5h window whenever the daemon has sampled it.
- The new graph is scaled 0..100% fixed, anchored to the current window, despiked, and
  degrades to simply not appearing when the daemon has no data for it yet.
- No new dependency, no new poll, no new config surface.
</success_criteria>

<output>
Create `.planning/workstreams/notifications-predictive-alerts/quick/260727-krn-add-cumulative-usage-timeseries-line-to-/260727-krn-SUMMARY.md` when done
</output>
