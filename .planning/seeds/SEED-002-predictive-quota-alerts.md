---
id: SEED-002
status: dormant
planted: 2026-07-12
planted_during: v1.1 Phase 3 (Usage Trends in the Tray)
trigger_when: after v1.2 ships (web dashboard complete); milestone v1.3
scope: small
---

# SEED-002: Predictive quota alerts (surface claude-monitor's forecast + notify)

## Why This Matters

Today the only proactive signal is a static >80% icon badge (ALERT-01) — it
fires when you're already almost out, with no lead time. We can warn *before*
the wall and push a real desktop notification so the user doesn't have to be
watching the top bar.

**Key finding (2026-07-12): we do NOT need to build a forecaster.**
`claude-monitor --output json --once` (the call the tray already makes) emits a
top-level `forecast` block the tray currently ignores:

```
forecast.predicted_tokens_exhausted_epoch   # when tokens run out
forecast.minutes_remaining                  # e.g. 38.4
forecast.tokens_remaining
forecast.display                            # pre-formatted human string
forecast.basis = "input_output_tokens_per_minute"
```

Method (claude_monitor/output/snapshots.py:284-300): plain linear
extrapolation — `io_burn = totalTokens / durationMinutes` (input+output only,
cache excluded so the basis matches tokens_remaining), then
`minutes_remaining = tokens_remaining / io_burn`. No smoothing/trend-fit. So the
"naive linear extrapolation" originally scoped here already exists upstream.

## When to Surface

**Trigger:** after v1.2 (web dashboard) ships — surface during
`/gsd-new-milestone`. Candidate scope for v1.3.

## Scope Estimate

**Small** — one phase. The forecast math already exists upstream; this is a
read + notify job, not a modeling job. No new deps (PyGObject already present).

Lazy shape (stdlib + PyGObject):
1. Extend `parse_usage()` in claude-monitor.py to pull the `forecast` block
   (it currently reads only `limits.five_hour` + `local.burn_rate`). Degrade to
   None if absent, same as existing fields.
2. Show `forecast.display` / `minutes_remaining` as a tray menu row.
3. New work: desktop notification via `Gio.Notification` (PyGObject) at
   thresholds (e.g. "~30m to limit", ">90%"), with de-dupe so it fires once per
   crossing, not every poll.
- Open questions for planning: threshold config surface (env vars vs. menu);
  whether the forecast row also lands in the v1.2 dashboard (`[[SEED-001]]`).
- `ponytail:` if upstream's linear forecast ever proves too jittery, smooth
  using our own Phase-2 history — but only then; don't pre-build it.

## Breadcrumbs

- `claude-monitor.py` — tray helper; ALERT-01 badge logic is the current
  (reactive) alerting to extend.
- `~/.claude/usage-history.jsonl` — burn-rate time series feeding the forecast.
- ROADMAP.md Phase 1 (ALERT-01 badge) — this seed makes that alerting
  predictive + push-based.
- [[SEED-001]] — the v1.2 dashboard is a natural place to also show the forecast.

## Notes

Captured via seed capture. Trigger/why/scope filled in at capture time.
Direction chosen over cost-tracking, multi-machine sync, and session analytics.
