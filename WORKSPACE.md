# Workspace: rust-tui

Created: 2026-07-30
Strategy: worktree

## Member Repos

| Repo | Source | Branch | Strategy |
|------|--------|--------|----------|
| claude-code-tray | /home/riccardo/code/claude/claude-code-tray | feat/11-rust-client-foundation | worktree |

## Notes

Isolated worktree for v2.0 Rust TUI (Phases 11-14). Shares this repo's existing
.planning/ history via git (checked out at main's HEAD) -- phase execution here
continues the same STATE.md/ROADMAP.md tracking under
.planning/workstreams/notifications-predictive-alerts/, not a fresh independent
planning tree.

Gotcha (see quick task 260729-e37): the live daemon (~/.claude/hooks/claude-monitor.py)
is symlinked to the MAIN checkout path, not this worktree. Build/test/plan here freely,
but run `just install && just restart` from the main checkout for live verification
before merging.
