---
phase: 02-usage-history-persistence
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - claude-monitor.py
autonomous: true
requirements: [HIST-01, HIST-02, HIST-03]

must_haves:
  truths:
    - "HIST-01: each successful poll appends exactly one JSON line to ~/.claude/usage-history.jsonl with the compact schema {t:<int epoch>, pct, tokens_used, token_limit, burn}; t is int(time.time()) of the poll (NOT resets_at_epoch); burn is the RAW per-MINUTE value (Phase 03 converts to per-hour); a poll where fetch_usage() returned None writes NOTHING."
    - "HIST-02: on startup and at most ~once every PRUNE_INTERVAL thereafter, records with t < now - HISTORY_DAYS*86400 are dropped; HISTORY_DAYS defaults 30, env-overridable via CLAUDE_TRAY_HISTORY_DAYS parsed with the guarded int()/except ValueError -> default pattern; the rewrite is atomic (survivors written to a temp file in the same dir, then os.replace over the original), never truncate-in-place."
    - "HIST-03: every file op (append, read-for-prune, replace) swallows OSError so a missing/unwritable path or full disk degrades to 'history just doesn't persist' without crashing or blocking the poll; the reader skips any line that fails json.loads (per-line try/except), tolerating a half-written trailing line from a killed process."
    - "All history file I/O runs on the existing poll_loop daemon thread (never in apply_usage, never on the Gtk main loop); no new thread and no new polling loop are added."
    - "v1.0 stays green: python3 claude-monitor.py --selfcheck still passes with every existing assert intact, plus new asserts for record construction, the retention predicate, and tolerant parse of a mixed valid/corrupt blob."
  artifacts:
    - "claude-monitor.py (extended in place; stdlib json/os/time/tempfile + existing PyGObject only; no new files, no new deps)"
    - "HISTORY_PATH, HISTORY_DAYS (env-parsed), PRUNE_INTERVAL constants; history_record(), history_keep(), parse_history(), append_history(), prune_history(); poll_loop append + startup/opportunistic prune wiring; extended demo()."
  key_links:
    - "poll_loop (daemon thread): fetch_usage() -> on success append_history(history_record(usage, time.time())) BEFORE GLib.idle_add(mon.apply_usage, usage) -> keeps all file I/O off the Gtk main loop by construction."
    - "startup prune + the in-process last_prune timer live inside poll_loop (not apply_usage, not main); prune_history rewrites atomically via a temp file in the same dir + os.replace."
    - "parse_history's per-line json.loads try/except is the corruption-tolerance boundary; history_keep(rec, now, days) is the retention predicate both prune_history and Phase 03 reuse."
---

<objective>
Extend the single-file `claude-monitor.py` tray helper so every successful usage poll is
durably recorded to an append-only JSONL history store at `~/.claude/usage-history.jsonl`
(HIST-01), kept bounded by a retention window pruned atomically at startup and periodically
(HIST-02), with fully defensive I/O that never crashes or blocks the long-lived tray and a
reader that tolerates corrupt/partial lines (HIST-03). This is the write/foundation half of
v1.1; Phase 03 reads what this phase writes.

Purpose: persist a durable, bounded usage timeline the trend views (Phase 03) will read,
without ever destabilizing the tray or adding a dependency, thread, or poll.
Output: an extended `claude-monitor.py` with the pure history logic (record builder,
retention predicate, tolerant loader) plus its `--selfcheck` asserts, and the poll_loop
wiring (append on success, startup + opportunistic atomic prune) with OSError-swallowing I/O.
No new dependencies, no new runtime files, no new threads or polling.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/02-usage-history-persistence/02-CONTEXT.md
@claude-monitor.py
</context>

## Artifacts this phase produces

All added to `claude-monitor.py` (no new files):

