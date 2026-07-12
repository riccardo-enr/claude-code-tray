---
phase: 03-usage-trends-in-the-tray
verified: 2026-07-12T00:00:00Z
status: human_needed
score: 2/5 must-haves verified
behavior_unverified: 3
overrides_applied: 0
behavior_unverified_items:
  - truth: "The tray menu renders a bare 24-char auto-scaled block sparkline of mean usage%/hour over 24h (TREND-01)"
    test: "Run the tray (python3 claude-monitor.py) and let it accumulate >~1h of history, then open the tray menu"
    expected: "A bare block-glyph sparkline row (e.g. the SPARK_GLYPHS ramp) appears below a separator under the usage rows, with visible gaps for empty hours and no label"
    why_human: "Pure sparkline logic is proven by --selfcheck and wiring is statically confirmed, but the live GTK render + ~1h data accumulation cannot be exercised programmatically"
  - truth: "The tray menu shows today and current-ISO-week mean burn RATE in tok/hr (TREND-02)"
    test: "With >~1h of history, open the tray menu"
    expected: "A row 'today <rate>/hr | wk <rate>/hr' appears (a literal '-' when a window has no records)"
    why_human: "trend_burn logic is selfcheck-proven and wired via compute_trends; the visible rendered row needs the live tray"
  - truth: "The tray menu shows the single peak usage hour-of-day (0-23 local) and its mean burn rate (TREND-03)"
    test: "With >~1h of history spanning multiple hours, open the tray menu"
    expected: "A row 'peak hour: HH:00 (<rate>/hr)' appears for the busiest local hour"
    why_human: "trend_peak_hour logic is selfcheck-proven and wired; the visible rendered row needs the live tray"
human_verification:
  - test: "Run tray with < ~1h of history and open the menu"
    expected: "A single insensitive 'trends: collecting history...' row shows under a separator; sessions, click-to-focus, and usage rows keep working"
    why_human: "Empty-state cutover render + no-regression of prior behavior are live-GTK observables"
  - test: "Run tray, accumulate > ~1h of history, open the menu"
    expected: "Collecting row swaps to three insensitive rows: bare sparkline, 'today .../hr | wk .../hr', 'peak hour: HH:00 (.../hr)'; menu order is sessions, usage rows, SEPARATOR, trend rows, SEPARATOR, Quit"
    why_human: "Live tray rendering of the three TREND rows is user-observable only"
  - test: "Point CLAUDE_TRAY / history at an unwritable or missing path and run the tray"
    expected: "Tray keeps running; trends fall back to collecting/last-known state; no crash, no frozen menu"
    why_human: "OSError degradation path in compute_trends is only observable while the daemon runs"
---

# Phase 3: Usage Trends in the Tray Verification Report

**Phase Goal:** The user sees usage history turned into trends inside the existing tray menu — a sparkline, daily and weekly burn, and peak-usage hours — with no separate window or charting GUI.
**Verified:** 2026-07-12
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Tray renders a bare 24-char auto-scaled block sparkline of mean usage%/hour over 24h (TREND-01) | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `trend_sparkline` (claude-monitor.py:264) logic proven by demo asserts (len==24, floor/top glyph, interior gap, empty->all gaps, flat window no ZeroDivisionError); wired compute_trends:609 -> self.trends -> trend_rows:563 -> rebuild_menu:527. Live GTK render needs ~1h data — human. |
| 2 | Tray shows today + current-ISO-week mean burn RATE tok/hr, raw per-min x60 once (TREND-02) | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `trend_burn` (claude-monitor.py:296) asserted mean(100,200)*60=9000.0, empty->None; formatted at compute_trends:613 'today %s/hr \| wk %s/hr' with '-' for None. Live render — human. |
| 3 | Tray shows single peak usage hour-of-day (0-23 local) + mean burn rate (TREND-03) | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `trend_peak_hour` (claude-monitor.py:308) asserted returns (15, 9000.0), ties->lowest hour, empty->None; formatted compute_trends:622 'peak hour: %02d:00 (%s/hr)'. Live render — human. |
| 4 | No history file I/O on the Gtk main thread; trends computed in poll_loop, only cached strings read at menu rebuild (D-05, HIST-03/POLL-02) | ✓ VERIFIED | All 3 `open(HISTORY_PATH)` are in poll-thread paths: append_history:216, prune_history:232, compute_trends:602. `compute_trends` called only from poll_loop:736. `trend_rows`:563 reads only self.trends; `usage_rows`:546 reads only self.usage; `rebuild_menu`:509 and `apply_usage`:576 do no I/O. |
| 5 | Trends recompute on ~5min throttle, compute once on first poll, empty-state 'collecting history...' until ~1h span (D-06/D-12) | ✓ VERIFIED | `last_trend = 0.0` (poll_loop:727) forces first-iteration compute; throttle `now - last_trend >= TREND_INTERVAL` (735), TREND_INTERVAL=5*60 (72). Cutover: compute_trends:606 sets self.trends=None when `records[-1][t]-records[0][t] < TREND_MIN_SPAN` (3600); trend_rows:569 returns collecting row when None. |

