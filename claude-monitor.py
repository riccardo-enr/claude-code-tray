#!/usr/bin/env python3
"""Claude Code monitor: GNOME top-bar tray indicator.

A long-lived helper showing per-session Claude Code status in the top bar.
Claude Code hooks push one-line JSON events to a unix socket:
    {event, session_id, cwd, message, pane, tmux}
event in {running, waiting, done, end}. The helper reflects each session's
status in the tray menu; clicking a session focuses its tmux pane and raises
the Ghostty window.
"""

import base64
import datetime
import json
import math
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

# Desktop notifications, spoken over the session bus as raw freedesktop
# org.freedesktop.Notifications (Gio.DBusProxy). NOT Gio.Notification: gnome-shell's
# GTK notification path does lookup_app(appId + ".desktop") and drops the notification
# outright when there is no installed .desktop -- and this script has none.
NOTIF_BUS = "org.freedesktop.Notifications"
NOTIF_PATH = "/org/freedesktop/Notifications"
# GNOME Shell urgency levels. This is the ONLY knob that changes banner lifetime here:
# Notify's 8th argument (expire_timeout) is destructured by gnome-shell 46 as an unused
# name and never read again -- banner life is a hardcoded 4000ms. Pass -1 for it and do
# not reason about its value.
URGENCY_NORMAL = 1  # 4s banner -> GNOME's notification list (SESS-02 "done")
URGENCY_CRITICAL = 2  # no dismiss timer armed; sticks until clicked (SESS-01 "waiting")


def notif_allowed(kind):
    """Mute gate (NOTIF-02 seam). Phase 6 wires the config in HERE and nowhere else.

    `kind` is one of the four event-type keys "waiting", "done", "5h", "7d". Phase 5
    ships the seam open: every event fires. Phase 6's global mute (CFG-02) is a
    `return False` for all four, so no fifth key and no separate global gate is needed.
    """
    return True  # ponytail: seam only. Phase 6 (CFG-01/02) replaces this body and
    # touches zero call sites -- that is the whole point of gating inside emit_notif.


def sess_should_notify(old_status, new_status):
    """De-dupe predicate for session notifications (NOTIF-02 / D-03). Pure: no I/O, no clock.

    True iff the session just CHANGED into a notifiable state. A session sitting in
    "waiting" re-sends "waiting" on every hook event; only a transition passes. A session
    first seen already waiting has old_status None, which differs, so it notifies.
    "running" and "end" are not notifiable states.

    Deliberately takes no on-screen argument and must not grow one (D-04): a notification
    fires on every waiting/done transition regardless of where the user is looking. The
    already-looking-at-this-pane signal that serve() computes keeps gating ONLY the "!"
    attention badge. That divergence is intentional -- do not "helpfully" wire it in here.
    """
    return new_status in ("waiting", "done") and old_status != new_status


# Quota-window lengths in seconds. Same literals the dashboard JS carries at :787 -- if
# one moves, move both (project() is duplicated there on purpose; see its docstring).
WIN5 = 18000  # 5 hours
WIN7 = 604800  # 7 days
# D-05: the minimum lead a predictive alert needs to be worth showing. A projection that
# says "you run out in 90 seconds" is not actionable, and the >80% badge already covers
# "you are nearly there". 15 minutes is the floor for still being able to do something.
ALERT_LEAD = 15 * 60


def project(pct, reset, win, now):
    """Projected quota use at window reset, from the elapsed fraction of the window.

    Python port of the dashboard's project() (the JS at :972) -- QUOTA-03's arithmetic,
    reused for ALERT-02/03. The window began at reset-win, so the elapsed fraction e is
    known exactly; extrapolating the current pct linearly over the window gives the
    projected % at reset, and when that crosses 100 we can say WHEN it would land.

    Pure: `now` is an argument, never read off a clock, so demo() can pin every case.

    Returns None (no data), {"early": True} (too soon to extrapolate), or {"proj": float}
    which additionally carries an "exhaust" epoch, but ONLY when the projection strictly
    exceeds 100.

    DELIBERATE DUPLICATION -- the JS copy STAYS. It re-runs against a live browser clock
    as the static dashboard page ages between regenerations, so it cannot be collapsed
    into a value baked in from here. Same arithmetic, two clocks. Change one, change the
    other; demo() pins this copy. ponytail: collapse the two only if the page ever stops
    recomputing as it ages.
    """
    # seven_day_pct / seven_day_reset come back None on an older CLI (parse_usage lets
    # them through unguarded, unlike used_percentage / resets_at_epoch). This guard is the
    # ONE place the port is stricter than the JS -- JS coerces, Python would raise -- and
    # it is what makes the 7d alert degrade silently, exactly as usage_rows already does.
    if not _is_num(pct) or not _is_num(reset):
        return None
    start = reset - win
    e = (now - start) / float(win)  # win is a nonzero constant -> no div-by-zero
    if e <= 0.05:
        # Barely into the window -> pct/e explodes. Doubles as the clock-skew guard: a
        # negative e (a reset epoch further out than one whole window) lands here too.
        return {"early": True}
    if e > 1:
        e = 1.0  # window already over -> the projection degrades to the current pct
    out = {"proj": pct / e}
    if out["proj"] > 100 and pct > 0:  # `pct > 0` is what guards the 100.0 / pct below
        exh = start + (100.0 / pct) * (now - start)
        if exh < reset:
            out["exhaust"] = exh
    return out


def hhmm(epoch):
    """Local wall-clock HH:MM for an epoch. D-08 wants the alert body to name a clock
    reading, not a duration. stdlib, and it is right about DST.
    """
    return time.strftime("%H:%M", time.localtime(epoch))


def alert_due(p, now):
    """The D-05 lead predicate: is `p` (a project() result) worth alerting on? Pure.

    Written as a membership test on the exhaust key ON PURPOSE, and this is the subtlest
    line in the phase. project() sets that key only when the projection STRICTLY exceeds
    100, so a predicate that first tests the projected value >= 100 and then reads the
    exhaust key raises KeyError at exactly 100.0. The membership test SUBSUMES the
    projection test -- there is no projection clause to write, and there must not be one.

    Three decisions ride that single expression:
      D-05  -- an exhaust nearer than ALERT_LEAD is not actionable, so it stays silent.
      D-07  -- an already-exhausted cap has an exhaust in the PAST, so the same
               subtraction rejects it. That is why D-07 needs no special case, no code.
      early -- {"early": True} has no exhaust key either, so it is silent for free.
    """
    return bool(p) and "exhaust" in p and (p["exhaust"] - now) >= ALERT_LEAD


def alert_should_fire(armed_reset, reset, p, now):
    """One alert per cap per window, re-armed when the window rolls (D-06 / ALERT-04). Pure.

    `armed_reset` is the resets_at_epoch of the window in which this cap last alerted
    (None if it never has). That one value IS the whole state machine: a reset epoch is the
    window's identity, so a CHANGED epoch is a new window, definitionally -- which re-arms
    the cap for free, with no reset-detection code, no timer, and no clock math (ALERT-04).

    Once a cap fires it stays silent for the remainder of that window even if the
    projection climbs further (D-06). There is deliberately NO re-arm on the projection
    dipping under 100 and climbing back inside the same window -- that flaps around the
    boundary. ponytail: lead-step re-fires ("30m left") are deferred; add a second armed
    threshold per cap if one alert per window ever proves too quiet.
    """
    if not _is_num(reset):
        return False  # the 7d cap is absent on an older CLI -> degrade to silence
    if armed_reset == reset:
        return False  # already alerted in THIS window (D-06)
    return alert_due(p, now)


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

# Regenerated dashboard artifact. A derived cache file (NOT under ~/.claude/), so
# it lives under the XDG cache dir per D-01.
DASH_DIR = os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "claude-tray"
)
DASH_PATH = os.path.join(DASH_DIR, "dashboard.html")

# --- Phase 03 trend rendering constants ---
# Auto-scale ramp for the 24h usage sparkline; index 0 = lowest, -1 = highest.
# These 8 block glyphs + SPARK_GAP are the ONLY intended non-ASCII in this file.
SPARK_GLYPHS = "▁▂▃▄▅▆▇█"
SPARK_GAP = " "  # rendered for hours with no samples (keeps columns time-aligned)
TREND_INTERVAL = 5 * 60  # trend recompute throttle in poll_loop (seconds)
TREND_MIN_SPAN = 3600  # min history span (s) before real rows replace empty state
DASH_INTERVAL = 5 * 60  # dashboard-regen throttle in poll_loop (seconds)
# The dashboard is a static file on disk: without this an open tab keeps showing
# whatever was written when it was opened. ponytail: meta-refresh over a JS poller;
# swap it out only if the page ever grows state a reload would throw away.
_DASH_META_REFRESH = f"<meta http-equiv=\"refresh\" content=\"{DASH_INTERVAL}\">"


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
        seven = doc["limits"].get("seven_day")
        if not isinstance(seven, dict):
            seven = {}
        u = {
            "tokens_used": five["tokens_used"],
            "token_limit": five["token_limit"],
            "used_percentage": five["used_percentage"],
            "resets_at_epoch": five["resets_at_epoch"],
            "burn_rate_per_min": local.get("burn_rate_tokens_per_minute", 0),
            # Weekly (7-day) cap. Claude Code enforces BOTH a rolling 5h window and
            # a rolling 7d one, and the weekly is often the binding constraint, so
            # capture it. OPTIONAL by design: older CLIs and non---api modes omit
            # the block entirely -- see the degrade-to-None rule below.
            "seven_day_pct": seven.get("used_percentage"),
            "seven_day_reset": seven.get("resets_at_epoch"),
        }
    except Exception:
        return None
    def is_num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    # Essentials must be numeric. A structurally valid payload carrying null or
    # string values here (e.g. a just-reset window) would otherwise crash the
    # Gtk-thread menu redraw (round()/epoch math) inside a GLib callback,
    # silently killing the countdown timer source. Degrade to "unavailable".
    if not all(is_num(u[k]) for k in ("used_percentage", "resets_at_epoch", "burn_rate_per_min")):
        return None
    # Token counts are optional: the official --api usage endpoint reports
    # percentages only, so tokens_used/token_limit legitimately come back null.
    # Accept numeric-or-null; reject any other junk (strings) that would break
    # fmt_tokens downstream. usage_rows renders "% used" when they are null.
    for k in ("tokens_used", "token_limit"):
        if u[k] is not None and not is_num(u[k]):
            return None
    # The weekly block is optional AND secondary: junk or nulls there must never
    # invalidate the five-hour payload the tray depends on. Degrade to None rather
    # than returning None for the whole poll (which would blank the usage rows).
    for k in ("seven_day_pct", "seven_day_reset"):
        if not is_num(u[k]):
            u[k] = None
    return u


def fetch_usage():
    """Shell out to the CLI (fixed arg list, never shell=True) and parse stdout.

    Returns parse_usage()'s result, or None on any subprocess/OS error (timeout,
    missing or non-executable CLI, ...) so the daemon poll thread can never die.
    stdout is parsed regardless of returncode (exit 11 == limit-hit carries JSON).
    """
    # --api pulls the official OAuth usage numbers (matching Claude Code's
    # /usage): authoritative used_percentage + reset time. That endpoint reports
    # percentages only, so tokens_used/token_limit come back null and the token
    # row degrades to "% used" (see parse_usage / usage_rows). --plan stays as
    # the fallback basis when the (experimental) endpoint is stale/absent.
    cmd = [USAGE_CLI, "--output", "json", "--once", "--api"]
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


