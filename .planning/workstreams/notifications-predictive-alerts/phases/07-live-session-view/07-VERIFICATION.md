---
phase: 07-live-session-view
verified: 2026-07-18T20:15:00Z
status: gaps_found
score: 5/9 must-haves verified
behavior_unverified: 3
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 4/7
  gaps_closed:
    - "G-07-2 (stale/stuck session never self-heals off tray+dashboard without SessionEnd) -- 07-02 added core.session_stale, pane_alive, Monitor.reap_stale/_pop_stale wired into poll_loop."
    - "SESSVIEW-02 duration-reset-on-transition (D-01) -- confirmed by 07-UAT.md Test 1 (pass)."
    - "SESSVIEW-02/D-02 live 1s tick -- confirmed by 07-UAT.md Test 3 (pass)."
  gaps_remaining:
    - "Sort waiting->running->done / done-rows-dimmed (D-04/D-06) -- 07-UAT.md Test 2 result was 'issue', root-caused entirely to G-07-2 (now closed), but the sort/dim behavior itself was never cleanly re-confirmed in isolation; 07-02-PLAN.md's own <verification> section explicitly calls for re-running UAT Test 2 post-fix, which has not happened."
  regressions:
    - "CR-01 (07-REVIEW.md, critical, newly found in this review pass, unfixed): the G-07-2 reap mechanism resurrects a genuinely-alive session as a brand-new entry, causing Monitor.handle() to read old=None and re-fire a full URGENCY_CRITICAL 'Waiting for input' notification (and re-arm the '!' badge) for a session that never actually changed state. This contradicts the 07-02 must-have's own 'no data loss / harmless' framing and regresses the already-delivered NOTIF-02 de-dupe guarantee (Phase 5)."
gaps:
  - truth: "A session that is genuinely still alive and receiving hook events is never wrongly disturbed by the reap mechanism -- a reaped-but-still-alive session simply reappears fresh on its next real event with no data loss (07-02-PLAN.md must_haves.truths[3])"
    status: failed
    reason: "CR-01 (07-REVIEW.md, critical): confirmed by direct code read. Monitor._pop_stale (claude-monitor.py:427-432) pops the session dict with no memory of its prior status. On the session's next real hook event, Monitor.handle (claude-monitor.py:385) does `s = self.sessions.setdefault(sid, {})` -> a brand-new empty dict -> `old = s.get('status')` reads None. `core.sess_should_notify(None, 'waiting')` evaluates True (new_status in ('waiting','done') and old_status != new_status), so `self.emit_notif(...)` fires again at URGENCY_CRITICAL with no dismiss timer, and the fresh dict's `acked` is reset (re-arming the tray '!' badge) -- for a session whose actual status never changed. `session_stale` (claude_monitor/core.py:119-137) deliberately lets alive=True sessions age out past REAP_MAX_AGE (1h) with no companion suppression, so any session idling in 'waiting' (user stepped away, in a meeting, etc.) for over an hour reproduces this. The 07-02 must-have's 'no data loss' framing does not account for this concrete, reproducible, user-visible side effect; the 07-02 threat register's T-07-05 disposition ('cosmetic... temporary disappearance') was written before this consequence was traced and is contradicted by it."
    artifacts:
      - path: "claude-monitor.py"
        issue: "Monitor._pop_stale (~line 427) discards status history on pop; Monitor.handle (~line 385) setdefaults a fresh dict on the session's next event, so a same-status resurrection is indistinguishable from a brand-new session to sess_should_notify."
      - path: "claude_monitor/core.py"
        issue: "session_stale (~line 119) intentionally reaps alive=True sessions past REAP_MAX_AGE with no companion mechanism to prevent the resulting spurious re-notification on resurrection."
    missing:
      - "A short-lived memory of a reaped session's last status (e.g. self._reaped_status[sid], as CR-01's suggested fix in 07-REVIEW.md sketches) consulted by Monitor.handle so a same-status resurrection is not read as a real transition and does not re-fire sess_should_notify."
      - "OR narrow the unconditional age ceiling so alive=True sessions are excluded from the age-based reap (only alive in (False, None) falls back to age), accepting a slower self-heal for the same-pane /exit//clear case in exchange for never disturbing a confirmed-live session."
      - "Either fix needs regression coverage per WR-06 (07-REVIEW.md): no test currently exercises the Monitor.handle x session_stale interaction, only the pure session_stale function in isolation."
