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
}

try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(0.5)
    s.connect(sock)
    s.sendall((json.dumps(msg) + "\n").encode())
    s.close()
except Exception:
    pass
