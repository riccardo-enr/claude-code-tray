---
gsd_state_version: 1.0
milestone: v1.6
milestone_name: TUI Polish
status: roadmapped
last_updated: "2026-07-24T10:45:00.000Z"
last_activity: 2026-07-24
progress:
  total_phases: 1
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-24)

**Core value:** At a glance from the top bar, know how much Claude Code quota is left and when it resets — without launching a separate terminal monitor.
**Current focus:** v1.6 TUI Polish — Phase 10 roadmapped (btop-style: color/gauge/graph/border `claude-tui.py`). Plan next via `/gsd-plan-phase 10`.

## Current Position

Phase: Phase 10 — TUI Polish (btop-style), not started
Plan: — (roadmap created; plans TBD)
Status: Roadmapped — awaiting `/gsd-plan-phase 10`
Last activity: 2026-07-24 — v1.6 roadmap created (single phase, Phase 10)

## Performance Metrics

**Velocity:**

- Total plans completed: 9
- Average duration: - min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 1 | 2 min | 2 min |
| 02 | 1 | 2 min | 2 min |
| 03 | 1 | 1 session | - |
| 04 | 1 | 12 min | 12 min |
| 07 | 3 | - | - |
| 08 | 2 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 05 P02 | 15 min | 2 tasks | 1 files |
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 06 P01 | 8 min | 3 tasks | 1 files |
| Phase 06 P02 | 6min | 2 tasks | 1 files |
| Phase 07 P02 | 3 min | 3 tasks | 3 files |
| Phase 07 P03 | 2min | 3 tasks | 3 files |
| Phase 08 P01 | 12min | 2 tasks | 3 files |
| Phase 08 P02 | 5min | 2 tasks | 1 files |
| Phase 09 P01 | 18min | 2 tasks | 2 files |
| Phase 09 P02 | 22min | 2 tasks | 5 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- **v1.6 is 1 phase** (Phase 10, TUI Polish). All five requirements (TUI-06..TUI-10) touch the same two files (`claude-tui.py` + `core.py` helpers) with no hard data dependency between them — unlike v1.5's Phase 8->9 socket-then-TUI unblock. The core-vs-TUI boundary (assertable helpers in `core`, `--selfcheck`-proven; color/gauge/border rendering in `claude-tui.py`) runs INSIDE each of TUI-06..TUI-09, not between requirements, so it cannot split them into two phases without spanning a requirement across both — it is a PLAN-level split within Phase 10, mirroring v1.5's 09-01 (core substrate) then 09-02 (textual wiring). Matches the 1-2-phases-per-milestone precedent (v1.2 shipped 11 reqs in one phase).

