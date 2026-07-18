#!/usr/bin/env python3
"""Claude Code monitor: GNOME top-bar tray indicator.

Claude Code hooks push one-line JSON events to a unix socket:
    {event, session_id, cwd, message, pane, tmux}
event in {running, waiting, done, end}. Each session's status shows in the tray menu;
clicking one focuses its tmux pane and raises the Ghostty window. A poll thread also
tracks quota usage, appends history, alerts on projected exhaustion, and regenerates a
dashboard page.
"""

import json
import os
import pathlib
import socket
import subprocess
import tempfile
import threading
import time
import traceback
import webbrowser

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3 as AppIndicator
from gi.repository import GLib, Gio, Gtk

from claude_monitor import core
from claude_monitor import dashboard

SOCK = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "claude-monitor.sock")
# Theme icon name; override with CLAUDE_TRAY_ICON. "claude-desktop" ships with the app.
ICON = os.environ.get("CLAUDE_TRAY_ICON", "claude-desktop")
# WM_CLASS of your terminal, used to raise its window on click (X11 / wmctrl).
GHOSTTY_CLASS = os.environ.get("CLAUDE_TRAY_WM_CLASS", "com.mitchellh.ghostty")

# Seconds between polls (the CLI itself takes ~5-10s). Override: CLAUDE_TRAY_POLL_INTERVAL.
try:
    POLL_INTERVAL = int(os.environ.get("CLAUDE_TRAY_POLL_INTERVAL", "15"))
except ValueError:
    POLL_INTERVAL = 15  # bad env -> default

# lookup_app(appId + ".desktop") and drops the notification when none is installed.
NOTIF_BUS = "org.freedesktop.Notifications"
NOTIF_PATH = "/org/freedesktop/Notifications"
# gnome-shell 46 destructures Notify's expire_timeout and never reads it (banner life is
# a hardcoded 4000ms), so urgency is the only lifetime knob.
URGENCY_NORMAL = 1  # 4s banner, then GNOME's notification list
URGENCY_CRITICAL = 2  # no dismiss timer; sticks until clicked

PRUNE_INTERVAL = 6 * 3600  # opportunistic-prune cadence (seconds)
TREND_INTERVAL = 5 * 60  # trend recompute throttle in poll_loop (seconds)


