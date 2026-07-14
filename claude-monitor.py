#!/usr/bin/env python3
"""Claude Code monitor: GNOME top-bar tray indicator.

Claude Code hooks push one-line JSON events to a unix socket:
    {event, session_id, cwd, message, pane, tmux}
event in {running, waiting, done, end}. Each session's status shows in the tray menu;
clicking one focuses its tmux pane and raises the Ghostty window. A poll thread also
tracks quota usage, appends history, alerts on projected exhaustion, and regenerates a
dashboard page.
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
# Theme icon name; override with CLAUDE_TRAY_ICON. "claude-desktop" ships with the app.
ICON = os.environ.get("CLAUDE_TRAY_ICON", "claude-desktop")
# WM_CLASS of your terminal, used to raise its window on click (X11 / wmctrl).
GHOSTTY_CLASS = os.environ.get("CLAUDE_TRAY_WM_CLASS", "com.mitchellh.ghostty")

# Absolute on purpose: the CLI shares the bare name "claude-monitor" with this helper.
USAGE_CLI = os.path.expanduser("~/.local/bin/claude-monitor")
# Override with CLAUDE_TRAY_PLAN (max5, max20, custom, pro, or "" for the CLI's saved
# default -- which is nondeterministic, it flips as different --plan values are used).
PLAN = os.environ.get("CLAUDE_TRAY_PLAN", "custom")
# Seconds between polls (the CLI itself takes ~5-10s). Override: CLAUDE_TRAY_POLL_INTERVAL.
try:
    POLL_INTERVAL = int(os.environ.get("CLAUDE_TRAY_POLL_INTERVAL", "15"))
except ValueError:
    POLL_INTERVAL = 15  # bad env -> default
POLL_TIMEOUT = 15  # subprocess seconds
# High-usage badge threshold (percent). Hardcoded on purpose: do NOT add an env lookup.
USAGE_THRESHOLD = 80

# Raw freedesktop D-Bus, NOT Gio.Notification: gnome-shell's GTK path does
# lookup_app(appId + ".desktop") and drops the notification when none is installed.
NOTIF_BUS = "org.freedesktop.Notifications"
NOTIF_PATH = "/org/freedesktop/Notifications"
# gnome-shell 46 destructures Notify's expire_timeout and never reads it (banner life is
# a hardcoded 4000ms), so urgency is the only lifetime knob.
URGENCY_NORMAL = 1  # 4s banner, then GNOME's notification list
URGENCY_CRITICAL = 2  # no dismiss timer; sticks until clicked


def notif_allowed(kind):
    """Mute gate. `kind` is one of "waiting", "done", "5h", "7d". Currently always open."""
    return True  # ponytail: seam only; a config-driven mute replaces this body.


def sess_should_notify(old_status, new_status):
    """True iff the session just CHANGED into "waiting"/"done". Pure.
    A session sitting in "waiting" re-sends it on every hook event; only a transition
    passes. Takes no on-screen argument by design -- that gates the "!" badge, not this.
    """
    return new_status in ("waiting", "done") and old_status != new_status


# Quota-window lengths (seconds). The dashboard JS carries the same literals; move both.
WIN5 = 18000  # 5 hours
WIN7 = 604800  # 7 days
ALERT_LEAD = 15 * 60  # an exhaust nearer than this is not actionable -> no alert


def project(pct, reset, win, now):
    """Extrapolate `pct` linearly over the window to its projected % at `reset`. Pure.
    None (no/bad data), {"early": True} (too soon), or {"proj": float} -- which also
    carries an "exhaust" epoch, but ONLY when the projection strictly exceeds 100.
    The JS copy in _DASH_JS is a deliberate duplicate (it recomputes against a live
    browser clock as the static page ages); change both.
    """
    # Stricter than the JS, which coerces: this makes a 7d cap absent on an older CLI
    # degrade to silence instead of raising.
    if not _is_num(pct) or not _is_num(reset):
        return None
    start = reset - win
    e = (now - start) / float(win)  # win is a nonzero constant -> no div-by-zero
    if e <= 0.05:
        # pct/e explodes this early. Also the clock-skew guard: negative e lands here.
        return {"early": True}
    if e > 1:
        e = 1.0  # window already over -> the projection degrades to the current pct
    out = {"proj": pct / e}
    if out["proj"] > 100 and pct > 0:  # `pct > 0` guards the 100.0 / pct below
        exh = start + (100.0 / pct) * (now - start)
        if exh < reset:
            out["exhaust"] = exh
    return out


def hhmm(epoch):
    """Local wall-clock HH:MM for an epoch."""
    return time.strftime("%H:%M", time.localtime(epoch))


def alert_due(p, now):
    """Is `p` (a project() result) worth alerting on, given the ALERT_LEAD floor? Pure.
    Membership-tests "exhaust" rather than reading p["proj"]: project() sets the key only
    above 100, so testing the projection first would KeyError at exactly 100.0. An
    exhausted cap (exhaust in the past) and {"early": True} fall out silent for free.
    """
    return bool(p) and "exhaust" in p and (p["exhaust"] - now) >= ALERT_LEAD


def alert_should_fire(armed_reset, reset, p, now):
    """One alert per cap per window, re-armed when the window rolls. Pure.
    `armed_reset` is the reset epoch of the window this cap last alerted in (None if
    never). A reset epoch identifies the window, so a changed epoch re-arms the cap.
    """
    if not _is_num(reset):
        return False  # the 7d cap is absent on an older CLI -> silence
    if armed_reset == reset:
        return False  # already alerted in THIS window
    # ponytail: no lead-step re-fires ("30m left"); add a second armed threshold if needed.
    return alert_due(p, now)


HISTORY_PATH = os.path.expanduser("~/.claude/usage-history.jsonl")  # append-only jsonl
# Retention window in days. Override with CLAUDE_TRAY_HISTORY_DAYS.
try:
    HISTORY_DAYS = int(os.environ.get("CLAUDE_TRAY_HISTORY_DAYS", "30"))
except ValueError:
    HISTORY_DAYS = 30  # bad env -> default
PRUNE_INTERVAL = 6 * 3600  # opportunistic-prune cadence (seconds)

# Derived cache file, so it lives under the XDG cache dir, not ~/.claude/.
DASH_DIR = os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "claude-tray"
)
DASH_PATH = os.path.join(DASH_DIR, "dashboard.html")

# The only intended non-ASCII in this file. Index 0 = lowest, -1 = highest.
SPARK_GLYPHS = "▁▂▃▄▅▆▇█"
SPARK_GAP = " "  # hours with no samples (keeps columns time-aligned)
TREND_INTERVAL = 5 * 60  # trend recompute throttle in poll_loop (seconds)
TREND_MIN_SPAN = 3600  # min history span (s) before real rows replace empty state
DASH_INTERVAL = 5 * 60  # dashboard-regen throttle in poll_loop (seconds)
# The page is a static file, so an open tab would otherwise never update. ponytail:
# meta-refresh over a JS poller.
_DASH_META_REFRESH = f"<meta http-equiv=\"refresh\" content=\"{DASH_INTERVAL}\">"


def parse_usage(stdout):
    """Parse claude-monitor JSON stdout into a normalized usage dict, or None.
    Parses stdout regardless of exit status: the CLI exits 11 while printing valid JSON
    at limit-hit. None on any parse failure or missing limits.five_hour.
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
            # Weekly cap; often the binding one. Optional: older CLIs omit the block.
            "seven_day_pct": seven.get("used_percentage"),
            "seven_day_reset": seven.get("resets_at_epoch"),
        }
    except Exception:
        return None
    def is_num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    # None here stops round()/epoch math raising inside the Gtk redraw, which would silently
    # kill the countdown timer source.
    if not all(is_num(u[k]) for k in ("used_percentage", "resets_at_epoch", "burn_rate_per_min")):
        return None
    # Token counts are legitimately null under --api (percentages only); strings are junk.
    for k in ("tokens_used", "token_limit"):
        if u[k] is not None and not is_num(u[k]):
            return None
    # Weekly is secondary: junk there degrades that block, never the 5h payload.
    for k in ("seven_day_pct", "seven_day_reset"):
        if not is_num(u[k]):
            u[k] = None
    return u


