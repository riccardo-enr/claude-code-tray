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

## Milestone: v1.5 — TUI Dashboard

**Shipped:** 2026-07-24 (tag `v1.5`)
**Phases:** 2 (8, 9) | **Plans:** 4

### What Was Built

- **A read-only `{"query": "snapshot"}` verb** on the daemon's existing unix socket, returning every tracked session (dir/status/pane/tmux) plus the last polled usage/history — the first time `serve()` answered a request instead of only receiving fire-and-forget hook events.
- **`claude-tui.py`** — a `textual`-rendered terminal dashboard: 5h/7d usage rows, trends (sparkline, daily/weekly burn, peak hour) reused verbatim from `core`, a live sessions panel sorted waiting -> running -> done, auto-refresh, and clean degradation when the daemon is unreachable. The third consumer of `claude_monitor.core` alongside `claude-monitor.py` and `dashboard.py`.
- **The project's first runtime-dependency exception** — `textual`, scoped to the one entry point via a PEP 723 inline block and an optional `tui` extra, so the daemon's PEP 668 system interpreter never gains a third-party package.

### What Worked

- **Splitting the socket verb (Phase 8) from the renderer (Phase 9) on a real unblocks-the-next boundary.** Phase 9 had no data source until the query verb existed, and the verb was independently verifiable (connect + query, no TUI needed) — not an arbitrary horizontal-layer split.
- **Putting the whole TUI substrate in `core.py` above the textual boundary.** Socket client, usage rows, trend text, session rows, and timing constants are all `--selfcheck`-provable on the stock interpreter; `claude-tui.py` stayed App-class-and-CSS only. `TUI_SOCK_TIMEOUT < TUI_FETCH_INTERVAL` became a standing selfcheck assert against fetch-thread pile-up.
- **Reusing the thread-safety precedent instead of inventing one.** `sessions_lock` wraps every `self.sessions` call site; the query responder reads `usage`/`trends` outside the lock as single-reference rebinds, matching `compute_trends`' existing no-lock posture. `serve()`'s per-connection `except` guard (from `260713-fry`) was the precedent for SOCK-02's containment.

### What Was Inefficient

- **Textual has two independent exit doors and both had to be closed on every callback** — `@work(exit_on_error=False)` and a blanket `except Exception` in the body — because `App._handle_exception` "always results in the app exiting" and `Timer._tick` routes straight to it. A single guard would have let an unreachable-daemon tick silently kill the app.
- **A cluster of post-UAT review fixes (WR-01..06, CR-01/02)** landed after the App was "done": unbounded socket read, non-object JSON at the parse boundary, render-failure crash path, command-palette leak, unpinned deps, missing usage keys, ANSI injection via session-dir cells, lost scroll position on the render tick. Several (ANSI injection, unbounded read) are the kind of trust-boundary hardening that ideally lands in the plan, not the review.
- **Subtle textual property trap:** D-10's dimming needed CSS `opacity`, not `text-opacity` — textual 8.2.8 declares `opacity` with `children=True` but `text_opacity` without it, so `text-opacity` dims only the container's own content and leaves child panels bright. Cost a debugging cycle.

### Patterns Established

- **A new rendering surface should be a thin consumer of `core.py`, never a reimplementation.** `claude-tui.py` is the third consumer proving the v1.3/v1.4 GTK-free-core restructure paid off: the TUI is mostly a new view over existing pure functions.
- **A new runtime dependency can be introduced without polluting the base install** — PEP 723 inline metadata + an optional extra keeps `uv sync` at zero third-party packages and lets a plain `./claude-tui.py` resolve its own deps through a symlink from any cwd.
- **Every DataTable cell as `rich.text.Text`, every `Static` with `markup=False`** — untrusted session dirs must not be parsed as markup (the same summary-vs-body markup-injection lesson from v1.3, re-applied to the TUI surface).

### Key Lessons

1. **Trust-boundary hardening for a new input surface belongs in the plan, not the review.** A socket that now answers queries, and a TUI that renders untrusted session dirs, both introduced input boundaries — most of the WR/CR fixes were bounding and sanitizing those, and could have been acceptance criteria up front.
2. **A GTK-free `core.py` is what makes a second (and third) frontend cheap.** The restructure done mid-v1.3/v1.4 as tech-debt paydown is precisely what let v1.5 add a whole terminal UI as a thin renderer.
3. **When a framework "always exits on unhandled exception," every async callback needs belt-and-suspenders containment** — one guard is not enough when the framework has multiple independent paths into its exit handler.

### Cost Observations

- One new runtime dependency (`textual` 8.2.8 + transitive `rich`), the first in the project's history — deliberately quarantined to the optional `tui` extra so the daemon and default install stay zero-third-party.
- Coarse 2-phase milestone (4 plans, 8 tasks, ~4 days) matching the 1-2-phases-per-milestone precedent; no VERIFICATION-blocking rework, but a heavy post-UAT review-fix tail.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Key Change |
|-----------|--------|------------|
| v1.0 | 1 | Baseline: background poll + tray usage rows. UAT caught a stale-usage defect the plan did not anticipate. |
| v1.1 | 2 | Split persistence from the read-side views — the store shipped and got verified before anything depended on it. |
| v1.2 | 1 | Single coherent read-side capability; scope grew mid-flight (QUOTA-*). UAT against the live artifact drove two reversals. |
| v1.3+v1.4 | 3 | First cross-phase regression (CR-01, reap x notification de-dupe intersection); v1.3 shipped without formal close-out, bundled into v1.4's archival. |
| v1.5 | 2 | First runtime dependency (`textual`, quarantined to an optional extra); a new frontend as a thin `core.py` consumer; heavy post-UAT trust-boundary review-fix tail. |

### Cumulative Quality

| Milestone | Verification | Zero-Dep Additions |
|-----------|--------------|--------------------|
| v1.0 | UAT 4/4 | 0 |
| v1.1 | UAT 3/3 + security review; `--selfcheck` green | 0 |
| v1.2 | `--selfcheck` + code review + security audit + UI audit + human UAT | 0 |
| v1.3+v1.4 | Phase 5: REVIEW.md + UAT 5/5 (no VERIFICATION.md, acknowledged override); Phase 6: VERIFICATION.md passed + UAT 6/6; Phase 7: VERIFICATION.md passed (re-verified after CR-01 gap closure) + UAT 2/2 + integration-checker sweep (0 broken flows) | 0 |
| v1.5 | Phase 8: VERIFICATION.md passed + UAT 3/3; Phase 9: code review + `--selfcheck` + UAT 3 pass / 2 skipped (documented non-failures) + WR-01..06/CR-01/02 review-fix pass. No `v1.5-MILESTONE-AUDIT.md` (audit not run; override closeout) | 1 (`textual`, optional extra) |

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
