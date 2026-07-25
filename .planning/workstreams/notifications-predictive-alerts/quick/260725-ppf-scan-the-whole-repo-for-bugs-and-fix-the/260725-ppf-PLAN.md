---
phase: 260725-ppf
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - claude_monitor/core.py
  - claude_monitor/dashboard.py
  - claude_monitor/test_claude_monitor.py
  - claude-monitor.py
  - claude-send.py
  - claude-status.py
  - install.sh
  - rust/src/main.rs
  - rust/src/format.rs
  - rust/src/snapshot.rs
  - rust/src/sanitize.rs
  - rust/src/client.rs
  - rust/src/error.rs
  - rust/src/lib.rs
  - tmux/claude_usage.sh
autonomous: true
requirements: [QT-260725-ppf]

must_haves:
  truths:
    - "The in-progress uncommitted work (tmux-powerline usage segment: fmt_countdown_short, statusline_text in claude_monitor/core.py, their asserts in claude_monitor/test_claude_monitor.py, and the tmux segment install wiring in install.sh) is still present and unbroken -- not reverted, not clobbered."
    - "Every genuine bug found in the Python daemon/core/entry scripts and install.sh (logic errors, crashes, race conditions, resource leaks, off-by-ones, incorrect error handling) is fixed with a minimal, root-cause diff -- not a rewrite or speculative refactor."
    - "Every genuine bug found in the Rust client and the tmux status segment script is fixed the same way."
    - "Every fix carries a regression check that fails without the fix: a new/extended assert in claude_monitor.test_claude_monitor.demo() for a Python fix, a new #[test] for a Rust fix."
    - "just selfcheck exits 0 and just lint (ruff) is clean after all fixes."
    - "just rust-test and just rust-lint (cargo clippy -D warnings) are clean after all fixes."
    - "No file is modified unless a real bug was found and fixed in it -- no style-only or speculative changes."
  artifacts:
    - claude_monitor/core.py
    - claude-monitor.py
    - install.sh
    - rust/src/main.rs
  key_links:
    - "poll_loop / serve / _handle_conn broad-except guards (established in 260713-fry) -> daemon thread liveness; a fix must not remove or weaken these guards"
    - "Monitor.sessions_lock -> every self.sessions read/write site (established in Phase 08-01); a fix must not bypass this lock"
    - "client.rs socket read -> snapshot.rs normalize_* (per-field degrade-to-None) -> format.rs row builders -> main.rs draw loop; a fix must preserve the degrade-not-panic contract at each hop"
---

<objective>
Scan the whole repository for real, fixable bugs -- logic errors, crashes, race conditions,
resource leaks, off-by-ones, incorrect error handling -- and fix each one found with a
minimal, root-cause diff. This is not a style pass and not a refactor: only genuine defects
get touched.

Purpose: no bug report or file was named going in; this task IS the investigation, and it
must land real fixes, not a list of findings. The working tree already carries in-progress,
uncommitted work (a tmux-powerline status-bar segment touching `claude_monitor/core.py`,
`claude_monitor/test_claude_monitor.py`, and `install.sh`) that must survive this pass intact.

Output: targeted fixes across the Python daemon, the Rust client, and/or the tmux segment
script -- only where a real bug was found -- each backed by a new or extended automated
check, with both verification gates (`just selfcheck`, `just lint`, `just rust-test`,
`just rust-lint`) green.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/workstreams/notifications-predictive-alerts/STATE.md
@.claude/CLAUDE.md

