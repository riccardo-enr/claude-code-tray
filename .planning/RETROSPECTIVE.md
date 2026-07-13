# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.2 — Usage Web Dashboard

**Shipped:** 2026-07-13
**Phases:** 1 (Phase 4) | **Plans:** 1 | **Commits:** ~28

### What Was Built

- A self-contained `file://` HTML dashboard opened from a tray item — usage-% trend
  over rolling 24h/7d/All, hour x day peak heatmap, dark mode, auto-refresh — generated
  off-thread from the existing `~/.claude/usage-history.jsonl`, stdlib only.
- The **weekly (7-day) quota cap**, made visible for the first time: parsed from
  `limits.seven_day`, surfaced in the tray rows and on the dashboard, with the icon
  badge now warning when *either* cap is hot.
- **Projections** for both caps ("on track — projected 57% at reset", "98% by Fri"),
  plus reset markers on the trend so the sawtooth reads as "the window rolled" rather
  than "usage fell".

### What Worked

- **Reviewing the running artifact, not the spec.** DASH-04 (burn-rate chart) was built
  exactly as specified and then deleted during UAT, because on screen it was a near-flat
  line of ~30M tok/hr raw throughput that the heatmap already conveyed. The spec was not
  wrong on paper; it was wrong once rendered. UAT against the live page caught it.
- **Making a constraint assertable instead of aspirational.** "Self-contained, no new
  deps" (DASH-06) became a `--selfcheck` assertion that fails on any `<link`, `src=`, or
  `https://` in the output. The constraint now defends itself.
- **One poll tick, three milestones.** Every feature since v1.0 — history, trends, the
  dashboard — hangs off the same background poll. No new polling, no second data source,
  no new dependency across the whole arc.

### What Was Inefficient

- **The weekly cap was invisible for two milestones on a stale assumption.** PROJECT.md's
  Out of Scope said "the CLI reports it as null for this account". It does not — it is
  right there in `limits.seven_day`. A 95%-weekly / 10%-five-hour state produced *no
  warning at all* until v1.2. The assumption was recorded once and never re-tested.
- **Corruption tolerance was declared "total" in Phase 2 and was not.** A corrupt record
  still crashed `compute_trends` after v1.2 shipped (quick task `260713-fry`), and the
  crash killed the poll daemon thread permanently. The Phase-2 hardening covered the
  reader it was written against, not every consumer of the store.
- **v1.2 scope grew a whole second theme mid-flight.** The QUOTA-01/02/03 requirements
  were added during the milestone, not planned into it. Good work, but it means the
  milestone shipped roughly double what it was scoped for.

### Patterns Established

- **Charts must not assert data they do not have.** The trend line breaks across sampling
  gaps rather than interpolating; a 13.7h outage was rendering as a smooth "decline" that
  never happened.
- **Derive from percentages, not tokens.** The CLI's own `forecast`/`status` are
  token-based and return `null` counts under `--api`, reporting "limit hit" at 20% real
  usage. All projection math is percentage-derived.
- **Rolling windows, not calendar ones.** A window that resets at local midnight hides the
  most recent activity right after it rolls — and rolling mirrors how Claude's quotas work.
- **Guard the daemon thread itself, not just its callees.** Any exception inside
  `poll_loop` must not be able to end the thread; a dead poll thread silently freezes
  every downstream feature.

### Key Lessons

1. **Re-test recorded assumptions at milestone boundaries.** "The API returns null for
   this" was true once, was written down, and then quietly cost two milestones of a
   missing feature. Out-of-Scope entries justified by an external system's behavior have
   a shelf life.
2. **A hardening claim is only as wide as the code paths it was tested against.** Phase 2
   hardened `parse_history` and called corruption tolerance done; `compute_trends` was a
   sibling caller nobody re-checked.
3. **Build it, then look at it.** Two of the milestone's best decisions (cutting DASH-04,
   breaking the line across gaps) were only visible in the rendered artifact.

### Cost Observations

- Single-file target (`claude-monitor.py`, ~1.8k lines) keeps context cheap — the whole
  implementation surface fits in one read.
- Zero new runtime dependencies added across v1.0, v1.1, and v1.2.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Key Change |
|-----------|--------|------------|
| v1.0 | 1 | Baseline: background poll + tray usage rows. UAT caught a stale-usage defect the plan did not anticipate. |
| v1.1 | 2 | Split persistence from the read-side views — the store shipped and got verified before anything depended on it. |
| v1.2 | 1 | Single coherent read-side capability; scope grew mid-flight (QUOTA-*). UAT against the live artifact drove two reversals. |

### Cumulative Quality

| Milestone | Verification | Zero-Dep Additions |
|-----------|--------------|--------------------|
| v1.0 | UAT 4/4 | 0 |
| v1.1 | UAT 3/3 + security review; `--selfcheck` green | 0 |
| v1.2 | `--selfcheck` + code review + security audit + UI audit + human UAT | 0 |

### Top Lessons (Verified Across Milestones)

1. **UAT against the running artifact finds what plan review cannot.** Every milestone so
   far has had at least one defect or scope reversal that only appeared on screen: v1.0's
   stale-usage bug, v1.2's DASH-04 cut and the interpolated-gap chart.
2. **The single background poll is the project's load-bearing decision.** Every feature
   since v1.0 hangs off it — which is also why guarding that thread from dying matters more
   than any individual feature.
3. **Defensive I/O has to be verified at every consumer, not declared once.** Corruption
   tolerance was claimed in v1.1 and still produced a crash after v1.2.
