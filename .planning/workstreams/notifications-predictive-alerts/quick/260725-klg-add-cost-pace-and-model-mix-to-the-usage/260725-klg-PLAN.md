---
phase: 260725-klg
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - claude_monitor/core.py
  - claude_monitor/test_claude_monitor.py
  - claude-monitor.py
  - rust/src/snapshot.rs
  - rust/src/format.rs
  - fixtures/generate.py
  - fixtures/snapshot/cost-pace-model-mix.json
  - fixtures/snapshot/cost-pace-junk-degrades-only-itself.json
  - rust/tests/fixtures.rs
autonomous: true
requirements: [QT-260725-klg]

must_haves:
  truths:
    - "parse_usage keeps six new optional keys off the already-fetched CLI document: cost_usd, cost_per_hour, pace_label, pace_used_pct, pace_elapsed_pct, model_mix."
    - "Junk, wrong-typed, missing, or non-finite values in any new field degrade that field to None and never cost the existing 5h payload (the seven_day_* posture, D-04)."
    - "One shared core helper builds the new detail row; tui_usage_rows and Monitor.usage_rows both append the SAME string, and the Rust mirror reproduces it (D-05)."
    - "When every new field is absent (older CLI, or --api returning nulls) the rendered rows are byte-identical to today's output -- no empty row, no placeholder."
    - "pace_label and model_distribution family text are treated as untrusted: control characters stripped and length bounded on the Python side, and sanitize_display_bounded applied again at the Rust snapshot boundary."
    - "Non-finite numbers never reach the socket line: json.dumps would emit the Infinity/NaN literals that serde_json rejects, which would turn one bad cost value into a whole-fetch decode failure for the Rust client."
    - "The Rust usage panel sizes and colours correctly with the extra row present, and the fixture corpus pins the new normalization behaviour in both the present and the junk case."
  artifacts:
    - claude_monitor/core.py
    - claude_monitor/test_claude_monitor.py
    - claude-monitor.py
    - rust/src/snapshot.rs
    - rust/src/format.rs
    - fixtures/generate.py
    - rust/tests/fixtures.rs
  key_links:
    - "core.parse_usage new keys -> mon.usage -> _handle_conn snapshot['usage'] (whole-dict serialization, so the socket carries them with no daemon code change) -> rust normalize_usage."
    - "core.usage_extra_row(usage) <-> format.rs usage_extra_row mirror: one row definition, two languages, parity asserted on both sides."
    - "tui_usage_rows returning an extra trailing row <-> main.rs draw_usage caps.get(i) else-branch + usage_panel_height rows.len() (both already handle a row with no cap)."
---

<objective>
Keep three groups of data the daemon already fetches and throws away -- cost, pace, and
model mix -- and surface them as one extra detail row under the existing 5h/7d cap rows,
on every surface (tray menu, socket snapshot, Rust dashboard).

Purpose: `claude-monitor --output json --once --api` returns `local.cost_usd`,
`local.burn_rate_cost_per_hour`, the `pace` block and `local.model_distribution` on every
poll; `parse_usage` drops all of it. This is a field-passthrough change, not a new
subsystem: no new polling, no new data source, no new dependency.

Output: six new optional keys on the usage dict, two small pure core helpers
(`usage_extra_row`, `model_mix`) with self-check asserts, their Rust mirrors, and two new
snapshot fixtures.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/workstreams/notifications-predictive-alerts/STATE.md

# Regions to read before editing (do NOT read whole files twice):
@claude_monitor/core.py                 # parse_usage ~268-309, tui_usage_rows ~921-957, _safe_cell ~1020, fmt_* ~328-352
@claude-monitor.py                      # Monitor.usage_rows ~317-340, _handle_conn ~578-609
@rust/src/snapshot.rs                   # wire-shape doc ~38-48, struct Usage ~176-185, normalize_usage ~319-377
@rust/src/format.rs                     # tui_usage_rows ~265-308 and its tests ~310-548
@rust/src/main.rs                       # usage_panel_height ~600, cap_row_spans ~641, draw_usage ~683-736 (read only; expected to need NO edit)
@fixtures/generate.py                   # F[...] entry shape ~20-60, writer loop at the tail
@rust/tests/fixtures.rs                 # check_usage match arms ~194-215

Reuse, do NOT reimplement:
- core._safe_cell(s)          -> strips non-printable/control chars (ESC and U+202E are both non-printable in Python)
- core._is_num(v)             -> numeric-and-not-bool predicate
- math.isfinite               -> already imported in core.py
- sanitize::sanitize_display_bounded(raw, max) -> the Rust untrusted-text boundary
- snapshot::number_field / Field -> the existing absent-vs-wrong-type discriminator

