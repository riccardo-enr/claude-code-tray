"""Author the shared snapshot fixture corpus.

Kept as a generator rather than 19 hand-typed files because several fixtures
carry raw control bytes that are hostile to paste into an editor -- which is
the same reason they need to exist.
"""

import json
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshot")
os.makedirs(OUT, exist_ok=True)

ESC = "\x1b"
BEL = "\x07"
BS = "\x08"
RLO = "\u202e"  # bidi right-to-left override: Trojan Source

F = {}

F["valid-full"] = {
    "note": "The happy path: every section present, both quota caps, token counts, "
            "one session per status.",
    "wire": {
        "usage": {"used_percentage": 42.5, "resets_at_epoch": 1700000000,
                  "burn_rate_per_min": 1200, "tokens_used": 417000, "token_limit": 880000,
                  "seven_day_pct": 15.0, "seven_day_reset": 1700500000},
        "trends": ["today 13.8M/hr | wk 16.5M/hr", "peak hour: 14:00 (29.3M/hr)"],
        "heatmap": [[None] * 24 for _ in range(7)],
        "sessions": [
            {"id": "s1", "dir": "~/code/tray", "status": "running", "entered": 1699999000,
             "frozen": None, "pane": "%1", "tmux": "main", "term": "ghostty"},
            {"id": "s2", "dir": "~/code/uav", "status": "waiting", "entered": 1699998000,
             "frozen": 300, "pane": "%2", "tmux": "main", "term": "ghostty"},
        ],
    },
    "expect": {
        "usage": {"used_percentage": 42.5, "resets_at_epoch": 1700000000,
                  "burn_rate_per_min": 1200, "tokens_used": 417000, "token_limit": 880000,
                  "seven_day_pct": 15.0, "seven_day_reset": 1700500000},
        "trends": {"rows": ["today 13.8M/hr | wk 16.5M/hr", "peak hour: 14:00 (29.3M/hr)"]},
        "heatmap": {"rows": 7, "cols": 24},
        "sessions": {"rejected": 0, "entries": [
            {"id": "s1", "dir": "~/code/tray", "status": "running", "focusable": True},
            {"id": "s2", "dir": "~/code/uav", "status": "waiting", "focusable": True},
        ]},
    },
}

F["cold-start-null-sections"] = {
    "note": "What the daemon actually sends before its first usage poll. Null is "
            "legitimate absence, never malformation -- conflating the two would show a "
            "malformed-data warning at every startup.",
    "wire": {"usage": None, "trends": None, "heatmap": None, "sessions": []},
    "expect": {"usage": "absent", "trends": "absent", "heatmap": "absent",
               "sessions": {"rejected": 0, "entries": []}},
}

F["missing-optional-fields"] = {
    "note": "--api mode: percentages only, token counts null, no weekly block at all "
            "(older CLI). All three are absence, so the 5h gauge still draws.",
    "wire": {"usage": {"used_percentage": 7.5, "resets_at_epoch": 1700000000,
                       "burn_rate_per_min": 90, "tokens_used": None, "token_limit": None}},
    "expect": {"usage": {"used_percentage": 7.5, "tokens_used": None, "token_limit": None,
                         "seven_day_pct": None, "seven_day_reset": None}},
}

F["partial-sections"] = {
    "note": "D-02, the central contract: a malformed heatmap must not blank the quota "
            "gauges or the sessions table.",
    "wire": {"usage": {"used_percentage": 91.0, "resets_at_epoch": 1700000000,
                       "burn_rate_per_min": 5},
             "heatmap": "not a grid",
             "trends": [42],
             "sessions": [{"id": "a", "dir": "~/x", "status": "done", "pane": "%1"}]},
    "expect": {"usage": {"used_percentage": 91.0}, "heatmap": "malformed",
               "trends": "malformed",
               "sessions": {"rejected": 0, "entries": [{"id": "a", "status": "done"}]}},
}

F["unknown-fields-ignored"] = {
    "note": "Forward compatibility: a newer daemon adding fields must not break an "
            "older client.",
    "wire": {"usage": {"used_percentage": 1.0, "resets_at_epoch": 2, "burn_rate_per_min": 3,
                       "brand_new_metric": {"nested": [1, 2]}},
             "some_future_section": {"anything": True},
             "sessions": [{"id": "a", "dir": "~/x", "status": "running", "pane": "%1",
                           "future_field": "ignored"}]},
    "expect": {"usage": {"used_percentage": 1.0},
               "sessions": {"rejected": 0, "entries": [{"id": "a", "focusable": True}]}},
}

