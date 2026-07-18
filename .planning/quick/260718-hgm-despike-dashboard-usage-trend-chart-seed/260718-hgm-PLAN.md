---
phase: 260718-hgm-despike-dashboard-usage-trend-chart-seed
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - claude-monitor.py
  - .planning/seeds/SEED-006-dashboard-usage-despike.md
autonomous: true
requirements: [SEED-006]

must_haves:
  truths:
    - "The dashboard 'Usage % over time' line chart no longer renders upstream 100% pins as spurious spikes: the 5h and weekly series pass through despike before with_gaps."
    - "A genuine window-reset drop (pct falling to ~0) and a real sub-RISE_MAX ramp both survive untouched -- only positive jumps > RISE_MAX are dropped."
    - "python3 claude-monitor.py --selfcheck exits 0, including a new despike assert."
  artifacts:
    - "claude-monitor.py (contains def despike, a pure stdlib helper next to with_gaps)"
  key_links:
    - "render_dashboard payload wraps both series as with_gaps(despike(...)) so gaps are computed on the cleaned series."
    - "despike shares RISE_MAX with heatmap_buckets -- one ceiling, two consumers."
---

<objective>
Implement SEED-006: despike the dashboard "Usage % over time" line chart (and its
weekly companion) by reusing the heatmap's EXISTING RISE_MAX outlier rejection.
Upstream claude-monitor pins pct=100 for a sample or two; the heatmap already drops
those (heatmap_buckets, rise > RISE_MAX), but the line chart plots raw pct.

