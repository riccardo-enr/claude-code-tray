---
phase: 02-usage-history-persistence
verified: 2026-07-12T00:00:00Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:

  - test: "Run `python3 claude-monitor.py` for several poll cycles and `tail -f ~/.claude/usage-history.jsonl`."
    expected: "Exactly one well-formed JSON line appears per successful poll; a degraded poll (rename/kill the CLI) adds no line while usage rows still update."
    why_human: "Requires the live GTK/AppIndicator tray and real polls; headless sandbox cannot import gi or drive poll_loop end-to-end. Code path is statically verified (append guarded by `usage is not None`, before idle_add) but the running-tray guarantee needs observation."

  - test: "Hand-seed an old record (a line with `t` set to now-40d) into ~/.claude/usage-history.jsonl, then restart the tray."
    expected: "The old record is pruned on startup and the file is rewritten whole (no partial/truncated file)."
    why_human: "Startup prune fires inside the live poll_loop daemon thread against the real on-disk file; the atomic rewrite logic is proven by harness but the live startup wiring needs one observed run."

  - test: "`chmod 000 ~/.claude/usage-history.jsonl` (or point HISTORY_PATH at an unwritable dir) with the tray running."
    expected: "The tray keeps running and usage rows keep updating; history just stops persisting (no crash, no freeze)."
    why_human: "The long-lived-tray resilience guarantee (SUMMARY D5) can only be confirmed by observing a running GTK process; the OSError-swallow code paths are proven non-raising by harness but not under the live main loop."
---

# Phase 02: Usage History Persistence Verification Report

**Phase Goal:** Every successful usage poll is durably recorded to a bounded, corruption-tolerant history store under ~/.claude/, reusing the existing background poll and never destabilizing the tray.
**Verified:** 2026-07-12
**Status:** human_needed
**Re-verification:** No — initial verification (assessed at current HEAD 38b14fd, post WR-01 fix)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | HIST-01: each successful poll appends one compact JSON line `{t,pct,tokens_used,token_limit,burn}`; `t=int(now)` not resets_at_epoch; burn raw per-minute; a None poll writes nothing | ✓ VERIFIED | `history_record` (150-163) builds exact schema; demo assert (322-328) pins `t=now0`, `burn=315615.2` raw; poll_loop (552-553) guards `if usage is not None: append_history(...)`; --selfcheck exits 0. Harness append -> 1 line confirmed. |
| 2 | HIST-02: records older than `now - HISTORY_DAYS*86400` pruned at startup + ~once/PRUNE_INTERVAL; HISTORY_DAYS default 30, env `CLAUDE_TRAY_HISTORY_DAYS` via guarded int/except; atomic temp-file + os.replace, never truncate-in-place | ✓ VERIFIED | Guarded env parse (59-62) mirrors POLL_INTERVAL; `history_keep` (166-172) predicate; `prune_history` (213-239) uses `tempfile.mkstemp(dir=os.path.dirname(HISTORY_PATH))` -> `os.replace`, `tmp=None` gate + finally cleanup; poll_loop startup prune (548) + `last_prune` timer (549,555-558). Harness: 40d record dropped, whole-file rewrite. |
| 3 | HIST-03: every file op swallows OSError; reader skips per-line json.loads failures, tolerating half-written trailing line | ✓ VERIFIED | `append_history` (206-210) and `prune_history` (222-233) wrap in `except OSError: return`; `parse_history` (186-197) per-line try/except keeps only dict with numeric `t` (WR-01 hardening, commit 352f9e3, reads `errors="replace"`). Harness: chmod-000 no raise, invalid UTF-8 + `42`/`null`/`[1,2]`/`{"t":"nope"}` all skipped, missing-file prune no-op. |
| 4 | All history I/O runs on the poll_loop daemon thread (never apply_usage, never Gtk main loop); no new thread and no new polling loop | ✓ VERIFIED | Call sites of append_history/prune_history/history_record only at lines 548,553,557 (all in poll_loop). apply_usage (432-447) and main (590-620) contain 0 history/HISTORY refs. main starts the same 3 daemon threads as v1.0 (serve, poll_loop, watch_focus) — no new thread. |
| 5 | v1.0 stays green: --selfcheck passes with every existing assert intact plus new record/retention/tolerant-parse asserts | ✓ VERIFIED | `python3 claude-monitor.py --selfcheck` exits 0, prints "ok". v1.0 asserts (parse_usage/fmt_tokens/build_label, 256-310) intact; new history asserts (312-341) added before single print. ast.parse -> parse-ok. |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