- v1.3 is **2 phases** (5: notification path + both producers; 6: config/control). Coarse granularity, and the project precedent is 1-2 phases per milestone (v1.2 shipped 11 requirements in one phase).
- **Both producers (SESS-* and ALERT-*) land in Phase 5, not separate phases.** The deliverable is the shared emit path (de-dupe, mute hook, click-to-focus); building it against one producer and bolting the second on later is how it grows two heads — the exact failure SEED-004 called out.
- **Config (CFG-*) comes last (Phase 6)** because CFG-01 enumerates all four event types — they must exist before they can be toggled.
- ALERT-* reuses v1.2's QUOTA-03 **percentage** projection. It is not a new forecaster; SEED-002's token-based EWMA plan is superseded (token counts are `null` under `--api`, quick task `260712-ndo`).
- [Phase 05]: SESS de-dupe is one pure expression: notifiable state AND a change from the previous status -- no timestamps, no seen-set (NOTIF-02, D-03)
- [Phase 05]: Structural greps/AST checks over claude-monitor.py are defeated by prose naming the symbol they forbid (docstrings are in ast.dump) -- second occurrence this phase
- [Phase 06]: notif_allowed(kind, config) short-circuits on mute_all before the per-event lookup (D-04) -- mute wins, never OR-merges with the per-event flag
- [Phase 06]: on_notif_toggle/on_threshold_toggle follow set_active-before-connect ordering on every new widget to avoid a spurious save+rebuild on menu construction
- [Phase ?]: [Phase 07-02] session_stale reap: alive=True never short-circuits to never-reap -- only the unconditional age ceiling catches the same-pane /exit or /clear case SessionEnd never fires for
- [Phase ?]: CR-01 fix: reaped-status memory + pure sess_notify_baseline baseline resolver; rejected the exclude-alive=True-from-age-reap trap to preserve 07-02 same-pane self-heal
- **v1.5 is 2 phases** (8: daemon socket query verb; 9: the TUI renderer). Coarse granularity and the 1-2-phases-per-milestone precedent both favor one phase, but Phase 9 has no data source until Phase 8's query verb exists and is independently verifiable (connect + query the socket, no TUI needed) — a real unblocks-the-next-phase boundary, not an arbitrary horizontal-layer split.
- [Phase ?]: [Phase 08-01]: build_session_snapshot shared shape (dir/status/entered/frozen/pane/tmux) established for write_dashboard and Plan 08-02's query verb; sessions_lock wraps each self.sessions call site as one atomic read-modify-write, with reap_stale's lock kept narrow around the tmux subprocess shell-out and rebuild_menu deliberately left unlocked (Gtk-thread-only)
- [Phase ?]: [Phase 09-01]: the whole TUI substrate (socket client, usage rows, trend text, session rows, timing constants) lives in core.py above the textual boundary, so `--selfcheck` on /usr/bin/python3 proves it; claude-tui.py is left as App-class-and-CSS only
- [Phase ?]: [Phase 09-01]: query_snapshot RAISES on every failure mode (no sentinel) -- degraded-mode swallowing belongs at 09-02's worker boundary; TUI_SOCK_TIMEOUT (1.5s) < TUI_FETCH_INTERVAL (2.0s) is asserted in --selfcheck as the standing guard against fetch-thread pile-up
- [Phase ?]: [Phase 09-02]: D-10's dimming uses CSS `opacity`, NOT `text-opacity` -- textual 8.2.8 declares `opacity = FractionalProperty(children=True)` but `text_opacity = FractionalProperty()`, so text-opacity dims only the container's own content and leaves child panels bright
- [Phase ?]: [Phase 09-02]: textual ships as an OPTIONAL `tui` extra (default `uv sync` stays at zero third-party packages); runtime resolution is claude-tui.py's own PEP 723 block, so a plain ./claude-tui.py works from any cwd and the daemon's PEP 668 interpreter never gains textual
- [Phase ?]: [Phase 09-02]: both textual exit doors must be closed on every callback -- @work(exit_on_error=False) AND a blanket `except Exception` in the body; App._handle_exception "always results in the app exiting" and Timer._tick routes straight to it
- [Phase ?]: [Phase 08-02]: serve() refactored to thread-per-connection (_handle_conn) so a stalled/malformed connection only blocks its own thread; query snapshot build runs entirely inside mon.sessions_lock, matching 08-01's lock discipline (SOCK-01/02/03)

### Pending Todos

None yet.

### Blockers/Concerns

**The binding is SETTLED — Route B.** Phase 5's load-bearing decision is closed. `05-RESEARCH.md` settled it against gnome-shell 46.0's actual source (extracted from `/usr/lib/gnome-shell/libshell-14.so`) plus live D-Bus probes on the running session bus. Verdict: **`org.freedesktop.Notifications.Notify` over `Gio.DBusProxy`.** Route A (`Gio.Application` + `Gio.Notification`) is not merely costlier, it is *impossible* here — gnome-shell does `lookup_app(appId + '.desktop')`, throws `InvalidAppError`, and drops the notification silently. This is a single-file script with no install step and no `.desktop`.

Execution landmines — each one, if ignored, ships a silently broken feature. All are encoded as acceptance criteria in the plans:

