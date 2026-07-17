---
phase: 4
reviewers: [codex]
reviewed_at: 2026-07-12T14:11:23Z
plans_reviewed: [04-01-PLAN.md]
---

# Cross-AI Plan Review — Phase 4

## Codex Review

## Summary

The plan is well-aligned with the phase goal and the current single-file architecture. It correctly reuses the existing history store, keeps history I/O off the Gtk main thread, preserves the stdlib-only constraint, and picks the simpler static `file://` delivery shape that the phase context recommends. Main risks are around the loose `parse_history()` contract: it only validates numeric `t`, so the plan needs stronger numeric filtering/coercion before chart aggregation and JS rendering.

## Strengths

- The static HTML approach matches the open planning decision: Phase 4 explicitly allows choosing static regenerated HTML over a loopback server, and the context recommends static `file://` because live browser refresh is deferred `.planning/ROADMAP.md:114`, `.planning/phases/04-usage-web-dashboard/04-CONTEXT.md:33`.
- The plan puts generation in `poll_loop`, which matches the existing off-main-thread pattern. Current `poll_loop` already owns history append/prune/trend recompute work, with `last_trend = 0.0` for immediate first recompute `claude-monitor.py:717`, `claude-monitor.py:725`, `claude-monitor.py:727`, `claude-monitor.py:735`.
- The plan correctly reuses existing burn semantics. `history_record()` stores raw per-minute burn `claude-monitor.py:159`, `claude-monitor.py:163`, and `trend_burn()` converts to tok/hr exactly once `claude-monitor.py:296`, `claude-monitor.py:299`, `claude-monitor.py:305`.
- The menu integration point is straightforward. `rebuild_menu()` already builds sensitive session rows and insensitive usage/trend rows, with the final separator and Quit item at the right insertion point `claude-monitor.py:509`, `claude-monitor.py:521`, `claude-monitor.py:527`, `claude-monitor.py:531`.
- The injection mitigation is appropriate for inline script embedding. This matters because `parse_history()` only keeps records with numeric `t` and does not validate `pct` or `burn` `claude-monitor.py:184`, `claude-monitor.py:187`, `claude-monitor.py:204`.

## Concerns

- **MEDIUM: Non-numeric `pct` / `burn` can still break charts or suppress dashboard updates.**
  The plan acknowledges this partly by wrapping `write_dashboard()` in broad `Exception`, but `parse_history()` only validates `t` `claude-monitor.py:184`, `claude-monitor.py:204`. Existing `trend_burn()` assumes numeric `burn` and will raise on strings at `sum(vals)` `claude-monitor.py:302`, `claude-monitor.py:305`. The plan's own injection test uses a string `pct`, which would be safely escaped but may still reach JS chart math unless filtered.

- **LOW/MEDIUM: The plan says "full retained history" but does not explicitly filter with `history_keep()` before rendering.**
  The roadmap says Phase 4 reads via `parse_history` / `history_keep` readers `.planning/ROADMAP.md:98`, and context calls out `history_keep()` as the retention predicate to reuse `.planning/phases/04-usage-web-dashboard/04-CONTEXT.md:122`. The proposed `write_dashboard()` reads `parse_history()` and passes all records to `render_dashboard()`. Usually pruning handles this, but `prune_history()` intentionally swallows failures `claude-monitor.py:222`, `claude-monitor.py:241`, so stale records can remain if pruning failed.

- **LOW: `file://` URL construction should escape paths.**
  `webbrowser.open("file://" + DASH_PATH)` works for the planned cache path in normal cases, but it is brittle for spaces or special characters. The current code already imports only stdlib modules `claude-monitor.py:12`, so `pathlib.Path(DASH_PATH).resolve().as_uri()` would stay dependency-free.

- **LOW: Self-containment verification is mostly manual.**
  DASH-06 requires no external assets/deps `.planning/REQUIREMENTS.md:18`, `.planning/REQUIREMENTS.md:33`. The plan says to inspect generated HTML, but an automated selfcheck assertion that no `<link`, external `src=`, `http://`, or `https://` appears would make this harder to regress.

## Suggestions

- Add a small pure sanitizer before building payloads, e.g. keep records only when `t`, `pct`, and `burn` are numeric for charts that need those fields. Test that bad `pct` / `burn` records are skipped, not embedded into chart datasets.
- In `Monitor.write_dashboard()`, filter parsed records with `history_keep(r, now, HISTORY_DAYS)` before rendering. That makes "full retained history" true even if opportunistic pruning failed.
- Use `pathlib.Path(DASH_PATH).resolve().as_uri()` for `open_dashboard()`.
- Add selfcheck assertions for self-contained output and no raw script-closing sequence in the full rendered page.
- Consider setting `last_dash = now` only after `write_dashboard()` returns, or document that failures are intentionally throttled for 5 minutes. Either behavior is acceptable, but it should be deliberate.

## Risk Assessment

**Overall risk: MEDIUM.** The architecture is sound and scoped well: one file, no new dependencies, no server, no main-thread history I/O, and clear test hooks. The main implementation risk is data-shape robustness because the existing parser deliberately accepts loose records. Tightening numeric filtering and retained-window filtering would reduce this to low.

---

## Consensus Summary

Single reviewer (codex), source-grounded against the working tree. The plan's architecture is endorsed without dissent — static `file://` dashboard, generation in `poll_loop` (off the Gtk main thread), reuse of existing history/burn/trend helpers, stdlib-only, no server. No HIGH-severity concerns.

### Agreed Strengths

- Static HTML `file://` delivery matches the open ROADMAP decision and CONTEXT recommendation.
- Dashboard generation placed in `poll_loop`, consistent with the existing off-main-thread history/trend pattern.
- Correct reuse of burn semantics (`history_record` raw burn -> `trend_burn` single tok/hr conversion) and the `rebuild_menu()` insertion point.
- Inline-script injection mitigation (escaping) is appropriate given the loose parser.

### Agreed Concerns (priority order)

1. **MEDIUM — Loose data shape.** `parse_history()` validates only numeric `t`; non-numeric `pct`/`burn` can reach chart math / `trend_burn()` and raise. Add a pure numeric sanitizer before building chart payloads; test that bad records are skipped, not embedded.
2. **LOW/MEDIUM — Retention filter.** Filter rendered records through `history_keep(r, now, HISTORY_DAYS)` in `write_dashboard()` so "full retained history" holds even when opportunistic `prune_history()` silently failed.
3. **LOW — Path escaping.** Use `pathlib.Path(DASH_PATH).resolve().as_uri()` instead of `"file://" + DASH_PATH` (stays stdlib-only, handles spaces/special chars).
4. **LOW — Automated self-containment check (DASH-06).** Add a selfcheck assertion that the rendered HTML contains no `<link`, external `src=`, `http://`, or `https://`, plus no raw script-closing sequence.

### Divergent Views

None — single reviewer.
