---
phase: 4
slug: usage-web-dashboard
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-07-12
---

# Phase 4 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

ASVS Level 1, block-on: high. Scope shape: a static local `file://` HTML artifact
regenerated from `~/.claude/usage-history.jsonl` — no network, no server, no bind,
no auth, read-only input. Verified at grep depth (register authored at plan time,
ASVS L1) and corroborated by the Phase-4 code review's end-to-end trace of the
inline-script embedding path (04-REVIEW.md) and the WR-01 hardening of the input
sanitizer (04-REVIEW-FIX.md, commit 2fdb913).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| history JSONL -> dashboard generator | `~/.claude/usage-history.jsonl` is loaded by `parse_history` (validates numeric `t` only); `pct`/`burn` are untrusted and a corrupt/tampered line can carry arbitrary values that get embedded into an inline `<script>`. | untrusted usage records (numeric only after sanitizing), embedded into generated HTML |
| generated HTML -> browser | The `file://` page runs its own inline JS under a local-file origin; no external assets, no network egress. | usage-% and burn figures (no tokens/credentials/message content) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-04-01 | Tampering/Injection | `render_dashboard` embedding untrusted records into inline `<script>` | high | mitigate | Two layers, both verified in code. (1) `history_numeric` runs FIRST in `render_dashboard` (`claude-monitor.py:543`) — drops any record whose `t`/`pct`/`burn` is non-numeric, non-finite (NaN/Inf), or an out-of-range `t` (WR-01 hardening), so a crafted value never enters the dataset. (2) `_embed_json` (`:353`) is the SOLE serializer of the embedded payload (`:557`), escaping `<`/`>`/`&` to JSON unicode escapes; `json.dumps` `ensure_ascii=True` also escapes U+2028/U+2029. Reviewer confirmed no key beyond `t`/`pct`/`burn` reaches the payload (dict never spread) and there is no unescaped serialization path. Automated `--selfcheck` asserts drop-then-escape + exactly-one-`</script>`. | closed |
| T-04-02 | Information disclosure | `dashboard.html` written under the user cache dir | low | accept | Output lives under `${XDG_CACHE_HOME:-~/.cache}/claude-tray/` (`:72`), user-owned on a single-user machine, and contains only usage-% and burn figures — no tokens, credentials, or message content — consistent with the JSONL already at `~/.claude/`. No secrets to leak. | closed |
| T-04-03 | Denial of service | `Monitor.write_dashboard` on the poll thread | medium | mitigate | Generation runs OFF the Gtk main thread (daemon `poll_loop`, `:1183`) on a ~5min throttle with `last_dash = now` set unconditionally so failures are throttled, not hot-retried (`:1142`). Input is bounded by HIST-02 retention AND re-bounded in `write_dashboard` via `history_keep(now, HISTORY_DAYS)` (`:1008`) even if a prune failed; `history_numeric` drops non-numeric/non-finite records so aggregation cannot raise (WR-01 removed the NaN/Inf/far-future crash-and-permanent-stall vector); and the whole body is wrapped in a broad `except Exception -> return` (`:1017`) so residual malformed input degrades to "not updated this tick." | closed |
| T-04-SC | Tampering | dependency supply chain | low | accept | No package installs this phase — stdlib only (`json`, `os`, `math`, `tempfile`, `datetime`, `pathlib`, `webbrowser`) plus the existing PyGObject. Grep confirms no third-party import added. Supply-chain surface unchanged. | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-04-01 | T-04-02 | Dashboard written to a user-owned cache path on a single-user machine; contains only usage-%/burn, no secrets — same sensitivity as the existing `~/.claude/usage-history.jsonl`. | Riccardo Enrico | 2026-07-12 |
| AR-04-02 | T-04-SC | Stdlib-only phase; no new dependency, so no new supply-chain surface to audit. | Riccardo Enrico | 2026-07-12 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-12 | 4 | 4 | 0 | /gsd-secure-phase (grep-depth L1, corroborated by 04-REVIEW.md trace + WR-01 fix) |
| 2026-07-13 | 4 | 4 | 0 | re-audit of post-audit scope growth (see below) |

### 2026-07-13 re-audit — post-audit scope growth

The phase grew substantially after the original audit (weekly cap, reset persistence,
projections, dark mode, embedded brand icon). Re-checked the two mitigated threats
against the new code:

**T-04-01 (injection) — still CLOSED, but the mitigation needed extending.** The new
payload fields (`pct7`, `reset`, `reset7`, `resets`) reach the inline `<script>` through
`usage7_series` / `reset_marks` / `latest_state` — and `history_numeric`, the phase's
front-line sanitizer, validates **only** `t`/`pct`/`burn`. A record can therefore be
"numeric-clean" by its lights while carrying hostile junk in the new fields. Verified by
probe that each new accessor independently `_is_num`-filters, so nothing hostile reaches
the payload; `_embed_json` escaping remains as defense-in-depth. This held only by
construction and was **not asserted**, so a future payload field added without a filter
would have silently reopened the hole — a regression guard is now in `--selfcheck`
(renders a record with `pct7`/`reset`/`reset7` set to a script-closing string and asserts
the value is absent and exactly one `</script>` remains).

**T-04-02 (info disclosure) — still CLOSED, accepted.** The embedded brand icon is a
local, already-world-readable system asset (`/usr/share/icons/.../claude-desktop.png`),
inlined as base64. It adds no new data to the page and no network reference. It is applied
via CSS `background-image:url(data:...)` rather than `<img src=>` precisely because the
DASH-06 self-containment assert forbids any `src=` — an `<img>` would have failed the build.

**T-04-03 (DoS) — still CLOSED.** No new unbounded input. New fields are numeric-filtered
before any arithmetic; the off-thread + throttled + broad-except posture is unchanged.

No new trust boundary was introduced: the dashboard still performs zero network I/O.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-12