def fmt_countdown_wk(secs):
    """Weekly reset countdown: 352800 -> 'week resets in 4d 2h'; under a day falls
    back to h/m; <= 0 -> 'week resets now'.

    Separate from fmt_countdown on purpose: the 5h row's 'Xh Ym' shape is right for
    a 5-hour window but a multi-day gap would render as 'resets in 98h 0m'.
    """
    secs = int(secs)
    if secs <= 0:
        return "week resets now"
    if secs >= 86400:
        return "week resets in %dd %dh" % (secs // 86400, (secs % 86400) // 3600)
    return "week resets in %dh %dm" % (secs // 3600, (secs % 3600) // 60)


def build_label(usage, attention):
    """Reconcile the usage-% badge and the attention-count badge into one label.

    `attention` is the number of sessions that need you (waiting on input, or
    just finished -> your turn). Usage leads ('47% 2!'), gains '!' above
    USAGE_THRESHOLD ('83%! 2!'). With no usage, falls back to the badge ('2!'/'').

    The '!' also fires when the WEEKLY cap is above threshold even if the 5h window
    is cool. Claude Code enforces both, and the weekly is often the binding one, so
    a 95%-weekly / 10%-five-hour state previously produced NO warning at all. The
    leading number stays the 5h one (swapping it would read as a glitch); the menu's
    'week: N% used' row tells you which limit is hot.
    """
    wseg = ("%d!" % attention) if attention else ""
    if usage is None:
        return wseg
    seg = "%d%%" % round(usage["used_percentage"])
    pct7 = usage.get("seven_day_pct")
    hot = usage["used_percentage"] > USAGE_THRESHOLD or (
        pct7 is not None and pct7 > USAGE_THRESHOLD
    )
    if hot:
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
        # `reset` is the 5h window's end epoch -- persisted so readers can mark
        # where the usage-% sawtooth DROPS because the window rolled (rather than
        # because usage fell) and can show a countdown. `pct7`/`reset7` are the
        # weekly cap. All three are OPTIONAL: records written before this change
        # simply lack the keys, so every reader must tolerate their absence.
        "reset": usage["resets_at_epoch"],
        "pct7": usage.get("seven_day_pct"),
        "reset7": usage.get("seven_day_reset"),
    }


def history_keep(rec, now, days):
    """Retention predicate: True when rec is within the window, else False.

    Records strictly older than `days` are dropped. Pure boolean, reused by
    prune_history and by Phase 03's readers.
    """
    return rec["t"] >= now - days * 86400


def parse_history(text):
    """Tolerant loader: per-line json.loads, keeping only well-formed records.

    A record is well-formed when it is a JSON object carrying a numeric "t" (the
    poll epoch). Empty lines, unparseable lines (e.g. a half-written trailing
    line from a killed process), and structurally invalid records (bare scalars,
    arrays, or objects whose "t" is missing or non-numeric) are all skipped
    rather than raised on. This is the single corruption-tolerance boundary both
    prune_history and Phase 03's readers route through, so a downstream
    history_keep(rec["t"]) can never raise on garbage. Returns survivors in order.
    """
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict) and isinstance(rec.get("t"), (int, float)):
            out.append(rec)
    return out


def append_history(record):
    """Append one record as a JSON line to HISTORY_PATH; swallow OSError.

    A missing/unwritable path or full disk degrades to "history just doesn't
    persist" rather than crashing or blocking the poll thread.
    """
    try:
        with open(HISTORY_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        return


def prune_history(now):
    """Drop records older than HISTORY_DAYS, rewriting HISTORY_PATH atomically.

    Survivors are written to a temp file in the same dir, then os.replace'd over
    the original -- never truncate-in-place, so there is no data-loss window. Any
    OSError (including the file not existing) is swallowed and leaves the original
    untouched; a leftover temp file is cleaned up if the replace did not happen.
    """
    tmp = None
    try:
        with open(HISTORY_PATH, errors="replace") as f:
            records = parse_history(f.read())
        survivors = [r for r in records if history_keep(r, now, HISTORY_DAYS)]
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(HISTORY_PATH))
        with os.fdopen(fd, "w") as f:
            for r in survivors:
                f.write(json.dumps(r) + "\n")
        os.replace(tmp, HISTORY_PATH)
        tmp = None  # replace succeeded; nothing to clean up
    except OSError:
        return
    finally:
        if tmp is not None:
            try:
                os.remove(tmp)
            except OSError:
                pass


def local_bounds(now):
    """Local-calendar day/week start epochs for `now` (per D-09).

    Returns (day_start_epoch, week_start_epoch): local midnight today and local
    Monday 00:00 of the current ISO week. Uses local time (no tz arg) so the
    boundaries match how a person reads "today" and align with the peak-hour view.
    """
    dt = datetime.datetime.fromtimestamp(now)
    day_start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - datetime.timedelta(days=day_start.weekday())
    return int(day_start.timestamp()), int(week_start.timestamp())