deferred: []
behavior_unverified_items:
  - truth: "Rows sort waiting -> running -> done; done rows render dimmed (D-04/D-06)"
    test: "Open the dashboard with sessions in all three statuses simultaneously (now that G-07-2 no longer produces stuck/duplicate rows); visually confirm row order waiting -> running -> done and that done rows are visibly dimmed (reduced opacity)."
    expected: "Row order is waiting, then running, then done; done rows render at .sess-done{opacity:.5}."
    why_human: "Pure client-side JS (SESS_RANK comparator, sess-done class) with no headless JS test runner in this repo. 07-UAT.md Test 2 (the only human attempt so far) returned 'issue', but the reported symptom (two 'running' rows, one already done) was entirely a G-07-2 stale-session artifact, not evidence the sort/dim logic itself is wrong. 07-02-PLAN.md's own <verification> section explicitly asks for this test to be re-run post-fix; that has not happened yet."
  - truth: "A session whose tmux pane no longer exists (killed pane/terminal/process) disappears from the tray menu and dashboard panel within one poll tick (~15s), with no SessionEnd hook event required (G-07-2)"
    test: "Restart the tray (just restart). Start a session in a tmux pane, confirm it shows in tray+dashboard. Run `tmux kill-pane -t <pane>` directly (bypassing SessionEnd). Confirm the session disappears from both the tray menu and the dashboard panel within about one poll tick, with no manual tray refresh needed (dashboard needs its existing meta-refresh/reload)."
    expected: "Session vanishes from both surfaces within ~15s of the pane being killed."
    why_human: "reap_stale/_pop_stale/pane_alive are wired correctly on inspection (poll_loop calls mon.reap_stale(now) every tick; pane_alive shells to tmux and returns tri-state; GLib.idle_add hands the pop back to the Gtk thread) and --selfcheck locks the pure session_stale decision table, but nothing exercises the live GTK Monitor + real tmux integration end-to-end. 07-02-SUMMARY.md explicitly flags this as 'Human Verification Pending' (D3) -- it was never gated because the plan had no checkpoint:* task, but it has not actually been run yet."
  - truth: "A session that stops sending events entirely while its pane stays open (/exit or /clear reused the same pane -- SessionEnd does not fire for either) self-heals off the list within REAP_MAX_AGE instead of ticking forever (G-07-2)"
    test: "Start a session, then run /exit (or /clear) inside the same pane without closing it. Confirm the session entry is still visible for a while (pane alive, age not yet exceeded), then disappears from tray+dashboard once REAP_MAX_AGE (1h) elapses without a fresh event."
    expected: "Entry self-heals off both surfaces once REAP_MAX_AGE elapses, even though the pane itself never closed."
    why_human: "Same reasoning as the pane-kill item above -- the pure age-ceiling logic is unit-tested, but the live integration (and the 1-hour wait) has not been exercised. Also the exact mechanism this human-check would trigger is what CR-01's regression (see Gaps) rides on, so this check and a CR-01 fix verification should be done together once CR-01 is closed."
human_verification:
  - test: "Restart the tray, start a session in a tmux pane, run `tmux kill-pane -t <pane>` directly (bypassing SessionEnd), confirm the session disappears from both the tray menu and dashboard panel within ~1 poll tick; separately confirm a genuinely active session (pane alive, real events still arriving) is never wrongly reaped while in normal use."
    expected: "Killed-pane session self-heals off both surfaces within ~15s; an actively-used session is undisturbed."
    why_human: "07-02-SUMMARY.md's own D3 item -- requires a live GTK tray + real tmux pane kill; not automatable from this environment."
  - test: "Re-run 07-UAT.md Test 2 (open the dashboard with sessions in all three statuses; confirm sort order waiting -> running -> done and done rows dimmed) now that G-07-2 is closed, to separate 'sort/dim logic is correct' from 'the stale-session bug was masking it'."
    expected: "Clean sort order and dimming with no stuck/duplicate rows this time."
    why_human: "No headless JS execution path in this repo; the only prior attempt was confounded by the now-fixed G-07-2 bug."
---

# Phase 07: Live Session View in the Dashboard Verification Report

