---
id: SEED-002
status: dormant
planted: 2026-07-12
planted_during: v1.1 Phase 3 (Usage Trends in the Tray)
trigger_when: after v1.2 ships (web dashboard complete); milestone v1.3
scope: medium
---

# SEED-002: Predictive quota alerts and forecasting

## Why This Matters

Today the only proactive signal is a static >80% icon badge (ALERT-01) — it
fires when you're already almost out, with no lead time. The history store from
Phase 2 makes the burn rate a real time series, so we can forecast: "at this
burn you'll hit the limit in ~40m" and warn *before* the wall, not at it. Pair
that with actual desktop notifications (not just an icon change) so the user
doesn't have to be looking at the top bar to get the warning. Turns the tray
from passive gauge into proactive guard.

## When to Surface

**Trigger:** after v1.2 (web dashboard) ships — surface during
`/gsd-new-milestone`. Candidate scope for v1.3.

## Scope Estimate

**Medium** — a phase or two. Reuses existing poll + history; no new deps beyond
the desktop-notification path.

Likely lazy shape (stdlib + PyGObject, matching project constraints):
- Forecast: extrapolate remaining-tokens / current-burn to a projected
  time-to-limit; simple linear from the recent window, refine only if noisy.
  `ponytail:` naive linear extrapolation, add smoothing/trend-fit only if the
  estimate visibly jitters.
- Notification: desktop notify via `Gio.Notification` / `Notify` (already have
  PyGObject) at configurable thresholds (e.g. "30m to limit", ">90%"), with
  de-dupe so it fires once per crossing, not every poll.
- Open questions for planning: threshold config surface (env vars vs. menu);
  whether forecast also lands in the v1.2 dashboard.

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