F["wrong-types-not-coerced"] = {
    "note": "D-04: a numeric string is contract drift, not a number. Coercing it here "
            "would put a silently wrong percentage on screen.",
    "wire": {"usage": {"used_percentage": "42.5", "resets_at_epoch": 2,
                       "burn_rate_per_min": 3}},
    "expect": {"usage": "malformed"},
}

F["wrong-types-booleans-are-not-numbers"] = {
    "note": "JSON true is not 1. A client whose JSON reader conflates them would pass "
            "the other fixtures by accident, which is why this one is pinned separately.",
    "wire": {"usage": {"used_percentage": True, "resets_at_epoch": 2,
                       "burn_rate_per_min": 3}},
    "expect": {"usage": "malformed"},
}

F["weekly-junk-degrades-only-itself"] = {
    "note": "The weekly block is secondary; junk there must never cost the 5h numbers.",
    "wire": {"usage": {"used_percentage": 55.0, "resets_at_epoch": 1700000000,
                       "burn_rate_per_min": 3,
                       "seven_day_pct": "junk", "seven_day_reset": []}},
    "expect": {"usage": {"used_percentage": 55.0, "seven_day_pct": None,
                         "seven_day_reset": None}},
}

F["sessions-narrow-rejection"] = {
    "note": "D-03: one bad entry costs that entry. Survivors keep daemon order and the "
            "reject count is retained, so a UI can say 2 sessions, 2 unreadable.",
    "wire": {"sessions": [
        {"id": "ok1", "dir": "~/a", "status": "running", "pane": "%1"},
        {"id": 42, "dir": "~/b", "status": "running", "pane": "%2"},
        "not an object",
        {"id": "ok2", "dir": "~/c", "status": "done", "pane": "%3"},
    ]},
    "expect": {"sessions": {"rejected": 2, "entries": [
        {"id": "ok1", "dir": "~/a"}, {"id": "ok2", "dir": "~/c"},
    ]}},
}

F["sessions-no-placeholder-invented"] = {
    "note": "A rejected entry is dropped, never replaced by a blank row -- a renderable "
            "row implies data we do not have.",
    "wire": {"sessions": [{"id": 1}, {"id": 2}, {"id": 3}]},
    "expect": {"sessions": {"rejected": 3, "entries": []}},
}

F["hostile-terminal-controls"] = {
    "note": "RTUI-13. A repo can legally contain a directory named with a CSI "
            "clear-screen or an OSC 52 clipboard write. Each complete sequence collapses "
            "to one marker; no ESC byte survives.",
    "wire": {"sessions": [
        {"id": "a", "dir": "~/" + ESC + "[2Jcleared", "status": "running", "pane": "%1"},
        {"id": "b", "dir": "~/" + ESC + "]52;c;aGk=" + BEL + "clip", "status": "done",
         "pane": "%2"},
        {"id": "c", "dir": "bell" + BEL + "back" + BS + "space", "status": "done",
         "pane": "%3"},
        {"id": "d", "dir": "gj" + RLO + "pj.txt", "status": "done", "pane": "%4"},
    ]},
    "expect": {"sessions": {"rejected": 0, "entries": [
        {"id": "a", "dir": "~/?cleared"},
        {"id": "b", "dir": "~/?clip"},
        {"id": "c", "dir": "bell?back?space"},
        {"id": "d", "dir": "gj?pj.txt"},
    ]}},
}

F["hostile-controls-in-trend-rows"] = {
    "note": "Daemon-built text still crosses the trust boundary. 'The daemon made this "
            "string' is not the same as 'this string is safe'.",
    "wire": {"trends": ["peak " + ESC + "]52;c;x" + BEL + "hour", ESC + "[31mred"]},
    "expect": {"trends": {"rows": ["peak ?hour", "?red"]}},
}