Note: Truths 1-3 have a live-tray confirmation surface (append-per-real-poll, startup prune on a live file, chmod-000 survival under the running GTK main loop) that a headless sandbox cannot drive. Their code contracts and function-level behavior are proven by static inspection plus a runtime round-trip harness; the end-to-end running-tray observation is routed to Human Verification below (per SUMMARY D4/D5 and the plan's Task 2 `<human-check>`), not counted as a failure.

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `claude-monitor.py` | extended in place, stdlib only, no new files/deps | ✓ VERIFIED | Single file; `import tempfile` (16) added; only stdlib json/os/time/tempfile + existing PyGObject; no created files (SUMMARY key-files.created: []). |
| HISTORY_PATH / HISTORY_DAYS / PRUNE_INTERVAL | config constants | ✓ VERIFIED | Lines 56, 59-62 (env-guarded), 64. |
| history_record / history_keep / parse_history | pure logic | ✓ VERIFIED | Lines 150, 166, 175. |
| append_history / prune_history | defensive atomic I/O | ✓ VERIFIED | Lines 200, 213. |
| poll_loop wiring + extended demo() | append + startup/opportunistic prune; new asserts | ✓ VERIFIED | poll_loop 548-558; demo 312-341. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| poll_loop (daemon) | append_history(history_record(usage, time.time())) | on success, BEFORE GLib.idle_add | ✓ WIRED | Lines 552-554: guard -> append -> idle_add ordering exact. |
| poll_loop | prune_history | startup (548) + in-process last_prune timer (555-558) | ✓ WIRED | Not in apply_usage/main. |
| prune_history | atomic rewrite | tempfile.mkstemp(dir=same) + os.replace | ✓ WIRED | Lines 226-231. |
| parse_history | corruption boundary | per-line json.loads try/except, numeric-t filter | ✓ WIRED | Lines 186-197; reused by history_keep and Phase 03. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| Pure-logic asserts | `python3 claude-monitor.py --selfcheck` | exit 0, "ok" | ✓ PASS |
| Module parses | `python3 -c "ast.parse(...)"` | parse-ok | ✓ PASS |
| Atomic prune drops 40d record, keeps 1d | round-trip harness | survivors == [1d record] | ✓ PASS |
| Corruption tolerance (invalid UTF-8 + scalars + bad-t) | round-trip harness | all garbage skipped, no raise | ✓ PASS |
| OSError swallow (chmod 000) | round-trip harness | no raise | ✓ PASS |
| Missing-file prune | round-trip harness | no-op, no raise | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| HIST-01 | 02-01 | Append one sample per successful poll; failed/degraded not recorded | ✓ SATISFIED | Truth 1; guarded append in poll_loop |
| HIST-02 | 02-01 | Prune older than retention window (default 30d, env-tunable) at startup + periodically | ✓ SATISFIED | Truth 2; atomic prune + guarded env |
| HIST-03 | 02-01 | Defensive I/O off Gtk main loop; tolerant reader | ✓ SATISFIED | Truths 3 & 4; OSError swallow + parse_history + poll-thread confinement |

All three PLAN-declared requirement IDs are present in REQUIREMENTS.md mapped to Phase 2. No orphaned requirements (TREND-01/02/03 map to Phase 3). No unaccounted IDs.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| — | — | No TODO/FIXME/XXX/HACK/PLACEHOLDER markers | ℹ️ Info | Clean; completion is auditable |

Code-review WR-01 (prune_history could be killed by non-OSError on a corrupt store) was FIXED at commit 352f9e3 and confirmed at HEAD: `parse_history` keeps only dicts with numeric `t`, and `prune_history` reads with `errors="replace"`. IN-01 accepted-by-design (relies on ~/.claude existing), IN-02 deferred (doc wording). No open blockers.

### Human Verification Required

Three live-tray confirmations that a headless environment cannot drive (GTK/AppIndicator + real polls). Code contracts and function behavior are already proven automatically; these confirm the running-tray guarantee (SUMMARY D4/D5, plan Task 2 `<human-check>`):

1. **One line per successful poll, none on degraded polls** — run `python3 claude-monitor.py` a few cycles, `tail -f ~/.claude/usage-history.jsonl`; kill/rename the CLI and confirm no line is added while usage rows still update.
2. **Startup prune on a live file** — seed a `t=now-40d` line, restart the tray; confirm it is pruned and the file is rewritten whole.
3. **chmod-000 / unwritable-dir survival** — with the tray running, make the file unwritable; confirm the tray keeps running and usage rows keep updating (history simply stops persisting).

### Gaps Summary

No gaps. Every automated/structural must-have is satisfied at current HEAD: the compact record schema, guarded-env retention, atomic temp-file+os.replace prune, total OSError/corruption tolerance, poll-thread confinement (no new thread or loop), and a green extended --selfcheck. The three remaining items are runtime observations of the live GTK tray that cannot be driven headlessly and are surfaced for human verification rather than counted as failures — hence status `human_needed`, not `passed`.

---

_Verified: 2026-07-12_
_Verifier: Claude (gsd-verifier)_