Module-level constants (join the existing `CLAUDE_TRAY_*` config block near lines 33-52):
- `HISTORY_PATH` -- `os.path.expanduser("~/.claude/usage-history.jsonl")`.
- `HISTORY_DAYS` -- retention window in days, default `30`, env override `CLAUDE_TRAY_HISTORY_DAYS`, parsed with the SAME guarded `int(...)`/`except ValueError -> default` pattern already used for `POLL_INTERVAL` (lines 45-48).
- `PRUNE_INTERVAL` -- seconds between opportunistic prunes, `6 * 3600` (>= 6h per CONTEXT; planner-picked constant, see decisions).

Pure functions (testable, no I/O):
- `history_record(usage, now)` -- build the compact record `{"t": int(now), "pct": used_percentage, "tokens_used": ..., "token_limit": ..., "burn": burn_rate_per_min}` from the normalized usage dict. `t` is the wall-clock poll time (NOT `resets_at_epoch`); `burn` is stored RAW per-minute.
- `history_keep(rec, now, days)` -- retention predicate: `True` when `rec["t"] >= now - days*86400`, else `False`. Reused by `prune_history` and Phase 03.
- `parse_history(text)` -- tolerant loader: split into lines, per-line `json.loads` in try/except, skip empties and any line that fails to parse, return the list of surviving records.

Defensive I/O functions (swallow `OSError`, run on the poll daemon thread):
- `append_history(record)` -- append one `json.dumps(record) + "\n"` line to `HISTORY_PATH`.
- `prune_history(now)` -- read + `parse_history` the file, filter with `history_keep`, write survivors to a temp file in the same dir, then `os.replace` over the original (atomic; never truncate-in-place).

