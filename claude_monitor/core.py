#!/usr/bin/env python3
"""Pure usage/config/history logic for the Claude Code tray monitor.

Stdlib only -- no gi/GTK -- so this module imports fast and is exercised end to end
by ``python3 claude-monitor.py --selfcheck`` (test_claude_monitor.demo). Both
dashboard.py and claude-monitor.py import their logic from here.
"""

import datetime
import json
import math
import os
import socket
import subprocess
import tempfile
import time

# Absolute on purpose: the CLI shares the bare name "claude-monitor" with this helper.
USAGE_CLI = os.path.expanduser("~/.local/bin/claude-monitor")
# Override with CLAUDE_TRAY_PLAN (max5, max20, custom, pro, or "" for the CLI's saved
# default -- which is nondeterministic, it flips as different --plan values are used).
PLAN = os.environ.get("CLAUDE_TRAY_PLAN", "custom")


POLL_TIMEOUT = 15  # subprocess seconds
# High-usage badge threshold (percent). This is only the startup default now -- overridable
# via ~/.claude/tray-config.json and the tray's Badge threshold menu (CFG-05), not via an
# env var, which stays out of this phase's scope (D-01).
USAGE_THRESHOLD = 80


# Sibling to HISTORY_PATH; "tray-" matches the existing CLAUDE_TRAY_* env var family (D-02).
CONFIG_PATH = os.path.expanduser("~/.claude/tray-config.json")
THRESHOLD_CHOICES = (70, 80, 90, 95)  # fixed badge-threshold presets (D-05)
DEFAULT_CONFIG = {
    "notify_waiting": True,
    "notify_done": True,
    "notify_5h": True,
    "notify_7d": True,
    "mute_all": False,
    "usage_threshold": USAGE_THRESHOLD,
}
# Maps notif_allowed's `kind` values (from Monitor.handle's `event` and poll_loop's `cap`)
# to their DEFAULT_CONFIG / tray-config.json key.
NOTIF_KEYS = {"waiting": "notify_waiting", "done": "notify_done", "5h": "notify_5h", "7d": "notify_7d"}


def parse_config(text):
    """Tolerant loader for a single JSON object (not JSONL -- tolerance is per-KEY here,
    not per-LINE). Malformed JSON, a non-dict root, or any individual key with the wrong
    type all fall back to DEFAULT_CONFIG -- but only for the affected key: a single bad
    key must never discard every other still-valid setting the user has saved. Never raises.
    """
    try:
        raw = json.loads(text)
    except Exception:
        return dict(DEFAULT_CONFIG)
    if not isinstance(raw, dict):
        return dict(DEFAULT_CONFIG)
    cfg = dict(DEFAULT_CONFIG)
    for key in ("notify_waiting", "notify_done", "notify_5h", "notify_7d", "mute_all"):
        if isinstance(raw.get(key), bool):
            cfg[key] = raw[key]
    if raw.get("usage_threshold") in THRESHOLD_CHOICES:
        cfg["usage_threshold"] = raw["usage_threshold"]
    return cfg


def load_config():
    """Read + parse CONFIG_PATH. A missing/unreadable file -> full default, never raises."""
    try:
        with open(CONFIG_PATH, errors="replace") as f:
            return parse_config(f.read())
    except OSError:
        return dict(DEFAULT_CONFIG)


def save_config(cfg):
    """Atomic write: temp file + os.replace, mirroring prune_history. On any OSError the
    write just doesn't happen -- the caller's in-memory config (already updated before this
    is called) is unaffected either way.
    """
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(CONFIG_PATH))
        with os.fdopen(fd, "w") as f:
            json.dump(cfg, f)
        os.replace(tmp, CONFIG_PATH)
        tmp = None  # replace succeeded; nothing to clean up
    except OSError:
        return
    finally:
        if tmp is not None:
            try:
                os.remove(tmp)
            except OSError:
                pass


def notif_allowed(kind, config):
    """Mute gate. `kind` is one of "waiting", "done", "5h", "7d". `config` is a dict shaped
    like DEFAULT_CONFIG. Mute wins: config["mute_all"] short-circuits before the per-event
    key is even looked up (D-04) -- the per-event flag is read from config unconditionally,
    never reset by this function.
    """
    return not config["mute_all"] and config[NOTIF_KEYS[kind]]


def sess_should_notify(old_status, new_status):
    """True iff the session just CHANGED into "waiting"/"done". Pure.
    A session sitting in "waiting" re-sends it on every hook event; only a transition
    passes. Takes no on-screen argument by design -- that gates the "!" badge, not this.
    """
    return new_status in ("waiting", "done") and old_status != new_status


