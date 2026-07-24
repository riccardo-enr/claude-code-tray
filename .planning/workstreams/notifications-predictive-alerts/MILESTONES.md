# Milestones

## v1.6 TUI Polish (Shipped: 2026-07-24)

**Phases completed:** 1 phase (10), 3 plans, 6 planned tasks
**Timeline:** 2026-07-24 (same-day milestone)
**Git range:** `2fef6e9` (first polish feature) -> `b4c01a4` (hourly trend correction)

**Delivered:**

- Btop-inspired Textual presentation: fixed proximity bands, gradient quota
  gauges, an eight-row colored trends graph, status-colored striped sessions,
  and titled rounded panels — TUI-06/07/08/09/10
- Per-cap quota projections and a dashboard-parity Mon-Sun hourly heatmap,
  reusing existing core calculations and the daemon's read-only snapshot
- Selected-session focus through the existing daemon/tmux path, selection
  retention across refreshes, and background-work resilience
- Corrected hourly trend chart based on trustworthy per-sample usage increments
  aligned to clock hours

**Verification:** Phase 10 conversational UAT 4/4 passed; `just selfcheck` and
`just lint` passed; security review closed 7/7 threats with 0 open.

**Closeout:** explicit override — no `v1.6-MILESTONE-AUDIT.md`. The historical
`10-REVIEW.md` still says `issues_found`, but its 0 critical / 2 warning findings
were fixed in `5fcb364` and `c604416` and verified by the release checks.

**Known closeout notes:** 3 (see STATE.md "Deferred Items") — missing milestone
audit acknowledged, stale pre-fix review status acknowledged, and standalone
no-daemon mode remains deferred.

**Phases:** 10-tui-polish-btop-style (UAT passed; security verified; archived).

---

## v1.5 TUI Dashboard (Shipped: 2026-07-24)

**Phases completed:** 2 phases (8-9), 4 plans, 8 tasks
**Timeline:** 2026-07-20 -> 2026-07-24 (4 days)
**Git range:** `6d12b95` (feat 08-01) -> `4c05121` (feat tui theme)

**Delivered:**

- Read-only `{"query": "snapshot"}` verb on the daemon's existing unix socket, returning every tracked session (dir/status/pane/tmux) plus the last polled usage/history — thread-per-connection so a stalled/malformed query blocks only its own thread, built under `sessions_lock` for torn-read safety, socket chmod 0600 — SOCK-01/02/03
- `claude-tui.py` — a `textual`-rendered terminal dashboard: 5h/7d usage rows (%, tokens, reset countdown, burn), trends (sparkline, daily/weekly burn, peak hour) reused verbatim from `core`, a live sessions panel sorted waiting -> running -> done, auto-refreshing on a two-timer loop, degrading to a clear message when the daemon is unreachable — TUI-01/02/03/04/05
- The whole TUI substrate lives in `claude_monitor/core.py` above the textual boundary, `--selfcheck`-proven on the stock interpreter; `claude-tui.py` is App-class-and-CSS only and resolves `textual` via its own PEP 723 block, so the daemon's PEP 668 interpreter never gains a third-party package (first exception to stdlib+PyGObject-only, scoped to one entry point via the optional `tui` extra)
- Post-UAT hardening: bounded socket read with wall-clock deadline + size cap (WR-01), non-object JSON rejected at the parse boundary (WR-02), render failures routed through the tick guard (WR-03), command palette disabled so `q` is the only binding (WR-04), tui deps pinned via committed per-script uv lockfile (WR-05), defensive usage-key reads (WR-06), ANSI-injection guard stripping control chars from session-dir cells (CR-02), sessions scroll position preserved across the 1s render tick (CR-01)

**Verification:** Phase 08 UAT 3/3 passed + VERIFICATION passed; Phase 09 UAT 3 pass / 2 skipped / 0 issues (skips: scroll-retention + daemon-outage, documented as non-failures verified by tests + code re-read). Requirements 8/8 delivered.

**Known deferred items:** 6 (see STATE.md "Deferred Items") — incl. TUI polish proposed for v1.6, TUI click-to-focus, no-daemon standalone mode, and 2 audit-format false positives acknowledged at close (Phase 01/09 UATs, both `[passed]`).

**Closeout:** override_closeout — no `v1.5-MILESTONE-AUDIT.md` (audit not run); 2 pre-existing out-of-scope open items (a diagnose-only debug session whose fix shipped in v1.4, and an unrelated Zed keybind quick task) acknowledged and deferred.

**Phases:** 08-daemon-socket-query-verb (verified), 09-terminal-dashboard-claude-tui-py (UAT passed).

---

## v1.4 Session Dashboard (Shipped: 2026-07-20)

**Phases completed:** 3 phases, 8 plans, 8 tasks

**Key accomplishments:**

- Task 1 (`badde8a`)
- Task 1 (`ecc3e9a`)
- Task 1 (`cfc6a45`)
- Task 1 -- Tolerant config load + atomic config save.
- core.sess_notify_baseline seeds handle's notification baseline from a short-lived Monitor._reaped_status memory, so a genuinely-alive session reaped after 1h idle and resuming its same-status hook event reads as "no transition" instead of re-firing a "Waiting for input" popup -- restoring the NOTIF-02 de-dupe guarantee without touching session_stale.

---
