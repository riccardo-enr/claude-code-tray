---
phase: 07-live-session-view
plan: 01
subsystem: dashboard
status: complete
tags: [dashboard, sessions, xss-mitigation, self-contained-html]
requires:
  - claude_monitor/dashboard.py::render_dashboard
  - claude-monitor.py::Monitor.handle
  - claude-monitor.py::Monitor.write_dashboard
provides:
  - render_dashboard(records, now, sessions=()) sessions param + "sessions" payload key
  - live Sessions panel (dir / status dot+word / client-ticked duration)
  - per-session `entered` epoch stamped on status change
affects:
  - the self-contained dashboard.html the tray writes to XDG cache
tech-stack:
  added: []
  patterns:
    - client-side DOM textContent render of untrusted dir (XSS mitigation, D-08)
    - snapshot-of-primitives to keep dashboard.py GTK-free
    - inline _DASH_* constants for a self-contained page
key-files:
  created: []
  modified:
    - claude_monitor/dashboard.py
    - claude-monitor.py
    - claude_monitor/test_claude_monitor.py
decisions:
  - D-01: stamp `entered` only when old != event (reuse pre-update old) so keepalives do not reset the counter
  - D-02: sub-hour duration formatted as "Nm SSs" and ticked every 1s so it visibly moves
  - D-08: session dir reaches the page only via _embed_json payload, rendered client-side via textContent
metrics:
  duration: ~4m
  completed: 2026-07-18
  tasks: 3
  files: 3
---

# Phase 07 Plan 01: Live Session View in the Dashboard Summary

Embedded the tray's in-memory session list into the existing self-contained dashboard as a live-refreshing Sessions panel (project dir, colored status dot + word, client-ticked time-in-state), sorted waiting -> running -> done with done rows dimmed and a clean empty state, with the untrusted project dir rendered inert via client-side `textContent`.

## What Was Built

- **Task 1 (dashboard.py, commit c722b45):** `render_dashboard(records, now, sessions=())` new param + `"sessions": list(sessions)` payload key; inline `<section>` Sessions panel (`#sess-tbl` table + `.sd` status-dot CSS reusing palette vars) in `_DASH_BODY`/`_DASH_STYLE`; `renderSessions()` in `_DASH_JS` that sorts by `SESS_RANK`, renders rows client-side via `textContent`, shows the empty-state row, and ticks every 1s via `sessDur()`.
- **Task 2 (claude-monitor.py, commit ff86660):** `Monitor.handle()` stamps `s["entered"] = time.time()` only when `old != event` (reusing the same `old` `sess_should_notify` reads); `Monitor.write_dashboard()` snapshots `[{dir,status,entered}]` from `list(self.sessions.values())` and threads it as `sessions=` inside the existing `try/except Exception` guard.
- **Task 3 (test_claude_monitor.py, commit 0094a13):** three new `--selfcheck` assert groups — empty state (`"sessions": []` + no-active string), payload + markup inertness (hostile `<b>x</b>` dir escaped, benign dirs and epoch present, single `</script>`), and self-containment with the panel populated.

## Landmines Handled

- **D-01:** `entered` stamped only on a real transition, reusing the pre-update `old` — an unconditional stamp would reset the duration counter on every keepalive tick.
- **D-08 (T-07-01 XSS):** session `dir` ships only inside the `_embed_json` payload (escapes `< > &`) and rows are built client-side with DOM `textContent` — no server-side HTML interpolation of dir. Verified: a `<b>x</b>` dir never appears as raw markup and `</script>` count stays 1.

## Verification

All four gates pass (run at completion):

```
### 1. python3 claude-monitor.py --selfcheck
ok
exit=0

### 2. python3 -c "import claude_monitor.dashboard; import sys; assert 'gi' not in sys.modules; print('gtk-free ok')"
gtk-free ok

### 3. python3 -m py_compile claude-monitor.py claude_monitor/dashboard.py claude_monitor/test_claude_monitor.py
compile ok

### 4. ruff check .
All checks passed!
```

## Commits

| Task | Commit  | Message |
| ---- | ------- | ------- |
| 1    | c722b45 | feat(07-01): add live sessions panel to the dashboard |
| 2    | ff86660 | feat(07-01): stamp session entered time and snapshot into dashboard |
| 3    | 0094a13 | test(07-01): lock session-panel empty state, inertness, self-containment |

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Operational Note

The tray daemon (`claude-monitor.py`) must be **restarted** (kill the running process and relaunch) to load the new dashboard-rendering code. A tray started before this change will keep emitting the old panel-less `dashboard.html` until restarted.

## Self-Check: PASSED

- FOUND: claude_monitor/dashboard.py (modified, render_dashboard sessions param present)
- FOUND: claude-monitor.py (modified, entered stamp + snapshot present)
- FOUND: claude_monitor/test_claude_monitor.py (modified, session panel asserts present)
- FOUND commit: c722b45
- FOUND commit: ff86660
- FOUND commit: 0094a13
