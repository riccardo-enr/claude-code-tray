# Phase 5: Notification Path & Event Producers - Context

**Gathered:** 2026-07-13
**Status:** Ready for planning

<domain>
## Phase Boundary

One shared notification emit path for the tray -- emit + de-dupe + mute hook +
click action -- with **both** producers riding it from day one:

- **NOTIF-01/02/03/04** -- the shared path: single emit function, de-duped per
  state transition (never per poll tick), click routes back to an action, and a
  failing/absent notification daemon degrades silently without killing a thread
  or blocking the Gtk main loop.
- **SESS-01/02** -- session `waiting` / `done` events, fed by the existing hook
  -> unix socket pipeline (`serve()` -> `GLib.idle_add` -> `Monitor.handle`).
- **ALERT-02/03/04** -- predictive 5-hour and 7-day quota alerts, evaluated on
  the existing poll thread, re-arming when a cap's window rolls over.

Includes the **Python port of the QUOTA-03 `project()` formula** (currently
JavaScript-only, `claude-monitor.py:931`) so the poll thread can evaluate it.
Mechanical arithmetic port with known semantics -- not a new forecaster.

Does NOT include: config/toggles/mute UI (Phase 6), new polling, a second data
source, new dependencies, a hard-threshold (non-predictive) push alert
(ALERT-F1, deferred), quiet hours (NOTIF-F1, deferred).

</domain>

<decisions>
## Implementation Decisions

### Session notification content & lifetime (SESS-01, SESS-02)
- **D-01:** **Directory as title, state as body.** Title is the session's `dir`
  (the `os.path.basename(cwd)` the tray row already uses); body is the state
  spelled out -- `"Waiting for input"` / `"Session finished"` (exact wording is
  Claude's discretion). The project name is the loudest thing in the popup,
  which is what you scan when several sessions are live.
- **D-02:** **`waiting` sticks, `done` expires.** A `waiting` event is a
  blocking prompt -- it must persist on screen until dismissed or clicked
  (resident / critical urgency, or the equivalent hint in whichever binding is
  chosen). A `done` event is informational and auto-expires on the daemon's
  normal timeout into GNOME's notification list.
- **D-03:** **One notification slot per session -- replace in place.** Each
  session id owns a single notification, and a later transition **overwrites**
  the previous popup rather than stacking a new one (same `replaces_id` for the
  D-Bus route, or same notification id for the `Gio.Notification` route). N live
  sessions means at most N popups, ever -- mirroring the tray, which shows one
  row per session. This is the de-dupe surface for SESS events (NOTIF-02): a
  session sitting in `waiting` across many ticks must not re-emit; only a
  *change* of state emits.

### When a session event fires (SESS-01, SESS-02)
- **D-04:** **Always fire -- do NOT suppress on `_onscreen`.** `serve()` already
  computes `looking_at(pane, tmux)` and uses it to pre-ack the `!` attention
  badge (`claude-monitor.py:1721-1722`, `Monitor.handle` line 1653). The
  notification path deliberately **ignores** that signal: a notification fires on
  every waiting/done transition regardless of where the user is looking.
  The existing badge pre-ack behavior is unchanged -- this is an explicit
  divergence between the two signals, not an oversight. Do not "helpfully" gate
  the notification on `_onscreen`.

### Predictive quota alert trigger (ALERT-02, ALERT-03, ALERT-04)
- **D-05:** **Fire when `proj >= 100` AND the exhaust time is at least 15 minutes
  away.** The ported `project()` yields `proj` (projected % at reset) and, when
  `proj > 100` and the crossing lands before reset, an `exhaust` epoch. An alert
  requires both: the projection crosses 100, *and* `exhaust - now >= 15 * 60`.
  A projection that says "you run out in 90 seconds" is not actionable, and the
  existing >80% icon badge (ALERT-01) already covers "you're nearly there".
  The `e <= 0.05` early guard in `project()` suppresses the noisy start of a
  window for free -- keep it in the port.
- **D-06:** **One alert per cap per window; re-arm only on reset.** Once a cap
  has alerted, it stays silent for the remainder of that window even if the
  projection climbs further. A change in that cap's `resets_at_epoch` means a new
  window, which re-arms it (ALERT-04). No re-arm on the projection falling back
  under 100% and climbing again within the same window -- that flaps around the
  boundary. Lead-time step re-fires ("~30m left") stay deferred, per
  REQUIREMENTS' lean, until one alert proves too coarse.
- **D-07:** **A cap already at ~100% used is NOT this phase's job.** The alert is
  strictly *predictive*; the reactive signal is the ALERT-01 badge, and a hard
  threshold push is explicitly deferred (ALERT-F1). An exhausted cap has no lead
  time, so D-05's rule keeps it silent naturally -- no special case, no code.

### Quota alert content & click action (ALERT-02, ALERT-03)
- **D-08:** **Cap as title, projection + exhaust time as body.** Title names the
  cap (`"5-hour quota"` / `"7-day quota"`); body carries both the severity and
  the actionable clock time -- e.g. `"Projected 140% at reset -- runs out
  ~16:20"`. Exhaust time rendered as a local wall-clock time (the dashboard's
  `hhmm()` convention), not a duration.
- **D-09:** **Clicking a quota alert opens the usage dashboard.** Reuses
  `Monitor.open_dashboard` (`claude-monitor.py:1468`) -- already a zero-file-I/O
  action that just opens the pre-written `file://`. The dashboard is exactly
  where you'd go to inspect the projection you were warned about. Note the click
  handler must marshal onto the Gtk main thread if the action arrives on a D-Bus
  worker.

### Claude's Discretion
- **The binding.** `Gio.Application` + `Gio.Notification` + a `.desktop` file
  vs. `org.freedesktop.Notifications.Notify` through `Gio.DBusProxy` (with
  `actions` + the `ActionInvoked` signal). ROADMAP and REQUIREMENTS both defer
  this to plan time; NOTIF-01's "`Gio.Notification`" is intent (PyGObject, no new
  dependency), not a mandate. Whichever route is chosen must support: replace-in-
  place ids (D-03), a per-notification urgency/resident hint (D-02), and click
  actions (D-09, NOTIF-03).