Wiring:
- `poll_loop` -- startup prune before the loop; append on each successful poll (off the Gtk main loop, before `idle_add`); opportunistic prune via an in-process `last_prune` timer.
- `demo()` + `--selfcheck` -- new asserts for `history_record`, `history_keep`, and tolerant `parse_history`, added alongside the intact v1.0 asserts.

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Pure history logic (record builder, retention predicate, tolerant loader) with self-check</name>
  <files>claude-monitor.py</files>
  <read_first>
    - claude-monitor.py: the config block ~lines 33-52 (reuse the guarded `int()`/`except ValueError -> default` env pattern verbatim for HISTORY_DAYS); parse_usage ~lines 55-85 (the normalized usage dict keys: tokens_used, token_limit, used_percentage, resets_at_epoch, burn_rate_per_min); demo() ~lines 138-207 (extend it -- keep every existing assert; still print "ok" exactly once).
    - .planning/phases/02-usage-history-persistence/02-CONTEXT.md (LOCKED record schema, retention rule, tolerant-parse rule).
  </read_first>
  <behavior>
    New asserts added to demo() (existing v1.0 asserts stay intact):
    - Record construction: with now0 = int(time.time()) and a usage dict {tokens_used 417000,
      token_limit 88000, used_percentage 473.5, resets_at_epoch now0+7380, burn_rate_per_min 315615.2},
      history_record(usage, now0) == {"t": now0, "pct": 473.5, "tokens_used": 417000,
      "token_limit": 88000, "burn": 315615.2}. Pins t == int(now0) (NOT resets_at_epoch) and burn
      stored RAW per-minute (315615.2, unconverted).
    - Retention predicate: history_keep({"t": now0 - 40*86400}, now0, 30) is False (40 days old dropped);
      history_keep({"t": now0 - 1*86400}, now0, 30) is True (1 day old kept).
    - Tolerant parse: parse_history of a 3-line blob whose middle line is corrupt
      (a valid record line, then a non-JSON line, then another valid record line) returns exactly the
      two well-formed records in order; the bad line is skipped, not raised on.
  </behavior>
  <action>
    Add the three constants to the config block near lines 33-52: HISTORY_PATH via
    os.path.expanduser("~/.claude/usage-history.jsonl"); HISTORY_DAYS from env
    CLAUDE_TRAY_HISTORY_DAYS default 30, using the SAME guarded try/int()/except ValueError -> 30
    shape as POLL_INTERVAL at lines 45-48; PRUNE_INTERVAL = 6 * 3600 with a one-line note that it is
    the opportunistic-prune cadence (>= 6h, planner-picked).

    Implement history_record(usage, now): return the compact dict {"t": int(now), "pct":
    usage["used_percentage"], "tokens_used": usage["tokens_used"], "token_limit":
    usage["token_limit"], "burn": usage["burn_rate_per_min"]}. Add a codedoc-style docstring noting t
    is the wall-clock poll time (int(time.time()) at the call site), NOT resets_at_epoch, and that burn
    is stored as the RAW per-MINUTE value the source carries so Phase 03 can convert to per-hour once
    without double-converting.

    Implement history_keep(rec, now, days): return rec["t"] >= now - days * 86400 (records strictly
    older than the window are dropped). Keep it a pure boolean predicate reused by prune_history and
    Phase 03.

    Implement parse_history(text): for each line in text.splitlines(), strip it, skip empties, and
    json.loads it inside a per-line try/except that skips (continues past) any line that fails to
    parse; collect and return the list of surviving records in order. This tolerates a corrupt or
    half-written trailing line.

    Extend demo() with the asserts in the behavior block, placed after the existing v1.0 asserts and
    before the single print("ok"); do not remove or weaken any existing assert. ASCII only;
    codedoc-style triple-quoted docstrings for prose doc blocks per project CLAUDE.md.
  </action>
  <verify>
    <automated>python3 claude-monitor.py --selfcheck && rg -q "def history_record\(" claude-monitor.py && rg -q "def history_keep\(" claude-monitor.py && rg -q "def parse_history\(" claude-monitor.py && rg -q "HISTORY_PATH" claude-monitor.py && rg -q "CLAUDE_TRAY_HISTORY_DAYS" claude-monitor.py && python3 -c "import ast; ast.parse(open('claude-monitor.py').read()); print('parse-ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `python3 claude-monitor.py --selfcheck` exits 0 and prints ok, with the existing v1.0 asserts (parse_usage / fmt_tokens / build_label) still present and passing.
    - claude-monitor.py contains `def history_record(`, `def history_keep(`, `def parse_history(`, `HISTORY_PATH`, and `HISTORY_DAYS`.
    - HISTORY_DAYS is parsed with the guarded `int(...)`/`except ValueError -> 30` pattern over env `CLAUDE_TRAY_HISTORY_DAYS`, mirroring POLL_INTERVAL at lines 45-48.
    - history_record sets `t` to `int(now)` (never resets_at_epoch) and stores `burn` as the raw per-minute value (asserted equal to 315615.2, unconverted).
    - history_keep drops a `now-40d` record and keeps a `now-1d` record at days=30.
    - parse_history returns only the well-formed records from a mixed valid/corrupt blob (bad line skipped, no exception).
  </acceptance_criteria>
  <done>The pure history logic (record builder, retention predicate, tolerant loader) and the three constants exist, and the extended assert-based `--selfcheck` passes with every v1.0 assert intact.</done>
</task>

