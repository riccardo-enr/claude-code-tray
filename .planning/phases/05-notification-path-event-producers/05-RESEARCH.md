# Phase 5: Notification Path & Event Producers - Research

**Researched:** 2026-07-13
**Domain:** Freedesktop desktop notifications on GNOME Shell 46 / X11, via PyGObject Gio D-Bus
**Confidence:** HIGH

## THE VERDICT (read this first)

**Route B wins: `org.freedesktop.Notifications` over `Gio.DBusProxy`.**

**Decisive reason:** Route A is not merely more expensive -- it is *impossible* without
installing a `.desktop` file. The notification daemon on this machine **is GNOME Shell
itself**, and its own source rejects any `Gio.Notification` whose app id has no matching
installed `.desktop`:

```js
// gnome-shell 46.0, ui/notificationDaemon.js:489-495  -- GtkNotificationDaemonAppSource
constructor(appId) {
    if (!Gio.Application.id_is_valid(appId))
        throw new InvalidAppError();
    const app = Shell.AppSystem.get_default().lookup_app(`${appId}.desktop`);
    if (!app)
        throw new InvalidAppError();          // <-- no .desktop => notification REJECTED
```
`AddNotificationAsync` catches that and returns a D-Bus error
(`NotificationError.INVALID_APP`, *"The app by ID X could not be found"*). The
notification **never appears at all**. Not degraded -- absent.
[VERIFIED: `gresource extract /usr/lib/gnome-shell/libshell-14.so /org/gnome/shell/ui/notificationDaemon.js`]

For a single-file script the user runs directly, that is disqualifying. Route B needs no
app id, no `.desktop`, and no `Gio.Application` -- and every single thing D-01..D-09 asks
for was **executed live against this machine's real daemon** and confirmed working.

**What Route A would have cost:** (1) install + maintain a `.desktop` in
`~/.local/share/applications/` matching the app id, and the app must stay findable by
`Shell.AppSystem` -- a second install artifact for a script that currently has none;
(2) restructure the bare `Gtk.main()` at `:1817` into a `Gio.Application` subclass with
`activate`/`startup` handlers; (3) register `GSimpleAction`s, whose invocation round-trips
through `app.activate_action()` -- i.e. **D-Bus activation of our own process via the
`.desktop`** (`notificationDaemon.js:510-518`), adding a whole second RPC surface. All of
that to obtain strictly *less* than Route B: the Gtk route exposes no `resident` hint and
no `replaces_id` -- only `priority` and an app-scoped notification id string.

Residual risk: **one** item could not be verified without a human hand -- the end-to-end
mouse click producing `ActionInvoked`. Everything up to and including the daemon's
`_emitActionInvoked` code path and the signal *delivery thread* is verified (see Q3).
That click is UAT material, and it is called out in Validation Architecture.

---

## Summary

The phase's load-bearing decision is settled by direct evidence, not inference. This
machine runs **GNOME Shell 46.0 on X11**, and GNOME Shell *is* the notification daemon --
`GetNameOwner(org.freedesktop.Notifications)` and `GetServerInformation()` both confirm it
[VERIFIED: `gdbus call`]. That means the daemon's behavior is not a matter of spec
interpretation: its source ships inside `libshell-14.so` and can be read.

Reading it settles two things that the freedesktop spec would have gotten **wrong**:

1. **GNOME Shell ignores `expire_timeout` entirely.** The 8th `Notify` argument is
   destructured as `timeout_` -- the trailing-underscore "deliberately unused" convention
   -- and never read again. Banner lifetime is a hardcoded `NOTIFICATION_TIMEOUT = 4000`
   ms. Any plan that reaches for `expire_timeout=0` vs `-1` to implement D-02 is building
   on a knob that is not connected to anything.
2. **The knob that actually works is `urgency`.** `urgency=2` (CRITICAL) causes the banner
   timeout to never be armed, so it persists until dismissed or clicked. `urgency=1`
   (NORMAL) gets the 4s banner and then slides into GNOME's notification list. That is
   D-02, exactly, with no `resident` hint involved -- and `resident` would in fact be
   *wrong* here (it means "survive being clicked", not "survive on screen").

Everything else fell out cleanly: `replaces_id` returns the same id and overwrites in
place (D-03); emitting from a non-main thread works; D-Bus signals are delivered on the
**Gtk main thread**, so the click handler needs no `GLib.idle_add` marshaling at all
(simplifying D-09); and an absent daemon surfaces as a catchable `GLib.Error` at *call*
time, never at construction time (NOTIF-04).

The `project()` port is mechanical. The JS at `:931` was transcribed to Python and 10
input/output cases pass, including the ones the planner would otherwise have to discover
the hard way (negative elapsed fraction from clock skew, expired window clamping, an
exhaust time landing in the past).

**Primary recommendation:** Route B. One `Gio.DBusProxy` built on the Gtk main thread in
`Monitor.__init__`, one `notify()` helper using async `proxy.call()` (safe from both
threads), `urgency` 2/1 for waiting/done, `replaces_id` from a per-session slot dict, one
`g-signal` handler filtering `ActionInvoked` by id.

## Project Constraints (from CLAUDE.md)

Extracted from `./.claude/CLAUDE.md` and the user's global `CLAUDE.md`. Research honors
all of these; any plan that violates one is invalid.

| Directive | Source | Effect on this phase |
|-----------|--------|----------------------|
| **ASCII only** -- no Unicode in code or output. `->` not an arrow glyph, `+/-` not the sign | global CLAUDE.md, "Response style" | Notification body/title strings must be ASCII. D-08's example body `"Projected 140% at reset -- runs out ~16:20"` uses `--`, which is fine. Watch the em-dash habit. |
| **Prefer minimal changes that solve the request** | global CLAUDE.md, "Workflow" | Reinforces Route B: no `Gio.Application` restructuring, no `.desktop` install. |
| **codedoc comment style** -- Python uses triple-quoted docstrings for prose blocks; `#` reserved for short annotations | global CLAUDE.md, "Code comments" | The emit helper, the port, and the arm-state functions all get docstrings, matching every existing function in `claude-monitor.py`. |
| **GSD workflow enforcement** -- no direct repo edits outside a GSD workflow | project `.claude/CLAUDE.md` | Implementation happens under `/gsd-execute-phase`, not ad hoc. |
| **`ponytail:` comments mark deliberate simplifications with their ceiling** | project convention, observed at `:1608`, `:1734` | The known ceilings in this phase (MAX_NOTIFICATIONS_PER_SOURCE=3, the deliberate JS/Python `project()` duplication) each want one. |
| **stdlib + PyGObject only, no new dependencies** | `.planning/PROJECT.md` | Route B uses only `gi.repository.Gio` / `GLib`, both already available via the existing `import gi`. `Gio` is a **new import line**, not a new dependency. |
| **X11 only, GTK3, one background poll, nothing blocking the Gtk main loop** | `.planning/PROJECT.md` | Drives the async-`call()` choice in the emit helper. |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Notification emit (D-Bus RPC) | Session bus / GNOME Shell | -- | The daemon owns rendering, lifetime, and the message list. We hand it a message; we do not draw anything. |
| Replace-in-place slot bookkeeping | Python process state (`Monitor`) | -- | The daemon gives us an id; only we know which session it belongs to. |
| De-dupe (emit only on state *change*) | Python, `Monitor.handle` (Gtk main thread) | -- | The transition is observable only where old and new status meet. Pure function, assertable. |
| Alert arm / re-arm state | Python, `poll_loop` (worker thread) | -- | Rides the existing poll tick per PROJECT.md; no new polling. |
| Projection arithmetic | Python (poll thread) **and** JS (browser) | -- | Deliberate duplication: the JS copy recomputes against a live browser clock; the Python copy runs on the poll tick. |
| Click action dispatch | GNOME Shell -> D-Bus signal -> Gtk main thread | -- | **Verified**: the signal lands on the Gtk main thread, so `focus()` / `open_dashboard` run exactly where the existing menu handlers already run. |
| Mute gate | Python, inside the shared emit path | Phase 6 config | Phase 5 ships the seam only. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `gi.repository.Gio` | ships with PyGObject (already installed) | `Gio.DBusProxy`, `Gio.DBusCallFlags`, `Gio.BusType` | The stdlib-adjacent way to speak D-Bus from PyGObject. Zero new dependencies -- satisfies NOTIF-01's *intent* ("PyGObject, no new dependency") without its literal `Gio.Notification` phrasing. [VERIFIED: `python3 -c "from gi.repository import Gio"` succeeds in this env] |
| `gi.repository.GLib` | already imported at `:31` | `GLib.Variant` for the `Notify` signature, `GLib.Error` for the failure guard | Already in the file. |

