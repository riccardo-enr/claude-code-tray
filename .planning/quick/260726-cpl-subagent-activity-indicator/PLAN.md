---
quick_id: 260726-cpl
slug: subagent-activity-indicator
date: 2026-07-26
status: in-progress
---

# Subagent-activity indicator in the tray

Show, per session, how many subagents are live -- as an overlay on the existing
status, not as a replacement for it.

## Why

`.planning/debug/resolved/subagent-shows-as-waiting.md` fixed the reported symptom by
registering `PreToolUse -> running`, which supplies the missing mid-turn un-latch. That
is correct but it is still a *single* latch: `status` is one string, so the tray can say
`running` or `waiting`, never "waiting on you, and 2 subagents are still grinding".

Consequences still visible today:

- A `Notification` (permission prompt / AskUserQuestion) mid-subagent flips the row to
  `waiting`; the subagent's next tool call flips it back to `running`. The row flaps,
  and neither value is the whole truth.
- Reported again by the user on session `4cb25eb3` (worktree `06-sim-time-fairness-fix`)
  with two subagents live.

A subagent count is orthogonal to the status, so it belongs in its own field rather
than fighting for the one that already carries the alert semantics.

## Decisions (defaulted, not asked)

- **Overlay, not a new status.** `waiting` must keep meaning "this session wants you" --
  that is what drives the `!` badge, the notification and the attention count. Encoding
  subagents into `status` would break all three.
- **Per-session menu row, not the global tray icon.** The tray has one icon, already
  carrying usage% and the attention badge. The complaint is per-session ("the session in
  hkust"), so the marker goes on the session's own row.
- **ASCII marker** (`(2 agents)`), per the global no-Unicode rule.
- **Rust TUI left alone.** Its snapshot parser ignores unknown keys, so adding `agents`
  keeps `just rust-test` green without touching Rust. Surfacing it in the TUI is a
  separate, optional follow-up.

## Tasks

1. `claude-send.py` -- forward `tool_name` from the hook payload (one added key).
2. `settings.hooks.json` + installed `~/.claude/settings.json` -- register
   `SubagentStop -> claude-send.py subagent_stop`, appended so unrelated gsd hooks
   survive. No new PreToolUse entry: the existing unmatched one already fires for
   `Task`, and the daemon derives the increment from `tool_name`.
3. `claude_monitor/core.py` -- pure helpers:
   - `AGENT_TOOLS`, `subagent_delta(event, tool_name)` -> +1 / -1 / 0
   - `apply_subagent_delta(count, delta)` -> clamped at 0
   - `session_row_label(dir, status, agents)`
   - `build_session_snapshot` gains `"agents"`.
4. `claude-monitor.py` -- intercept `subagent_stop` BEFORE the status write (it is a
   counter event, never a status), apply the delta on ordinary events, clear the count
   on a genuine `done`, render via `session_row_label`.
5. `claude_monitor/test_claude_monitor.py` -- asserts for the new pure functions, and
   extend the hook-registration guard to require `SubagentStop`.
6. README hook table.

## Verification

- `just selfcheck` exit 0
- `just lint` clean
- `just rust-test` 21 passed
- `just restart` (daemon code changed), then confirm a live session shows a count while
  a subagent runs.

## Known ceiling (ponytail)

A subagent killed without firing `SubagentStop` (SIGKILL, daemon restarted mid-run)
leaks a count. Mitigated by clamping at 0 and by clearing on a genuine `done`;
`SessionEnd` drops the whole dict. Upgrade path if it bites: expire the count off
`entered` age.
