---
schema_version: 1
open_count: 0
waived_count: 0
fixed_count: 1
total_count: 1
last_updated: 2026-07-29T08:35:24.537Z
---

# Broken Windows Ledger

> Cross-phase defect register. `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 260729-e37 | deviation | justfile |  | Task 3 deploy steps (just install/restart/status) deferred to main checkout post-merge -- worktree-isolated agent cannot safely repoint the live ~/.claude/hooks/claude-monitor.py symlink | fixed |  | 2026-07-29T08:32:13.827Z | 2026-07-29T08:35:24.537Z |

````json
[
  {
    "id": 1,
    "kind": "deviation",
    "phase": "260729-e37",
    "file": "justfile",
    "line": null,
    "description": "Task 3 deploy steps (just install/restart/status) deferred to main checkout post-merge -- worktree-isolated agent cannot safely repoint the live ~/.claude/hooks/claude-monitor.py symlink",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-07-29T08:32:13.827Z",
    "resolved_at": "2026-07-29T08:35:24.537Z"
  }
]
````
