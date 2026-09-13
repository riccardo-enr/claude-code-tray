#!/usr/bin/env python3
"""Forward a Claude Code hook event to the claude-monitor helper.

Reads the hook JSON on stdin, tags it with the tmux pane/socket from the
environment, and fires it at the monitor's unix socket. Non-blocking and
silent if the monitor is not running -- must never hold up a hook.

Usage (as a hook command):  claude-send.py {running|waiting|done|end|subagent_stop}
Usage (as a statusLine feeder): claude-send.py usage
"""

import json
import os
import socket
import sys


def send_event(msg, sock_path, sock_factory=socket.socket):
    """Emit one hook event to the daemon socket. Silent on any failure -- a hook
    must never block on this. The socket is closed via finally, even when connect
    or sendall raises (e.g. the daemon closed the connection mid-write): a
    normal-exit path already closes it, so the exception path must not leak the fd
    (core.query_snapshot's own docstring calls this out by name).
    """
    try:
        s = sock_factory(socket.AF_UNIX, socket.SOCK_STREAM)
    except OSError:
        return
    try:
        s.settimeout(0.5)
        s.connect(sock_path)
        s.sendall((json.dumps(msg) + "\n").encode())
    except Exception:
        pass
    finally:
        s.close()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "done"
    sock = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "claude-monitor.sock")

    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    # statusLine feeder: the hook's rate_limits are the server's own numbers, unlike the
    # CLI percentage the daemon polls. Absent on the first render of a session and for
    # non-subscribers (verified in the 2.1.251 bundle's statusLine schema) -- say nothing.
    if mode == "usage":
        limits = data.get("rate_limits")
        if not isinstance(limits, dict):
            sys.exit(0)
        five = limits.get("five_hour")
        seven = limits.get("seven_day")
        five = five if isinstance(five, dict) else {}
        seven = seven if isinstance(seven, dict) else {}
        live = {
            "event": "usage_live",
            "pct": five.get("used_percentage"),
            "reset": five.get("resets_at"),
            "pct7": seven.get("used_percentage"),
            "reset7": seven.get("resets_at"),
        }
        if live["pct"] is None and live["pct7"] is None:
            sys.exit(0)
        send_event(live, sock)
        sys.exit(0)

    msg = {
        "event": mode,
        "session_id": data.get("session_id", ""),
        "cwd": data.get("cwd", ""),
        "message": data.get("message", ""),
        "pane": os.environ.get("TMUX_PANE", ""),
        "tmux": os.environ.get("TMUX", ""),
        "term": os.environ.get("TERM_PROGRAM", ""),  # "zed" -> raise the Zed window, not tmux
        "background_tasks": data.get("background_tasks", []),
        # PreToolUse only: lets the daemon tell a subagent dispatch from any other tool
        # call, both of which arrive as the same "running" event.
        "tool_name": data.get("tool_name", ""),
    }

    send_event(msg, sock)
