#!/usr/bin/env python3
"""Print one Claude Code usage line for a terminal status bar.

Writes "CC 62% 2h14m" on stdout and exits 0, or exits 1 having printed nothing when there
is no usage to show -- which is what tells tmux-powerline to hide the segment rather than
render a hole. In the yellow and red bands the line carries an inline tmux colour override;
the normal band inherits whatever colour the theme gave the segment, so only an unusual
state pulls the eye (the same idiom the user's own git_status.sh segment uses).

Data comes from the tray daemon that is already running, so this adds no polling and no
second source of truth. The live socket is tried first; when it is not there -- daemon
stopped, or never started -- the history file the daemon already maintains is read instead,
which is at most one poll interval (15s) stale. This never calls core.fetch_usage(): that
shells out to the CLI for 5-10 seconds and belongs to the daemon alone. A status bar that
blocked that long would simply stop updating.

Usage (as a tmux-powerline segment):  claude-status.py
"""

import sys
import time

from claude_monitor import core

# Catppuccin Mocha 256-colour approximations, matching the tmux-powerline theme.
# "green" is deliberately absent -- see the module docstring.
BAND_COLOUR = {"yellow": "colour216", "red": "colour210"}

# Makes the segment a click target. tmux reports the name back as #{mouse_status_range},
# which a MouseDown1Status binding tests to open the dashboard popup; see tmux/claude_usage.sh.
# Harmless when no such binding exists -- an unclaimed range is just inert markup.
RANGE = "claude_usage"


def read_usage():
    """(pct, reset_epoch) from the live daemon, else the history file, else (None, None).

    This is the boundary core.query_snapshot's docstring defers the swallowing to: it raises
    on every failure mode on purpose (no daemon, stale socket file, hung daemon, truncated
    JSON) because only the caller knows what a failure should look like. Here every one of
    them means the same thing -- fall back to disk -- and if that fails too, the segment
    simply does not render. Nothing about a status bar is worth a traceback in a hook.
    """
    try:
        usage = core.query_snapshot().get("usage") or {}
        return usage.get("used_percentage"), usage.get("resets_at_epoch")
    except Exception:
        pass
    try:
        with open(core.HISTORY_PATH) as f:
            state = core.latest_state(core.parse_history(f.read()))
        return state["pct"], state["reset"]
    except Exception:
        return None, None


def main():
    pct, reset = read_usage()
    text = core.statusline_text(pct, reset, time.time())
    if text is None:
        return 1  # nothing to say -> powerline drops the segment entirely
    colour = BAND_COLOUR.get(core.band(pct))
    # The colour goes OUTSIDE the range markers: tmux ends a range at #[norange], and
    # reopening a style inside one is what makes a clicked segment lose its tint.
    body = "#[range=user|%s]CC %s#[norange]" % (RANGE, text)
    print(body if colour is None else "#[fg=%s]%s" % (colour, body))
    return 0


if __name__ == "__main__":
    sys.exit(main())
