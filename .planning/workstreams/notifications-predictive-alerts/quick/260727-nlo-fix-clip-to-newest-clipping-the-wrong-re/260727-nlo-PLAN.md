---
phase: 260727-nlo
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - rust/src/main.rs
  - fixtures/generate.py
  - fixtures/snapshot/cum-trend-clipped-keeps-newest.json
autonomous: true
requirements: [QT-260727-nlo]

must_haves:
  truths:
    - "clip_to_newest finds the end of the REAL (non-blank) prefix in the cum_trend sparkline before slicing by width, so a genuinely climbing series with a trailing future-blank run never renders as an all-blank graph. build_cum_trend buckets the WHOLE window through reset (not just up to now), so every index past (now - start) // CUM_TREND_INTERVAL is a genuine, not-yet-sampled FUTURE bucket rendered as SPARK_GAP (a literal space) -- correct and intentional (an unsampled bucket must read distinctly from an idle-but-sampled one, which renders at the floor glyph). The pre-fix clip kept the LAST N raw characters of the WHOLE string and could keep nothing but that trailing blank run -- confirmed empirically: a live daemon snapshot's real cum_trend row was 300 chars (a climb across ~124 chars followed by 176 literal SPARK_GAP spaces), graph_width was 136, and the pre-fix clip output was 132 chars, ALL SPACES."
    - "The trailing blank/future run is always dropped from the returned row, even when the real prefix already fits within budget -- the graph never spends screen width on blank future space it could give to real data instead."
    - "The original hourly bar chart (trend_sparkline/trend_axis/build_trend_rows/TREND_INTERVAL/core.build_cum_trend/core.cum_trend_axis) and clip_to_newest's own budget/gutter computation are both untouched -- only the slicing target inside clip_to_newest changes, from whole-string-relative to real-prefix-relative. This is a Rust-only, single-function fix."
    - "A pure-function unit test on clip_to_newest, shaped like the actual bug (a real-data prefix shorter than the total string, followed by a trailing run of spaces, at a panel_width narrower than the total string), demonstrates the fix directly -- unlike 260727-mki's own tests, which used an all-real synthetic sparkline with no trailing blanks and so never exercised this shape despite being green when the bug shipped."
    - "The permanent fixture corpus asset (fixtures/snapshot/cum-trend-clipped-keeps-newest.json, generated from fixtures/generate.py) now carries a trailing blank run too, so the SAME live/manual `just rust-fixture cum-trend-clipped-keeps-newest` check this and the prior quick task both used actually exercises this regression, rendering real bars (not blank space) at a terminal width narrower than the real climb."
  artifacts:
    - rust/src/main.rs
    - fixtures/generate.py
    - fixtures/snapshot/cum-trend-clipped-keeps-newest.json
  key_links:
    - "draw_trends's single call site (`clip_to_newest(cum, cum_axis, graph_width)`, rust/src/main.rs) is the ONLY caller of clip_to_newest -- it operates exclusively on the cum_trend row, never on the hourly `trends` graph, so this fix is scoped identically to the function it corrects."
    - "fixtures/generate.py's F[\"cum-trend-clipped-keeps-newest\"] is the SAME fixture `just rust-fixture cum-trend-clipped-keeps-newest` renders for the live tmux check -- extending its existing wire with a trailing blank run (not creating a second fixture) keeps ONE canonical corpus asset covering both the width-clip regression (260727-mki) and the trailing-blank-run regression (this task)."
---

<objective>
Fix `clip_to_newest` (rust/src/main.rs) clipping the WRONG region of the cum_trend
sparkline: it currently keeps the last `budget` raw characters of the whole string,
which can be entirely inside the trailing future-blank run `build_cum_trend` appends
(the array spans the WHOLE window through reset, not just up to "now"), rendering a
genuinely climbing series as a totally empty graph. This is a same-session bug-fix
follow-up to 260727-mki's own `clip_to_newest` (caught before the user needed to
report it a second time) -- root cause: 260727-mki assumed the array's tail IS the
newest real data (true for the ORIGINAL hourly bar chart, whose last index has no
future buckets at all) and applied that assumption to cum_trend, where it is false.

Purpose: the cum_trend graph currently renders as completely empty axis labels and
text with zero glyph bars whenever the terminal is narrow enough to force clipping
and the window has not yet finished (i.e. almost always, since `reset` is future by
definition) -- this defeats the entire point of the graph.

