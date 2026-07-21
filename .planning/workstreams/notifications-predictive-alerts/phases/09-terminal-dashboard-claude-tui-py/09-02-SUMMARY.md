---
phase: 09-terminal-dashboard-claude-tui-py
plan: 02
subsystem: ui
tags: [textual, tui, pep723, uv, packaging, markup-safety, degraded-mode]

# Dependency graph
requires:
  - phase: 09-01
    provides: the twelve textual-free core symbols (query_snapshot, tui_usage_rows, trend_text, sess_rows, the four timing constants) this App calls and never reimplements
  - phase: 08-daemon-socket-query-verb
    provides: the read-only `{"query": "snapshot"}` socket verb that is the TUI's only data source
provides:
  - claude-tui.py -- the PEP 723 entry script; the only file in the repo that imports textual
  - ClaudeTui -- textual App with inline CSS, one binding, two timers and one thread worker
  - the `tui` optional-dependency extra in pyproject.toml (`uv sync --extra tui`)
  - a guarded ~/.local/bin/claude-tui symlink in install.sh
  - the `just tui` recipe
affects: [v1.5 UAT, install.sh, justfile, pyproject.toml, uv.lock]

# Tech tracking
tech-stack:
  added: ["textual>=8,<9 (resolved 8.2.8)", "rich (transitive)"]
  patterns:
    - "PEP 723 inline metadata + `uv run --quiet --script` shebang: the entry script resolves its own dependency, so a plain ./claude-tui.py works from any cwd and through a symlink without a venv and without touching the PEP 668 system interpreter"
    - "Double containment on every textual callback: @work(exit_on_error=False) closes the worker door, a blanket `except Exception` in the body closes the callback door -- both are needed because App._handle_exception always exits"
    - "Every DataTable cell wrapped in rich.text.Text; every Static built markup=False -- DataTable has no per-widget markup opt-out"

key-files:
  created:
    - claude-tui.py
  modified:
    - pyproject.toml
    - install.sh
    - justfile
    - uv.lock

key-decisions:
  - "D-10's dimming uses CSS `opacity`, not the plan's `text-opacity`: textual 8.2.8 declares `opacity = FractionalProperty(children=True)` and `text_opacity = FractionalProperty()` (no children), so text-opacity would have left the three panels inside #body at full brightness"
  - "textual landed as an OPTIONAL extra (`tui`), not in `dependencies`, so the default `uv sync` still installs zero third-party packages -- the spirit of the stdlib+PyGObject-only rule this milestone makes one scoped exception to"
  - "Both entry doors shipped (Research Open Question 1): `just tui` for the house rule, plus a `[ -d ~/.local/bin ]`-guarded symlink so a machine without that directory is unaffected -- which retires research assumption A3"
  - "The version range `>=8,<9` is declared twice (PEP 723 block + pyproject extra) and must agree; uv.lock supplies the exact reproducible pin"

patterns-established:
  - "Headless textual verification via `App.run_test()` + a stubbed core.query_snapshot -- exercises CSS parsing, compose, on_mount, the worker/call_from_thread marshal and both degraded-mode branches without a TTY. Not committed (it would need textual on the selfcheck interpreter); run ad hoc with `uv run --with 'textual>=8,<9'`"

requirements-completed: [TUI-01, TUI-02, TUI-03, TUI-04, TUI-05]