F["markup-like-text-preserved"] = {
    "note": "D-11: printable markup is a legitimate directory name and survives byte "
            "for byte. Markup injection is closed at the renderer, not by mangling user "
            "content here.",
    "wire": {"trends": ["[bold]today[/] 1k/hr"],
             "sessions": [{"id": "a", "dir": "[bold]repo[/]", "status": "done",
                           "pane": "%1"}]},
    "expect": {"trends": {"rows": ["[bold]today[/] 1k/hr"]},
               "sessions": {"rejected": 0, "entries": [{"dir": "[bold]repo[/]"}]}},
}

F["focus-targets-valid-and-invalid"] = {
    "note": "A tmux pane is focusable; so is Zed by window title alone; a terminal with "
            "neither is not. Mirrors request_focus's own refusal.",
    "wire": {"sessions": [
        {"id": "pane", "dir": "~/a", "status": "running", "pane": "%1", "term": "ghostty"},
        {"id": "zed", "dir": "~/b", "status": "running", "pane": "", "term": "zed"},
        {"id": "none", "dir": "~/c", "status": "running", "pane": "", "term": "ghostty"},
    ]},
    "expect": {"sessions": {"rejected": 0, "entries": [
        {"id": "pane", "focusable": True},
        {"id": "zed", "focusable": True},
        {"id": "none", "focusable": False},
    ]}},
}

F["focus-routing-value-over-bound"] = {
    "note": "D-12: an over-long pane id rejects its entry rather than being truncated. "
            "A clipped routing value would focus the wrong window, which is worse than "
            "not focusing at all.",
    "wire": {"sessions": [
        {"id": "ok", "dir": "~/a", "status": "running", "pane": "%1"},
        {"id": "huge", "dir": "~/b", "status": "running", "pane": "%" * 300},
    ]},
    "expect": {"sessions": {"rejected": 1, "entries": [{"id": "ok"}]}},
}

F["heatmap-null-cell-is-no-data"] = {
    "note": "A null cell means no samples for that hour, which is distinct from a "
            "genuine zero. Collapsing them would draw a cold hour as a worked hour.",
    "wire": {"heatmap": [[0.0] + [None] * 23] + [[None] * 24 for _ in range(6)]},
    "expect": {"heatmap": {"rows": 7, "cols": 24, "cell_0_0": 0.0, "cell_0_1": None}},
}

F["heatmap-wrong-shape"] = {
    "note": "A grid that is not 7x24 is malformed, never reshaped or padded.",
    "wire": {"heatmap": [[None] * 23 for _ in range(7)]},
    "expect": {"heatmap": "malformed"},
}

for name, body in F.items():
    doc = {"name": name, "note": body["note"],
           "wire": json.dumps(body["wire"], ensure_ascii=False),
           "expect": body["expect"]}
    with open(os.path.join(OUT, name + ".json"), "w") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

# Inputs that are not valid UTF-8, or not valid JSON, and so cannot be carried
# as a JSON string. Byte arrays keep them reviewable without an editor mangling
# them on save.
RAW = {
    "malformed-json-truncated": (
        b'{"usage": {"used_percentage": 4',
        "A daemon that closed mid-line. Decode, not transport -- we reached it, it just "
        "did not finish.",
        {"error": "decode"}),
    "malformed-json-not-json": (
        b"this is not json at all\n",
        "Anything non-JSON on the line is a decode failure.",
        {"error": "decode"}),
    "root-not-an-object-null": (
        b"null\n",
        "D-01: a bare null must be rejected outright. Accepting it would rebind live "
        "state to nothing, which reads on screen as a cold start under a live header.",
        {"error": "schema"}),
    "root-not-an-object-array": (
        b"[1, 2, 3]\n",
        "Valid JSON, wrong root type. No section to salvage, so the whole fetch is "
        "rejected.",
        {"error": "schema"}),
    "invalid-utf8-in-session-dir": (
        b'{"sessions": [{"id": "a", "dir": "~/caf\xe9bad", "status": "done", '
        b'"pane": "%1"}]}\n',
        "A latin-1 byte inside a path. Decodes lossily like the Python client does "
        "rather than raising -- a non-UTF-8 directory name must not take down the fetch.",
        {"sessions": {"rejected": 0, "entries": [{"id": "a"}]}}),
}

for name, (wire, note, expect) in RAW.items():
    doc = {"name": name, "note": note, "wire_bytes": list(wire), "expect": expect}
    with open(os.path.join(OUT, name + ".json"), "w") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")

print("wrote %d fixtures to %s" % (len(F) + len(RAW), OUT))
