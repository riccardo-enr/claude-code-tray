---
quick_id: 260712-ndo
slug: api-official-usage
date: 2026-07-12
---

# Quick Task 260712-ndo: Use official /usage numbers via --api

## Goal

Make the tray report the same official OAuth usage numbers as Claude Code's
`/usage` (authoritative used_percentage + reset time) instead of the P90 local
estimate, by passing `--api` to `claude-monitor`.

## Constraint discovered before implementing

`--api` returns `used_percentage` + `resets_at_epoch` but leaves
`tokens_used` / `token_limit` **null** (the official endpoint reports
percentages, not absolute tokens). The existing `parse_usage()` guard required
all five fields numeric, so `--api` alone made `fetch_usage()` return None ->
tray would show "usage unavailable" and lose the token row. Chosen resolution
(user decision): switch to official %, drop the absolute token counts.

## Tasks

1. Add `--api` to the poll command in `fetch_usage()` (claude-monitor.py).
2. Relax `parse_usage()`: essentials (used_percentage, resets_at_epoch,
   burn_rate_per_min) stay strictly numeric; tokens_used/token_limit accepted as
   numeric-OR-null, still rejecting non-numeric junk (strings).
3. `usage_rows()`: render "N% used" when token counts are null; keep the
   "72k / 88k (82%)" form when the P90 fallback still carries tokens.
4. Add a `--selfcheck` case for the official null-token payload (valid, not a
   crash) and for non-numeric token junk (still rejected).

## Verify

- `python3 claude-monitor.py --selfcheck` prints `ok`.
- Live `fetch_usage()` returns a dict with tokens_used=None and a numeric
  used_percentage matching `/usage`; usage row renders "N% used".

## Notes

Weekly-limit display (limits.seven_day, also unlocked by --api) is intentionally
NOT in scope here — parked in SEED-003. Forecast anchoring is SEED-002.
