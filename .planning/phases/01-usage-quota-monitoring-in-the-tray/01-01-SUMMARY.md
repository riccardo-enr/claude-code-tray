---
phase: 01-usage-quota-monitoring-in-the-tray
plan: 01
subsystem: tray-usage-monitoring
tags: [tray, gtk, claude-monitor, usage, polling]
requires: [claude-monitor CLI v4.0.0 at ~/.local/bin/claude-monitor, PyGObject/Gtk3]
provides: [usage %/tokens row, live reset countdown, burn-rate row, high-usage icon badge, background usage poll]
affects: [claude-monitor.py]
tech-stack:
  added: []
  patterns: [daemon-thread + GLib.idle_add marshaling, env-var-with-default config, defensive error swallowing, assert-based --selfcheck]
key-files:
  created: []
  modified: [claude-monitor.py]
decisions:
  - Parse CLI stdout regardless of returncode (exit 11 == limit-hit carries valid JSON) so degradation never hides usage when it is highest.
  - Countdown recomputed locally on a GLib timer between 30s polls; the CLI is never re-shelled just to tick the clock.
  - USAGE_THRESHOLD hardcoded at 80 (env-configurability deferred per ALERT-F1).
metrics:
  duration: ~2 min
  completed: 2026-07-11
status: complete
---

# Phase 1 Plan 1: Usage & Quota Monitoring in the Tray Summary

Extended the 128-line `claude-monitor.py` tray helper to surface Claude Code 5-hour-window
quota in the top bar: a tokens/percent row, a live reset countdown, a burn-rate row, and a
high-usage icon badge, all fed by a non-blocking 30s background poll of the `claude-monitor`
CLI that degrades to "usage unavailable" without touching session status or click-to-focus.

## Tasks

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Usage parse/format/label logic + --selfcheck | bf3e782 | claude-monitor.py |
| 2 | Wire usage into the tray (poll thread, idle_add, live countdown, menu rows, icon label) | d29e9ab | claude-monitor.py |

## What was built

- `parse_usage(stdout)` — pure, returncode-independent JSON -> normalized dict (`tokens_used`,
  `token_limit`, `used_percentage`, `resets_at_epoch`, `burn_rate_per_min`) or None. This is what
  makes exit-code-11 read as available (POLL-02).
- `fetch_usage()` — fixed arg-list subprocess (no shell=True), `POLL_TIMEOUT`, swallows
  TimeoutExpired/FileNotFoundError to None, parses stdout regardless of returncode.
- `fmt_tokens` (k/M), `fmt_countdown` (`resets in Xh Ym` / `resets now`), `build_label`
  (usage-% badge + `!` above 80% + waiting badge reconciled onto one label surface).
- `demo()` + `--selfcheck` guard — assert-based check pinning the exit-code-11 degradation,
  over-limit percent (474%, never clamped), and burn*60 per-minute->per-hour conversion.
- `Monitor.usage_rows()` / `Monitor.apply_usage()` — usage menu rows and the idle_add redraw target.
- `poll_loop(mon)` daemon thread + `GLib.timeout_add_seconds` live-countdown tick wired in `main()`.

## Requirements satisfied

- USAGE-01 tokens/percent row (over-limit rendered as `474%`, not clamped).
- USAGE-02 live reset countdown, recomputed locally between polls.
- USAGE-03 per-hour burn rate (`burn_rate_tokens_per_minute * 60`).
- ALERT-01 icon label leads with usage %, appends `!` above 80%, then the waiting badge; falls
  back to waiting-only when usage is unavailable.
- POLL-01 background daemon-thread poll (~30s) marshaled via `GLib.idle_add`; Gtk never blocks.
- POLL-02 timeout / empty / parse-error / missing-CLI / missing-five_hour -> "usage unavailable";
  degradation never gates on `returncode == 0`.

## Verification

- `python3 claude-monitor.py --selfcheck` -> `ok` (exit 0).
- `python3 -c "import ast; ast.parse(...)"` -> `parse-ok`.
- Presence checks: `apply_usage`, `target=poll_loop`, `GLib.timeout_add_seconds`,
  `build_label(self.usage`, `self.usage = None` all present.
- Human-check (deferred to user): running the live GTK tray to confirm the three rows render,
  the icon badge leads with usage %, session rows still focus on click, and killing/renaming the
  CLI flips to "usage unavailable" while sessions keep working.

## Deviations from Plan

None - plan executed exactly as written.

## Threat surface

No new surface beyond the plan's threat_model. fetch_usage uses a fixed arg list (no shell=True),
POLL_TIMEOUT bounds the call, and parse_usage wraps json.loads in try/except — T-01-01 and
T-01-02 mitigations are in place.

## Self-Check: PASSED

- claude-monitor.py: FOUND
- Commit bf3e782 (Task 1): FOUND
- Task 2 commit: recorded in final metadata commit