**Installation:** none. The only source change is extending the existing import at `:31`:

```python
from gi.repository import GLib, Gio, Gtk
```

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `Gio.DBusProxy` + fdo spec (Route B) | `Gio.Application` + `Gio.Notification` (Route A) | **Rejected.** Hard-requires an installed `.desktop`; requires restructuring `Gtk.main()`; exposes no `replaces_id` and no `resident`. See The Verdict. |
| `Gio.DBusProxy` | `notify-send` subprocess | **Rejected.** A `subprocess` shell-out on the Gtk main thread is exactly what PROJECT.md forbids, and `notify-send` gives no id back (no D-03) and no action callback (no NOTIF-03). |
| `Gio.DBusProxy` | `notify2` / `dbus-python` / `plyer` | **Rejected.** New dependencies. Forbidden by PROJECT.md. |

## Package Legitimacy Audit

**Not applicable -- this phase installs no external packages.** The stack is
`gi.repository.Gio`, which ships with the already-installed PyGObject. No registry lookup
is required because nothing is fetched from a registry. [VERIFIED: `import gi` already
present at `claude-monitor.py:26`; `Gio` importable in this environment]

---

## THE BINDING: evidence table

Environment, established first, because every answer below is machine-specific:

```
$ gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
    --method org.freedesktop.DBus.GetNameOwner org.freedesktop.Notifications
(':1.47',)

$ gdbus call --session --dest org.freedesktop.Notifications \
    --object-path /org/freedesktop/Notifications \
    --method org.freedesktop.Notifications.GetServerInformation
('gnome-shell', 'GNOME', '46.0', '1.2')          <-- the daemon IS gnome-shell

$ ... GetCapabilities
(['actions', 'body', 'body-markup', 'icon-static', 'persistence', 'sound'],)

XDG_SESSION_TYPE=x11   XDG_CURRENT_DESKTOP=ubuntu:GNOME   GNOME Shell 46.0
```
[VERIFIED: `gdbus call` against the live session bus]

`actions` **is** advertised -- so Route B's click actions are supported by this daemon, not
merely by the spec. `persistence` is advertised -- notifications survive into the message
list. [VERIFIED: matches `GetCapabilities()` in `notificationDaemon.js:273-286`]

Because the daemon is gnome-shell, its source is authoritative and readable:

```bash
gresource extract /usr/lib/gnome-shell/libshell-14.so \
  /org/gnome/shell/ui/notificationDaemon.js
gresource extract /usr/lib/gnome-shell/libshell-14.so \
  /org/gnome/shell/ui/messageTray.js
```
All `[VERIFIED: gnome-shell 46.0 source]` claims below cite those two files.

---

### Q1 -- D-03: replace-in-place ids

| Route | Verdict |
|-------|---------|
| **Route B** | **SATISFIED.** |
| Route A | Satisfied-with-caveats (different mechanism, weaker). |

**Route B mechanism:** the 2nd `Notify` argument, `replaces_id` (`u`). Pass `0` for a new
notification; `Notify` **returns the allocated `u` id**. Pass that id back as
`replaces_id` on the next emit for the same session and the daemon reuses the same
notification object in place.

```js
// notificationDaemon.js:162-179
let source, notification;
if (replacesId !== 0 && this._notifications.has(replacesId)) {
    notification = this._notifications.get(replacesId);   // <-- same object
    source = notification.source;
    id = replacesId;                                      // <-- same id returned
} else {
    id = this._nextNotificationId++;                      // <-- new slot
    ...
}
```
[VERIFIED: gnome-shell 46.0 source]

Executed live on this machine:

```
Q1: first Notify   -> id=14
Q1: replace Notify -> id=14  (same as first? True)
```
[VERIFIED: live probe against the running daemon]

So: N live sessions -> at most N popups, ever. Exactly D-03.

**Two consequences the planner must not miss:**

- **Always store the id `Notify` returns, every time.** When a notification is clicked (and
  is not `resident`), the daemon **destroys** it and drops it from `_notifications`
  (`notificationDaemon.js:180-181`, `messageTray.js:470-473`). A later `Notify` with that
  now-stale `replaces_id` falls into the `else` branch and allocates a **fresh id**. That
  is correct behavior -- but only if we overwrite our stored slot with the returned value
  rather than assuming it stayed constant. [VERIFIED: gnome-shell 46.0 source]
- **`MAX_NOTIFICATIONS_PER_SOURCE = 3`** (`messageTray.js:28`, enforced at `:563-566`). All
  our notifications share one source (our pid). Beyond 3 retained notifications the daemon
  destroys the oldest with reason `EXPIRED`. Banners still display; only the *message-list
  backlog* is capped. Harmless here, but it is a real ceiling and wants a `ponytail:`
  comment. [VERIFIED: gnome-shell 46.0 source]

**Route A mechanism:** `Gio.Application.send_notification(id_string, notification)` --
replacement is keyed on the caller-chosen **string** id, and `withdraw_notification()`
removes it. The daemon side (`GtkNotificationDaemonAppSource.addNotification`,
`notificationDaemon.js:526-540`) destroys any existing notification with the same id with
reason `REPLACED`. It would work -- *if the `.desktop` existed*. It does not.
[VERIFIED: gnome-shell 46.0 source]

---

### Q2 -- D-02: divergent lifetimes (the big spec divergence)

| Route | Verdict |
|-------|---------|
| **Route B** | **SATISFIED -- but via `urgency`, NOT via `expire_timeout`.** |
| Route A | Satisfied-with-caveats (`Gio.NotificationPriority.URGENT` -> CRITICAL), moot given Q4. |

**LOUD FINDING #1 -- GNOME Shell ignores `expire_timeout` completely.**

The freedesktop spec says `expire_timeout` is milliseconds; `0` means never expire; `-1`
means "daemon default". **GNOME Shell reads none of it.** The 8th `Notify` parameter is
destructured and immediately abandoned:

```js
// notificationDaemon.js:138
let [appName, replacesId, appIcon, summary, body, actions, hints, timeout_] = params;
//                                                                  ^^^^^^^^
//                             trailing underscore = deliberately unused. Never read again.
```
[VERIFIED: gnome-shell 46.0 source -- `timeout_` appears exactly once in the file]

Banner lifetime is instead a **hardcoded constant**:

```js
// messageTray.js:22
const NOTIFICATION_TIMEOUT = 4000;

// messageTray.js:1185-1188
_showNotificationCompleted() {
    if (this._notification.urgency !== Urgency.CRITICAL)
        this._updateNotificationTimeout(NOTIFICATION_TIMEOUT);   // 4s, always
}
```
[VERIFIED: gnome-shell 46.0 source]

**Any plan that implements D-02 by choosing `expire_timeout=0` vs `-1` is wiring a knob to
nothing.** Both values produce identical behavior. This is precisely the class of thing
that turns into a rewrite during UAT, which is why it is flagged here.

**LOUD FINDING #2 -- `urgency` is the real knob, and it maps onto D-02 exactly.**

```js
// notificationDaemon.js:27-31          // messageTray.js:1185-1188 & 1072-1076
const Urgency = { LOW: 0, NORMAL: 1, CRITICAL: 2 };
```

| `urgency` | GNOME Shell 46 behavior | D-02 mapping |
|-----------|-------------------------|--------------|
| `0` LOW | **No banner at all.** `_onNotificationRequestBanner` returns early (`messageTray.js:911-912`). Goes straight to the message list. | unused |
| `1` NORMAL | Banner shown, 4s timeout armed, then auto-hides into GNOME's notification list (`persistence` capability). | **`done`** -- "auto-expire on the daemon's normal timeout into GNOME's notification list". Exact match. |
| `2` CRITICAL | **No timeout is ever armed** (`_showNotificationCompleted` skips it), and CRITICAL is explicitly excluded from the `expired` condition in `_updateState` (`messageTray.js:1075`). The banner persists until dismissed or clicked. Also auto-expands, and shows even when `policy.showBanners` is false (`messageTray.js:914`). | **`waiting`** -- "persist on screen until dismissed or clicked". Exact match. |

[VERIFIED: gnome-shell 46.0 source]

Confirms the freedesktop `urgency=2 => never auto-expire` semantic *does* hold on GNOME
Shell -- it is the one part of the spec the shell honors, and it is implemented as
"never arm the timer" rather than "use a longer timer".

**LOUD FINDING #3 -- `resident` is NOT what D-02 wants.**

