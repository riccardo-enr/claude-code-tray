---
id: SEED-003
status: dormant
planted: 2026-07-12
planted_during: v1.1 Phase 3 (Usage Trends in the Tray)
trigger_when: after v1.2 ships; pairs with v1.3 (SEED-002 already needs --api)
scope: small
---

# SEED-003: Weekly (7-day) limit monitoring in the tray

## Why This Matters

The tray tracks only the rolling 5-hour window (`limits.five_hour`). But the
plan also has a **weekly quota** — Claude Code's `/usage` shows "Current week
(all models): 31% used, resets Jul 17" plus a separate per-model weekly bucket
(e.g. Fable 0%). You can sit comfortably on the 5h window while quietly draining
the week — and the tray gives zero warning, which defeats its core value ("know
how much quota is left without opening a terminal").

Discovered 2026-07-12 comparing `/usage` against the tray: they disagreed
because the tray never sees the weekly limit at all.

## When to Surface

**Trigger:** after v1.2 ships. Naturally pairs with SEED-002 (v1.3), since both
depend on the same `--api` change.

## Scope Estimate

**Small** — one phase, no new deps. The data is already one flag away.

Verified: `claude-monitor --output json --once --api` populates
`limits.seven_day` with `used_percentage` / `resets_at_epoch` (returned 31%
weekly, matching `/usage` exactly). WITHOUT `--api` the whole `seven_day` block
is null — which is why the tray can't show it today.

Lazy shape:
1. Add `--api` to the poll command (shared prerequisite with SEED-002).
2. Extend `parse_usage()` to also read `limits.seven_day` (same numeric-guard
   degradation as five_hour; `seven_day` is null on P90-only fallback, so treat
   null as "weekly unavailable", never crash).
3. Show a weekly row + reset countdown alongside the 5h row; optionally a second
   badge threshold on weekly %.
- `ponytail:` per-model weekly buckets (Fable/Opus separately) — the `/usage`
  screen shows them, but only add if the all-models weekly proves insufficient.
- Open question: does `--api`'s `experimental` confidence warrant a visual
  "estimated" marker on the weekly row? Decide at planning time.

## Breadcrumbs

- `claude-monitor.py` — `parse_usage()` reads only `limits.five_hour`; poll
  command lacks `--api`.
- `~/.local/.../claude_monitor/output/api_usage.py` — the opt-in OAuth usage
  reader (`--api` flag, endpoint `api.anthropic.com/api/oauth/usage`).
- [[SEED-002]] — same `--api` prerequisite; forecast anchoring + weekly display
  should land together.

## Notes

Split from SEED-002 because weekly monitoring is a distinct usage dimension, not
a prediction. Shares the `--api` enablement, so likely planned in the same
milestone.