class Monitor:
    def __init__(self):
        self.config = core.load_config()  # CFG-01..05: mute/per-event toggles + badge threshold
        self.sessions = {}  # session_id -> {dir,status,pane,tmux,cwd}
        self.usage = None  # latest parse_usage() dict, or None if unavailable
        self.usage_misses = 0  # consecutive failed polls; >= threshold -> unavailable
        self.trends = None  # cached trend row strings, or None (collecting state)
        self.dash_ready = False  # gates the menu item until the first dashboard write

        self.notif_slots = {}  # ("sess", sid) / ("cap", "5h") -> daemon notification id
        self.notif_acts = {}  # daemon notification id -> click-action tuple (focus | dash)
        self.alert_armed = {}  # cap -> reset epoch it last alerted in; lost on restart
        self.notif = None
        try:
            # MUST be built on the Gtk main thread: a GDBusProxy captures the thread-default
            # main context here, so one built on the poll thread never fires ActionInvoked.
            # The try covers an unreachable session bus (bare TTY, stripped systemd unit).
            self.notif = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION,
                Gio.DBusProxyFlags.NONE,
                None,
                NOTIF_BUS,
                NOTIF_PATH,
                NOTIF_BUS,
                None,
            )
            self.notif.connect("g-signal", self.on_notif_signal)
        except Exception:
            self.notif = None  # no bus -> no notifications; everything else keeps working

        self.ind = AppIndicator.Indicator.new(
            "claude-monitor", ICON, AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.menu = Gtk.Menu()
        self.ind.set_menu(self.menu)
        self.rebuild_menu()

    def focus(self, pane, tmux):
        if pane:
            env = dict(os.environ)
            if tmux:
                env["TMUX"] = tmux
            subprocess.run(
                ["tmux", "select-window", "-t", pane],
                env=env,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["tmux", "select-pane", "-t", pane], env=env, stderr=subprocess.DEVNULL
            )
        subprocess.run(["wmctrl", "-x", "-a", GHOSTTY_CLASS], stderr=subprocess.DEVNULL)

    # .resolve().as_uri() escapes spaces/special chars; string concat would not.
    def open_dashboard(self, *_):
        webbrowser.open(pathlib.Path(dashboard.DASH_PATH).resolve().as_uri())

    def emit_notif(self, key, kind, title, body, action, urgency):
        """Shared notification emit path, safe from both threads (async proxy.call()).
        `key` is the slot (one per session, one per cap): its previous id goes back as
        replaces_id, so the daemon overwrites that popup instead of stacking. `action` is
        stashed against the returned id for on_notif_signal.
        ponytail: gnome-shell retains only 3 per source; collapse into one summary if that
        ever bites.
        """
        if self.notif is None or not core.notif_allowed(kind, self.config):
            return
        prev = self.notif_slots.get(key, 0)
        args = GLib.Variant(
            "(susssasa{sv}i)",
            (
                "claude-monitor",  # app_name
                prev,  # replaces_id: 0 = new slot, else overwrite that popup in place
                ICON,  # app_icon
                title,  # summary: NOT Pango-parsed, so session-derived strings go HERE
                body,  # body: IS Pango-parsed
                ["default", "Focus"],  # "default" makes a body click emit ActionInvoked; the
                #  label is never drawn, but omitting it makes that click fall through.
                {"urgency": GLib.Variant("y", urgency)},  # the only hint we pass
                -1,  # expire_timeout: gnome-shell never reads it. Inert.
            ),
        )

        def done(proxy, res, _):
            try:
                nid = proxy.call_finish(res).unpack()[0]
            except Exception:
                return  # daemon vanished mid-call -> no popup this time
            # Re-store on EVERY reply: a clicked notification is destroyed daemon-side and
            # the next Notify gets a fresh id; keeping the dead one stacks popups.
            self.notif_slots[key] = nid
            self.notif_acts[nid] = action

        try:
            self.notif.call("Notify", args, Gio.DBusCallFlags.NONE, -1, None, done, None)
        except Exception:
            return  # degrade to "no popup", never a raise

    def on_notif_signal(self, _proxy, _sender, signame, params):
        """Notification click dispatcher. Runs on the Gtk main thread, so no idle_add.
        ActionInvoked is a BROADCAST: every app's notification clicks arrive here, so the
        notif_acts lookup must filter to ids we own before acting on one.
        """
        try:
            if signame == "ActionInvoked":
                act = self.notif_acts.get(params[0])
                if act is None:
                    return  # not one of ours -> ignore (broadcast signal)
                if act[0] == "focus":
                    self.focus(act[1], act[2])
                elif act[0] == "dash":
                    self.open_dashboard()
            if signame in ("ActionInvoked", "NotificationClosed"):
                # The daemon destroyed it; drop our bookkeeping so the next emit is clean.
                self.notif_acts.pop(params[0], None)
                for k, v in list(self.notif_slots.items()):
                    if v == params[0]:
                        del self.notif_slots[k]
        except Exception:
            return  # inside a GLib callback: a raise here can kill the signal source

    def on_click(self, s):
        s["acked"] = True
        self.rebuild_menu()
        self.focus(s["pane"], s["tmux"])

    def on_notif_toggle(self, item, key):
        """Shared CheckMenuItem "toggled" handler for the mute-all row and the four
        per-event rows -- they differ only in which config key `key` names. Same
        mutate/persist/redraw sequence apply_usage/handle/on_click already use.
        """
        self.config[key] = item.get_active()
        core.save_config(self.config)
        self.rebuild_menu()

    def on_threshold_toggle(self, item, val):
        # RadioMenuItem "toggled" fires for BOTH the item losing active state and the
        # item gaining it -- ignore the losing fire or usage_threshold gets written
        # twice per click, once to the old value.
        if not item.get_active(): return
        self.config["usage_threshold"] = val
        core.save_config(self.config)
        self.rebuild_menu()

    def notif_submenu(self):
        """Builds the "Notifications" submenu fresh from self.config every call (no
        incremental diffing, matching rebuild_menu's own full-teardown style): mute-all,
        then the four ordered event checkboxes.
        """
        sub = Gtk.Menu()

        mute = Gtk.CheckMenuItem.new_with_label("Mute all")
        mute.set_active(self.config["mute_all"])  # BEFORE connect: avoids a spurious
        mute.connect("toggled", self.on_notif_toggle, "mute_all")  # save+rebuild on every build
        sub.append(mute)
        sub.append(Gtk.SeparatorMenuItem.new())

        event_rows = (
            ("Waiting for input", "notify_waiting"),
            ("Session finished", "notify_done"),
            ("5-hour quota alert", "notify_5h"),
            ("7-day quota alert", "notify_7d"),
        )
        for label, key in event_rows:
            row = Gtk.CheckMenuItem.new_with_label(label)
            row.set_active(self.config[key])  # BEFORE connect, same reason as mute above
            row.connect("toggled", self.on_notif_toggle, key)
            sub.append(row)

        sub.append(Gtk.SeparatorMenuItem.new())
        threshold_item = Gtk.MenuItem.new_with_label("Badge threshold")
        threshold_menu = Gtk.Menu()
        group = None
        for val in core.THRESHOLD_CHOICES:  # fixed ascending order (D-05); never sorted/reversed
            radio = Gtk.RadioMenuItem.new_with_label_from_widget(group, "%d%%" % val)
            radio.set_active(self.config["usage_threshold"] == val)  # BEFORE connect
            radio.connect("toggled", self.on_threshold_toggle, val)
            threshold_menu.append(radio)
            group = radio
        threshold_item.set_submenu(threshold_menu)
        sub.append(threshold_item)

        return sub

    def rebuild_menu(self):
        for c in self.menu.get_children():
            self.menu.remove(c)
        if not self.sessions:
            mi = Gtk.MenuItem.new_with_label("No active Claude sessions")
            mi.set_sensitive(False)
            self.menu.append(mi)
        else:
            for s in self.sessions.values():
                mi = Gtk.MenuItem.new_with_label("%s  [%s]" % (s["dir"], s["status"]))
                mi.connect("activate", lambda _w, s=s: self.on_click(s))
                self.menu.append(mi)
        for row in self.usage_rows():
            mi = Gtk.MenuItem.new_with_label(row)
            mi.set_sensitive(False)
            self.menu.append(mi)
        self.menu.append(Gtk.SeparatorMenuItem.new())
        for row in self.trend_rows():
            mi = Gtk.MenuItem.new_with_label(row)
            mi.set_sensitive(False)
            self.menu.append(mi)
        dash = Gtk.MenuItem.new_with_label("Open Usage Dashboard")
        dash.connect("activate", self.open_dashboard)
        dash.set_sensitive(self.dash_ready)
        self.menu.append(dash)
        notif = Gtk.MenuItem.new_with_label("Notifications")
        notif.set_submenu(self.notif_submenu())
        self.menu.append(notif)
        self.menu.append(Gtk.SeparatorMenuItem.new())
        q = Gtk.MenuItem.new_with_label("Quit monitor")
        q.connect("activate", lambda _w: Gtk.main_quit())
        self.menu.append(q)
        self.menu.show_all()

        attention = sum(
            1
            for s in self.sessions.values()
            if s["status"] in ("waiting", "done") and not s.get("acked")
        )
        self.ind.set_label(core.build_label(self.usage, attention, self.config["usage_threshold"]), "")

    def usage_rows(self):
        """Menu-row strings from self.usage: 'unavailable', else used/countdown/burn."""
        u = self.usage
        if u is None:
            return ["usage unavailable"]
        # --api carries no token counts -> "% used"; the P90 path has them -> "72k / 88k".
        if u["tokens_used"] is not None and u["token_limit"] is not None:
            used = "%s / %s (%d%%)" % (
                core.fmt_tokens(u["tokens_used"]),
                core.fmt_tokens(u["token_limit"]),
                round(u["used_percentage"]),
            )
        else:
            used = "%d%% used" % round(u["used_percentage"])
        rows = [
            used,
            core.fmt_countdown(u["resets_at_epoch"] - time.time()),
            "burn: %s tok/hr" % core.fmt_tokens(round(u["burn_rate_per_min"] * 60)),
        ]
        if u.get("seven_day_pct") is not None:
            rows.append("week: %d%% used" % round(u["seven_day_pct"]))
            if u.get("seven_day_reset") is not None:
                rows.append(core.fmt_countdown_wk(u["seven_day_reset"] - time.time()))
        return rows

    def trend_rows(self):
        """Trend rows from the self.trends cache (no file I/O), or the collecting row."""
        if self.trends is None:
            return ["trends: collecting history..."]
        return self.trends

    USAGE_MISS_LIMIT = 2  # failed polls tolerated before showing "unavailable"

    def apply_usage(self, usage):
        # Stale beats empty for a transient failure, but sustained failure must surface.
        if usage is not None:
            self.usage = usage
            self.usage_misses = 0
        else:
            self.usage_misses += 1
            if self.usage_misses >= self.USAGE_MISS_LIMIT:
                self.usage = None
        self.rebuild_menu()
        return False

    def compute_trends(self, now):
        """Read history off the Gtk main thread and cache the trend rows."""
        try:
            with open(core.HISTORY_PATH, errors="replace") as f:
                records = core.parse_history(f.read())
        except OSError:
            return  # keep last-known trends; never crash the poll thread
        # ponytail: single list rebind, read-only in the Gtk redraw -- no lock.
        self.trends = core.build_trend_rows(records, now)

    def write_dashboard(self, now):
        """Read history off the Gtk main thread, render, atomic-write, flip dash_ready.
        Re-applies history_keep in case an opportunistic prune silently failed.
        ponytail: broad `except Exception` -- a render bug costs one tick, not the thread.
        """
        tmp = None
        try:
            with open(core.HISTORY_PATH, errors="replace") as f:
                records = core.parse_history(f.read())
            records = [r for r in records if core.history_keep(r, now, core.HISTORY_DAYS)]
            html = dashboard.render_dashboard(records, now)
            os.makedirs(dashboard.DASH_DIR, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=dashboard.DASH_DIR)
            with os.fdopen(fd, "w") as f:
                f.write(html)
            os.replace(tmp, dashboard.DASH_PATH)
            tmp = None  # replace succeeded; nothing to clean up
            self.dash_ready = True
        except Exception:
            return  # degrade: not updated this tick; retried next throttle window
        finally:
            if tmp is not None:
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    # runs on the Gtk main thread (via idle_add)
    def handle(self, msg):
        sid = msg.get("session_id") or msg.get("pane") or "?"
        event = msg.get("event", "done")
        if event == "end":
            self.sessions.pop(sid, None)
            self.rebuild_menu()
            return False

        cwd = msg.get("cwd") or "."
        d = os.path.basename(cwd.rstrip("/")) or cwd
        pane = msg.get("pane") or ""
        tmux = msg.get("tmux") or ""
        s = self.sessions.setdefault(sid, {})
        old = s.get("status")  # MUST be read before the update below overwrites it
        # _onscreen pre-acknowledges the "!" when serve() found you already looking.
        s.update(
            dir=d, status=event, pane=pane, tmux=tmux, cwd=cwd,
            acked=bool(msg.get("_onscreen")),
        )
        # `d` (the project dir) goes in the summary, which is not Pango-parsed, unlike body.
        if core.sess_should_notify(old, event):
            self.emit_notif(
                ("sess", sid),  # one slot per session -> a later transition replaces it
                event,
                d,
                "Waiting for input" if event == "waiting" else "Session finished",
                ("focus", pane, tmux),  # same outcome as clicking the tray row
                URGENCY_CRITICAL if event == "waiting" else URGENCY_NORMAL,
            )
        self.rebuild_menu()
        return False


def terminal_focused():
    """Best-effort: is the active X window our terminal? (X11 only, never raises)."""
    try:
        root = subprocess.run(
            ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
            capture_output=True, text=True, timeout=1).stdout
        wid = root.split()[-1]
        if not wid.startswith("0x"):
            return False
        cls = subprocess.run(
            ["xprop", "-id", wid, "WM_CLASS"],
            capture_output=True, text=True, timeout=1).stdout
        return GHOSTTY_CLASS in cls
    except Exception:
        return False


def pane_onscreen(pane, tmux):
    """Best-effort: is this tmux pane the one currently displayed? (never raises)."""
    if not pane:
        return False
    cmd = ["tmux"]
    if tmux:
        cmd += ["-S", tmux.split(",")[0]]
    cmd += ["display-message", "-t", pane, "-p", "#{pane_active}#{window_active}"]
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=1).stdout.strip()
        return out == "11"
    except Exception:
        return False