<task type="auto">
  <name>Task 2: Wire history into poll_loop -- append on success, startup + opportunistic atomic prune, defensive I/O</name>
  <files>claude-monitor.py</files>
  <read_first>
    - claude-monitor.py: poll_loop ~lines 405-411 (the daemon-thread loop where fetch_usage runs and marshals via GLib.idle_add -- the append hook goes here, before idle_add); apply_usage ~lines 297-312 (confirm history is NOT written here -- it runs on the Gtk main thread); main ~lines 442-456 (thread startup, unchanged); the stdlib import block ~lines 12-17 (add tempfile).
    - .planning/phases/02-usage-history-persistence/02-CONTEXT.md (LOCKED: write from poll_loop never apply_usage; prune startup + opportunistic not per-write; atomic temp-file + os.replace; swallow OSError everywhere).
  </read_first>
  <action>
    Add `import tempfile` to the stdlib import block (json/os/socket/subprocess/threading/time).

    Implement append_history(record): open HISTORY_PATH in append text mode, write
    json.dumps(record) + "\n", the whole op inside a try/except OSError that swallows the error and
    returns (a missing/unwritable path or full disk degrades to "history just doesn't persist"). Rely
    on ~/.claude existing (it is the Claude Code home the CLI itself lives under); the OSError swallow
    covers the case where it does not.

    Implement prune_history(now): inside one try/except OSError that swallows and returns, read
    HISTORY_PATH's text, parse it with parse_history, filter to survivors with history_keep(rec, now,
    HISTORY_DAYS), then write the survivors atomically -- create a temp file in the SAME directory as
    HISTORY_PATH (tempfile.mkstemp(dir=os.path.dirname(HISTORY_PATH))), write each survivor as
    json.dumps(rec) + "\n", flush/close it, then os.replace(tmp, HISTORY_PATH). Never truncate the
    original in place. On any OSError (including the file not existing) swallow and leave the original
    untouched; clean up the temp file if the replace did not happen.

    Wire into poll_loop: before the `while True` loop, run one startup prune -- prune_history(time.time())
    -- and initialize last_prune = time.time(); keep all this on the daemon thread so file I/O never
    touches the Gtk main loop. Inside the loop, after `usage = fetch_usage()` and BEFORE
    GLib.idle_add(mon.apply_usage, usage): when usage is not None, call
    append_history(history_record(usage, time.time())) (a None poll writes nothing). After the idle_add,
    add the opportunistic prune: now = time.time(); if now - last_prune >= PRUNE_INTERVAL:
    prune_history(now); last_prune = now. Keep the existing time.sleep(POLL_INTERVAL).

    Do NOT add any history I/O to apply_usage or main -- apply_usage stays exactly as is (it runs on the
    Gtk main thread via idle_add).
  </action>
  <verify>
    <automated>python3 claude-monitor.py --selfcheck && rg -q "^import tempfile" claude-monitor.py && rg -q "def append_history\(" claude-monitor.py && rg -q "def prune_history\(" claude-monitor.py && rg -q "append_history\(history_record\(" claude-monitor.py && rg -q "os.replace" claude-monitor.py && rg -q "prune_history\(time.time\(\)\)" claude-monitor.py && python3 -c "import ast; ast.parse(open('claude-monitor.py').read()); print('parse-ok')"</automated>
    <human-check>Run the tray (`python3 claude-monitor.py`) for a few poll cycles and `tail -f ~/.claude/usage-history.jsonl`: confirm one well-formed JSON line appears per successful poll and a degraded poll (rename/kill the CLI) adds no line while usage rows still update. Hand-seed an old record (a line with `t` set to now-40d), restart the tray, and confirm it is pruned on startup and the file is rewritten whole (no partial/truncated file). Then `chmod 000 ~/.claude/usage-history.jsonl` (or point HISTORY_PATH at an unwritable dir) and confirm the tray keeps running and usage rows keep updating -- history just stops persisting.</human-check>
  </verify>
  <acceptance_criteria>
    - `python3 claude-monitor.py --selfcheck` still exits 0 (Task 1 logic intact) and the file parses (`ast.parse` -> parse-ok).
    - claude-monitor.py contains `import tempfile`, `def append_history(`, `def prune_history(`, `os.replace`, and the `append_history(history_record(` call.
    - The append call sits in poll_loop (daemon thread) between `fetch_usage()` and `GLib.idle_add(mon.apply_usage, ...)`; apply_usage and main contain no history I/O (writes stay off the Gtk main loop).
    - The append is guarded by `usage is not None`; a failed/degraded poll writes nothing.
    - prune runs once at startup (before the poll while-loop) and opportunistically at most ~once/PRUNE_INTERVAL via the in-process `last_prune` timer; prune_history writes survivors to a temp file in the same dir then `os.replace` (atomic, never truncate-in-place).
    - Every file op swallows OSError: with the file `chmod 000` / an unwritable dir / a missing file, the tray keeps running and usage rows keep updating (observable via human-check).
  </acceptance_criteria>
  <done>Successful polls append one schema-correct line to `~/.claude/usage-history.jsonl` off the Gtk main loop; the file is pruned atomically at startup and periodically; every history op swallows OSError so no failure mode crashes or blocks the tray; v1.0 `--selfcheck` stays green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| helper -> history file (~/.claude/usage-history.jsonl) | the helper writes and reads a JSONL file under the user's own home |