**Phase Goal:** See all currently-tracked Claude Code sessions and their status at a glance in the existing web dashboard, refreshed live, without leaving the top bar or opening the tray menu.
**Verified:** 2026-07-18T20:15:00Z
**Status:** gaps_found
**Re-verification:** Yes — after 07-02 gap closure (G-07-2), full re-pass over both plans' must-haves.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SESSVIEW-01: dashboard shows every tracked session with status (running/waiting/done) | VERIFIED | `write_dashboard()` (claude-monitor.py:337-364) builds `sessions=[{dir,status,entered}...]` from `list(self.sessions.values())` unconditionally and threads it into `render_dashboard`; `renderSessions()` (dashboard.py:478-509) renders the full list. `--selfcheck` (test b) confirms `waiting`/`running`/`done` and multiple dirs reach the page. |
| 2 | SESSVIEW-02: each row shows project dir and accurate live time-in-current-state | VERIFIED | Project dir: selfcheck-verified (`textContent`, `alpha-proj`/`beta-proj`). Duration-reset-only-on-transition (D-01, `if old != event: s["entered"] = time.time()`, claude-monitor.py:395-396): **human-confirmed** — 07-UAT.md Test 1 result `pass` ("Ticking confirmed... counter is monotonic across same-status repeats; resets to 0 only on a genuine transition"). Live 1s tick (D-02, `setInterval(renderSessions,1000)`, dashboard.py:511): **human-confirmed** — 07-UAT.md Test 3 result `pass`. |
| 3 | SESSVIEW-03: reflects live in-memory state, updates on existing meta-refresh cadence, no new IPC/socket/persistence | VERIFIED | `write_dashboard` still runs from the pre-existing `poll_loop` `dashboard.DASH_INTERVAL` throttle (claude-monitor.py:576-578), unchanged by 07-02. `reap_stale`/`_pop_stale` add no new socket/file/timer — `mon.reap_stale(now)` (claude-monitor.py:546) is an unconditional in-loop call, same cadence as the existing poll tick; grep confirms no new `open(...,'w')`/socket calls in either plan's diff. |
| 4 | SESSVIEW-04: no-sessions renders a clean empty state, no break/blank/reflow | VERIFIED | `--selfcheck` test (a): `render_dashboard(_srec, now_dash, sessions=[])` contains literal `"No active Claude Code sessions"` and `'"sessions": []'`. `<section>` panel markup emitted unconditionally. |
| 5 | SESSVIEW-05: dashboard stays self-contained (no external references), consistent with DASH-06 | VERIFIED | `--selfcheck` test (c) against the populated-sessions page: no `<link`, no `src=`, no `https://`; only `http://` is the SVG namespace string. All panel HTML/CSS/JS inline in `_DASH_BODY`/`_DASH_STYLE`/`_DASH_JS`. |
| 6 | Rows sort waiting -> running -> done; done rows render dimmed (D-04/D-06) | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `SESS_RANK`/`.sess-done` present and wired (dashboard.py:470,484-486,498). 07-UAT.md Test 2 result was `issue`, but the reported symptom ("two running sessions when one is done") is the now-closed G-07-2 bug, not evidence against the sort logic itself. Never cleanly re-confirmed in isolation — routed to human verification. |
| 7 | A session whose tmux pane no longer exists disappears from tray + dashboard within ~1 poll tick, no SessionEnd required (G-07-2) | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `pane_alive` (claude-monitor.py:468-482), `Monitor.reap_stale`/`_pop_stale` (claude-monitor.py:410-432), and the `poll_loop` wiring (claude-monitor.py:546) all present and correctly structured on inspection; `core.session_stale`'s pure decision table is locked by `--selfcheck`. But 07-02-SUMMARY.md itself flags the live end-to-end check (D3) as "Human Verification Pending" — it has not actually been run. |
| 8 | A session that stops sending events while its pane stays open (/exit or /clear) self-heals off the list within REAP_MAX_AGE (G-07-2) | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Same code path as #7 (`session_stale`'s `alive in (True, None)` age-ceiling branch). Pure-function behavior locked by `--selfcheck`; live 1-hour-elapsed integration behavior not yet observed. |
| 9 | A reaped-but-still-alive session simply reappears fresh with no data loss / no adverse side effect (07-02 safety claim) | ✗ FAILED | **CR-01 (07-REVIEW.md, critical, confirmed by direct code read this pass).** `Monitor._pop_stale` discards status history; the resurrected session's `old` status reads `None` in `Monitor.handle`, so `core.sess_should_notify(None, event)` is `True` even though nothing actually changed — a spurious `URGENCY_CRITICAL` "Waiting for input" popup re-fires (and the `acked`/"!" badge re-arms) for any session idling past `REAP_MAX_AGE` (1h) while genuinely alive. This is a reproducible regression to the already-delivered NOTIF-02 de-dupe guarantee, not "no data loss." See Gaps. |