def sess_notify_baseline(live_status, reaped_status):
    """Resolve the `old` status Monitor.handle feeds sess_should_notify. Pure.
    A reaped-then-resurrected session reads its live status as None (Monitor._pop_stale
    popped the whole dict), so without this it looks identical to a brand-new session and a
    same-status resurrection re-fires the notification (CR-01, regressing NOTIF-02). Falling
    back to the short-lived reaped-status memory makes a same-status resurrection read as "no
    transition"; a genuinely new session (no reaped memory, reaped_status is None) stays None
    so its first waiting/done still notifies. Live status always wins when present -- an
    explicit `is not None` test (not truthiness) keeps the contract exact.
    """
    return live_status if live_status is not None else reaped_status


REAP_MAX_AGE = 3600  # 1 hour; self-heal ceiling for a session SessionEnd never popped (G-07-2)


def session_stale(alive, entered, now, max_age):
    """Should this session be reaped out of self.sessions? Pure.
    `alive` is tri-state pane liveness (pane_alive()'s return shape in claude-monitor.py):
    False means the pane is confirmably gone -> reap immediately, regardless of age. True
    and None both fall through to the SAME unconditional age check -- alive=True must NOT
    short-circuit to "never reap": a pane surviving /exit or /clear in the exact same tmux
    pane is precisely the case pane-liveness alone cannot detect (SessionEnd fires for
    neither, anthropics/claude-code#17885 / #6428), so only the age ceiling catches it.
    `entered=None` (a session Monitor.handle() is still creating this tick) reads as `now`
    so a same-tick race never gets reaped mid-creation -- unless alive is already False.
    Reaping a session that is still genuinely alive is harmless by design: Monitor.handle()
    re-setdefault()s a fresh dict on the session's next real event (its `old` status reads
    as None again, same as a brand-new session), so it simply reappears with a reset
    duration counter rather than losing any data -- this is what makes an
    aggressive-looking 1-hour default safe.
    """
    if alive is False:
        return True
    return now - (entered if entered is not None else now) > max_age


def build_session_snapshot(sessions):
    """Snapshot a list of session dicts into plain, JSON-serializable primitives. Pure.
    `sessions` is a plain list already copied out of Monitor.sessions.values() by the
    caller (which must hold sessions_lock while copying, per D-01) -- this function does
    no locking, no I/O, and never mutates its input or the dicts it reads. Six keys per
    session: dir/status/entered/frozen (write_dashboard's original shape) plus pane/tmux
    (D-06's "superset" extension, shared with Plan 08-02's query responder).
    """
    return [
        {
            "dir": s.get("dir", ""),
            "status": s.get("status", ""),
            "entered": s.get("entered"),
            "frozen": None if s.get("status") == "running" else s.get("run_dur"),
            "pane": s.get("pane", ""),
            "tmux": s.get("tmux", ""),
        }
        for s in sessions
    ]


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


# The only intended non-ASCII in this file. Index 0 = lowest, -1 = highest.
SPARK_GLYPHS = "▁▂▃▄▅▆▇█"
SPARK_GAP = " "  # hours with no samples (keeps columns time-aligned)


TREND_MIN_SPAN = 3600  # min history span (s) before real rows replace empty state


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


