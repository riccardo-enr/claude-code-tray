---
phase: 06-notification-control-config
plan: 01
subsystem: notification-config
tags: [config, persistence, mute-gate, badge-threshold]
status: complete
dependency-graph:
  requires: [NOTIF-01, ALERT-02, ALERT-03, ALERT-04]
  provides:
    - "parse_config / load_config / save_config (tolerant JSON config layer)"
    - "notif_allowed(kind, config) -- config-driven mute gate"
    - "build_label(usage, attention, threshold=USAGE_THRESHOLD) -- configurable badge threshold"
    - "Monitor.config -- loaded before first rebuild_menu()"
  affects:
    - "06-02 (menu UI): consumes self.config, save_config, DEFAULT_CONFIG, THRESHOLD_CHOICES"
tech-stack:
  added: []
  patterns:
    - "Atomic single-JSON-object config write (tempfile.mkstemp + os.fdopen + os.replace), mirroring prune_history's JSONL pattern"
    - "Per-key tolerant parse: one malformed key falls back to its own default, not the whole file"
key-files:
  created: []
  modified:
    - claude-monitor.py
decisions:
  - "Config constants (CONFIG_PATH, THRESHOLD_CHOICES, DEFAULT_CONFIG, NOTIF_KEYS) land immediately after URGENCY_CRITICAL, before notif_allowed -- matches plan's exact insertion point"
  - "usage_threshold rejection is exact-membership-in-THRESHOLD_CHOICES, never rounded/snapped to nearest preset"
metrics:
  duration: 8 min
  completed: 2026-07-16
---

# Phase 6 Plan 1: Config data layer, mute gate, badge threshold Summary

Tolerant per-key JSON config loader/atomic writer for `~/.claude/tray-config.json`, a
config-driven rewrite of the `notif_allowed` mute gate (mute short-circuits before the
per-event lookup, D-04), and a `build_label` threshold parameter defaulting to the
existing `USAGE_THRESHOLD` constant -- no menu UI yet, that's Plan 2.

## What Was Built

**Task 1 -- Tolerant config load + atomic config save.** Added four module constants
(`CONFIG_PATH`, `THRESHOLD_CHOICES`, `DEFAULT_CONFIG`, `NOTIF_KEYS`) and three module
functions (`parse_config`, `load_config`, `save_config`) immediately after
`URGENCY_CRITICAL`. `parse_config` never raises: malformed JSON or a non-dict root falls
back to the full default; each of the five boolean keys and `usage_threshold` is validated
independently, so one bad key never discards the rest of a valid file.  `save_config` uses
the exact temp-file + `os.replace` + `finally`-cleanup shape `prune_history` already uses,
adapted from per-line JSONL to a single `json.dump`.

**Task 2 -- Wire the config-driven gate and configurable threshold.** `notif_allowed` is
now `notif_allowed(kind, config)`, returning `not config["mute_all"] and
config[NOTIF_KEYS[kind]]` -- mute wins unconditionally, the per-event flag is read but
never itself resets the mute state. `build_label` gained a `threshold=USAGE_THRESHOLD`
third parameter, both reads of the old module-level constant inside `hot = ...` replaced
with it. `Monitor.config = load_config()` is now the first statement in `__init__`,
executing before `self.rebuild_menu()` runs at the end of `__init__`. Both call sites
(`emit_notif`, `rebuild_menu`) updated to pass `self.config`. The stale "do NOT add an env
lookup" comment above `USAGE_THRESHOLD` was replaced with a note that the value is now
overridable via the config file and (in Plan 2) the tray menu.

**Task 3 -- Pin the behavior into `--selfcheck`.** Added three assertion groups to `demo()`
before the closing `print("ok")`: eight `parse_config` cases (the file-I/O-free subset of
Task 1's behavior spec -- `load_config`/`save_config` stay proven only by the temp-directory
script, per Task 1's acceptance criteria), four `notif_allowed` cases covering mute-wins,
per-event-blocks-independently, both-open-allows, and the `5h` cap-kind key, and three
`build_label` threshold-boundary cases (at-threshold not hot, one-over is hot, a lowered
custom threshold changes what counts as hot). Verified all four required mutation checks
(loosening the bool guard, loosening the threshold membership test, `and`->`or` in the
gate, `>`->`>=` in the threshold comparison) each independently make `--selfcheck` fail,
then reverted every mutation before committing.

## Deviations from Plan

None - plan executed exactly as written.

## Verification

- `python3 claude-monitor.py --selfcheck` exits 0 and prints `ok` after every task.
- Temp-directory round-trip script (missing file, malformed file x2 same result, full
  round-trip, byte-identical double-write) passes.
- All AST-based signature/ordering acceptance checks from the plan pass (`parse_config`,
  `load_config`, `save_config` signatures; `notif_allowed(kind, config)`;
  `build_label(usage, attention, threshold)` with exactly one default; `self.config`
  assigned before `rebuild_menu()` inside `__init__`).
- `grep -c 'do NOT add an env lookup'` returns 0 -- stale comment removed.
- `LC_ALL=C grep -nP '[^\x00-\x7F]' claude-monitor.py` returns only the pre-existing
  `SPARK_GLYPHS` sparkline-glyph lines (unrelated to this plan, present in HEAD before this
  plan started) -- no new non-ASCII characters introduced.
- All four Task 3 mutation checks independently fail `--selfcheck`; the working tree is
  byte-identical to pre-mutation state after each revert (`diff` confirmed empty).

## Known Stubs

None.

## Self-Check: PASSED

- FOUND: `claude-monitor.py` contains `CONFIG_PATH`, `THRESHOLD_CHOICES`, `DEFAULT_CONFIG`,
  `NOTIF_KEYS`, `parse_config`, `load_config`, `save_config`, `notif_allowed(kind, config)`,
  `build_label(usage, attention, threshold=USAGE_THRESHOLD)`, `Monitor.config`.
- FOUND: commit `df6a741` (Task 1), `7ff578e` (Task 2), `60f1a57` (Task 3) all present in
  `git log --oneline`.
