# Quick Task 260718-hz5: Restructure claude-monitor.py into 4 modular files - Context

**Gathered:** 2026-07-18
**Status:** Ready for planning

<domain>
## Task Boundary

Split the 2081-line single-file `claude-monitor.py` into 4 flat sibling files in
the repo root. This is a **pure MOVE refactor**: no behavior change, no logic
rewrite, no new features. Smallest diff that achieves the layout; function bodies
byte-identical except for necessary import lines.

Scope was decided directly with the user (do NOT re-litigate the file count or
whether to split -- both are locked). File composition measured this session:
pure logic ~490 lines, dashboard HTML/CSS/JS blob ~447, `demo()` selfcheck suite
~462, `class Monitor` ~340, daemon/focus/main ~180.
</domain>

<decisions>
## Implementation Decisions (LOCKED)

### Target layout -- 4 flat siblings, NOT a package, NO install step
- `claude-monitor.py` -- entry point: module constants/config, `class Monitor`,
  `serve` / `poll_loop` / `watch_focus` / `terminal_focused` / `pane_onscreen` /
  `looking_at`, `main`, and the `--selfcheck` dispatch. (~700 lines)
- `core.py` -- pure logic, NO GTK: project, hhmm, alert_due, alert_should_fire,
  parse_usage, fetch_usage, fmt_tokens, fmt_countdown(_wk), build_label,
  history_record/keep, parse_history, append_history, prune_history, local_bounds,
  trend_sparkline, trend_burn, trend_peak_hour, build_trend_rows, _embed_json,
  history_numeric, heatmap_buckets, _is_num, reset_marks, with_gaps, despike,
  usage7_series, latest_state. (~490 lines)
- `dashboard.py` -- render_dashboard + the `_DASH_*` HTML/CSS/JS string constants
  (_DASH_DARK/_DASH_STYLE/_DASH_EMPTY/_DASH_BODY/_DASH_JS), `_brand_icon_uri`, and
  the dashboard path/interval constants (DASH_PATH/DASH_DIR/DASH_INTERVAL/
  _DASH_META_REFRESH). (~450 lines)
- `test_claude_monitor.py` -- the `demo()` assert suite (currently ~1097-1559). (~460 lines)

### Deployment invariants (VERIFIED this session -- do not break)
- Deployed as a SYMLINK: `~/.claude/hooks/claude-monitor.py -> repo/claude-monitor.py`,
  launched by gnome-session as `/usr/bin/python3 ~/.claude/hooks/claude-monitor.py`.
- Verified: Python 3.12 resolves the symlink so `sys.path[0]` = repo dir. Plain
  `import core` / `import dashboard` from claude-monitor.py works THROUGH the symlink.
  **No sys.path bootstrap, no launch-command change, no `.desktop`, no install.**

### Import DAG (must stay acyclic)
- `core` imports from neither.
- `dashboard` imports from `core`.
- `test_claude_monitor` imports from `core` (and `dashboard` as needed).
- `claude-monitor.py` imports from `core` + `dashboard`.

### The `--selfcheck` gate is unchanged
- `python3 claude-monitor.py --selfcheck` MUST remain the verification gate (every
  GSD phase depends on it). Move `demo()` into `test_claude_monitor.py`; the
  `--selfcheck` dispatch in claude-monitor.py imports that module and runs it, so
  the exact command and its exit-0 contract are preserved.

### GTK isolation
- `gi.require_version(...)` + `from gi.repository import ...` stay ONLY in
  claude-monitor.py. `core.py` and `dashboard.py` import NO gi/GTK (keeps them pure,
  fast-importing, testable). Any moved function that references GTK belongs in
  claude-monitor.py.

### Standing project constraints
- stdlib + PyGObject only, NO new runtime dependency. ASCII-only in code.
- Preserve codedoc-style triple-quoted docstrings and existing `ponytail:` comments
  verbatim (e.g. the RISE_MAX note).
- Dashboard stays fully self-contained (inline CSS/JS, no external refs); the
  existing selfcheck assertions that enforce this must still pass.

### Claude's Discretion
- Filename `core.py` is the default; may use `usage.py` if clearer -- planner's call,
  but keep it ONE pure-logic module.
- Shared module-level constants (e.g. USAGE_THRESHOLD used by both build_label and
  the badge, POLL/interval constants) live in their OWNING module and are imported by
  cross-module users. Do NOT introduce a 5th `constants.py` -- 4 files is the target.
- Whether to `git mv` then edit vs. write-new -- either, as long as history stays
  legible and bodies stay byte-identical.
</decisions>

<specifics>
## Specific Ideas

Current line anchors (may shift; verify before moving): pure logic 155-648;
dashboard blob + render 649-1096; `demo()` 1097-1559; `class Monitor` 1560-1900;
serve/poll/focus/main 1901-2081.

Verification gates (all must pass before done):
- `python3 claude-monitor.py --selfcheck` exits 0.
- `python3 -c "import ast; [ast.parse(open(f).read()) for f in ('claude-monitor.py','core.py','dashboard.py','test_claude_monitor.py')]"` succeeds.
- `python3 -c "import core, dashboard"` succeeds standalone (no GTK needed).
- `ruff check` clean.
- SUMMARY notes the tray must be restarted (kill + relaunch) to load the new layout;
  the symlink itself is unchanged.
</specifics>

<canonical_refs>
## Canonical References

- `./.claude/CLAUDE.md` (project conventions: codedoc docstrings, ASCII-only, uv/just).
- STATE.md "Blockers/Concerns": the notification design (Route B, no `.desktop`) is
  preserved -- multi-file with a plain `python3 script.py` entry keeps "no Gio.Application,
  no .desktop", so this split does not threaten it.
</canonical_refs>