def build_label(usage, attention, threshold=USAGE_THRESHOLD):
    """Tray label: usage % leads, attention count follows ('47% 2!', '83%! 2!', '2!', '').
    `attention` counts sessions needing you. '!' fires when EITHER cap is above
    `threshold`, but the leading number is always the 5h one. `threshold` defaults to
    USAGE_THRESHOLD so every pre-existing two-positional-arg call site keeps working.
    """
    wseg = ("%d!" % attention) if attention else ""
    if usage is None:
        return wseg
    seg = "%d%%" % round(usage["used_percentage"])
    pct7 = usage.get("seven_day_pct")
    hot = usage["used_percentage"] > threshold or (
        pct7 is not None and pct7 > threshold
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

    `pct` is cumulative within the rolling 5h window, so averaging it directly measures
    how late in a window a sample landed, not how hard that hour was worked. We sum the
    per-sample RISE in `pct` instead, per calendar day, then average each (dow, hour)
    across the days it actually saw data.

    Only rises count; a drop contributes 0. A drop is either upstream jitter (`pct` is a
    recomputed estimate and does wobble down mid-window) or a genuine 5h roll, and we do
    not need to tell them apart: at POLL_INTERVAL granularity the first sample after a
    roll is still near 0%, so there is no real consumption to recover from the drop
    itself -- the rises that follow pick it up. Reading a drop as "the window rolled, so
    this pct is all fresh usage" instead re-adds the whole cumulative value on every
    jitter blip, and reports impossible >100%/hour buckets.

    A rise is trusted only if it can honestly be attributed to this hour: it must not
    span a data gap (the usage may belong to hours we never sampled) and must be
    physically plausible (see RISE_MAX). An untrusted rise contributes 0 rather than a
    clamped value -- clamping would still book usage that never happened.

    Empty buckets stay None so "no data" stays distinct from a genuine 0%.
    """
    grid = [[None] * 24 for _ in range(7)]
    acc = {}  # (dow, hour) -> {date: % consumed that hour, that day}
    prev = None  # (t, pct) of the previous sample
    for rec in sorted(records, key=lambda r: r["t"]):
        dt = datetime.datetime.fromtimestamp(rec["t"])
        pct = rec["pct"]
        rise = 0.0
        if prev is not None and rec["t"] - prev[0] <= GAP_MAX:
            rise = pct - prev[1]
            if rise < 0 or rise > RISE_MAX:
                rise = 0.0
        prev = (rec["t"], pct)
        day = acc.setdefault((dt.weekday(), dt.hour), {})
        day[dt.date()] = day.get(dt.date(), 0.0) + rise
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

# ponytail: flat ceiling on a believable one-sample jump in usage %. Upstream sometimes
# pins `pct` to 100 for minutes (burn spikes with it) then drops straight back -- nobody
# burns ~98% of a window between two 15s polls. Observed genuine rises top out near 11;
# 25 leaves generous headroom. Upgrade path if real bursts ever get swallowed: bound the
# rise by `burn` * elapsed instead of a constant.
RISE_MAX = 25.0


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


def despike(series, max_rise=RISE_MAX):
    """Drop upstream 100%-pin outliers from a [[t, pct], ...] series before with_gaps.

    Mirrors the `rise > RISE_MAX` rejection in heatmap_buckets so the line chart and the
    heatmap agree on a believable one-sample jump (see the ponytail: note at RISE_MAX for
    why upstream pins pct=100). Reject-and-drop, not median-smooth: kept points are real
    samples only -- no synthesized midpoints -- so the line stays honest.

    A sample is dropped only when its pct rises more than max_rise above the previous KEPT
    sample; the kept reference is left unchanged on a drop, so consecutive pins both go.
    Only positive jumps are bound -- drops (window resets to ~0) survive untouched. Must
    run BEFORE with_gaps so pen-up breaks are computed on the cleaned series. Input is
    already numeric (history_numeric / _is_num), so no None handling is needed.
    """
    out = []
    ref = None  # pct of the previous kept sample
    for t, v in series:
        if ref is not None and v - ref > max_rise:
            continue
        out.append([t, v])
        ref = v
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


"""The terminal-dashboard (claude-tui.py) substrate.

Everything the TUI needs that is not a textual widget lives here rather than in the
entry script, because `just selfcheck` runs on an interpreter that cannot have textual
installed (PEP 668 externally-managed system python). Logic above that boundary is
provable by --selfcheck; logic inside the App class is not provable at all. Nothing
below may import textual, rich, or any other third-party package.
"""

# The daemon's socket. Restates the path expression at claude-monitor.py:32 and
# claude-send.py:17, both out of scope this phase -- change all three.
SOCK_PATH = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "claude-monitor.sock")
# D-08: socket poll cadence, deliberately independent of the daemon's usage-poll clock
# because sessions change on hook events, not on that clock.
TUI_FETCH_INTERVAL = 2.0
# D-09: local re-render, so a running session's counter ticks between snapshots.
TUI_TICK_INTERVAL = 1.0
TUI_SOCK_TIMEOUT = 1.5  # < TUI_FETCH_INTERVAL so at most one fetch is ever in flight
SESS_RANK = {"waiting": 0, "running": 1, "done": 2}  # D-03: the only ordering authority


def read_line(sock, deadline=None, max_bytes=1 << 20):
    """Read one newline-terminated response line off an ALREADY-CONNECTED socket.

    Neither connects nor closes -- that is what lets --selfcheck drive it over a plain
    socket.socketpair(). Stops on the newline OR on EOF, so a peer that closes mid-line
    returns what arrived (possibly "") instead of blocking forever (T-09-02). Decodes
    utf-8 with errors="replace", matching _handle_conn's own decode posture, so a
    non-utf-8 byte inside a project dir degrades to a replacement character instead of
    raising UnicodeDecodeError inside a timer callback (T-09-05).

    `settimeout` only bounds each individual `recv`, not the whole read, so a peer that
    dribbles one byte per (timeout - epsilon) keeps the loop alive forever while the 2s
    fetch interval keeps firing -- exactly the Pitfall-2 thread pile-up. `deadline` (a
    time.monotonic() instant) bounds the whole function; `max_bytes` caps a daemon that
    streams without ever sending a newline so `buf` cannot grow to OOM (T-09-02).
    """
    buf = b""
    while not buf.endswith(b"\n"):
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError("snapshot read exceeded %ss" % TUI_SOCK_TIMEOUT)
        chunk = sock.recv(65536)
        if not chunk:
            break  # EOF: the daemon closed, buf is whatever arrived
        buf += chunk
        if len(buf) > max_bytes:
            raise ValueError("snapshot response exceeded %d bytes" % max_bytes)
    return buf.decode("utf-8", "replace")


def query_snapshot(path=SOCK_PATH, timeout=TUI_SOCK_TIMEOUT):
    """Ask the daemon for one snapshot: one request line out, one response line back.

    RAISES on every failure mode -- FileNotFoundError (no daemon has ever run),
    ConnectionRefusedError (stale socket file), socket.timeout (hung daemon),
    json.JSONDecodeError (truncated or non-JSON line). Nothing is swallowed here on
    purpose: a sentinel return would make "no daemon" indistinguishable from "a daemon
    with no usage yet", and only the caller's degraded-mode state machine knows what a
    failure should look like on screen. The swallowing belongs at that boundary.

    settimeout runs BEFORE connect, so a hung connect is bounded by the same 1.5s as a
    hung read. The finally-close is not optional: claude-send.py:34-41 omits it and
    leaks the fd when sendall raises.
    """
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(path)
        s.sendall(b'{"query": "snapshot"}\n')
        obj = json.loads(read_line(s, time.monotonic() + timeout))
        # json.loads happily returns null/[]/3/"x". A bare `null` would make
        # apply_snapshot rebind snapshot=None -- re-arming the D-11 cold-start predicate
        # under a "live" header (stale-as-live, Plan 09-02's first prohibition). Reject a
        # non-object here so a malformed line is a failure the degraded state machine owns.
        if not isinstance(obj, dict):
            raise ValueError("snapshot response was %s, not an object" % type(obj).__name__)
        return obj
    finally:
        s.close()


def band(pct):
    """Fixed btop proximity-to-cap band for a usage percent: <70 -> "green",
    70-<90 -> "yellow", >=90 -> "red" (TUI-06, D-01). Pure and total -- any numeric
    input maps to a band and it never raises, so an over-limit percent (e.g. 473.5) or a
    negative one still classifies. The cutoffs are LITERALS, deliberately kept separate
    from the mutable badge USAGE_THRESHOLD / THRESHOLD_CHOICES: band means proximity to
    the cap, not the user's "warn me" line. The token doubles as an ANSI style name so
    the render side needs no translation table.
    """
    if pct < 70:
        return "green"
    if pct < 90:
        return "yellow"
    return "red"


def gauge_fill(pct, width):
    """Filled-cell count for a `width`-cell gradient gauge at usage `pct` (TUI-07, D-04).
    Clamps pct to 0..100, then rounds pct/100 * width to a cell count: 0 at 0%, `width`
    at 100%, monotonic non-decreasing between, and never past `width` for an over-limit
    percent (so it cannot index past the bar). Counts cells only -- no glyph, no color;
    claude-tui.py applies those.
    """
    pct = max(0.0, min(100.0, pct))
    return round(pct / 100 * width)


def tui_usage_rows(usage, now):
    """One compact row per visible cap (D-01), 5h first then 7d. Pure.

    Mirrors Monitor.usage_rows' three-way None branching (claude-monitor.py:316-339) in
    the TUI's two-row shape instead of the tray's five-row vertical list. `now` is a
    parameter, never time.time() read inside -- the repo's test discipline is synthetic
    epochs. Every numeric goes through an EXISTING core formatter or round(); a new
    number formatter here is exactly the tray/TUI divergence D-05 exists to prevent.
    """
    if usage is None:
        # change both: claude-monitor.py:320 carries the same string.
        return ["usage unavailable"]
    # parse_usage's "all three numeric or None wholesale" guarantee lives in another
    # process and crosses a JSON socket enforced by nothing here; read defensively and
    # fall back to the same string rather than subscript-raising into a false
    # "daemon unreachable" (WR-03). Every sibling helper uses .get for this reason.
    pct = usage.get("used_percentage")
    reset = usage.get("resets_at_epoch")
    burn = usage.get("burn_rate_per_min")
    if pct is None or reset is None or burn is None:
        return ["usage unavailable"]
    row = ["5h", "%d%%" % round(pct)]
    # --api carries no token counts -> percent only; the P90 path has them -> "72k / 88k".
    if usage.get("tokens_used") is not None and usage.get("token_limit") is not None:
        row.append(
            "%s / %s" % (fmt_tokens(usage["tokens_used"]), fmt_tokens(usage["token_limit"]))
        )
    row.append(fmt_countdown(reset - now))
    row.append("burn: %s tok/hr" % fmt_tokens(round(burn * 60)))
    rows = ["  ".join(row)]
    pct7 = usage.get("seven_day_pct")
    if pct7 is not None:  # an older CLI omits the whole weekly block -> one row only
        wrow = ["7d", "%d%%" % round(pct7)]
        if usage.get("seven_day_reset") is not None:
            wrow.append(fmt_countdown_wk(usage["seven_day_reset"] - now))
        rows.append("  ".join(wrow))
    return rows


def trend_text(trends):
    """The trends panel as one string: build_trend_rows' rows joined by newlines. Pure.

    A falsy `trends` -- both the None of build_trend_rows' collecting state (D-07) and an
    empty list -- renders the tray menu's collecting row verbatim (change both:
    claude-monitor.py:344). Otherwise the rows are joined and NOT recomputed: they are
    already the exact strings build_trend_rows produced for the tray, so under D-05 the
    two surfaces cannot disagree. Iterates, never indexes -- build_trend_rows appends the
    peak row conditionally, so the list is length 2 or 3.
    """
    if not trends:
        return "trends: collecting history..."
    return "\n".join(trends)


def sess_rank(status):
    """Sort rank for a session status; an unrecognized status sorts last. Pure."""
    return SESS_RANK.get(status, 99)


def fmt_elapsed(secs):
    """Time-in-state: 134 -> '2m 14s', 4920 -> '1h 22m', 266400 -> '3d 02h'. Pure.
    Negative (clock skew) clamps to '0m 00s'. Below an hour the seconds field is always
    shown and zero-padded so the counter visibly ticks each second (D-09); above an hour
    a stale session does not need second precision.
    """
    secs = max(0, int(secs))
    if secs >= 86400:
        return "%dd %02dh" % (secs // 86400, (secs % 86400) // 3600)
    if secs >= 3600:
        return "%dh %dm" % (secs // 3600, (secs % 3600) // 60)
    return "%dm %02ds" % (secs // 60, secs % 60)


def sess_elapsed(session, now):
    """Seconds to display for one session, or None when there is nothing to show. Pure.
    Only a RUNNING session ticks live off `entered` + the caller's clock; waiting/done
    show the snapshot's frozen run duration, so the counter stops climbing once the
    session stops working (D-09). `frozen` is legitimately None -- that means the caller
    renders a dash. Reads every key with .get, so a short session dict never raises. A
    negative live elapsed (clock skew) clamps to 0.
    """
    if session.get("status") == "running" and session.get("entered") is not None:
        return max(0.0, now - session["entered"])
    return session.get("frozen")


def _safe_cell(s):
    """Strip C0/C1 control characters from an arbitrary filesystem path. Pure.

    rich.text.Text only strips BEL/BS/VT/FF/CR (rich/control.py), so ESC-based
    terminal-control sequences would otherwise reach the terminal verbatim through the
    sessions table -- the control-sequence half of T-09-01. A hostile repo can ship a
    subdirectory named e.g. $'\\e[2J' (clear screen) or an OSC 52 clipboard write; every
    such byte becomes '?'. Printable characters, including markup like [bold]x[/], are
    left byte-for-byte -- markup injection is closed separately at the widget (Plan 09-02).
    """
    return "".join(c if c.isprintable() or c == " " else "?" for c in s)


def sess_rows(sessions, now):
    """(status, dir, duration) cells for the sessions table, sorted per D-03. Pure.

    An empty input returns exactly ONE row carrying the v1.4 empty-state string in the
    dir cell -- never [] and never a raise -- so the widget above stays a branch-free
    loop over three columns (change both: dashboard.py:491). sorted() is stable, which
    is what delivers the guarantee that two sessions sharing a status come back in input
    order. Never mutates the input list or any dict in it.
    """
    if not sessions:
        return [("", "No active Claude Code sessions", "")]
    rows = []
    for s in sorted(sessions, key=lambda s: sess_rank(s.get("status", ""))):
        secs = sess_elapsed(s, now)
        rows.append(
            (
                s.get("status", ""),
                _safe_cell(s.get("dir", "")),
                "-" if secs is None else fmt_elapsed(secs),
            )
        )
    return rows
