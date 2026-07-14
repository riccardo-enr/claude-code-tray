# Requirements — claude-code-tray v1.3 (Notifications & Predictive Alerts)

Milestone goal: give the tray a **push voice**. One notification subsystem that all
tray events route through, so the user can context-switch away from the top bar and
get pulled back only when a session actually needs them — or when quota is about to
run out. Merges SEED-002 (predictive quota alerts) and SEED-004 (session-finished
notification), which converge on the same shared path.

Constraints carried forward: stdlib + PyGObject only, no new dependencies, no new
polling, nothing on the Gtk main loop, X11 only.

## v1.3 Requirements

### Notification subsystem (NOTIF)

The shared path. This is the actual deliverable — the individual pings are producers.

- [x] **NOTIF-01**: Tray events are delivered as GNOME desktop notifications via a single shared emit path (`Gio.Notification` / PyGObject — no new dependency).
- [x] **NOTIF-02**: An event notifies **once per state transition**, not once per poll — de-duped so a session sitting in `waiting`, or a cap sitting over its projection, does not re-notify on every tick.
- [x] **NOTIF-03**: Clicking a session notification focuses the originating tmux pane and raises the terminal window, reusing the tray's existing click-to-focus action.
- [x] **NOTIF-04**: Notification delivery never blocks the Gtk main loop and never kills the helper — a failing/absent notification daemon degrades silently, matching the HIST-03 / POLL-02 posture.

### Session events (SESS)

- [x] **SESS-01**: User is notified when a Claude Code session is **waiting for input** (permission prompt / question), fed by the existing hook -> unix socket status pipeline.
- [x] **SESS-02**: User is notified when a Claude Code session **finishes (done)**, same pipeline.

### Predictive quota alerts (ALERT)

Continues from ALERT-01 (the existing reactive >80% icon badge, v1.0). This milestone
adds the *predictive* signal. Derived from v1.2's QUOTA-03 **percentage** projection —
not from tokens. Under `--api` (quick task `260712-ndo`) the CLI's token counts come
back `null`, so SEED-002's original `tokens_remaining` / EWMA forecaster is not
buildable on the data we poll, and is superseded.

- [ ] **ALERT-02**: User is notified when the **5-hour** cap is projected to reach 100% *before its window resets* — not merely "usage is high". If the projection says the user coasts to reset, no alert fires.
- [ ] **ALERT-03**: User is notified when the **7-day** cap is projected to reach 100% before its window resets.
- [ ] **ALERT-04**: A cap's predictive alert **re-arms when its window resets**, so a fresh window can alert again after the previous one was already warned about.

### Configuration (CFG)

- [ ] **CFG-01**: User can toggle each notification event type (waiting / done / 5h alert / 7d alert) on and off from the tray menu, with the change taking effect without a restart.
- [ ] **CFG-02**: User can mute **all** notifications with a single tray toggle.
- [ ] **CFG-03**: Notification settings persist across restarts, in a small JSON config under `~/.claude/`.
- [ ] **CFG-04**: Config I/O is corruption-tolerant — a missing, unreadable, or malformed config falls back to defaults and never crashes the helper (same total-tolerance bar as the history store, which a corrupt record did once crash: quick task `260713-fry`).
- [ ] **CFG-05**: User can configure the high-usage badge threshold (currently a fixed 80%) through the same config. *(Closes the deferred "Alerting: configurable threshold" item.)*

## Future Requirements (deferred)

- **NOTIF-F1**: Quiet hours — suppress notifications in a configured time range. Deliberately deferred: a plain global mute (CFG-02) ships the value; add scheduling only if the mute proves insufficient. GNOME already has its own global Do Not Disturb.
- **NOTIF-F2**: Per-event sound / urgency customization.
- **ALERT-F1**: Push notification on a **hard** threshold crossing (e.g. >90%), as opposed to a projection. Not in v1.3 — the ALERT-01 icon badge remains the reactive signal; this milestone is about the predictive one.
- **HIST-F1 / DASH-F2**: Raw data export (CSV/JSON). Carried forward, unrelated to this milestone.
- **TREND-F1 / DASH-F3**: Configurable trend/dashboard ranges. Carried forward.