- **The mute hook (NOTIF-02 -> Phase 6).** Phase 5 owns the *hook point* -- a
  single gate inside the shared emit path that Phase 6's config will consult.
  One gate function, four event-type keys (waiting / done / 5h / 7d) plus a
  global. Do not build the config file, the toggles, or persistence here.
- Exact body wording, urgency constants, and the notification icon.
- Where the de-dupe / arm state lives (per-session dict entry, per-cap arm flag).
  It must be expressible as **pure functions** so `--selfcheck` can assert it.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and requirements
- `.planning/ROADMAP.md` -- "Phase 5" section, including the **Grounding** block
  (four verified facts about the current code that the plan must respect) and the
  five Success Criteria.
- `.planning/REQUIREMENTS.md` -- NOTIF-01..04, SESS-01/02, ALERT-02/03/04; the
  "Open Questions" section (binding choice, alert timing surface); the "Note on
  the QUOTA-03 reuse" appendix; the Out of Scope list.
- `.planning/PROJECT.md` -- standing constraints: stdlib + PyGObject only, X11
  only, one background poll, nothing blocking the Gtk main loop.

### Source (single file -- read these regions)
- `claude-monitor.py:931` -- `project()`, the JS QUOTA-03 projection to port to
  Python verbatim (elapsed-fraction linear extrapolation, `e<=0.05` early guard,
  exhaust time when `proj>100`). The JS copy **stays** -- it recomputes against a
  live browser clock. Note the deliberate duplication where the Python port lands.
- `claude-monitor.py:1636` -- `Monitor.handle`, the Gtk-main-thread `idle_add`
  target where session state transitions land. The SESS producer hooks here; the
  emit must be non-blocking on this thread.
- `claude-monitor.py:1699` -- `serve()`, the socket thread. **Unguarded** -- no
  blanket `except`. A raise in its loop kills the socket thread and all session
  events permanently. NOTIF-04 has real teeth here.
- `claude-monitor.py:1726` -- `poll_loop`, which HAS the blanket `except` +
  `traceback.print_exc()` from quick task `260713-fry`. The ALERT producer runs
  here and inherits that protection.
- `claude-monitor.py:1450` -- `Monitor.focus(pane, tmux)`, the existing
  click-to-focus action NOTIF-03 must reuse.
- `claude-monitor.py:1468` -- `Monitor.open_dashboard`, the click action for
  quota alerts (D-09).
- `claude-monitor.py:1033` -- `demo()` / `--selfcheck`, where the projection-port
  and de-dupe/arm assertions go.