def fetch_usage():
    """Shell out to the CLI (fixed arg list, never shell=True) and parse stdout.
    None on any subprocess/OS error, so the daemon poll thread can never die.
    """
    # --api: official OAuth numbers, but percentages only (tokens come back null). --plan
    # stays as the fallback basis when that endpoint is stale/absent.
    cmd = [USAGE_CLI, "--output", "json", "--once", "--api"]
    if PLAN:
        cmd += ["--plan", PLAN]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=POLL_TIMEOUT)
    except (subprocess.SubprocessError, OSError):
        return None  # timeout, missing CLI, non-executable -> unavailable
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
    """Weekly reset countdown: 352800 -> 'week resets in 4d 2h'; under a day falls back
    to h/m. Separate from fmt_countdown, whose 'Xh Ym' would render '98h 0m' for a week.
    """
    secs = int(secs)
    if secs <= 0:
        return "week resets now"
    if secs >= 86400:
        return "week resets in %dd %dh" % (secs // 86400, (secs % 86400) // 3600)
    return "week resets in %dh %dm" % (secs // 3600, (secs % 3600) // 60)


def build_label(usage, attention):
    """Tray label: usage % leads, attention count follows ('47% 2!', '83%! 2!', '2!', '').
    `attention` counts sessions needing you. '!' fires when EITHER cap is above
    USAGE_THRESHOLD, but the leading number is always the 5h one.
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
    """Compact history record. `t` is the poll time, `burn` the RAW per-minute rate."""
    return {
        "t": int(now),
        "pct": usage["used_percentage"],
        "tokens_used": usage["tokens_used"],
        "token_limit": usage["token_limit"],
        "burn": usage["burn_rate_per_min"],
        # Optional: older records lack these keys, so every reader must tolerate that.
        "reset": usage["resets_at_epoch"],
        "pct7": usage.get("seven_day_pct"),
        "reset7": usage.get("seven_day_reset"),
    }


def history_keep(rec, now, days):
    """Retention predicate: True when rec is within the `days` window."""
    return rec["t"] >= now - days * 86400


def parse_history(text):
    """Tolerant loader: JSON objects with a numeric "t", in order. Skips blank, unparseable
    (a half-written line from a killed process) and wrong-shape lines. Every reader routes
    through here, so a downstream history_keep(rec["t"]) cannot raise on garbage.
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
    """Append one record as a JSON line. OSError -> history just doesn't persist."""
    try:
        with open(HISTORY_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        return


def prune_history(now):
    """Drop records older than HISTORY_DAYS, rewriting HISTORY_PATH atomically: temp file
    + os.replace, never truncate-in-place, so there is no data-loss window.
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
    """(day_start, week_start) epochs: local midnight today, local Monday 00:00.
    Local, not UTC, so the boundaries match how a person reads "today".
    """
    dt = datetime.datetime.fromtimestamp(now)
    day_start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - datetime.timedelta(days=day_start.weekday())
    return int(day_start.timestamp()), int(week_start.timestamp())


def trend_sparkline(records, now):
    """24-char block sparkline of mean pct per hour; column 0 = 23h ago, 23 = now.
    Heights auto-scale to the window's own min..max; empty hours render SPARK_GAP.
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
            out.append(SPARK_GLYPHS[0])  # flat window -> floor, and no ZeroDivisionError
        else:
            idx = round((m - lo) / span * (len(SPARK_GLYPHS) - 1))
            out.append(SPARK_GLYPHS[idx])
    return "".join(out)


def trend_burn(records, start, end):
    """Mean burn rate in tok/hr over [start, end), or None. Converts per-min -> per-hr."""
    vals = [rec["burn"] for rec in records if start <= rec["t"] < end]
    if not vals:
        return None
    return sum(vals) / len(vals) * 60


def trend_peak_hour(records):
    """(hour, tok/hr) for the busiest local hour-of-day, or None. Ties -> lowest hour."""
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
    """History records -> trend row strings. Gtk-free pure core of compute_trends.
    Sanitizes through history_numeric first, so no corrupt value reaches the trend math.
    None while the history spans less than TREND_MIN_SPAN (collecting state).
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
    """JSON-serialize obj, escaping <, >, & so no value can break out of the inline
    <script> that embeds it. Unicode escapes, so the JS still parses the const.
    """
    return (
        json.dumps(obj)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def history_numeric(records):
    """Keep only records whose t, pct and burn are all finite numbers. Order preserved.
    Rejects NaN/Infinity (json.loads accepts both) and bounds t to before 2100, so a
    far-future record -- which history_keep never prunes -- cannot break regeneration.
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
    """7x24 grid (dow Mon..Sun x hour 0..23) of mean quota % *consumed in that hour*.

    `pct` is cumulative within the rolling 5h window, so averaging it directly just
    shows how late in a window a sample landed. Here we take the per-sample rise
    instead. A drop, a first sample, or a sampling gap wider than GAP_MAX all mean
    we cannot difference against the previous sample, and the `pct` we see is itself
    the consumption to attribute. Per-hour rises are summed per calendar day, then
    averaged across the days that hour actually saw data.

    Empty buckets stay None so "no data" stays distinct from a genuine 0%.
    """
    grid = [[None] * 24 for _ in range(7)]
    acc = {}  # (dow, hour) -> {date: consumed%}
    prev = None  # (t, pct) of previous sample
    for rec in sorted(records, key=lambda r: r["t"]):
        dt = datetime.datetime.fromtimestamp(rec["t"])
        pct = rec["pct"]
        if prev and pct >= prev[1] and rec["t"] - prev[0] <= GAP_MAX:
            delta = pct - prev[1]
        else:
            delta = pct
        prev = (rec["t"], pct)
        day = acc.setdefault((dt.weekday(), dt.hour), {})
        day[dt.date()] = day.get(dt.date(), 0.0) + max(0.0, delta)
    for (dow, hour), days in acc.items():
        grid[dow][hour] = sum(days.values()) / len(days)
    return grid


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def reset_marks(records):
    """Sorted unique 5h reset epochs, so the chart can mark where usage-% drops because
    the window rolled, not because usage fell. Legacy records contribute nothing.
    """
    return sorted({int(r["reset"]) for r in records if _is_num(r.get("reset"))})


GAP_MAX = 300  # seconds; a hole wider than this is a data gap, not a trend


def with_gaps(series, max_gap=GAP_MAX):
    """Insert [t, None] pen-up breaks where samples are >max_gap apart, so the renderer
    breaks the line across an outage instead of drawing a trend that never happened.
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
    """[[t, weekly_pct], ...] for records carrying a numeric `pct7`, in order."""
    return [[int(r["t"]), r["pct7"]] for r in records if _is_num(r.get("pct7"))]


def latest_state(records):
    """Newest record's quota fields (by max t, not file order), for the status card.
    Missing/legacy fields come back None so the card renders only what it knows.
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
# Its one http:// is the SVG namespace passed to createElementNS: an identifier, never
# fetched. No <link, no src=, no https:// -- --selfcheck asserts all of that.
def _brand_icon_uri():
    """base64 data: URI for the installed Claude icon, or "" when absent. Embedded, and
    applied via CSS background-image, because the page may carry no `src=` (see above).
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

# One string, so the [data-theme=dark] rule and the prefers-color-scheme fallback that
# both interpolate it cannot drift apart.
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
    # currentColor so glyphs theme for free; no xmlns, which inline SVG does not need.
    ".ic{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:1.5;"
    "stroke-linecap:round;stroke-linejoin:round;vertical-align:-2px;"
    "margin-right:.35em;flex:none}"
    "h2 .ic{opacity:.75}"
    ".ttl{display:flex;align-items:center;min-width:0}"
    + _BRAND_CSS
)

_IC_GAUGE = (  # no xmlns on purpose -- see .ic above
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
      else tip=days[r]+" "+c+":00 - "+val.toFixed(1)+"% quota used (mean/hour)";
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
    """Full self-contained dashboard HTML; the empty-state page when there is no data.
    Range bounds are ROLLING windows (now-24h, now-7d), not calendar ones, which would
    hide the most recent activity right after a reset.
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
    # --- parse_usage ---
    u = parse_usage(json.dumps(sample))
    assert u is not None and u["used_percentage"] == 473.5
    assert parse_usage("") is None
    assert parse_usage("not json") is None
    assert parse_usage(json.dumps({"limits": {}})) is None
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
    assert official["seven_day_pct"] is None and official["seven_day_reset"] is None
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
    # --- formatting + label ---
    assert fmt_tokens(417000) == "417k"
    assert fmt_tokens(88000) == "88k"
    assert fmt_tokens(18936912) == "18.9M"
    assert fmt_tokens(round(u["burn_rate_per_min"] * 60)) == "18.9M"
    assert fmt_countdown(7380) == "resets in 2h 3m"
    assert fmt_countdown(0) == "resets now"
    assert fmt_countdown_wk(352800) == "week resets in 4d 2h"
    assert fmt_countdown_wk(7380) == "week resets in 2h 3m"
    assert fmt_countdown_wk(0) == "week resets now"
    assert round(473.5) == 474  # over-limit percent renders raw, never clamped
    assert build_label({"used_percentage": 47}, 2) == "47% 2!"
    assert build_label({"used_percentage": 83}, 2) == "83%! 2!"
    assert build_label({"used_percentage": 47}, 0) == "47%"
    assert build_label(None, 2) == "2!"
    assert build_label(None, 0) == ""
    assert build_label({"used_percentage": 10, "seven_day_pct": 95}, 0) == "10%!"
    assert build_label({"used_percentage": 10, "seven_day_pct": 40}, 0) == "10%"
    assert build_label({"used_percentage": 10, "seven_day_pct": None}, 0) == "10%"

    # --- history logic ---
    now0 = int(time.time())
    hu = {
        "tokens_used": 417000,
        "token_limit": 88000,
        "used_percentage": 473.5,
        "resets_at_epoch": now0 + 7380,
        "burn_rate_per_min": 315615.2,
    }
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
    hu7 = dict(hu, seven_day_pct=40.0, seven_day_reset=now0 + 86400)
    r7 = history_record(hu7, now0)
    assert r7["pct7"] == 40.0 and r7["reset7"] == now0 + 86400
    assert history_numeric([{"t": now0, "pct": 1.0, "burn": 2.0}]) == [
        {"t": now0, "pct": 1.0, "burn": 2.0}
    ]
    assert history_keep({"t": now0 - 40 * 86400}, now0, 30) is False
    assert history_keep({"t": now0 - 1 * 86400}, now0, 30) is True
    good1 = {"t": now0, "pct": 10.0}
    good2 = {"t": now0 + 1, "pct": 20.0}
    blob = json.dumps(good1) + "\nnot json {oops\n" + json.dumps(good2) + "\n"
    assert parse_history(blob) == [good1, good2]
    junk = "42\nnull\n[1, 2]\n{}\n" + json.dumps({"t": "nope"}) + "\n\"hi\"\n"
    assert parse_history(json.dumps(good1) + "\n" + junk + json.dumps(good2) + "\n") == [good1, good2]

    # --- trend logic ---
    now_lb = int(time.time())
    day_start, week_start = local_bounds(now_lb)
    assert datetime.datetime.fromtimestamp(day_start).hour == 0
    assert datetime.datetime.fromtimestamp(day_start).minute == 0
    assert datetime.datetime.fromtimestamp(week_start).weekday() == 0
    assert datetime.datetime.fromtimestamp(week_start).hour == 0
    assert week_start <= day_start <= now_lb
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
    flat = [{"t": now_sp - h * 3600, "pct": 42.0} for h in range(24)]
    fspark = trend_sparkline(flat, now_sp)
    assert all(c == SPARK_GLYPHS[0] for c in fspark)
    burn_recs = [{"t": 100, "burn": 100.0}, {"t": 200, "burn": 200.0}]
    assert trend_burn(burn_recs, 0, 1000) == 9000.0
    assert trend_burn(burn_recs, 1000, 2000) is None
    base_ph = datetime.datetime(2024, 1, 1)
    ep = lambda h: int(base_ph.replace(hour=h).timestamp())
    peak_recs = [
        {"t": ep(3), "burn": 10.0}, {"t": ep(3) + 60, "burn": 20.0},   # hour 3, mean 15
        {"t": ep(15), "burn": 100.0}, {"t": ep(15) + 60, "burn": 200.0},  # hour 15, mean 150
    ]
    assert trend_peak_hour(peak_recs) == (15, 9000.0)
    assert trend_peak_hour([]) is None
    # `now` must be real, so local_bounds' day/week windows contain the records.
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
    mixed_bt = [clean_bt[0], corrupt_bt[0], clean_bt[1], corrupt_bt[1], clean_bt[2], corrupt_bt[2]]
    assert build_trend_rows(mixed_bt, now_bt) == rows_clean
    assert build_trend_rows(corrupt_bt, now_bt) is None
    assert build_trend_rows([], now_bt) is None

    # --- dashboard logic ---
    emb = _embed_json({"x": "</" + "script><b>&"})
    assert "<" not in emb and ">" not in emb and "&" not in emb
    assert "evil" not in emb
    assert "b" in emb and "\\u003c" in emb
    ok1 = {"t": 1, "pct": 10.0, "burn": 5.0}
    ok2 = {"t": 2, "pct": 20.0, "burn": 6.0}
    bad_pct = {"t": 3, "pct": "x", "burn": 5.0}
    bad_burn = {"t": 4, "pct": 10.0, "burn": "x"}
    no_burn = {"t": 5, "pct": 10.0}
    assert history_numeric([ok1, bad_pct, bad_burn, no_burn, ok2]) == [ok1, ok2]
    nan_t = {"t": float("nan"), "pct": 1.0, "burn": 1.0}
    inf_pct = {"t": 1, "pct": float("inf"), "burn": 1.0}
    inf_burn = {"t": 1, "pct": 1.0, "burn": float("inf")}
    far_t = {"t": 1e18, "pct": 1.0, "burn": 1.0}
    assert history_numeric([nan_t, inf_pct, inf_burn, far_t, ok1]) == [ok1]
    mon = datetime.datetime(2024, 1, 1, 15)  # 2024-01-01 is a Monday
    t0 = int(mon.timestamp())
    hm = heatmap_buckets([
        {"t": t0, "pct": 10.0, "burn": 100.0},
        {"t": t0 + 60, "pct": 20.0, "burn": 200.0},
    ])
    assert len(hm) == 7 and all(len(row) == 24 for row in hm)
    assert hm[0][15] == 20.0  # 10 (first sample) + 10 rise -- consumed, not mean of 10/20
    assert hm[2][3] is None
    # a drop means the 5h window rolled: the new pct is fresh consumption, not a -35 rise
    tue = int(datetime.datetime(2024, 1, 2, 9).timestamp())
    hm = heatmap_buckets([
        {"t": tue, "pct": 40.0},
        {"t": tue + 60, "pct": 5.0},
        {"t": tue + 7 * 86400, "pct": 30.0},  # same weekday+hour, next week
    ])
    assert hm[1][9] == 37.5  # mean of day1 (40+5) and day2 (30), not their sum
    assert reset_marks(
        [
            {"t": 1, "reset": 300},
            {"t": 2, "reset": 300},
            {"t": 3, "reset": 100},
            {"t": 4},
        ]
    ) == [100, 300]
    assert reset_marks([{"t": 1, "pct": 1.0}]) == []
    assert with_gaps([[0, 1.0], [60, 2.0], [3000, 3.0]], 300) == [
        [0, 1.0],
        [60, 2.0],
        [60, None],
        [3000, 3.0],
    ]
    assert with_gaps([[0, 1.0], [60, 2.0]], 300) == [[0, 1.0], [60, 2.0]]
    assert with_gaps([], 300) == []
    assert usage7_series([{"t": 5, "pct7": 40.0}, {"t": 6}, {"t": 7, "pct7": None}]) == [
        [5, 40.0]
    ]
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
    # --- script-injection guards ---
    # history_numeric validates t/pct/burn only, so junk can ride in pct7/reset/reset7;
    # each reader must filter it with _is_num.
    _evil = "</" + "script><script>evil"
    _hostile = {
        "t": now0,
        "pct": 10.0,
        "burn": 5.0,
        "pct7": _evil,
        "reset": _evil,
        "reset7": _evil,
    }
    assert history_numeric([_hostile]) == [_hostile]  # it does pass that gate
    assert usage7_series([_hostile]) == []
    assert reset_marks([_hostile]) == []
    assert latest_state([_hostile])["pct7"] is None
    assert latest_state([_hostile])["reset"] is None
    _hpage = render_dashboard([_hostile], now0)
    assert "evil" not in _hpage
    assert _hpage.count("</" + "script>") == 1
    now_dash = int(time.time())
    page = render_dashboard([{"t": now_dash, "pct": 42.0, "burn": 10.0}], now_dash)
    assert isinstance(page, str) and "doctype" in page and "const D" in page
    assert "Collecting usage history" in render_dashboard([], now_dash)
    assert "Collecting usage history" in render_dashboard(
        [{"t": now_dash, "pct": "x", "burn": "y"}], now_dash
    )
    assert "Collecting usage history" in render_dashboard(
        [{"t": float("nan"), "pct": 1.0, "burn": 1.0}], now_dash
    )
    assert "Collecting usage history" in render_dashboard(
        [{"t": 1e18, "pct": 1.0, "burn": 1.0}], now_dash
    )
    evil = "</" + "script><script>evil"
    inj = render_dashboard(
        [{"t": now_dash, "pct": 42.0, "burn": 10.0}, {"t": now_dash + 1, "pct": evil, "burn": 1.0}],
        now_dash,
    )
    assert "evil" not in inj
    assert inj.count("</" + "script>") == 1
    # self-containment: the only http:// is the SVG namespace.
    assert "<link" not in page and "src=" not in page and "https://" not in page
    assert page.replace("http://www.w3.org/2000/svg", "").find("http://") == -1

    # --- session-notification de-dupe ---
    assert sess_should_notify(None, "waiting") is True
    assert sess_should_notify("running", "waiting") is True
    assert sess_should_notify("waiting", "done") is True
    assert sess_should_notify("waiting", "waiting") is False
    assert sess_should_notify("done", "done") is False
    assert sess_should_notify("waiting", "running") is False
    assert sess_should_notify("done", "end") is False

    # --- project() ---
    # Synthetic epochs, never time.time(): deterministic, and they cannot go stale.
    R = 1_000_000  # a 5h window's reset epoch
    S = R - WIN5  # ...so the window started here
    assert project(None, R, WIN5, S + 9000) is None
    assert project(50.0, None, WIN5, S + 9000) is None
    assert project("x", R, WIN5, S + 9000) is None  # non-numeric -> None, not TypeError
    assert project(50.0, R, WIN5, S + 900) == {"early": True}  # e == 0.05 exactly
    assert "proj" in project(50.0, R, WIN5, S + 901)
    assert project(50.0, R, WIN5, S - 5000) == {"early": True}  # negative e (clock skew)
    # exactly 100.0 gets NO exhaust key -- the pair alert_due's membership test rides on.
    assert abs(project(50.0, R, WIN5, S + WIN5 // 2)["proj"] - 100.0) < 1e-9
    assert "exhaust" not in project(50.0, R, WIN5, S + WIN5 // 2)
    over = project(60.0, R, WIN5, S + WIN5 // 2)
    assert abs(over["proj"] - 120.0) < 1e-9
    assert abs(over["exhaust"] - (S + 15000.0)) < 1e-6 and over["exhaust"] < R
    assert abs(project(10.0, R, WIN5, S + WIN5 // 2)["proj"] - 20.0) < 1e-9
    assert abs(project(42.0, R, WIN5, R + 3600)["proj"] - 42.0) < 1e-9  # expired -> e = 1
    assert "exhaust" not in project(42.0, R, WIN5, R + 3600)
    assert project(0.0, R, WIN5, S + WIN5 // 2)["proj"] == 0.0  # pct 0, no div-by-zero
    R7 = 2_000_000
    S7 = R7 - WIN7  # same function, 7d window
    assert abs(project(80.0, R7, WIN7, S7 + WIN7 // 2)["proj"] - 160.0) < 1e-9
    # Swept invariant: an exhaust epoch exists ONLY above 100, and always before the reset.
    for _pct in range(0, 201):
        for _n in range(1, 41):  # sweep the window, and well past its reset
            _p = project(float(_pct), R, WIN5, S + WIN5 * _n // 20)
            if _p and "exhaust" in _p:
                assert _p["proj"] > 100 and _p["exhaust"] < R
    assert len(hhmm(0)) == 5 and ":" in hhmm(0)  # the value itself is TZ-dependent

    # --- the arm/re-arm state machine ---
    now = S + WIN5 // 2
    hot = project(60.0, R, WIN5, now)  # 120%, exhaust 2500s out -> actionable
    cold = project(10.0, R, WIN5, now)  # 20% -> coasting
    assert alert_due(hot, now) is True
    assert alert_due(cold, now) is False
    assert alert_due({"early": True}, now) is False
    assert alert_due(None, now) is False
    assert alert_should_fire(None, R, hot, now) is True  # never armed + hot -> fire
    assert alert_should_fire(R, R, hot, now) is False  # already fired THIS window
    assert alert_should_fire(R, R + WIN5, hot, now) is True  # window rolled -> re-armed
    assert alert_should_fire(None, R, cold, now) is False
    assert alert_should_fire(None, R, {"early": True}, now) is False
    assert alert_should_fire(None, R, None, now) is False
    assert alert_should_fire(None, None, None, now) is False  # 7d absent on an older CLI
    soon = {"proj": 200.0, "exhaust": now + 60}
    assert alert_should_fire(None, R, soon, now) is False  # under the lead floor
    assert alert_should_fire(None, R, {"proj": 200.0, "exhaust": now + 901}, now) is True
    dead = project(200.0, R, WIN5, R + WIN5 // 2)  # expired AND over 100
    assert dead["exhaust"] < R + WIN5 // 2
    assert alert_should_fire(None, R, dead, R + WIN5 // 2) is False
    print("ok")


class Monitor:
    def __init__(self):
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
        webbrowser.open(pathlib.Path(DASH_PATH).resolve().as_uri())

    def emit_notif(self, key, kind, title, body, action, urgency):
        """Shared notification emit path, safe from both threads (async proxy.call()).
        `key` is the slot (one per session, one per cap): its previous id goes back as
        replaces_id, so the daemon overwrites that popup instead of stacking. `action` is
        stashed against the returned id for on_notif_signal.
        ponytail: gnome-shell retains only 3 per source; collapse into one summary if that
        ever bites.
        """
        if self.notif is None or not notif_allowed(kind):
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
        self.ind.set_label(build_label(self.usage, attention), "")

    def usage_rows(self):
        """Menu-row strings from self.usage: 'unavailable', else used/countdown/burn."""
        u = self.usage
        if u is None:
            return ["usage unavailable"]
        # --api carries no token counts -> "% used"; the P90 path has them -> "72k / 88k".
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
        if u.get("seven_day_pct") is not None:
            rows.append("week: %d%% used" % round(u["seven_day_pct"]))
            if u.get("seven_day_reset") is not None:
                rows.append(fmt_countdown_wk(u["seven_day_reset"] - time.time()))
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
            with open(HISTORY_PATH, errors="replace") as f:
                records = parse_history(f.read())
        except OSError:
            return  # keep last-known trends; never crash the poll thread
        # ponytail: single list rebind, read-only in the Gtk redraw -- no lock.
        self.trends = build_trend_rows(records, now)

    def write_dashboard(self, now):
        """Read history off the Gtk main thread, render, atomic-write, flip dash_ready.
        Re-applies history_keep in case an opportunistic prune silently failed.
        ponytail: broad `except Exception` -- a render bug costs one tick, not the thread.
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
        old = s.get("status")  # MUST be read before the update below overwrites it
        # _onscreen pre-acknowledges the "!" when serve() found you already looking.
        s.update(
            dir=d, status=event, pane=pane, tmux=tmux, cwd=cwd,
            acked=bool(msg.get("_onscreen")),
        )
        # `d` (the project dir) goes in the summary, which is not Pango-parsed, unlike body.
        if sess_should_notify(old, event):
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
    prune_history(time.time())
    last_prune = time.time()
    last_trend = 0.0  # 0 -> recompute on the first iteration, no blank window
    last_dash = 0.0  # 0 -> write the dashboard immediately at startup
    while True:
        try:
            usage = fetch_usage()
            now = time.time()
            if usage is not None:
                append_history(history_record(usage, now))
                # Rides this tick: every value is already in `usage`, and emit_notif is async.
                for cap, pct, reset, win, title in (
                    ("5h", usage["used_percentage"], usage["resets_at_epoch"], WIN5, "5-hour quota"),
                    # .get(): the 7d block is absent on an older CLI, which the predicates
                    # below already turn into silence.
                    ("7d", usage.get("seven_day_pct"), usage.get("seven_day_reset"), WIN7, "7-day quota"),
                ):
                    p = project(pct, reset, win, now)
                    if alert_should_fire(mon.alert_armed.get(cap), reset, p, now):
                        # Unguarded reads are safe: the predicate required "exhaust" in p.
                        mon.emit_notif(
                            ("cap", cap),  # one slot per cap -> a later alert replaces it
                            cap,
                            title,
                            # Both values are numbers we computed: no payload-derived string
                            # reaches the Pango-parsed body.
                            "Projected %d%% at reset -- runs out ~%s"
                            % (round(p["proj"]), hhmm(p["exhaust"])),
                            ("dash",),
                            URGENCY_NORMAL,  # informational; it need not block the screen
                        )
                        mon.alert_armed[cap] = reset  # silent until this reset changes
            # After the append (fresh record counts) and before the idle_add (redraw sees it).
            if now - last_trend >= TREND_INTERVAL:
                mon.compute_trends(now)
                last_trend = now
            # last_dash advances unconditionally, so a failed write is throttled, not retried.
            if now - last_dash >= DASH_INTERVAL:
                mon.write_dashboard(now)
                last_dash = now
            GLib.idle_add(mon.apply_usage, usage)
            if now - last_prune >= PRUNE_INTERVAL:
                prune_history(now)
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
        demo()
    else:
        main()