- **gnome-shell ignores `expire_timeout` entirely.** It destructures it as `timeout_` (the deliberately-unused convention) and never reads it; banner life is a hardcoded `NOTIFICATION_TIMEOUT = 4000`. D-02 ("`waiting` sticks, `done` expires") must be implemented via the **`urgency` hint** — `2`/CRITICAL never arms the dismiss timer, `1`/NORMAL gets 4s then falls to the notification list. An `expire_timeout=0` vs `-1` implementation wires a knob to nothing.
- **Do not use the `resident` hint.** It means "survive being *clicked*", not "survive on screen". D-02's own parenthetical in CONTEXT.md invites this exact mistake.
- **`ActionInvoked` is a broadcast signal** — we receive *every* application's notification clicks. The handler must filter on notification ids we own, or clicking an unrelated Slack notification yanks a tmux pane into focus. Correctness *and* security (threat T-05-01).
- **The `Gio.DBusProxy` must be constructed on the Gtk main thread** (in `Monitor.__init__`, before `Gtk.main()`). Signals are delivered to the `GMainContext` the proxy was built on; construct it in `poll_loop` and clicks silently never fire.
- **Keep the project `dir` in the notification title (summary), never the body.** The body is parsed as Pango markup unconditionally (`useBodyMarkup: true`); the summary is not. D-01's shape is accidentally the secure one — a repo named `<b>x</b>` is markup injection the moment it moves into an unescaped body (threat T-05-04).
- **D-05's operative predicate is `"exhaust" in p and p["exhaust"] - now >= 900`**, not `proj >= 100` — the JS sets `exhaust` only when `proj > 100` *strictly*, so `proj >= 100` would `KeyError` at exactly 100.0. This predicate also delivers D-07 for free, confirming its "no special case, no code" claim.
- **`serve()` is unguarded** (`claude-monitor.py:1699`) — a raise in its loop kills the socket thread and every session event, permanently. `poll_loop` gained a blanket `except` + traceback in `260713-fry`; `serve()` did not. The guard goes **inside the `while`, around the per-connection body** — not around the `accept()` loop, which would swallow the shutdown path. Success Criterion 5 is exactly this.
- **`project()` (QUOTA-03) is JavaScript-only** at `claude-monitor.py:931`, inside the dashboard HTML. Phase 5 ports the ~15-line formula to Python for the poll thread and asserts it in `--selfcheck`. The JS copy **stays** — it recomputes against a live browser clock. The duplication is deliberate.
- Standing constraints: no new polling, no second data source, no new runtime dependencies, X11 only, ASCII-only in code.
- **[v1.5 planning]** `serve()`'s existing per-connection `except Exception` guard (see above) is the precedent Phase 8 inherits for SOCK-02: a malformed/stalled query connection must be contained the same way a malformed hook event already is. Phase 8 should not need a second guarding mechanism.
- **[v1.5 planning]** `self.sessions` is single-mutator today (Gtk thread only, per `reap_stale`'s docstring at `claude-monitor.py:435-440`). `write_dashboard` already reads it off-thread as a read-only snapshot into plain dicts, accepting a possible mid-iteration exception via its broad `except Exception` (D-08 posture). SOCK-03 asks for something stronger ("no torn/partial reads") — Phase 8 needs to decide at plan time whether `write_dashboard`'s accepted-risk posture satisfies that bar or whether the query responder needs `GLib.idle_add` marshaling back to the Gtk thread instead.
- **[v1.5 planning]** `textual` is a new runtime dependency (first exception to stdlib+PyGObject-only) — install/packaging (`pyproject.toml` / `install.sh`) is Phase 9's problem, not Phase 8's.

### Quick Tasks Completed

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| 260712-ndo | Poll claude-monitor with --api for official /usage numbers (drops absolute token counts) | 2026-07-12 | 04b45d7 | Verified | [260712-ndo-api-official-usage](./quick/260712-ndo-api-official-usage/) |
| 260713-fry | Fix compute_trends corrupt-record crash — sanitize via history_numeric + guard poll_loop so the daemon thread cannot die | 2026-07-13 | 6d0ec43 | Verified | [260713-fry-fix-compute-trends-corrupt-record-crash](./quick/260713-fry-fix-compute-trends-corrupt-record-crash/) |
| 260718-hgm | Despike dashboard usage-% trend chart — reuse heatmap RISE_MAX to drop upstream 100% pins before with_gaps (SEED-006) | 2026-07-18 | 4ebec5e | Verified | [260718-hgm-despike-dashboard-usage-trend-chart-seed](./quick/260718-hgm-despike-dashboard-usage-trend-chart-seed/) |
| 260718-hz5 | Restructure claude-monitor.py (2081 lines) into 4 flat modules: core.py + dashboard.py + test_claude_monitor.py + slim 580-line entry. Pure move, --selfcheck green, 65/65 defs preserved, gi isolated | 2026-07-18 | 02aef11 | Verified | [260718-hz5-restructure-claude-monitor-py-into-4-mod](./quick/260718-hz5-restructure-claude-monitor-py-into-4-mod/) |
| 260718-pkg | (fast) Move core/dashboard/test into `claude_monitor/` package; entry script stays at root; relative internal imports; pyright extraPaths=["."] so first-party import resolves. --selfcheck green | 2026-07-18 | d2ac504 | Verified | - |
| 260719-pzd | Symlink both hook scripts in install.sh (ln -sf, not install -m 0755); fixed stale ~/.claude/hooks/claude-send.py plain-file copy on this machine, root-causing the class of drift | 2026-07-19 | d9a13d3 | Verified | [260719-pzd-symlink-claude-hooks-claude-send-py-to-t](./quick/260719-pzd-symlink-claude-hooks-claude-send-py-to-t/) |
| 260724-thm | claude-tui inherits the terminal palette: self.theme = "ansi-dark" in on_mount, so the TUI renders in Ghostty/Catppuccin colors and follows terminal-theme changes (chose inherit over hardcoded catppuccin-mocha). Headless run_test + selfcheck + lint green | 2026-07-24 | 4c05121 | Complete | [260724-thm-tui-inherit-terminal-theme](./quick/260724-thm-tui-inherit-terminal-theme/) |

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Usage | ~~7-day / weekly limit display — SEED-003~~ | **DONE 2026-07-13** (QUOTA-01) | 2026-07-11 |
| Dashboard | ~~Live in-browser auto-refresh — DASH-F1~~ | **DONE 2026-07-13** (`ea00509`) | 2026-07-12 |
| Alerting | ~~Configurable threshold via env var~~ | **ACTIVE in v1.3** as CFG-05 (Phase 6) | 2026-07-11 |
| Seed | ~~SEED-002 — predictive quota alerts~~ | **ACTIVE in v1.3** as ALERT-02/03/04 (Phase 5); token-based forecaster superseded | 2026-07-13 |
| Seed | ~~SEED-004 — desktop notification when a session finishes~~ | **ACTIVE in v1.3** as SESS-01/02 + NOTIF-* (Phase 5) | 2026-07-13 |
| History | Raw data export (CSV/JSON dump) — HIST-F1 / DASH-F2 | Deferred | 2026-07-11 |
| Trends | Configurable sparkline window / aggregation period — TREND-F1 / DASH-F3 | Deferred | 2026-07-11 |
| Notifications | Quiet hours — NOTIF-F1 | Deferred (global mute CFG-02 ships the value; GNOME has its own DND) | 2026-07-13 |
| Notifications | Per-event sound / urgency — NOTIF-F2 | Deferred | 2026-07-13 |
| Alerting | Hard-threshold push (>90%) — ALERT-F1 | Deferred (the ALERT-01 icon badge stays the reactive signal) | 2026-07-13 |
| UAT | Phase 01 flagged by pre-close audit; 01-UAT.md is `[passed]` with 0 pending scenarios — audit-format false positive, no real gap | Acknowledged | 2026-07-13 |
| UAT | Phase 05 flagged by pre-close audit at v1.4 close; 05-UAT.md status reads `unknown` but 0 pending scenarios — same audit-format false positive as Phase 01, no real gap, unrelated to v1.4/Phase 7 | Acknowledged | 2026-07-20 |
| Verification | Phase 05 (Notification Path & Event Producers, v1.3) has no VERIFICATION.md — v1.3 was never run through /gsd-complete-milestone, so gsd-tools bundles Phases 5-7 into one open milestone bucket. Feature has been live since 2026-07-17 with a passing 05-REVIEW.md and 05-UAT.md; not re-verified retroactively at v1.4 close | Acknowledged (verification override) | 2026-07-20 |
| v1.5 | Click-to-focus a pane from the TUI (reusing `pane`/`tmux` fields) — deferred; the tray remains the click-to-focus surface for v1.5 | Deferred | 2026-07-20 |
| v1.5 | Standalone (no-daemon) mode reading `usage-history.jsonl` directly — deferred; shared-socket was chosen over it to get live sessions in v1.5 scope, but a fallback mode could still be added later | Deferred | 2026-07-20 |
| UAT | Phase 01 + Phase 09 flagged by pre-close audit at v1.5 close; both UATs are `[passed]` with 0 pending scenarios — audit-format false positive, no real gap. Phase 09 additionally had 2 tests skipped (scroll-retention CR-01, daemon-outage D5/WR-03), documented as non-failures verified by tests + code re-read | Acknowledged (verification override) | 2026-07-24 |
| v1.5 | TUI feels v1.0-tier — polish (color-by-threshold, progress bars, richer trends, optional pane focus) deferred to a proposed v1.6 milestone | Deferred | 2026-07-24 |
| debug | `stale-session-status-stuck` [diagnosed] flagged by pre-close audit at v1.5 close — diagnose-only session whose fix (core.session_stale reap, CR-01) already shipped in v1.4/Phase 07; not a v1.5 gap | Acknowledged | 2026-07-24 |
| quick_task | `260719-qc6-add-xdotool-zed-terminal-focus-toggle-ke` [missing] flagged by pre-close audit at v1.5 close — unrelated Zed terminal-focus keybind task, never in v1.5 (TUI) scope | Acknowledged | 2026-07-24 |

## Session Continuity

Last session: 2026-07-24T10:45:00.000Z
Stopped at: v1.6 roadmap created — Phase 10 (TUI Polish) defined, TUI-06..TUI-10 mapped, traceability filled
Resume file: None
Next: `/gsd-plan-phase 10`

## Operator Next Steps

- Phase 9 is code-complete (both plans executed). Run `./install.sh` once to pick up the new
  `~/.local/bin/claude-tui` symlink, then `just tui`.

- Verify with `/gsd-verify-work` — 09-02-PLAN.md carries 10 human-check steps. The ones with no
  automated substitute are step 5 (sparkline width, assumption A2), step 9 (tmux, assumption A1),
  the tray-menu cross-checks in steps 3-4, and step 10 (`claude-tui` on PATH).

- Plan-checker was skipped (`workflow.plan_check: false`) — the plans were not independently
  verified before execution.
