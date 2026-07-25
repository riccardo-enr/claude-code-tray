#!/usr/bin/env python3
"""Forward a Claude Code hook event to the claude-monitor helper.

Reads the hook JSON on stdin, tags it with the tmux pane/socket from the
environment, and fires it at the monitor's unix socket. Non-blocking and
silent if the monitor is not running -- must never hold up a hook.

Usage (as a hook command):  claude-send.py {running|waiting|done|end}
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

    msg = {
        "event": mode,
        "session_id": data.get("session_id", ""),
        "cwd": data.get("cwd", ""),
        "message": data.get("message", ""),
        "pane": os.environ.get("TMUX_PANE", ""),
        "tmux": os.environ.get("TMUX", ""),
        "term": os.environ.get("TERM_PROGRAM", ""),  # "zed" -> raise the Zed window, not tmux
        "background_tasks": data.get("background_tasks", []),
    }

    send_event(msg, sock)