Purpose: consistency, not new machinery -- apply the guard the heatmap already trusts
to the two line series. NO Kalman filter, NO numpy/scipy, NO new dependency.
Output: one pure helper despike(series, max_rise=RISE_MAX) in claude-monitor.py, both
payload series wrapped, one new --selfcheck assert; SEED-006 marked sprouted.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/seeds/SEED-006-dashboard-usage-despike.md
@claude-monitor.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add despike helper, wire both dashboard series, add selfcheck assert</name>
  <files>claude-monitor.py</files>
  <read_first>
    - claude-monitor.py lines 582-608 (RISE_MAX definition + docstring, with_gaps, usage7_series)
    - claude-monitor.py lines 552-568 (heatmap_buckets rise > RISE_MAX rejection -- the pattern to mirror)
    - claude-monitor.py lines 1054-1062 (render_dashboard payload building "usage" and "usage7")
    - claude-monitor.py lines 1074, 1380-1390 (selfcheck function; existing with_gaps / usage7_series asserts)
  </read_first>
  <behavior>
    - despike([[0, 5.0], [15, 100.0], [30, 8.0]]) returns [[0, 5.0], [30, 8.0]]: the 100 pin rises 95 (> RISE_MAX) above the previous KEPT sample 5.0 and is dropped; the following 8.0 is measured against 5.0 (rise 3), so it is kept.
    - despike([[0, 5.0], [15, 15.0], [30, 25.0]]) returns the input unchanged: each step rises 10 (< RISE_MAX), a genuine ramp survives whole.
    - A drop (negative jump, e.g. window reset to ~0) is never dropped -- only positive jumps above max_rise are rejected. The reference is always the previous KEPT sample, so consecutive pins ([5,100,100,8]) both drop.
  </behavior>
  <action>
    Add a pure function despike(series, max_rise=RISE_MAX) to claude-monitor.py placed
    immediately AFTER with_gaps (~line 603) and before usage7_series/the dashboard
    section -- so RISE_MAX (defined ~line 589) is already in scope. It walks the
    [[t, pct], ...] series in the given order (do NOT sort -- mirror with_gaps, which
    already assumes time order) and appends each [t, v] to the output UNLESS v rises
    more than max_rise above the pct of the previous KEPT sample, in which case it is
    skipped and the kept reference is unchanged. Only bound positive jumps; leave drops
    (negative deltas) alone so window-reset sawtooth edges survive. Input carries no None
    markers (it runs before with_gaps, on already-numeric records via history_numeric /
    _is_num), so no None handling is needed.

    Give it a codedoc-style triple-quoted docstring (ASCII only, no Unicode) that states
    WHY: it mirrors the rise > RISE_MAX rejection in heatmap_buckets so the chart and the
    heatmap agree on a believable one-sample jump; it is reject-and-drop (kept points are
    real samples only -- no synthesized midpoints, unlike a median smooth); and it must
    run BEFORE with_gaps so pen-up breaks are computed on the cleaned series. Reference
    the existing ponytail: note at RISE_MAX for the 100%-pin cause rather than repeating it.

    Wire it into the render_dashboard payload (~lines 1055-1056): change the "usage" value
    to with_gaps(despike([[int(r["t"]), r["pct"]] for r in records])) and the "usage7"
    value to with_gaps(despike(usage7_series(records))). despike is the inner call, with_gaps
    the outer.

    Add ONE assert-based check inside the --selfcheck function next to the existing
    with_gaps / usage7_series asserts (~line 1390), covering both behavior cases above and
    asserting on the exact returned lists (the pin dropped, the ramp preserved unchanged).
  </action>
  <verify>
    <automated>cd /home/riccardo/code/claude/claude-code-tray && python3 claude-monitor.py --selfcheck && grep -q 'def despike(' claude-monitor.py && grep -c 'with_gaps(despike(' claude-monitor.py | grep -qx 2</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n 'def despike(' claude-monitor.py` matches, and despike's default arg is max_rise=RISE_MAX.
    - `grep -c 'with_gaps(despike(' claude-monitor.py` returns 2 (both "usage" and "usage7" series wrapped).
    - `python3 claude-monitor.py --selfcheck` exits 0.
    - The new selfcheck asserts include a case where a 100 pin between low samples is removed and a case where a sub-RISE_MAX ramp is returned unchanged (grep the selfcheck region for `despike(` shows a `100` pin case dropped).
    - despike's docstring is a triple-quoted block, references RISE_MAX / heatmap_buckets consistency, and contains no Unicode characters.
    - No new import, no new dependency; the diff touches claude-monitor.py only.
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 2: Mark SEED-006 sprouted</name>
  <files>.planning/seeds/SEED-006-dashboard-usage-despike.md</files>
  <read_first>
    - .planning/seeds/SEED-006-dashboard-usage-despike.md lines 1-9 (frontmatter)
  </read_first>
  <action>
    In the SEED-006 frontmatter set status from planted to sprouted, and set
    sprouted_into to 260718-hgm. Change only those two frontmatter values; leave the
    body prose untouched.
  </action>
  <verify>
    <automated>grep -q '^status: sprouted$' /home/riccardo/code/claude/claude-code-tray/.planning/seeds/SEED-006-dashboard-usage-despike.md && grep -q '^sprouted_into: 260718-hgm$' /home/riccardo/code/claude/claude-code-tray/.planning/seeds/SEED-006-dashboard-usage-despike.md</automated>
  </verify>
  <acceptance_criteria>
    - SEED-006 frontmatter has `status: sprouted` and `sprouted_into: 260718-hgm`.
    - The seed body (Why This Matters, NOT a Kalman filter, etc.) is unchanged.
  </acceptance_criteria>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| history file -> render_dashboard | Records already pass history_numeric / _is_num; despike is a pure in-process transform over validated numeric [t, pct] pairs. No new input, no new parsing. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-hgm-01 | Tampering | despike output feeding dashboard JSON | low | accept | despike only drops elements from an already-validated numeric series; it emits no new strings and adds no dependency, so it cannot introduce injection. Existing script-injection selfcheck asserts (render_dashboard) still hold. |
</threat_model>

<verification>
Run `python3 claude-monitor.py --selfcheck` -- exits 0 with the new despike assert.
Confirm `grep -c 'with_gaps(despike(' claude-monitor.py` == 2 and `grep 'def despike(' claude-monitor.py` matches.
Confirm SEED-006 frontmatter shows status: sprouted / sprouted_into: 260718-hgm.
No new import lines; `git diff --stat` shows only claude-monitor.py and the seed file.
</verification>

<success_criteria>
- despike helper exists next to with_gaps, defaults to RISE_MAX, reject-and-drop on rises only.
- Both dashboard line series (5h "usage" and weekly "usage7") are despiked before with_gaps.
- One new selfcheck assert proves a 100 pin is dropped and a real ramp is preserved.
- stdlib only, ASCII only, no new dependency, minimal two-file diff.
- SEED-006 marked sprouted into 260718-hgm.
</success_criteria>

<output>
Create `.planning/quick/260718-hgm-despike-dashboard-usage-trend-chart-seed/260718-hgm-SUMMARY.md` when done.
</output>