**Score:** 5/9 truths verified (3 present-behavior-unverified, 1 failed)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `claude-monitor.py::Monitor.handle()` | `entered` epoch stamped on status change only (D-01) | ✓ VERIFIED | Lines 385-396, human-confirmed via 07-UAT.md Test 1. |
| `claude-monitor.py::Monitor.write_dashboard()` | sessions snapshot built and threaded into `render_dashboard` (D-08) | ✓ VERIFIED | Lines 337-364, snapshot inside existing `try/except Exception` guard. |
| `claude_monitor/dashboard.py::render_dashboard` | `sessions=()` param + `"sessions"` payload key | ✓ VERIFIED | Signature and payload key both present; default stays empty. |
| `claude_monitor/dashboard.py` (`_DASH_BODY`/`_DASH_STYLE`) | session-panel table markup + dot CSS | ✓ VERIFIED | `#sess-tbl`, `.sd`/`.sd-waiting`/`.sd-running`/`.sd-done`, `.sess-done`, `.sdur` all present. |
| `claude_monitor/dashboard.py` (`_DASH_JS`) | client-side textContent row render + 1s live-ticker | ✓ VERIFIED | `renderSessions()` uses `textContent`/`createTextNode` exclusively; `setInterval(renderSessions,1000)` present. |
| `claude_monitor/core.py::REAP_MAX_AGE` / `session_stale` | pure reap-decision function + constant (G-07-2) | ✓ VERIFIED | Lines 116-137, matches all four documented behavior cases; `--selfcheck` locks all of them plus the exact boundary. |
| `claude-monitor.py::pane_alive` | tri-state tmux pane-existence check | ✓ VERIFIED | Lines 468-482: `None` for falsy pane, `True`/`False` for a real target, `None` on any subprocess exception — never raises. |
| `claude-monitor.py::Monitor.reap_stale`/`_pop_stale` | wired into `poll_loop`, single-mutator preserved | ✓ VERIFIED (wiring), ✗ regression in resurrection semantics | `poll_loop` calls `mon.reap_stale(now)` unconditionally every tick (line 546); `reap_stale` never mutates `self.sessions` directly, only `_pop_stale` (invoked via `GLib.idle_add`) does. Threading discipline is sound (see CR-01's own confirmation of this). The wiring itself is correct; the **consequence** of what it wires into `Monitor.handle` is CR-01's gap. |
| `claude_monitor/test_claude_monitor.py` | `session_stale` `--selfcheck` asserts covering all three alive states + boundary | ✓ VERIFIED | Lines 465-486, all four behavior cases plus the exact `now - entered == max_age` boundary. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `Monitor.handle()` | `s["entered"]` | stamped only when `old != event` | WIRED, behavior VERIFIED | Human-confirmed via 07-UAT.md Test 1 (this pass upgrades it from the prior verification's PRESENT_BEHAVIOR_UNVERIFIED). |
| `poll_loop` | `Monitor.reap_stale(now)` | unconditional call every tick, right after `now = time.time()` | WIRED | claude-monitor.py:545-546, matches plan spec exactly. |
| `Monitor.reap_stale` | `Monitor._pop_stale` | `GLib.idle_add(self._pop_stale, stale)`, poll-thread compute / Gtk-thread mutate | WIRED | claude-monitor.py:424-425; `reap_stale` itself performs no `.pop()`/`.update()` on `self.sessions` (confirmed by reading — single-mutator invariant holds for the *mutation* boundary). |
| `Monitor._pop_stale` (resurrection) | `Monitor.handle`'s `old` read | NOT wired — no memory of prior status crosses the pop/resurrect boundary | BROKEN | This is exactly CR-01: the pop discards status, so the next `handle()` call cannot distinguish "resurrected, same status" from "brand new session," and unconditionally re-notifies. |
| `D.sessions` payload | DOM rows | client-side `textContent`, never HTML interpolation | WIRED | Unchanged from 07-01, reconfirmed by `--selfcheck` test (b). |
| Sessions `<section>` | self-contained page | inline `_DASH_*` constants, no `<link>`/`src=`/external URL | WIRED | Confirmed by `--selfcheck` test (c) and grep. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| Sessions panel (`#sessions` tbody) | `D.sessions` | `Monitor.write_dashboard()` snapshots `list(self.sessions.values())`, mutated by `Monitor.handle()` (hook events) and now also `Monitor._pop_stale()` (reap) | Yes — live in-memory dict | ✓ FLOWING (but the reap-induced resurrection injects a stale/incorrect "brand new" signal into the notification path downstream of this same dict — see CR-01) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full `--selfcheck` suite (incl. session-panel + `session_stale` groups) | `python3 claude-monitor.py --selfcheck` | `ok` / exit 0 | ✓ PASS |
| dashboard.py stays GTK-free | `python3 -c "import claude_monitor.dashboard; assert 'gi' not in sys.modules"` | `gtk-free ok` | ✓ PASS |
| Entry points compile | `python3 -m py_compile claude-monitor.py claude_monitor/dashboard.py claude_monitor/core.py claude_monitor/test_claude_monitor.py` | exit 0 | ✓ PASS |
| Lint clean | `ruff check .` | `All checks passed!` | ✓ PASS |
| `sess_should_notify(None, "waiting")` reproduces CR-01's re-fire condition | `python3 -c "from claude_monitor.core import sess_should_notify as f; print(f(None,'waiting'))"` (verified by reading `core.py:113`: `return new_status in ("waiting","done") and old_status != new_status`) | `True` | ✗ FAIL (confirms the regression traced in CR-01 / gap #9) |
| `Monitor.handle` x `reap_stale` interaction exercised by any test | grep `Monitor(` / `reap_stale(` / `_pop_stale(` in `test_claude_monitor.py` | no matches | ? SKIP — WR-06 (07-REVIEW.md): no test exists, requires a live GTK `Monitor()`; routed to human verification for the presence checks, but CR-01's notify-refire is provable by pure-function composition alone (done above) without needing GTK. |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| SESSVIEW-01 | 07-01-PLAN.md, 07-02-PLAN.md | dashboard shows all tracked sessions w/ status | ✓ SATISFIED | Truth #1 |
| SESSVIEW-02 | 07-01-PLAN.md | each row shows dir + accurate time-in-state | ✓ SATISFIED | Truth #2, human-confirmed |
| SESSVIEW-03 | 07-01-PLAN.md, 07-02-PLAN.md | live in-memory reflect, existing cadence, no new IPC/persistence | ✓ SATISFIED | Truth #3 |
| SESSVIEW-04 | 07-01-PLAN.md | clean empty state | ✓ SATISFIED | Truth #4 |
| SESSVIEW-05 | 07-01-PLAN.md | self-contained, no external refs | ✓ SATISFIED | Truth #5 |

No orphaned requirements — all 5 SESSVIEW-01..05 IDs appear across the two plans' `requirements:` frontmatter and match `REQUIREMENTS.md`'s v1.4 section exactly.

**Documentation-sync note (not a code gap):** `REQUIREMENTS.md`'s checkboxes for SESSVIEW-02/04/05 are still `[ ]` and the Traceability table still lists all five SESSVIEW-* rows as "Planned" rather than "Delivered," even though SESSVIEW-01 and -03 are already checked `[x]`. This is inconsistent bookkeeping left over from before 07-01 executed — worth fixing at the ship/complete-milestone step, does not block this verification.

### Anti-Patterns Found

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers, no stub returns, no hardcoded-empty props feeding the panel, in any of the four modified files (`claude-monitor.py`, `claude_monitor/core.py`, `claude_monitor/dashboard.py`, `claude_monitor/test_claude_monitor.py`).

The one 🛑 blocker-class finding is CR-01, already elevated to a structured gap above (not merely an anti-pattern — it is a demonstrated functional regression, confirmed independently in this pass).

### Code Review Findings (07-REVIEW.md, carried forward for context)

07-REVIEW.md (re-run after 07-02, `b663814`) found 1 critical / 6 warning / 3 info. The critical (CR-01) is promoted to a Gap above per the task's explicit instruction. The warnings/info below do not block this phase's goal but should be triaged before the v1.4 milestone ships:

- **WR-01** (low): `SESS_RANK` plain-object lookup vulnerable to an `Object.prototype` key collision on an unrestricted status string — silent sort breakage, local trust boundary only.
- **WR-02** (medium): `_pop_stale`'s decision (`reap_stale`, poll thread) and enactment (`_pop_stale`, Gtk thread, `idle_add`) are split by an unsynchronized time gap (TOCTOU) — a session that "un-stales" itself in that window still gets popped.
- **WR-03** (medium): `watch_focus` mutates live `self.sessions` dicts (`s["acked"] = True`) directly from its own thread, bypassing `GLib.idle_add` entirely — predates this phase but violates the same single-mutator invariant `reap_stale`/`_pop_stale` were built to respect.
- **WR-04** (medium): `write_dashboard`'s three-separate-`.get()` snapshot can read a torn dict mid-`Monitor.handle()` update (new status, stale `entered`).
- **WR-05** (low): `SESS_RANK` guard issue duplicate framing (see WR-01) — the sort comparator itself.
- **WR-06** (info/process): no test exercises the `Monitor.handle` x `reap_stale`/`session_stale` interaction beyond the pure function — this is exactly the coverage gap that let CR-01 land unnoticed by `--selfcheck`.
- **IN-01/02/03**: hardcoded `colspan="3"`, orphaned `notif_slots`/`notif_acts` entries on reap, unvalidated `event` strings from the socket. Minor, non-blocking hygiene items.

### Human Verification Required

### 1. Killed-pane self-heal, end-to-end (G-07-2, 07-02-SUMMARY.md's own D3 item)

**Test:** Restart the tray (`just restart`). Start a session in a tmux pane so it shows in the tray menu and dashboard Sessions panel. Run `tmux kill-pane -t <pane>` directly (bypassing `SessionEnd`). Confirm the session disappears from both surfaces within about one poll tick (~15s). Separately, keep a genuinely active session running and confirm it is never wrongly reaped while in normal use.
**Expected:** Killed-pane session vanishes from tray + dashboard within ~15s; an actively-used session is undisturbed.
**Why human:** Requires a live GTK tray process and a real tmux pane kill; 07-02-SUMMARY.md itself records this as pending, not yet run.

### 2. Re-run sort/dim UAT now that G-07-2 is closed (D-04/D-06)

**Test:** Open the dashboard with sessions simultaneously in all three statuses; confirm row order waiting -> running -> done and that done rows render visibly dimmed, with no stuck/duplicate rows this time.
**Expected:** Clean sort order and dimming, no leftover-stale entries.
**Why human:** No headless JS runner in this repo; the one prior attempt (07-UAT.md Test 2) was confounded by the since-fixed G-07-2 bug, so the sort/dim logic itself was never cleanly observed.

### Gaps Summary

One blocking gap: **CR-01** — the G-07-2 self-heal reap mechanism, once it ages out a genuinely-alive session past `REAP_MAX_AGE`, resurrects it as a brand-new entry with no memory of its prior status. `Monitor.handle`'s `old = s.get("status")` then reads `None`, `core.sess_should_notify(None, event)` evaluates `True`, and a full `URGENCY_CRITICAL` "Waiting for input" notification re-fires (badge re-arms too) for a session the user may have already seen and dismissed an hour earlier. This was verified directly in this pass by reading the exact code path and confirming `sess_should_notify(None, "waiting")` returns `True` via `core.py`'s own implementation — not merely inferred from 07-REVIEW.md's narrative. It contradicts the 07-02 plan's own must-have framing ("no data loss," "harmless by design") and is a concrete regression against the already-delivered NOTIF-02 de-dupe guarantee from Phase 5. This phase is the last phase on the roadmap for this milestone, so there is no later phase to defer this to — it needs its own gap-closure plan (07-03) before the v1.4 milestone ships.

Two items remain routed to human verification rather than failed, because the underlying code is present and correctly wired on inspection but has not been observed running live: (1) the killed-pane end-to-end self-heal timing (07-02-SUMMARY.md's own pending D3 check), and (2) a clean re-run of the sort/dim UAT now that the G-07-2 confound is removed.

Everything from the original 07-01 delivery (panel presence, empty state, self-containment, dir-inertness/XSS mitigation, duration accuracy and live-tick) either remains verified or has since been upgraded from behavior-unverified to human-confirmed via 07-UAT.md's Tests 1 and 3.

---

_Verified: 2026-07-18T20:15:00Z_
_Verifier: Claude (gsd-verifier)_
