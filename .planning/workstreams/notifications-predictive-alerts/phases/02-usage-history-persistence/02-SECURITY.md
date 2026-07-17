---
phase: 02
slug: usage-history-persistence
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-07-12
---

# Phase 02 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| helper -> history file (`~/.claude/usage-history.jsonl`) | the helper writes and reads a JSONL file under the user's own home | numeric usage fields (tokens_used, token_limit, used_percentage, burn) + poll epoch — non-sensitive, same trust level as the tray |
| history file content -> `parse_history` | previously-written (possibly corrupt or half-written) file content is parsed back as JSON on prune/read | untrusted-shaped bytes from disk (could be corrupted, partial, or externally edited) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-02-01 | Tampering | `HISTORY_PATH` under `~/.claude` | low | accept | File lives under the user's own home at the same trust level as the tray. No privilege elevation; the writer serializes only its own numeric usage fields via `json.dumps` — no shell, no `eval`/`exec`, no `subprocess` in any history function (verified: history_record/keep/parse/append/prune are shell-free). | closed |
| T-02-02 | Denial of Service | unbounded file growth (disk exhaustion) | low | mitigate | `prune_history` drops records older than `HISTORY_DAYS` at startup + every `PRUNE_INTERVAL`; rewrite is atomic (`tempfile.mkstemp` in the same dir -> `os.replace`), never truncate-in-place. Verified live (UAT Test 2: seeded 40d record pruned on startup, file rewritten whole). | closed |
| T-02-03 | Tampering | corrupt/partial line on read (`parse_history`) | low | mitigate | `parse_history` wraps `json.loads` per line in try/except and keeps only JSON objects with a numeric `"t"`; `prune_history` reads with `errors="replace"`. A half-written trailing line, invalid UTF-8, or valid-JSON-but-wrong-shape line is skipped, never crashing the reader/prune (hardened in code-review WR-01 fix, commit 352f9e3). Verified live (UAT) + runtime corruption harness. | closed |
| T-02-04 | Denial of Service | history file I/O on unwritable path / full disk | low | mitigate | Every file op (append, read-for-prune, replace) swallows `OSError` (3 guards), so a missing/unwritable path, permission error, or full disk degrades to "history just doesn't persist". All I/O runs on the `poll_loop` daemon thread, off the Gtk main loop, so a slow/failing filesystem cannot freeze the tray. Verified live (UAT Test 3: `chmod 000` left the tray running and updating; persistence resumed on `chmod 600`). | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on (high) count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

No supply-chain (T-02-SC) row applies: this phase installs no packages (stdlib `json`/`os`/`time`/`tempfile` + already-present PyGObject only). No network calls, no shell, no privileged operations, and no untrusted input beyond the self-written history file reach this code.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-02-01 | T-02-01 | The history file lives under the user's own `~/.claude` at the same trust level as the tray helper; if that path is attacker-controlled the whole session is already compromised. The writer only serializes numeric fields via `json.dumps` (no shell/eval), so a tampered file cannot escalate beyond the invoking user. | Riccardo | 2026-07-12 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-12 | 4 | 4 | 0 | Claude (secure-phase, L1 short-circuit; register authored at plan time, threats_open 0) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-12