Verified CLI shape (claude-monitor 4.0.0, live output):
  local.cost_usd = 113.9296
  local.burn_rate_cost_per_hour = 143.31
  local.model_distribution = [{"family": "opus", "percentage": 100.0, ...}]
  pace = {"label": "slow down", "used_percentage": 27.0, "elapsed_percentage": 16.0}
Under --api any of these may be null or absent. Treat every one as optional.

Target row text (one row, cells joined by the existing two-space separator, each cell
omitted when its data is absent, whole row omitted when all three groups are absent):
  $113.93  $143/hr  pace: 27%/16% slow down  opus 100%
</context>

<tasks>

<task type="tracer" tdd="true">
  <name>Task 1: Python core keeps the fields and builds the one shared row</name>
  <files>claude_monitor/core.py, claude_monitor/test_claude_monitor.py, claude-monitor.py</files>
  <behavior>
    New asserts in test_claude_monitor.demo (assert style, no pytest, no fixtures):
    - parse_usage on a document carrying local.cost_usd / local.burn_rate_cost_per_hour /
      pace / local.model_distribution returns those six keys populated.
    - parse_usage on the existing --api sample (none of the new blocks present) returns all
      six keys as None and leaves used_percentage / resets_at_epoch / burn_rate_per_min
      untouched.
    - Wrong types degrade only themselves: cost_usd "lots", pace a list, pace.label 42,
      model_distribution a string, model_distribution entries missing family/percentage --
      each yields None for that field while the 5h payload survives.
    - Non-finite input (float("inf"), float("nan") via json.loads of Infinity/NaN) yields
      None for that field, so json.dumps can never emit a bare Infinity token on the wire.
    - Hostile text is neutralized: a pace label and a model family containing ESC[2J, a BEL,
      and U+202E come back with no character that fails str.isprintable(), and each is
      bounded in length.
    - usage_extra_row returns None when all three groups are absent, and returns each cell
      independently when only one group is present.
    - tui_usage_rows with no new fields returns exactly the same list it returns today
      (row count and text unchanged); with the fields present it returns one extra trailing
      row equal to usage_extra_row's output.
  </behavior>
  <action>
    In claude_monitor/core.py:

    1. Add two module constants near the existing usage constants: a character ceiling for
       daemon-sourced display text (32 is enough for a pace label or a condensed mix) and a
       cap on how many model-distribution entries are kept (2 -- three entries plus the cost
       and pace cells overflow the left column of an 80-column terminal, and the panel
       clips rather than wraps). Give the entry cap a ponytail: note naming the ceiling and
       the upgrade path (widen when the panel gets a width-aware layout).

    2. Add a pure helper that condenses local.model_distribution into a short string. It
       takes the raw value, returns None unless it is a list; keeps only dict entries whose
       family is a str and whose percentage is a finite number; sorts by percentage
       descending; drops entries that round to zero percent; keeps at most the entry cap;
       renders each as the sanitized-and-bounded family followed by the rounded percentage
       and a percent sign, joined by single spaces; returns None when nothing survives.
       Route family text through _safe_cell and bound it before it is joined.

    3. Extend parse_usage. After the existing seven keys are built, read local.cost_usd,
       local.burn_rate_cost_per_hour, and the pace block (doc.get("pace") coerced to {} when
       it is not a dict, mirroring how `seven` is handled today), then add six keys:
       cost_usd, cost_per_hour, pace_used_pct, pace_elapsed_pct, pace_label, model_mix.
       Numeric ones survive only when _is_num AND math.isfinite; everything else becomes
       None. pace_label survives only when it is a str, routed through _safe_cell and
       bounded to the text ceiling, and an empty result becomes None. model_mix comes from
       the helper in step 2. Extend the docstring to say the new block degrades per field
       and never rejects the 5h payload, and to record WHY non-finite is rejected: a bare
       Infinity token in the socket line is a whole-fetch decode failure for the Rust
       client, not a cosmetic glitch.

    4. Add a pure `usage_extra_row(usage)` helper returning the detail row string, or None
       when it would be empty. Cells, in order, each appended only when its data is present:
       cost_usd formatted with two decimals behind a dollar sign; cost_per_hour rounded to
       whole dollars with a "/hr" suffix; the pace cell, emitted only when the label and
       BOTH percentages are present, as the rounded used percent, a slash, the rounded
       elapsed percent, then the label; model_mix verbatim. Join with the same two-space
       separator tui_usage_rows already uses. Read every field with .get -- this function
       also runs against a dict that arrived over a socket. Document that this is the single
       definition of the row per D-05, and that the dollar formatting lives here precisely so
       neither surface grows its own.

    5. In tui_usage_rows, after the weekly row block, append usage_extra_row's result when
       it is not None. Nothing else in that function changes, so the 5h/7d row text and the
       two-space cell contract stay exactly as they are.

    In claude-monitor.py:

    6. In Monitor.usage_rows, append the same core.usage_extra_row(u) result when it is not
       None, as one additional insensitive menu row. No second formatting path.

    7. _handle_conn needs NO code change: it serializes mon.usage wholesale, so the six new
       keys ride the existing snapshot response. Confirm this by reading the handler, and
       note it in the SUMMARY rather than editing it.

    Style: codedoc block/docstring comments, ASCII only ($143/hr and -> only), no new
    imports, no new dependency. Do not persist cost into history_record -- history is
    usage-percent denominated and nothing reads a cost column.
  </action>
  <verify>
    <automated>just selfcheck &amp;&amp; just lint</automated>
  </verify>
  <done>`just selfcheck` exits 0 with the new asserts in place, `just lint` is clean, and grep shows exactly one definition of the dollar formatting (in core.usage_extra_row) with call sites in tui_usage_rows and Monitor.usage_rows.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Rust snapshot normalization and row mirror</name>
  <files>rust/src/snapshot.rs, rust/src/format.rs</files>
  <behavior>
    New #[cfg(test)] tests alongside the existing ones:
    - snapshot.rs: a usage object carrying all six new fields normalizes to Present with each
      value populated.
    - snapshot.rs: junk in any new field (a numeric string, a bool, an array, an object)
      degrades that field to None while used_percentage and the rest survive -- the same
      shape as the existing weekly-junk test.
    - snapshot.rs: hostile text in pace_label (a CSI sequence, an OSC, a bidi override)
      comes back sanitized, mirroring hostile_session_text_is_sanitized_at_the_boundary.
    - format.rs: tui_usage_rows with no new fields returns the same rows the existing tests
      already pin (row count unchanged) -- the regression guard for silent row growth.
    - format.rs: with the fields present, the trailing row equals the target string from the
      plan context, and each group renders alone when the others are absent.
  </behavior>
  <action>
    In rust/src/snapshot.rs:

    1. Update the wire-shape doc comment near the top so the usage line lists the six new
       keys alongside the existing seven.

    2. Extend `struct Usage` with cost_usd, cost_per_hour, pace_used_pct, pace_elapsed_pct
       (all Option&lt;f64&gt;) and pace_label, model_mix (both Option&lt;String&gt;). Extend the
       struct's doc comment to state that this whole block follows the weekly block's
       posture: absent or wrong-typed degrades the field, never the section, because a
       cosmetic extra is not allowed to cost the gauge.

    3. In normalize_usage, add the six fields after the weekly block, using the same
       `match number_field(...) { Field::Value(n) =&gt; Some(n), _ =&gt; None }` shape for the
       numbers. For the two strings: present-and-a-str goes through
       sanitize_display_bounded with a small ceiling constant matching the Python text
       ceiling; anything else is None; an empty sanitized result is None. Add a brief
       comment that the daemon built these strings but they originate in CLI output, so
       "the daemon built it" is not "it is safe" -- the same reasoning the trends rows
       already carry.

    4. Update every existing struct-literal construction of Usage in this file's tests so it
       compiles (or give the new fields a construction helper if the churn is large --
       prefer whatever is the smaller diff).

    In rust/src/format.rs:

    5. Add a `usage_extra_row(usage: &amp;Usage) -&gt; Option&lt;String&gt;` mirroring the Python
       helper cell for cell, using the same two-space join, the same two-decimal cost, the
       same rounded per-hour dollars, and the same all-three-or-nothing pace predicate.
       Document it as the deliberate mirror of claude_monitor.core.usage_extra_row under the
       same reproduce-verbatim rule the existing tui_usage_rows doc comment states.

    6. Append its result to the rows vector in tui_usage_rows, after the weekly row.

    7. Update the `usage_of` test constructor for the new fields (keep it terse -- either
       extend it with Default-style Nones internally or add one wider constructor used only
       by the new tests).

    Read rust/src/main.rs but expect NO edit there: usage_panel_height already derives from
    rows.len(), and draw_usage's `caps.get(i)` else-branch already renders a row that has no
    cap as a plain, uncoloured line with an empty projection cell. Confirm that by reading
    both, and if either assumption is wrong, fix it minimally in main.rs and say so in the
    SUMMARY. ASCII only, codedoc block comments, no new crate.
  </action>
  <verify>
    <automated>just rust-test &amp;&amp; just rust-lint</automated>
  </verify>
  <done>`cargo test` and `cargo clippy -- -D warnings` are both green; the new usage fields normalize, degrade and sanitize under test; the extra row appears in tui_usage_rows output only when its data is present.</done>
</task>

<task type="auto">
  <name>Task 3: Fixture corpus and both verification gates</name>
  <files>fixtures/generate.py, fixtures/snapshot/cost-pace-model-mix.json, fixtures/snapshot/cost-pace-junk-degrades-only-itself.json, rust/tests/fixtures.rs</files>
  <action>
    1. In rust/tests/fixtures.rs, extend check_usage with match arms for the four new numeric
       expectation keys via check_optional_number, and add an optional-string comparison for
       pace_label and model_mix (a small sibling of check_optional_number, comparing
       Option&lt;&amp;str&gt; against a JSON string or null). Without these arms a fixture naming
       the new fields fails as an unknown field, which is the corpus working as designed.

    2. In fixtures/generate.py, add two F entries following the existing entry shape:
       - cost-pace-model-mix: every new field present with realistic values; expect asserts
         each normalized value, including the condensed model_mix string exactly as the
         daemon would have built it.
       - cost-pace-junk-degrades-only-itself: cost_usd a numeric string, pace_elapsed_pct a
         bool, pace_label an object, model_mix an array, alongside a valid used_percentage /
         resets_at_epoch / burn_rate_per_min trio; expect asserts the 5h numbers survive and
         all four junk fields normalize to null. Write the note field so it states what the
         fixture pins and why, matching the corpus voice.
       Do not add a hostile-text fixture here -- that behaviour is pinned by the snapshot.rs
       unit test in Task 2, and the corpus already carries a hostile-controls case for the
       display-string boundary.

    3. Regenerate the corpus with `python3 fixtures/generate.py` and commit the two new
       files. The count assertion in fixtures.rs is a floor (&gt;= 15), so it needs no bump;
       confirm the new total in the generator's printed output.

    4. Run both gates plus an eyeball render of the new fixture through the real renderer, on
       the MAIN checkout (never a worktree-isolated build against the deployed symlink).
  </action>
  <verify>
    <automated>python3 fixtures/generate.py &amp;&amp; just check &amp;&amp; just lint &amp;&amp; just rust-lint</automated>
    <human-check>`just rust-fixture cost-pace-model-mix -- --once` shows the detail row under the 5h row with the cost, pace and model cells; `just rust-fixture missing-optional-fields -- --once` is unchanged from before this task.</human-check>
  </verify>
  <done>Both gates green (`just selfcheck` exit 0, `cargo test` passing), ruff and clippy clean, the two new fixtures load and assert, and rendering an old fixture is byte-identical to its pre-change output.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| claude-monitor CLI stdout -> parse_usage | CLI-controlled text (`pace.label`, `model_distribution[].family`) derived from files under ~/.claude/projects; untrusted display text |
| daemon socket line -> Rust client | JSON the Rust client must decode wholesale; one bad token fails the entire fetch |
| usage row string -> terminal / GTK menu | Control sequences reaching a real TTY execute |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-klg-01 | Tampering | `pace.label` / `model_distribution[].family` -> terminal | high | mitigate | `_safe_cell` + length bound at parse (Task 1), `sanitize_display_bounded` again at the Rust snapshot boundary (Task 2), unit-tested with CSI/OSC/bidi input |
| T-klg-02 | Denial of Service | non-finite cost/pace number -> `json.dumps` -> serde_json | high | mitigate | reject non-finite at parse so the socket line never carries an `Infinity`/`NaN` token; asserted in `--selfcheck` (Task 1) |
| T-klg-03 | Denial of Service | unbounded `model_distribution` length -> row width / menu | medium | mitigate | entry cap (2) plus per-family and whole-string character bounds (Task 1); panel clips rather than wraps |
| T-klg-04 | Tampering | junk in a new field collapsing the whole usage section | medium | mitigate | per-field degradation on both sides, pinned by the junk fixture (Task 3) and the snapshot unit test (Task 2) |
| T-klg-SC | Tampering | package installs | low | accept | no dependency is added by this task |
</threat_model>

<verification>
- `just selfcheck` exits 0 (the mandated gate).
- `just lint` (ruff) clean.
- `just rust-test` (cargo test) and `just rust-lint` (clippy -D warnings) clean.
- `just check` runs both gates in one shot.
- Old fixtures render byte-identically; only the new fixtures show the detail row.
</verification>

<success_criteria>
- The tray menu, the socket snapshot, and the Rust dashboard all show cost, pace and model
  mix when the CLI supplies them, and all three are unchanged when it does not.
- One row definition exists per language (`core.usage_extra_row`, `format::usage_extra_row`);
  no surface formats a dollar amount, a pace percent or a model family on its own.
- Every new field is optional end to end; no new field can degrade the 5h payload.
- No new dependency, no new poll, no new data source.
</success_criteria>

<output>
Create `.planning/workstreams/notifications-predictive-alerts/quick/260725-klg-add-cost-pace-and-model-mix-to-the-usage/260725-klg-SUMMARY.md` when done
</output>
