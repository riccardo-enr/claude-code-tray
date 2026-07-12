#!/usr/bin/env python3
"""Claude Code monitor: GNOME top-bar tray indicator.

A long-lived helper showing per-session Claude Code status in the top bar.
Claude Code hooks push one-line JSON events to a unix socket:
    {event, session_id, cwd, message, pane, tmux}
event in {running, waiting, done, end}. The helper reflects each session's
status in the tray menu; clicking a session focuses its tmux pane and raises
the Ghostty window.
"""

import datetime
import json
import os
import socket
import subprocess
import tempfile
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

# --- Phase 03 trend rendering constants ---
# Auto-scale ramp for the 24h usage sparkline; index 0 = lowest, -1 = highest.
# These 8 block glyphs + SPARK_GAP are the ONLY intended non-ASCII in this file.
SPARK_GLYPHS = "▁▂▃▄▅▆▇█"
SPARK_GAP = " "  # rendered for hours with no samples (keeps columns time-aligned)
TREND_INTERVAL = 5 * 60  # trend recompute throttle in poll_loop (seconds)
TREND_MIN_SPAN = 3600  # min history span (s) before real rows replace empty state


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
    print("ok")


class Monitor:
    def __init__(self):
        self.sessions = {}  # session_id -> {dir,status,pane,tmux,cwd}
        self.usage = None  # latest parse_usage() dict, or None if unavailable
        self.usage_misses = 0  # consecutive failed polls; >= threshold -> unavailable
        self.trends = None  # cached trend row strings, or None (collecting/empty state)

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
        # separator dividing the usage block from the trend block (D-11)
        self.menu.append(Gtk.SeparatorMenuItem.new())
        for row in self.trend_rows():
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
        return [
            used,
            fmt_countdown(u["resets_at_epoch"] - time.time()),
            "burn: %s tok/hr" % fmt_tokens(round(u["burn_rate_per_min"] * 60)),
        ]

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
        trends, never raise on the poll thread). Leaves self.trends = None until the
        retained history spans TREND_MIN_SPAN seconds (empty/collecting state, D-12).
        """
        try:
            with open(HISTORY_PATH, errors="replace") as f:
                records = parse_history(f.read())
        except OSError:
            return  # degrade to last-known trends; never crash the poll thread
        if not records or records[-1]["t"] - records[0]["t"] < TREND_MIN_SPAN:
            self.trends = None  # not enough data yet -> collecting state
            return
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
        # ponytail: single list rebind, read-only in the Gtk redraw (mirrors self.usage) -- no lock.
        self.trends = rows

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
    back via GLib.idle_add (mirrors serve()'s pattern), then sleep.

    All history file I/O lives here (never in apply_usage/main, which run on the
    Gtk main thread): a successful poll appends one record before the idle_add,
    and the store is pruned once at startup then opportunistically thereafter.
    """
    prune_history(time.time())
    last_prune = time.time()
    last_trend = 0.0  # 0 -> first iteration recomputes immediately (no 5-min blank window)
    while True:
        usage = fetch_usage()
        now = time.time()
        if usage is not None:
            append_history(history_record(usage, now))
        # recompute trends off the Gtk main thread, AFTER the append (so the fresh
        # record is included) and BEFORE the idle_add (so this poll's redraw sees it).
        if now - last_trend >= TREND_INTERVAL:
            mon.compute_trends(now)
            last_trend = now
        GLib.idle_add(mon.apply_usage, usage)
        if now - last_prune >= PRUNE_INTERVAL:
            prune_history(now)
            last_prune = now
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
