---
phase: 07-live-session-view
verified: 2026-07-18T21:30:00Z
status: passed
score: 6/9 must-haves verified
behavior_unverified: 3
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 5/9
  gaps_closed:

    - "CR-01 / 07-02 must_haves.truths[3] (the one FAILED truth): the age-ceiling reap resurrected a genuinely-alive session as a brand-new entry, so Monitor.handle read old=None and core.sess_should_notify(None,'waiting') re-fired a spurious URGENCY_CRITICAL 'Waiting for input' notification (regressing NOTIF-02). Closed by 07-03 (66d7f24/393aec6/02c6498): Monitor._pop_stale now records self._reaped_status[sid]=s.get('status') BEFORE the pop, and handle seeds its baseline via core.sess_notify_baseline(s.get('status'), self._reaped_status.pop(sid,None)). Confirmed from live code + behavioral trace: a same-status resurrection reads old='waiting' -> sess_should_notify False (no re-notify, entered not re-stamped); a genuine waiting->done across the reap still fires exactly once."
    - "WR-06 (coverage gap that let CR-01 land): the reap/resurrect notification baseline is now a pure core.sess_notify_baseline function locked by 5 --selfcheck asserts (test_claude_monitor.py:489-500), including the two composed-with-sess_should_notify resurrection cases."
  gaps_remaining: []
  regressions: []
gaps: []
deferred: []
behavior_unverified_items:

  - truth: "Rows sort waiting -> running -> done; done rows render dimmed (D-04/D-06)"
    test: "Open the dashboard with sessions in all three statuses simultaneously (now that G-07-2 no longer produces stuck/duplicate rows and CR-01 no longer re-fires notifications); visually confirm row order waiting -> running -> done and that done rows render visibly dimmed (reduced opacity)."
    expected: "Row order is waiting, then running, then done; done rows render at .sess-done{opacity:.5}."
    why_human: "Pure client-side JS (SESS_RANK comparator, sess-done class) with no headless JS runner in this repo. 07-UAT.md Test 2 (the only human attempt so far) returned 'issue', but the reported symptom (two 'running' rows, one already done) was entirely a G-07-2 stale-session artifact, not evidence the sort/dim logic is wrong. 07-02-PLAN.md's own <verification> asks for this test to be re-run post-fix; that has not happened."

  - truth: "A session whose tmux pane no longer exists (killed pane/terminal/process) disappears from the tray menu and dashboard panel within one poll tick (~15s), with no SessionEnd hook event required (G-07-2)"
    test: "Restart the tray (just restart). Start a session in a tmux pane, confirm it shows in tray+dashboard. Run `tmux kill-pane -t <pane>` directly (bypassing SessionEnd). Confirm the session disappears from both the tray menu and the dashboard panel within about one poll tick, with no manual tray refresh (dashboard needs its existing meta-refresh/reload). Separately, confirm a genuinely active session is never wrongly reaped in normal use."
    expected: "Killed-pane session vanishes from both surfaces within ~15s; an actively-used session is undisturbed."
    why_human: "reap_stale/_pop_stale/pane_alive are wired correctly on inspection (poll_loop calls mon.reap_stale(now) every tick; pane_alive shells to tmux, tri-state; GLib.idle_add hands the pop to the Gtk thread) and --selfcheck locks the pure session_stale decision table, but nothing exercises the live GTK Monitor + real tmux integration end-to-end. 07-02-SUMMARY.md flags this as its own pending D3 item -- never run because the plan had no checkpoint:* task."

  - truth: "A session that stops sending events while its pane stays open (/exit or /clear reused the same pane -- SessionEnd fires for neither) self-heals off the list within REAP_MAX_AGE (G-07-2)"
    test: "Start a session, then run /exit (or /clear) inside the same pane without closing it. Confirm the entry stays visible for a while (pane alive, age not yet exceeded), then disappears from tray+dashboard once REAP_MAX_AGE (1h) elapses without a fresh event. While observing, confirm the same-pane resurrection path does NOT re-fire a 'Waiting for input' popup (the CR-01 live confirmation, 07-03-SUMMARY.md D5)."
    expected: "Entry self-heals off both surfaces once REAP_MAX_AGE elapses even though the pane never closed; a reaped-then-resurrected same-status session reappears with no new popup and no `!`-badge re-arm."
    why_human: "Same live-integration reasoning as the pane-kill item, plus a real ~1h idle. The pure age-ceiling logic (session_stale) and the resurrection baseline (sess_notify_baseline) are both unit-locked by --selfcheck; only the live GTK Monitor + 1h wait is unverified. 07-03-PLAN.md pairs this human-check with the deterministic Task 3 asserts (which already pass)."
