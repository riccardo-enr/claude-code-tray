---
phase: 260724-wdy
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - claude-tui.py
  - claude_monitor/core.py
  - claude_monitor/test_tui.py
  - claude_monitor/test_claude_monitor.py
autonomous: true
requirements: [QT-260724-wdy]

must_haves:
  truths:
    - "The 5-hour projection keeps its compact local HH:MM timestamp for both projected-at-reset and projected-exhaustion output."
    - "The weekly projection shows a local abbreviated weekday plus HH:MM for both projected-at-reset and projected-exhaustion output."
    - "Projection percentages, early/unavailable behavior, colors, and projection math remain unchanged."
  artifacts:
    - path: "claude_monitor/core.py"
      provides: "Pure local abbreviated-weekday-plus-time formatter alongside hhmm"
      exports: ["weekday_hhmm"]
    - path: "claude-tui.py"
      provides: "Window-aware projection timestamp selection in ClaudeTui._projection_text"
      contains: "_projection_text"
    - path: "claude_monitor/test_tui.py"
      provides: "Focused renderer coverage for 5-hour and weekly reset/exhaustion strings"
    - path: "claude_monitor/test_claude_monitor.py"
      provides: "Selfcheck coverage for the weekday-aware core formatter"
  key_links:
    - from: "claude-tui.py"
      to: "claude_monitor/core.py"
      via: "_projection_text selects core.weekday_hhmm only when win == core.WIN7 and otherwise retains core.hhmm"
      pattern: "WIN7.*weekday_hhmm|weekday_hhmm.*WIN7"
    - from: "claude_monitor/test_tui.py"
      to: "claude-tui.py"
      via: "Direct _projection_text assertions cover reset and exhaust branches for WIN5 and WIN7"
      pattern: "_projection_text"
---

<objective>
Correct the TUI's weekly projection timestamps so they identify the local day as well as the time, while preserving the existing compact 5-hour display.

Purpose: a bare HH:MM is sufficient inside a 5-hour window but ambiguous for a weekly reset or exhaustion several days away.
Output: one pure core formatter, window-aware rendering in `_projection_text`, and focused automated coverage for all four timestamp cases.
</objective>

<execution_context>
@/home/riccardo/.codex/gsd-core/workflows/execute-plan.md
@/home/riccardo/.codex/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/workstreams/notifications-predictive-alerts/STATE.md
@.planning/workstreams/notifications-predictive-alerts/quick/260724-hcm-tui-right-side-info-usage-projection-tre/260724-hcm-PLAN.md
@claude-tui.py
@claude_monitor/core.py
@claude_monitor/test_tui.py
@claude_monitor/test_claude_monitor.py

<interfaces>
From `claude_monitor/core.py`:
- `project(pct, reset, win, now)` returns `None`, `{"early": True}`, or `{"proj": float}` with an optional `"exhaust"` epoch. Its math and result contract are unchanged.
- `hhmm(epoch)` returns local `HH:MM` and remains the formatter for the 5-hour window.
- `WIN5` and `WIN7` are the exact window constants passed to `ClaudeTui._projection_text`.

