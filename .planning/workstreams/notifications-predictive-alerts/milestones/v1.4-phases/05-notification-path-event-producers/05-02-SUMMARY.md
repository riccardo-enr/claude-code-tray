---
phase: 05-notification-path-event-producers
plan: 02
subsystem: notifications
tags: [notifications, sessions, de-dupe, pure-function, security]
status: complete

requires:
  - "05-01: Monitor.emit_notif, URGENCY_NORMAL, URGENCY_CRITICAL, notif_allowed, on_notif_signal"
provides:
  - "sess_should_notify(old_status, new_status) -- pure de-dupe predicate (NOTIF-02, D-03)"
  - "Monitor.handle emitting session waiting/done notifications -- emit_notif's first caller"
  - "the ('sess', sid) slot key and ('focus', pane, tmux) action tuple in live use"
affects:
  - "claude-monitor.py"

tech-stack:
  added: []
  patterns:
    - "De-dupe as a pure old-vs-new comparison -- assertable in --selfcheck without a bus"
    - "Session-derived strings go in the notification TITLE; bodies are fixed literals"

key-files:
  created: []
  modified:
    - "claude-monitor.py"

decisions:
  - "sess_should_notify is a single boolean expression -- notifiable state AND a change. It carries all of NOTIF-02 without any per-session timestamp or seen-set"
  - "Reworded the predicate's docstring to avoid the literal token _onscreen: ast.dump includes docstrings, so prose defeated the D-04 acceptance check"
  - "Did not duplicate emit_notif's MAX_NOTIFICATIONS_PER_SOURCE paragraph at the call site -- wrote a shorter one naming the same ceiling and upgrade path"

metrics:
  duration: "~15 min"
  completed: 2026-07-13
  tasks: 2
  commits: 2
  files_changed: 1
---

# Phase 05 Plan 02: Session Notification Producer Summary

`emit_notif` has its first caller. A session entering `waiting` or `done` now raises a
desktop notification titled with its project directory, exactly once per transition, into
a slot that a later transition overwrites in place.

## What Was Built

**Task 1 (`ecc3e9a`)** -- `sess_should_notify(old_status, new_status)`, module-level and
pure:

```python
return new_status in ("waiting", "done") and old_status != new_status
```

That one expression is the whole of NOTIF-02. A session sitting in `waiting` re-sends
`waiting` on every hook event and only a *change* passes; a session first seen already
waiting has `old_status is None`, which differs, so it notifies. No timestamp, no seen-set,
no per-session bookkeeping. Seven cases pinned in `demo()`.

**Task 2 (`2e8cecb`)** -- the wiring in `Monitor.handle`. `old = s.get("status")` is read
immediately after the `setdefault` and **before** `s.update(...)`; the emit is gated on
`sess_should_notify(old, event)` and passes `("sess", sid)` as the slot, `d` as the title,
one of two fixed literal bodies, `("focus", pane, tmux)` as the action, and
`URGENCY_CRITICAL` / `URGENCY_NORMAL` for `waiting` / `done`.

## Landmines Respected

| Landmine | How it landed |
|----------|---------------|
| Read `old` AFTER the update and the de-dupe is dead code that never fires | AST-verified: the `get` statement's line number is strictly less than the `update` statement's |
| The `dir` is attacker-influenceable and the body IS Pango-parsed (T-05-04) | `d` goes to the title (summary, not markup-parsed). Both bodies are fixed literals interpolating nothing, so there is nothing to escape |
| D-04 -- do not "helpfully" gate on the already-looking signal | `_onscreen` appears exactly once inside `handle`, in the pre-existing `acked=` kwarg. The behavior test drives a `waiting` event with `_onscreen: True` and asserts a notification still fires |
| D-02 via `urgency`, never `expire_timeout` | `URGENCY_CRITICAL` / `URGENCY_NORMAL` at the call site; the timeout argument is untouched inside `emit_notif` |
| D-03 -- one slot per session | Every emit for a session carries the same `("sess", sid)` key |
| `end` must not notify | It short-circuits at the top of `handle`, before any of this; asserted |

## Verification

- `python3 claude-monitor.py --selfcheck` -> `ok`, exit 0. Run before both commits.
- Every acceptance criterion in the plan checked and passing (the four AST checks, the four
  grep counts, ASCII-only).
- **Mutation test, executed:** dropping the `old_status != new_status` clause makes
  `--selfcheck` exit 1 on `assert sess_should_notify("waiting", "waiting") is False`. The
  assertions are load-bearing, not decorative.
- **Behavior test, executed headlessly** (stub `Monitor`, recording `emit_notif`, no Gtk, no
  bus): the sequence `running, waiting, waiting, waiting, done, done, waiting` produces
  exactly **3** emits, all on slot `("sess", "s1")`, with kinds `[waiting, done, waiting]`,
  urgencies `[2, 1, 2]`, action `("focus", "%3", tmux)`, bodies `Waiting for input` /
  `Session finished`, and a title of `<b>repo` -- proving the markup-shaped directory lands
  in the summary and never the body. Three repeated `waiting` events collapse to one emit.

## Deviations from Plan

**1. [Rule 3 - Blocking] Reworded the `sess_should_notify` docstring to drop the literal `_onscreen`**

- **Found during:** Task 1 acceptance checks
- **Issue:** The docstring explained D-04 by naming the `_onscreen` signal. The plan's D-04
  criterion is `'onscreen' in ast.dump(f)` -> fail, and `ast.dump` includes docstrings, so
  the *explanation* of the rule tripped the check enforcing it.
- **Fix:** "the already-looking-at-this-pane signal that serve() computes". Same meaning, no
  token. Identical in kind to Plan 01's deviation 2 -- structural greps over this file are
  defeated by prose that mentions the symbol.
- **Commit:** ecc3e9a

**2. [Rule 1 - Simplification] Did not duplicate the `MAX_NOTIFICATIONS_PER_SOURCE` paragraph**

- **Found during:** Task 2
- **Issue:** The plan asks for a `ponytail:` comment on the 3-notifications-per-source
  ceiling at the call site. That exact five-line paragraph already exists in `emit_notif`'s
  docstring (Plan 01), where every producer shares it.
- **Fix:** wrote a shorter comment at the call site naming the same ceiling and the same
  upgrade path (coalesce into one summary notification), rather than copying the paragraph.
  The ceiling is documented at the producer; it is just not documented twice.
- **Commit:** 2e8cecb

## Known Stubs

None. `notif_allowed` remains open (`return True`) -- that is Plan 01's deliverable and
Phase 6's job, not a stub introduced here.

## Outstanding: Human UAT

The plan's live-tray checks (a) waiting popup sticks past 30s, (b) done replaces it in place
and expires in ~4s, (c) a repeated waiting event produces no second popup, (d) clicking the
popup focuses the pane -- require a running GNOME/X11 session with the tray up. (b) and (c)
are proven headlessly above (same slot key, urgency 1 vs 2). (a) and (d) depend on
gnome-shell's actual handling of the urgency hint and on `ActionInvoked` reaching us -- the
one thing 05-RESEARCH.md could not verify end to end. Verify on the live tray.

## Threat Flags

None. This plan introduces no new network endpoint, auth path, file access, or schema. The
one trust boundary it crosses (hook `cwd` -> notification) is T-05-04, mitigated as planned.

## Self-Check: PASSED

- `claude-monitor.py` exists, parses, `--selfcheck` -> `ok` exit 0.
- Commits `ecc3e9a` and `2e8cecb` both found in `git log`.
- No new non-ASCII: the file's only two non-ASCII lines are the pre-existing em-dash comment
  and `SPARK_GLYPHS`.
