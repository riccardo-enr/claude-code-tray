# Phase 5: Notification Path & Event Producers - Discussion Log

**Date:** 2026-07-13
**Mode:** discuss (standard)

Human-reference record of the discussion. Downstream agents read `05-CONTEXT.md`,
not this file.

## Areas Selected

All four offered gray areas:

1. Session notification content & lifetime
2. When NOT to fire a session event
3. Predictive alert trigger rule
4. Quota alert content & click action

## Area 1 -- Session notification content & lifetime

**Q: What should a session notification say?**
Options: (a) dir + state mirroring the tray row; (b) **dir as title, state as
body**; (c) state as title, dir as body.
-> **(b)**. Project name is the loudest element -- what you scan when several
sessions are live. [D-01]

**Q: How long should a session notification live on screen?**
Options: (a) **waiting sticks, done expires**; (b) both auto-expire; (c) both
stick until dismissed.
-> **(a)**. `waiting` is a blocking prompt and must persist; `done` is
informational. [D-02]

**Q: Two popups per session, or one that updates in place?**
Options: (a) **replace in place, one slot per session**; (b) stack a new popup
each time.
-> **(a)**. Mirrors the tray's one-row-per-session model; N sessions -> at most N
popups. Doubles as the SESS de-dupe surface for NOTIF-02. [D-03]

## Area 2 -- When NOT to fire a session event

**Q: Should notifications fire when `serve()` found you were already looking at
that pane (`_onscreen`)?**
Options: (a) suppress -- reuse the existing `looking_at()` pre-ack; (b) **always
fire**.
-> **(b)**. Deliberate divergence: `_onscreen` keeps gating only the `!` attention
badge; the notification path ignores it entirely. Noted explicitly so a planner
does not "helpfully" reintroduce the gate. [D-04]

## Area 3 -- Predictive alert trigger rule

**Q: What exactly trips the alert?**
Options: (a) `proj >= 100`, nothing else; (b) **`proj >= 100` AND exhaust far
enough out to act on**; (c) configurable margin below 100.
-> **(b)**. A projection with no lead time is not actionable, and the >80% badge
already covers "nearly there". [D-05]

**Q: How much lead time?**
Options: (a) **15 minutes**; (b) 30 minutes; (c) 5 minutes.
-> **(a) 15 minutes**. [D-05]

**Q: Once a cap has alerted, when may it alert again?**
Options: (a) **once per window, re-arm on reset only**; (b) also re-arm on falling
back below 100% within the same window.
-> **(a)**. ALERT-04 exactly; (b) flaps around the boundary. Lead-time step
re-fires stay deferred. [D-06]

**Q: What about a cap ALREADY at ~100% used?**
Options: (a) **not this phase's job -- the badge owns it**; (b) fire a distinct
"cap exhausted" notification.
-> **(a)**. The alert is strictly predictive (ALERT-F1 is deferred); an exhausted
cap has no lead time, so D-05's rule silences it with no special case. (b) would
also add a fifth event type that Phase 6's four toggles do not cover. [D-07]

## Area 4 -- Quota alert content & click action

**Q: What should a predictive quota alert say?**
Options: (a) **cap as title, projection + exhaust time as body**; (b) exhaust time
as headline; (c) terse -- cap and time only.
-> **(a)**. Names the cap, the severity, and the actionable clock time. [D-08]

**Q: What happens when you click a quota alert (no pane to focus)?**
Options: (a) **opens the usage dashboard**; (b) nothing -- click just dismisses.
-> **(a)**. Reuses the existing zero-I/O `Monitor.open_dashboard`. [D-09]

## Not Asked (already settled upstream)

- **The notification binding** (`Gio.Application` + `Gio.Notification` vs.
  `org.freedesktop.Notifications` via `Gio.DBusProxy`). ROADMAP and REQUIREMENTS
  both explicitly defer this to plan time. Left as Claude's discretion, with the
  three capabilities it must support recorded in CONTEXT.md.
- The projection formula's semantics -- fixed by QUOTA-03; Phase 5 ports, does not
  redesign.

## Claude's Discretion

- Notification binding (see above).
- The mute gate's shape (Phase 5 owns the hook point only; Phase 6 owns config).
- Exact body wording, urgency constants, notification icon.
- Where the de-dupe / arm state lives -- constrained only by "must be pure
  functions so `--selfcheck` can assert it".

## Deferred Ideas

- Suppress-when-looking for notifications (rejected here, D-04).
- Lead-time step alerts ("~30m left").
- "Cap exhausted" hard-threshold push (ALERT-F1).
- Quiet hours (NOTIF-F1); per-event sound/urgency (NOTIF-F2).
- Config file, toggles, global mute, configurable badge threshold -- Phase 6.
