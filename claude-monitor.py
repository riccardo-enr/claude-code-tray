#!/usr/bin/env python3
"""Claude Code monitor: GNOME top-bar tray indicator.

A long-lived helper showing per-session Claude Code status in the top bar.
Claude Code hooks push one-line JSON events to a unix socket:
    {event, session_id, cwd, message, pane, tmux}
event in {running, waiting, done, end}. The helper reflects each session's
status in the tray menu; clicking a session focuses its tmux pane and raises
the Ghostty window.
"""
import os
import json
import socket
import threading
import subprocess

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import Gtk, GLib, AyatanaAppIndicator3 as AppIndicator

SOCK = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "claude-monitor.sock")
# Icon name from your theme; override with CLAUDE_TRAY_ICON. "claude-desktop"
# ships with the Claude desktop app; falls back to a generic terminal icon.
ICON = os.environ.get("CLAUDE_TRAY_ICON", "claude-desktop")
# WM_CLASS of your terminal, used to raise its window on click (X11 / wmctrl).
GHOSTTY_CLASS = os.environ.get("CLAUDE_TRAY_WM_CLASS", "com.mitchellh.ghostty")


class Monitor:
    def __init__(self):
        self.sessions = {}     # session_id -> {dir,status,pane,tmux,cwd}

        self.ind = AppIndicator.Indicator.new(
            "claude-monitor", ICON,
            AppIndicator.IndicatorCategory.APPLICATION_STATUS)
        self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.menu = Gtk.Menu()
        self.ind.set_menu(self.menu)
        self.rebuild_menu()

    # focus the originating tmux pane, then raise the Ghostty window (X11).
    def focus(self, pane, tmux):
        if pane:
            env = dict(os.environ)
            if tmux:
                env["TMUX"] = tmux
            subprocess.run(["tmux", "select-window", "-t", pane],
                           env=env, stderr=subprocess.DEVNULL)
            subprocess.run(["tmux", "select-pane", "-t", pane],
                           env=env, stderr=subprocess.DEVNULL)
        subprocess.run(["wmctrl", "-x", "-a", GHOSTTY_CLASS],
                       stderr=subprocess.DEVNULL)

    def rebuild_menu(self):
        for c in self.menu.get_children():
            self.menu.remove(c)
        if not self.sessions:
            mi = Gtk.MenuItem.new_with_label("No active Claude sessions")
            mi.set_sensitive(False)
            self.menu.append(mi)
        else:
            for s in self.sessions.values():
                mi = Gtk.MenuItem.new_with_label(
                    "%s  [%s]" % (s["dir"], s["status"]))
                mi.connect("activate",
                           lambda _w, s=s: self.focus(s["pane"], s["tmux"]))
                self.menu.append(mi)
        self.menu.append(Gtk.SeparatorMenuItem.new())
        q = Gtk.MenuItem.new_with_label("Quit monitor")
        q.connect("activate", lambda _w: Gtk.main_quit())
        self.menu.append(q)
        self.menu.show_all()

        waiting = sum(1 for s in self.sessions.values()
                      if s["status"] == "waiting")
        self.ind.set_label(("%d!" % waiting) if waiting else "", "")

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
        s.update(dir=d, status=event, pane=pane, tmux=tmux, cwd=cwd)
        self.rebuild_menu()
        return False


def serve(mon):
    if os.path.exists(SOCK):
        os.unlink(SOCK)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCK)
    srv.listen(8)
    while True:
        conn, _ = srv.accept()
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
            GLib.idle_add(mon.handle, msg)


def main():
    mon = Monitor()
    threading.Thread(target=serve, args=(mon,), daemon=True).start()
    Gtk.main()


if __name__ == "__main__":
    main()