From `claude-tui.py`:
- `ClaudeTui._projection_text(self, pct, reset, win, now) -> Text` owns both normal `proj NN% @...` and over-limit `out ~...` presentation.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Render weekday-aware weekly projection times without changing 5-hour output</name>
  <files>claude_monitor/test_claude_monitor.py, claude_monitor/test_tui.py, claude_monitor/core.py, claude-tui.py</files>
  <behavior>
    - Core formatter: a synthetic epoch formats as the local `%a %H:%M`, and its time suffix exactly matches `hhmm(epoch)`.
    - 5-hour normal projection: `_projection_text` remains `proj NN% @HH:MM`.
    - 5-hour exhaustion projection: `_projection_text` remains `out ~HH:MM`.
    - Weekly normal projection: `_projection_text` becomes `proj NN% @Day HH:MM`.
    - Weekly exhaustion projection: `_projection_text` becomes `out ~Day HH:MM`.
    - None and early projection results, percentage rounding, `core.band` styling, and red exhaustion styling remain unchanged.
  </behavior>
  <action>
  Start with failing focused assertions. In `claude_monitor/test_claude_monitor.py`, import and exercise a new `weekday_hhmm(epoch)` helper beside the existing `hhmm` assertion, comparing its weekday token with `time.strftime("%a", time.localtime(epoch))` and its time suffix with `hhmm(epoch)` so the test is deterministic in any local timezone. In `claude_monitor/test_tui.py`, call `ClaudeTui._projection_text` with synthetic reset/now values that drive both the ordinary projection branch and the over-100% exhaustion branch for `core.WIN5` and `core.WIN7`; assert each returned `Text.plain` against the appropriate core formatter. This renderer coverage must prove both that the weekly day appears and that the 5-hour text does not gain one.

  Add `weekday_hhmm(epoch)` next to `hhmm` in `claude_monitor/core.py`, implemented with the same `time.localtime(epoch)` basis and `time.strftime` using local abbreviated weekday plus 24-hour time (`%a %H:%M`). Keep `hhmm` unchanged to preserve its existing callers and compact contract.

  Update only timestamp selection inside `ClaudeTui._projection_text`: select `core.weekday_hhmm` when `win == core.WIN7`, otherwise select `core.hhmm`, then use the selected formatter for both the `"exhaust"` epoch and the normal reset epoch. Keep `core.project(pct, reset, win, now)` as the sole projection authority; do not modify projection arithmetic, branching, rounding, labels, or styles. Do not change countdown rows (`fmt_countdown` / `fmt_countdown_wk`), because this task concerns only the right-side absolute projection timestamp.
  </action>
  <verify>
    <automated>just selfcheck</automated>
    <automated>just tui-selfcheck</automated>
    <automated>just lint</automated>
  </verify>
  <done>The weekly reset and exhaustion projection strings include the local abbreviated weekday and HH:MM; their 5-hour counterparts remain HH:MM-only; existing unavailable/early, math, rounding, and styling behavior is preserved; focused core and TUI assertions pass with selfcheck, tui-selfcheck, and lint green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| daemon snapshot -> TUI | Numeric percentage and epoch values already cross the existing local socket boundary and are validated/degraded by existing projection logic. |
| epoch -> local display | The new formatter converts an existing numeric epoch through the process-local timezone and locale; it introduces no external input or I/O. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-QT-01 | Tampering | `_projection_text` window selection | mitigate | Select the weekday formatter only for the exact `core.WIN7` constant and retain `core.hhmm` for every other window; focused WIN5/WIN7 renderer assertions prevent scope drift. |
| T-QT-02 | Denial of Service | local epoch formatting | accept | `time.localtime`/`strftime` is the existing `hhmm` path and receives the same already-numeric projection epochs; no new data source or loop is introduced. |
| T-QT-SC | Tampering | package supply chain | accept | No package install, lockfile change, or new dependency is part of this task. |
</threat_model>

<source_audit>

| Source | ID | Feature/Requirement | Plan | Status | Notes |
|--------|----|---------------------|------|--------|-------|
| GOAL | — | Fix weekly projected time and show the day | 01 | COVERED | Core formatter plus window-aware renderer selection. |
| REQ | QT-260724-wdy | Weekly projection day with focused automated coverage | 01 | COVERED | One atomic task covers behavior and tests. |
| RESEARCH | — | No research artifact; quick task explicitly forbids a research phase | 01 | COVERED | Existing established patterns are sufficient (Level 0 discovery). |
| CONTEXT | Locked interpretation | Keep 5-hour HH:MM; weekly uses abbreviated weekday + HH:MM for reset and exhaustion | 01 | COVERED | All four render cases are explicit in behavior and done criteria. |
</source_audit>

<verification>
- `just selfcheck` proves the pure local weekday/time formatter contract and preserves all existing core assertions.
- `just tui-selfcheck` proves the normal and exhaustion renderer branches for both WIN5 and WIN7.
- `just lint` remains clean.
</verification>

<success_criteria>
- Weekly normal projection renders `proj NN% @Day HH:MM`.
- Weekly projected exhaustion renders `out ~Day HH:MM`.
- Both equivalent 5-hour strings remain HH:MM-only.
- No projection math, countdown formatting, runtime dependency, or unrelated TUI behavior changes.
- Focused core and renderer checks pass.
</success_criteria>

<output>
Create `.planning/workstreams/notifications-predictive-alerts/quick/260724-wdy-weekly-projection-day/260724-wdy-SUMMARY.md` when done.
</output>