## Out of Scope

- **A forecaster of our own** (EWMA, least-squares, Holt smoothing over the burn series, per SEED-002's "Better Than Upstream"). The projection already exists as QUOTA-03 and is percentage-denominated; a second one would be a competing source of truth. Revisit only if QUOTA-03's projection is measurably wrong in practice.
- **The CLI's token-based `forecast` / `status` blocks.** Same standing reason as v1.2: `null` token counts under `--api`, and "limit hit" reported at 20% real usage.
- **Notification history / a notification center in the tray.** GNOME's own notification tray is the history.
- **Remote push** (email, phone, webhook) — local desktop only.
- **Replacing the icon badge or any existing tray row.** Notifications are additive; the glanceable top-bar signals stay.
- **New polling or a second data source** — alerts ride the existing poll tick; session events ride the existing hook socket.
- **New runtime dependencies** — `Gio.Notification` comes with PyGObject, already present.
- **Wayland support** — the app remains X11-only.

## Open Questions (settle at phase planning)

- **Notification binding (Phase 5, load-bearing).** The helper has **no `Gio.Application`** — `claude-monitor.py:1817` is a bare `Gtk.main()`. `Gio.Notification.send_notification` requires one, and notification *click actions* (NOTIF-03) additionally require an app id with a matching `.desktop` file. The alternative is calling `org.freedesktop.Notifications.Notify` through `Gio.DBusProxy`, which carries `actions` + an `ActionInvoked` signal with no app-id/.desktop plumbing. NOTIF-01's "`Gio.Notification`" is intent (PyGObject, no new dependency), not a binding mandate — settle the actual route at plan time.
- **Alert timing surface:** does the predictive alert fire once on crossing into "will exhaust before reset", or also re-fire with lead-time steps (e.g. "~30m left")? Lean: once per crossing per window (NOTIF-02 + ALERT-04), lead-time steps deferred until the single alert proves too coarse.
- **Config file location/name** under `~/.claude/` and whether it subsumes the existing `CLAUDE_TRAY_*` env vars or layers over them (env as default, menu as override).

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| NOTIF-01 | Phase 5 | Planned |
| NOTIF-02 | Phase 5 | Planned |
| NOTIF-03 | Phase 5 | Planned |
| NOTIF-04 | Phase 5 | Planned |
| SESS-01 | Phase 5 | Planned |
| SESS-02 | Phase 5 | Planned |
| ALERT-02 | Phase 5 | Planned |
| ALERT-03 | Phase 5 | Planned |
| ALERT-04 | Phase 5 | Planned |
| CFG-01 | Phase 6 | Planned |
| CFG-02 | Phase 6 | Planned |
| CFG-03 | Phase 6 | Planned |
| CFG-04 | Phase 6 | Planned |
| CFG-05 | Phase 6 | Planned |

**Coverage:** 14/14 v1.3 requirements mapped, no orphans, no duplicates.

### Note on the QUOTA-03 reuse (ALERT-02/03)

Verified during roadmapping: `project()` — the QUOTA-03 percentage projection — exists
**only as JavaScript**, at `claude-monitor.py:931`, inside the generated dashboard HTML.
`poll_loop` computes no projection. ALERT-02/03 must evaluate it on the poll thread, so
Phase 5 **ports** that ~15-line formula into Python (elapsed-fraction linear
extrapolation, `e<=0.05` early guard, exhaust-time when `proj>100`) and asserts it in
`--selfcheck`. This is mechanical arithmetic, not modeling, and not a new forecaster —
the semantics are already decided. The JS copy necessarily remains, since it recomputes
against a live browser clock.
