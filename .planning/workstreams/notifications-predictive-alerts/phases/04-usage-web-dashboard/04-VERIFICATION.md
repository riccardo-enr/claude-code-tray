---
status: passed
phase: 04-usage-web-dashboard
verified: 2026-07-13
method: automated self-check + code review + security audit + UI audit + human UAT
note: workflow.verifier is false in config, so no gsd-verifier agent ran; goal
  verification was performed against the codebase and through UAT (04-UAT.md).
---

# Phase 4 — Verification

**Goal:** a tray menu item opens a self-contained HTML dashboard rendering the persisted
JSONL history as real charts — complementing, not replacing, the cramped tray menu.

**Verdict: PASSED**, with two deliberate, user-approved deviations (below). Verified
against the actual code, not against the SUMMARY's claims.

## Must-haves (from 04-01-PLAN.md)

| # | Must-have | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Menu item opens `dashboard.html` via a resolved `file://` URI (DASH-01) | PASS | `open_dashboard` = `webbrowser.open(pathlib.Path(DASH_PATH).resolve().as_uri())`, zero history I/O. Exercised by the user repeatedly. |
| 2 | Usage-% trend with range switching, filtered client-side from one embedded dataset (DASH-02) | PASS* | Delivered as rolling **24h/7d/All** rather than calendar day/week (see Deviations). One embedded dataset, filtered client-side, as specified. |
| 3 | Hour x day-of-week heatmap, empty cells a distinct gray (DASH-03) | PASS* | Grid + gray empty cells as specified. Cell **metric changed** from `mean(burn)*60` to mean usage % (see Deviations). |
| 4 | Daily burn-rate trend over full retained history (DASH-04) | **DESCOPED** | Built as specified, then removed at user request during UAT (`ae0691f`). See Deviations. |
| 5 | Self-contained HTML, regenerated on the poll tick from the Phase-2 JSONL only (DASH-05/06) | PASS | Single source via `parse_history`; **assertion-enforced**: `--selfcheck` fails on any `<link`, `src=`, `https://`, or a second `</script>`. |
| 6 | Only numeric records reach the payload; `history_numeric` **drops** corrupt records (T-04-01) | PASS | `render_dashboard` calls `history_numeric` first. Hardened during review (WR-01: NaN/Inf/out-of-range `t` now rejected) and **extended** to the later `pct7`/`reset`/`reset7` fields, with a regression guard in `--selfcheck`. |
| 7 | `write_dashboard` renders only `history_keep` survivors (retention holds even if prune failed) | PASS | Retention re-filter applied before render. |
| 8 | Self-containment asserted automatically in `--selfcheck` | PASS | 3 injection/self-containment asserts present and passing. |
| 9 | History read + HTML written off the Gtk main thread; menu handler does zero history I/O | PASS | `write_dashboard` called only from `poll_loop`, which runs on a `daemon=True` thread. |

`*` = delivered, with an approved change of substance recorded below.

## Deviations (both user decisions, made against the running artifact)

1. **DASH-04 descoped** — the daily burn-rate chart was built to spec, then removed. On
   real data it plotted near-flat ~30M tok/hr raw-throughput figures and duplicated the
   burn data the heatmap already showed more usefully. Recorded in REQUIREMENTS.md as
   descoped, **not** as delivered.
2. **DASH-03 metric changed** — heatmap cells are mean **usage %** rather than mean burn,
   for the same readability reason and for consistency with a dashboard that is otherwise
   denominated in percent.

## Scope added beyond the plan (QUOTA-01..03)

The weekly (7-day) cap, reset persistence + on-chart reset markers, and usage projections
were added during UAT. These are **new requirements**, tracked as QUOTA-01..03, not silent
scope creep. QUOTA-01 closes the long-deferred SEED-003.

## Gates

| Gate | Result |
|------|--------|
| `python3 claude-monitor.py --selfcheck` | **ok** (all v1.0 / Phase-2 / Phase-3 / Phase-4 asserts) |
| Code review (`04-REVIEW.md`) | 0 Critical, 1 Warning (**fixed**, `2fdb913`), 2 Info (deferred) |
| Security (`04-SECURITY.md`) | `threats_open: 0`; re-audited 2026-07-13 after scope growth |
| UI audit (`04-UI-REVIEW.md`) | 11/24 at audit time; top findings fixed (`13b822c`) |
| Human UAT (`04-UAT.md`) | 4/4 passed; 7 findings raised **and resolved in-session** |

## Known limitations (data maturity, not defects)

- The heatmap and the weekly series are **sparse** — history only began accumulating
  2026-07-12, and the weekly cap only from 2026-07-13. Both fill in with time.
- Weekly trend and reset markers have no backfill: they start where the data starts.
  Faking backfill was explicitly rejected.

## Explicitly not built

A comparison against **global//cross-user Claude Code usage** was requested and **refused**:
no such dataset exists. The Anthropic Economic Index — the only public aggregate — has no
temporal dimension and no token/burn-intensity metric, and its "Cadences" report publishes
normalized relative frequencies rather than data. Rather than fabricate a baseline (which
would have made every cell on the chart meaningless), the feature was declined.
