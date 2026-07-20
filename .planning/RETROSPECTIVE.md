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

## Milestone: v1.3 — Notifications & Predictive Alerts + v1.4 — Session Dashboard

**Shipped:** v1.3 2026-07-17, v1.4 2026-07-20 (closed out together — v1.3 was never run through `/gsd-complete-milestone` on its own)
**Phases:** 3 (5, 6, 7) | **Plans:** 8

### What Was Built

- **One shared notification path** (`org.freedesktop.Notifications.Notify` via `Gio.DBusProxy`) that all tray events route through: session waiting/done, predictive 5h/7d quota alerts, click-to-focus reusing the existing tmux-pane + Ghostty-window action.
- **Per-event control**: tray toggles for all four event types, one global mute, and a configurable badge threshold — all persisted to a corruption-tolerant JSON config.
- **A live sessions panel** embedded in the v1.2 dashboard: every tracked session with status/dir/duration, sorted waiting -> running -> done, self-healing off the panel when a tmux pane dies with no `SessionEnd` hook event required.
- A structural restructure of `claude-monitor.py` (2081 lines) into a `claude_monitor/` package (`core.py` + `dashboard.py` + a slim entry script) mid-arc, keeping the growing surface navigable.

### What Worked

- **Grounding the notification binding against the actual gnome-shell source before planning**, not guessing. `05-RESEARCH.md` extracted `libshell-14.so` and ran live D-Bus probes to settle `Gio.DBusProxy` over `Gio.Notification` — a wrong guess here (the `Gio.Application`/`.desktop` route) would have silently dropped every notification.
- **Encoding landmines as acceptance criteria, not prose warnings.** `expire_timeout` being ignored, `resident` meaning the wrong thing, `ActionInvoked` being a broadcast signal — each became a specific plan assertion instead of a comment nobody re-reads.
- **Bundling both notification producers (session + quota) into one phase.** SEED-004 had already called out the failure mode of building against one producer and bolting the second on later; Phase 5 built the shared path by construction instead.

### What Was Inefficient

- **CR-01: a genuinely-alive session reaped past `REAP_MAX_AGE` and resuming its same status re-fired a spurious "Waiting for input" popup**, regressing NOTIF-02. The reap and the notification de-dupe were both individually correct in isolation and only broke at their intersection — closed with a one-shot `Monitor._reaped_status` memory in Phase 7-03 rather than the tempting-but-wrong fix (excluding `alive=True` from the age reap, which would have broken the same-pane `/exit` self-heal).
- **v1.3 shipped (2026-07-17) without ever running `/gsd-complete-milestone`.** Phase 5 has no VERIFICATION.md as a result — not a failed verification, a missing one. It sat as unarchived tech debt for a full milestone until v1.4's close-out bundled both together and recorded the gap as an acknowledged override rather than re-verifying weeks-old shipped code.
- **Three live-GUI human checks were needed for Phase 7** (killed-pane reap, same-pane 1h self-heal, sort/dim re-run) because none of session_stale/reap_stale/the DOM sort logic can be exercised without a live GTK tray + real tmux + real elapsed time. One of the three (the 1h same-pane idle check) was never explicitly re-run as its own UAT step — carried forward as tech debt, not a known defect.

### Patterns Established

- **A reap and a notification de-dupe guard must share one baseline-resolution function**, not two independently-correct-in-isolation code paths. `core.sess_notify_baseline` is now the single seam both consume.
- **Broadcast D-Bus signals need id-filtering at the handler, not just correct emission.** `ActionInvoked` fires for every application's notifications; the click handler must filter to ids this app owns.
- **A `# ponytail:` comment marking a deliberate bound (e.g. an unbounded-but-small in-memory dict) is a disposition, not debt** — distinct from an unresolved TODO.

### Key Lessons

1. **Verify the load-bearing binding decision against the platform's actual source before committing a plan to it** — not the documented API surface, which can silently diverge (gnome-shell's own notification daemon ignores a documented hint field entirely).
2. **Self-healing logic and notification de-dupe logic will eventually intersect; design the seam between them up front**, or the intersection becomes its own gap-closure phase.
3. **A milestone that ships without running the formal close-out accrues archival debt that compounds** — the next milestone inherits an unarchived phase and a missing verification report it did not create.

### Cost Observations

- Zero new runtime dependencies added across v1.3 and v1.4 (D-Bus and Gtk plumbing both come with PyGObject).
- The `claude_monitor/` package restructure (quick tasks `260718-hz5` and `260718-pkg`) happened mid-arc, between Phase 6 and Phase 7, rather than as a dedicated phase — kept the diff small by riding an already-scheduled context switch.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Key Change |
|-----------|--------|------------|
| v1.0 | 1 | Baseline: background poll + tray usage rows. UAT caught a stale-usage defect the plan did not anticipate. |
| v1.1 | 2 | Split persistence from the read-side views — the store shipped and got verified before anything depended on it. |
| v1.2 | 1 | Single coherent read-side capability; scope grew mid-flight (QUOTA-*). UAT against the live artifact drove two reversals. |
| v1.3+v1.4 | 3 | First cross-phase regression (CR-01, reap x notification de-dupe intersection); v1.3 shipped without formal close-out, bundled into v1.4's archival. |

### Cumulative Quality

| Milestone | Verification | Zero-Dep Additions |
|-----------|--------------|--------------------|
| v1.0 | UAT 4/4 | 0 |
| v1.1 | UAT 3/3 + security review; `--selfcheck` green | 0 |
| v1.2 | `--selfcheck` + code review + security audit + UI audit + human UAT | 0 |
| v1.3+v1.4 | Phase 5: REVIEW.md + UAT 5/5 (no VERIFICATION.md, acknowledged override); Phase 6: VERIFICATION.md passed + UAT 6/6; Phase 7: VERIFICATION.md passed (re-verified after CR-01 gap closure) + UAT 2/2 + integration-checker sweep (0 broken flows) | 0 |

### Top Lessons (Verified Across Milestones)

1. **UAT against the running artifact finds what plan review cannot.** Every milestone so
   far has had at least one defect or scope reversal that only appeared on screen: v1.0's
   stale-usage bug, v1.2's DASH-04 cut and the interpolated-gap chart, v1.4's CR-01
   reap/notification regression.
2. **The single background poll is the project's load-bearing decision.** Every feature
   since v1.0 hangs off it — which is also why guarding that thread from dying matters more
   than any individual feature.
3. **Defensive I/O has to be verified at every consumer, not declared once.** Corruption
   tolerance was claimed in v1.1 and still produced a crash after v1.2.
4. **Run the formal milestone close-out before shipping the next one.** v1.3 shipping
   without `/gsd-complete-milestone` left Phase 5 without a VERIFICATION.md for a full
   milestone cycle — cheap to skip in the moment, compounds into an archival gap someone
   else has to reconcile later.
