---
quick_id: 260712-ndo
slug: api-official-usage
date: 2026-07-12
status: complete
---

# Quick Task 260712-ndo: Summary

## What changed

`claude-monitor.py` — the tray now polls with `--api`, reporting the official
OAuth usage numbers (same as Claude Code's `/usage`) instead of the P90 local
estimate.

- `fetch_usage()`: added `--api` to the command.
- `parse_usage()`: split the numeric guard — essentials (used_percentage,
  resets_at_epoch, burn_rate_per_min) must be numeric; tokens_used/token_limit
  are now optional (numeric-or-null), with non-numeric junk still rejected.
- `usage_rows()`: renders "N% used" when token counts are null; keeps
  "72k / 88k (82%)" when the fallback path still carries absolute tokens.
- `demo()`: added self-checks for the official null-token payload (valid) and
  non-numeric token junk (rejected).

## Verification (behavioral, not just tests)

- `python3 claude-monitor.py --selfcheck` -> `ok`.
- Live `fetch_usage()` returned
  `{'tokens_used': None, 'token_limit': None, 'used_percentage': 9.0,
  'resets_at_epoch': 1783885200, 'burn_rate_per_min': 643147.45}` — official %,
  no crash, no "usage unavailable".
- Rendered rows: `9% used` / `resets in 4h 42m` / `burn: ...`.

## Trade-off accepted

The tray no longer shows absolute token counts (72k / 88k) — the official
endpoint doesn't provide them. Percentages now match `/usage` exactly.

## Follow-ups (not in this task)

- [[SEED-003]] weekly (seven_day) limit — also unlocked by --api.
- [[SEED-002]] anchor the forecast to the official tokens_remaining.
- `ponytail:` --api hits an experimental/undocumented endpoint; it degrades to
  the P90 basis when stale/absent, so the poll never hard-fails.