| history file content -> parse_history | previously-written (possibly corrupt or half-written) file content is parsed back as JSON on prune/read |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-02-01 | Tampering | HISTORY_PATH under ~/.claude | low | accept | The file lives under the user's own home at the same trust level as the tray helper itself; if that path is attacker-controlled the whole session is already compromised. No elevation beyond the invoking user; the writer only serializes its own numeric usage fields via json.dumps (no shell, no eval). |
| T-02-02 | Denial of Service | unbounded file growth (disk exhaustion) | low | mitigate | Retention prune (once at startup + opportunistically every PRUNE_INTERVAL) drops records older than HISTORY_DAYS so the file stays bounded (~one small line per poll, well under a few MB over 30 days). The rewrite is atomic -- survivors go to a temp file in the same dir, then os.replace over the original -- so there is no truncate-in-place data-loss window. |
| T-02-03 | Tampering | corrupt/partial line on read (parse_history) | low | mitigate | parse_history wraps json.loads per line in try/except and skips any line that fails, so a half-written trailing line from a killed process (or any garbage line) is ignored rather than crashing the reader or the prune rewrite. |
| T-02-04 | Denial of Service | history file I/O on unwritable path / full disk | low | mitigate | Every file op (append, read-for-prune, replace) swallows OSError, so a missing/unwritable path, permission error, or full disk degrades to "history just doesn't persist" -- never a crash or a blocked poll. All I/O runs on the poll_loop daemon thread, off the Gtk main loop, so a slow/failing filesystem cannot freeze the tray. |

No package-manager installs this phase (stdlib json/os/time/tempfile + already-present PyGObject only), so no supply-chain (T-02-SC) row applies. No network calls, no shell, no privileged operations, and no untrusted input beyond the self-written history file reach this code.
</threat_model>

<verification>
- `python3 claude-monitor.py --selfcheck` passes: the new pure-logic asserts (history_record construction with t=int(now) and raw per-minute burn, history_keep dropping now-40d / keeping now-1d, parse_history skipping a corrupt line) plus every intact v1.0 assert.
- Structural: file parses (`ast.parse` -> parse-ok); contains HISTORY_PATH / HISTORY_DAYS (guarded-int over CLAUDE_TRAY_HISTORY_DAYS) / PRUNE_INTERVAL, history_record / history_keep / parse_history / append_history / prune_history, `import tempfile`, `os.replace`; the append call sits in poll_loop before `GLib.idle_add`; apply_usage and main carry no history I/O.
- Manual (human-check): running the tray a few cycles grows the JSONL by one well-formed line per successful poll and none on degraded polls; a hand-seeded old record is pruned at startup with an atomic (whole-file) rewrite; `chmod 000` / unwritable dir leaves the tray running and usage rows updating.
</verification>

<success_criteria>
All three phase requirements are satisfied in `claude-monitor.py`:
- HIST-01: each successful poll appends one JSON line `{t, pct, tokens_used, token_limit, burn}` to `~/.claude/usage-history.jsonl` (t = int(time.time()) of the poll, burn raw per-minute); failed/degraded polls add no line.
- HIST-02: records older than HISTORY_DAYS (default 30, env CLAUDE_TRAY_HISTORY_DAYS) are pruned at startup and at most ~once/PRUNE_INTERVAL, atomically (temp file + os.replace), so the file stays bounded.
- HIST-03: every history file op swallows OSError and the reader skips corrupt/partial lines; all I/O runs on the poll_loop daemon thread off the Gtk main loop, so no missing/unwritable/corrupt-file condition crashes or blocks the tray; usage rows + session status keep working in every failure mode.
</success_criteria>

<output>
Create `.planning/phases/02-usage-history-persistence/02-01-SUMMARY.md` when done.
</output>