coverage:
  - id: D1
    description: "Usage panel renders core.tui_usage_rows output -- a 5h row and a 7d row visible at once with percent, tokens, reset countdown and burn rate"
    requirement: "TUI-01"
    verification:
      - kind: integration
        ref: "headless run_test: usage panel == '5h  62%  1.2M / 2.0M  resets in 1h 3m  burn: 23k tok/hr\\n7d  41%  week resets in 3d 1h'"
        status: pass
      - kind: manual
        ref: "09-02-PLAN.md human-check step 3 (cross-check against the tray menu)"
        status: pending
    human_judgment: true
  - id: D2
    description: "Trends panel prints snapshot['trends'] verbatim through core.trend_text; nothing recomputed (D-05)"
    requirement: "TUI-02"
    verification:
      - kind: static
        ref: "grep over non-comment lines for build_trend_rows|trend_sparkline|fetch_usage|open( -> 0"
        status: pass
      - kind: integration
        ref: "headless run_test: 3-row trends echoed verbatim; trends=None -> 'trends: collecting history...'"
        status: pass
    human_judgment: false
  - id: D3
    description: "Sessions DataTable ordered waiting -> running -> done with status/project/time columns"
    requirement: "TUI-03"
    verification:
      - kind: integration
        ref: "headless run_test: rows == [['waiting','[bold]evil','2m 14s'], ['running','[/]','1m 00s'], ['done','dotfiles','1h 22m']]"
        status: pass
    human_judgment: false
  - id: D4
    description: "Two set_interval timers (2s fetch, 1s render) driven by core's constants, no manual-refresh key"
    requirement: "TUI-04"
    verification:
      - kind: static
        ref: "grep -c set_interval == 2; core.TUI_FETCH_INTERVAL / core.TUI_TICK_INTERVAL present; BINDINGS holds exactly one tuple"
        status: pass
      - kind: integration
        ref: "live pty launch: real usage rows rendered from the running daemon with no keypress"
        status: pass
    human_judgment: false
  - id: D5
    description: "Cold start shows a centered message (D-11); an outage after a good snapshot dims the last data with an honest header (D-10); the app retries forever and never exits (D-12)"
    requirement: "TUI-05"
    verification:
      - kind: integration
        ref: "headless run_test: cold-start branch, stale branch keeping 3 rows + 'daemon unreachable -- last update HH:MM:SS', recovery back to 'live', malformed snapshot survived via the tick guard"
        status: pass
      - kind: static
        ref: "grep -c exit_on_error=False == 1; grep -c 'except Exception' == 2"
        status: pass
      - kind: manual
        ref: "09-02-PLAN.md human-check steps 1, 2, 8 (real terminal, real daemon restart)"
        status: pending
    human_judgment: true
  - id: D6
    description: "Markup-hostile project directory names render literally and cannot exit the app (T-09-01)"
    requirement: "TUI-03"
    verification:
      - kind: integration
        ref: "headless run_test: dirs '[bold]evil' and '[/]' came back byte-identical through DataTable cells; no MarkupError"
        status: pass
      - kind: static
        ref: "single add_row call site wraps every cell in Text(; grep -c 'Static(' == grep -c 'markup=False' == 3"
        status: pass
    human_judgment: false
  - id: D7
    description: "A plain ./claude-tui.py runs from a foreign cwd, resolving textual itself, with textual never reaching the daemon's PEP 668 interpreter"
    requirement: "TUI-04"
    verification:
      - kind: integration
        ref: "`script -qec 'cd /tmp && <repo>/claude-tui.py'` -> app stayed up 20s rendering live 5h/7d rows, no traceback, no 'Installed N packages' line"
        status: pass
      - kind: integration
        ref: "/usr/bin/python3 claude-monitor.py --selfcheck -> exit 0 (the textual boundary holds)"
        status: pass
      - kind: integration
        ref: "install.sh under `set -euo pipefail` both with and without ~/.local/bin -> symlink created / guard holds, exit 0 both times"
        status: pass
    human_judgment: false
  - id: D8
    description: "TUI-04 backstop: a coincident 2s fetch and 1s render tick cannot observe a half-applied snapshot"
    requirement: "TUI-04"
    verification:
      - kind: backstop
        ref: "apply_snapshot runs on the event loop via call_from_thread and rebinds self.snapshot in a single assignment before render_all; render_all reads it into a local first"
        status: human_needed
    human_judgment: true

# Metrics
duration: 22min
completed: 2026-07-21
status: complete
---

# Phase 9 Plan 02: claude-tui.py and Packaging Summary

**A 170-line PEP 723 textual App -- three stacked panels, one key, two timers and one socket worker -- plus the packaging that makes `./claude-tui.py` run from anywhere while `just selfcheck` keeps running on an interpreter that has never seen textual.**

## Performance

- **Duration:** ~22 min
- **Tasks:** 2
- **Files created:** 1 | **Files modified:** 4

## Accomplishments

