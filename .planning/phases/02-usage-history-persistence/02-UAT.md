---
status: complete
phase: 02-usage-history-persistence
source: [02-VERIFICATION.md]
started: 2026-07-12T00:00:00Z
updated: 2026-07-12T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Append-per-poll on the live tray
expected: Run `python3 claude-monitor.py` for several poll cycles and `tail -f ~/.claude/usage-history.jsonl` — exactly one well-formed JSON line appears per successful poll; a degraded poll (rename/kill the CLI) adds no line while usage rows still update.
result: pass
note: Confirmed against live ~/.claude/usage-history.jsonl — 3 poll cycles produced 3 full-schema lines (t,pct,tokens_used,token_limit,burn), values matching the tray (104k/913k, 11%, burn raw-per-minute 237310 tok/min x60 = 14.2M tok/hr as shown). tail -f output corroborated by user.

### 2. Startup prune of an old record, atomic whole-file rewrite
expected: Hand-seed an old record (a line with `t` set to now-40d) into `~/.claude/usage-history.jsonl`, then restart the tray. The old record is pruned on startup and the file is rewritten whole (no partial/truncated file).
result: pass
note: Seeded a 40d-old marker (pct 99.9) into the live file, user restarted the tray. Post-restart: marker gone (pruned on startup), 10 recent records survived, 0 malformed lines (valid whole JSONL, no truncation), tray still appending. HIST-02 confirmed on-disk.

### 3. Unwritable history file leaves the tray running
expected: With the tray running, `chmod 000 ~/.claude/usage-history.jsonl` (or point HISTORY_PATH at an unwritable dir). The tray keeps running and usage rows keep updating; history just stops persisting (no crash, no freeze).
result: pass
note: chmod 000 on the live file with the tray running — user confirmed the tray stayed up. File stayed at 1358 bytes (append swallowed, no growth, no corruption); after chmod 600 it grew again (persistence resumed). Record gap ...291 -> ...446 (155s) = the unwritable window where polls continued but weren't persisted. 14 valid, 0 malformed throughout. HIST-03 confirmed live.

## Summary

total: 3
passed: 3
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
