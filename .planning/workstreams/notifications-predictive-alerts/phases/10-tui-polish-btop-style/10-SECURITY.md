---
phase: 10
slug: tui-polish-btop-style
status: verified
threats_open: 0
asvs_level: 1
created: 2026-07-24
---

# Phase 10 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Daemon unix socket → `claude-tui.py` | Same-user, read-only snapshot socket with mode 0600; Phase 10 adds presentation only and introduces no new IPC | Usage percentages, reset/burn values, trend strings, session status, and project paths |
| Snapshot values → Rich/Textual rendering | Untrusted snapshot fields are converted into gauges, graphs, and styled table cells on the timer-driven render path | Numeric percentages, sparkline glyphs, and arbitrary filesystem path text |
| Locked Python dependency → TUI runtime | `textual` remains the only Phase 10 third-party runtime dependency | Lock-pinned package artifacts and hashes |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-10-01 | Tampering | `core.band` / `core.gauge_fill` over snapshot percentages | mitigate | `band` is total for numeric under/over-range values; `gauge_fill` clamps percentage to 0–100 and bounds fill to the fixed width. Boundary and monotonicity assertions pass under `just selfcheck`. | closed |
| T-10-02 (P01) | Denial of Service | Usage render under the one-second timer | mitigate | `parse_usage` rejects non-numeric required fields; `_usage_renderable` gates on the data rather than a rendered sentinel; `tick` catches render exceptions and reports a render error instead of terminating the app. | closed |
| T-10-03 | Tampering | `core.spark_levels` over malformed trend glyphs | mitigate | The inverse lookup maps gaps and unknown characters to `None`, preventing out-of-range indexing. Non-string payloads remain contained by the timer render guard; the socket is same-user and mode 0600. | closed |
| T-10-04 | Denial of Service | Empty or malformed trends during rendering | mitigate | Falsy trends return `core.trend_text` without decoding; any later render exception is contained by `tick` and surfaced without exiting. | closed |
| T-10-02 (P03) | Tampering | Styled session cells over hostile project paths | mitigate | `core._safe_cell` removes C0/C1 terminal-control characters, and every DataTable cell is a `rich.Text` renderable with style applied separately, bypassing markup parsing. Existing injection assertions pass. | closed |
| T-10-05 | Denial of Service | Unknown session status during the timer render | mitigate | `sess_status_band` is a total lookup with a neutral default, and the outer timer guard contains unrelated render failures. | closed |
| T-10-SC | Tampering | Python dependency supply chain | accept | Phase 10 adds no package; the existing `textual` dependency remains version constrained and fully hash-pinned in `claude-tui.py.lock`. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-10-01 | T-10-SC | No dependency change in Phase 10; retaining the existing hash-pinned Textual runtime is lower risk than replacing or duplicating the rendering stack during a presentation-only phase. | Project planning decision | 2026-07-24 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-24 | 7 | 7 | 0 | Codex inline security audit |

Evidence gates:

- `just selfcheck` — passed
- `just lint` — passed
- `git diff --check` — passed
- Manual Phase 10 UAT — 4/4 passed

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-24