- `claude-tui.py` is the only file in the repo that imports textual, and the boundary is stated in both directions in its module docstring. It contains layout, CSS, timers, worker marshaling and degraded-mode presentation -- and no formatting logic: every rendered string comes from a Plan 09-01 `core` helper.
- **Both exit doors closed.** `@work(thread=True, exclusive=True, exit_on_error=False)` plus a blanket `except Exception` in the worker body, and a second guard around the 1s render tick. `App._handle_exception` is documented "Always results in the app exiting" and `Timer._tick` routes straight to it, so neither guard is redundant. Verified by driving a `FileNotFoundError`, a recovery, and a malformed snapshot through a live headless app.
- **Markup safety, verified end to end.** The single `add_row` call site wraps every cell in `rich.text.Text`; all three `Static` widgets are built `markup=False`. A headless run with sessions in `/[bold]evil` and `/[/]` returned both names byte-identical and the app stayed up -- `[/]` is the case that would have raised `MarkupError` inside a timer callback and exited the app (T-09-01).
- **Degraded mode behaves on all three branches:** cold start hides `#body` and centers a message naming `just start`; an outage after a good snapshot keeps all three rows on screen, adds `.stale`, and sets the header to `daemon unreachable -- last update HH:MM:SS`; the next success clears the class silently with no counter and no backoff (D-12).
- **Packaging works from a foreign cwd.** `script -qec 'cd /tmp && <repo>/claude-tui.py'` launched the real script, resolved textual through the PEP 723 block, connected to the running daemon and rendered live `5h 27%` / `7d 34%` rows -- with no venv activated, no traceback, and no cold-run "Installed N packages" line leaking into frame one (`--quiet` doing its job).
- **The scope fence held:** `claude-monitor.py`, `claude-send.py` and `claude_monitor/dashboard.py` are byte-unchanged, and `/usr/bin/python3 claude-monitor.py --selfcheck` still exits 0.

## Task Commits

1. **Task 1: Build claude-tui.py -- the textual App, CSS, and two-timer refresh loop** - `f96e5aa` (feat)
2. **Task 2: Package textual and wire the three entry points** - `35320de` (chore)

## Files Created/Modified

- `claude-tui.py` (new, 0755) - PEP 723 header + `ClaudeTui`: `CSS`, `BINDINGS`, `TITLE`, `compose`, `on_mount`, `fetch`, `apply_snapshot`, `mark_stale`, `tick`, `render_all`
- `pyproject.toml` - new `[project.optional-dependencies]` table with `tui = ["textual>=8,<9"]`; `dependencies = []` unchanged
- `install.sh` - guarded `~/.local/bin/claude-tui` symlink plus its guarded echo-back line
- `justfile` - new `tui` recipe; no existing recipe repointed (`grep -c python3 justfile` still 3)
- `uv.lock` - the 10-package transitive set pinned (T-09-SC mitigation)

## Decisions Made

- **`opacity` instead of `text-opacity` for D-10.** See Deviations -- this is the one place the implementation departs from the plan's literal CSS, and it is the difference between D-10 dimming and D-10 doing nothing visible.
- **`cursor_type = "none"` on the DataTable.** D-01 specifies no navigation, and a visible cursor cell on a glance-only surface implies interaction that does not exist.
- **No panel captions.** D-01's mock shows `trends` / `SESSIONS` labels, but the plan's CSS specifies `border-bottom` only, and a `border_title` needs a full border. The panels self-describe (rows lead with `5h`/`7d`; the table carries `status`/`project`/`time` headers; the collecting state literally reads `trends: collecting history...`). Left as the plan wrote it rather than growing the CSS for a caption.
- **The headless smoke harness was deliberately not committed.** It imports textual, so putting it in `claude_monitor/test_claude_monitor.py` would turn `just selfcheck` red on the system interpreter -- the exact boundary this phase exists to protect. It lives in the scratchpad and is reproducible from this summary's coverage refs.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] D-10's dimming used a style that does not reach child widgets**

- **Found during:** Task 1
- **Issue:** The plan (and 09-RESEARCH.md Pattern 5) specified `#body.stale { text-opacity: 60%; }`. In textual 8.2.8, `css/styles.py:319-321` declares `opacity = FractionalProperty(children=True)` but `text_opacity = FractionalProperty()` -- no `children=True`. `text-opacity` therefore dims only the widget's own content, and `#body` is an empty container: its three child panels would have stayed at full brightness. D-10's "keeps the last data on screen (dimmed)" would have been silently inert, leaving stale numbers looking exactly like live ones -- the failure this plan's first prohibition forbids.
- **Fix:** `#body.stale { opacity: 60%; }`, with a CSS comment recording why. `Widget.opacity` (`widget.py:629-636`) multiplies down the ancestor chain, so the whole block dims.
- **Files modified:** `claude-tui.py`
- **Commit:** `f96e5aa`