def trend_sparkline(records, now):
    """24-char auto-scaled block sparkline of mean pct/hour over 24h (D-01..D-04).

    Column i (0 = 23h ago, 23 = current hour) is the mean `pct` of records in that
    hour bucket. Heights auto-scale to the window's own non-empty min..max across
    the 8 block glyphs; empty hours render SPARK_GAP so columns stay time-aligned.
    Guards a flat window (hi == lo -> lowest glyph) and empty input (all gaps) so
    there is no ZeroDivisionError. Bare string, no label/prefix.
    """
    buckets = [[] for _ in range(24)]
    for rec in records:
        bucket = 23 - int((now - rec["t"]) // 3600)
        if 0 <= bucket <= 23:
            buckets[bucket].append(rec["pct"])
    means = [sum(b) / len(b) if b else None for b in buckets]
    vals = [m for m in means if m is not None]
    if not vals:
        return SPARK_GAP * 24
    lo, hi = min(vals), max(vals)
    span = hi - lo
    out = []
    for m in means:
        if m is None:
            out.append(SPARK_GAP)
        elif span == 0:
            out.append(SPARK_GLYPHS[0])  # flat window: all non-empty at the floor
        else:
            idx = round((m - lo) / span * (len(SPARK_GLYPHS) - 1))
            out.append(SPARK_GLYPHS[idx])
    return "".join(out)


def trend_burn(records, start, end):
    """Mean burn RATE in tok/hr over [start, end), or None (per D-08).

    Averages the RAW per-minute `burn` field of records with start <= t < end,
    then multiplies by 60 exactly ONCE to convert per-minute -> per-hour.
    """
    vals = [rec["burn"] for rec in records if start <= rec["t"] < end]
    if not vals:
        return None
    return sum(vals) / len(vals) * 60


def trend_peak_hour(records):
    """Busiest local hour-of-day and its mean burn rate in tok/hr, or None (D-10).

    Groups all records by local hour (0-23), ranks by mean raw per-minute `burn`,
    and returns (hour, mean_burn * 60) for the top hour. Ties break to the lowest
    hour index for determinism (ascending scan, strict-greater update).
    """
    if not records:
        return None
    hours = {}
    for rec in records:
        h = datetime.datetime.fromtimestamp(rec["t"]).hour
        hours.setdefault(h, []).append(rec["burn"])
    best_hour, best_rate = None, None
    for h in sorted(hours):
        rate = sum(hours[h]) / len(hours[h])
        if best_rate is None or rate > best_rate:
            best_hour, best_rate = h, rate
    return best_hour, best_rate * 60


def build_trend_rows(records, now):
    """Pure core of Monitor.compute_trends: history records -> trend rows (or None).

    Sanitizes through history_numeric FIRST -- the SAME choke point render_dashboard
    uses. parse_history validates a numeric `t` only, so a corrupt record can still
    carry a string `burn` (TypeError inside trend_burn's sum), a NaN `burn` (renders
    "nan/hr") or a far-future `t` (OSError inside fromtimestamp). Dropping the whole
    suspect record here means no corrupt value reaches ANY trend math, and the
    TREND_MIN_SPAN check below is evaluated on sanitized records so a far-future `t`
    can no longer inflate the span.

    Returns None while the retained history spans less than TREND_MIN_SPAN seconds
    (empty/collecting state, D-12), else the list of row strings.

    Split out of the Monitor method on purpose: this is Gtk-free, so demo() exercises
    the real path without instantiating Monitor.
    """
    records = history_numeric(records)
    if not records or records[-1]["t"] - records[0]["t"] < TREND_MIN_SPAN:
        return None  # not enough data yet -> collecting state
    rows = [trend_sparkline([r for r in records if history_keep(r, now, 1)], now)]
    day_start, week_start = local_bounds(now)
    today = trend_burn(records, day_start, now)
    week = trend_burn(records, week_start, now)
    rows.append(
        "today %s/hr | wk %s/hr"
        % (
            fmt_tokens(round(today)) if today is not None else "-",
            fmt_tokens(round(week)) if week is not None else "-",
        )
    )
    peak = trend_peak_hour(records)
    if peak is not None:
        rows.append("peak hour: %02d:00 (%s/hr)" % (peak[0], fmt_tokens(round(peak[1]))))
    return rows


def _embed_json(obj):
    """JSON-serialize obj, escaping <, >, & so a value can't break out of the
    inline <script> that embeds it (T-04-01). The ONLY place the dashboard
    payload is serialized; escapes to JSON unicode escapes, so the JS still
    parses the const while '</script>' etc. can never appear literally.
    """
    return (
        json.dumps(obj)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def history_numeric(records):
    """Keep only records whose t, pct AND burn are ALL numeric (review finding 1).

    parse_history validates a numeric `t` only, so a corrupt/tampered record can
    still carry a string `pct`/`burn` that would raise inside trend_burn's
    sum(vals) or reach the JS chart math. Dropping the whole suspect record here
    (before any aggregation or embedding) keeps bad values out of every dataset;
    _embed_json escaping remains as defense-in-depth. Order preserved.

    Also rejects non-finite floats (NaN/Infinity, which json.loads accepts by
    default) for t/pct/burn, and bounds `t` to a plausible epoch window
    (0 < t < 4102444800, i.e. before 2100-01-01 UTC) so int(t)/
    datetime.fromtimestamp(t) can never overflow and so a far-future record --
    which history_keep never prunes -- cannot permanently break regeneration
    (WR-01).
    """
    def num(v):
        return (
            isinstance(v, (int, float))
            and not isinstance(v, bool)
            and math.isfinite(v)
        )

    return [
        r for r in records
        if num(r.get("t")) and 0 < r["t"] < 4102444800
        and num(r.get("pct")) and num(r.get("burn"))
    ]


def heatmap_buckets(records):
    """7x24 grid (dow Mon..Sun x hour 0..23) of MEAN USAGE % (DASH-03).

    Buckets `pct` (percent of the 5h cap), NOT raw `burn`. The whole dashboard is
    denominated in percent, and burn is a raw per-minute throughput estimate whose
    tens-of-millions scale is unreadable -- the same reason the burn line chart was
    dropped. mean(pct) answers the useful question: "how full is my quota at this
    hour, typically". Empty buckets stay None so "no data" stays distinct from a
    genuine 0% (gray vs ramp, D-07).
    """
    grid = [[None] * 24 for _ in range(7)]
    acc = {}
    for rec in records:
        dt = datetime.datetime.fromtimestamp(rec["t"])
        acc.setdefault((dt.weekday(), dt.hour), []).append(rec["pct"])
    for (dow, hour), vals in acc.items():
        grid[dow][hour] = sum(vals) / len(vals)
    return grid


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def reset_marks(records):
    """Sorted unique 5h-window reset epochs seen in `records` (DASH: reset markers).

    The usage-% line DROPS every time the window rolls. Without markers those drops
    read as "usage fell" when they mean "the window reset" -- actively misleading.
    Records written before the `reset` field existed simply contribute nothing.
    """
    return sorted({int(r["reset"]) for r in records if _is_num(r.get("reset"))})


GAP_MAX = 300  # seconds; a hole wider than this is a data gap, not a trend


def with_gaps(series, max_gap=GAP_MAX):
    """Insert [t, None] breaks wherever consecutive samples are >max_gap apart.

    Without this the renderer joins the two samples either side of an outage with a
    straight line, which reads as a smooth trend that never happened (e.g. a tidy
    diagonal "decline" across a night when the tray simply was not running). None is
    the renderer's existing pen-up signal, so the line breaks instead of lying.
    """
    out = []
    prev = None
    for t, v in series:
        if prev is not None and t - prev > max_gap:
            out.append([prev, None])
        out.append([t, v])
        prev = t
    return out


def usage7_series(records):
    """[[t, weekly_pct], ...] for records carrying a numeric `pct7`, in order.

    Empty for history written before the weekly cap was captured -- the weekly line
    simply starts where the data starts rather than faking backfill.
    """
    return [[int(r["t"]), r["pct7"]] for r in records if _is_num(r.get("pct7"))]


def latest_state(records):
    """Newest record's current-quota fields, for the dashboard status card.

    Picks by MAX t rather than trusting file order. Returns None-filled fields when
    a legacy record lacks them, so the card renders only what it actually knows.
    """
    if not records:
        return {"pct": None, "reset": None, "pct7": None, "reset7": None}
    r = max(records, key=lambda x: x["t"])
    out = {}
    for k in ("pct", "reset", "pct7", "reset7"):
        v = r.get(k)
        out[k] = v if _is_num(v) else None
    return out


# --- Dashboard HTML (self-contained: inline CSS/JS, SVG charts, no CDN/deps) ---
# The ONE permitted http:// in the page is the SVG XML namespace passed to
# createElementNS -- an identifier, never fetched. No <link, no src=, no https://.
def _brand_icon_uri():
    """base64 data: URI for the locally-installed Claude icon, or "" when absent.

    EMBEDDED, not referenced: the page must stay self-contained (DASH-06, asserted
    in --selfcheck), so a file path or a URL is not an option. It is applied via CSS
    `background-image:url(data:...)` rather than `<img src=...>` because the very
    same self-containment assert forbids any `src=` in the page -- an <img> tag would
    fail it. 32x32 is ~2KB of base64; small enough to re-embed on every regeneration.

    Degrades to "" (no mark, no broken image) on machines with no claude-desktop
    install, which is why the CSS below is emitted conditionally.
    """
    for p in (
        "/usr/share/icons/hicolor/32x32/apps/claude-desktop.png",
        "/usr/share/icons/hicolor/48x48/apps/claude-desktop.png",
    ):
        try:
            with open(p, "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            return "data:image/png;base64," + data
        except OSError:
            continue
    return ""


_BRAND_URI = _brand_icon_uri()

_BRAND_CSS = (
    (
        "#brand{width:20px;height:20px;display:inline-block;flex:none;"
        "margin-right:.45em;background-size:contain;background-repeat:no-repeat;"
        "background-position:center;background-image:url(" + _BRAND_URI + ")}"
    )
    if _BRAND_URI
    else "#brand{display:none}"
)

# Dark palette, reused by BOTH the explicit [data-theme="dark"] rule (toggle) and
# the prefers-color-scheme fallback (so the JS-less empty page still respects the
# system theme). Kept as one string so the two selectors cannot drift apart.
_DASH_DARK = (
    "--bg:#16181d;--fg:#e6e8ec;--card:#1e2128;--border:#2c313a;--muted:#8b929c;"
    "--accent:#4a9eda;--accent2:#e0a458;--mark:#4a5261;--grid:#3a414b;"
    "--gridlite:#2a2f37;--h2:#cfd3da;"
    "--btn:#252932;--btnbd:#3a414b;--legend:#9aa1ab;--swbd:#3a414b;"
    "--shadow:rgba(0,0,0,.35)"
)

_DASH_STYLE = (
    ":root{--bg:#f4f5f7;--fg:#1a1a1a;--card:#fff;--border:#e6e6e6;--muted:#888;"
    "--accent:#1a6cae;--accent2:#c2670f;--mark:#c9ccd1;--grid:#ccc;"
    "--gridlite:#eee;--h2:#333;--btn:#fff;"
    "--btnbd:#bbb;--legend:#555;--swbd:#ddd;--shadow:rgba(0,0,0,.06)}"
    "[data-theme=\"dark\"]{" + _DASH_DARK + "}"
    "@media (prefers-color-scheme:dark){:root:not([data-theme=\"light\"]){"
    + _DASH_DARK + "}}"
    "body{font-family:sans-serif;background:var(--bg);color:var(--fg);"
    "max-width:920px;margin:0 auto;padding:1.5em}"
    "h1{font-size:1.3em;margin:.2em 0;display:flex;align-items:center;"
    "justify-content:space-between}"
    "h2{font-size:1em;color:var(--h2);margin:0 0 .6em}"
    "section{background:var(--card);border:1px solid var(--border);"
    "border-radius:8px;padding:.9em 1.1em;margin:0 0 1.1em;"
    "box-shadow:0 1px 3px var(--shadow)}"
    "svg{max-width:100%;height:auto}"
    "svg .grid{stroke:var(--grid)}svg .gridlite{stroke:var(--gridlite)}"
    "svg .axis{fill:var(--muted)}"
    "svg .series{stroke:var(--accent);fill:none;stroke-width:2}"
    "svg .series7{stroke:var(--accent2);fill:none;stroke-width:2}"
    "svg .reset{stroke:var(--mark);stroke-dasharray:3 3}"
    "svg .dot{fill:var(--accent);stroke:none}"
    "svg .dot7{fill:var(--accent2);stroke:none}"
    "svg .proj{stroke:var(--accent);stroke-dasharray:4 3;fill:none;"
    "stroke-width:2;opacity:.75}"
    "svg .proj7{stroke:var(--accent2);stroke-dasharray:4 3;fill:none;"
    "stroke-width:2;opacity:.75}"
    "svg .proj.over,svg .proj7.over{stroke:#d1495b;opacity:.95}"
    "svg .projlab{fill:var(--accent);font-size:11px;font-weight:600}"
    "svg .projlab7{fill:var(--accent2);font-size:11px;font-weight:600}"
    "svg .projlab.over,svg .projlab7.over{fill:#d1495b}"
    "#u-legend .kp{background:repeating-linear-gradient(90deg,"
    "var(--accent) 0 4px,transparent 4px 7px)}"
    "#status{display:flex;flex-direction:column;gap:.55em}"
    ".srow{display:grid;grid-template-columns:5em 3.2em 7em 1fr;align-items:center;"
    "gap:.6em;font-size:.9em}"
    ".sname{font-weight:600;display:flex;align-items:center}"
    ".sval{text-align:right;font-variant-numeric:tabular-nums}"
    ".sbar{height:8px;background:var(--gridlite);border-radius:4px;"
    "overflow:hidden;display:block}"
    ".sfill{display:block;height:100%;background:var(--accent);border-radius:4px}"
    ".sfill.hot{background:#d1495b}"
    ".smeta{color:var(--muted);font-size:.9em}"
    "#u-legend{display:flex;align-items:center;gap:.4em;font-size:.85em;"
    "color:var(--legend);margin-top:.4em}"
    "#u-legend .k{width:14px;height:3px;display:inline-block;vertical-align:middle}"
    "#u-legend .k5{background:var(--accent)}"
    "#u-legend .k7{background:var(--accent2)}"
    "#u-legend .kr{background:var(--mark)}"
    "#ranges button,#theme{padding:.25em .8em;border:1px solid var(--btnbd);"
    "background:var(--btn);color:var(--fg);border-radius:4px;cursor:pointer;"
    "font:inherit}"
    "#ranges button{margin-right:.4em}"
    "#theme{font-size:.7em}"
    "#ranges button.active{background:var(--accent);color:#fff;"
    "border-color:var(--accent)}"
    "#usage-now{color:var(--accent);font-weight:600}"
    "p.empty{color:var(--muted)}"
    "#meta{color:var(--muted);font-size:.85em;margin:.2em 0 1.5em}"
    "#hm-legend{display:flex;align-items:center;gap:.4em;font-size:.85em;"
    "color:var(--legend);margin-top:.5em}"
    "#hm-legend .sw{width:16px;height:12px;display:inline-block;"
    "border:1px solid var(--swbd);vertical-align:middle}"
    # Inline SVG glyphs. Stroked with currentColor so they inherit the themed text
    # colour with no per-theme rules, and carry NO xmlns -- inline SVG in HTML does
    # not need one, which keeps the page's only http:// the createElementNS literal.
    ".ic{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:1.5;"
    "stroke-linecap:round;stroke-linejoin:round;vertical-align:-2px;"
    "margin-right:.35em;flex:none}"
    "h2 .ic{opacity:.75}"
    ".ttl{display:flex;align-items:center;min-width:0}"
    + _BRAND_CSS
)

# Inline SVG icon markup (no xmlns on purpose -- see .ic above).
_IC_GAUGE = (
    "<svg class=\"ic\" viewBox=\"0 0 16 16\">"
    "<path d=\"M2 12a6 6 0 1 1 12 0\"/><path d=\"M8 12l3.5-3.5\"/></svg>"
)
_IC_TREND = (
    "<svg class=\"ic\" viewBox=\"0 0 16 16\">"
    "<path d=\"M2 13V3\"/><path d=\"M2 13h12\"/><path d=\"M4 10l3-3 2.5 2.5L14 5\"/></svg>"
)
_IC_GRID = (
    "<svg class=\"ic\" viewBox=\"0 0 16 16\">"
    "<path d=\"M2.5 2.5h11v11h-11z\"/><path d=\"M6 2.5v11\"/><path d=\"M10 2.5v11\"/>"
    "<path d=\"M2.5 6h11\"/><path d=\"M2.5 10h11\"/></svg>"
)

_DASH_EMPTY = (
    "<!doctype html><html><head><meta charset=\"utf-8\">"
    + _DASH_META_REFRESH +
    "<title>Claude Code - Usage Dashboard</title>"
    "<style>" + _DASH_STYLE + "</style></head>"
    "<body><h1><span class=\"ttl\"><span id=\"brand\"></span>"
    "Claude Code - Usage Dashboard</span></h1>"
    "<p class=\"empty\">Collecting usage history...</p></body></html>"
)

_DASH_BODY = (
    "<h1><span class=\"ttl\"><span id=\"brand\"></span>"
    "Claude Code - Usage Dashboard</span>"
    "<button id=\"theme\">Dark</button></h1>"
    "<div id=\"meta\"></div>"
    "<section><h2>" + _IC_GAUGE + "Current quota</h2>"
    "<div id=\"status\"></div></section>"
    "<section><h2>" + _IC_TREND + "Usage % over time"
    "<span id=\"usage-now\"></span></h2>"
    "<div id=\"ranges\"><button data-range=\"h24\">24h</button>"
    "<button data-range=\"d7\">7d</button>"
    "<button data-range=\"all\" class=\"active\">All</button></div>"
    "<svg id=\"usage-chart\" viewBox=\"0 0 600 200\"></svg>"
    "<div id=\"u-legend\"><span class=\"k k5\"></span><span>5-hour</span>"
    "<span class=\"k k7\"></span><span>weekly</span>"
    "<span class=\"k kp\"></span><span>projected</span>"
    "<span class=\"k kr\"></span><span>window reset</span></div></section>"
    "<section><h2>" + _IC_GRID + "Usage by hour (mean % of the 5h cap)</h2>"
    "<svg id=\"heatmap\" viewBox=\"0 0 520 170\"></svg>"
    "<div id=\"hm-legend\"></div></section>"
)

_DASH_JS = """
var NS="http://www.w3.org/2000/svg";
// Declared up here on purpose: drawUsage() runs during init and reads WIN5 for the
// projection. Left further down (beside the status card) `var` hoisting would give
// it the name but not the value -- WIN5 would be undefined at first paint.
var WIN5=18000,WIN7=604800;
var DAYS=["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
function clear(n){while(n.firstChild)n.removeChild(n.firstChild);}
function el(name,attrs){var e=document.createElementNS(NS,name);for(var k in attrs)e.setAttribute(k,attrs[k]);return e;}
function two(n){return(n<10?"0":"")+n;}
function drawChart(svg,seriesList,marks,unit,yfloor,projs){
  var W=600,H=200,PL=42,PR=12,PT=12,PB=30,xs=[],ys=[];
  seriesList.forEach(function(s){s.pts.forEach(function(p){
    if(p[1]!==null){xs.push(p[0]);ys.push(p[1]);}});});
  if(!xs.length)return;
  // A "to" projection lands in the FUTURE (the 5h reset), so widen the domain to
  // include it or it would be drawn off the right edge. "rate" projections are
  // deliberately NOT included -- see the note where they are drawn.
  (projs||[]).forEach(function(pr){
    if(pr.kind==="to"){xs.push(pr.t1);ys.push(pr.p1);}
  });
  var xmin=Math.min.apply(null,xs),xmax=Math.max.apply(null,xs);
  var ymax=Math.max.apply(null,ys);if(ymax<yfloor)ymax=yfloor;if(ymax<=0)ymax=1;
  var xr=(xmax-xmin)||1,spanDays=xr/86400,i,yv,xv,gy,gx,t;
  function sx(x){return PL+(x-xmin)/xr*(W-PL-PR);}
  function sy(y){return H-PB-(y/ymax)*(H-PB-PT);}
  function xlab(xv){var dt=new Date(xv*1000);return spanDays<2?(dt.getHours()+":"+two(dt.getMinutes())):((dt.getMonth()+1)+"/"+dt.getDate());}
  for(i=0;i<=4;i++){
    yv=ymax*i/4;gy=sy(yv);
    svg.appendChild(el("line",{x1:PL,y1:gy,x2:W-PR,y2:gy,"class":i?"gridlite":"grid"}));
    t=el("text",{x:PL-5,y:gy+4,"font-size":11,"text-anchor":"end","class":"axis"});
    t.textContent=(ymax>=10?Math.round(yv):yv.toFixed(1))+(unit||"");svg.appendChild(t);
  }
  for(i=0;i<=4;i++){
    xv=xmin+xr*i/4;gx=sx(xv);
    svg.appendChild(el("line",{x1:gx,y1:H-PB,x2:gx,y2:H-PB+4,"class":"grid"}));
    t=el("text",{x:gx,y:H-PB+16,"font-size":11,"text-anchor":"middle","class":"axis"});
    t.textContent=xlab(xv);svg.appendChild(t);
  }
  svg.appendChild(el("line",{x1:PL,y1:PT,x2:PL,y2:H-PB,"class":"grid"}));
  // Window-reset markers, drawn UNDER the series: the usage line drops at these
  // instants because the 5h window rolled, not because usage fell. Without them
  // the sawtooth reads as "my usage went down", which is simply false.
  (marks||[]).forEach(function(m){
    if(m<xmin||m>xmax)return;
    var mx=sx(m);
    svg.appendChild(el("line",{x1:mx,y1:PT,x2:mx,y2:H-PB,"class":"reset"}));
  });
  // Projected trajectories. Dashed because they are guesses, not data; red past 100.
  // Two shapes:
  //   kind "to"   - runs to a specific future point (the 5h reset is only hours out,
  //                 so the domain above was widened to include it).
  //   kind "rate" - runs to the chart's right edge at a known %/sec. Used for the
  //                 WEEKLY: its reset is ~4 days out, and stretching the axis that far
  //                 would squash the real history into a sliver, so the line shows the
  //                 slope in view while the LABEL carries the projected-at-reset value.
  (projs||[]).forEach(function(pr){
    var x0=sx(pr.t0),y0=sy(pr.p0),x1,y1;
    if(pr.kind==="rate"){x1=sx(xmax);y1=sy(pr.p0+pr.rate*(xmax-pr.t0));}
    else{x1=sx(pr.t1);y1=sy(pr.p1);}
    svg.appendChild(el("path",{
      d:"M"+x0.toFixed(1)+" "+y0.toFixed(1)+"L"+x1.toFixed(1)+" "+y1.toFixed(1),
      "class":pr.over?(pr.cls+" over"):pr.cls}));
    var lt=el("text",{x:(x1-3).toFixed(1),y:(y1-6).toFixed(1),"font-size":11,
      "text-anchor":"end","class":pr.over?(pr.lcls+" over"):pr.lcls});
    lt.textContent=pr.lab;
    svg.appendChild(lt);
  });
  seriesList.forEach(function(s){
    var d="",pen=false,n=0;
    s.pts.forEach(function(p){if(p[1]!==null)n++;});
    s.pts.forEach(function(p){
      if(p[1]===null){pen=false;return;}
      d+=(pen?"L":"M")+sx(p[0]).toFixed(1)+" "+sy(p[1]).toFixed(1)+" ";pen=true;
    });
    if(d)svg.appendChild(el("path",{d:d,"class":s.cls}));
    // A 1-2 sample series cannot form a line and renders as a stray floating dash.
    // Dot sparse series so a couple of samples read as DATA rather than an artifact.
    if(n<=30&&s.dot){
      s.pts.forEach(function(p){
        if(p[1]===null)return;
        svg.appendChild(el("circle",{cx:sx(p[0]).toFixed(1),cy:sy(p[1]).toFixed(1),
          r:2.5,"class":s.dot}));
      });
    }
  });
}
function drawUsage(range){
  var svg=document.getElementById("usage-chart");clear(svg);
  var lo=(range==="h24")?D.bounds.h24:(range==="d7")?D.bounds.d7:-Infinity;
  function f(a){return (a||[]).filter(function(p){return p[0]>=lo;});}
  var marks=(D.resets||[]).filter(function(m){return m>=lo;});
  function lastOf(a){for(var j=a.length-1;j>=0;j--){if(a[j][1]!==null)return a[j];}return null;}
  var u5=f(D.usage),u7=f(D.usage7),projs=[];
  // 5h: reset is only hours away -> project all the way TO it (domain widens to fit).
  var pj5=project(D.now.pct,D.now.reset,WIN5),l5=lastOf(u5);
  if(pj5&&!pj5.early&&l5){
    projs.push({kind:"to",t0:l5[0],p0:l5[1],t1:D.now.reset,p1:pj5.proj,
                over:pj5.proj>100,cls:"proj",lcls:"projlab",
                lab:Math.round(pj5.proj)+"%"});
  }
  // Weekly: reset is ~4 days out. Drawing TO it would stretch the axis 4 days into
  // the future and squash the real history, so run the line at its true %/sec to the
  // chart edge and let the label carry the number that matters (% at the weekly reset).
  var pj7=project(D.now.pct7,D.now.reset7,WIN7),l7=lastOf(u7);
  if(pj7&&!pj7.early&&l7){
    var nowS=Date.now()/1000,start7=D.now.reset7-WIN7;
    var rate7=D.now.pct7/(nowS-start7);
    projs.push({kind:"rate",t0:l7[0],p0:l7[1],rate:rate7,
                over:pj7.proj>100,cls:"proj7",lcls:"projlab7",
                lab:Math.round(pj7.proj)+"% by "+DAYS[new Date(D.now.reset7*1000).getDay()]});
  }
  // yfloor 100: the axis always spans the whole cap, so 22% reads as "plenty of
  // headroom" instead of filling the chart the way an auto-scaled axis would. The
  // 100% gridline already says where the cap is -- no separate "limit" rule needed.
  drawChart(svg,[{pts:u5,cls:"series",dot:"dot"},
                 {pts:u7,cls:"series7",dot:"dot7"}],
            marks,"%",100,projs);
  var bs=document.querySelectorAll("#ranges button");
  for(var i=0;i<bs.length;i++)bs[i].className=(bs[i].getAttribute("data-range")===range)?"active":"";
}
function isDark(){return document.documentElement.getAttribute("data-theme")==="dark";}
function hmFill(val,max){
  // Heatmap cells are data-driven, so they cannot be pure CSS like the rest of the
  // chrome -- the ramp is picked per theme here. Light: pale->dark. Dark: INVERTED
  // (dark->bright), else a low-value cell would glow brightest against a dark page.
  if(val===null)return isDark()?"hsl(220,8%,26%)":"hsl(0,0%,88%)";
  var f=max?val/max:0;
  return isDark()?"hsl(210,75%,"+(20+f*45).toFixed(0)+"%)"
                 :"hsl(210,80%,"+(92-f*62).toFixed(0)+"%)";
}
function hmLegend(max){
  var box=document.getElementById("hm-legend");clear(box);
  function sw(bg){var e=document.createElement("span");e.className="sw";e.style.background=bg;return e;}
  function txt(x){var e=document.createElement("span");e.textContent=x;return e;}
  box.appendChild(txt("Low"));
  box.appendChild(sw(hmFill(max*0.05,max)));
  box.appendChild(sw(hmFill(max*0.5,max)));
  box.appendChild(sw(hmFill(max,max)));
  box.appendChild(txt("High"));
  box.appendChild(sw(hmFill(null,max)));
  box.appendChild(txt("no data"));
}
function drawHeatmap(){
  var svg=document.getElementById("heatmap");clear(svg);
  var g=D.heatmap,max=1,r,c,v;
  for(r=0;r<7;r++)for(c=0;c<24;c++){v=g[r][c];if(v!==null&&v>max)max=v;}
  var days=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],cw=20,ch=20,lx=34,ty=18;
  for(c=0;c<24;c+=3){var t=el("text",{x:lx+c*cw+cw/2,y:13,"font-size":12,"text-anchor":"middle","class":"axis"});t.textContent=c;svg.appendChild(t);}
  for(r=0;r<7;r++){
    var lbl=el("text",{x:lx-5,y:ty+r*ch+ch/2+4,"font-size":12,"text-anchor":"end","class":"axis"});
    lbl.textContent=days[r];svg.appendChild(lbl);
    for(c=0;c<24;c++){
      var val=g[r][c],tip;
      if(val===null)tip=days[r]+" "+c+":00 - no data";
      else tip=days[r]+" "+c+":00 - "+val.toFixed(0)+"% mean";
      var rect=el("rect",{x:lx+c*cw,y:ty+r*ch,width:cw-1,height:ch-1,fill:hmFill(val,max)});
      var ttl=el("title",{});ttl.textContent=tip;rect.appendChild(ttl);
      svg.appendChild(rect);
    }
  }
  hmLegend(max);
}
drawUsage("all");drawHeatmap();
var un=D.usage[D.usage.length-1];
document.getElementById("usage-now").textContent=un?(" - now "+Math.round(un[1])+"%"):"";
document.getElementById("meta").textContent="Generated "+new Date(D.generated*1000).toLocaleString();
document.getElementById("ranges").addEventListener("click",function(e){
  var r=e.target.getAttribute("data-range");if(r)drawUsage(r);
});
function setTheme(t){
  document.documentElement.setAttribute("data-theme",t);
  document.getElementById("theme").textContent=(t==="dark")?"Light":"Dark";
  try{localStorage.setItem("ccdash-theme",t);}catch(e){}
  drawHeatmap();
}
var savedTheme=null;
try{savedTheme=localStorage.getItem("ccdash-theme");}catch(e){}
var prefDark=window.matchMedia&&window.matchMedia("(prefers-color-scheme:dark)").matches;
setTheme(savedTheme||(prefDark?"dark":"light"));
document.getElementById("theme").addEventListener("click",function(){
  setTheme(isDark()?"light":"dark");
});
function fmtDur(s){
  s=Math.max(0,Math.floor(s));
  if(s>=86400)return Math.floor(s/86400)+"d "+Math.floor((s%86400)/3600)+"h";
  if(s>=3600)return Math.floor(s/3600)+"h "+Math.floor((s%3600)/60)+"m";
  return Math.floor(s/60)+"m";
}
function hhmm(ep){var d=new Date(ep*1000);return d.getHours()+":"+two(d.getMinutes());}
function project(pct,reset,win){
  // Honest, PERCENTAGE-based projection. claude-monitor ships forecast/status, but
  // both are token-based and report "limit hit" under --api (token counts come back
  // null), so using them would claim you are exhausted at 18%. Instead: the window
  // began at reset-win, so the elapsed fraction is known exactly; extrapolating the
  // current pct linearly over the window gives the projected % at reset, and when
  // that crosses 100 we can say WHEN it would land.
  if(pct===null||pct===undefined||reset===null||reset===undefined)return null;
  var now=Date.now()/1000,start=reset-win,e=(now-start)/win;
  if(e<=0.05)return {early:true};   // barely into the window -> pct/e explodes
  if(e>1)e=1;
  var out={proj:pct/e};
  if(out.proj>100&&pct>0){
    var exh=start+(100/pct)*(now-start);
    if(exh<reset)out.exhaust=exh;
  }
  return out;
}
var IC={
  clock:["M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13z","M8 4.5V8l2.5 1.5"],
  cal:["M2.5 3.5h11v10h-11z","M2.5 6.5h11","M5.5 2v3","M10.5 2v3"]
};
function icon(name){
  // Built with createElementNS (same NS literal the charts use) so the glyph is a
  // real SVG node; .ic strokes it with currentColor, so it themes for free.
  var s=el("svg",{"class":"ic","viewBox":"0 0 16 16"});
  (IC[name]||[]).forEach(function(d){s.appendChild(el("path",{d:d}));});
  return s;
}
function addQuotaRow(box,name,pct,reset,win,ic){
  if(pct===null||pct===undefined)return;
  var now=Date.now()/1000;
  var row=document.createElement("div");row.className="srow";
  function sp(cls,txt){var e=document.createElement("span");e.className=cls;e.textContent=txt;return e;}
  var lab=sp("sname",name);
  if(ic)lab.insertBefore(icon(ic),lab.firstChild);
  row.appendChild(lab);
  row.appendChild(sp("sval",Math.round(pct)+"%"));
  var bar=document.createElement("span");bar.className="sbar";
  var fill=document.createElement("span");
  fill.className=(pct>=80)?"sfill hot":"sfill";
  fill.style.width=Math.min(100,Math.max(0,pct))+"%";
  bar.appendChild(fill);row.appendChild(bar);
  var txt=(reset!==null&&reset!==undefined)?("resets in "+fmtDur(reset-now)):"";
  var p=project(pct,reset,win);
  if(p&&p.exhaust!==undefined)txt+=" - projected to hit 100% at "+hhmm(p.exhaust);
  else if(p&&p.early)txt+=" - too early to project";
  else if(p)txt+=" - on track (projected "+Math.round(p.proj)+"% at reset)";
  row.appendChild(sp("smeta",txt));
  box.appendChild(row);
}
function statusCard(){
  var box=document.getElementById("status");clear(box);
  addQuotaRow(box,"5-hour",D.now.pct,D.now.reset,WIN5,"clock");
  addQuotaRow(box,"Weekly",D.now.pct7,D.now.reset7,WIN7,"cal");
  if(!box.firstChild)box.appendChild(document.createTextNode(
    "No current quota data yet - it appears after the next poll."));
}
statusCard();
// Countdowns and the projection are computed against the LIVE clock, so the card
// stays truthful as this static page ages between the ~5min regenerations.
setInterval(statusCard,20000);
"""


def render_dashboard(records, now):
    """Full self-contained dashboard HTML string (DASH-02/03/04/06, D-02/D-03/D-07).

    Drops non-numeric records via history_numeric FIRST (review finding 1) so only
    numeric-safe data reaches the embedded payload and chart math. Empty (no input
    or everything dropped) -> a minimal "collecting history" page. Otherwise embeds
    one payload (usage pairs filtered client-side per D-03, heatmap, ROLLING 24h/7d
    bounds, generated stamp) via _embed_json and inline JS that draws the charts with
    plain DOM SVG -- no CDN, no library (DASH-06).

    Range bounds are ROLLING windows (now-24h, now-7d), not calendar boundaries: a
    "day" that resets at local midnight and a "week" that resets on Monday hide the
    most recent activity right after a reset. Rolling also mirrors how Claude's own
    quota windows work. local_bounds() stays calendar-based for the tray trend rows.
    """
    records = history_numeric(records)
    if not records:
        return _DASH_EMPTY
    payload = {
        "usage": with_gaps([[int(r["t"]), r["pct"]] for r in records]),
        "usage7": with_gaps(usage7_series(records)),
        "resets": reset_marks(records),
        "now": latest_state(records),
        "heatmap": heatmap_buckets(records),
        "bounds": {"h24": int(now - 86400), "d7": int(now - 7 * 86400)},
        "generated": int(now),
    }
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        + _DASH_META_REFRESH +
        "<title>Claude Code - Usage Dashboard</title>"
        "<style>" + _DASH_STYLE + "</style></head>"
        "<body>" + _DASH_BODY + "<script>const D = " + _embed_json(payload) + ";"
        + _DASH_JS + "</script></body></html>"
    )


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
    # official --api payload: percentages only, token counts null -> still valid
    # (tokens optional), not a crash. usage_rows renders "% used" for this shape.
    now_plus = int(time.time()) + 7380
    official = parse_usage(
        json.dumps(
            {
                "limits": {
                    "five_hour": {
                        "tokens_used": None,
                        "token_limit": None,
                        "used_percentage": 5.0,
                        "resets_at_epoch": now_plus,
                    }
                },
                "local": {"burn_rate_tokens_per_minute": 12000.0},
            }
        )
    )
    assert official is not None and official["tokens_used"] is None
    assert official["used_percentage"] == 5.0
    # no seven_day block -> weekly degrades to None, five_hour data still valid.
    assert official["seven_day_pct"] is None and official["seven_day_reset"] is None
    # seven_day (weekly cap) is captured when the --api payload carries it.
    weekly = parse_usage(
        json.dumps(
            {
                "limits": {
                    "five_hour": {
                        "tokens_used": None,
                        "token_limit": None,
                        "used_percentage": 18.0,
                        "resets_at_epoch": now_plus,
                    },
                    "seven_day": {
                        "used_percentage": 40.0,
                        "resets_at_epoch": now_plus + 86400,
                    },
                },
                "local": {"burn_rate_tokens_per_minute": 1000.0},
            }
        )
    )
    assert weekly["seven_day_pct"] == 40.0
    assert weekly["seven_day_reset"] == now_plus + 86400
    # junk in the weekly block degrades that block to None -- it must NOT discard
    # the five_hour payload (which would blank the tray's usage rows entirely).
    junk7 = parse_usage(
        json.dumps(
            {
                "limits": {
                    "five_hour": {
                        "tokens_used": None,
                        "token_limit": None,
                        "used_percentage": 7.0,
                        "resets_at_epoch": now_plus,
                    },
                    "seven_day": {"used_percentage": "lots", "resets_at_epoch": None},
                },
                "local": {"burn_rate_tokens_per_minute": 1000.0},
            }
        )
    )
    assert junk7 is not None and junk7["used_percentage"] == 7.0
    assert junk7["seven_day_pct"] is None and junk7["seven_day_reset"] is None
    # a non-numeric token count (not just null) is still rejected as junk.
    assert (
        parse_usage(
            json.dumps(
                {
                    "limits": {
                        "five_hour": {
                            "tokens_used": "lots",
                            "token_limit": None,
                            "used_percentage": 5.0,
                            "resets_at_epoch": now_plus,
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
    # weekly countdown is days-aware (fmt_countdown would say "resets in 98h 0m").
    assert fmt_countdown_wk(352800) == "week resets in 4d 2h"
    assert fmt_countdown_wk(7380) == "week resets in 2h 3m"
    assert fmt_countdown_wk(0) == "week resets now"
    # over-limit percent renders raw, never clamped to 100.
    assert round(473.5) == 474
    assert build_label({"used_percentage": 47}, 2) == "47% 2!"
    assert build_label({"used_percentage": 83}, 2) == "83%! 2!"
    assert build_label({"used_percentage": 47}, 0) == "47%"
    assert build_label(None, 2) == "2!"
    assert build_label(None, 0) == ""
    # a HOT WEEKLY warns even when the 5h window is cool -- the 5h number still
    # leads, but the '!' fires so a near-exhausted weekly cap cannot pass silently.
    assert build_label({"used_percentage": 10, "seven_day_pct": 95}, 0) == "10%!"
    assert build_label({"used_percentage": 10, "seven_day_pct": 40}, 0) == "10%"
    # missing weekly (older CLI / no --api) behaves exactly as before.
    assert build_label({"used_percentage": 10, "seven_day_pct": None}, 0) == "10%"

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
    # reset carries the 5h window end; pct7/reset7 are None when the payload that
    # produced `hu` had no seven_day block (the pre---api / older-CLI shape).
    assert history_record(hu, now0) == {
        "t": now0,
        "pct": 473.5,
        "tokens_used": 417000,
        "token_limit": 88000,
        "burn": 315615.2,
        "reset": now0 + 7380,
        "pct7": None,
        "reset7": None,
    }
    # weekly fields survive into the record when the payload carries them.
    hu7 = dict(hu, seven_day_pct=40.0, seven_day_reset=now0 + 86400)
    r7 = history_record(hu7, now0)
    assert r7["pct7"] == 40.0 and r7["reset7"] == now0 + 86400
    # a legacy record (no reset/pct7/reset7 keys at all) must still pass the
    # numeric sanitizer -- the new fields are optional, never required.
    assert history_numeric([{"t": now0, "pct": 1.0, "burn": 2.0}]) == [
        {"t": now0, "pct": 1.0, "burn": 2.0}
    ]
    # retention: a 40-day-old record is dropped, a 1-day-old record is kept (days=30).
    assert history_keep({"t": now0 - 40 * 86400}, now0, 30) is False
    assert history_keep({"t": now0 - 1 * 86400}, now0, 30) is True
    # tolerant parse: the corrupt middle line is skipped; the two good ones survive in order.
    good1 = {"t": now0, "pct": 10.0}
    good2 = {"t": now0 + 1, "pct": 20.0}
    blob = json.dumps(good1) + "\nnot json {oops\n" + json.dumps(good2) + "\n"
    assert parse_history(blob) == [good1, good2]
    # tolerant parse also drops valid-JSON-but-wrong-shape lines (bare scalar, null,
    # array, object with no "t", object with non-numeric "t") so prune_history's
    # history_keep(rec["t"]) can never raise and kill the poll thread.
    junk = "42\nnull\n[1, 2]\n{}\n" + json.dumps({"t": "nope"}) + "\n\"hi\"\n"
    assert parse_history(json.dumps(good1) + "\n" + junk + json.dumps(good2) + "\n") == [good1, good2]

    # --- trend logic (Phase 03) ---
    # local_bounds: day_start is local midnight, week_start is local Monday 00:00.
    now_lb = int(time.time())
    day_start, week_start = local_bounds(now_lb)
    assert datetime.datetime.fromtimestamp(day_start).hour == 0
    assert datetime.datetime.fromtimestamp(day_start).minute == 0
    assert datetime.datetime.fromtimestamp(week_start).weekday() == 0
    assert datetime.datetime.fromtimestamp(week_start).hour == 0
    assert week_start <= day_start <= now_lb
    # sparkline: 24 chars; lowest column -> floor glyph, highest -> top glyph, an
    # interior hour with no samples -> gap; empty input -> all gaps.
    now_sp = 1_700_000_000
    recs_sp = [
        {"t": now_sp - 23 * 3600, "pct": 5.0},  # bucket 0 (oldest), lowest mean
        {"t": now_sp, "pct": 90.0},  # bucket 23 (current hour), highest mean
    ]
    spark = trend_sparkline(recs_sp, now_sp)
    assert len(spark) == 24
    assert spark[0] == SPARK_GLYPHS[0]
    assert spark[23] == SPARK_GLYPHS[-1]
    assert spark[12] == SPARK_GAP  # interior empty hour stays a gap
    assert trend_sparkline([], now_sp) == SPARK_GAP * 24
    # flat window (all equal pct): no ZeroDivisionError, every column at the floor.
    flat = [{"t": now_sp - h * 3600, "pct": 42.0} for h in range(24)]
    fspark = trend_sparkline(flat, now_sp)
    assert all(c == SPARK_GLYPHS[0] for c in fspark)
    # burn: raw per-minute mean(100,200)=150 -> *60 = 9000 tok/hr; empty window None.
    burn_recs = [{"t": 100, "burn": 100.0}, {"t": 200, "burn": 200.0}]
    assert trend_burn(burn_recs, 0, 1000) == 9000.0
    assert trend_burn(burn_recs, 1000, 2000) is None
    # peak hour: later hour has the higher mean burn -> it wins; empty input None.
    base_ph = datetime.datetime(2024, 1, 1)
    ep = lambda h: int(base_ph.replace(hour=h).timestamp())
    peak_recs = [
        {"t": ep(3), "burn": 10.0}, {"t": ep(3) + 60, "burn": 20.0},   # hour 3, mean 15
        {"t": ep(15), "burn": 100.0}, {"t": ep(15) + 60, "burn": 200.0},  # hour 15, mean 150
    ]
    assert trend_peak_hour(peak_recs) == (15, 9000.0)
    assert trend_peak_hour([]) is None
    # build_trend_rows: a corrupt record NEVER reaches the trend math. Without the
    # history_numeric sanitizer the string `burn` raises TypeError inside trend_burn,
    # the NaN `burn` renders "nan/hr", and t=1e18 raises OSError in fromtimestamp.
    # `now` is real (not a fixed epoch) so local_bounds' day/week windows contain the
    # records; span is 2h > TREND_MIN_SPAN so real rows replace the collecting state.
    now_bt = time.time()
    clean_bt = [
        {"t": now_bt - 7200, "pct": 10.0, "burn": 100.0},
        {"t": now_bt - 3600, "pct": 30.0, "burn": 200.0},
        {"t": now_bt, "pct": 50.0, "burn": 300.0},
    ]
    corrupt_bt = [
        {"t": now_bt - 5400, "pct": 20.0, "burn": "lots"},  # string burn -> TypeError
        {"t": now_bt - 1800, "pct": 20.0, "burn": float("nan")},  # NaN -> "nan/hr"
        {"t": 1e18, "pct": 20.0, "burn": 50.0},  # far-future t -> OSError
    ]
    rows_clean = build_trend_rows(clean_bt, now_bt)
    assert rows_clean is not None and len(rows_clean) == 3
    assert rows_clean[1].startswith("today ") and "nan" not in rows_clean[1]
    assert rows_clean[2].startswith("peak hour: ")
    # THE regression guard: corrupt records are dropped, so the mixed history yields
    # byte-identical rows to the clean history alone -- and raises nothing.
    mixed_bt = [clean_bt[0], corrupt_bt[0], clean_bt[1], corrupt_bt[1], clean_bt[2], corrupt_bt[2]]
    assert build_trend_rows(mixed_bt, now_bt) == rows_clean
    # all records corrupt -> everything dropped -> collecting state, not a crash.
    assert build_trend_rows(corrupt_bt, now_bt) is None
    assert build_trend_rows([], now_bt) is None

    # --- dashboard logic (Phase 04) ---
    # _embed_json: the raw <, >, & are gone; letters survive; the < escape is present.
    emb = _embed_json({"x": "</" + "script><b>&"})
    assert "<" not in emb and ">" not in emb and "&" not in emb
    assert "evil" not in emb  # sanity: none of our literal here
    assert "b" in emb and "\\u003c" in emb
    # history_numeric: drops string-pct, string-burn, and missing-burn; keeps good in order.
    ok1 = {"t": 1, "pct": 10.0, "burn": 5.0}
    ok2 = {"t": 2, "pct": 20.0, "burn": 6.0}
    bad_pct = {"t": 3, "pct": "x", "burn": 5.0}
    bad_burn = {"t": 4, "pct": 10.0, "burn": "x"}
    no_burn = {"t": 5, "pct": 10.0}
    assert history_numeric([ok1, bad_pct, bad_burn, no_burn, ok2]) == [ok1, ok2]
    # non-finite floats (NaN/Inf json.loads accepts) and out-of-range t are ALL
    # dropped so int(t)/fromtimestamp() downstream can never raise (WR-01).
    nan_t = {"t": float("nan"), "pct": 1.0, "burn": 1.0}
    inf_pct = {"t": 1, "pct": float("inf"), "burn": 1.0}
    inf_burn = {"t": 1, "pct": 1.0, "burn": float("inf")}
    far_t = {"t": 1e18, "pct": 1.0, "burn": 1.0}
    assert history_numeric([nan_t, inf_pct, inf_burn, far_t, ok1]) == [ok1]
    # heatmap_buckets: MEAN USAGE % (not burn) -- two records local Monday 15:xx with
    # pct 10,20 -> grid[0][15]=15.0; an untouched cell is None; grid is 7x24.
    mon = datetime.datetime(2024, 1, 1, 15)  # 2024-01-01 is a Monday
    hm = heatmap_buckets([
        {"t": int(mon.timestamp()), "pct": 10.0, "burn": 100.0},
        {"t": int(mon.replace(minute=30).timestamp()), "pct": 20.0, "burn": 200.0},
    ])
    assert len(hm) == 7 and all(len(row) == 24 for row in hm)
    assert hm[0][15] == 15.0
    assert hm[2][3] is None
    # reset_marks: unique + sorted; legacy records with no `reset` contribute nothing.
    assert reset_marks(
        [
            {"t": 1, "reset": 300},
            {"t": 2, "reset": 300},
            {"t": 3, "reset": 100},
            {"t": 4},
        ]
    ) == [100, 300]
    assert reset_marks([{"t": 1, "pct": 1.0}]) == []
    # with_gaps: a hole wider than GAP_MAX gets a None break so the renderer lifts the
    # pen instead of drawing a straight line across an outage (which reads as a real
    # trend). Tight samples are left untouched.
    assert with_gaps([[0, 1.0], [60, 2.0], [3000, 3.0]], 300) == [
        [0, 1.0],
        [60, 2.0],
        [60, None],
        [3000, 3.0],
    ]
    assert with_gaps([[0, 1.0], [60, 2.0]], 300) == [[0, 1.0], [60, 2.0]]
    assert with_gaps([], 300) == []
    # usage7_series: only records carrying a numeric weekly pct.
    assert usage7_series([{"t": 5, "pct7": 40.0}, {"t": 6}, {"t": 7, "pct7": None}]) == [
        [5, 40.0]
    ]
    # latest_state: newest by MAX t (not file order); legacy fields -> None.
    ls = latest_state(
        [
            {"t": 9, "pct": 3.0, "reset": 99, "pct7": 40.0, "reset7": 88},
            {"t": 1, "pct": 1.0, "reset": 11},
        ]
    )
    assert ls == {"pct": 3.0, "reset": 99, "pct7": 40.0, "reset7": 88}
    assert latest_state([{"t": 1, "pct": 1.0}]) == {
        "pct": 1.0,
        "reset": None,
        "pct7": None,
        "reset7": None,
    }
    assert latest_state([])["pct"] is None
    # T-04-01 regression guard for the NEWER payload fields. history_numeric only
    # validates t/pct/burn, so a record can be "numeric-clean" by its lights while
    # carrying hostile junk in pct7/reset/reset7. Those fields reach the inline
    # <script> through usage7_series / reset_marks / latest_state, which each filter
    # with _is_num -- this asserts that, so adding a payload field without a filter
    # cannot silently reopen the injection hole.
    _evil = "</" + "script><script>evil"
    _hostile = {
        "t": now0,
        "pct": 10.0,
        "burn": 5.0,
        "pct7": _evil,
        "reset": _evil,
        "reset7": _evil,
    }
    assert history_numeric([_hostile]) == [_hostile]  # it really does pass that gate
    assert usage7_series([_hostile]) == []
    assert reset_marks([_hostile]) == []
    assert latest_state([_hostile])["pct7"] is None
    assert latest_state([_hostile])["reset"] is None
    _hpage = render_dashboard([_hostile], now0)
    assert "evil" not in _hpage
    assert _hpage.count("</" + "script>") == 1
    # render_dashboard: good record -> real page (doctype + embedded const D marker).
    now_dash = int(time.time())
    page = render_dashboard([{"t": now_dash, "pct": 42.0, "burn": 10.0}], now_dash)
    assert isinstance(page, str) and "doctype" in page and "const D" in page
    # empty input and all-non-numeric input both fall to the empty-state page.
    assert "Collecting usage history" in render_dashboard([], now_dash)
    assert "Collecting usage history" in render_dashboard(
        [{"t": now_dash, "pct": "x", "burn": "y"}], now_dash
    )
    # a lone NaN/Inf/out-of-range record is dropped too -> empty-state page, not a
    # crash from int(t)/fromtimestamp() (WR-01).
    assert "Collecting usage history" in render_dashboard(
        [{"t": float("nan"), "pct": 1.0, "burn": 1.0}], now_dash
    )
    assert "Collecting usage history" in render_dashboard(
        [{"t": 1e18, "pct": 1.0, "burn": 1.0}], now_dash
    )
    # injection (review finding 1 + T-04-01): a crafted string-pct record is dropped so its
    # value never reaches the dataset, and the page holds exactly ONE script-closing sequence.
    evil = "</" + "script><script>evil"
    inj = render_dashboard(
        [{"t": now_dash, "pct": 42.0, "burn": 10.0}, {"t": now_dash + 1, "pct": evil, "burn": 1.0}],
        now_dash,
    )
    assert "evil" not in inj
    assert inj.count("</" + "script>") == 1
    # self-containment (review finding 4, DASH-06): no <link, no src=, no https://; the only
    # http:// is the SVG namespace -- stripping it leaves none behind.
    assert "<link" not in page and "src=" not in page and "https://" not in page
    assert page.replace("http://www.w3.org/2000/svg", "").find("http://") == -1
    # sess_should_notify: the whole of NOTIF-02's de-dupe (D-03), and D-04's "always fire".
    assert sess_should_notify(None, "waiting") is True  # first seen already waiting
    assert sess_should_notify("running", "waiting") is True  # SESS-01
    assert sess_should_notify("waiting", "done") is True  # SESS-02
    assert sess_should_notify("waiting", "waiting") is False  # THE de-dupe (NOTIF-02)
    assert sess_should_notify("done", "done") is False
    assert sess_should_notify("waiting", "running") is False  # running never notifies
    assert sess_should_notify("done", "end") is False  # end never notifies

    # --- the project() port: ALERT-02/03 + D-05 -------------------------------------
    # Synthetic epochs, never time.time(): these must be deterministic and must not go
    # stale. Same 10 cases the JS copy is expected to produce -- if you change one copy,
    # change the other and re-run these.
    R = 1_000_000  # a 5h window's reset epoch
    S = R - WIN5  # ...so the window started here
    assert project(None, R, WIN5, S + 9000) is None  # no data
    assert project(50.0, None, WIN5, S + 9000) is None  # no reset epoch
    assert project("x", R, WIN5, S + 9000) is None  # non-numeric -> None, not TypeError
    assert project(50.0, R, WIN5, S + 900) == {"early": True}  # e == 0.05 exactly
    assert "proj" in project(50.0, R, WIN5, S + 901)  # e just over the guard -> projects
    assert project(50.0, R, WIN5, S - 5000) == {"early": True}  # negative e (clock skew)
    # THE boundary. 50% at half window projects to exactly 100.0 -- and gets NO exhaust
    # key, because project() sets it only when the projection STRICTLY exceeds 100. This
    # pair is what makes alert_due's membership test the only safe way to ask the question.
    assert abs(project(50.0, R, WIN5, S + WIN5 // 2)["proj"] - 100.0) < 1e-9
    assert "exhaust" not in project(50.0, R, WIN5, S + WIN5 // 2)
    over = project(60.0, R, WIN5, S + WIN5 // 2)  # 60% at half window -> 120%, runs out early
    assert abs(over["proj"] - 120.0) < 1e-9
    assert abs(over["exhaust"] - (S + 15000.0)) < 1e-6 and over["exhaust"] < R
    assert abs(project(10.0, R, WIN5, S + WIN5 // 2)["proj"] - 20.0) < 1e-9  # coasting
    # Window already over -> e clamps to 1 -> the projection degrades to the current pct.
    assert abs(project(42.0, R, WIN5, R + 3600)["proj"] - 42.0) < 1e-9
    assert "exhaust" not in project(42.0, R, WIN5, R + 3600)
    assert project(0.0, R, WIN5, S + WIN5 // 2)["proj"] == 0.0  # pct 0, no div-by-zero
    R7 = 2_000_000
    S7 = R7 - WIN7  # same function, 7d window
    assert abs(project(80.0, R7, WIN7, S7 + WIN7 // 2)["proj"] - 160.0) < 1e-9
    # The INVARIANT the two exhaust guards exist to hold, swept across the domain rather
    # than poked at one point: an exhaust epoch is present ONLY when the projection
    # strictly exceeds 100 AND that epoch lands before the reset. This is what forbids
    # Pitfall 7's false alert at exactly 100%, and it is the only thing covering the
    # `exh < reset` guard -- which matters for an EXPIRED window, where e clamps to 1 but
    # (now - start) does not, so a barely-over-100 pct can otherwise project an exhaust
    # LATER than the reset it is supposed to precede.
    for _pct in range(0, 201):
        for _n in range(1, 41):  # sweep the window, and well past its reset
            _p = project(float(_pct), R, WIN5, S + WIN5 * _n // 20)
            if _p and "exhaust" in _p:
                assert _p["proj"] > 100 and _p["exhaust"] < R
    assert len(hhmm(0)) == 5 and ":" in hhmm(0)  # HH:MM; the value is TZ-dependent (D-08)

    # --- the arm/re-arm state machine: ALERT-04 + D-06 + D-07 ------------------------
    now = S + WIN5 // 2
    hot = project(60.0, R, WIN5, now)  # 120%, exhaust 2500s out -> actionable
    cold = project(10.0, R, WIN5, now)  # 20% -> coasting
    assert alert_due(hot, now) is True
    assert alert_due(cold, now) is False
    assert alert_due({"early": True}, now) is False  # early guard is silent for free
    assert alert_due(None, now) is False  # no data -> silent
    assert alert_should_fire(None, R, hot, now) is True  # never armed + hot -> FIRE
    assert alert_should_fire(R, R, hot, now) is False  # already fired THIS window (D-06)
    # The window rolled: a changed reset epoch IS a new window, so the cap re-arms. This
    # single line is ALERT-04 / ROADMAP SC4 -- nothing else pins the re-arm.
    assert alert_should_fire(R, R + WIN5, hot, now) is True
    assert alert_should_fire(None, R, cold, now) is False  # coasting -> nothing fires
    assert alert_should_fire(None, R, {"early": True}, now) is False
    assert alert_should_fire(None, R, None, now) is False
    assert alert_should_fire(None, None, None, now) is False  # 7d absent on an older CLI
    # D-05's lead: an exhaust 60s away is not actionable; 15min+ away is.
    soon = {"proj": 200.0, "exhaust": now + 60}
    assert alert_should_fire(None, R, soon, now) is False
    assert alert_should_fire(None, R, {"proj": 200.0, "exhaust": now + 901}, now) is True
    # D-07, and the ONLY thing that would catch someone "helpfully" adding a special case:
    # an already-exhausted cap has an exhaust epoch in the PAST, so the same lead
    # subtraction rejects it. No special case, no code.
    dead = project(200.0, R, WIN5, R + WIN5 // 2)  # expired AND over 100
    assert dead["exhaust"] < R + WIN5 // 2
    assert alert_should_fire(None, R, dead, R + WIN5 // 2) is False
    print("ok")


class Monitor:
    def __init__(self):
        self.sessions = {}  # session_id -> {dir,status,pane,tmux,cwd}
        self.usage = None  # latest parse_usage() dict, or None if unavailable
        self.usage_misses = 0  # consecutive failed polls; >= threshold -> unavailable
        self.trends = None  # cached trend row strings, or None (collecting/empty state)
        self.dash_ready = False  # True after the first successful dashboard write (gates the menu item)

        self.notif_slots = {}  # ("sess", sid) / ("cap", "5h") -> daemon notification id
        self.notif_acts = {}  # daemon notification id -> a click-action tuple (focus | dash)
        # Cap key ("5h" / "7d") -> the resets_at_epoch of the window in which that cap last
        # alerted. D-06: one alert per cap per window. In-memory only, and correctly lost on
        # restart -- a restart legitimately re-arms every cap. No file, no persistence.
        self.alert_armed = {}
        self.notif = None
        try:
            # Constructed HERE, on the Gtk main thread, ON PURPOSE. A GDBusProxy captures
            # the thread-default main context at construction and dispatches every signal
            # and async callback there. Built inside poll_loop instead, popups would still
            # appear but ActionInvoked would be queued into a context with no running main
            # loop -- clicks would silently never fire, with no error to grep for.
            #
            # What the try is actually for: constructing the proxy does NOT raise when the
            # notification daemon is absent (it returns a proxy whose get_name_owner() is
            # None; that failure surfaces later at call time as a GLib.Error). It DOES raise
            # when the SESSION BUS ITSELF is unreachable -- a bare TTY, a stripped systemd
            # unit. That is the NOTIF-04 case: self.notif stays None, every emit is a no-op,
            # and the tray keeps polling, rendering and serving session events regardless.
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

    # menu click (Gtk main thread): open the already-written dashboard, ZERO history
    # I/O (D-05). pathlib .resolve().as_uri() builds a correct file:// URI that escapes
    # spaces/special chars, unlike string concat (review finding 3); stdlib-only.
    def open_dashboard(self, *_):
        webbrowser.open(pathlib.Path(DASH_PATH).resolve().as_uri())

    def emit_notif(self, key, kind, title, body, action, urgency):
        """The single shared notification emit path (NOTIF-01). Safe from BOTH threads.

        Called from Monitor.handle (Gtk main thread) and from poll_loop (daemon thread).
        Uses the ASYNC proxy.call() in both cases: the synchronous call form would block the
        Gtk main loop on a bus round-trip (PROJECT.md forbids it), and async is verified to
        work from a worker thread. The reply callback always lands on the Gtk main thread, so
        notif_slots/notif_acts are only ever mutated from one thread -- no lock needed.

        `key` names the notification SLOT (D-03): one per session, one per quota cap.
        Handing the slot's previous id back as replaces_id makes the daemon overwrite that
        popup in place instead of stacking a second one. N live sessions -> at most N
        popups, ever.

        `action` is what a click should do, stashed against the returned id for
        on_notif_signal to dispatch (NOTIF-03 / D-09).

        ponytail: the daemon caps a source at 3 retained notifications and destroys the
        oldest beyond that (MAX_NOTIFICATIONS_PER_SOURCE). Banners still display; only the
        message-list backlog is capped. Accepted -- 4+ simultaneously-waiting sessions is
        not the common case and the tray rows remain the complete picture. Upgrade path:
        collapse multiple sessions into one summary notification if it ever bites.
        """
        if self.notif is None or not notif_allowed(kind):
            return
        prev = self.notif_slots.get(key, 0)
        args = GLib.Variant(
            "(susssasa{sv}i)",
            (
                "claude-monitor",  # app_name
                prev,  # replaces_id: 0 = new slot, else overwrite that popup in place
                ICON,  # app_icon: the tray's own icon, for free consistency
                title,  # summary (NOT markup-parsed -- this is where session-derived
                #          strings belong; the body IS parsed as Pango markup)
                body,  # body
                ["default", "Focus"],  # "default" makes a click on the BODY emit
                #                        ActionInvoked; its label is never drawn. Omit it
                #                        and a body click falls through to source.open().
                {"urgency": GLib.Variant("y", urgency)},  # D-02, and the ONLY hint we pass
                -1,  # expire_timeout: gnome-shell never reads it. Inert.
            ),
        )

        def done(proxy, res, _):
            try:
                nid = proxy.call_finish(res).unpack()[0]
            except Exception:
                return  # daemon vanished mid-call -> no popup this time (NOTIF-04)
            # Re-store on EVERY reply, not just the first. A clicked notification is
            # destroyed daemon-side and dropped from its table, so a later Notify carrying
            # that stale replaces_id allocates a FRESH id. Keep the dead one and popups
            # start stacking the moment the user interacts once.
            self.notif_slots[key] = nid
            self.notif_acts[nid] = action

        try:
            self.notif.call("Notify", args, Gio.DBusCallFlags.NONE, -1, None, done, None)
        except Exception:
            return  # degrade to "no popup", never a raise (NOTIF-04)

    def on_notif_signal(self, _proxy, _sender, signame, params):
        """Notification click dispatcher (NOTIF-03 / D-09). Runs on the GTK MAIN THREAD.

        No GLib.idle_add anywhere in here: a GDBusProxy dispatches on the main context
        captured at construction, which is the Gtk main thread (see __init__). focus() and
        open_dashboard therefore run exactly where the existing on_click menu handler
        already runs them today. The extra hop would be dead code.

        ActionInvoked is a BROADCAST on /org/freedesktop/Notifications -- we receive it for
        EVERY application's notifications, not just ours. The notif_acts lookup is the trust
        boundary: without it, a click on an unrelated app's popup would drive focus() and
        yank a tmux pane into view.
        """
        try:
            if signame == "ActionInvoked":
                act = self.notif_acts.get(params[0])
                if act is None:
                    return  # not one of ours -> ignore (broadcast signal)
                if act[0] == "focus":
                    self.focus(act[1], act[2])  # NOTIF-03
                elif act[0] == "dash":
                    self.open_dashboard()  # D-09
            if signame in ("ActionInvoked", "NotificationClosed"):
                # Clicked or dismissed -> the daemon destroyed it. Drop our bookkeeping so
                # the next emit for that slot starts a clean notification.
                self.notif_acts.pop(params[0], None)
                for k, v in list(self.notif_slots.items()):
                    if v == params[0]:
                        del self.notif_slots[k]
        except Exception:
            return  # runs inside a GLib callback -- a raise here can kill the signal source

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
        # separator dividing the usage block from the trend block (D-11)
        self.menu.append(Gtk.SeparatorMenuItem.new())
        for row in self.trend_rows():
            mi = Gtk.MenuItem.new_with_label(row)
            mi.set_sensitive(False)
            self.menu.append(mi)
        # sensitive action item (like "Quit monitor"): greyed until the first HTML
        # write has happened, then opens the pre-written dashboard (DASH-01).
        dash = Gtk.MenuItem.new_with_label("Open Usage Dashboard")
        dash.connect("activate", self.open_dashboard)
        dash.set_sensitive(self.dash_ready)
        self.menu.append(dash)
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
        # Official --api usage has no absolute token counts -> show "% used"
        # only; the P90 fallback path still carries tokens -> "72k / 88k (82%)".
        if u["tokens_used"] is not None and u["token_limit"] is not None:
            used = "%s / %s (%d%%)" % (
                fmt_tokens(u["tokens_used"]),
                fmt_tokens(u["token_limit"]),
                round(u["used_percentage"]),
            )
        else:
            used = "%d%% used" % round(u["used_percentage"])
        rows = [
            used,
            fmt_countdown(u["resets_at_epoch"] - time.time()),
            "burn: %s tok/hr" % fmt_tokens(round(u["burn_rate_per_min"] * 60)),
        ]
        # Weekly cap: only rendered when the payload actually carried it, so an
        # older CLI / non---api poll degrades to the original three rows.
        if u.get("seven_day_pct") is not None:
            rows.append("week: %d%% used" % round(u["seven_day_pct"]))
            if u.get("seven_day_reset") is not None:
                rows.append(fmt_countdown_wk(u["seven_day_reset"] - time.time()))
        return rows

    def trend_rows(self):
        """Insensitive trend-row strings from the self.trends cache (no file I/O).

        None -> the single collecting-history empty-state row (D-12); otherwise the
        ready-to-render rows compute_trends built (sparkline, today/week, peak hour).
        """
        if self.trends is None:
            return ["trends: collecting history..."]
        return self.trends

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

    def compute_trends(self, now):
        """Read history once (OFF the Gtk main thread) and cache trend rows (D-05/D-07).

        The ONLY place trend history is read. Routes through the corruption-tolerant
        parse_history and swallows OSError (missing/unwritable file -> keep last-known
        trends, never raise on the poll thread). The rows themselves are built by the
        pure build_trend_rows, which sanitizes through history_numeric -- the SAME
        choke point render_dashboard uses -- so a corrupt record (string/NaN burn,
        far-future t) is dropped before any trend math and cannot raise here. Yields
        None until the retained history spans TREND_MIN_SPAN seconds (collecting, D-12).
        """
        try:
            with open(HISTORY_PATH, errors="replace") as f:
                records = parse_history(f.read())
        except OSError:
            return  # degrade to last-known trends; never crash the poll thread
        # ponytail: single list rebind, read-only in the Gtk redraw (mirrors self.usage) -- no lock.
        self.trends = build_trend_rows(records, now)

    def write_dashboard(self, now):
        """Read history OFF the Gtk main thread, render the dashboard, atomic-write it (D-04).

        The ONLY place the dashboard reads history (single source, DASH-05): routes
        through parse_history, then re-applies history_keep(now, HISTORY_DAYS) so
        "full retained history" means the retained window even if an opportunistic
        prune silently failed (review finding 2). render_dashboard additionally
        drops non-numeric records. Writes atomically (temp + os.replace, mirroring
        prune_history) and flips dash_ready on first success.

        ponytail: the whole body is wrapped in a broad `except Exception` -- broader
        than append_history/prune_history on purpose. A malformed record, a render
        bug, or an OS error must all degrade to "dashboard just isn't updated this
        tick" rather than killing the poll thread (HIST-03 / T-04-03).
        """
        tmp = None
        try:
            with open(HISTORY_PATH, errors="replace") as f:
                records = parse_history(f.read())
            records = [r for r in records if history_keep(r, now, HISTORY_DAYS)]
            html = render_dashboard(records, now)
            os.makedirs(DASH_DIR, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=DASH_DIR)
            with os.fdopen(fd, "w") as f:
                f.write(html)
            os.replace(tmp, DASH_PATH)
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
        old = s.get("status")  # MUST be read before the update below overwrites it --
        # read it after and old == event always, so sess_should_notify never fires.
        # a fresh event re-arms the "!" -- unless serve() found you were already
        # looking at this pane, in which case pre-acknowledge it (no alert).
        s.update(
            dir=d, status=event, pane=pane, tmux=tmux, cwd=cwd,
            acked=bool(msg.get("_onscreen")),
        )
        # SESS-01 / SESS-02. Fires on EVERY waiting/done transition -- the pre-ack above
        # gates only the "!" badge, never this (D-04). `d` (the project dir) goes in the
        # TITLE: the summary is not markup-parsed, the body is, and a repo can be named
        # anything (T-05-04). The two bodies are fixed literals, interpolating nothing.
        # ponytail: gnome-shell retains at most 3 notifications per source and drops the
        # oldest beyond that -- banners still show, only the message-list backlog is capped.
        # 4+ sessions waiting at once is not the common case and the tray rows stay complete.
        # Upgrade path: coalesce into one summary notification if it ever bites.
        if sess_should_notify(old, event):
            self.emit_notif(
                ("sess", sid),  # one slot per session: a later transition replaces in place (D-03)
                event,  # "waiting" / "done" -- two of notif_allowed's four keys
                d,
                "Waiting for input" if event == "waiting" else "Session finished",
                ("focus", pane, tmux),  # NOTIF-03: same outcome as clicking the tray row
                URGENCY_CRITICAL if event == "waiting" else URGENCY_NORMAL,  # D-02
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
    """Socket thread: hook events -> Monitor.handle on the Gtk main thread.

    ponytail: the per-connection body is wrapped in a broad `except Exception`, mirroring
    poll_loop. This thread is the ONLY thing feeding session events, so ANY raise escaping
    one connection kills it permanently and the tray goes silently deaf to every session
    forever -- the same failure shape as the corrupt-record bug (260713-fry), and what
    NOTIF-04 is actually protecting. The guard is INSIDE the while, around the connection
    body: one bad connection costs one connection, not the thread. Made OBSERVABLE rather
    than silent -- traceback.print_exc() puts the full traceback in the journal on every
    failing connection. accept() stays OUTSIDE the try: a raise there is the listening
    socket itself dying, which is unrecoverable and has nothing useful to retry.

    Monitor.handle is a new source of raises now that it emits notifications, but it runs
    on the Gtk main thread via idle_add -- a raise there kills the idle source, not this
    thread. emit_notif's own guards cover it.
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
                conn.close()  # keep the close nested inside: a recv failure must not leak an fd
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
                    msg["_onscreen"] = looking_at(
                        msg.get("pane", ""), msg.get("tmux", "")
                    )
                GLib.idle_add(mon.handle, msg)
        except Exception:
            traceback.print_exc()  # loud and repeated; the thread survives regardless
            continue


def poll_loop(mon):
    """Daemon-thread loop: fetch usage off the Gtk main loop, marshal the result
    back via GLib.idle_add (mirrors serve()'s pattern), then sleep.

    All history file I/O lives here (never in apply_usage/main, which run on the
    Gtk main thread): a successful poll appends one record before the idle_add,
    and the store is pruned once at startup then opportunistically thereafter.

    ponytail: the whole while-body is wrapped in a broad `except Exception` --
    mirroring write_dashboard. This thread is the ONLY thing polling usage, computing
    trends and regenerating the dashboard, so ANY raise escaping one iteration kills
    it permanently and the tray silently freezes until restart (exactly the corrupt-
    record bug). A blanket swallow could mask a real bug, so the degradation is made
    OBSERVABLE instead of silent: traceback.print_exc() writes the full traceback to
    stderr (the journal) on EVERY failing iteration -- a persistent failure is loud and
    repeated, a transient one costs a single poll. Upgrade path: surface the failure in
    the tray label if a real bug ever hides in here. time.sleep stays OUTSIDE the try
    so a failing iteration is still throttled and cannot hot-spin.
    """
    prune_history(time.time())
    last_prune = time.time()
    last_trend = 0.0  # 0 -> first iteration recomputes immediately (no 5-min blank window)
    last_dash = 0.0  # 0 -> generate the dashboard file immediately at startup
    while True:
        try:
            usage = fetch_usage()
            now = time.time()
            if usage is not None:
                append_history(history_record(usage, now))
                # Predictive quota alerts (ALERT-02/03/04). Rides the tick that already
                # happened: every value comes out of the `usage` dict parse_usage just
                # produced, so this adds no poll, no interval, no thread, no data source.
                # emit_notif is async and safe from this daemon thread (its reply lands on
                # the Gtk main thread), so nothing here blocks the Gtk main loop and no
                # idle_add is needed. A raise is caught by the blanket except below.
                for cap, pct, reset, win, title in (
                    ("5h", usage["used_percentage"], usage["resets_at_epoch"], WIN5, "5-hour quota"),
                    # .get(): the 7d block is absent on an older CLI. project()'s _is_num
                    # guard and alert_should_fire's own turn that into silence, not a
                    # crash -- so no second, redundant guard here.
                    ("7d", usage.get("seven_day_pct"), usage.get("seven_day_reset"), WIN7, "7-day quota"),
                ):
                    p = project(pct, reset, win, now)
                    if alert_should_fire(mon.alert_armed.get(cap), reset, p, now):
                        # p["proj"] and p["exhaust"] are safe to read UNGUARDED here: the
                        # predicate returned True, which required "exhaust" in p, which
                        # only happens when the projection exceeds 100. A defensive .get()
                        # would only hide a broken predicate.
                        mon.emit_notif(
                            ("cap", cap),  # D-03: one slot per cap, so a later alert
                            cap,  # overwrites this popup in place instead of stacking
                            title,  # D-08: the cap is the title...
                            # ...and the body carries the severity and the actionable
                            # clock reading. Both interpolated values are numbers we
                            # computed ourselves (a rounded float, a strftime output), so
                            # no payload-derived string reaches the markup-parsed body
                            # (T-05-07). round(): "Projected 140.237%" helps nobody.
                            "Projected %d%% at reset -- runs out ~%s"
                            % (round(p["proj"]), hhmm(p["exhaust"])),
                            ("dash",),  # D-09: the dashboard is where you go to look
                            URGENCY_NORMAL,  # informational; it need not block the screen
                        )
                        mon.alert_armed[cap] = reset  # arm: silent until this reset changes
            # recompute trends off the Gtk main thread, AFTER the append (so the fresh
            # record is included) and BEFORE the idle_add (so this poll's redraw sees it).
            if now - last_trend >= TREND_INTERVAL:
                mon.compute_trends(now)
                last_trend = now
            # regenerate the dashboard HTML off the Gtk main thread on the same cadence.
            # last_dash = now UNCONDITIONALLY: write_dashboard swallows its own errors, so
            # a transient failure is throttled ~5min not hot-retried (mirrors last_trend).
            if now - last_dash >= DASH_INTERVAL:
                mon.write_dashboard(now)
                last_dash = now
            GLib.idle_add(mon.apply_usage, usage)
            if now - last_prune >= PRUNE_INTERVAL:
                prune_history(now)
                last_prune = now
        except Exception:
            traceback.print_exc()  # loud + repeated: the thread survives, the failure doesn't hide
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