**Score:** 2/5 truths verified (3 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `claude-monitor.py` | Extended in place: trend fns, constants, Monitor.trends cache, compute_trends, trend_rows, rebuild_menu wiring | ✓ VERIFIED | All symbols present and wired. py_compile clean. 4 trend defs, 1 `import datetime`, SPARK_GLYPHS ramp exactly `▁▂▃▄▅▆▇█`, compute_trends+trend_rows present, 2 SeparatorMenuItem. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| poll_loop | compute_trends(now) | Throttled TREND_INTERVAL, forced first poll (last_trend=0.0), off Gtk main thread | ✓ WIRED | poll_loop:735-737 |
| rebuild_menu | trend_rows() | Reads self.trends only, appends SeparatorMenuItem + insensitive rows | ✓ WIRED | rebuild_menu:526-530; set_sensitive(False) at 529 |
| compute_trends | parse_history(open(HISTORY_PATH)) | Single OSError-guarded corruption-tolerant read | ✓ WIRED | compute_trends:602-605, `except OSError: return` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| trend rows (rebuild_menu) | self.trends | compute_trends reads HISTORY_PATH via parse_history, builds rows from real records | ✓ FLOWING (static) | Data path is real (reads the Phase-2 JSONL store, not hardcoded). Runtime presence of >~1h data is the human-verified precondition. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Automated self-check suite (embedded asserts, project's test suite) | `python3 claude-monitor.py --selfcheck` | prints `ok`, exit 0 | ✓ PASS |
| Module compiles | `python3 -m py_compile claude-monitor.py` | clean | ✓ PASS |
| Live tray rendering of trend rows | (needs running GTK tray + ~1h history) | — | ? SKIP (human) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| TREND-01 | 03-01 | Sparkline of usage % over recent window (24h) from history | ✓ SATISFIED (logic+wiring); live render human | trend_sparkline + wiring; selfcheck asserts |
| TREND-02 | 03-01 | Aggregate burn for today and current week from history | ✓ SATISFIED (logic+wiring); live render human | trend_burn + local_bounds + wiring; selfcheck asserts |
| TREND-03 | 03-01 | Peak-usage hour-of-day by mean usage/burn | ✓ SATISFIED (logic+wiring); live render human | trend_peak_hour + wiring; selfcheck asserts |

No orphaned requirements — REQUIREMENTS.md maps exactly TREND-01/02/03 to Phase 3, all three declared in the plan's `requirements` frontmatter.

### Anti-Patterns Found

None. No `TBD`/`FIXME`/`XXX` debt markers, no `TODO`/`HACK`/`PLACEHOLDER`. The `trends: collecting history...` string is the endorsed D-12 empty state (not a stub). The single `# ponytail:` note at line 623 documents the intentional lockless single-rebind of self.trends. No stray unicode (`·`/`…`) — only the endorsed SPARK_GLYPHS ramp + SPARK_GAP.

### Human Verification Required

Per phase context, the three ROADMAP success criteria describe user-OBSERVABLE tray rendering. The `--selfcheck` gate proves the pure-function LOGIC and static inspection proves the wiring, but whether the rows visibly render in the live GTK tray requires running the daemon and accumulating ~1h of history. Three items (see `behavior_unverified_items`) plus the empty-state, full-render, and OSError-degradation checks (see `human_verification`) need a human on an X11 session.

### Gaps Summary

No gaps. All automated gates pass (selfcheck `ok`, py_compile clean), every source assertion in the plan holds, the load-bearing D-05 invariant (no history I/O on the Gtk main thread) is statically confirmed, and TREND-01/02/03 logic is proven by the embedded asserts and wired end-to-end (poll_loop -> compute_trends -> self.trends -> trend_rows -> rebuild_menu). The phase is not `passed` only because the three success criteria are inherently user-observable live-tray renders that cannot be exercised without running the GTK tray for ~1h — these route to human verification, not failure.

---

_Verified: 2026-07-12_
_Verifier: Claude (gsd-verifier)_