No architectural changes, no auth gates, no blocked tasks.

## Issues Encountered

- The plan's acceptance criterion `grep -c 'dependencies = \[\]' pyproject.toml == 1` initially read 2, because the rationale comment above the new extra quoted that literal while explaining it. Reworded the comment to "the empty top-level dependency list above" -- the criterion is measuring that the empty list survived, and a comment quoting it defeats the measurement.
- `Static.renderable` does not exist in textual 8.x (the content lives behind the `content` property and a `Visual`). Only affected the throwaway smoke harness.

## Verification

Automated, all green:

- `just selfcheck` -> exit 0; `/usr/bin/python3 claude-monitor.py --selfcheck` -> exit 0
- `just lint` -> exit 0
- `test -x claude-tui.py`; `head -1` is exactly `#!/usr/bin/env -S uv run --quiet --script`; `python3 -m py_compile` -> exit 0
- Source gates: `Static(` 3 == `markup=False` 3; `add_row` 1 and that line contains `Text(`; `exit_on_error=False` 1; `except Exception` 2; `set_interval` 2; `BINDINGS` 1 and `"q"` 1; `query_snapshot` 3; forbidden-pattern grep over non-comment lines -> 0; whole-file non-ASCII scan -> 0 lines
- `uv sync --extra tui` -> exit 0, textual 8.2.8; `textual>=8,<9` appears exactly once in each of `pyproject.toml` and `claude-tui.py`; `dependencies = []` still 1
- `bash -n install.sh` -> exit 0; full `set -euo pipefail` run WITH `~/.local/bin` creates the symlink; full run WITHOUT it exits 0 (guard holds)
- `just --list` shows `tui` with its doc comment; `grep -c python3 justfile` unchanged at 3
- `git diff --stat claude-monitor.py claude-send.py claude_monitor/dashboard.py` -> empty

Runtime, via a headless `App.run_test()` harness with `core.query_snapshot` stubbed: D-11 cold start, first live snapshot (`sub_title == "live"`), D-03 ordering, markup-hostile dirs literal, D-10 stale keeping all 3 rows under an honest header, D-12 recovery, TUI-04 all-empty snapshot, and a malformed snapshot caught by the tick guard with the app still running.

Runtime, real script under a pty from `/tmp`: live 5h/7d rows against the running daemon, no traceback, no uv noise.

## Known Stubs

None.

## Threat Flags

None. The plan's register covers every surface this plan touched; no new endpoint, auth path, file access or schema crossed a trust boundary.

## Follow-Up / Human Verification

The plan's 10 human-check steps run at phase UAT (`workflow.human_verify_mode: end-of-phase`). Steps 1, 2, 7 and 8 have equivalent automated evidence above; the ones with no automated substitute are:

- **Step 5 (sparkline width, research assumption A2)** -- ambiguous-width glyph rendering in Ghostty and under tmux.
- **Step 9 (tmux, research assumption A1)** -- border/color readability with `TERM=tmux-256color`.
- **Step 3/4 cross-checks against the live tray menu** -- the numbers must agree exactly.
- **Step 10** -- `claude-tui` on PATH after a real `./install.sh`, and `q` restoring the terminal.
- **The TUI-04 backstop (D8 above)** abstains to `human_needed` by design: the two-timer coincidence is a runtime-timing property that no source grep and no `--selfcheck` assert can prove.

## User Setup Required

Run `./install.sh` to pick up the new `~/.local/bin/claude-tui` symlink. No other configuration.

## Next Phase Readiness

- Phase 9 is code-complete; the remaining work is UAT (`/gsd-verify-work`).
- The first cold run of `./claude-tui.py` on a new machine pays uv's resolve cost once; warm runs add ~6ms.

## Self-Check: PASSED

- `claude-tui.py` - FOUND (created, mode 0755)
- `pyproject.toml` - FOUND (modified)
- `install.sh` - FOUND (modified)
- `justfile` - FOUND (modified)
- `uv.lock` - FOUND (modified)
- Commit `f96e5aa` - FOUND
- Commit `35320de` - FOUND

---
*Phase: 09-terminal-dashboard-claude-tui-py*
*Completed: 2026-07-21*
