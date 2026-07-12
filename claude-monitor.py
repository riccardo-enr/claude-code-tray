#!/usr/bin/env python3
"""Claude Code monitor: GNOME top-bar tray indicator.

A long-lived helper showing per-session Claude Code status in the top bar.
Claude Code hooks push one-line JSON events to a unix socket:
    {event, session_id, cwd, message, pane, tmux}
event in {running, waiting, done, end}. The helper reflects each session's
status in the tray menu; clicking a session focuses its tmux pane and raises
the Ghostty window.
"""

import json
import os
import socket
import subprocess
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3 as AppIndicator
from gi.repository import GLib, Gtk

SOCK = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "claude-monitor.sock")
# Icon name from your theme; override with CLAUDE_TRAY_ICON. "claude-desktop"
# ships with the Claude desktop app; falls back to a generic terminal icon.
ICON = os.environ.get("CLAUDE_TRAY_ICON", "claude-desktop")
# WM_CLASS of your terminal, used to raise its window on click (X11 / wmctrl).
GHOSTTY_CLASS = os.environ.get("CLAUDE_TRAY_WM_CLASS", "com.mitchellh.ghostty")

# Absolute path to the installed claude-monitor CLI. Absolute on purpose: the
# CLI shares the bare name "claude-monitor" with this helper (claude-monitor.py).
USAGE_CLI = os.path.expanduser("~/.local/bin/claude-monitor")
# Which claude-monitor plan to query, passed as --plan. Default "custom" =
# session-based dynamic limits (P90), matching claude-monitor's own default view.
# An explicit plan is deterministic; the CLI's saved default (CLAUDE_TRAY_PLAN="")
# is NOT — it flips as different --plan values are used, so avoid relying on it.
# Override with CLAUDE_TRAY_PLAN (max5, max20, custom, pro, or "" for saved default).
PLAN = os.environ.get("CLAUDE_TRAY_PLAN", "custom")
# Seconds to sleep between CLI polls. The CLI itself takes ~5-10s (it re-parses
# the jsonl history), so effective refresh is roughly that + POLL_INTERVAL; going
# much below ~10 mostly just burns CPU. Override with CLAUDE_TRAY_POLL_INTERVAL.
try:
    POLL_INTERVAL = int(os.environ.get("CLAUDE_TRAY_POLL_INTERVAL", "15"))
except ValueError:
    POLL_INTERVAL = 15  # bad env -> default
POLL_TIMEOUT = 15  # subprocess seconds
# High-usage badge threshold (percent). Hardcoded on purpose: env-configurability
# is deferred (ALERT-F1). Do NOT add an env lookup here.
USAGE_THRESHOLD = 80

# Append-only usage history store (one JSON object per line). Phase 03 reads it.
HISTORY_PATH = os.path.expanduser("~/.claude/usage-history.jsonl")
# Retention window in days; records older than this are pruned. Env-overridable
# via CLAUDE_TRAY_HISTORY_DAYS, guarded the same way as POLL_INTERVAL above.
try:
    HISTORY_DAYS = int(os.environ.get("CLAUDE_TRAY_HISTORY_DAYS", "30"))
except ValueError:
    HISTORY_DAYS = 30  # bad env -> default
# Opportunistic-prune cadence in seconds (>= 6h per CONTEXT; planner-picked).
PRUNE_INTERVAL = 6 * 3600


def parse_usage(stdout):
    """Parse claude-monitor JSON stdout into a normalized usage dict, or None.

    Independent of the subprocess returncode by design: the CLI exits 11 while
    printing valid JSON at limit-hit, so this must parse stdout regardless of
    exit status. Returns None on any parse failure or missing limits.five_hour.
    """
    try:
        doc = json.loads(stdout)
        five = doc["limits"]["five_hour"]
        if not isinstance(five, dict):
            return None
        local = doc.get("local") or {}
        u = {
            "tokens_used": five["tokens_used"],
            "token_limit": five["token_limit"],
            "used_percentage": five["used_percentage"],
            "resets_at_epoch": five["resets_at_epoch"],
            "burn_rate_per_min": local.get("burn_rate_tokens_per_minute", 0),
        }
    except Exception:
        return None
    # Require numeric usage fields. A structurally valid payload carrying null or
    # string values (e.g. a just-reset window) would otherwise pass here and then
    # crash the Gtk-thread menu redraw (round()/epoch math) inside a GLib callback,
    # silently killing the countdown timer source. Degrade to "unavailable" instead.
    if not all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in u.values()
    ):
        return None
    return u