Output: `clip_to_newest` finds the end of the real (non-blank) prefix first, clips
WITHIN that prefix only, and always drops the trailing blank/future run (even when
the real prefix already fits the budget). A new pure-function unit test proves it
directly. The `cum-trend-clipped-keeps-newest` fixture corpus asset gains a trailing
blank run so its own live/manual render check actually exercises this regression.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/workstreams/notifications-predictive-alerts/STATE.md

# Regions to read before editing (do NOT re-read a range already seen):
@rust/src/main.rs   # doc comment + clip_to_newest ~lines 903-931 (rewrite both); draw_trends's single call site ~line 973 (`trend_graph_lines(&clip_to_newest(cum, cum_axis, graph_width), cum_axis)` -- do NOT touch this line, only the function it calls); TREND_ROWS const ~line 67; trend_graph_lines ~lines 806-856 (do NOT modify -- clip_to_newest's gutter formula duplicates its axis_width formula deliberately, per the existing doc comment. CONFIRMED during planning: `axis_width`/the gutter indent depend only on the `axis` ticks' own widths, never on row 0's character count, and the text rows below are indented by that SAME axis_width regardless of row 0's length -- so row 0 coming back shorter after this fix (real_len instead of always-exactly-budget) has no knock-on effect on the gutter or the text rows, it only narrows the rendered graph's column count, which is the intended effect); test module ~line 1225 `mod tests`; render_trends_rows helper ~lines 1389-1403 (existing shared render fn, reuse if a full-stack check is added -- not required for the new unit test, which calls clip_to_newest directly); existing clip regression test `cum_trend_sparkline_clipping_keeps_the_newest_columns_not_the_oldest` ~lines 1460-1491 (pure climb, NO trailing blanks -- exactly why it passed despite this bug; leave this test's body unchanged, it still passes after the fix since real_len == total_len for a pure climb with no spaces, add the NEW test near it)
@fixtures/generate.py   # `_CUM_CLIMB` ~lines 186-193 (leave UNCHANGED -- the comment two lines above it says "the SAME string rust/src/main.rs's ... test uses", keep that true); `F["cum-trend-clipped-keeps-newest"]` ~lines 195-209 (extend: add a trailing blank-run variable, use it in wire/expect, update note); write loop ~lines 290-296 (`python3 fixtures/generate.py` regenerates ALL of fixtures/snapshot/*.json from this file -- confirm via git diff/status that only the one intended fixture file changes)
@fixtures/snapshot/cum-trend-clipped-keeps-newest.json   # current generated content, no trailing blanks -- read-only reference, this file is REGENERATED by generate.py, never hand-edited
@justfile   # rust-test ~line 74-75, rust-lint ~line 78-79, rust-fixture ~line 82-83 (`cd rust && cargo run --release --quiet -- --fixture ../fixtures/snapshot/{{name}}.json {{args}}`), selfcheck ~line 37-38

Reuse, do NOT reimplement:
- clip_to_newest's existing gutter/budget computation (axis widest-tick + 1, panel_width.saturating_sub(gutter)) -> unchanged, only the slicing target changes
- SPARK_GAP == " " (claude_monitor/core.py:311) -- the exact character that marks an unsampled bucket; do NOT touch core.py, core.build_cum_trend, core.cum_trend_axis, CUM_TREND_INTERVAL, TREND_INTERVAL, or POLL_INTERVAL in this task (Rust-only fix)
- fixtures/generate.py's write loop and corpus conventions (wire as JSON string, expect as pass-through dict) -- extend the one entry, do not add a parallel generation path

