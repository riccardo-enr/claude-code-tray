# Phase 02 Context — Usage History Persistence

**Source:** Milestone v1.1 scoping (decisions captured with the user during /gsd-new-milestone).
Design preferences below are LOCKED unless the planner finds a concrete blocker.

## Domain

Extend the single-file GTK tray helper `claude-monitor.py` so that every successful
usage poll is durably recorded to an append-only history file, bounded by a retention
window, without ever destabilizing the long-lived tray. This is the write/foundation
half of v1.1; Phase 03 (trends) reads what this phase writes.

Requirements: **HIST-01** (append sample per successful poll), **HIST-02** (prune past
retention window), **HIST-03** (defensive I/O, never crash/block the helper).

## Locked decisions

- **Store:** append-only JSONL at `~/.claude/usage-history.jsonl` (one JSON object per line).
  Path constant near the other config constants; expand `~` via `os.path.expanduser`.
- **Sample schema (one line per SUCCESSFUL poll):** the record is derived from the existing
  normalized usage dict (keys `tokens_used`, `token_limit`, `used_percentage`,
  `resets_at_epoch`, `burn_rate_per_min`). Persist a compact record:
  `{"t": <int epoch seconds>, "pct": used_percentage, "tokens_used": ..., "token_limit": ..., "burn": burn_rate_per_min}`.
  - `t` is the wall-clock time of the poll (`int(time.time())`), NOT `resets_at_epoch`.
  - Store `burn` as the raw per-MINUTE value the source carries (Phase 03 converts to per-hour). Note this in a comment so Phase 03 doesn't double-convert.
  - Failed / degraded polls (fetch_usage returned None) write NOTHING.
- **Where the write happens:** in `poll_loop` (the existing daemon thread), right after a
  successful `fetch_usage()` and independent of the `GLib.idle_add(apply_usage, ...)` marshaling.
  This keeps all file I/O OFF the Gtk main loop by construction. Do NOT write from
  `apply_usage` (that runs on the main thread via idle_add).
- **Retention:** default **30 days**, env-configurable via `CLAUDE_TRAY_HISTORY_DAYS`,
  parsed with the same guarded `int(...)`/`except ValueError -> default` pattern already used
  for `POLL_INTERVAL` (lines 45-48). Records with `t < now - days*86400` are dropped.
- **Pruning cadence:** prune once at startup, then opportunistically — not on every write.
  Simplest sufficient trigger: track the last prune time in-process and prune at most about
  once every few hours (e.g. >= 6h since last prune) from within `poll_loop`. Rewrite
  atomically: write survivors to a temp file in the same dir, then `os.replace` over the
  original (never truncate-in-place). The planner picks the exact interval constant.
- **Defensive I/O (HIST-03):** every file operation (append, read-for-prune, replace) is
  wrapped so any `OSError` is swallowed and the tray keeps running — a missing/unwritable
  path or full disk degrades to "history just doesn't persist", never a crash or a blocked
  poll. The reader tolerates a corrupt/partial trailing line by skipping lines that fail
  `json.loads` (per-line try/except), so a half-written last line from a killed process is ignored.

## Constraints

- One file, `claude-monitor.py`, extended in place. Stdlib only (`json`, `os`, `time`,
  `tempfile`) + existing PyGObject. No new dependencies. X11-only, unchanged.
- Must not regress v1.0: `python3 claude-monitor.py --selfcheck` stays green; session
  status, click-to-focus, usage rows, and the degradation path all keep working.
- No new polling and no new threads — reuse the existing `poll_loop` daemon thread.

## Success criteria (what must be TRUE)

1. After several poll cycles, `~/.claude/usage-history.jsonl` has one well-formed JSON line
   per successful poll with the schema above; degraded polls add no line. (HIST-01)
2. Records older than the retention window are pruned on startup and periodically; the file
   stays bounded rather than growing without limit; the prune is atomic (no data-loss window). (HIST-02)
3. Missing/unwritable/corrupt history file never crashes or freezes the tray; writes are off
   the Gtk main loop; a corrupt line is skipped on read. Usage rows + session status keep
   working in every failure mode. (HIST-03)

## Verification approach

- **Automated self-check (`--selfcheck` / `demo()`):** add asserts for the NEW pure logic —
  sample-record construction from a usage dict, the retention filter predicate (a record at
  `now-40d` is dropped, one at `now-1d` kept), and tolerant parsing of a history blob mixing
  valid lines with a corrupt/partial line (bad line skipped, good lines returned). Keep the
  existing v1.0 asserts intact.
- **Observable:** run the tray a few cycles -> file gains lines; hand-seed an old line ->
  it's pruned; `chmod 000` the file or point at an unwritable dir -> tray keeps running and
  usage rows still update.

## Out of scope (this phase)

- Any display/reading of history for trends — that's Phase 03 (sparkline, daily/weekly burn,
  peak hours). This phase only WRITES and PRUNES.
- Data export (CSV/JSON) — deferred (HIST-F1).
