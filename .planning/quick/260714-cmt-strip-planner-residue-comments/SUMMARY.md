---
task_id: 260714-cmt
slug: strip-planner-residue-comments
completed: 2026-07-14
status: complete
---

# Summary: Strip planner-residue comments from claude-monitor.py

## What changed

Comments and docstrings only. `claude-monitor.py` 2226 -> 1821 lines.

| | before | after |
|---|--------|-------|
| comment lines | 361 | 167 |
| docstring lines | 358 | 133 |
| **total commentary** | **719** | **300** |

Removed: requirement/decision-ID provenance (`D-0x`, `NOTIF-0x`, `SESS-0x`,
`ALERT-0x`, `CFG-0x`, `QUOTA-0x`, `WR-01`, `SC4`, phase numbers), prose defending
why a line is correct, comments restating the line below them, and all narration
between assertions in `demo()` (now five section headers plus a dozen notes naming
a non-obvious input).

Kept, one line each: the gnome-shell 46 `expire_timeout`/urgency quirk, raw D-Bus
vs `Gio.Notification` `.desktop` lookup, `ActionInvoked` broadcast filtering, the
Gtk-main-thread `Gio.DBusProxy` construction, the deliberate JS/Python `project()`
duplication, summary-not-Pango-parsed, the `actions` second-element note, the
`claude-monitor` CLI name collision, the nondeterministic saved `--plan`,
corrupt-record tolerance, all nine `CLAUDE_TRAY_*` env one-liners, all eight
`ponytail:` markers.

## Verification

- `python3 -m py_compile claude-monitor.py` -- OK
- `python3 claude-monitor.py --selfcheck` -- `ok`, exit 0
- AST of HEAD vs working copy, docstring nodes stripped from both: **identical**.
  Zero executable-code changes, proven rather than eyeballed.

## Not done

`_DASH_JS` still carries its own planner-ish JS comments. They live inside a Python
string literal, so editing them changes the rendered dashboard HTML -- a code change,
not a comment change. Separate pass if wanted.

## Also

Discarded an uncommitted working-tree change (kept in `git stash`): a whole-file
`black` reflow, an `ATTENTION_ICON` + `set_status(ATTENTION)` addition, and a
`notif_allowed` body returning `False` for `waiting`/`done` -- which would have
silently disabled the notifications Phase 5 shipped. The attention-icon idea is
worth revisiting on its own.
