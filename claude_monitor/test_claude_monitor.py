#!/usr/bin/env python3
"""Assert-based self-check suite for the pure usage logic (run via --selfcheck).

claude-monitor.py --selfcheck imports this module and calls demo(); its exit-0
contract is the GSD verification gate.
"""

import datetime
import importlib.util
import json
import pathlib
import socket
import threading
import time

from .core import (
    DEFAULT_CONFIG,
    GAP_MAX,
    SESS_RANK,
    SPARK_GAP,
    SPARK_GLYPHS,
    TUI_FETCH_INTERVAL,
    TUI_SOCK_TIMEOUT,
    TUI_TICK_INTERVAL,
    WIN5,
    WIN7,
    _embed_json,
    alert_due,
    alert_should_fire,
    build_label,
    build_session_snapshot,
    build_trend_rows,
    despike,
    fmt_countdown,
    fmt_countdown_wk,
    fmt_elapsed,
    fmt_tokens,
    heatmap_buckets,
    history_keep,
    history_numeric,
    history_record,
    hhmm,
    latest_state,
    local_bounds,
    notif_allowed,
    parse_config,
    parse_history,
    parse_usage,
    project,
    read_line,
    reset_marks,
    sess_elapsed,
    sess_notify_baseline,
    sess_rank,
    sess_rows,
    sess_should_notify,
    session_stale,
    trend_burn,
    trend_peak_hour,
    trend_sparkline,
    trend_text,
    tui_usage_rows,
    usage7_series,
    with_gaps,
)
from .dashboard import render_dashboard

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
        {"t": t0 + 15, "pct": 20.0, "burn": 200.0},
        {"t": t0 + 30, "pct": 26.0, "burn": 200.0},
    ])
    assert len(hm) == 7 and all(len(row) == 24 for row in hm)
    assert hm[0][15] == 16.0  # rises 10->20->26, NOT the cumulative mean (18.7)
    assert hm[2][3] is None
    # pct wobbles down mid-window (upstream jitter) and drops hard on a 5h roll. Neither
    # may be re-counted as fresh usage -- only the rises are real consumption.
    tue = int(datetime.datetime(2024, 1, 2, 9).timestamp())
    hm = heatmap_buckets([
        {"t": tue, "pct": 40.0},
        {"t": tue + 15, "pct": 32.0},  # jitter drop, not consumption
        {"t": tue + 30, "pct": 36.0},  # +4
        {"t": tue + 45, "pct": 1.0},   # window rolled; ~0% consumed since reset
        {"t": tue + 60, "pct": 6.0},   # +5
    ])
    assert hm[1][9] == 9.0  # 4 + 5, not 40+32+36+1+6
    # upstream pins pct at 100 for a stretch then falls back: not 98% burned in 15s
    hm = heatmap_buckets([
        {"t": tue, "pct": 1.6},
        {"t": tue + 15, "pct": 100.0},  # rise > RISE_MAX -> untrusted, contributes 0
        {"t": tue + 30, "pct": 100.0},
        {"t": tue + 45, "pct": 3.0},    # back to reality
        {"t": tue + 60, "pct": 5.0},    # +2
    ])
    assert hm[1][9] == 2.0
    # a rise spanning a data gap belongs to hours we never sampled -- do not attribute it
    hm = heatmap_buckets([
        {"t": tue, "pct": 10.0},
        {"t": tue + GAP_MAX + 1, "pct": 18.0},   # +8 across a gap -> ignored
        {"t": tue + GAP_MAX + 16, "pct": 21.0},  # +3 contiguous -> counted
    ])
    assert hm[1][9] == 3.0
    # the same weekday+hour on another day averages, it does not accumulate
    hm = heatmap_buckets([
        {"t": tue, "pct": 10.0},
        {"t": tue + 15, "pct": 30.0},               # day 1: +20
        {"t": tue + 7 * 86400, "pct": 50.0},        # next week: rise spans a gap -> 0
        {"t": tue + 7 * 86400 + 15, "pct": 60.0},   # +10 -> day 2 total 10
    ])
    assert hm[1][9] == 15.0  # mean(20, 10)
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
    # 100 pin between low samples dropped (measured against last KEPT sample), genuine
    # sub-RISE_MAX ramp preserved whole.
    assert despike([[0, 5.0], [15, 100.0], [30, 8.0]]) == [[0, 5.0], [30, 8.0]]
    assert despike([[0, 5.0], [15, 15.0], [30, 25.0]]) == [[0, 5.0], [15, 15.0], [30, 25.0]]
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

    # --- session panel (SESSVIEW-01..05) ---
    _srec = [{"t": now_dash, "pct": 42.0, "burn": 10.0}]
    # (a) empty state: JS empty-string present, no rows shipped in the payload (D-07).
    sempty = render_dashboard(_srec, now_dash, sessions=[])
    assert "No active Claude Code sessions" in sempty
    assert '"sessions": []' in sempty
    # (b) payload + markup inertness (D-08, T-07-01). One dir is angle-bracket markup;
    # it must ship _embed_json-escaped, never as raw markup (no server-side interpolation).
    hostile_dir = "<b>x</b>"  # planner-discipline-allow: <b>x</b>
    ep = 1700000000
    sess = [
        {"dir": hostile_dir, "status": "running", "entered": ep},
        {"dir": "alpha-proj", "status": "waiting", "entered": ep + 1},
        {"dir": "beta-proj", "status": "done", "entered": ep + 2},
    ]
    spage = render_dashboard(_srec, now_dash, sessions=sess)
    assert "alpha-proj" in spage and "beta-proj" in spage
    assert "waiting" in spage and "running" in spage and "done" in spage
    assert str(ep + 1) in spage  # a distinctive entered epoch reached the payload
    assert hostile_dir not in spage  # escaped -> no raw markup, no server-side interp
    assert spage.count("</" + "script>") == 1  # no script breakout
    # (c) self-containment holds with the panel populated (SESSVIEW-05, DASH-06).
    assert "<link" not in spage and "src=" not in spage and "https://" not in spage
    assert spage.replace("http://www.w3.org/2000/svg", "").find("http://") == -1

    # --- build_session_snapshot (SOCK-01 shape groundwork, SOCK-03 idempotency) ---
    _snap_in = [
        {"dir": "proj-a", "status": "running", "entered": 100.0, "pane": "%1", "tmux": "/tmp/x"},
        {"dir": "proj-b", "status": "done", "entered": 90.0, "run_dur": 12.5},
    ]
    _snap_out = build_session_snapshot(_snap_in)
    assert _snap_out == [
        {"dir": "proj-a", "status": "running", "entered": 100.0, "frozen": None, "pane": "%1", "tmux": "/tmp/x"},
        {"dir": "proj-b", "status": "done", "entered": 90.0, "frozen": 12.5, "pane": "", "tmux": ""},
    ]
    assert build_session_snapshot([]) == []
    # purity: calling twice yields independent lists, input untouched.
    assert build_session_snapshot(_snap_in) == _snap_out
    assert build_session_snapshot(_snap_in) is not build_session_snapshot(_snap_in)
    assert _snap_in == [
        {"dir": "proj-a", "status": "running", "entered": 100.0, "pane": "%1", "tmux": "/tmp/x"},
        {"dir": "proj-b", "status": "done", "entered": 90.0, "run_dur": 12.5},
    ]
    json.dumps(_snap_out)  # must not raise

    # --- session-notification de-dupe ---
    assert sess_should_notify(None, "waiting") is True
    assert sess_should_notify("running", "waiting") is True
    assert sess_should_notify("waiting", "done") is True
    assert sess_should_notify("waiting", "waiting") is False
    assert sess_should_notify("done", "done") is False
    assert sess_should_notify("waiting", "running") is False
    assert sess_should_notify("done", "end") is False

    # --- session_stale reap decision (G-07-2 self-heal) ---
    NOW = 2_000_000  # synthetic epoch, never time.time()
    MAX_AGE = 3600
    # pane confirmed gone (alive=False) reaps regardless of age.
    assert session_stale(False, NOW, NOW, MAX_AGE) is True  # entered == now, still reaped
    assert session_stale(False, NOW - 10, NOW, MAX_AGE) is True
    assert session_stale(False, None, NOW, MAX_AGE) is True  # no entered stamp either
    # pane alive (alive=True) does NOT block reaping once past the ceiling
    # (the /exit or /clear same-pane case -- SessionEnd never fires for either).
    assert session_stale(True, NOW - MAX_AGE - 1, NOW, MAX_AGE) is True
    assert session_stale(True, NOW - 10, NOW, MAX_AGE) is False  # well within the ceiling
    # unknown liveness (alive=None) follows the identical age-ceiling rule as alive=True.
    assert session_stale(None, NOW - MAX_AGE - 1, NOW, MAX_AGE) is True
    assert session_stale(None, NOW - 10, NOW, MAX_AGE) is False
    # no entered stamp yet (mid-creation race guard): never reaped by age...
    assert session_stale(True, None, NOW, MAX_AGE) is False
    assert session_stale(None, None, NOW, MAX_AGE) is False
    # ...but still reaped when alive=False (already covered above, restated for contrast).
    assert session_stale(False, None, NOW, MAX_AGE) is True
    # exact boundary (now - entered == max_age) does not reap (strict >).
    assert session_stale(True, NOW - MAX_AGE, NOW, MAX_AGE) is False
    assert session_stale(None, NOW - MAX_AGE, NOW, MAX_AGE) is False

    # --- sess_notify_baseline resurrection (CR-01 no re-notify) ---
    # normal existing session: live status present, no reaped memory -> unchanged.
    assert sess_notify_baseline("running", None) == "running"
    # brand-new session: nothing live, no reaped memory -> None, first waiting still notifies.
    assert sess_notify_baseline(None, None) is None
    assert sess_should_notify(sess_notify_baseline(None, None), "waiting") is True
    # CR-01 same-status resurrection: reaped "waiting" memory -> baseline "waiting", no re-notify.
    assert sess_should_notify(sess_notify_baseline(None, "waiting"), "waiting") is False
    # genuine-change resurrection: reaped "waiting" -> "done" is a real transition, notifies once.
    assert sess_should_notify(sess_notify_baseline(None, "waiting"), "done") is True
    # live-status-wins: a live dict's status is never overridden by stale reaped memory.
    assert sess_notify_baseline("done", "waiting") == "done"

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

    # --- config / gate / threshold (CFG-01..05) ---
    assert parse_config("") == DEFAULT_CONFIG
    assert parse_config("not json") == DEFAULT_CONFIG
    assert parse_config("[]") == DEFAULT_CONFIG
    assert parse_config('{"mute_all": "yes"}')["mute_all"] is False
    assert parse_config('{"usage_threshold": 85}')["usage_threshold"] == 80
    assert parse_config('{"usage_threshold": 90}')["usage_threshold"] == 90
    assert parse_config(json.dumps({"mute_all": True}))["notify_waiting"] is True
    assert parse_config(json.dumps(DEFAULT_CONFIG)) == DEFAULT_CONFIG

    assert notif_allowed("waiting", {**DEFAULT_CONFIG, "mute_all": True}) is False
    assert notif_allowed("waiting", {**DEFAULT_CONFIG, "notify_waiting": False}) is False
    assert notif_allowed("waiting", DEFAULT_CONFIG) is True
    assert notif_allowed("5h", {**DEFAULT_CONFIG, "notify_5h": True, "mute_all": False}) is True

    assert build_label({"used_percentage": 80}, 0, 80) == "80%"
    assert build_label({"used_percentage": 81}, 0, 80) == "81%!"
    assert build_label({"used_percentage": 75}, 0, 70) == "75%!"

    # --- socket wire protocol (IN-01): _handle_conn end-to-end over a real socket ---
    # claude-monitor.py has no importable name (hyphen), so load it by path -- it
    # already requires the gi/GTK stack to run at all, same as this daemon in prod.
    _daemon_path = pathlib.Path(__file__).resolve().parent.parent / "claude-monitor.py"
    _spec = importlib.util.spec_from_file_location("_claude_monitor_daemon", _daemon_path)
    _daemon = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_daemon)

    class _FakeMonitor:
        def __init__(self):
            self.sessions = {
                "sid-1": {"dir": "proj-a", "status": "running", "entered": 1.0, "pane": "%1", "tmux": "/tmp/x"},
            }
            self.sessions_lock = threading.Lock()
            self.usage = {"used_percentage": 42}
            self.trends = ["line1"]

    _mon = _FakeMonitor()
    _server_sock, _client_sock = socket.socketpair()
    _client_sock.settimeout(5)
    _thread = threading.Thread(target=_daemon._handle_conn, args=(_mon, _server_sock), daemon=True)
    _thread.start()
    _client_sock.sendall(b'{"query": "snapshot"}\n')
    _resp = b""
    while True:
        _chunk = _client_sock.recv(65536)
        if not _chunk:
            break
        _resp += _chunk
    _thread.join(timeout=5)
    _client_sock.close()
    _snapshot = json.loads(_resp.decode("utf-8"))
    assert set(_snapshot.keys()) == {"sessions", "usage", "trends"}
    assert _snapshot["usage"] == _mon.usage
    assert _snapshot["trends"] == _mon.trends
    assert _snapshot["sessions"] == build_session_snapshot(list(_mon.sessions.values()))
    # IN-02, deferred: the wire shape carries no `term` key yet (matches
    # build_session_snapshot's current 6-key output above) -- add it when a query-side
    # consumer (e.g. Phase 9's TUI) actually needs to tell a Zed session from a tmux one.
    assert "term" not in _snapshot["sessions"][0]

    # --- tui socket client (TUI-05) ---
    # read_line takes an ALREADY-CONNECTED socket, so a bare socketpair drives it; the
    # full query_snapshot is not exercisable here because it does its own connect(path).
    _wire_a, _wire_b = socket.socketpair()
    _wire_b.sendall(b'{"query": "snapshot"}\n')
    assert read_line(_wire_a) == '{"query": "snapshot"}\n'
    _wire_a.close()
    _wire_b.close()
    # split delivery: the newline arrives only in the second chunk, so read_line must loop.
    _split_a, _split_b = socket.socketpair()

    def _split_writer():
        _split_b.sendall(b'{"part": ')
        time.sleep(0.05)
        _split_b.sendall(b"1}\n")

    _split_t = threading.Thread(target=_split_writer, daemon=True)
    _split_t.start()
    assert read_line(_split_a) == '{"part": 1}\n'
    _split_t.join(timeout=5)
    _split_a.close()
    _split_b.close()
    # EOF without a newline returns what arrived rather than blocking forever (T-09-02).
    _eof_a, _eof_b = socket.socketpair()
    _eof_b.sendall(b"no newline here")
    _eof_b.close()
    assert read_line(_eof_a) == "no newline here"
    _eof_a.close()
    _empty_a, _empty_b = socket.socketpair()
    _empty_b.close()
    assert read_line(_empty_a) == ""
    _empty_a.close()
    # a non-utf-8 byte degrades to the replacement character, never UnicodeDecodeError
    # (T-09-05) -- a project dir is arbitrary bytes on this wire.
    _bad_a, _bad_b = socket.socketpair()
    _bad_b.sendall(b"caf\xe9\n")
    assert read_line(_bad_a) == "caf\ufffd\n"  # escaped, not the glyph: this file is ASCII
    _bad_a.close()
    _bad_b.close()
    # The standing guard against Pitfall 2's thread pile-up: a client timeout at or above
    # the fetch interval starts a new fetch while the previous recv is still blocked.
    assert TUI_SOCK_TIMEOUT < TUI_FETCH_INTERVAL
    assert TUI_TICK_INTERVAL < TUI_FETCH_INTERVAL  # D-09: re-render faster than we refetch

    # --- tui usage rows (TUI-01) ---
    _unow = 1700000000
    _usage = {
        "tokens_used": 417000,
        "token_limit": 880000,
        "used_percentage": 47.4,
        "resets_at_epoch": _unow + 7380,
        "burn_rate_per_min": 6333.0,
        "seven_day_pct": 41.2,
        "seven_day_reset": _unow + 352800,
    }
    assert tui_usage_rows(None, _unow) == ["usage unavailable"]
    assert tui_usage_rows(_usage, _unow) == [
        "5h  47%  417k / 880k  resets in 2h 3m  burn: 380k tok/hr",
        "7d  41%  week resets in 4d 2h",
    ]
    # --api shape: both token counts null -> the used/limit segment drops, nothing else.
    assert tui_usage_rows({**_usage, "tokens_used": None, "token_limit": None}, _unow) == [
        "5h  47%  resets in 2h 3m  burn: 380k tok/hr",
        "7d  41%  week resets in 4d 2h",
    ]
    # weekly pct present but its reset absent -> a second row with no countdown.
    assert tui_usage_rows({**_usage, "seven_day_reset": None}, _unow) == [
        "5h  47%  417k / 880k  resets in 2h 3m  burn: 380k tok/hr",
        "7d  41%",
    ]
    # older CLI: no weekly block at all -> exactly one row.
    assert len(tui_usage_rows({**_usage, "seven_day_pct": None}, _unow)) == 1
    # boundaries: a reset epoch already past renders the formatters' "now" strings.
    _past = tui_usage_rows(
        {**_usage, "resets_at_epoch": _unow - 10, "seven_day_reset": _unow - 10}, _unow
    )
    assert "resets now" in _past[0] and "week resets now" in _past[1]
    # 0% and 100% are ordinary rows -- no special case, same row count as mid-range.
    assert len(tui_usage_rows({**_usage, "used_percentage": 0}, _unow)) == 2
    assert len(tui_usage_rows({**_usage, "used_percentage": 100}, _unow)) == 2
    assert tui_usage_rows({**_usage, "used_percentage": 0}, _unow)[0].startswith("5h  0%")
    assert tui_usage_rows({**_usage, "used_percentage": 100}, _unow)[0].startswith("5h  100%")

    # --- tui trend text (TUI-02) ---
    assert trend_text(None) == "trends: collecting history..."
    assert trend_text([]) == "trends: collecting history..."
    assert trend_text(["spark", "today"]) == "spark\ntoday"
    assert trend_text(["spark", "today", "peak"]) == "spark\ntoday\npeak"
    # D-05 verbatim property: build_trend_rows is the ONLY producer, so every row it
    # emits for a record set survives into the TUI text unchanged -- the TUI and the tray
    # menu cannot disagree because there is nothing to disagree with.
    _trec = [{"t": _unow - 7200 + i * 600, "pct": 40.0 + i, "burn": 100.0 + i} for i in range(13)]
    _trows = build_trend_rows(_trec, _unow)
    assert _trows is not None and len(_trows) in (2, 3)
    _ttext = trend_text(_trows)
    for _trow in _trows:
        assert _trow in _ttext
    assert _ttext.split("\n") == _trows

    # --- tui session rows (TUI-03/TUI-04) ---
    assert SESS_RANK == {"waiting": 0, "running": 1, "done": 2}
    assert [sess_rank(s) for s in ("waiting", "running", "done")] == [0, 1, 2]
    assert sess_rank("") == 99 and sess_rank("nope") == 99 and sess_rank(None) == 99
    assert fmt_elapsed(-5) == "0m 00s" and fmt_elapsed(0) == "0m 00s"
    assert fmt_elapsed(134) == "2m 14s"
    assert fmt_elapsed(3599) == "59m 59s"
    assert fmt_elapsed(3600) == "1h 0m" and fmt_elapsed(3601) == "1h 0m"
    assert fmt_elapsed(4920) == "1h 22m"
    assert fmt_elapsed(86399) == "23h 59m"
    assert fmt_elapsed(86400) == "1d 00h" and fmt_elapsed(86401) == "1d 00h"
    assert fmt_elapsed(266400) == "3d 02h"
    # D-09 split: only running ticks off `entered`; everything else shows `frozen`.
    assert sess_elapsed({"status": "running", "entered": _unow - 30}, _unow) == 30
    assert sess_elapsed({"status": "running", "entered": _unow + 30}, _unow) == 0  # skew clamps
    assert sess_elapsed({"status": "done", "entered": _unow - 30, "frozen": 12.5}, _unow) == 12.5
    assert sess_elapsed({}, _unow) is None
    assert sess_rows([], _unow) == [("", "No active Claude Code sessions", "")]
    # A project dir is an arbitrary repo path; sess_rows is a pure string builder and must
    # return it byte-for-byte, neither escaping nor interpreting it. The markup escaping
    # belongs at the widget (Plan 09-02); asserting it here would encode the wrong contract.
    _hostile = "[bold]myrepo[/]"  # planner-discipline-allow: [bold]myrepo[/]
    _srows_in = [
        {"dir": "done-proj", "status": "done", "entered": _unow - 500, "frozen": 4920},
        {"dir": _hostile, "status": "running", "entered": _unow - 134, "frozen": None},
        {"dir": "wait-proj", "status": "waiting", "entered": _unow - 20, "frozen": 74},
        {"dir": "odd-proj", "status": "zombie", "entered": None, "frozen": None},
    ]
    assert sess_rows(_srows_in, _unow) == [
        ("waiting", "wait-proj", "1m 14s"),
        ("running", _hostile, "2m 14s"),
        ("done", "done-proj", "1h 22m"),
        ("zombie", "odd-proj", "-"),  # unknown status sorts last (rank 99), duration is a dash
    ]
    # stability: equal-rank rows keep their input order and never merge or swap.
    _stable = [
        {"dir": "first", "status": "running", "entered": None, "frozen": 10},
        {"dir": "second", "status": "running", "entered": None, "frozen": 20},
        {"dir": "odd-a", "status": "zombie"},
        {"dir": "odd-b", "status": "ghost"},
    ]
    assert [r[1] for r in sess_rows(_stable, _unow)] == ["first", "second", "odd-a", "odd-b"]
    # purity: input list and its dicts untouched, and two calls return independent lists.
    _srows_before = [dict(s) for s in _srows_in]
    _srows_out = sess_rows(_srows_in, _unow)
    assert [dict(s) for s in _srows_in] == _srows_before
    assert sess_rows(_srows_in, _unow) == _srows_out
    assert sess_rows(_srows_in, _unow) is not sess_rows(_srows_in, _unow)

    print("ok")