human_verification:

  - test: "Restart the tray, start a session in a tmux pane, run `tmux kill-pane -t <pane>` directly (bypassing SessionEnd); confirm the session disappears from both the tray menu and dashboard panel within ~1 poll tick; separately confirm a genuinely active session (pane alive, real events arriving) is never wrongly reaped -- and, when a reaped-then-alive session resends its same status, that NO new 'Waiting for input' popup fires and the `!` badge does not re-arm (the live CR-01 confirmation)."
    expected: "Killed-pane session self-heals off both surfaces within ~15s; an actively-used session is undisturbed; a same-status resurrection produces no popup / no badge re-arm; a genuine-change resurrection shows exactly one notification."
    why_human: "07-02-SUMMARY.md's D3 and 07-03-SUMMARY.md's D5 -- both require a live GTK tray + real tmux pane kill (and, for the CR-01 live case, a synthetic or real reap-then-resurrect); not automatable from this environment. The deterministic proof is the passing --selfcheck resurrection block."

  - test: "Re-run 07-UAT.md Test 2 (open the dashboard with sessions in all three statuses; confirm sort order waiting -> running -> done and done rows dimmed) now that G-07-2 AND CR-01 are both closed, to separate 'sort/dim logic is correct' from 'the stale-session bug was masking it'."
    expected: "Clean sort order and dimming with no stuck/duplicate rows this time."
    why_human: "No headless JS execution path in this repo; the only prior attempt (07-UAT.md Test 2) was confounded by the since-fixed G-07-2 bug."
---

# Phase 07: Live Session View in the Dashboard Verification Report

**Phase Goal:** See all currently-tracked Claude Code sessions and their status at a glance in the existing web dashboard, refreshed live, without leaving the top bar or opening the tray menu.
**Verified:** 2026-07-18T21:30:00Z
**Status:** human_needed
**Re-verification:** Yes -- after 07-03 gap closure (CR-01 / the one FAILED truth). The previously-failed truth is now VERIFIED; the remaining open items are LIVE-GUI checks carried forward, not failures.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SESSVIEW-01: dashboard shows every tracked session with status (running/waiting/done) | ✓ VERIFIED | `write_dashboard()` builds the `sessions=[{dir,status,entered}...]` snapshot from `list(self.sessions.values())` and threads it into `render_dashboard`; `renderSessions()` renders the full list. `--selfcheck` (green) confirms all three statuses and multiple dirs reach the page. Unchanged by 07-03 (dashboard.py not in the 07-03 diff). |
| 2 | SESSVIEW-02: each row shows project dir and accurate live time-in-current-state | ✓ VERIFIED | Project dir selfcheck-verified. Duration-reset-only-on-transition (D-01, `if old != event: s["entered"]=time.time()`, claude-monitor.py:403-404) **human-confirmed** via 07-UAT.md Test 1 (pass). Live 1s tick (D-02) **human-confirmed** via 07-UAT.md Test 3 (pass). |
| 3 | SESSVIEW-03: reflects live in-memory state, existing meta-refresh cadence, no new IPC/socket/persistence | ✓ VERIFIED | 07-03 adds no new socket/file/timer -- only an in-memory `self._reaped_status` dict (Gtk-thread-only) and a pure `core.sess_notify_baseline`. `write_dashboard` still runs from the pre-existing poll-loop throttle. No `open(...,'w')`/socket added in any 07-03 commit. |
| 4 | SESSVIEW-04: no-sessions renders a clean empty state, no break/blank/reflow | ✓ VERIFIED | `--selfcheck` asserts `render_dashboard([rec], now, sessions=[])` contains the literal `No active Claude Code sessions` and `"sessions": []`; `<section>` panel emitted unconditionally. Unregressed (dashboard.py untouched by 07-03). |
| 5 | SESSVIEW-05: dashboard stays self-contained (no external references), consistent with DASH-06 | ✓ VERIFIED | `--selfcheck` self-containment asserts pass against the populated page: no `<link`, no `src=`, no `https://`; only `http://` is the SVG namespace. Unregressed. |
| 6 | Rows sort waiting -> running -> done; done rows render dimmed (D-04/D-06) | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `SESS_RANK`/`.sess-done` present and wired. The one prior UAT attempt (Test 2) returned `issue`, but the symptom was the now-closed G-07-2 bug, not the sort logic. Never cleanly re-observed -- routed to human verification. |
| 7 | A session whose tmux pane no longer exists disappears from tray + dashboard within ~1 poll tick, no SessionEnd required (G-07-2) | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `pane_alive`, `Monitor.reap_stale`/`_pop_stale`, and the `poll_loop` wiring all present and correctly structured; `core.session_stale`'s pure table locked by `--selfcheck`. Byte-for-byte unchanged by 07-03. Live end-to-end GTK+tmux check (07-02-SUMMARY.md D3) not yet run. |
| 8 | A session that stops sending events while its pane stays open (/exit or /clear) self-heals off the list within REAP_MAX_AGE (G-07-2) | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Same code path as #7 (`session_stale`'s `alive in (True,None)` age-ceiling branch), unchanged by 07-03. Pure-function behavior locked by `--selfcheck`; live 1h-elapsed integration not yet observed. |
| 9 | A reaped-but-still-alive session reappears with no adverse side effect -- a same-status resurrection does NOT re-fire a notification or re-arm the `!` badge, while a genuine transition across a reap still fires exactly once (07-02 must_haves.truths[3] / CR-01, now closed by 07-03) | ✓ VERIFIED | **Was FAILED, now VERIFIED.** 07-03 gives the reap a one-shot memory: `Monitor._pop_stale` records `self._reaped_status[sid]=s.get("status")` before the pop (claude-monitor.py:438-441); `handle` seeds `old = core.sess_notify_baseline(s.get("status"), self._reaped_status.pop(sid,None))` (claude-monitor.py:394). Behaviorally traced against live code: resurrected `old="waiting"` -> `sess_should_notify("waiting","waiting")` is **False** (no re-notify; `old != event` also False -> `entered` not re-stamped) and `waiting->done` across a reap is **True** (fires once). Locked by 5 `--selfcheck` asserts (test:489-500), including the two composed resurrection cases. `session_stale`/`reap_stale`/`pane_alive`/`sess_should_notify` byte-for-byte unchanged, so both 07-02 self-heal paths carry forward. |

