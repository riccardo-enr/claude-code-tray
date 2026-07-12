---
status: testing
phase: 02-usage-history-persistence
source: [02-VERIFICATION.md]
started: 2026-07-12T00:00:00Z
updated: 2026-07-12T00:00:00Z
---

## Current Test

number: 1
name: Live tray appends one JSONL line per successful poll, none on degraded polls
expected: |
  Running `python3 claude-monitor.py` for several poll cycles and `tail -f ~/.claude/usage-history.jsonl`
  shows exactly one well-formed JSON line per successful poll; a degraded poll (rename/kill the
  claude-monitor CLI) adds no line while the usage rows in the tray menu still update.
awaiting: user response

## Tests

### 1. Append-per-poll on the live tray
expected: Run `python3 claude-monitor.py` for several poll cycles and `tail -f ~/.claude/usage-history.jsonl` — exactly one well-formed JSON line appears per successful poll; a degraded poll (rename/kill the CLI) adds no line while usage rows still update.
result: [pending]

### 2. Startup prune of an old record, atomic whole-file rewrite
expected: Hand-seed an old record (a line with `t` set to now-40d) into `~/.claude/usage-history.jsonl`, then restart the tray. The old record is pruned on startup and the file is rewritten whole (no partial/truncated file).
result: [pending]

### 3. Unwritable history file leaves the tray running
expected: With the tray running, `chmod 000 ~/.claude/usage-history.jsonl` (or point HISTORY_PATH at an unwritable dir). The tray keeps running and usage rows keep updating; history just stops persisting (no crash, no freeze).
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