### Prior phase context (patterns that bind)
- `.planning/phases/04-usage-web-dashboard/04-CONTEXT.md` -- D-04/D-05: all file
  I/O and expensive work happens on `poll_loop`, never on the Gtk main thread;
  menu actions do zero I/O.
- `.planning/codebase/OVERVIEW.md`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`Monitor.focus(pane, tmux)`** (`:1450`) -- tmux select-window/select-pane +
  `wmctrl -x -a`. NOTIF-03's click action is literally this call, with the
  session's stored `pane`/`tmux`. Shells out, so it must not run on the Gtk main
  thread synchronously if the daemon delivers the action there -- the existing
  `on_click` menu handler already does exactly that, so precedent exists.
- **`Monitor.open_dashboard`** (`:1468`) -- zero-I/O `webbrowser.open(file://)`,
  reused verbatim for the quota-alert click (D-09).
- **`self.sessions[sid]`** dict entries already carry `dir`, `status`, `pane`,
  `tmux`, `cwd`, `acked` -- everything a session notification and its click
  action need. The per-session notification id (D-03) is one more key.
- **`u["resets_at_epoch"]` / `u["seven_day_reset"]` / `u["used_percentage"]` /
  `u["seven_day_pct"]`** -- already parsed into `self.usage` by `parse_usage`;
  the ALERT producer needs no new fields. Note `seven_day_*` may be `None` on an
  older CLI -- the 7d alert must degrade silently, exactly as `usage_rows` does.
- **`demo()` / `--selfcheck`** -- the established place for pure-function
  assertions. The projection port and the de-dupe/arm state machine both belong
  there.

### Established Patterns
- **Nothing blocking on the Gtk main thread.** `serve()` and `poll_loop` do the
  slow work on daemon threads and marshal back with `GLib.idle_add`. A D-Bus
  notify is async and fine; a `subprocess` shell-out is not.
- **Total tolerance at the edges.** `parse_history` swallows corruption;
  `write_dashboard` and `poll_loop`'s body wrap in broad `except`. The
  notification emit path must follow suit -- an absent/failing daemon degrades to
  "no popup this tick", never a raise. **`serve()` is the gap:** it has no such
  guard today, and the session producer rides it.
- **Degrade on missing data, don't crash.** `usage_rows` only renders the weekly
  cap when the payload carried it. The 7d alert does the same.
- **`ponytail:` comments** mark deliberate simplifications with their ceiling.

### Integration Points
- `Monitor.handle` (`:1636`) -- session transition -> compare old vs new status ->
  emit or not. This is where SESS de-dupe (D-03) lives.
- `poll_loop`'s per-tick body (`:1749+`) -- after `fetch_usage()`, evaluate the
  ported projection for both caps and emit/arm. Runs off the Gtk main thread.
- The shared emit function -- one place, called from both, carrying the mute gate
  Phase 6 will wire config into.

</code_context>

<specifics>
## Specific Ideas

- Session popup shape, as the user pictured it:
  ```
  +---------------------------+
  | my-project                |
  | Waiting for input         |
  +---------------------------+
  ```
- Quota alert shape:
  ```
  +------------------------------------+
  | 5-hour quota                       |
  | Projected 140% at reset            |
  | runs out ~16:20                    |
  +------------------------------------+
  ```
- Lead-time constant: **15 minutes** (D-05).

</specifics>

<deferred>
## Deferred Ideas

- **Suppress-when-looking for notifications** -- explicitly rejected for this
  phase (D-04). The `_onscreen` signal keeps gating only the `!` badge. Revisit
  only if the always-fire behavior proves annoying in practice.
- **Lead-time step alerts** ("~30m left", "~10m left") -- deferred until the
  single per-window alert (D-06) proves too coarse. Carried from REQUIREMENTS'
  Open Questions.
- **"Cap exhausted" hard-threshold notification** -- ALERT-F1, already deferred
  in REQUIREMENTS; reconfirmed here (D-07). Would also add a fifth event type
  that Phase 6's four toggles do not cover.
- **Quiet hours** (NOTIF-F1) and **per-event sound/urgency config** (NOTIF-F2) --
  deferred in REQUIREMENTS; nothing in this discussion changes that.
- **Config file, toggles, global mute, configurable badge threshold** -- Phase 6
  (CFG-01..05). Phase 5 leaves only the gate hook.

</deferred>

---

*Phase: 5-Notification Path & Event Producers*
*Context gathered: 2026-07-13*
