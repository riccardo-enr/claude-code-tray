---
phase: quick-260713-fry
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - claude-monitor.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "A corrupt record in ~/.claude/usage-history.jsonl (string burn, NaN burn, far-future t) never reaches trend_sparkline / trend_burn / trend_peak_hour."
    - "compute_trends produces the SAME rows for a corrupt+clean history as for the clean records alone."
    - "poll_loop survives any exception raised inside one iteration: usage polling, trend recompute and dashboard regeneration keep running."
    - "A persistent poll_loop failure is visible (traceback on stderr / journal), not silently swallowed."
    - "python3 claude-monitor.py --selfcheck still prints ok -- every pre-existing assert (v1.0 / Phase-2 / Phase-3 / Phase-4) passes."
  artifacts:
    - claude-monitor.py
  key_links:
    - "Monitor.compute_trends -> build_trend_rows -> history_numeric (same sanitizer choke point render_dashboard already uses)"
    - "poll_loop while-body -> try/except Exception -> traceback.print_exc()"
---

<objective>
Stop one corrupt line in `~/.claude/usage-history.jsonl` from permanently bricking the
tray's poll thread.

Root cause: `Monitor.compute_trends` feeds `parse_history` output straight into
`trend_sparkline` / `trend_burn` / `trend_peak_hour`. `parse_history` only validates a
numeric `t`; `pct` / `burn` are untrusted. A string `burn` raises TypeError, `t: 1e18`
raises OSError in `fromtimestamp`, a NaN `burn` silently renders "nan/hr". The existing
`try/except OSError` in `compute_trends` wraps ONLY the file read, and `poll_loop`'s
while-body has no guard at all -- so the raise escapes `poll_loop` and the daemon thread
DIES. Usage polling, trends and dashboard regeneration all stop until the tray restarts.

Purpose: route trend history through `history_numeric` (the sanitizer `render_dashboard`
already uses) AND make the poll thread unkillable, so no future raise can repeat this.
Output: modified `claude-monitor.py` (single source file), `--selfcheck` prints `ok`.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
</execution_context>

<context>
@.planning/STATE.md
@claude-monitor.py

Key existing code (do NOT change its semantics -- only WHERE the sanitizer is applied):
- `history_numeric(records)` (line ~416): drops any record whose `t`/`pct`/`burn` is
  non-numeric, non-finite, or whose `t` is outside `0 < t < 4102444800`. Already correct.
- `render_dashboard` (line ~953): calls `history_numeric(records)` on its FIRST line. This
  is the pattern to mirror.
- `Monitor.compute_trends` (line ~1508): the broken path -- `parse_history` then straight
  into trend math.
- `Monitor.write_dashboard` (line ~1541): already wraps its whole body in a broad
  `except Exception` with a `ponytail:` comment naming the tradeoff. Mirror that style.
- `poll_loop` (line ~1669): unguarded while-body.
- `demo()` (line ~989): assert-based self-check, run via `--selfcheck`, ends with
  `print("ok")`. Phase-4 asserts for `history_numeric` live around line ~1242.

House rules (hard):
- ASCII-only in the Python source. No `+/-`, no arrows, no unicode punctuation in comments.
- Stdlib only, no new dependencies.
- codedoc style: triple-quoted docstrings for prose; `#` only for short annotations.
- A deliberate shortcut gets a `ponytail:` comment naming the tradeoff and upgrade path.
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Route trend history through history_numeric (root cause) + prove it in demo()</name>
  <files>claude-monitor.py</files>
  <behavior>
    New module-level `build_trend_rows(records, now)` -> `None` (collecting state) or the
    list of trend row strings. It is the pure, Gtk-free core of `compute_trends`, so
    `demo()` can exercise the real path without instantiating `Monitor`.

    - build_trend_rows(clean_records, now) == the rows compute_trends builds today
      (sparkline, "today X/hr | wk Y/hr", optional "peak hour: HH:00 (Z/hr)").
    - build_trend_rows(clean + corrupt, now) == build_trend_rows(clean, now)
      where corrupt = a string `burn`, a NaN `burn`, and a `t` of 1e18. This is the assert
      that FAILS today: the string burn raises TypeError inside trend_burn.
    - build_trend_rows(only_corrupt_records, now) is None  (all dropped -> collecting)
    - build_trend_rows([], now) is None
    - No call raises.
  </behavior>
  <action>
    Extract the pure tail of `Monitor.compute_trends` into a module-level function
    `build_trend_rows(records, now)`, placed next to the other pure trend helpers (after
    `trend_peak_hour`, before `_embed_json`). Its FIRST statement sanitizes:
    `records = history_numeric(records)`. Then keep the existing logic byte-for-byte:
    the `TREND_MIN_SPAN` span check (now evaluated on sanitized records, so a far-future
    `t` can no longer inflate the span), the `trend_sparkline` row over
    `history_keep(r, now, 1)`, the `local_bounds` / `trend_burn` "today X/hr | wk Y/hr"
    row, and the optional `trend_peak_hour` row. Return `None` instead of assigning
    `self.trends = None`; return `rows` instead of assigning `self.trends = rows`.

    Rewrite `Monitor.compute_trends` to: keep its `try` / `except OSError: return` around
    the file read (missing/unwritable file must still degrade to last-known trends without
    touching `self.trends`), then `self.trends = build_trend_rows(records, now)`. Move the
    existing `ponytail:` no-lock comment with the assignment. Update the docstring to say
    the sanitizer is `history_numeric` -- the SAME choke point `render_dashboard` uses --
    so a corrupt record is dropped before any trend math, and note why the function was
    split out (Gtk-free, so `demo()` covers the real path).

    Do NOT modify `history_numeric`, `trend_burn`, `trend_peak_hour`, `trend_sparkline` or
    `history_keep`.

    Extend `demo()` in the Phase-3 trend section (after the existing `trend_peak_hour`
    asserts, ~line 1234) with a `build_trend_rows` block covering the behavior above.
    Build the clean records so the span check passes (spread > TREND_MIN_SPAN) and so
    `trend_burn`/`trend_peak_hour` return real values; use a fixed `now` derived from
    `time.time()` so the local_bounds day/week windows contain the records. Assert
    equality of the corrupt-mixed result against the clean-only result -- that single
    assert is the regression guard and it fails without this fix.
  </action>
  <verify>
    <automated>python3 claude-monitor.py --selfcheck</automated>
  </verify>
  <done>
    `--selfcheck` prints `ok`. `build_trend_rows` exists at module level, its first
    statement is `records = history_numeric(records)`, and `Monitor.compute_trends` calls
    it. Reverting only the `history_numeric` line makes `--selfcheck` fail (TypeError).
    Every pre-existing assert still passes.
  </done>