Repo shape (justfile recipes are the ONLY sanctioned way to run/verify -- see project
CLAUDE.md, do not hand-roll python3/cargo invocations outside them except where a recipe
doesn't cover it):
- `just selfcheck` -> `python3 ~/.claude/hooks/claude-monitor.py --selfcheck` (that path is a
  symlink to this repo's `claude-monitor.py`, so repo edits are picked up with no extra step)
- `just lint` -> `ruff check .`
- `just rust-test` -> `cd rust && cargo test --quiet`
- `just rust-lint` -> `cd rust && cargo clippy --all-targets -- -D warnings`
- `just check` -> selfcheck + rust-test together

House rules (hard, from `.claude/CLAUDE.md`): ASCII-only in code and comments (`->` not an
arrow glyph, `+/-` not `+/-` unicode, etc.); codedoc comment style (Python: triple-quoted
docstrings for prose, `#` for short annotations; Rust: `/* */` blocks for prose); a
deliberate shortcut gets a `ponytail:` comment naming the tradeoff and upgrade path;
minimal targeted diffs only, no unrequested abstractions.

Known in-progress local diff (DO NOT REVERT, must still be present and passing after this
plan): `git diff -- claude_monitor/core.py claude_monitor/test_claude_monitor.py install.sh`
currently shows a new `fmt_countdown_short` / `statusline_text` pair in `core.py`, their
asserts in `test_claude_monitor.py`, and tmux-powerline segment install wiring in
`install.sh`. There is also an untracked `claude-status.py`, `tmux/claude_usage.sh`, and a
quick-task directory for that same in-progress feature -- leave all of it alone unless a fix
in this plan happens to land on the same lines, in which case merge cleanly and keep both.

Prior related hardening (do not re-solve, learn the pattern instead):
- `poll_loop` / `serve` / `_handle_conn` in `claude-monitor.py` already wrap their bodies in
  broad `except Exception` + `traceback.print_exc()` so one bad iteration/connection cannot
  kill the daemon thread (260713-fry). A fix must extend this pattern, not remove it.
- `Monitor.sessions_lock` in `claude-monitor.py` guards every `self.sessions` read/write
  across the Gtk thread and query threads (Phase 08-01). A fix must not bypass it.
- Rust `snapshot.rs` normalizes every field independently: junk in one field degrades only
  that field to `None`, never the whole snapshot (see `normalize_usage`). A fix must not
  turn a per-field degrade into a whole-render panic.
</context>

<tasks>

<task type="auto">
  <name>Task 1: Audit and fix bugs in the Python daemon and install script</name>
  <files>claude_monitor/core.py, claude_monitor/dashboard.py, claude_monitor/test_claude_monitor.py, claude-monitor.py, claude-send.py, claude-status.py, install.sh</files>
  <precondition>`git status` shows claude_monitor/core.py, claude_monitor/test_claude_monitor.py, and install.sh as modified (uncommitted) -- if that in-progress diff is gone (already committed or reverted by someone else), skip the preservation check and proceed with the audit as normal.</precondition>
  <action>
    Start with `git status` and `git diff --stat` to confirm the in-progress uncommitted
    work described in context. Note it and move on -- do not touch those hunks except where
    a real bug's fix genuinely lands on the same lines.

    Read every Python source file in the repo end to end: `claude_monitor/core.py`,
    `claude_monitor/dashboard.py`, `claude-monitor.py`, `claude-send.py`, `claude-status.py`,
    and `install.sh`. Trace real control flow, not isolated functions: follow `poll_loop`,
    `serve`/`_handle_conn`, `watch_focus`, and the Gtk callback chain in `claude-monitor.py`;
    follow each shell script's actual execution path in `install.sh`.

    Hunt specifically for:
    - Logic errors: wrong comparison operators, inverted/incorrect boolean combinations,
      off-by-one slicing or indexing, a wrong variable used where a similarly-named one was
      intended.
    - Crashes: unguarded dict/list access, division, or type coercion on data that can be
      absent or malformed (usage-history.jsonl records, socket payloads, subprocess output,
      environment variables).
    - Race conditions: any read or write of `self.sessions` or other daemon-thread-shared
      state that bypasses `sessions_lock`, or a `GLib.idle_add` marshaling gap that lets a
      background thread touch Gtk state directly.
    - Resource leaks: sockets, files, or subprocess handles left open on an exception path
      that a normal-exit path already closes.
    - Incorrect error handling: an `except` that silently swallows an error where the
      project's own convention (see the three sites named in context) is to guard AND
      surface via `traceback.print_exc()`; a `subprocess.run` call with no `timeout` that
      could hang a thread indefinitely; an `except` clause catching a narrower or wrong
      exception type so the real error escapes uncaught.
    - Shell bugs in `install.sh`: unquoted variable expansions that break on paths with
      spaces, a command whose failure should abort the script but doesn't, wrong `[ ]` test
      flags, a glob or `ln`/`rm` that is broader than the single file it's meant to target.

    For every genuine bug found, fix it with the smallest possible diff at its root cause --
    if the real source is a shared helper called from multiple sites, fix the helper once
    rather than patching every caller. Skip anything that is a style preference, a
    speculative "could be cleaner," or working-as-intended (e.g. the broad `except Exception`
    guards named in context are deliberate, not bugs).

    For every Python fix, add or extend exactly one assert in
    `claude_monitor.test_claude_monitor.demo()` that fails without the fix and passes with
    it, in the same assert-based style already used throughout that function (see the
    existing `fmt_countdown_wk` / `history_numeric` blocks for the pattern). If nothing in
    Python actually needs fixing, say so explicitly in the summary and change nothing.
  </action>
  <verify>
    <automated>just selfcheck && just lint</automated>
  </verify>
  <done>
    `just selfcheck` prints `ok` and `just lint` is clean. Every Python bug fix has a
    corresponding new/extended assert in `demo()` that fails on the pre-fix code (verified by
    temporarily reverting the fix locally, or by reasoning through it, before finalizing).
    The uncommitted tmux-powerline segment work (`fmt_countdown_short`, `statusline_text`,
    their asserts, the install.sh wiring) is still present in `git diff`.
  </done>
</task>

<task type="auto">
  <name>Task 2: Audit and fix bugs in the Rust client and the tmux status segment script</name>
  <files>rust/src/main.rs, rust/src/format.rs, rust/src/snapshot.rs, rust/src/sanitize.rs, rust/src/client.rs, rust/src/error.rs, rust/src/lib.rs, tmux/claude_usage.sh</files>
  <action>
    Read every Rust source file under `rust/src` (`main.rs`, `format.rs`, `snapshot.rs`,
    `sanitize.rs`, `client.rs`, `error.rs`, `lib.rs`) and the tmux segment script
    `tmux/claude_usage.sh`. Trace the real data flow: `client.rs`'s socket read ->
    `snapshot.rs`'s `normalize_usage`/`normalize_sessions` -> `format.rs`'s row builders ->
    `main.rs`'s draw loop, plus the shell script's own execution path end to end.

    Hunt for the same bug categories as Task 1, adapted to Rust: logic errors (wrong
    comparisons, off-by-one indexing/slicing on rows, caps, or spans); panics (`.unwrap()`,
    `.expect()`, or raw indexing that can panic on malformed/absent/short snapshot data;
    integer overflow or underflow subtracting durations or percentages); resource/lifecycle
    bugs (a socket read with no timeout that can hang the client against a stuck daemon; a
    connection not closed on an early-return error path); incorrect error handling (a
    `Result` silently discarded with `let _ =` or `.ok()` where the project's own
    per-field-degrade convention -- see `normalize_usage` -- says a bad field should become
    `None`, not be dropped in a way that hides a real decode bug). In the shell script:
    unquoted variable expansions, a command failure that should abort the segment but
    doesn't, unsafe arithmetic on values that could be empty or non-numeric.

    Fix genuine bugs with the smallest diff at the root cause. Skip anything working as
    intended (the per-field degrade-to-`None` pattern in `snapshot.rs` is deliberate, not a
    bug) or that is a style preference.

    For every Rust fix, add or extend exactly one `#[test]` in the same module, mirroring the
    existing test style (see the existing `normalize_usage` / `tui_usage_rows` tests), that
    fails without the fix. Do not restructure the existing fixture-driven test suite. If
    nothing in Rust or the shell script actually needs fixing, say so explicitly in the
    summary and change nothing.
  </action>
  <verify>
    <automated>just rust-test && just rust-lint</automated>
  </verify>
  <done>
    `cargo test` and `cargo clippy --all-targets -- -D warnings` are both clean. Every Rust
    bug fix has a corresponding new/extended `#[test]` that fails on the pre-fix code. No
    change was made to code that had no real bug.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|--------------|
| Local IPC socket (tray <-> Rust client, `_handle_conn` <-> `client.rs`) | Any bug fix touching `client.rs`'s socket read or `_handle_conn` changes how malformed/partial input degrades |
| `subprocess.run` call sites (`claude-monitor.py`: wmctrl, tmux, xdotool) | Existing calls use the argument-list form, never `shell=True`; a fix must not introduce shell string interpolation |
| `install.sh` writes under `$HOME` | A fix must not widen a targeted `ln -sf`/single-file write into a broader glob/delete |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|------------------|
| T-ppf-01 | Tampering | `subprocess.run` call sites in `claude-monitor.py` | high | accept | Existing calls already pass argument lists (no shell). This task only fixes genuine bugs found there and must preserve that form -- no shell string interpolation is introduced by any fix. |
| T-ppf-02 | Denial of Service | Socket read loops (`core.py` response reader, `client.rs` connect/recv) | medium | mitigate | If a resource-leak or unbounded-read bug is found on either side, fix it with the same bounded-read/timeout discipline the code already applies elsewhere (matches `key_links`). |
| T-ppf-03 | Tampering / Info Disclosure | `install.sh` file writes under `$HOME` | low | accept | `install.sh` is only touched if a genuine correctness bug is found (e.g. an unquoted path); scope stays a minimal fix, not a rewrite of the install flow. |
| T-ppf-SC | Tampering | npm/pip/cargo installs | low | accept | This task adds no new dependency. If a fix appears to need one, stop and flag it in the summary instead of installing anything. |
</threat_model>

<verification>
```bash
just check          # just selfcheck (must print "ok") + just rust-test
just lint            # ruff check . -- clean
just rust-lint        # cargo clippy --all-targets -- -D warnings -- clean
git diff --stat -- claude_monitor/core.py claude_monitor/test_claude_monitor.py install.sh
  # confirms the pre-existing tmux-powerline in-progress work is still present, not reverted
```
</verification>

<success_criteria>
- Every real bug found in the Python daemon, Rust client, or tmux segment script during the
  sweep is fixed at its root cause with a minimal diff.
- No file is touched unless a genuine bug was found and fixed in it.
- Each fix carries a new or extended automated assert/test that fails without the fix.
- `just selfcheck`, `just lint`, `just rust-test`, and `just rust-lint` are all clean.
- The pre-existing uncommitted tmux-powerline usage-segment work is intact and unbroken.
</success_criteria>

<output>
Create `.planning/workstreams/notifications-predictive-alerts/quick/260725-ppf-scan-the-whole-repo-for-bugs-and-fix-the/260725-ppf-SUMMARY.md` when done
</output>
