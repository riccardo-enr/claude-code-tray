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
import tempfile
import threading
import time

from . import core
from .core import (
    DEFAULT_CONFIG,
    EXTRA_TEXT_MAX_CHARS,
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
    band,
    build_label,
    build_session_snapshot,
    build_trend_rows,
    despike,
    fmt_countdown,
    fmt_countdown_short,
    fmt_countdown_wk,
    fmt_elapsed,
    fmt_tokens,
    focus_tmux_cmds,
    gauge_fill,
    heatmap_active_span,
    heatmap_buckets,
    heatmap_levels,
    history_keep,
    history_numeric,
    history_record,
    hhmm,
    hook_session_event,
    latest_state,
    local_bounds,
    notif_allowed,
    parse_config,
    parse_history,
    parse_usage,
    project,
    _safe_cell,
    read_line,
    request_focus,
    reset_marks,
    sess_elapsed,
    sess_notify_baseline,
    sess_rank,
    sess_rows,
    sess_should_notify,
    sess_status_band,
    session_stale,
    spark_levels,
    statusline_text,
    trend_burn,
    trend_spent,
    trend_peak_hour,
    trend_sparkline,
    trend_text,
    tui_usage_rows,
    usage_extra_row,
    usage7_series,
    weekday_hhmm,
    with_gaps,
)
from .dashboard import _DASH_JS, render_dashboard

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
    # The cost/pace/model extras: absent in the samples above, so all six must read as
    # None rather than KeyError-ing whichever surface renders them, and the untouched
    # 5h keys survive verbatim.
    assert official["cost_usd"] is None and official["cost_per_hour"] is None
    assert official["pace_used_pct"] is None and official["pace_elapsed_pct"] is None
    assert official["pace_label"] is None and official["model_mix"] is None
    assert official["used_percentage"] == 5.0 and official["tokens_used"] is None
    extras = parse_usage(
        json.dumps(
            {
                "limits": {
                    "five_hour": {
                        "tokens_used": None,
                        "token_limit": None,
                        "used_percentage": 27.0,
                        "resets_at_epoch": now_plus,
                    }
                },
                "local": {
                    "burn_rate_tokens_per_minute": 1000.0,
                    "cost_usd": 113.9296,
                    "burn_rate_cost_per_hour": 143.31,
                    "model_distribution": [
                        {"family": "sonnet", "percentage": 28.0},
                        {"family": "opus", "percentage": 72.0},
                        {"family": "haiku", "percentage": 0.4},
                    ],
                },
                "pace": {
                    "label": "slow down",
                    "used_percentage": 27.0,
                    "elapsed_percentage": 16.0,
                },
            }
        )
    )
    assert extras["cost_usd"] == 113.9296 and extras["cost_per_hour"] == 143.31
    # Shares sorted, haiku's 0.4% rounds to 0 and is dropped, tail dropped past the
    # 2-family cap.
    assert extras["model_mix"] == "opus 72% sonnet 28%"
    assert extras["pace_label"] == "slow down"
    assert extras["pace_used_pct"] == 27.0 and extras["pace_elapsed_pct"] == 16.0
    assert usage_extra_row(extras) == "$113.93  $143/hr  pace: 27%/16% slow down  opus 72% sonnet 28%"
    # Wrong types degrade only their own field -- the 5h payload and every sibling extra
    # survive.
    junk_extra = parse_usage(
        json.dumps(
            {
                "limits": {
                    "five_hour": {
                        "tokens_used": None,
                        "token_limit": None,
                        "used_percentage": 9.0,
                        "resets_at_epoch": now_plus,
                    }
                },
                "local": {
                    "burn_rate_tokens_per_minute": 1000.0,
                    "cost_usd": "lots",
                    "model_distribution": "opus",
                },
                "pace": ["slow down"],
            }
        )
    )
    assert junk_extra is not None and junk_extra["used_percentage"] == 9.0
    assert junk_extra["cost_usd"] is None and junk_extra["model_mix"] is None
    assert junk_extra["pace_label"] is None and junk_extra["pace_used_pct"] is None
    assert usage_extra_row(junk_extra) is None
    junk_label = parse_usage(
        json.dumps(
            {
                "limits": {
                    "five_hour": {
                        "tokens_used": None,
                        "token_limit": None,
                        "used_percentage": 9.0,
                        "resets_at_epoch": now_plus,
                    }
                },
                "local": {
                    "burn_rate_tokens_per_minute": 1000.0,
                    "model_distribution": [
                        {"family": None, "percentage": 100.0},
                        {"family": "opus"},  # missing percentage
                    ],
                },
                "pace": {"label": 42, "used_percentage": 1.0, "elapsed_percentage": 1.0},
            }
        )
    )
    assert junk_label["pace_label"] is None and junk_label["model_mix"] is None
    assert junk_label["used_percentage"] == 9.0
    # Non-finite input never survives to become a bare Infinity/NaN token on the wire
    # (T-klg-02): json.loads parses the literal, parse_usage must still null it.
    nonfinite = parse_usage(
        json.dumps(
            {
                "limits": {
                    "five_hour": {
                        "tokens_used": None,
                        "token_limit": None,
                        "used_percentage": 3.0,
                        "resets_at_epoch": now_plus,
                    }
                },
                "local": {"burn_rate_tokens_per_minute": 1000.0, "cost_usd": float("inf")},
                "pace": {"used_percentage": float("nan"), "elapsed_percentage": 1.0},
            }
        )
    )
    assert nonfinite["cost_usd"] is None and nonfinite["pace_used_pct"] is None
    assert nonfinite["used_percentage"] == 3.0
    assert json.dumps(nonfinite["cost_usd"]) == "null"
    # Hostile text is neutralized before it reaches a terminal or a Gtk label, and
    # bounded in length.
    hostile = parse_usage(
        json.dumps(
            {
                "limits": {
                    "five_hour": {
                        "tokens_used": None,
                        "token_limit": None,
                        "used_percentage": 1.0,
                        "resets_at_epoch": now_plus,
                    }
                },
                "local": {
                    "burn_rate_tokens_per_minute": 1000.0,
                    "model_distribution": [
                        {"family": "opus\x1b[2J\x07\u202e" + "x" * 40, "percentage": 100.0}
                    ],
                },
                "pace": {
                    "label": "slow\x1b[2J\x07\u202edown" + "y" * 40,
                    "used_percentage": 1.0,
                    "elapsed_percentage": 1.0,
                },
            }
        )
    )
    assert all(c.isprintable() for c in hostile["pace_label"])
    assert all(c.isprintable() for c in hostile["model_mix"])
    assert len(hostile["pace_label"]) <= EXTRA_TEXT_MAX_CHARS
    # usage_extra_row: None when everything is absent, one cell alone when only one
    # group is present.
    assert usage_extra_row({}) is None and usage_extra_row(None) is None
    assert usage_extra_row({"cost_usd": 4.2}) == "$4.20"
    assert usage_extra_row({"model_mix": "opus 100%"}) == "opus 100%"
    assert usage_extra_row({"pace_label": "slow down", "pace_used_pct": 27.0}) is None
    # tui_usage_rows: row count and text unchanged when no new fields are present (no
    # silent row growth); one extra trailing row equal to usage_extra_row's output when
    # they are.
    plain_rows = tui_usage_rows(official, time.time())
    assert len(plain_rows) == 1 and plain_rows[0].startswith("5h")  # no weekly, no extras
    rows_with_extras = tui_usage_rows(extras, time.time())
    assert len(rows_with_extras) == len(plain_rows) + 1  # extras carries no weekly block
    assert rows_with_extras[-1] == usage_extra_row(extras)
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
    # fetch_usage: a UnicodeDecodeError (ValueError subclass) escaping subprocess.run
    # with text=True must degrade to None like every other subprocess/OS failure --
    # not kill the poll thread (T-ppf... same "daemon poll thread can never die"
    # contract fetch_usage's own docstring states).
    _orig_run = core.subprocess.run

    def _raise_udec(*_a, **_kw):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    core.subprocess.run = _raise_udec
    try:
        assert core.fetch_usage() is None
    finally:
        core.subprocess.run = _orig_run

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

    # fmt_countdown_short: status-bar width, hours cell dropped under an hour.
    assert fmt_countdown_short(7380) == "2h3m"
    assert fmt_countdown_short(840) == "14m"
    assert fmt_countdown_short(0) == "now"
    assert fmt_countdown_short(-90) == "now"  # a past reset clamps, does not go negative
    assert fmt_countdown_short(3600) == "1h0m"  # exactly an hour keeps the hours cell
    assert fmt_countdown_short(59) == "0m"  # sub-minute is still a minutes cell, not ""

    # statusline_text: the tmux segment string. now=1000 keeps the arithmetic readable.
    assert statusline_text(62, 1000 + 8040, 1000) == "62% 2h14m"
    assert statusline_text(91, 1000 + 2880, 1000) == "91% 48m !"  # red band adds the glyph
    assert statusline_text(89.4, 1000 + 60, 1000) == "89% 1m"  # yellow band: colour only
    assert statusline_text(90, 1000, 1000) == "90% now !"  # band edge is inclusive
    # No percent -> None, so run_segment can hide the segment instead of printing a fake 0%.
    assert statusline_text(None, 1000, 1000) is None
    assert statusline_text("n/a", 1000, 1000) is None
    # Missing/legacy reset degrades to a bare percent rather than a bogus countdown.
    assert statusline_text(62, None, 1000) == "62%"
    assert statusline_text(95, None, 1000) == "95% !"
    # Purity: same inputs, same output, and nothing mutated between calls.
    assert statusline_text(62, 9040, 1000) == statusline_text(62, 9040, 1000)
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
    oldest_hour = int(datetime.datetime(2024, 1, 2, 1).timestamp())
    current_hour = oldest_hour + 23 * 3600
    now_sp = current_hour + 300
    recs_sp = [
        {"t": oldest_hour, "burn": 0.0},
        {"t": oldest_hour + 60, "burn": 100.0},  # bucket 0: 100 tokens
        {"t": current_hour, "burn": 500.0},  # data gap: no inferred usage
        {"t": current_hour + 60, "burn": 900.0},  # bucket 23: 900 tokens
    ]
    spark = trend_sparkline(recs_sp, now_sp)
    assert len(spark) == 24
    assert spark[0] == SPARK_GLYPHS[0]
    assert spark[23] == SPARK_GLYPHS[-1]
    assert spark[12] == SPARK_GAP  # interior empty hour stays a gap
    assert trend_sparkline([], now_sp) == SPARK_GAP * 24
    # Equal usage in consecutive clock hours must render equal bars: a steady burn rate
    # over three full hours is three identical columns, not a staircase.
    hour_start = int(datetime.datetime(2024, 1, 2, 1).timestamp())
    hourly = [{"t": hour_start - 300, "burn": 200.0}]  # seeds a full 5-min interval
    for hour in range(3):
        for minute in range(0, 60, 5):
            hourly.append({
                "t": hour_start + hour * 3600 + minute * 60,
                "burn": 200.0,
            })
    hourly_spark = trend_sparkline(hourly, hour_start + 3 * 3600 - 1)
    assert hourly_spark[21] == hourly_spark[22] == hourly_spark[23]
    # Bins align to clock-hour boundaries, not rolling 60-minute slices anchored at now.
    boundary = int(datetime.datetime(2024, 1, 2, 2).timestamp())
    boundary_spark = trend_sparkline(
        [
            {"t": boundary + 49 * 60, "burn": 0.0},
            {"t": boundary + 50 * 60, "burn": 500.0},
            {"t": boundary + 55 * 60, "burn": 0.0},
            {"t": boundary + 60 * 60, "burn": 0.0},
        ],
        boundary + 90 * 60,
    )
    assert boundary_spark[22] == SPARK_GLYPHS[-1]
    assert boundary_spark[23] == SPARK_GLYPHS[0]
    flat = [{"t": now_sp - h * 3600, "burn": 42.0} for h in range(24)]
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
    # trend_spent integrates burn (tok/min) over sub-GAP_MAX intervals only. burn is a
    # trailing estimate, so each interval takes the burn of the sample ENDING it: two
    # 60s steps at 200 and 300 tok/min -> 200 + 300 = 500. The 9599s hole is a daemon
    # outage, not idle time, so it contributes 0 rather than 400 * 9599/60.
    spend_recs = [
        {"t": 100, "burn": 100.0},
        {"t": 160, "burn": 200.0},
        {"t": 220, "burn": 300.0},
        {"t": 9999, "burn": 400.0},  # spans a > GAP_MAX hole -> not counted
    ]
    assert trend_spent(spend_recs, 0, 1e10) == 500.0
    assert trend_spent(spend_recs, 500, 600) is None  # no interval in window
    assert trend_spent([{"t": 1, "burn": 5.0}], 0, 10) is None  # single sample
    # 14 samples 300s apart: spans TREND_MIN_SPAN, every interval within GAP_MAX.
    # 13 intervals * 60 tok/min * 5 min = 3900 -> "4k".
    spent_bt = [
        {"t": now_bt - i * 300, "pct": 10.0, "burn": 60.0} for i in reversed(range(14))
    ]
    rows_spent = build_trend_rows(spent_bt, now_bt)
    # Row presence and position, not the totals: now_bt is real, so the 3900s span can
    # straddle local midnight (or Monday 00:00) and book part of itself to the prior
    # period. trend_spent's own asserts above pin the arithmetic.
    assert len(rows_spent) == 4 and rows_spent[2].startswith("spent today ")
    assert fmt_tokens(2.1e9) == "2.1G"

    # --- dashboard logic ---
    # Math.min/max applied via .apply(null, arr) throw "Maximum call stack size
    # exceeded" once `arr` crosses a JS-engine argument-count ceiling (~65536 on V8)
    # -- reachable at the default 15s poll interval well within HISTORY_DAYS=30.
    # amin/amax replace them with a manual reduce that has no such ceiling.
    assert "Math.min.apply" not in _DASH_JS and "Math.max.apply" not in _DASH_JS
    assert "function amin(" in _DASH_JS and "function amax(" in _DASH_JS
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
    empty_hm = [[None] * 24 for _ in range(7)]
    assert heatmap_active_span(empty_hm) is None
    span_hm = [[None] * 24 for _ in range(7)]
    span_hm[0][9] = 1.0
    span_hm[6][14] = 2.0
    assert heatmap_active_span(span_hm) == (9, 14)
    one_hour_hm = [[None] * 24 for _ in range(7)]
    one_hour_hm[3][7] = 0.0
    assert heatmap_active_span(one_hour_hm) == (7, 7)
    assert heatmap_active_span(None) is None
    assert heatmap_active_span(123) is None
    assert heatmap_active_span([[None], 123]) is None
    assert spark_levels(123) == []
    parity_hm = [[None] * 24 for _ in range(7)]
    parity_hm[0][0] = 0.0
    parity_hm[0][1] = 5.0
    parity_hm[0][2] = 10.0
    parity_levels = heatmap_levels(parity_hm, 4)
    assert len(parity_levels) == 7
    assert all(len(row) == 24 for row in parity_levels)
    assert parity_levels[0][:4] == [0, 2, 3, None]
    assert heatmap_levels([[None] * 24 for _ in range(7)], 4) is None
    assert heatmap_levels(None, 4) is None
    assert heatmap_levels(parity_hm, 0) is None
    low_hm = [[None] * 24 for _ in range(7)]
    low_hm[3][12] = 0.5
    assert heatmap_levels(low_hm, 4)[3][12] == 2  # dashboard floors max at 1
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
        {"id": "sid-a", "dir": "proj-a", "status": "running", "entered": 100.0, "pane": "%1", "tmux": "/tmp/x", "term": "ghostty"},
        {"dir": "proj-b", "status": "done", "entered": 90.0, "run_dur": 12.5},
    ]
    _snap_out = build_session_snapshot(_snap_in)
    assert _snap_out == [
        {"id": "sid-a", "dir": "proj-a", "status": "running", "entered": 100.0, "frozen": None, "pane": "%1", "tmux": "/tmp/x", "term": "ghostty"},
        {"id": "", "dir": "proj-b", "status": "done", "entered": 90.0, "frozen": 12.5, "pane": "", "tmux": "", "term": ""},
    ]
    assert build_session_snapshot([]) == []
    # purity: calling twice yields independent lists, input untouched.
    assert build_session_snapshot(_snap_in) == _snap_out
    assert build_session_snapshot(_snap_in) is not build_session_snapshot(_snap_in)
    assert _snap_in == [
        {"id": "sid-a", "dir": "proj-a", "status": "running", "entered": 100.0, "pane": "%1", "tmux": "/tmp/x", "term": "ghostty"},
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

    # A parent Stop can fire while background subagents are still running. Claude's
    # hook payload reports those tasks explicitly; the session is only done once the
    # list is empty.
    assert hook_session_event("done", [{"id": "agent-1"}]) == "running"
    assert hook_session_event("done", []) == "done"
    assert hook_session_event("done", None) == "done"
    assert hook_session_event("waiting", [{"id": "agent-1"}]) == "waiting"

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
    assert weekday_hhmm(0).split()[0] == time.strftime("%a", time.localtime(0))
    assert weekday_hhmm(0).endswith(hhmm(0))

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
            self.heatmap = [[None] * 24 for _ in range(7)]
            self.trends = ["line1"]
            self.focused = []

        def focus(self, pane, tmux, title, term):
            self.focused.append((pane, tmux, title, term))

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
    assert set(_snapshot.keys()) == {"heatmap", "sessions", "usage", "trends"}
    assert _snapshot["heatmap"] == _mon.heatmap
    assert _snapshot["usage"] == _mon.usage
    assert _snapshot["trends"] == _mon.trends
    assert _snapshot["sessions"] == build_session_snapshot(list(_mon.sessions.values()))
    assert _snapshot["sessions"][0]["term"] == ""

    # The focus action dispatches to the same Monitor.focus path as tray-menu clicks.
    _focus_server, _focus_client = socket.socketpair()
    _focus_thread = threading.Thread(
        target=_daemon._handle_conn, args=(_mon, _focus_server), daemon=True
    )
    _focus_thread.start()
    _focus_client.sendall(
        b'{"action":"focus","pane":"%7","tmux":"/tmp/t","title":"proj","term":"ghostty"}\n'
    )
    _focus_client.shutdown(socket.SHUT_WR)
    _focus_thread.join(timeout=5)
    _focus_client.close()
    assert not _focus_thread.is_alive()
    assert _mon.focused == [("%7", "/tmp/t", "proj", "ghostty")]

    # An over-long routing value rejects the whole action (D-12 parity with the
    # Rust client's MAX_ROUTE_CHARS) rather than focusing a clipped/wrong target.
    _huge_server, _huge_client = socket.socketpair()
    _huge_thread = threading.Thread(
        target=_daemon._handle_conn, args=(_mon, _huge_server), daemon=True
    )
    _huge_thread.start()
    _huge_client.sendall(
        (
            json.dumps(
                {"action": "focus", "pane": "%" * 300, "tmux": "", "title": "", "term": ""}
            )
            + "\n"
        ).encode("utf-8")
    )
    _huge_client.shutdown(socket.SHUT_WR)
    _huge_thread.join(timeout=5)
    _huge_client.close()
    assert not _huge_thread.is_alive()
    assert _mon.focused == [("%7", "/tmp/t", "proj", "ghostty")]  # unchanged

    # --- claude-send.py: send_event must not leak the socket fd on failure ---
    # Loaded by path like claude-monitor.py above: claude-send.py's hyphenated name
    # is not importable as a package module.
    _send_path = pathlib.Path(__file__).resolve().parent.parent / "claude-send.py"
    _send_spec = importlib.util.spec_from_file_location("_claude_send_helper", _send_path)
    _send = importlib.util.module_from_spec(_send_spec)
    _send_spec.loader.exec_module(_send)

    class _FailingSocket:
        """A socket stand-in whose sendall raises, so send_event's finally-close
        is the only thing that can ever close it -- exactly the fd-leak path
        core.query_snapshot's docstring names claude-send.py:34-41 for.
        """

        def __init__(self):
            self.closed = False

        def settimeout(self, _t):
            pass

        def connect(self, _path):
            pass

        def sendall(self, _data):
            raise OSError("broken pipe")

        def close(self):
            self.closed = True

    _fsock = _FailingSocket()
    _send.send_event({"event": "done"}, "/nonexistent", sock_factory=lambda *_a, **_kw: _fsock)
    assert _fsock.closed, "socket leaked when sendall raised"

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

    # --- focus argv: the attached client must actually move ---
    # switch-client first, or focusing a pane in another tmux session moves nothing the
    # user can see and the tray appears to open the wrong Claude.
    _cmds = focus_tmux_cmds("%5", "/tmp/tmux-1000/default,4242,1")
    assert [c[-3] for c in _cmds] == [
        "switch-client",
        "select-window",
        "select-pane",
    ], _cmds
    # -S addresses the server without naming a current session (an exported TMUX would
    # make tmux pick a client already attached to the target -- the wrong one to move).
    assert all(c[:3] == ["tmux", "-S", "/tmp/tmux-1000/default"] for c in _cmds), _cmds
    assert all(c[-2:] == ["-t", "%5"] for c in _cmds), _cmds
    # No TMUX on the session record -> no -S, talk to the ambient server.
    assert focus_tmux_cmds("%1", "") == [
        ["tmux", "switch-client", "-t", "%1"],
        ["tmux", "select-window", "-t", "%1"],
        ["tmux", "select-pane", "-t", "%1"],
    ]

    # --- tui focus client ---
    with tempfile.TemporaryDirectory() as _focus_dir:
        _focus_path = str(pathlib.Path(_focus_dir) / "focus.sock")
        _listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        _listener.bind(_focus_path)
        _listener.listen(1)
        _received = []

        def _receive_focus():
            conn, _ = _listener.accept()
            try:
                _received.append(json.loads(read_line(conn)))
            finally:
                conn.close()

        _receiver = threading.Thread(target=_receive_focus, daemon=True)
        _receiver.start()
        request_focus(
            {"dir": "proj", "pane": "%3", "tmux": "/tmp/tmux", "term": "ghostty"},
            path=_focus_path,
        )
        _receiver.join(timeout=5)
        _listener.close()
        assert not _receiver.is_alive()
        assert _received == [
            {
                "action": "focus",
                "pane": "%3",
                "tmux": "/tmp/tmux",
                "title": "proj",
                "term": "ghostty",
            }
        ]
    try:
        request_focus({"dir": "missing target"})
        assert False, "unfocusable session should raise"
    except ValueError:
        pass

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

    # --- tui band (TUI-06) ---
    # Fixed three-band shape, both sides of each cutoff: <70 green / 70-<90 yellow / >=90 red.
    assert band(69) == "green" and band(70) == "yellow"
    assert band(89) == "yellow" and band(90) == "red"
    # Total over out-of-range / over-limit input -- never clamped, never raises.
    assert band(0) == "green" and band(100) == "red" and band(473.5) == "red"
    assert band(-5) == "green"  # a negative (clock-skew) percent still bands, does not raise
    # D-01: cutoffs are literals, independent of the mutable badge threshold. The badge
    # USAGE_THRESHOLD default (80) lands in band's yellow zone, not on its yellow->red line.
    assert band(80) == "yellow"

    # --- tui gauge fill (TUI-07) ---
    _gw = 20
    assert gauge_fill(0, _gw) == 0  # empty bar at 0%
    assert gauge_fill(100, _gw) == _gw  # full bar at 100%
    assert gauge_fill(50, _gw) == 10  # mid value
    assert gauge_fill(150, _gw) == _gw  # over-limit clamps to full, never overflows the bar
    assert gauge_fill(-5, _gw) == 0  # negative clamps to empty
    # monotonic non-decreasing in pct across 0..100 (btop's fill only ever grows with usage).
    _walk = [gauge_fill(p, _gw) for p in range(0, 101)]
    assert _walk == sorted(_walk)
    assert min(_walk) == 0 and max(_walk) == _gw

    # --- tui spark levels (TUI-08) ---
    # Round-trip: the full ramp decodes to its own indices; no new trend math, pure inverse.
    assert spark_levels(SPARK_GLYPHS) == [0, 1, 2, 3, 4, 5, 6, 7]
    assert spark_levels(SPARK_GAP) == [None]  # an empty-hour column is not a level
    assert spark_levels("?") == [None]  # unknown/hostile char is tolerated -> None, never raises
    # A real trend_sparkline output (`spark` from the trend-logic block) decodes to 24
    # columns, each an int 0..7 or None -- the exact column heights the graph draws.
    _slv = spark_levels(spark)
    assert len(_slv) == 24
    assert all(x is None or (isinstance(x, int) and 0 <= x <= 7) for x in _slv)
    assert _slv[0] == 0 and _slv[23] == 7 and _slv[12] is None  # matches the spark asserts above

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

    # --- tui session band (TUI-09) ---
    # Fixed D-07 palette; the token is a rich style name applied per-cell in claude-tui.py.
    assert sess_status_band("waiting") == "yellow"
    assert sess_status_band("running") == "green"
    assert sess_status_band("done") == "dim"
    # Total like sess_rank: any unknown/empty/None status -> one neutral default, never raises.
    assert sess_status_band("") == "default"
    assert sess_status_band("zombie") == "default"
    assert sess_status_band(None) == "default"
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
    # A project dir is an arbitrary repo path. Printable content (including rich markup)
    # passes through byte-for-byte -- markup injection is closed at the widget (Plan 09-02).
    # But sess_rows strips C0/C1 control characters via _safe_cell so an ESC-based terminal
    # sequence in a hostile dir name cannot reach the terminal (T-09-01, control half):
    assert _safe_cell("[bold]myrepo[/]") == "[bold]myrepo[/]"  # printable markup untouched
    assert _safe_cell("A\x1b[2JB") == "A?[2JB"  # ESC -> '?', clear-screen defused
    assert _safe_cell("\x07\x08\x1b\x9b") == "????"  # BEL/BS/ESC/CSI all stripped
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
    # "dir" present but null (or any wrong type), not just missing -- exactly what a
    # malformed/legacy socket snapshot can send -- must degrade to "" rather than
    # TypeError-ing inside _safe_cell's `for c in s` loop.
    _null_dir = [
        {"dir": None, "status": "done", "entered": _unow - 10, "frozen": 5},
        {"dir": 42, "status": "waiting", "entered": _unow - 5, "frozen": 3},
    ]
    assert [r[1] for r in sess_rows(_null_dir, _unow)] == ["", ""]
    # purity: input list and its dicts untouched, and two calls return independent lists.
    _srows_before = [dict(s) for s in _srows_in]
    _srows_out = sess_rows(_srows_in, _unow)
    assert [dict(s) for s in _srows_in] == _srows_before
    assert sess_rows(_srows_in, _unow) == _srows_out
    assert sess_rows(_srows_in, _unow) is not sess_rows(_srows_in, _unow)

    print("ok")