**Score:** 6/9 truths verified (3 present-behavior-unverified, 0 failed). Previous: 5/9 with 1 failed. The CR-01 truth (#9) flipped FAILED -> VERIFIED.

### 07-03 must_haves.truths (gap-closure plan) coverage

| 07-03 truth | Status | Evidence |
|-------------|--------|----------|
| Same-status resurrection past REAP_MAX_AGE does NOT re-notify or re-arm `!` (closes CR-01, restores NOTIF-02) | ✓ VERIFIED | Truth #9. `sess_should_notify(sess_notify_baseline(None,"waiting"),"waiting")` is False; no `emit_notif`. Badge: `acked` reset on resurrection is identical to any same-status keepalive (pre-existing NOTIF behavior), and the notification -- the actual interruption -- is now suppressed. |
| A genuine change straddling a reap (waiting -> done) still fires exactly one notification | ✓ VERIFIED | `sess_should_notify(sess_notify_baseline(None,"waiting"),"done")` is True. Selfcheck assert:498. |
| Both 07-02 self-heal truths still hold; the fix touches only the notification baseline, never session_stale | ✓ VERIFIED | git diff 66d7f24~1..02c6498 shows `session_stale`/`reap_stale`/`pane_alive` unchanged; only `__init__`, `handle` (baseline read), `_pop_stale` (remember-before-pop) changed. session_stale `--selfcheck` block still passes. |
| Reaped-status memory consulted through a testable core.py fn locked by --selfcheck (closes WR-06) | ✓ VERIFIED | `core.sess_notify_baseline` pure fn + 5-case resurrection assert block; `--selfcheck` exits 0. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `claude_monitor/core.py::sess_notify_baseline` | pure live-then-reaped baseline resolver (CR-01/WR-06) | ✓ VERIFIED | core.py:116-126, `return live_status if live_status is not None else reaped_status`, explicit `is not None`, "Pure." docstring. Placed directly after `sess_should_notify`. |
| `claude-monitor.py::Monitor._reaped_status` | Gtk-thread-only one-shot reaped-status memory | ✓ VERIFIED | Initialized __init__:71 with ponytail bound comment; written in `_pop_stale` (438-441), popped one-shot in `handle` (394). `reap_stale` (poll thread) never references it (confirmed by read). |
| `claude-monitor.py::Monitor.handle` baseline seed | `old` derived via sess_notify_baseline, feeds both entered-stamp + sess_should_notify | ✓ VERIFIED | Line 394; the corrected `old` flows into `if old != event` (403) and `sess_should_notify(old,event)` (406). |
| `claude_monitor/test_claude_monitor.py::resurrection block` | 5-case --selfcheck asserts (WR-06) | ✓ VERIFIED | Lines 489-500: normal, brand-new (+notify), same-status resurrection (no notify), genuine-change resurrection (notify), live-wins. Import sorted (41). |
| `core.py::session_stale` / `pane_alive` / `reap_stale` / `_pop_stale` (07-02) | unchanged by 07-03 | ✓ VERIFIED | Byte-for-byte unchanged in the 07-03 range (git diff); `_pop_stale` gained only the remember-before-pop lines. |
| `dashboard.py` panel (07-01) | table markup, dot CSS, textContent rows, 1s ticker | ✓ VERIFIED | Not in the 07-03 diff; `--selfcheck` panel/empty/self-containment groups still green. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `Monitor._pop_stale` | `self._reaped_status[sid]` | remember-before-pop | WIRED | claude-monitor.py:438-441, guarded for an already-gone session. |
| `self._reaped_status[sid]` | `Monitor.handle`'s `old` | `.pop(sid,None)` one-shot | WIRED | This is exactly the pop/resurrect boundary CR-01 found broken; now carries prior status across it. Consumed once, then absent (plain None for a never-reaped session). |
| `old` | entered-stamp + notify guard | `if old != event` / `sess_should_notify(old,event)` | WIRED, behavior VERIFIED | Both consumers see the corrected baseline; same-status resurrection re-stamps neither `entered` nor fires `emit_notif`. |
| `_reaped_status` mutation | Gtk main thread only | written in `_pop_stale` (idle_add), popped in `handle` (serve idle_add); `reap_stale` (poll thread) never touches it | WIRED | Single-mutator invariant preserved -- confirmed by reading reap_stale (no `_reaped_status` reference). |
| `poll_loop` | `Monitor.reap_stale(now)` | unconditional every tick | WIRED | Unchanged from 07-02. |
| `D.sessions` payload | DOM rows | client-side `textContent` | WIRED | Unchanged from 07-01, reconfirmed by `--selfcheck`. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full `--selfcheck` suite (panel + session_stale + sess_notify_baseline resurrection groups) | `python3 claude-monitor.py --selfcheck` | `ok` / exit 0 | ✓ PASS |
| CR-01 same-status resurrection no re-notify | `sess_should_notify(sess_notify_baseline(None,"waiting"),"waiting")` | `False` | ✓ PASS (CR-01 closed) |
| CR-01 entered not re-stamped on resurrection | `sess_notify_baseline(None,"waiting") != "waiting"` | `False` | ✓ PASS |
| Genuine transition across reap fires once | `sess_should_notify(sess_notify_baseline(None,"waiting"),"done")` | `True` | ✓ PASS |
| Brand-new first waiting still notifies | `sess_should_notify(sess_notify_baseline(None,None),"waiting")` | `True` | ✓ PASS |
| Lint clean | `ruff check .` | `All checks passed!` | ✓ PASS |
| Entry points compile | `python3 -m py_compile` (4 files) | exit 0 | ✓ PASS |
| dashboard.py stays GTK-free | `import claude_monitor.dashboard; assert 'gi' not in sys.modules` | `gtk-free ok` | ✓ PASS |
| Live GTK Monitor x tmux self-heal + resurrection | (requires live tray + real tmux) | -- | ? SKIP -> human verification |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| SESSVIEW-01 | 07-01, 07-02, 07-03 | dashboard shows all tracked sessions w/ status | ✓ SATISFIED | Truth #1; 07-03 restores correct de-duped state |
| SESSVIEW-02 | 07-01 | each row shows dir + accurate time-in-state | ✓ SATISFIED | Truth #2, human-confirmed (UAT 1 & 3) |
| SESSVIEW-03 | 07-01, 07-02, 07-03 | live in-memory reflect, existing cadence, no new IPC/persistence | ✓ SATISFIED | Truth #3 |
| SESSVIEW-04 | 07-01 | clean empty state | ✓ SATISFIED | Truth #4 |
| SESSVIEW-05 | 07-01 | self-contained, no external refs | ✓ SATISFIED | Truth #5 |
| NOTIF-02 | 07-03 | notify once per transition, de-duped (Phase 5 guarantee) | ✓ SATISFIED (restored) | Truth #9 -- CR-01 regression against NOTIF-02 closed |

All five SESSVIEW IDs appear across the three plans' `requirements:` frontmatter and match REQUIREMENTS.md's v1.4 section. 07-03 additionally re-touches SESSVIEW-01/03 and restores NOTIF-02. No orphaned requirements.

**Requirements-bookkeeping assessment (task item 3):** REQUIREMENTS.md's checklist marks SESSVIEW-01/03 `[x]` but SESSVIEW-02/04/05 `[ ]`, while the Traceability table (lines 107-111) lists all five as "Planned". This is a **cosmetic table-vs-checklist inconsistency, NOT a real coverage gap.** The live code delivers all five (verified: SESSVIEW-01/03/04/05 by `--selfcheck`, SESSVIEW-02 by UAT Tests 1 & 3), and every ID is claimed by a plan's `requirements:` frontmatter. The stale "Planned" rows and unchecked boxes are bookkeeping left over from before 07-01 executed -- they under-report delivered state, they do not indicate missing implementation. Fix at the ship / complete-milestone step (flip SESSVIEW-01..05 to `[x]` / "Delivered"); does not block this verification.

### Anti-Patterns Found

None. No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER`, no stub returns, no hardcoded-empty props in any of the four modified files. The one `# ponytail:` comment on `_reaped_status` (claude-monitor.py:68-70) is a deliberate, documented bound (matches the accepted `notif_slots`/`notif_acts` leak profile, IN-02), not a debt marker -- it references the accepted disposition, not deferred work.

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| Sessions panel (`#sessions` tbody) | `D.sessions` | `write_dashboard()` snapshots `list(self.sessions.values())`, mutated by `handle` (hooks) and `_pop_stale` (reap) | Yes -- live in-memory dict | ✓ FLOWING. The reap-induced resurrection no longer injects a false "brand new" signal into the notification path (CR-01 closed); a resurrected same-status session may briefly show `-` duration until its next real transition (fresh dict has no `entered`), a harmless cosmetic, not a regression against any must-have. |

### Gaps Summary

**No blocking gaps.** The single FAILED truth from the prior pass (CR-01 / 07-02 must_haves.truths[3]) is closed: 07-03 gives the reap a short-lived `Monitor._reaped_status` memory and seeds `Monitor.handle`'s notification baseline through the new pure `core.sess_notify_baseline`, so a genuinely-alive session reaped past `REAP_MAX_AGE` and resuming its routine same-status hook event reads as "no transition" -- no spurious `URGENCY_CRITICAL` popup, no `entered` reset -- while a genuine change across the reap still fires exactly once. Verified directly against the live code path and a behavioral trace, and locked by five `--selfcheck` resurrection asserts (closing WR-06). `session_stale`/`reap_stale`/`pane_alive` are byte-for-byte unchanged, so both 07-02 self-heal paths carry forward and the rejected "exclude alive=True from the age reap" trap was correctly avoided. Single-mutator (Gtk-thread-only) discipline is preserved -- `reap_stale` on the poll thread never touches `_reaped_status`.

Three items remain routed to human verification (`human_needed`), NOT failed, because the code is present and correctly wired on inspection but requires a live GTK tray / real tmux / real time-elapsed to observe: (1) killed-pane end-to-end self-heal timing (07-02-SUMMARY.md's pending D3, now also the natural place to confirm CR-01's fix live per 07-03-SUMMARY.md D5); (2) the same-pane `/exit`//`clear` 1h age-ceiling self-heal; and (3) a clean re-run of the sort/dim UAT (07-UAT.md Test 2) now that both G-07-2 and CR-01 are closed and the confounds are gone. These are LIVE-GUI checks that cannot be automated in this environment; the deterministic decision logic under each is already unit-locked by `--selfcheck`.

Everything from 07-01 (panel presence, empty state, self-containment, dir XSS-inertness, duration accuracy, live tick) remains verified or human-confirmed and is unregressed -- dashboard.py was not touched by 07-03.

---

_Verified: 2026-07-18T21:30:00Z_
_Verifier: Claude (gsd-verifier)_