def fetch_usage():
    """Shell out to the CLI (fixed arg list, never shell=True) and parse stdout.

    Returns parse_usage()'s result, or None on any subprocess/OS error (timeout,
    missing or non-executable CLI, ...) so the daemon poll thread can never die.
    stdout is parsed regardless of returncode (exit 11 == limit-hit carries JSON).
    """
    cmd = [USAGE_CLI, "--output", "json", "--once"]
    if PLAN:
        cmd += ["--plan", PLAN]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=POLL_TIMEOUT)
    except (subprocess.SubprocessError, OSError):
        # timeout, missing CLI (FileNotFoundError), non-executable
        # (PermissionError) and other OS errors all degrade to unavailable.
        return None
    return parse_usage(r.stdout)


def fmt_tokens(n):
    """Compact token count: 417000 -> '417k', 18936912 -> '18.9M'."""
    if n >= 1e6:
        return "%.1fM" % (n / 1e6)
    return "%dk" % round(n / 1000)


def fmt_countdown(secs):
    """Reset countdown: 7380 -> 'resets in 2h 3m'; <= 0 -> 'resets now'."""
    secs = max(0, int(secs))
    if secs <= 0:
        return "resets now"
    return "resets in %dh %dm" % (secs // 3600, (secs % 3600) // 60)


def build_label(usage, attention):
    """Reconcile the usage-% badge and the attention-count badge into one label.

    `attention` is the number of sessions that need you (waiting on input, or
    just finished -> your turn). Usage leads ('47% 2!'), gains '!' above
    USAGE_THRESHOLD ('83%! 2!'). With no usage, falls back to the badge ('2!'/'').
    """
    wseg = ("%d!" % attention) if attention else ""
    if usage is None:
        return wseg
    seg = "%d%%" % round(usage["used_percentage"])
    if usage["used_percentage"] > USAGE_THRESHOLD:
        seg += "!"
    return " ".join(s for s in (seg, wseg) if s)


def history_record(usage, now):
    """Build the compact history record from a normalized usage dict.

    `t` is the wall-clock poll time (int(time.time()) at the call site), NOT
    resets_at_epoch. `burn` is stored as the RAW per-MINUTE value the source
    carries; Phase 03 converts it to per-hour once, so do not convert here.
    """
    return {
        "t": int(now),
        "pct": usage["used_percentage"],
        "tokens_used": usage["tokens_used"],
        "token_limit": usage["token_limit"],
        "burn": usage["burn_rate_per_min"],
    }


def history_keep(rec, now, days):
    """Retention predicate: True when rec is within the window, else False.

    Records strictly older than `days` are dropped. Pure boolean, reused by
    prune_history and by Phase 03's readers.
    """
    return rec["t"] >= now - days * 86400


def parse_history(text):
    """Tolerant loader: per-line json.loads, skipping empty and unparseable lines.

    A half-written trailing line from a killed process (or any garbage line) is
    skipped rather than raised on. Returns the surviving records in order.
    """
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def demo():
    """Assert-based self-check for the pure usage logic (run via --selfcheck)."""
    sample = {
        "limits": {
            "five_hour": {
                "tokens_used": 417000,
                "token_limit": 88000,
                "used_percentage": 473.5,
                "resets_at_epoch": int(time.time()) + 7380,
            }
        },
        "local": {"burn_rate_tokens_per_minute": 315615.2},
        "status": {"code": 11, "label": "limit_hit"},
    }
    u = parse_usage(json.dumps(sample))
    # parse is independent of the exit code (11): it never sees a returncode.
    assert u is not None and u["used_percentage"] == 473.5
    assert parse_usage("") is None
    assert parse_usage("not json") is None
    assert parse_usage(json.dumps({"limits": {}})) is None
    # structurally valid but non-numeric fields -> unavailable, not a crash (WR-01).
    assert (
        parse_usage(
            json.dumps(
                {
                    "limits": {
                        "five_hour": {
                            "tokens_used": 1,
                            "token_limit": 1,
                            "used_percentage": None,
                            "resets_at_epoch": 1,
                        }
                    }
                }
            )
        )
        is None
    )
    assert (
        parse_usage(
            json.dumps(
                {
                    "limits": {
                        "five_hour": {
                            "tokens_used": 1,
                            "token_limit": 1,
                            "used_percentage": 50.0,
                            "resets_at_epoch": "later",
                        }
                    }
                }
            )
        )
        is None
    )
    assert fmt_tokens(417000) == "417k"
    assert fmt_tokens(88000) == "88k"
    assert fmt_tokens(18936912) == "18.9M"
    # burn: per-minute field * 60 -> per-hour, then k/M formatted.
    assert fmt_tokens(round(u["burn_rate_per_min"] * 60)) == "18.9M"
    assert fmt_countdown(7380) == "resets in 2h 3m"
    assert fmt_countdown(0) == "resets now"
    # over-limit percent renders raw, never clamped to 100.
    assert round(473.5) == 474
    assert build_label({"used_percentage": 47}, 2) == "47% 2!"
    assert build_label({"used_percentage": 83}, 2) == "83%! 2!"
    assert build_label({"used_percentage": 47}, 0) == "47%"
    assert build_label(None, 2) == "2!"
    assert build_label(None, 0) == ""

    # --- history logic (Phase 02) ---
    now0 = int(time.time())
    hu = {
        "tokens_used": 417000,
        "token_limit": 88000,
        "used_percentage": 473.5,
        "resets_at_epoch": now0 + 7380,
        "burn_rate_per_min": 315615.2,
    }
    # record: t pinned to int(now) (NOT resets_at_epoch), burn stored RAW per-minute.
    assert history_record(hu, now0) == {
        "t": now0,
        "pct": 473.5,
        "tokens_used": 417000,
        "token_limit": 88000,
        "burn": 315615.2,
    }
    # retention: a 40-day-old record is dropped, a 1-day-old record is kept (days=30).
    assert history_keep({"t": now0 - 40 * 86400}, now0, 30) is False
    assert history_keep({"t": now0 - 1 * 86400}, now0, 30) is True
    # tolerant parse: the corrupt middle line is skipped; the two good ones survive in order.
    good1 = {"t": now0, "pct": 10.0}
    good2 = {"t": now0 + 1, "pct": 20.0}
    blob = json.dumps(good1) + "\nnot json {oops\n" + json.dumps(good2) + "\n"
    assert parse_history(blob) == [good1, good2]
    print("ok")


class Monitor:
    def __init__(self):
        self.sessions = {}  # session_id -> {dir,status,pane,tmux,cwd}
        self.usage = None  # latest parse_usage() dict, or None if unavailable
        self.usage_misses = 0  # consecutive failed polls; >= threshold -> unavailable

        self.ind = AppIndicator.Indicator.new(
            "claude-monitor", ICON, AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
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
            subprocess.run(
                ["tmux", "select-window", "-t", pane],
                env=env,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["tmux", "select-pane", "-t", pane], env=env, stderr=subprocess.DEVNULL
            )
        subprocess.run(["wmctrl", "-x", "-a", GHOSTTY_CLASS], stderr=subprocess.DEVNULL)

    # menu click: acknowledge (clears the session's "!" attention) and focus it.
    def on_click(self, s):
        s["acked"] = True
        self.rebuild_menu()
        self.focus(s["pane"], s["tmux"])

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
        q = Gtk.MenuItem.new_with_label("Quit monitor")
        q.connect("activate", lambda _w: Gtk.main_quit())
        self.menu.append(q)
        self.menu.show_all()

        # sessions that need you: waiting on input, or finished (your turn), and
        # not yet acknowledged by clicking the row -> "N!"
        attention = sum(
            1
            for s in self.sessions.values()
            if s["status"] in ("waiting", "done") and not s.get("acked")
        )
        self.ind.set_label(build_label(self.usage, attention), "")

    def usage_rows(self):
        """Insensitive menu-row label strings from self.usage (one 'unavailable'
        row when None, else the USAGE-01/02/03 lines)."""
        u = self.usage
        if u is None:
            return ["usage unavailable"]
        return [
            "%s / %s (%d%%)"
            % (
                fmt_tokens(u["tokens_used"]),
                fmt_tokens(u["token_limit"]),
                round(u["used_percentage"]),
            ),
            fmt_countdown(u["resets_at_epoch"] - time.time()),
            "burn: %s tok/hr" % fmt_tokens(round(u["burn_rate_per_min"] * 60)),
        ]

    # idle_add target on the Gtk main thread: store usage, redraw once.
    USAGE_MISS_LIMIT = 2  # consecutive failed polls tolerated before showing "unavailable"

    def apply_usage(self, usage):
        # Retain last-known usage across a transient poll failure so a single slow/
        # timed-out CLI call doesn't wipe a good readout (WR-03) -- slightly-stale data
        # beats an empty one for an at-a-glance indicator. But sustained failure must
        # surface as "usage unavailable" rather than silently showing hours-old numbers
        # (POLL-02): after USAGE_MISS_LIMIT consecutive misses, drop to the unavailable
        # state. A successful poll resets the counter.
        if usage is not None:
            self.usage = usage
            self.usage_misses = 0
        else:
            self.usage_misses += 1
            if self.usage_misses >= self.USAGE_MISS_LIMIT:
                self.usage = None
        self.rebuild_menu()
        return False

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
        # a fresh event re-arms the "!" -- unless serve() found you were already
        # looking at this pane, in which case pre-acknowledge it (no alert).
        s.update(
            dir=d, status=event, pane=pane, tmux=tmux, cwd=cwd,
            acked=bool(msg.get("_onscreen")),
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
    """True when the user is very likely watching this pane now: terminal focused
    AND it is the on-screen tmux pane. Best-effort -- 'can't tell' errs toward
    alerting. Runs off the Gtk main thread (shells out to xprop/tmux)."""
    return terminal_focused() and pane_onscreen(pane, tmux)


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
            # decide "already looking" here (background thread) so the xprop/tmux
            # shell-outs never block the Gtk main loop.
            if msg.get("event") in ("done", "waiting"):
                msg["_onscreen"] = looking_at(msg.get("pane", ""), msg.get("tmux", ""))
            GLib.idle_add(mon.handle, msg)


def poll_loop(mon):
    """Daemon-thread loop: fetch usage off the Gtk main loop, marshal the result
    back via GLib.idle_add (mirrors serve()'s pattern), then sleep."""
    while True:
        usage = fetch_usage()
        GLib.idle_add(mon.apply_usage, usage)
        time.sleep(POLL_INTERVAL)


def watch_focus(mon):
    """Auto-clear the "!" when you switch to a finished/waiting session's pane.

    Polls only while an un-acked attention session exists (idle-cheap), so the
    badge clears within ~2s of you looking at it -- tmux window switches send us
    no event. Runs off the Gtk main thread; the redraw is marshaled via idle_add.
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

    # Light Gtk timer: recompute the reset countdown locally from the cached
    # resets_at_epoch between polls, so it stays live without re-shelling the CLI.
    def tick():
        mon.rebuild_menu()
        return True

    GLib.timeout_add_seconds(POLL_INTERVAL, tick)

    Gtk.main()


if __name__ == "__main__":
    import sys

    if "--selfcheck" in sys.argv:
        demo()
    else:
        main()
