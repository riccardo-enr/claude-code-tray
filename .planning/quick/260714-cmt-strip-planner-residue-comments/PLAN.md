---
task_id: 260714-cmt
slug: strip-planner-residue-comments
created: 2026-07-14
status: in-progress
---

# Quick Task: Strip planner-residue comments from claude-monitor.py

## Problem

`claude-monitor.py` carries 268 comment lines across 2339 lines. Most were written
during GSD planning and address a reviewer, not the next reader: requirement-ID
tracing (`D-03`, `ALERT-04`, `NOTIF-02`, `ROADMAP SC4`), self-congratulatory framing
(`THE boundary`, `THE regression guard`, `the ONLY thing that would catch someone`),
and comments restating the line below them. All of it already lives in `.planning/`.

## Scope

**Delete:**
- Requirement / decision IDs used as provenance (`D-0x`, `NOTIF-0x`, `SESS-0x`,
  `ALERT-0x`, `CFG-0x`, `QUOTA-0x`, `WR-01`, `SC4`, phase numbers).
- Prose defending why a line is correct, or narrating what the next line does.
- `demo()` narration that restates the assertion immediately below it.

**Keep** (constraints the code cannot show):
- gnome-shell ignores `expire_timeout`; urgency is the only lifetime knob.
- `ActionInvoked` is a broadcast signal -- ids must be filtered.
- The `Gio.DBusProxy` must be constructed on the Gtk main thread.
- The JS/Python `project()` duplication is deliberate.
- Notification summary is not Pango-parsed, the body is.
- Env-var one-liners on module constants.
- `ponytail:` markers naming a shortcut and its upgrade path.

**No behavior changes.** Comments and docstring prose only.

## Verification

- `python3 -m py_compile claude-monitor.py`
- `python3 claude-monitor.py --selfcheck` -> PASS
- `git diff --stat` shows deletions only, zero net code-line changes.