D-02's parenthetical says "resident / critical urgency, or the equivalent hint". Those are
not equivalents, and `resident` is the wrong one. `resident` does not affect on-screen
lifetime *at all*. It means: **when the user clicks/activates the notification, do not
destroy it.**

```js
// messageTray.js:466-473  (activate)
// We don't hide a resident notification when the user invokes one of its actions,
// because it is common for such notifications to update themselves with new
// information based on the action.
if (this.resident)
    return;
this.destroy();
```
[VERIFIED: gnome-shell 46.0 source]

For this phase we **want** `resident` false (its default): clicking a `waiting`
notification should focus the pane and make the popup go away. Setting `resident=true`
would leave a clicked notification stuck in the list. **Do not set the `resident` hint.**

**The lifetime answer, then, is one hint and nothing else:**

```python
# waiting -> sticks until dismissed/clicked
hints = {"urgency": GLib.Variant("y", 2)}      # CRITICAL
# done -> 4s banner, then into GNOME's notification list
hints = {"urgency": GLib.Variant("y", 1)}      # NORMAL
# expire_timeout: pass -1 and ignore it. GNOME Shell does.
```

---

### Q3 -- NOTIF-03 / D-09: click actions routing back into Python

| Route | Verdict |
|-------|---------|
| **Route B** | **SATISFIED.** |
| Route A | NOT SATISFIED without a `.desktop` (see Q4). |

**What delivers the click:** the `ActionInvoked(u id, s action_key)` D-Bus **signal**,
received through the proxy's `g-signal` GObject signal.

**The "clicked the body itself" case is the `"default"` action key** -- and it only works
if `"default"` is present in the `actions` array you pass to `Notify`:

```js
// notificationDaemon.js:213-238
let hasDefaultAction = false;
if (actions.length) {
    for (let i = 0; i < actions.length - 1; i += 2) {
        let [actionId, label] = [actions[i], actions[i + 1]];
        if (actionId === 'default') {
            hasDefaultAction = true;          // consumed, NOT rendered as a button
        } else {
            notification.addAction(label, () => {         // rendered as a button
                this._emitActivationToken(source, id);
                this._emitActionInvoked(id, actionId);
            });
        }
    }
}
if (hasDefaultAction) {
    notification.connect('activated', () => {             // <-- body click
        this._emitActivationToken(source, id);
        this._emitActionInvoked(id, 'default');
    });
} else {
    notification.connect('activated', () => {
        source.open();                        // <-- fallback: tries to launch the app
    });
}
```
[VERIFIED: gnome-shell 46.0 source]

