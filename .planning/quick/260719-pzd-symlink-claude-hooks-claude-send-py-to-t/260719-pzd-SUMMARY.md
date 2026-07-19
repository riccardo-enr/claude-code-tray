---
phase: 260719-pzd-symlink-claude-send
plan: 01
subsystem: claude-code-tray
status: complete
tags: [install, symlink, hooks, root-cause-fix]
requires: []
provides: [install.sh ln -sf deployment for both hook scripts]
affects: [claude-send.py, claude-monitor.py deployment]
key-files:
  created: []
  modified:
    - install.sh
decisions:
  - "Symlink (not copy) claude-send.py in install.sh, matching claude-monitor.py's existing (out-of-band) symlink deployment -- one root-cause fix instead of a one-off cp."
metrics:
  duration: ~5m
  completed: 2026-07-19
  tasks: 2
  files: 1
---

# Phase 260719-pzd Plan 01: Symlink claude-hooks claude-send.py Summary

Fixed the class of bug (not just the symptom): `install.sh` now `ln -sf`s both
`claude-monitor.py` and `claude-send.py` into `~/.claude/hooks/`, and the stale plain-file
`~/.claude/hooks/claude-send.py` on this machine was replaced with a live symlink into the repo.

## What was done

- **Task 1** - `install.sh`: replaced both `install -m 0755 ...` lines with `ln -sf "$SRC/claude-monitor.py" "$HOOKS/claude-monitor.py"` and `ln -sf "$SRC/claude-send.py" "$HOOKS/claude-send.py"`. Two-line substitution; `mkdir -p`, autostart `.desktop` heredoc, and trailing echo instructions unchanged.
- **Task 2** - removed the stale `~/.claude/hooks/claude-send.py` plain file (last touched 2026-07-16, missing the `term` field) and replaced it with `ln -sf /home/riccardo/code/claude/claude-code-tray/claude-send.py ~/.claude/hooks/claude-send.py`.

## Verification results

1. `bash -n install.sh` -> passes (no syntax error).
2. `grep -c 'ln -sf "\$SRC/claude-monitor.py"\|ln -sf "\$SRC/claude-send.py"' install.sh` -> `2`.
3. `grep -q 'install -m 0755' install.sh` -> no match (zero remaining copy lines).
4. `readlink -f ~/.claude/hooks/claude-send.py` -> `/home/riccardo/code/claude/claude-code-tray/claude-send.py`.
5. `grep TERM_PROGRAM ~/.claude/hooks/claude-send.py` -> matches (the `term` field is live through the symlink).

No `claude-monitor.py` restart was needed or performed -- it already reads `msg.get("term")`
(line 399, confirmed during planning); only the sender side was stale. `claude-send.py` is a
short-lived per-hook process, so the very next hook fire picks up the symlinked file.

## Task Commits

1. **Task 1: Make install.sh symlink both hook scripts instead of copying them** - `d9a13d3` (fix)
2. **Task 2: Apply the fix on this machine** - no commit (target is `~/.claude/hooks/claude-send.py`, outside the repo and not git-tracked, per plan's `files_modified` scope)

## Files Created/Modified
- `install.sh` - both hook deployments now `ln -sf` instead of `install -m 0755`
- `~/.claude/hooks/claude-send.py` (outside repo) - now a symlink to the repo's `claude-send.py`, replacing a stale plain-file copy

## Decisions Made
- Symlink both hook scripts (root-cause fix) rather than a one-off `cp` to refresh the stale file, so this class of drift closes for good, matching the deployment pattern the justfile already documents for `claude-monitor.py`.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Next Phase Readiness

Both hooks now deploy identically (symlink). Future edits to either `claude-monitor.py` or
`claude-send.py` in the repo take effect immediately (`claude-send.py` on next hook fire,
`claude-monitor.py` on next daemon restart) with no manual re-copy step required, for this
machine and any future `install.sh` run.

---
*Phase: 260719-pzd-symlink-claude-send*
*Completed: 2026-07-19*

## Self-Check: PASSED
- install.sh contains 2 `ln -sf` lines, zero `install -m 0755` lines.
- Commit d9a13d3 present in git log.
- `~/.claude/hooks/claude-send.py` is a symlink (target confirmed via `readlink -f` above).
