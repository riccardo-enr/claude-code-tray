---
phase: 260719-pzd-symlink-claude-send
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - install.sh
autonomous: true
requirements: []

must_haves:
  truths:
    - "~/.claude/hooks/claude-send.py is a symlink into this repo (matching ~/.claude/hooks/claude-monitor.py's existing deployment), not a stale plain-file copy."
    - "install.sh creates BOTH hook deployments as symlinks (ln -sf), not install -m 0755 copies, so a fresh clone/re-run also gets live-updating hooks instead of drifting."
    - "The deployed claude-send.py payload includes the term field end-to-end: readlink resolves to the repo file, and that file's socket payload carries os.environ.get(\"TERM_PROGRAM\", \"\") under the \"term\" key that claude-monitor.py:399 already consumes."
  artifacts:
    - "install.sh (ln -sf for claude-monitor.py AND claude-send.py)"
    - "~/.claude/hooks/claude-send.py (symlink -> repo claude-send.py, live on this machine)"
  key_links:
    - "install.sh ln -sf claude-send.py -> ~/.claude/hooks/claude-send.py -> unix socket -> claude-monitor.py:399 msg.get(\"term\") -> focus() Zed WM_CLASS raise (claude-monitor.py:104)"
---

<objective>
Replace the stale plain-file copy at `~/.claude/hooks/claude-send.py` with a symlink into
this repo, and fix `install.sh` so it creates BOTH hook symlinks (not `install -m 0755`
copies) going forward -- matching the deployment `claude-monitor.py` already uses (per the
justfile's own comment: "Deployed entry: a symlink -> this repo's claude-monitor.py").

Root cause: `claude-monitor.py` is a symlink (created out-of-band, not via `install.sh`),
so edits deploy automatically. `install.sh` still copies both files with `install -m 0755`,
which is what left `~/.claude/hooks/claude-send.py` stale (last touched 2026-07-16) while
the repo's copy gained a `term` field today. `claude-monitor.py` already reads
`msg.get("term")` (line 399) and branches on `term == "zed"` (line 104) -- the consumer
side is live; only the stale sender was missing the field.

Purpose: one root-cause fix (symlink both hook scripts, everywhere they're deployed from)
instead of a one-off `cp`, so this class of drift can't recur.
Output: `~/.claude/hooks/claude-send.py` is a live symlink; `install.sh` symlinks both
hook files for any future install/re-run.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@justfile
@install.sh
@claude-send.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Make install.sh symlink both hook scripts instead of copying them</name>
  <files>install.sh</files>
  <read_first>
    - install.sh lines 1-16 (the two `install -m 0755` lines for claude-monitor.py and claude-send.py)
    - justfile line 7 (`# Deployed entry: a symlink -> this repo's claude-monitor.py`)
  </read_first>
  <action>
    In install.sh, replace both `install -m 0755 "$SRC/claude-monitor.py" "$HOOKS/claude-monitor.py"`
    and `install -m 0755 "$SRC/claude-send.py" "$HOOKS/claude-send.py"` with `ln -sf` equivalents
    (`ln -sf "$SRC/claude-monitor.py" "$HOOKS/claude-monitor.py"` and
    `ln -sf "$SRC/claude-send.py" "$HOOKS/claude-send.py"`), so a fresh install and any re-run
    produce the same live-symlink deployment the repo already relies on for claude-monitor.py
    (per the justfile comment), and claude-send.py can never drift out of date again. Leave the
    surrounding `mkdir -p`, autostart `.desktop` heredoc, and trailing echo instructions
    unchanged -- this is a two-line substitution, not a rewrite.
  </action>
  <verify>
    <automated>cd /home/riccardo/code/claude/claude-code-tray && bash -n install.sh && [ "$(grep -c 'ln -sf "\$SRC/claude-monitor.py"\|ln -sf "\$SRC/claude-send.py"' install.sh)" = "2" ] && ! grep -q 'install -m 0755' install.sh</automated>
  </verify>
  <done>install.sh contains two `ln -sf` lines (one per hook script) and zero remaining `install -m 0755` lines; `bash -n install.sh` passes (no syntax error).</done>
</task>

<task type="auto">
  <name>Task 2: Apply the fix on this machine -- symlink the live claude-send.py</name>
  <files>~/.claude/hooks/claude-send.py (outside repo, not git-tracked)</files>
  <read_first>
    - claude-send.py lines 24-32 (the msg dict, confirms the "term" field is present in the repo's current source)
  </read_first>
  <action>
    Run the same operation Task 1 wires into install.sh, applied immediately on this machine
    so the fix takes effect now (without waiting for a fresh install.sh run): remove the stale
    ~/.claude/hooks/claude-send.py plain file and replace it with
    `ln -sf /home/riccardo/code/claude/claude-code-tray/claude-send.py ~/.claude/hooks/claude-send.py`.
    No daemon restart is needed for this half of the fix -- claude-send.py is a short-lived
    per-hook process (per README: "Claude Code hook processes are short-lived"), not the
    long-lived claude-monitor.py daemon `just restart` targets; the very next hook fire reads
    the live, symlinked file. claude-monitor.py itself needs no change -- it already reads
    `msg.get("term")` (line 399), confirmed during planning.
  </action>
  <verify>
    <automated>[ "$(readlink -f ~/.claude/hooks/claude-send.py)" = "/home/riccardo/code/claude/claude-code-tray/claude-send.py" ] && grep -q 'TERM_PROGRAM' ~/.claude/hooks/claude-send.py</automated>
  </verify>
  <done>`readlink -f ~/.claude/hooks/claude-send.py` resolves to the repo's claude-send.py, and reading through the symlink shows the `term` field (TERM_PROGRAM) -- matching claude-monitor.py's existing symlink deployment.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| install.sh / manual `ln -sf` -> ~/.claude/hooks/ | Local filesystem only; no network input, no untrusted data. Both source and target paths are hardcoded to this repo and $HOME -- no user-supplied path is interpolated. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-pzd-01 | Tampering | ~/.claude/hooks/claude-send.py symlink target | low | accept | Symlinking (vs. copying) means the hook script is whatever's currently checked out in the repo working tree -- same trust model already accepted for claude-monitor.py's existing symlink; no new attack surface, no elevated privilege, `ln -sf` targets are hardcoded literals not derived from any external input. |
</threat_model>

<verification>
Run `bash -n install.sh` -- passes.
Confirm `grep -c 'ln -sf' install.sh` shows both hook lines and `install -m 0755` is gone.
Confirm `readlink -f ~/.claude/hooks/claude-send.py` equals this repo's `claude-send.py` path.
Confirm the live symlinked file contains the `term` field (`grep TERM_PROGRAM ~/.claude/hooks/claude-send.py`).
No claude-monitor.py restart required -- it already consumes `msg.get("term")`; only the sender was stale.
</verification>

<success_criteria>
- ~/.claude/hooks/claude-send.py is a symlink to this repo's claude-send.py, not a stale copy.
- install.sh symlinks both claude-monitor.py and claude-send.py (ln -sf), matching the deployment pattern the justfile already documents for claude-monitor.py.
- Future edits to claude-send.py deploy automatically, with no manual re-copy step, closing the class of bug that caused the missing `term` field.
- Zed-integrated-terminal hook payloads now reach claude-monitor.py's existing `msg.get("term")` handling end-to-end.
</success_criteria>

<output>
Create `.planning/quick/260719-pzd-symlink-claude-hooks-claude-send-py-to-t/260719-pzd-SUMMARY.md` when done.
</output>
