<!-- GSD:project-start source:PROJECT.md -->

## Project

**claude-code-tray**

A GNOME top-bar tray indicator for Claude Code. It already shows per-session
status (running / waiting / done) fed by Claude Code hooks over a unix socket,
and focuses the originating tmux pane + Ghostty window on click. This milestone
adds **token-usage and quota-reset monitoring** to the same tray: current usage
against the plan limit, time until the rolling 5-hour window resets, and burn
rate.

**Core Value:** At a glance from the top bar, know **how much Claude Code quota is left and when
it resets** — without launching a separate terminal monitor.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->

## Technology Stack

Technology stack not yet documented. Will populate after codebase mapping or first phase.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

## Running & Tooling (use `just`)

This repo has a `justfile`. **Always use the `just` recipes to run, restart, or test
the tray** -- do not hand-roll `python3 ...` / `pkill` / `setsid` commands:

- `just restart` -- kill and relaunch the tray daemon. Run after **any** code change:
  Python does not hot-reload, and the deployed `~/.claude/hooks/claude-monitor.py` is a
  symlink to this repo, so edits are on disk but the running process holds the old code.
- `just start` / `just stop` / `just status`
- `just selfcheck` -- run the assert suite (`claude-monitor.py --selfcheck`), the
  verification gate every change MUST keep green (exit 0).
- `just lint` -- `ruff check .`
- `just dashboard` -- open the generated dashboard in the browser.

Run recipes from inside the desktop session (an interactive shell or overseer.nvim) so
the GUI daemon inherits `DISPLAY` / `DBUS_SESSION_BUS_ADDRESS`.

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