def looking_at(pane, tmux):
    """Is the user watching this pane? Best-effort; "can't tell" errs toward alerting.
    Shells out to xprop/tmux, so it must run off the Gtk main thread.
    """
    return terminal_focused() and pane_onscreen(pane, tmux)


def serve(mon):
    """Socket thread: hook events -> Monitor.handle on the Gtk main thread.
    ponytail: broad `except Exception` INSIDE the loop, so one bad connection costs one
    connection, not the only thread feeding session events. accept() stays outside it.
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
                conn.close()  # nested: a recv failure must not leak an fd
            for line in buf.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                # Decided here, off the Gtk main thread: looking_at() shells out.
                if msg.get("event") in ("done", "waiting"):
                    msg["_onscreen"] = looking_at(
                        msg.get("pane", ""), msg.get("tmux", "")
                    )
                GLib.idle_add(mon.handle, msg)
        except Exception:
            traceback.print_exc()  # loud and repeated; the thread survives regardless
            continue


def poll_loop(mon):
    """Daemon thread: fetch usage, append history, alert, then idle_add the redraw.
    All history file I/O lives here, never on the Gtk main thread.
    ponytail: broad `except Exception` around the loop body, printed not swallowed, so a
    bad iteration costs one poll instead of freezing the tray. time.sleep stays outside
    it so a failing iteration cannot hot-spin.
    """
    core.prune_history(time.time())
    last_prune = time.time()
    last_trend = 0.0  # 0 -> recompute on the first iteration, no blank window
    last_dash = 0.0  # 0 -> write the dashboard immediately at startup
    while True:
        try:
            usage = core.fetch_usage()
            now = time.time()
            if usage is not None:
                core.append_history(core.history_record(usage, now))
                # Rides this tick: every value is already in `usage`, and emit_notif is async.
                for cap, pct, reset, win, title in (
                    ("5h", usage["used_percentage"], usage["resets_at_epoch"], core.WIN5, "5-hour quota"),
                    # .get(): the 7d block is absent on an older CLI, which the predicates
                    # below already turn into silence.
                    ("7d", usage.get("seven_day_pct"), usage.get("seven_day_reset"), core.WIN7, "7-day quota"),
                ):
                    p = core.project(pct, reset, win, now)
                    if core.alert_should_fire(mon.alert_armed.get(cap), reset, p, now):
                        # Unguarded reads are safe: the predicate required "exhaust" in p.
                        mon.emit_notif(
                            ("cap", cap),  # one slot per cap -> a later alert replaces it
                            cap,
                            title,
                            # Both values are numbers we computed: no payload-derived string
                            # reaches the Pango-parsed body.
                            "Projected %d%% at reset -- runs out ~%s"
                            % (round(p["proj"]), core.hhmm(p["exhaust"])),
                            ("dash",),
                            URGENCY_NORMAL,  # informational; it need not block the screen
                        )
                        mon.alert_armed[cap] = reset  # silent until this reset changes
            # After the append (fresh record counts) and before the idle_add (redraw sees it).
            if now - last_trend >= TREND_INTERVAL:
                mon.compute_trends(now)
                last_trend = now
            # last_dash advances unconditionally, so a failed write is throttled, not retried.
            if now - last_dash >= dashboard.DASH_INTERVAL:
                mon.write_dashboard(now)
                last_dash = now
            GLib.idle_add(mon.apply_usage, usage)
            if now - last_prune >= PRUNE_INTERVAL:
                core.prune_history(now)
                last_prune = now
        except Exception:
            traceback.print_exc()  # the thread survives, the failure doesn't hide
        time.sleep(POLL_INTERVAL)


def watch_focus(mon):
    """Clear the "!" when you switch to a waiting/finished session's pane.
    tmux window switches send no event, so this polls -- but only while an un-acked
    session exists. Off the Gtk main thread; the redraw goes back via idle_add.
    """
    while True:
        time.sleep(2)
        try:
            pending = [
                s
                for s in list(mon.sessions.values())
                if s.get("status") in ("waiting", "done") and not s.get("acked")
            ]
            if not pending or not terminal_focused():
                continue
            changed = False
            for s in pending:
                if pane_onscreen(s.get("pane", ""), s.get("tmux", "")):
                    s["acked"] = True
                    changed = True
            if changed:
                GLib.idle_add(mon.rebuild_menu)
        except Exception:
            continue


def main():
    mon = Monitor()
    threading.Thread(target=serve, args=(mon,), daemon=True).start()
    threading.Thread(target=poll_loop, args=(mon,), daemon=True).start()
    threading.Thread(target=watch_focus, args=(mon,), daemon=True).start()

    # Keeps the countdown live between polls without re-shelling the CLI.
    def tick():
        mon.rebuild_menu()
        return True

    GLib.timeout_add_seconds(POLL_INTERVAL, tick)

    Gtk.main()


if __name__ == "__main__":
    import sys

    if "--selfcheck" in sys.argv:
        from claude_monitor import test_claude_monitor

        test_claude_monitor.demo()
    else:
        main()
