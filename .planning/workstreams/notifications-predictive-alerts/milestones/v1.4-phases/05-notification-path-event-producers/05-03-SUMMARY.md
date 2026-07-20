---
phase: 05-notification-path-event-producers
plan: 03
subsystem: notifications
tags: [notifications, quota, alerts, projection, pure-function, state-machine]
status: complete

requires:
  - "05-01: Monitor.emit_notif, URGENCY_NORMAL, the ('cap', cap) slot keys, the ('dash',) action tuple, Monitor.open_dashboard"
provides:
  - "WIN5 / WIN7 / ALERT_LEAD module constants"
  - "project(pct, reset, win, now) -- pure Python port of the QUOTA-03 JS projection"
  - "hhmm(epoch) -- local wall-clock formatter (D-08)"
  - "alert_due(p, now) -- the D-05/D-07 lead-time predicate"
  - "alert_should_fire(armed_reset, reset, p, now) -- the D-06/ALERT-04 arm/re-arm predicate"
  - "Monitor.alert_armed -- per-cap armed-window dict"
  - "the ALERT producer wired into poll_loop's existing per-tick body"
affects:
  - "claude-monitor.py"

tech-stack:
  added: []
  patterns:
    - "Projection ported from JS to Python as pure functions, asserted in --selfcheck instead of against a live clock"
    - "Arm/re-arm via a stored resets_at_epoch, not a timer -- a changed epoch IS the new window"

key-files:
  created: []
  modified:
    - "claude-monitor.py"

decisions:
  - "alert_due tests membership on the 'exhaust' key, never 'proj >= 100' -- project() sets 'exhaust' only when proj > 100 strictly, so testing proj first would KeyError at exactly 100.0"
  - "No re-arm on the projection dipping under 100 and climbing back inside the same window -- only a changed resets_at_epoch re-arms (avoids flapping at the boundary, D-06)"
  - "7-day fields read via .get(...); project()'s and alert_should_fire's own _is_num guards degrade an absent 7d block to silence, so no second guard was added at the call site"

metrics:
  duration: "not tracked live -- see Provenance note"
  completed: 2026-07-14
  tasks: 3
  commits: 3
  files_changed: 1
---

# Phase 05 Plan 03: Predictive Quota Alert Producer Summary

Second producer proves the shared emit path generalizes: `project()` (the QUOTA-03 JS
formula) ported to Python as four pure functions, an arm/re-arm dict keyed on
`resets_at_epoch`, and one emit inside `poll_loop`'s existing per-tick body.