So: `actions = ["default", "Focus"]` gives a body-clickable notification with **no extra
button** (the `default` entry's label is never rendered). That is the shape this phase
wants -- click the popup, focus the pane. Omitting `"default"` means a body click falls
through to `source.open()`, which tries to activate our app and does nothing useful.
**`"default"` must be present.**

**LOUD FINDING #4 -- `ActionInvoked` is a BROADCAST. You must filter by id.**

```js
// notificationDaemon.js:302-305
_emitActionInvoked(id, action) {
    this._dbusImpl.emit_signal('ActionInvoked',
        GLib.Variant.new('(us)', [id, action]));     // no destination -> broadcast
}
```
[VERIFIED: gnome-shell 46.0 source]

Our proxy on `/org/freedesktop/Notifications` receives `ActionInvoked` for **every fdo
notification from every app on the session**. The handler must look the id up in our own
slot table and ignore anything it does not own. A handler that acts on any `ActionInvoked`
will focus a tmux pane when the user clicks a Slack notification.

**On which thread does the callback arrive: the Gtk main thread.** This is the answer that
*simplifies* D-09 -- no marshaling is needed.

`NotificationClosed` and `ActionInvoked` travel the identical broadcast path
(`_emitNotificationClosed` / `_emitActionInvoked`, adjacent functions, same `emit_signal`
mechanism), so a live probe on `NotificationClosed` establishes the delivery thread for
both without needing a human to click:

```
main thread name = MainThread
worker(pollthread): emitted a=17 b=18
SIGNAL NotificationClosed   thread=MainThread   ON_MAIN=True params=(17, 3)
SIGNAL NotificationClosed   thread=MainThread   ON_MAIN=True params=(18, 3)
```
[VERIFIED: live probe -- notifications emitted from a worker thread, closed from that
worker thread, signals delivered on `MainThread`]

**Why**, and the trap it implies: `Gio.DBusProxy` captures the **thread-default main
context at construction time** and dispatches all its signals and async callbacks there.
Construct the proxy on the Gtk main thread (in `Monitor.__init__`) and every `g-signal`
lands on the Gtk main thread, where `Monitor.focus()` and `Monitor.open_dashboard` already
run today from menu handlers.

> **Trap:** if the proxy were instead constructed inside `poll_loop`, its signals would be
> dispatched into that thread's default main context -- which has **no running main loop**.
> `ActionInvoked` would then never fire, silently. Construct the proxy on the Gtk main
> thread. [VERIFIED: GDBus main-context semantics, confirmed by the probe above]

D-09's note -- *"the click handler must marshal onto the Gtk main thread if the action
arrives on a D-Bus worker"* -- is therefore satisfied **for free**. It does not arrive on a
worker. No `GLib.idle_add` in the click path.

Note `focus()` shells out with `subprocess.run` on the Gtk main thread. That is already
exactly what the existing `on_click` menu handler does (`:1472-1475`), so this introduces
no new blocking that the codebase does not already accept. Precedent holds.

---

### Q4 -- no new dependency, no `.desktop` install

| Route | Verdict |
|-------|---------|
| **Route B** | **SATISFIED.** No app id, no `.desktop`, no `Gio.Application`. |
| Route A | **NOT SATISFIED. This is the disqualifier.** |

**Does `Gio.Notification` require a `Gio.Application` with a valid app id?** Yes. It is
sent via `Gio.Application.send_notification()`, which requires a registered application
with an id passing `Gio.Application.id_is_valid()`. There is no `Gio.Application` anywhere
in `claude-monitor.py` -- `:1817` is a bare `Gtk.main()`. [VERIFIED: codebase read;
`grep` for `Gio.Application` returns nothing]

**Does GNOME Shell require a matching installed `.desktop` for the notification to appear
at all?** **Yes -- and this is fatal.** Not merely for actions to route back: for the
notification to exist.

```js
// notificationDaemon.js:487-495
export const GtkNotificationDaemonAppSource = GObject.registerClass(
class GtkNotificationDaemonAppSource extends MessageTray.Source {
    constructor(appId) {
        if (!Gio.Application.id_is_valid(appId))
            throw new InvalidAppError();
        const app = Shell.AppSystem.get_default().lookup_app(`${appId}.desktop`);
        if (!app)
            throw new InvalidAppError();
        ...

// notificationDaemon.js:643-657  -- what happens when it throws
AddNotificationAsync(params, invocation) {
    let [appId, notificationId, notificationSerialized] = params;
    let source;
    try {
        source = this._ensureAppSource(appId);
    } catch (e) {
        if (e instanceof InvalidAppError) {
            invocation.return_error_literal(NotificationErrors,
                NotificationError.INVALID_APP,
                `The app by ID "${appId}" could not be found`);
            return;                          // <-- notification DROPPED
        }
        throw e;
    }
```
[VERIFIED: gnome-shell 46.0 source]

**What happens if the `.desktop` is missing:** the `org.gtk.Notifications.AddNotification`
call returns a D-Bus **error**. The notification is dropped. Because `send_notification()`
is fire-and-forget on the client side, the app typically sees **nothing** -- the failure is
effectively silent from Python's perspective. That is the worst possible failure mode: no
popup, no exception, no clue.

Separately, Route A's **actions** route back via
`this._app.activate_action(actionId, params, ...)` (`notificationDaemon.js:510-518`) --
a D-Bus activation of *our own process* looked up through the `.desktop`. Even with a
`.desktop` present, that requires the app to be D-Bus-activatable and exporting its action
group. More plumbing, more failure surface.

**Weighing the "single-file script the user runs directly" reality:** this app is launched
from `~/.config/autostart`, lives at `~/.claude/hooks/claude-monitor.py`, and has no
install step. Route A would add a *second install artifact* that must stay in sync with an
app id string, and whose absence silently disables the entire feature. Route B adds one
import line.

---

### Q5 -- NOTIF-04: degrade silently when the daemon is absent or failing

| Route | Verdict |
|-------|---------|
| **Route B** | **SATISFIED. Catchable `GLib.Error` at call time.** |
| Route A | Silent drop with no client-side signal -- *worse* for diagnosis, though it also does not crash. |

Probed directly by pointing a proxy at a name nobody owns:

```
--- failure surface: name with NO owner, auto-start ALLOWED ---
  construction: OK (no raise), get_name_owner() -> None
  call_sync RAISES: type=Error domain=g-dbus-error-quark code=2
  message: GDBus.Error:org.freedesktop.DBus.Error.ServiceUnknown:
           The name org.freedesktop.NotificationsABSENT was not provided by any .service files
  -> is GLib.Error an Exception subclass? True
```
[VERIFIED: live probe]

**The concrete failure surface to wrap:**

| Stage | Behavior with no daemon | Guard |
|-------|------------------------|-------|
| `Gio.DBusProxy.new_for_bus_sync(...)` | **Does NOT raise.** Returns a live proxy object whose `get_name_owner()` is `None`. | Still wrap it: if the **session bus itself** is unreachable (no `DBUS_SESSION_BUS_ADDRESS`, e.g. under a bare TTY or a stripped systemd unit), *this* call raises `GLib.Error`. Catch -> `self.notif_proxy = None` -> every emit becomes a no-op. |
| `proxy.call(...)` / `call_sync(...)` | **Raises `GLib.Error`**, domain `g-dbus-error-quark`, `org.freedesktop.DBus.Error.ServiceUnknown`. | `GLib.Error` **is an `Exception` subclass** [VERIFIED: probe], so the codebase's existing `except Exception` posture catches it with no special-casing. |
| async `proxy.call(...)` callback | The error surfaces inside `call_finish(res)` in the callback. | The callback must have its own `try/except` -- an unhandled raise inside a GLib callback prints a traceback and can kill the source. |

This is a strictly *better* failure surface than Route A's silent drop, and it slots
directly into the file's established "total tolerance at the edges" pattern.

---

### Q6 -- non-blocking on the Gtk main thread

| Route | Verdict |
|-------|---------|
| **Route B** | **SATISFIED.** `proxy.call()` (async) is safe to initiate from **both** threads. |

**Which call form is async:** `Gio.DBusProxy.call()` is asynchronous (returns immediately,
result delivered to a callback). `Gio.DBusProxy.call_sync()` **blocks** on a bus round-trip
to gnome-shell.

**Is the emit safe from a non-main thread (`poll_loop`)?** Yes -- verified directly:

```
Q4: notify from thread worker -> id=16 (no crash)          # call_sync from a worker thread
Q4: async callback on thread=MainThread -> (16,)           # call() from worker, cb on main
```
[VERIFIED: live probe -- both `call_sync` and `call` invoked from a non-main daemon thread]

GDBus is thread-safe; you may *initiate* a call from any thread. The **callback**, however,
is always dispatched on the proxy's construction-time main context -- the Gtk main thread.

**The recommended shape, and why it needs no thread branching:**

| Caller | Thread | Form |
|--------|--------|------|
| `Monitor.handle` (SESS producer) | Gtk main thread | `proxy.call()` -- **must** be async. `call_sync()` here would block the Gtk main loop on a bus round-trip, violating PROJECT.md. |
| `poll_loop` (ALERT producer) | daemon worker thread | `proxy.call()` -- async works fine here too. |

Use `proxy.call()` **everywhere**. One code path, no `threading.current_thread()` checks,
correct on both threads. The returned id arrives in the callback, which always runs on the
Gtk main thread -- so the slot dict is only ever mutated from one thread, which
incidentally makes the whole thing free of locking.

> `Gio.DBusProxy.new_for_bus_sync()` in `Monitor.__init__` **does** block briefly (one bus
> round-trip, sub-millisecond) at startup, on the Gtk main thread. That is a one-time cost
> before `Gtk.main()` even runs. Acceptable, and it is what buys the correct signal
> dispatch context.

---

## Code Examples

### The chosen route, minimal and complete (ASCII only, matching this codebase's style)

```python
# --- module level, near the other constants -------------------------------------
NOTIF_BUS = "org.freedesktop.Notifications"
NOTIF_PATH = "/org/freedesktop/Notifications"
# GNOME Shell urgency levels (notificationDaemon.js). CRITICAL is the ONLY thing that
# makes a banner persist -- expire_timeout is destructured as `timeout_` and never read,
# so it is dead weight on this daemon. Pass -1 and do not think about it again.
URGENCY_NORMAL = 1     # 4s banner -> GNOME's notification list (SESS-02 "done")
URGENCY_CRITICAL = 2   # no timeout armed; sticks until dismissed/clicked (SESS-01 "waiting")


def notif_allowed(kind):
    """Mute gate (NOTIF-02 seam). Phase 6 wires the config in HERE and nowhere else.

    `kind` is one of "waiting", "done", "5h", "7d". Phase 5 ships the seam open:
    every event fires. Phase 6 replaces the body with a config lookup (four per-event
    toggles plus a global mute) without touching a single call site.
    """
    return True  # ponytail: Phase 6 (CFG-01/02) replaces this body. Seam only.
```

```python
    # --- in Monitor.__init__, ON THE GTK MAIN THREAD (this matters, see below) ----
    def __init__(self):
        ...
        self.notif_slots = {}   # key ("sess", sid) / ("cap", "5h") -> daemon notification id
        self.notif_acts = {}    # daemon notification id -> ("focus", pane, tmux) | ("dash",)
        self.notif = None
        try:
            # Constructed on the Gtk main thread ON PURPOSE: a GDBusProxy dispatches its
            # signals and async callbacks on the thread-default main context captured HERE.
            # Built on poll_loop instead, ActionInvoked would be posted to a context with no
            # running main loop and clicks would silently never arrive.
            #
            # This does NOT raise when the daemon is absent -- it returns a proxy whose
            # get_name_owner() is None, and the failure surfaces later at call time as a
            # GLib.Error. It DOES raise if the session bus itself is unreachable (bare TTY),
            # which is what this guard is for: no bus -> self.notif stays None -> every emit
            # is a no-op and the tray runs on regardless (NOTIF-04).
            self.notif = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None,
                NOTIF_BUS, NOTIF_PATH, NOTIF_BUS, None,
            )
            self.notif.connect("g-signal", self.on_notif_signal)
        except Exception:
            self.notif = None  # degrade: no notifications, everything else keeps working
```

```python
    def emit_notif(self, key, kind, title, body, action, urgency):
        """Shared notification emit path (NOTIF-01). Safe from BOTH threads.

        Called from Monitor.handle (Gtk main thread) and from poll_loop (daemon thread).
        Uses the ASYNC proxy.call() in both cases: sync would block the Gtk main loop on a
        bus round-trip (PROJECT.md), and async is verified to work from a worker thread.
        The reply callback always lands on the Gtk main thread, so notif_slots/notif_acts
        are only ever mutated from one thread -- no lock needed.

        `key` names the notification SLOT (D-03): one slot per session, one per cap. Passing
        the slot's previous id as replaces_id makes the daemon overwrite that popup in place
        instead of stacking a second one. N live sessions -> at most N popups, ever.

        `action` is what a click should do, stashed against the returned id for
        on_notif_signal to dispatch (NOTIF-03 / D-09).
        """
        if self.notif is None or not notif_allowed(kind):
            return
        prev = self.notif_slots.get(key, 0)
        args = GLib.Variant(
            "(susssasa{sv}i)",
            (
                "claude-monitor",         # app_name
                prev,                     # replaces_id: 0 = new slot, else overwrite in place
                ICON,                     # app_icon
                title,                    # summary  (D-01: the project dir / D-08: the cap)
                body,                     # body     (D-01: the state / D-08: proj + exhaust)
                ["default", "Focus"],     # "default" = body click. Its label is never drawn;
                                          # omit it and a body click hits source.open() instead.
                {"urgency": GLib.Variant("y", urgency)},
                -1,                       # expire_timeout: IGNORED by GNOME Shell. Inert.
            ),
        )

        def done(proxy, res, _):
            try:
                nid = proxy.call_finish(res).unpack()[0]
            except Exception:
                return  # daemon vanished mid-call -> no popup this time (NOTIF-04)
            # ALWAYS re-store: a clicked notification is destroyed daemon-side, so the next
            # Notify with that stale id allocates a FRESH one. Assuming the id is stable
            # across a click is how you end up stacking duplicates.
            self.notif_slots[key] = nid
            self.notif_acts[nid] = action

        try:
            self.notif.call("Notify", args, Gio.DBusCallFlags.NONE, -1, None, done, None)
        except Exception:
            return  # degrade silently (NOTIF-04)

    def on_notif_signal(self, _proxy, _sender, signame, params):
        """D-Bus signal handler -- runs on the GTK MAIN THREAD (verified).

        No GLib.idle_add needed: GDBusProxy dispatches on the main context captured at
        construction. focus()/open_dashboard therefore run exactly where the existing menu
        handlers already run (Monitor.on_click, :1472).

        ActionInvoked is BROADCAST -- we see clicks on every app's notifications, not just
        ours. Filtering on notif_acts is what stops a click on someone else's popup from
        yanking a tmux pane into focus.
        """
        try:
            if signame == "ActionInvoked":
                nid = params[0]
                act = self.notif_acts.get(nid)   # not ours -> None -> ignored
                if act is None:
                    return
                if act[0] == "focus":
                    self.focus(act[1], act[2])   # NOTIF-03
                elif act[0] == "dash":
                    self.open_dashboard()        # D-09
            if signame in ("ActionInvoked", "NotificationClosed"):
                # Clicked or dismissed -> the daemon destroyed it. Drop our bookkeeping so
                # the next emit for this slot starts a clean notification.
                self.notif_acts.pop(params[0], None)
                for k, v in list(self.notif_slots.items()):
                    if v == params[0]:
                        del self.notif_slots[k]
        except Exception:
            return  # a raise here would run inside a GLib callback -- never let it escape
```

Call sites:

```python
# SESS-01/02, inside Monitor.handle (Gtk main thread), AFTER computing the new status:
if sess_should_notify(old_status, event):                     # pure fn, see below
    self.emit_notif(
        ("sess", sid), event,
        d,                                                    # D-01: dir is the title
        "Waiting for input" if event == "waiting" else "Session finished",
        ("focus", pane, tmux),                                # NOTIF-03
        URGENCY_CRITICAL if event == "waiting" else URGENCY_NORMAL,   # D-02
    )

# ALERT-02/03, inside poll_loop's per-tick body (daemon thread), after fetch_usage():
self.emit_notif(
    ("cap", "5h"), "5h",
    "5-hour quota",
    "Projected %d%% at reset -- runs out ~%s" % (round(p["proj"]), hhmm(p["exhaust"])),
    ("dash",),                                                # D-09
    URGENCY_NORMAL,
)
```

## Secondary Question 2: the `project()` port (ALERT-02/03, QUOTA-03 reuse)

The JS at `claude-monitor.py:931-948`, transcribed. **Exact semantics preserved.**

```python
# The 5h and 7d window lengths, in seconds. Same literals the dashboard JS uses
# (claude-monitor.py:746, `var WIN5=18000,WIN7=604800`).
WIN5 = 18000     # 5 hours
WIN7 = 604800    # 7 days


def project(pct, reset, win, now):
    """Percentage-based projection at window reset. Python port of the dashboard's
    project() (claude-monitor.py:931) -- QUOTA-03, reused for ALERT-02/03.

    The window began at reset-win, so the elapsed fraction e is known exactly;
    extrapolating the current pct linearly over the window gives the projected % at
    reset, and when that crosses 100 we can say WHEN it would land.

    Returns None (no data), {"early": True} (too soon to project), or
    {"proj": float} optionally carrying {"exhaust": epoch}.

    DELIBERATE DUPLICATION: the JS copy at :931 stays. It recomputes against a LIVE
    browser clock as the static page ages between regenerations, so it cannot be
    replaced by a value baked in from here. Same arithmetic, two clocks. If you change
    one, change the other, and update demo()'s assertions -- they pin both.
    """
    # seven_day_pct/seven_day_reset are None on an older CLI (parse_usage:119-120 lets
    # them through unguarded, unlike used_percentage/resets_at_epoch which are forced
    # numeric). Guard here so the 7d alert degrades silently, exactly like usage_rows.
    if not _is_num(pct) or not _is_num(reset):
        return None
    start = reset - win
    e = (now - start) / float(win)          # win is a nonzero constant -> no div-by-zero
    if e <= 0.05:
        return {"early": True}              # barely into the window -> pct/e explodes.
                                            # Also catches e < 0 (a reset epoch further out
                                            # than one full window: clock skew / stale data).
    if e > 1:
        e = 1.0                             # window already over -> proj degrades to pct
    out = {"proj": pct / e}
    if out["proj"] > 100 and pct > 0:       # pct > 0 guards the 100/pct below
        exh = start + (100.0 / pct) * (now - start)
        if exh < reset:
            out["exhaust"] = exh
    return out
```

**Edge cases, answered:**

| Edge | Behavior | Why it is safe |
|------|----------|----------------|
| Division by zero on `pct/e` | impossible | `e <= 0.05` returned early. |
| Division by zero on `100/pct` | impossible | guarded by `pct > 0`. |
| Division by zero on `/win` | impossible | `win` is a nonzero module constant. |
| `resets_at_epoch` in the **past** (`now > reset`) | `e > 1` -> clamped to `1.0` -> `proj == pct` | No crash. Projection degrades to "current pct", which is the truth for a finished window. |
| `resets_at_epoch` far in the **future** (> one window out; clock skew) | `e` is negative -> `e <= 0.05` -> `{"early": True}` | The early guard doubles as the skew guard. |
| `pct` / `reset` is `None` or a string | `None` | `_is_num` (`:508`). **This is the one place the Python port must be stricter than the JS** -- JS coerces, Python raises `TypeError`. `seven_day_*` is exactly this shape on an older CLI. |
| Expired window already over 100% | `exhaust` may land **in the past** | D-05's `exhaust - now >= 900` rejects it. **D-07 needs no special case and no code** -- confirmed. |

**A subtlety the planner must not trip on -- D-05's real predicate.**

`exhaust` is set only when `proj > 100` **strictly**. At `proj == 100.0` exactly there is no
`exhaust` key. So D-05's stated `proj >= 100 AND exhaust - now >= 15*60` has a redundant
first clause: the `exhaust` key cannot exist unless `proj > 100`. Writing both invites a
`KeyError` on the `proj == 100` boundary. The operative predicate is:

```python
ALERT_LEAD = 15 * 60   # D-05: a projection that says "you run out in 90 seconds" is not actionable

def alert_due(p, now):
    """Pure predicate for ALERT-02/03 (D-05). Assertable in --selfcheck."""
    return bool(p) and "exhaust" in p and (p["exhaust"] - now) >= ALERT_LEAD
```

That one expression carries D-05, D-07, and the `{"early": True}` suppression, because
`{"early": True}` has no `"exhaust"` key either.

**Test cases (all 10 executed and passing against the port):**
[VERIFIED: run locally, `python3 port.py` -> `port ok - all 10 cases`]

```python
R = 1_000_000; S = R - WIN5                     # reset epoch, window start
assert project(None, R, WIN5, S + 9000) is None
assert project(50.0, None, WIN5, S + 9000) is None
assert project("x", R, WIN5, S + 9000) is None                  # non-numeric -> None
assert project(50.0, R, WIN5, S + 900) == {"early": True}       # e == 0.05 exactly -> early
assert "proj" in project(50.0, R, WIN5, S + 901)                # e just over -> projects
assert project(50.0, R, WIN5, S - 5000) == {"early": True}      # negative e (clock skew)
p = project(50.0, R, WIN5, S + WIN5 // 2)                       # 50% at half window
assert abs(p["proj"] - 100.0) < 1e-9 and "exhaust" not in p     # exactly 100 -> NO exhaust
p = project(60.0, R, WIN5, S + WIN5 // 2)                       # 60% at half window
assert abs(p["proj"] - 120.0) < 1e-9
assert abs(p["exhaust"] - (S + 15000.0)) < 1e-6 and p["exhaust"] < R
assert abs(project(10.0, R, WIN5, S + WIN5 // 2)["proj"] - 20.0) < 1e-9   # coasting
p = project(42.0, R, WIN5, R + 3600)                            # window already over
assert abs(p["proj"] - 42.0) < 1e-9 and "exhaust" not in p
p = project(200.0, R, WIN5, R + WIN5 // 2)                      # expired AND over 100
assert p["proj"] == 200.0 and p["exhaust"] < R + WIN5 // 2      # exhaust in the PAST
assert not alert_due(p, R + WIN5 // 2)                          # -> D-05 rejects it (D-07)
assert project(0.0, R, WIN5, S + WIN5 // 2)["proj"] == 0.0      # pct 0, no div-by-zero
R7 = 2_000_000; S7 = R7 - WIN7                                  # same fn, 7d window
assert abs(project(80.0, R7, WIN7, S7 + WIN7 // 2)["proj"] - 160.0) < 1e-9
```

## Secondary Question 3: hardening `serve()` (NOTIF-04)

`serve()` (`:1699-1723`) has **no guard**. `poll_loop` got one from quick task `260713-fry`
(`:1770-1771`). Success Criterion 5 is exactly this gap.

**Where the guard goes is the whole question.** Three candidate placements, only one right:

| Placement | Result |
|-----------|--------|
| Around the whole `while True` loop (outside it) | **Wrong.** One bad connection still kills the thread -- the `except` catches, then falls out of the loop and the function returns. Identical to today. |
| Around `srv.accept()` only | **Wrong.** Hot-spin risk, and it does not cover the body where the raises actually live (`recv`, `json.loads` -- already guarded -- `looking_at`'s shell-outs, `idle_add`). |
| **Around the per-connection body, INSIDE the loop** | **Correct.** A bad connection costs that one connection; `accept()` comes back around for the next. This is structurally what `poll_loop` does (its `try` is inside the `while`, with `time.sleep` outside so a failing iteration cannot hot-spin). |

Matching the `poll_loop` precedent exactly:

```python
def serve(mon):
    """Socket thread: hook events -> Monitor.handle on the Gtk main thread.

    ponytail: the per-connection body is wrapped in a broad `except Exception` --
    mirroring poll_loop (:1770). This thread is the ONLY thing feeding session events, so
    ANY raise escaping one connection kills it permanently and the tray goes silently deaf
    to every session forever -- the same failure shape as the corrupt-record bug
    (260713-fry), and the whole point of NOTIF-04. The guard is INSIDE the while, around
    the connection body: one bad connection costs one connection, not the thread. Made
    OBSERVABLE, not silent: traceback.print_exc() puts the full traceback in the journal on
    every failing connection. accept() stays OUTSIDE the try -- a raise there is the socket
    itself dying (unrecoverable) and there is nothing useful to retry.
    """
    if os.path.exists(SOCK):
        os.unlink(SOCK)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCK)
    srv.listen(8)
    while True:
        conn, _ = srv.accept()
        try:
            try:
                buf = conn.recv(65536).decode("utf-8", "replace")
            finally:
                conn.close()
            for line in buf.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                # decide "already looking" here (background thread) so the xprop/tmux
                # shell-outs never block the Gtk main loop.
                if msg.get("event") in ("done", "waiting"):
                    msg["_onscreen"] = looking_at(msg.get("pane", ""), msg.get("tmux", ""))
                GLib.idle_add(mon.handle, msg)
        except Exception:
            traceback.print_exc()  # loud + repeated: the thread survives, the failure does not hide
            continue
```

Note the `conn.close()` `finally` is **preserved inside** the new guard -- wrapping the
whole body naively would be an easy way to leak file descriptors on a `recv` failure.

Also note: `Monitor.handle` now emits notifications, so it is a *new* source of raises --
but it runs on the Gtk main thread via `idle_add`, not on `serve()`'s thread. A raise there
kills the idle source, not the socket thread. `emit_notif`'s own guards cover it.

## Secondary Question 4: de-dupe / arm state as pure functions

Both required to be pure so `--selfcheck` can assert them (D-03, D-06, CONTEXT
"Claude's Discretion").

### SESS de-dupe (D-03, NOTIF-02)

**State shape:** none of its own. The old status is already in `self.sessions[sid]["status"]`
before `s.update(...)` overwrites it at `:1651`. The de-dupe is a comparison, not a store.

```python
def sess_should_notify(old_status, new_status):
    """True iff this is a state CHANGE into a notifiable state (NOTIF-02, D-03).

    Pure. A session sitting in `waiting` across many ticks re-sends `waiting` on every
    hook event; only a CHANGE emits. `running` and `end` never notify. old_status is None
    for a session seen for the first time -- a brand-new session that arrives already
    `waiting` IS a change and DOES notify.
    """
    return new_status in ("waiting", "done") and old_status != new_status
```

The one integration constraint: **capture `old = s.get("status")` BEFORE the `s.update(...)`
at `:1651`**, or the comparison is always false.

Note it deliberately does **not** consult `_onscreen` -- D-04.

### ALERT arm/re-arm (D-06, ALERT-04)

**State shape:** one dict on `Monitor`, `{cap_key: armed_reset_epoch}`, recording the reset
epoch of the window in which that cap last alerted. A cap is muted for the rest of a window
by remembering *which* window it fired in; a new `resets_at_epoch` is by definition a new
window, which re-arms it for free.

```python
def alert_should_fire(armed_reset, reset, p, now):
    """True iff this cap should alert now (D-05, D-06, ALERT-04). Pure.

    `armed_reset` is the resets_at_epoch of the window in which this cap last alerted
    (None if it never has). `p` is project()'s output.

    One alert per cap per window: once fired, armed_reset == reset suppresses the rest of
    that window even if the projection climbs further. When the window rolls, reset changes,
    armed_reset != reset, and the cap re-arms (ALERT-04) -- no explicit reset-detection
    code, no timer. No re-arm on the projection dipping under 100 and climbing back within
    the same window: that flaps around the boundary.
    """
    if not _is_num(reset):
        return False              # 7d cap absent on an older CLI -> degrade silently
    if armed_reset == reset:
        return False              # already alerted in THIS window
    return alert_due(p, now)      # D-05: exhaust exists AND >= 15min of lead time
```

Caller (in `poll_loop`, on fire: `self.alert_armed[cap] = reset`):

```python
for cap, pct, reset, win, title in (
    ("5h", u["used_percentage"], u["resets_at_epoch"], WIN5, "5-hour quota"),
    ("7d", u["seven_day_pct"],   u["seven_day_reset"], WIN7, "7-day quota"),
):
    p = project(pct, reset, win, now)          # None when the 7d block is absent
    if alert_should_fire(self.alert_armed.get(cap), reset, p, now):
        self.emit_notif(("cap", cap), cap, title,
                        "Projected %d%% at reset -- runs out ~%s"
                        % (round(p["proj"]), hhmm(p["exhaust"])),
                        ("dash",), URGENCY_NORMAL)
        self.alert_armed[cap] = reset          # arm: silent until this reset changes
```

`hhmm()` must be ported alongside (it is JS at `:930`); D-08 wants a local wall-clock time.
`time.strftime("%H:%M", time.localtime(exhaust))` is the stdlib one-liner.

### Assertion cases for `--selfcheck`

```python
# --- SESS de-dupe (D-03 / NOTIF-02) ---
assert sess_should_notify(None, "waiting")          # brand-new session, already waiting
assert sess_should_notify("running", "waiting")     # the transition that matters
assert sess_should_notify("waiting", "done")        # waiting -> done still notifies
assert not sess_should_notify("waiting", "waiting") # THE de-dupe: sitting in waiting
assert not sess_should_notify("done", "done")
assert not sess_should_notify("waiting", "running") # not a notifiable state
assert not sess_should_notify("done", "end")        # end never notifies

# --- ALERT arm / re-arm (D-05 / D-06 / D-07 / ALERT-04) ---
R = 1_000_000; S = R - WIN5
now = S + WIN5 // 2
hot = project(60.0, R, WIN5, now)                   # proj 120, exhaust = S+15000, 2500s out
cold = project(10.0, R, WIN5, now)                  # proj 20, coasting
assert alert_should_fire(None, R, hot, now)         # never armed + hot -> FIRE
assert not alert_should_fire(R, R, hot, now)        # already fired THIS window -> silent
assert alert_should_fire(R, R + WIN5, hot, now)     # window rolled -> RE-ARM (ALERT-04)
assert not alert_should_fire(None, R, cold, now)    # coasting -> nothing fires
assert not alert_should_fire(None, R, {"early": True}, now)   # early guard -> silent
assert not alert_should_fire(None, R, None, now)    # no data -> silent
assert not alert_should_fire(None, None, None, now) # 7d absent on old CLI -> silent
# D-05 lead time: exhaust 60s away is NOT actionable; 15min+ away IS.
soon = {"proj": 200.0, "exhaust": now + 60}
assert not alert_should_fire(None, R, soon, now)
assert alert_should_fire(None, R, {"proj": 200.0, "exhaust": now + 901}, now)
# D-07: an already-exhausted cap has an exhaust time in the PAST -> stays silent, no
# special case. This asserts the "no code" claim.
dead = project(200.0, R, WIN5, R + WIN5 // 2)
assert not alert_should_fire(None, R, dead, R + WIN5 // 2)
```

## Secondary Question 5: the mute gate hook (NOTIF-02 -> Phase 6)

**One function, one call site.** Shown in the code sketch above:

```python
def notif_allowed(kind):
    return True  # ponytail: Phase 6 (CFG-01/02) replaces this body. Seam only.
```

Called exactly once, at the top of `emit_notif` -- the single choke point every producer
already routes through. `kind` is one of the four event-type keys `"waiting"`, `"done"`,
`"5h"`, `"7d"`. The global mute (CFG-02) is a `return False` for all four, so it needs no
fifth key and no separate gate.

**Phase 5 builds nothing else.** No config file, no toggles, no persistence, no menu items.
Phase 6 replaces the function body and adds the menu -- and touches **zero** call sites,
which is the entire point of putting the gate inside the shared emit path rather than at
each producer.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Notification de-dup / replace | A "have I shown this already" cache keyed on content hash, or a timer that closes old popups | `replaces_id` + a slot dict | The daemon does it natively and atomically. A content cache gets the "clicked -> destroyed daemon-side" case wrong. |
| "Keep the waiting popup on screen" | A re-emit timer, or `expire_timeout=0` | `urgency=2` (CRITICAL) | `expire_timeout` is **inert** on GNOME Shell. A re-emit timer would fight the daemon and stack popups. |
| Marshaling the click back to the Gtk thread | `GLib.idle_add` in the `ActionInvoked` handler | nothing -- it already arrives there | Verified. The extra hop is dead code that also makes the failure mode harder to reason about. |
| Detecting a window reset for ALERT-04 | A timer, or comparing `now` against `reset` | Compare the stored `armed_reset` to the incoming `reset` | The reset epoch **is** the window identity. A changed epoch is a new window, definitionally. No clock math. |
| Projection / forecasting | An EWMA or least-squares forecaster | Port `project()` verbatim | Explicitly out of scope (REQUIREMENTS "Out of Scope"); a second forecaster is a competing source of truth. |
| Wall-clock formatting | Hand-rolled `hhmm` from `divmod` | `time.strftime("%H:%M", time.localtime(e))` | stdlib, and it is right about DST. |

**Key insight:** almost every "feature" this phase appears to need -- de-dupe, persistence,
lifetime, a notification list, click routing -- is already implemented *inside the daemon*.
The Python side's job is to pass the right two integers (`replaces_id`, `urgency`) and keep
a dict. Every line beyond that is re-implementing GNOME Shell.

## Common Pitfalls

### Pitfall 1: Implementing D-02 with `expire_timeout`
**What goes wrong:** `done` notifications never expire, or `waiting` notifications vanish
after 4 seconds -- the exact opposite of D-02, with no error anywhere.
**Why it happens:** the freedesktop spec says `expire_timeout` controls this, and every
tutorial on the internet says so. GNOME Shell does not read the parameter.
**How to avoid:** `urgency` 2 vs 1. Pass `expire_timeout=-1` and treat it as decoration.
**Warning signs:** any code comment reasoning about `0` vs `-1`.

### Pitfall 2: Constructing the `Gio.DBusProxy` on `poll_loop`
**What goes wrong:** notifications appear normally, but **clicks silently never fire**.
**Why it happens:** `Gio.DBusProxy` dispatches signals on the thread-default main context
captured at construction. On a worker thread that context has no running main loop, so
`ActionInvoked` is queued into a void.
**How to avoid:** construct it in `Monitor.__init__`, on the Gtk main thread.
**Warning signs:** popups work, NOTIF-03 does not, and there is no error to grep for.

### Pitfall 3: Acting on every `ActionInvoked`
**What goes wrong:** clicking a *Slack* notification focuses a tmux pane.
**Why it happens:** `ActionInvoked` is a broadcast on `/org/freedesktop/Notifications`.
Our proxy sees every app's clicks.
**How to avoid:** look the id up in `notif_acts`; return if absent.
**Warning signs:** the tray steals focus at times that correlate with nothing.

### Pitfall 4: Assuming a notification id is stable
**What goes wrong:** after a session's popup is clicked once, subsequent transitions for
that session **stack new popups** instead of replacing.
**Why it happens:** clicking destroys the notification daemon-side and removes it from
`_notifications`; a `Notify` with that stale `replaces_id` allocates a fresh id. If you
never re-read the return value, your slot dict holds a dead id forever.
**How to avoid:** write `notif_slots[key] = nid` on **every** reply, not just the first.
**Warning signs:** duplicates appear only after the user has interacted once.

### Pitfall 5: Setting the `resident` hint to make `waiting` persist
**What goes wrong:** the `waiting` popup does not stay on screen (that is `urgency`'s job),
*and* clicking it no longer dismisses it -- it sticks in the notification list.
**Why it happens:** `resident` means "survive activation", not "survive on screen". D-02's
own wording invites this mistake.
**How to avoid:** do not pass `resident`.

### Pitfall 6: Putting `serve()`'s guard around the `while` instead of inside it
**What goes wrong:** looks fixed, is not. One bad connection still kills the socket thread.
**How to avoid:** guard the per-connection body; keep `accept()` outside; keep the
`conn.close()` `finally` nested inside.
**Warning signs:** the test for Success Criterion 5 is "kill the daemon, keep working" --
but the *thread-death* bug only reproduces on a raise inside the body.

### Pitfall 7: Checking `proj >= 100` and then reading `p["exhaust"]`
**What goes wrong:** `KeyError` at exactly `proj == 100.0`.
**Why it happens:** the JS sets `exhaust` only when `proj > 100` **strictly**. D-05's prose
says `>= 100`.
**How to avoid:** the predicate is `"exhaust" in p`, which subsumes it.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `pynotify` / `notify2` Python bindings | `Gio.DBusProxy` against the fdo interface, or `Gio.Notification` | `pynotify` deprecated ~2012; `notify2` unmaintained | Both are new dependencies and forbidden here anyway. Most search results still recommend them. |
| `libnotify` via GObject Introspection (`gi.repository.Notify`) | `Gio.Notification` (upstream's preferred path) *or* raw D-Bus | GNOME has pushed `GNotification` since ~3.16 | `Notify` may not be installed (`gir1.2-notify-0.7`), so it is not a safe assumption for a zero-dependency script. Raw D-Bus needs nothing beyond PyGObject. [ASSUMED -- not probed; irrelevant to the verdict since it would be an added dependency either way] |
| Spec-conformant `expire_timeout` | GNOME Shell's hardcoded 4s + `urgency` | long-standing GNOME behavior | Documented above from source; treat all generic freedesktop tutorials on lifetime as wrong *for this desktop*. |

**Deprecated/outdated:** any guidance that reaches for `notify-send`, `notify2`, `pynotify`,
`plyer`, or `dbus-python` -- all violate the no-new-dependency constraint, and none of them
give back a notification id *and* an action callback *and* an urgency hint.

## Runtime State Inventory

Not a rename/refactor/migration phase -- this is additive feature work. Section included
only to record the one piece of *external* runtime state this phase touches:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **None.** No new file, no schema change. Notification slot ids and arm flags are in-memory only and are correctly lost on restart (a restart legitimately re-arms every cap). | none |
| Live service config | **GNOME Shell's own notification state.** Notifications we emit persist in GNOME's message list after our process exits, and GNOME persists `org.gtk.Notifications` sources across shell restarts (`_saveNotifications`, `notificationDaemon.js:630`) -- but **not** fdo ones, which are per-connection. Route B therefore leaves no residue. [VERIFIED: gnome-shell 46.0 source] | none |
| OS-registered state | **None.** Route B registers no D-Bus name, no `.desktop`, nothing. (Route A would have added a `.desktop` here -- another mark against it.) | none |
| Secrets/env vars | **None.** | none |
| Build artifacts | **None.** Single file, no packaging. | none |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Session D-Bus | the whole notification path | Yes | -- | `self.notif = None` -> emits are no-ops; tray fully functional (NOTIF-04) |
| `org.freedesktop.Notifications` owner | NOTIF-01 | Yes (`:1.47` = gnome-shell) | GNOME Shell 46.0 | `GLib.Error` at call time, caught; no popup, no crash |
| `actions` capability | NOTIF-03 / D-09 | Yes (advertised) | -- | none needed |
| `persistence` capability | D-02 (`done` -> notification list) | Yes (advertised) | -- | none needed |
| `gi.repository.Gio` | Route B | Yes | ships with PyGObject | none needed -- no fallback exists, and none is required |
| X11 session | existing `wmctrl` / `xprop` focus path | Yes (`XDG_SESSION_TYPE=x11`) | -- | out of scope (PROJECT.md: X11 only) |

[VERIFIED: `gdbus call`, `python3 -c "from gi.repository import Gio"`, `echo $XDG_SESSION_TYPE`]

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none missing.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | none -- `assert`-based `demo()` at `claude-monitor.py:1033`, the established project convention |
| Config file | none |
| Quick run command | `python3 claude-monitor.py --selfcheck` |
| Full suite command | same (it is the whole suite) |

### Phase Requirements -> Test Map

| Req | Behavior | Test Type | Command | Exists? |
|-----|----------|-----------|---------|---------|
| ALERT-02/03 | `project()` port matches the JS, incl. all edge cases | unit (pure) | `--selfcheck` | Add to `demo()` |
| ALERT-02/03 | D-05 lead-time predicate (`alert_due`) | unit (pure) | `--selfcheck` | Add to `demo()` |
| ALERT-04 / D-06 | arm / re-arm on reset change (`alert_should_fire`) | unit (pure) | `--selfcheck` | Add to `demo()` |
| D-07 | exhausted cap stays silent with no special case | unit (pure) | `--selfcheck` | Add to `demo()` |
| NOTIF-02 / D-03 | de-dupe: emit only on state change (`sess_should_notify`) | unit (pure) | `--selfcheck` | Add to `demo()` |
| NOTIF-01 | emit body-shape (title/body strings are ASCII, non-empty) | unit (pure) | `--selfcheck` | Add to `demo()` -- factor the body strings into a pure `notif_body(...)` so they are assertable without a bus |

### What `--selfcheck` CANNOT assert (-> human UAT)

These need a live daemon and a live mouse. They are the UAT script:

1. **NOTIF-03 / D-09 -- the click.** The only claim in this research not verified
   end-to-end. Clicking a session popup focuses the tmux pane; clicking a quota popup opens
   the dashboard. (The daemon's `_emitActionInvoked` path and the delivery thread *are*
   verified; the human click is not.) **Highest-value UAT item.**
2. **D-02 -- `waiting` sticks, `done` expires.** Verified from the daemon's source, but not
   watched with human eyes on a real popup. Confirm the waiting banner is still on screen
   after ~30s and the done banner is gone in ~4s.
3. **D-03 -- replace-in-place across a real session's lifetime.** The id mechanism is
   verified live; what is not is the full `running -> waiting -> done` sequence producing
   exactly one popup slot per session. Watch for Pitfall 4 (stacking after a click).
4. **Success Criterion 5 -- `pkill -STOP gnome-shell` / mask the daemon**, confirm the tray
   keeps polling, rendering, and serving session events.
5. **serve() thread survival.** Send a malformed/hostile hook payload; confirm a traceback
   appears in the journal **and** the next well-formed event still arrives.

### Sampling Rate
- **Per task commit:** `python3 claude-monitor.py --selfcheck`
- **Phase gate:** `--selfcheck` green + the five UAT items above, on the live tray.

### Wave 0 Gaps
None -- `demo()` already exists and is the established home for exactly this kind of pure
assertion. No framework install, no new test file.

## Security Domain

Low-surface phase, but two items are real:

| ASVS | Applies | Control |
|------|---------|---------|
| V5 Input Validation | **yes** | `body-markup` **is advertised by this daemon** [VERIFIED: `GetCapabilities`], and `notificationDaemon.js:207` sets `useBodyMarkup: true` unconditionally [VERIFIED: source]. The notification **body is parsed as Pango markup.** Session `dir` comes from the hook's `cwd` -- attacker-influenced if a project directory is named `<b>x</b>`. Broken markup can cause the body to render wrong or be dropped. Mitigation: `GLib.markup_escape_text()` on any interpolated value (the `dir`), or keep the dir in the **title** (summary is *not* markup-parsed) and the fixed string in the body -- which is exactly what D-01 already specifies. **D-01's shape is accidentally the secure one; do not "improve" it by moving the dir into the body without escaping.** |
| V6 Cryptography | no | -- |
| V2/V3/V4 | no | Local session bus only; no auth surface. |

| Pattern | STRIDE | Mitigation |
|---------|--------|------------|
| Pango-markup injection via a crafted project directory name | Tampering | `GLib.markup_escape_text()` on interpolated body values; prefer the summary field |
| Acting on another app's `ActionInvoked` (broadcast signal) | Spoofing / Elevation | Filter by owned notification id (Pitfall 3). Without this, any app -- or any process able to emit on the bus -- can trigger a `wmctrl` focus change and a `tmux select-pane`. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `gi.repository.Notify` (libnotify GI bindings) may not be installed | State of the Art | **None.** Not on the chosen path; it would be a new dependency regardless, so it is excluded on constraint grounds, not on this assumption. |
| A2 | The human mouse click on a notification body produces `ActionInvoked` with key `"default"` | The Verdict, Q3 | **Low, but non-zero.** The daemon's code path is verified from source (`notificationDaemon.js:229-233`), the `actions` capability is advertised, and the signal *delivery thread* is verified live via `NotificationClosed` on the identical broadcast path. What is unverified is only that a physical click reaches `notification.emit('activated')`. If wrong, NOTIF-03/D-09 fail and the route would need `ActionInvoked` from an explicit **button** instead of the body (still Route B; a one-line change to the `actions` array). **Does not threaten the verdict** -- Route A cannot do this at all without a `.desktop`. Listed as UAT item 1. |

Everything else in this document is `[VERIFIED]` against either the live session bus or the
running daemon's own source. **The binding verdict rests on no `[ASSUMED]` claim.**

## Open Questions

1. **Notification icon** (CONTEXT: Claude's discretion)
   - What we know: the existing `ICON` constant (`:36`, default `"claude-desktop"`) is a
     themed icon name; the `app_icon` `Notify` parameter takes exactly that.
   - Recommendation: pass `ICON`. Free consistency with the tray, zero new config.

2. **More than 3 simultaneous session notifications**
   - What we know: `MAX_NOTIFICATIONS_PER_SOURCE = 3` -- the daemon destroys the oldest
     beyond 3 [VERIFIED: source]. Banners still show; only the retained message-list backlog
     is capped.
   - Recommendation: accept it, mark with a `ponytail:` comment naming the ceiling. Four
     simultaneously-waiting sessions is not the common case, and the tray rows remain the
     complete picture.

## Sources

### Primary (HIGH confidence)
- **The running notification daemon's own source**, extracted from the installed binary:
  `gresource extract /usr/lib/gnome-shell/libshell-14.so /org/gnome/shell/ui/notificationDaemon.js`
  and `.../messageTray.js` (GNOME Shell 46.0). Every `[VERIFIED: gnome-shell 46.0 source]`
  claim cites these.
- **Live D-Bus probes against the running session bus:** `GetNameOwner`,
  `GetServerInformation`, `GetCapabilities`, `Introspect` via `gdbus call`.
- **Two live PyGObject probes** executed against the real daemon, establishing:
  `replaces_id` returns the same id; emit works from a non-main thread; async callbacks and
  broadcast signals are delivered on the Gtk main thread; proxy construction for an absent
  name does not raise but `call` raises `GLib.Error` / `ServiceUnknown`; `GLib.Error` is an
  `Exception` subclass.
- **The codebase itself:** `claude-monitor.py` (`:931` `project()`, `:1033` `demo()`,
  `:1450` `focus()`, `:1468` `open_dashboard`, `:1636` `handle`, `:1699` `serve()`,
  `:1726` `poll_loop`, `:1817` `Gtk.main()`), and the `project()` port re-executed against
  10 test cases.

### Secondary (MEDIUM confidence)
- Freedesktop Desktop Notifications Specification 1.2 (the version this daemon reports) --
  used only to *frame* the questions. Where it conflicts with the daemon's source on
  `expire_timeout`, **the source wins and the spec is wrong for this desktop.**

### Tertiary (LOW confidence)
- None used. No claim in this document rests on a web search.

## Metadata

**Confidence breakdown:**
- **The binding verdict: HIGH** -- rests on the daemon's own source plus live probes, not on
  documentation or training knowledge.
- **Standard stack: HIGH** -- one import line from an already-present library.
- **Architecture (thread model, emit shape): HIGH** -- the delivery thread and cross-thread
  emit were executed, not reasoned about.
- **Pitfalls: HIGH** -- each is derived from a specific line of the daemon's source.
- **`project()` port: HIGH** -- transcribed from the JS in-repo and executed against 10 cases.
- **NOTIF-03 end-to-end click: MEDIUM** -- code path verified, physical click is UAT (A2).

**Research date:** 2026-07-13
**Valid until:** stable indefinitely for this machine. The one thing that could invalidate
the lifetime findings is a **GNOME Shell major-version upgrade** (47+), since
`NOTIFICATION_TIMEOUT` and the urgency handling are internal implementation, not API. If the
user upgrades GNOME and `waiting` popups stop sticking, re-extract `messageTray.js` and
re-read `_showNotificationCompleted`. The `.desktop` requirement (the verdict's basis) is
long-standing and structural -- it will not move.