Do not touch: core.build_cum_trend, core.cum_trend_axis, CUM_TREND_INTERVAL,
TREND_INTERVAL, POLL_INTERVAL, the original hourly bar chart's own logic
(trend_sparkline/trend_axis/build_trend_rows), trend_graph_lines, or
clip_to_newest's budget/gutter computation. No new dependency, no new poll, no new
config knob. `trend_graph_lines` itself stays unmodified.
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: clip_to_newest clips within the real (non-blank) prefix, not the whole array</name>
  <files>rust/src/main.rs, fixtures/generate.py, fixtures/snapshot/cum-trend-clipped-keeps-newest.json</files>
  <behavior>
    New #[test] in rust/src/main.rs's test module (near the existing
    `cum_trend_sparkline_clipping_keeps_the_newest_columns_not_the_oldest`, which stays
    unchanged), named e.g. `clip_to_newest_drops_the_trailing_future_blank_run_not_the_real_data`:
    - Build a sparkline shaped like the REAL bug case: a real-data prefix shorter than
      the total string, followed by a trailing run of spaces extending to the full
      length -- concretely `let real = "0123456789";` (10 chars) followed by 20 literal
      spaces (`" ".repeat(20)`), for a 30-char total. Assert `.chars().count() == 30` as
      a transcription guard.
    - Call `clip_to_newest(&[sparkline], None, 15)` -- panel_width (15) is narrower than
      the total string (30) but WIDER than the real prefix (10), exactly mirroring the
      live bug's own relationship (budget(132) > real_len(~124), budget(132) <
      total_len(300)) -- this is precisely the condition under which the pre-fix code
      grabbed nothing but blank tail.
    - Assert the returned row's first character is NOT a space (`assert_ne!(first.chars().next(), Some(' '))`)
      -- the pre-fix code fails this (it returns all spaces here); this is the direct
      "it must not just be blank" check.
    - Assert the returned row's last character IS `'9'` (the real prefix's own last
      character), not a space.
    - Assert the returned row equals `real` exactly ("0123456789") -- since budget(15) >
      real_len(10), the whole real prefix survives with the trailing blank run fully
      dropped and no padding added. This exercises the `start == 0` branch (real prefix
      already fits budget).
    - Second case, SAME sparkline, `clip_to_newest(&[sparkline], None, 6)` (budget(6) <
      real_len(10) this time): assert the result equals `"456789"` exactly -- length 6,
      ends on `'9'`, contains no space. This exercises the OTHER branch
      (`start = real_len - budget > 0`, slicing within the real prefix) -- the fix
      introduces two branches and both must be guarded by an automated test, not one
      guarded by a test and the other guarded only by the manual tmux check.
    The existing `cum_trend_sparkline_clipping_keeps_the_newest_columns_not_the_oldest`
    test (pure 60-char climb, no spaces at all) passes UNCHANGED: for it, real_len ==
    total_len == 60, so the new real-prefix-relative slicing produces the byte-identical
    result the old whole-string-relative slicing did.
  </behavior>
  <action>
    In rust/src/main.rs (production code):

    1. Rewrite the doc comment immediately above `clip_to_newest` (~lines 903-917).
       Keep the existing framing (sparkline can be up to 300 chars wide, a `Paragraph`
       with no `.wrap()` drops what does not fit, columns run oldest-left/newest-right,
       keep the newest and drop the oldest). ADD the root-cause explanation: `build_cum_trend`
       buckets the WHOLE window, `[reset - WIN5, reset)` -- window START to window
       END/reset, not "oldest sampled" to "now". Since `reset` is always in the future
       relative to "now" (the window has not finished), every bucket index past
       `(now - start) // CUM_TREND_INTERVAL` is a genuine, not-yet-sampled FUTURE bucket
       and renders as `SPARK_GAP` (a literal space) by design -- so an unsampled bucket
       reads distinctly from a genuinely-idle-but-sampled one (which renders at the
       floor glyph, not a gap). That trailing blank run is real, but it is never the
       "newest data" a raw last-N-characters clip assumes it is: true for the ORIGINAL
       hourly bar chart (its last index IS the current hour, no future buckets exist at
       all), false here. Note that a raw whole-string clip (the pre-fix code, added by
       260727-mki) could keep nothing but that trailing blank run, rendering a
       genuinely climbing series as a totally empty graph -- confirmed live (300-char
       row, ~124 real chars + 176 literal spaces, graph_width 136, pre-fix output 132
       chars all spaces). State the fix: find the end of the REAL (non-blank) prefix
       first, clip WITHIN that prefix only, and drop the trailing blank run
       unconditionally -- even when the whole real prefix already fits `budget`, so the
       display never spends width on blank future space it could give to real data
       instead. Keep the closing paragraph about `trend_graph_lines` staying unmodified
       and the gutter formula being deliberately duplicated, unchanged.

    2. Rewrite `clip_to_newest`'s body (~lines 918-931). Keep the `gutter`/`budget`
       computation byte-for-byte unchanged (do not touch it). Replace the "clone rows,
       conditionally truncate the first row by raw length" logic with: collect the
       first row's characters into `let chars: Vec<char> = first.chars().collect();`.
       Compute `let real_len = chars.iter().rposition(|&c| c != ' ').map(|i| i + 1).unwrap_or(0);`
       -- one past the index of the last non-space character (0 if the whole row is
       somehow blank; `build_cum_trend` never actually returns an all-blank sparkline
       since it early-returns `None` when nothing survives `despike`, but this stays
       safe regardless). Compute `let start = real_len.saturating_sub(budget);`
       (unchanged budget, new base value). Assign
       `*first = chars[start..real_len].iter().collect();` -- always slicing within
       `[0, real_len)`, so the trailing blank run past `real_len` is dropped
       unconditionally, and the result is never longer than `budget` characters. Apply
       this to `first` UNCONDITIONALLY (remove the `if len > budget` guard entirely --
       the new logic is correct in both the "needs clipping" and "already fits" cases,
       and dropping the trailing blank run even when the real prefix already fits
       budget is a deliberate part of the fix, not a special case to gate).

    3. Add the new unit test described in `<behavior>` (BOTH cases -- the fits-within-
       budget case and the clips-within-real-prefix case), near the existing
       `cum_trend_sparkline_clipping_keeps_the_newest_columns_not_the_oldest` test
       (~line 1460). Call `clip_to_newest` directly (it is a private fn in the same
       module, no `App`/fixture plumbing needed for this test).

    In fixtures/generate.py:

    4. Immediately after the existing `_CUM_CLIMB` definition and its
       `assert len(_CUM_CLIMB) == 60` (~lines 186-193, leave both UNCHANGED -- the
       comment above `_CUM_CLIMB` claims it is "the SAME string rust/src/main.rs's ...
       test uses", and that must stay true), add:
       `_CUM_FUTURE_BLANK = " " * 60` (models the trailing not-yet-sampled region
       `build_cum_trend` actually produces) and
       `_CUM_SPARKLINE = _CUM_CLIMB + _CUM_FUTURE_BLANK` (120 chars total: 60 real + 60
       blank).

    5. In `F["cum-trend-clipped-keeps-newest"]` (~lines 195-209): replace both uses of
       `_CUM_CLIMB` (in `"wire"` and `"expect"`, the `"cum_trend"` row's first element)
       with `_CUM_SPARKLINE`. Update `"note"` to explain the fixture now ALSO covers
       the 260727-nlo trailing-blank-run regression: the 60-column real climb is
       followed by 60 trailing blank (unsampled-future) columns, modeling
       `build_cum_trend`'s actual window-through-reset shape; at a `just rust-fixture
       cum-trend-clipped-keeps-newest` terminal width narrower than the 60-column real
       climb, the top row must still show filled cells from the REAL data -- proving
       the clip found the real prefix and kept its newest columns, not the blank future
       run and not the oldest real columns either. Everything else in this fixture
       entry (`"trends"`, `"trend_axis"`, `"cum_trend_axis"`, the text row) stays
       unchanged.

    6. Run `python3 fixtures/generate.py` to regenerate the corpus. Confirm with
       `git status` and `git diff --stat fixtures/snapshot/` that ONLY
       `cum-trend-clipped-keeps-newest.json` changed (no other fixture's generated
       content drifts).

    Verification (do not skip -- this is exactly how the bug shipped last time on green
    unit tests alone):

    7. Run `just rust-test` and `just rust-lint`; both must be green/clean.

    8. Live tmux-captured render check, reusing the SAME narrow width 260727-mki
       already validated in this exact codebase: from the repo root,
       `tmux new-session -d -s nlo-check -x 55 -y 45 "just rust-fixture cum-trend-clipped-keeps-newest"`,
       `sleep 1`, `tmux capture-pane -p -t nlo-check`, `tmux kill-session -t nlo-check`.
       Confirm the captured pane shows the cum_trend graph's rows with visible filled
       glyphs from the real climb -- NOT an empty/blank graph (which is what the
       pre-fix code showed for this fixture once it carries the trailing blank run).

    9. Run `just lint` (ruff) -- `fixtures/generate.py` is Python and step 5 adds a
       re-wrapped `"note"` string, so this catches a line-length/formatting slip before
       it becomes a second commit.

    10. Run `just selfcheck` -- expected to be a no-op green pass (this task makes no
        changes to the daemon/core Python that `--selfcheck` asserts against), kept as
        a cheap regression gate.

    11. Recommended, not required: fetch the live daemon socket's actual snapshot
        (`echo '{"query": "snapshot"}' | socat - UNIX-CONNECT:"$XDG_RUNTIME_DIR/claude-monitor.sock"`
        or equivalent), extract its real `cum_trend` value into a scratch fixture file,
        and render it through the fixed binary at the terminal's real live width (the
        same approach used during diagnosis) to end-to-end confirm the exact live case
        is fixed, not just a synthetic analog of it. Do not commit the scratch fixture.
  </action>
  <verify>
    <automated>python3 fixtures/generate.py &amp;&amp; just rust-test &amp;&amp; just rust-lint &amp;&amp; just lint &amp;&amp; just selfcheck</automated>
  </verify>
  <done>`cargo test` is green, including the new
  `clip_to_newest_drops_the_trailing_future_blank_run_not_the_real_data` test's BOTH
  cases (the `start == 0` fits-within-budget case, which fails against the pre-fix
  code and passes against the fix; and the `start = real_len - budget` clips-within-
  real-prefix case) and the unchanged
  `cum_trend_sparkline_clipping_keeps_the_newest_columns_not_the_oldest` test.
  `cargo clippy --all-targets -- -D warnings` is clean. `just lint` (ruff) is clean.
  `just selfcheck` exits 0 (this task makes no changes to the daemon/core Python that
  `--selfcheck` asserts against). `git diff --stat fixtures/snapshot/` shows exactly
  one changed file (`cum-trend-clipped-keeps-newest.json`), no new file. The live
  tmux-captured render of `cum-trend-clipped-keeps-newest` at `-x 55 -y 45` shows real
  filled bars in the cum_trend graph, not blank space. The SUMMARY and STATE.md
  quick-task row name the root cause explicitly: `build_cum_trend`'s array spans the
  whole window through reset (not just up to now), so a genuine trailing future-blank
  region is real and by design -- the bug was clipping by raw whole-string length
  instead of within the real (non-blank) prefix.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|--------------|
| cum_trend sparkline string -> `clip_to_newest`'s char-level slicing | an untrusted-origin `String` (already normalized by the existing wire-decode path) crossing into `.chars().collect()` / index-range slicing |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-nlo-01 | Tampering | `cum_trend` wire value -> `clip_to_newest`'s real-prefix detection | low | mitigate | unchanged trust boundary from 260727-mki (T-mki-01); no new parsing code, still routed through the existing `normalize_trends` path before reaching this function |
| T-nlo-02 | Denial of Service | `clip_to_newest` panicking on a pathological (empty or all-space) sparkline string | low | mitigate | `rposition(...).map(...).unwrap_or(0)` defaults `real_len` to 0 on an all-blank/empty row; `start = real_len.saturating_sub(budget)` never exceeds `real_len`, so `chars[start..real_len]` is always a valid, non-panicking range regardless of string content |
| T-nlo-SC | Tampering | npm/pip/cargo installs | low | accept | no new dependency is added by this task |
</threat_model>

<verification>
- `python3 fixtures/generate.py` then `just rust-test` and `just rust-lint` are
  green/clean (both new unit-test cases + the existing test all pass; no clippy
  warnings).
- `just lint` (ruff) is clean on the `fixtures/generate.py` edit.
- `just selfcheck` exits 0 (no-op regression gate; this task makes no changes to the
  daemon/core Python that `--selfcheck` asserts against).
- `git diff --stat fixtures/snapshot/` plus `git status` show exactly one changed
  fixture file, no unintended drift in the rest of the corpus.
- Live tmux-captured render of `cum-trend-clipped-keeps-newest` at `-x 55 -y 45` shows
  real filled bars in the cum_trend graph, not blank space (see Task 1 `<done>`).
</verification>

<success_criteria>
- `clip_to_newest` clips within the real (non-blank) prefix of the cum_trend
  sparkline, never the whole raw string -- a genuinely climbing series with a
  trailing future-blank run always shows real data, never renders as an empty graph.
- The trailing blank/future run is always dropped, even when the real prefix already
  fits the available budget.
- The original hourly bar chart, `trend_graph_lines`, `core.build_cum_trend`,
  `core.cum_trend_axis`, and clip_to_newest's own budget/gutter computation are all
  untouched.
- A pure-function unit test shaped exactly like the live bug (real prefix + trailing
  blank run, panel_width narrower than the total string) exists and passes.
- The `cum-trend-clipped-keeps-newest` fixture corpus asset now models the same
  trailing-blank shape, so its own live/manual render check actually exercises this
  regression going forward.
- No new dependency, no new poll, no new config knob.
- The root cause (window-spanning array with a genuine trailing future-blank region)
  is named explicitly in the SUMMARY and STATE.md quick-task row, so it is not
  "fixed" again in the wrong direction later.
</success_criteria>

<output>
Create `.planning/workstreams/notifications-predictive-alerts/quick/260727-nlo-fix-clip-to-newest-clipping-the-wrong-re/260727-nlo-SUMMARY.md` when done
</output>