> **Provenance:** written retroactively by `/gsd-execute-phase 5` on 2026-07-16. Tasks 1-3
> were already committed and Phase 5 was already closed (`8b13272`, UAT PASS 5/5) on
> 2026-07-14, but this SUMMARY.md was never written -- the executor session ended before that
> step, and the workstream split (`a435708`) carried the gap forward. Reconstructed from the
> three task commits, `05-03-PLAN.md`, and `05-UAT.md`; every acceptance criterion in the plan
> was re-verified against current HEAD (`--selfcheck` plus the plan's own AST/grep checks)
> before this file was written -- see Verification below.

## What Was Built

**Task 1 (`cfc6a45`)** -- `WIN5`/`WIN7`/`ALERT_LEAD` constants and four pure module functions:
`project(pct, reset, win, now)` (verbatim port of the JS at `claude-monitor.py:931`, `now`
passed in rather than read from the clock), `hhmm(epoch)`, `alert_due(p, now)`, and
`alert_should_fire(armed_reset, reset, p, now)`. The JS copy stays -- it recomputes against a
live browser clock as the static dashboard page ages; same arithmetic, two clocks.

**Task 2 (`7f7f6a8`)** -- all 10 `project()` cases from RESEARCH pinned in `demo()` on
synthetic epochs, plus the full `alert_due`/`alert_should_fire` matrix: the exactly-100.0
boundary (no `exhaust` key), the window-roll re-arm (ALERT-04), and D-07's
already-exhausted-cap-stays-silent claim. Mutation-checked: relaxing the early guard, zeroing
`ALERT_LEAD`, dropping the `armed_reset == reset` clause, and relaxing either exhaust guard
each make `--selfcheck` exit non-zero.

**Task 3 (`86164c3`)** -- `Monitor.alert_armed = {}` added alongside `notif_slots`/
`notif_acts`; the alert evaluation wired into `poll_loop`'s existing guarded per-tick body,
iterating `("5h", used_percentage, resets_at_epoch, WIN5, "5-hour quota")` and
`("7d", seven_day_pct, seven_day_reset, WIN7, "7-day quota")`. On fire: `emit_notif` with slot
`("cap", cap)`, body `"Projected %d%% at reset -- runs out ~%s"`, action `("dash",)`,
`URGENCY_NORMAL`; then `alert_armed[cap] = reset`. No new thread, poll, or data source -- every
value comes from the `usage` dict `parse_usage` already produces on the existing tick.

## Landmines Respected

| Landmine | How it landed |
|----------|---------------|
| `proj >= 100` then `p["exhaust"]` KeyErrors at exactly 100.0 (Pitfall 7) | `alert_due` tests `'exhaust' in p` only -- the projection test is never written, structurally impossible |
| Re-arming on projection dipping and climbing within the same window (flapping) | `alert_should_fire` re-arms ONLY on `armed_reset != reset` -- no clock, no timer |
| 7-day block absent on an older CLI | Read via `.get(...)`; `project()`'s and `alert_should_fire`'s own `_is_num` guards degrade to silence, no second guard added |
| A malformed/skewed `now` (negative elapsed fraction) | `e <= 0.05` catches it and returns `{"early": True}`, not a garbage projection |
| Payload-derived string reaching the markup-parsed body (T-05-07) | Body interpolates only `round(p["proj"])` and `hhmm(p["exhaust"])` -- both values computed by us, nothing from the CLI payload |

## Verification (re-run against current HEAD, 2026-07-16)

- `python3 claude-monitor.py --selfcheck` -> `ok`, exit 0.
- Function signatures, `WIN5`/`WIN7`/`ALERT_LEAD` constants (3), JS `project` untouched,
  `Monitor.alert_armed` in `__init__`, and the `poll_loop` wiring (`alert_should_fire` +
  `emit_notif` + `project` all present) -- every plan AST/grep acceptance criterion re-checked,
  all pass.
- `alert_due`'s only `Subscript` node is `p['exhaust']`, confirmed via AST walk -- the plan's
  naive grep-for-`'proj'` check flags a false positive (the docstring explains the KeyError
  trap in prose, and `ast.dump` includes docstrings; same defeat pattern already called out
  twice this phase, per STATE.md).
- ASCII: the file's only non-ASCII line (`SPARK_GLYPHS`, `claude-monitor.py:150`) predates
  this plan by two phases (introduced in `d0ed008`, Phase 03) -- confirmed present before
  `cfc6a45`. Not a regression from this plan.
- Assertion coverage: 13 `project()` asserts, 10 `alert_should_fire` asserts, 4 `alert_due`
  asserts -- all exceed the plan's stated minimums (10 / 7 / 2).
- Live UAT (2026-07-14, recorded in `05-UAT.md`): SC3 and SC4 both PASS. Both route through
  the `--selfcheck` asserts above rather than a separate live observation.

## Deviations from Plan

None found in the shipped code -- every acceptance criterion in the plan passes as written.

## Issues Encountered

None in the implementation. The only gap was process, not code: the SUMMARY.md step was
skipped at the end of Task 3's session (see Provenance above).

## Threat Flags

None new. T-05-07 (body markup injection) mitigated structurally -- only `round()`/`strftime`
outputs reach the body. T-05-09 (division DoS) -- three divisions, three structural guards
(`/ win`, `pct / e` gated by the early-exit, `100.0 / pct` gated by `pct > 0`), asserted via
the Task 2 mutation checks.

## Self-Check: PASSED

- `claude-monitor.py` exists, parses, `--selfcheck` -> `ok`, exit 0.
- Commits `cfc6a45`, `7f7f6a8`, `86164c3` all found in `git log`.
- Phase 5 was already marked complete in ROADMAP.md/STATE.md (`8b13272`, 2026-07-14) with UAT
  PASS 5/5 recorded in `05-UAT.md`. This SUMMARY closes the one missing artifact from that
  closure -- no code, ROADMAP, or UAT changes required.

---
*Phase: 05-notification-path-event-producers*
*Completed: 2026-07-14 (commits) / SUMMARY written 2026-07-16*
