#!/usr/bin/env python3
"""Assert-based self-check suite for the pure usage logic (run via --selfcheck).

claude-monitor.py --selfcheck imports this module and calls demo(); its exit-0
contract is the GSD verification gate.
"""

import datetime
import json
import time

from core import (
    DEFAULT_CONFIG,
    GAP_MAX,
    SPARK_GAP,
    SPARK_GLYPHS,
    WIN5,
    WIN7,
    _embed_json,
    alert_due,
    alert_should_fire,
    build_label,
    build_trend_rows,
    despike,
    fmt_countdown,
    fmt_countdown_wk,
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
    reset_marks,
    sess_should_notify,
    trend_burn,
    trend_peak_hour,
    trend_sparkline,
    usage7_series,
    with_gaps,
)
from dashboard import render_dashboard

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
    print("ok")
