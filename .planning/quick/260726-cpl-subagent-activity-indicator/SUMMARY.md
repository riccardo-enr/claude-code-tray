---
quick_id: 260726-cpl
slug: subagent-activity-indicator
date: 2026-07-26
status: complete
---

# Subagent-activity indicator -- summary

A per-session live-subagent count, rendered as an overlay on the existing status
(`hkust  [waiting]  (2 agents)`) rather than as a replacement for it.

## What changed

| File | Change |
|------|--------|
| `claude-send.py` | forwards `tool_name` so the daemon can tell a subagent dispatch from any other tool (both arrive as `running`) |
| `settings.hooks.json` | registers `SubagentStop -> claude-send.py subagent_stop` |
| `~/.claude/settings.json` | same hook **appended** to the existing `SubagentStop` array (1 -> 2 entries; the gsd hook there is untouched). Backup: `settings.json.bak-260726` |
| `claude_monitor/core.py` | `AGENT_TOOLS`, `subagent_delta`, `apply_subagent_delta`, `session_row_label`; `build_session_snapshot` gains `agents` |
| `claude-monitor.py` | intercepts `subagent_stop` before the status write, folds the delta, clears on a genuine `done`, renders via `session_row_label` |
| `claude_monitor/test_claude_monitor.py` | asserts for the new pure functions; hook-registration guard now requires `SubagentStop` |
| `README.md` | hook table row + "Live subagent count" section |

## Why an overlay and not a new status

`waiting` has to keep meaning "this session wants you" -- it is what drives the `!`
badge, the desktop notification and the attention count. Folding subagents into
`status` would have broken all three. The count is orthogonal, so it got its own field.

This also fixes the flapping the earlier `PreToolUse -> running` fix left behind: a
`Notification` mid-subagent still flips the status to `waiting`, but the count no longer
gets lost, so the row stays truthful either way.

## Verification

Gates: `just selfcheck` -> ok (exit 0), `just lint` -> all checks passed,
`just rust-test` -> 112 passed / 0 failed. `just restart` done; daemon pid 119169
(started 09:16:34) confirmed serving the new `agents` field.

Live end-to-end against the running daemon, driving the real socket path with
correctly-formed events on this session's real id (so no phantom row -- session count
held at 4 throughout):

```
Task dispatch #1                  -> agents=1
Task dispatch #2                  -> agents=2
ordinary Bash                     -> agents=2   (not counted)
SubagentStop x2                   -> agents=0
unmatched SubagentStop            -> agents=0   (clamped, not -1)

Notification mid-subagent         -> claude-code-tray  [waiting]  (2 agents)   <- the reported bug
subagent's next tool call         -> claude-code-tray  [running]  (2 agents)
turn ends                         -> claude-code-tray  [done]                  <- count cleared
```

## Not done (deliberate)

- **Rust TUI** does not show the count. Its parser ignores unknown keys, so `agents`
  reaches it harmlessly and `just rust-test` stays green; surfacing it there is a
  separate change.
- **Global tray icon** unchanged. It already carries usage% and the attention badge, and
  the complaint was per-session.
- Subagents already running when the daemon restarts are not counted (the count starts
  from zero). Clamping keeps that from ever going negative.