</task>

<task type="auto">
  <name>Task 2: Guard poll_loop so the daemon thread can never die permanently</name>
  <files>claude-monitor.py</files>
  <action>
    Add `import traceback` to the stdlib import block (alphabetical: after `import time`,
    before `import webbrowser`).

    In `poll_loop`, wrap the ENTIRE while-body -- `fetch_usage`, `append_history`, the
    `compute_trends` throttle, the `write_dashboard` throttle, the `GLib.idle_add`, and the
    `prune_history` throttle -- in `try: ... except Exception: traceback.print_exc()`.
    Keep the `prune_history(time.time())` startup call and the `last_*` initializers
    OUTSIDE the loop, unchanged.

    Keep `time.sleep(POLL_INTERVAL)` OUTSIDE the try, as the last statement of the while
    body, so a failing iteration is still throttled and cannot hot-spin.

    Address the tension explicitly with a `ponytail:` comment on the except, naming both
    sides: a blanket swallow could mask a real bug, so the degradation is made OBSERVABLE
    -- `traceback.print_exc()` writes the full traceback to stderr (the journal) on EVERY
    failing iteration, so a persistent failure is loud and repeated rather than silent,
    while a transient one costs one poll. State the upgrade path (surface it in the tray
    label if a real bug ever hides here). This mirrors `write_dashboard`'s existing broad
    `except Exception` and its ponytail comment -- match that voice.

    ASCII only, no new dependencies.
  </action>
  <verify>
    <automated>python3 claude-monitor.py --selfcheck && python3 -c "import ast,sys; src=open('claude-monitor.py').read(); fn=[n for n in ast.walk(ast.parse(src)) if isinstance(n,ast.FunctionDef) and n.name=='poll_loop'][0]; w=[n for n in fn.body if isinstance(n,ast.While)][0]; assert any(isinstance(n,ast.Try) for n in w.body), 'poll_loop while-body has no try'; assert isinstance(w.body[-1],ast.Expr), 'sleep must be last and outside the try'; print('guard ok')"</automated>
  </verify>
  <done>
    `--selfcheck` prints `ok` (no regressions) and the AST check prints `guard ok`: the
    poll_loop while-body contains a `try`, and the trailing `time.sleep` sits outside it.
    An exception raised anywhere in one iteration prints a traceback and the loop
    continues to the next poll.
  </done>
</task>

</tasks>

<verification>
```bash
python3 claude-monitor.py --selfcheck   # must print: ok
rtk proxy grep -n "history_numeric" claude-monitor.py   # 3 sites: def, render_dashboard, build_trend_rows
LC_ALL=C rtk proxy grep -nP "[^\x00-\x7F]" claude-monitor.py   # only pre-existing SPARK_GLYPHS/icon data
```
Manual sanity (optional): append a corrupt line to a COPY of the history file and confirm
`build_trend_rows(parse_history(open(copy).read()), time.time())` returns rows without
raising.
</verification>

<success_criteria>
- Corrupt records (string `burn`, NaN `burn`, `t = 1e18`) are dropped by `history_numeric`
  before ANY trend math runs -- `compute_trends` cannot raise on them.
- `poll_loop` survives any per-iteration exception; the daemon thread keeps polling,
  recomputing trends and regenerating the dashboard.
- A persistent failure prints a traceback every poll -- observable, not masked.
- `python3 claude-monitor.py --selfcheck` prints `ok`; no existing assert removed or
  weakened.
- ASCII-only source, stdlib only, single file touched.
</success_criteria>

<output>
Create `.planning/quick/260713-fry-fix-compute-trends-corrupt-record-crash/260713-fry-SUMMARY.md` when done.
</output>
