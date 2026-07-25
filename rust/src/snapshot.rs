/*
Normalization: raw wire JSON to deterministic, render-ready state.

This module is the whole point of Phase 11. Everything above it (Phase 12's
renderer, Phase 13's event loop, Phase 14's parity harness) consumes `Snapshot`
and never `serde_json::Value`. That boundary is what makes "panic-free" a
property of the design rather than a promise: by the time a value reaches a
renderer it has already been type-checked, sanitized and bounded, so there is
no unwrap left to fail.

Three rules drive the shape here.

**Section independence (D-02).** Once the root object is valid, `usage`,
`trends`, `heatmap` and `sessions` are normalized separately. A daemon that
starts emitting a malformed `heatmap` must not blank the quota gauges. Each
section is therefore a `Section<T>` rather than an `Option<T>`, because three
states are genuinely distinct and collapsing them loses information the UI
needs: *present*, *legitimately absent* (the daemon really does send
`"usage": null` before its first poll), and *malformed* (the daemon sent
something, and it was wrong).

**Narrow rejection (D-03).** Inside `sessions`, one bad entry costs that entry.
Valid siblings survive in daemon order, and the count of rejects is retained so
a UI can say "3 sessions (1 unreadable)" instead of quietly showing three of
four. Inventing a placeholder session from invalid data is specifically not
allowed -- a renderable row implies data we do not have.

**No coercion (D-04).** A numeric string stays wrong; it does not become a
number. An arbitrary value does not become a display string. This is why
normalization walks `Value` by hand instead of deriving `Deserialize`: serde's
default behaviour and most of its attributes exist to be permissive, and
permissiveness here hides contract drift until it surfaces as a wrong number on
screen. Unknown fields, by contrast, are ignored -- that is forward
compatibility, not drift.

The wire contract being consumed is fixed and lives in
`claude-monitor.py::_handle_conn`:

    {"heatmap": [[float|null; 24]; 7] | null,
     "sessions": [{id, dir, status, entered, frozen, pane, tmux, term}],
     "usage":    {tokens_used, token_limit, used_percentage, resets_at_epoch,
                  burn_rate_per_min, seven_day_pct, seven_day_reset,
                  cost_usd, cost_per_hour, pace_used_pct, pace_elapsed_pct,
                  pace_label, model_mix} | null,
     "trends":   [string] | null}
*/

use std::fmt;

use serde_json::Value;

use crate::error::ClientError;
use crate::sanitize::{sanitize_display, sanitize_display_bounded, MAX_ROUTE_CHARS};

/* Cap for the short CLI-chosen labels (pace, model mix). Matches
`claude_monitor.core.EXTRA_TEXT_MAX_CHARS` -- the daemon already bounds them; this is the
second wall, and it is tight because they share one narrow row. */
const MAX_LABEL_CHARS: usize = 32;

/* Rows and columns of the heatmap grid: Monday-Sunday by hour 0-23. Fixed by
`claude_monitor.core.heatmap_buckets`. */
pub const HEATMAP_ROWS: usize = 7;
pub const HEATMAP_COLS: usize = 24;

/*
The availability of one snapshot section.

`Malformed` carries a short static reason. It is `&'static str` rather than a
formatted string on purpose: the reason describes *our* contract, never the
payload, so it can never carry attacker-controlled text into a UI.
*/
#[derive(Debug, Clone, PartialEq)]
pub enum Section<T> {
    Present(T),
    /* Key missing, or explicitly null. The daemon does this legitimately
    before its first usage poll and before enough history exists for trends. */
    Absent,
    Malformed(&'static str),
}

impl<T> Section<T> {
    pub fn as_ref(&self) -> Section<&T> {
        match self {
            Section::Present(v) => Section::Present(v),
            Section::Absent => Section::Absent,
            Section::Malformed(r) => Section::Malformed(r),
        }
    }

    pub fn present(&self) -> Option<&T> {
        match self {
            Section::Present(v) => Some(v),
            _ => None,
        }
    }

    pub fn is_present(&self) -> bool {
        matches!(self, Section::Present(_))
    }

    pub fn is_absent(&self) -> bool {
        matches!(self, Section::Absent)
    }

    pub fn is_malformed(&self) -> bool {
        matches!(self, Section::Malformed(_))
    }

    /* The stable spelling used by the fixture corpus. */
    pub fn state_name(&self) -> &'static str {
        match self {
            Section::Present(_) => "present",
            Section::Absent => "absent",
            Section::Malformed(_) => "malformed",
        }
    }
}

/*
Opaque focus-routing values (D-12).

These are deliberately NOT display strings. They are never sanitized, never
truncated and never rendered -- rewriting a pane id would focus the wrong
window, which is a worse outcome than a failed focus. They are only
type-validated and length-bounded, then handed straight back to the daemon.

`Debug` is implemented by hand to print lengths instead of contents, so a raw
hostile value cannot reach a log or a test failure message.
*/
#[derive(Clone, PartialEq, Eq, Default)]
pub struct FocusTarget {
    pub pane: String,
    pub tmux: String,
    /* The daemon's focus verb calls this field `title` and fills it from the
    session's `dir`. Named for the wire, not for what it happens to hold. */
    pub title: String,
    pub term: String,
}

impl FocusTarget {
    /*
    Whether this target can actually be focused.

    Mirrors `claude_monitor.core.request_focus`: a target needs a tmux pane,
    unless the terminal is Zed, which is focused by window title alone.
    */
    pub fn focusable(&self) -> bool {
        !self.pane.is_empty() || self.term == "zed"
    }

    fn within_bounds(&self) -> bool {
        [&self.pane, &self.tmux, &self.title, &self.term]
            .iter()
            .all(|v| v.chars().count() <= MAX_ROUTE_CHARS)
    }
}

impl fmt::Debug for FocusTarget {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        /* Lengths only. Contents are attacker-controlled (D-12). */
        f.debug_struct("FocusTarget")
            .field("pane_len", &self.pane.chars().count())
            .field("tmux_len", &self.tmux.chars().count())
            .field("title_len", &self.title.chars().count())
            .field("term_len", &self.term.chars().count())
            .field("focusable", &self.focusable())
            .finish()
    }
}

/*
The 5-hour and 7-day quota block.

Required fields mirror `claude_monitor.core.parse_usage`: without a percentage,
a reset epoch and a burn rate there is nothing to draw, so the whole section is
malformed. Token counts are legitimately null under the CLI's `--api` mode
(percentages only), so they are `Option` -- but a *string* where a number
belongs is malformed, not absent, because that is contract drift.

The weekly block degrades on its own: an older CLI omits it entirely, and junk
there must not cost us the 5-hour numbers.
*/
#[derive(Debug, Clone, PartialEq)]
pub struct Usage {
    pub used_percentage: f64,
    pub resets_at_epoch: f64,
    pub burn_rate_per_min: f64,
    pub tokens_used: Option<f64>,
    pub token_limit: Option<f64>,
    pub seven_day_pct: Option<f64>,
    pub seven_day_reset: Option<f64>,
    /* Cost, pace and model mix. Follows the weekly block's posture: absent or
    wrong-typed degrades the field, never the section, because a cosmetic extra is
    not allowed to cost the gauge. The two text fields are CLI-chosen strings, so they
    arrive sanitized like every other display string. */
    pub cost_usd: Option<f64>,
    pub cost_per_hour: Option<f64>,
    pub pace_used_pct: Option<f64>,
    pub pace_elapsed_pct: Option<f64>,
    pub pace_label: Option<String>,
    pub model_mix: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Session {
    /* Identity, not a display string: raw and unsanitized on purpose. The renderer
    never draws `id` -- it exists only so `main.rs::stable_key` can key a session
    across refreshes. Sanitizing it would collapse any complete terminal control
    sequence to the same one marker, so two daemon-distinct ids differing only in
    escape-sequence content would collide onto the same stable key and the second
    session could never be selected. `dir` and `status` below ARE rendered, so they
    stay sanitized. */
    pub id: String,
    /* Display strings: already sanitized and bounded. */
    pub dir: String,
    pub status: String,
    /* Epoch seconds this session entered its current status. */
    pub entered: Option<f64>,
    /* Frozen run duration for a non-running session. */
    pub frozen: Option<f64>,
    /* Opaque routing values. Never rendered. */
    pub focus: FocusTarget,
}

/*
The sessions section: survivors in daemon order, plus how many were dropped.

`rejected` is not diagnostics-only decoration. Without it a UI cannot tell
"two sessions are running" from "two sessions are running and one is
unreadable", and the second is a state a user should be able to see.
*/
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Sessions {
    pub entries: Vec<Session>,
    pub rejected: usize,
}

/* Mean quota percent consumed per (weekday, hour) cell. `None` means no data
for that cell, which is distinct from a genuine zero. */
#[derive(Debug, Clone, PartialEq)]
pub struct Heatmap {
    pub grid: Vec<Vec<Option<f64>>>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Snapshot {
    pub usage: Section<Usage>,
    /* Pre-formatted trend row strings, produced by
    `claude_monitor.core.build_trend_rows`. Sanitized here anyway: they are
    daemon-sourced text reaching a terminal, and "the daemon built it" is not
    the same as "it is safe". */
    pub trends: Section<Vec<String>>,
    /* The trend graph's y-axis ticks, pre-formatted by the daemon, one per graph
    row, TOP ROW FIRST; an untocked row is "". Optional rather than a Section: a
    missing axis costs labels, not a panel, so there is no degraded state worth
    distinguishing from absent. */
    pub trend_axis: Option<Vec<String>>,
    pub heatmap: Section<Heatmap>,
    pub sessions: Section<Sessions>,
}

impl Snapshot {
    /*
    Normalize a decoded root value.

    The root must be a JSON object. Anything else -- `null`, an array, a bare
    number -- is a whole-fetch rejection (D-01), because there is no section to
    salvage and because a bare `null` would otherwise rebind live state to
    "nothing", which reads on screen as a cold start under a live header.

    This function is total below the root: once the root is an object it always
    returns a `Snapshot`, with bad sections marked rather than raised.
    */
    pub fn from_value(root: &Value) -> Result<Snapshot, ClientError> {
        let obj = match root.as_object() {
            Some(map) => map,
            None => {
                return Err(ClientError::schema(format!(
                    "snapshot root was {}, not an object",
                    kind_of(root)
                )))
            }
        };

        Ok(Snapshot {
            usage: normalize_usage(obj.get("usage")),
            trends: normalize_trends(obj.get("trends")),
            trend_axis: normalize_trend_axis(obj.get("trend_axis")),
            heatmap: normalize_heatmap(obj.get("heatmap")),
            sessions: normalize_sessions(obj.get("sessions")),
        })
    }

    /* Convenience for the fixture harness and for callers holding raw bytes. */
    pub fn from_slice(bytes: &[u8]) -> Result<Snapshot, ClientError> {
        let text = String::from_utf8_lossy(bytes);
        Snapshot::from_json(&text)
    }

    pub fn from_json(text: &str) -> Result<Snapshot, ClientError> {
        let root: Value = serde_json::from_str(text.trim_end_matches('\n'))
            .map_err(|e| ClientError::decode(format!("response was not JSON (at line {})", e.line())))?;
        Snapshot::from_value(&root)
    }
}

/* A stable, payload-free name for a JSON value's type. Used in error context,
so it must never include the value itself. */
fn kind_of(v: &Value) -> &'static str {
    match v {
        Value::Null => "null",
        Value::Bool(_) => "boolean",
        Value::Number(_) => "number",
        Value::String(_) => "string",
        Value::Array(_) => "array",
        Value::Object(_) => "object",
    }
}

/*
A JSON number, and only a JSON number.

`Value::as_f64` is already strict -- it returns `None` for booleans and for
numeric strings -- which is exactly the no-coercion rule D-04 asks for. This
wrapper exists to make that reliance explicit rather than incidental.
*/
fn num(v: &Value) -> Option<f64> {
    v.as_f64()
}

/* Distinguish "field absent or null" from "field present with the wrong type".
The first is legitimate; the second is drift. */
enum Field<T> {
    Value(T),
    Absent,
    WrongType,
}

fn number_field(obj: &serde_json::Map<String, Value>, key: &str) -> Field<f64> {
    match obj.get(key) {
        None | Some(Value::Null) => Field::Absent,
        Some(v) => match num(v) {
            Some(n) => Field::Value(n),
            None => Field::WrongType,
        },
    }
}

fn normalize_usage(raw: Option<&Value>) -> Section<Usage> {
    let value = match raw {
        None | Some(Value::Null) => return Section::Absent,
        Some(v) => v,
    };
    let obj = match value.as_object() {
        Some(map) => map,
        None => return Section::Malformed("usage was not an object"),
    };

    /* Required trio. A missing or mistyped member of it means there is nothing
    drawable, so the section is malformed rather than partially present. */
    let used_percentage = match number_field(obj, "used_percentage") {
        Field::Value(n) => n,
        _ => return Section::Malformed("usage.used_percentage missing or not a number"),
    };
    let resets_at_epoch = match number_field(obj, "resets_at_epoch") {
        Field::Value(n) => n,
        _ => return Section::Malformed("usage.resets_at_epoch missing or not a number"),
    };
    let burn_rate_per_min = match number_field(obj, "burn_rate_per_min") {
        Field::Value(n) => n,
        _ => return Section::Malformed("usage.burn_rate_per_min missing or not a number"),
    };

    /* Token counts: null is legitimate (`--api` reports percentages only), a
    wrong type is not. */
    let tokens_used = match number_field(obj, "tokens_used") {
        Field::Value(n) => Some(n),
        Field::Absent => None,
        Field::WrongType => return Section::Malformed("usage.tokens_used was not a number"),
    };
    let token_limit = match number_field(obj, "token_limit") {
        Field::Value(n) => Some(n),
        Field::Absent => None,
        Field::WrongType => return Section::Malformed("usage.token_limit was not a number"),
    };

    /* Weekly block is secondary: junk there degrades only itself, matching
    parse_usage's own posture. */
    let seven_day_pct = match number_field(obj, "seven_day_pct") {
        Field::Value(n) => Some(n),
        _ => None,
    };
    let seven_day_reset = match number_field(obj, "seven_day_reset") {
        Field::Value(n) => Some(n),
        _ => None,
    };

    /* Extras: same degrade-alone posture as the weekly block. A wrong type here is
    silently dropped rather than escalated, because none of these can change what the
    gauges say -- claude_monitor.core.parse_usage nulls them the same way. */
    let opt_num = |key: &str| match number_field(obj, key) {
        Field::Value(n) => Some(n),
        _ => None,
    };
    /* The daemon built these strings, but they originate in CLI output (a pace label,
    a model family) -- "the daemon built it" is not "it is safe", the same reasoning
    the trends rows already carry, so they are sanitized again at this boundary. */
    let opt_text = |key: &str| match obj.get(key) {
        Some(Value::String(s)) => {
            let cleaned = sanitize_display_bounded(s, MAX_LABEL_CHARS);
            if cleaned.is_empty() {
                None
            } else {
                Some(cleaned)
            }
        }
        _ => None,
    };

    Section::Present(Usage {
        used_percentage,
        resets_at_epoch,
        burn_rate_per_min,
        tokens_used,
        token_limit,
        seven_day_pct,
        seven_day_reset,
        cost_usd: opt_num("cost_usd"),
        cost_per_hour: opt_num("cost_per_hour"),
        pace_used_pct: opt_num("pace_used_pct"),
        pace_elapsed_pct: opt_num("pace_elapsed_pct"),
        pace_label: opt_text("pace_label"),
        model_mix: opt_text("model_mix"),
    })
}

fn normalize_trends(raw: Option<&Value>) -> Section<Vec<String>> {
    let value = match raw {
        None | Some(Value::Null) => return Section::Absent,
        Some(v) => v,
    };
    let arr = match value.as_array() {
        Some(a) => a,
        None => return Section::Malformed("trends was not an array"),
    };
    let mut rows = Vec::with_capacity(arr.len());
    for item in arr {
        match item.as_str() {
            /* Daemon-built text still crosses the trust boundary. */
            Some(s) => rows.push(sanitize_display(s)),
            None => return Section::Malformed("trends contained a non-string row"),
        }
    }
    Section::Present(rows)
}

/* Daemon-built, but still crossing the trust boundary into a terminal, and bounded
per tick so a runaway label cannot push the graph off-screen. Anything but an array
of strings -- including a bare string, which was the pre-tick wire shape -- degrades
to no axis at all rather than a half-drawn one. An all-empty array is no axis too. */
fn normalize_trend_axis(raw: Option<&Value>) -> Option<Vec<String>> {
    let arr = raw?.as_array()?;
    let mut ticks = Vec::with_capacity(arr.len());
    for item in arr {
        ticks.push(sanitize_display_bounded(item.as_str()?, MAX_LABEL_CHARS));
    }
    if ticks.iter().all(|t| t.is_empty()) {
        return None;
    }
    Some(ticks)
}

fn normalize_heatmap(raw: Option<&Value>) -> Section<Heatmap> {
    let value = match raw {
        None | Some(Value::Null) => return Section::Absent,
        Some(v) => v,
    };
    let rows = match value.as_array() {
        Some(a) => a,
        None => return Section::Malformed("heatmap was not an array"),
    };
    if rows.len() != HEATMAP_ROWS {
        return Section::Malformed("heatmap did not have 7 weekday rows");
    }

    let mut grid = Vec::with_capacity(HEATMAP_ROWS);
    for row in rows {
        let cells = match row.as_array() {
            Some(c) => c,
            None => return Section::Malformed("heatmap row was not an array"),
        };
        if cells.len() != HEATMAP_COLS {
            return Section::Malformed("heatmap row did not have 24 hour cells");
        }
        let mut out = Vec::with_capacity(HEATMAP_COLS);
        for cell in cells {
            match cell {
                /* No data for this hour: distinct from a genuine zero. */
                Value::Null => out.push(None),
                other => match num(other) {
                    Some(n) => out.push(Some(n)),
                    None => return Section::Malformed("heatmap cell was neither a number nor null"),
                },
            }
        }
        grid.push(out);
    }
    Section::Present(Heatmap { grid })
}

/*
Normalize the sessions array with per-entry rejection (D-03).

An entry is rejected when it is not an object, when a string-typed field holds
a non-string, when a numeric field holds a non-number, or when a routing value
exceeds its bound. Survivors keep daemon order -- ordering is
`claude_monitor.core.sess_rank`'s job at render time, not ours, and reordering
here would put this crate in the business of presentation.
*/
fn normalize_sessions(raw: Option<&Value>) -> Section<Sessions> {
    let value = match raw {
        None | Some(Value::Null) => return Section::Absent,
        Some(v) => v,
    };
    let arr = match value.as_array() {
        Some(a) => a,
        None => return Section::Malformed("sessions was not an array"),
    };

    let mut entries = Vec::with_capacity(arr.len());
    let mut rejected = 0usize;
    for item in arr {
        match normalize_session(item) {
            Some(s) => entries.push(s),
            None => rejected += 1,
        }
    }
    Section::Present(Sessions { entries, rejected })
}

fn normalize_session(raw: &Value) -> Option<Session> {
    let obj = raw.as_object()?;

    /* A string field that is absent becomes an empty string, matching
    build_session_snapshot's own `.get(k, "")`. A field that is present with
    the wrong type rejects the entry. */
    let text = |key: &str| -> Option<String> {
        match obj.get(key) {
            None | Some(Value::Null) => Some(String::new()),
            Some(Value::String(s)) => Some(s.clone()),
            Some(_) => None,
        }
    };

    let optional_number = |key: &str| -> Option<Option<f64>> {
        match obj.get(key) {
            None | Some(Value::Null) => Some(None),
            Some(v) => num(v).map(Some),
        }
    };

    let focus = FocusTarget {
        pane: text("pane")?,
        tmux: text("tmux")?,
        /* The daemon's focus verb takes the directory as its window title. */
        title: text("dir")?,
        term: text("term")?,
    };
    /* Bounded, not truncated: a clipped routing value would focus the wrong
    window (D-12). */
    if !focus.within_bounds() {
        return None;
    }

    Some(Session {
        /* Raw, not sanitized: id is identity-only (see the Session struct doc),
        and sanitizing it would let two distinct daemon ids collapse onto the same
        stable_key. */
        id: text("id")?,
        dir: sanitize_display(&text("dir")?),
        status: sanitize_display(&text("status")?),
        entered: optional_number("entered")?,
        frozen: optional_number("frozen")?,
        focus,
    })
}

/*
Validate a focus target before it goes back out on the wire.

Mirrors `claude_monitor.core.request_focus`'s own refusal to send an
unfocusable target. Returning `Focus` here rather than attempting the socket
call keeps the failure action-scoped and cheap (D-07).
*/
pub fn validate_focus(target: &FocusTarget) -> Result<(), ClientError> {
    if !target.within_bounds() {
        return Err(ClientError::focus("focus target field exceeded its length bound"));
    }
    if !target.focusable() {
        return Err(ClientError::focus("session has no focusable terminal target"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::error::ErrorCode;
    use serde_json::json;

    fn snap(v: Value) -> Snapshot {
        Snapshot::from_value(&v).expect("root object should normalize")
    }

    #[test]
    fn a_full_valid_snapshot_normalizes_every_section() {
        let s = snap(json!({
            "usage": {
                "used_percentage": 42.5, "resets_at_epoch": 1_700_000_000.0,
                "burn_rate_per_min": 120.0, "tokens_used": 1000, "token_limit": 5000,
                "seven_day_pct": 12.5, "seven_day_reset": 1_700_500_000.0
            },
            "trends": ["today 3k/hr | wk 2k/hr"],
            "heatmap": vec![vec![Value::Null; 24]; 7],
            "sessions": [{"id": "a", "dir": "~/repo", "status": "running",
                          "entered": 1.0, "frozen": Value::Null,
                          "pane": "%1", "tmux": "main", "term": "ghostty"}]
        }));
        assert!(s.usage.is_present() && s.trends.is_present());
        assert!(s.heatmap.is_present() && s.sessions.is_present());
        let usage = s.usage.present().unwrap();
        assert_eq!(usage.used_percentage, 42.5);
        assert_eq!(usage.tokens_used, Some(1000.0));
    }

    #[test]
    fn a_non_object_root_is_a_whole_fetch_rejection() {
        /* D-01: a bare null must not rebind live state to "nothing". */
        for bad in [json!(null), json!([]), json!(3), json!("x")] {
            let err = Snapshot::from_value(&bad).expect_err("must reject");
            assert_eq!(err.code, ErrorCode::Schema);
        }
    }

    #[test]
    fn null_sections_are_absent_not_malformed() {
        /* The daemon really does send these before its first poll. */
        let s = snap(json!({"usage": null, "trends": null, "heatmap": null, "sessions": null}));
        assert!(s.usage.is_absent() && s.trends.is_absent());
        assert!(s.heatmap.is_absent() && s.sessions.is_absent());
    }

    #[test]
    fn missing_sections_are_absent() {
        let s = snap(json!({}));
        assert!(s.usage.is_absent() && s.sessions.is_absent());
    }

    #[test]
    fn unknown_fields_are_ignored() {
        /* Forward compatibility: a newer daemon may add fields. */
        let s = snap(json!({
            "usage": {"used_percentage": 1.0, "resets_at_epoch": 2.0,
                      "burn_rate_per_min": 3.0, "brand_new_field": {"nested": true}},
            "some_future_section": [1, 2, 3]
        }));
        assert!(s.usage.is_present());
    }

    #[test]
    fn one_malformed_section_does_not_blank_its_siblings() {
        /* D-02: the whole reason sections are normalized independently. */
        let s = snap(json!({
            "usage": {"used_percentage": 9.0, "resets_at_epoch": 2.0, "burn_rate_per_min": 3.0},
            "heatmap": "not a grid",
            "sessions": [{"id": "a", "dir": "~/x", "status": "done"}]
        }));
        assert!(s.heatmap.is_malformed());
        assert!(s.usage.is_present(), "a bad heatmap blanked the quota gauges");
        assert!(s.sessions.is_present());
    }

    #[test]
    fn numeric_strings_are_never_coerced() {
        /* D-04: "42.5" is drift, not a percentage. */
        let s = snap(json!({"usage": {"used_percentage": "42.5",
                                      "resets_at_epoch": 2.0, "burn_rate_per_min": 3.0}}));
        assert!(s.usage.is_malformed());
    }

    #[test]
    fn booleans_are_not_numbers() {
        let s = snap(json!({"usage": {"used_percentage": true,
                                      "resets_at_epoch": 2.0, "burn_rate_per_min": 3.0}}));
        assert!(s.usage.is_malformed());
    }

    #[test]
    fn null_token_counts_are_absence_not_malformation() {
        /* The CLI's --api mode reports percentages only. */
        let s = snap(json!({"usage": {"used_percentage": 1.0, "resets_at_epoch": 2.0,
                                      "burn_rate_per_min": 3.0,
                                      "tokens_used": null, "token_limit": null}}));
        let usage = s.usage.present().expect("null token counts are legitimate");
        assert_eq!(usage.tokens_used, None);
    }

    #[test]
    fn a_mistyped_token_count_is_malformation_not_absence() {
        let s = snap(json!({"usage": {"used_percentage": 1.0, "resets_at_epoch": 2.0,
                                      "burn_rate_per_min": 3.0, "tokens_used": "1000"}}));
        assert!(s.usage.is_malformed());
    }

    #[test]
    fn a_junk_weekly_block_does_not_cost_the_five_hour_numbers() {
        let s = snap(json!({"usage": {"used_percentage": 55.0, "resets_at_epoch": 2.0,
                                      "burn_rate_per_min": 3.0,
                                      "seven_day_pct": "junk", "seven_day_reset": []}}));
        let usage = s.usage.present().expect("weekly junk must degrade only itself");
        assert_eq!(usage.used_percentage, 55.0);
        assert_eq!(usage.seven_day_pct, None);
    }

    #[test]
    fn one_bad_session_costs_only_that_session() {
        /* D-03: narrow rejection with a retained count. */
        let s = snap(json!({"sessions": [
            {"id": "ok1", "dir": "~/a", "status": "running", "pane": "%1"},
            {"id": 42,    "dir": "~/b", "status": "running", "pane": "%2"},
            "not an object",
            {"id": "ok2", "dir": "~/c", "status": "done",    "pane": "%3"}
        ]}));
        let sessions = s.sessions.present().unwrap();
        assert_eq!(sessions.rejected, 2);
        assert_eq!(sessions.entries.len(), 2);
        /* Daemon order preserved -- ordering is the renderer's job. */
        assert_eq!(sessions.entries[0].id, "ok1");
        assert_eq!(sessions.entries[1].id, "ok2");
    }

    #[test]
    fn a_rejected_session_is_never_replaced_by_a_placeholder() {
        let s = snap(json!({"sessions": [{"id": 1}, {"id": 2}]}));
        let sessions = s.sessions.present().unwrap();
        assert!(sessions.entries.is_empty(), "invented a renderable session from invalid data");
        assert_eq!(sessions.rejected, 2);
    }

    #[test]
    fn an_empty_sessions_array_is_present_and_empty_not_absent() {
        /* "No sessions running" and "the daemon told us nothing" are
        different screens. */
        let s = snap(json!({"sessions": []}));
        let sessions = s.sessions.present().expect("an empty list is data");
        assert!(sessions.entries.is_empty());
        assert_eq!(sessions.rejected, 0);
    }

    #[test]
    fn hostile_session_text_is_sanitized_at_the_boundary() {
        /* D-09: renderers receive display-safe values, not raw payload. */
        let s = snap(json!({"sessions": [
            {"id": "x", "dir": "~/\u{1b}[2Jevil", "status": "running", "pane": "%1"}
        ]}));
        let sessions = s.sessions.present().unwrap();
        assert_eq!(sessions.entries[0].dir, "~/?evil");
        assert!(!sessions.entries[0].dir.contains('\u{1b}'));
    }

    #[test]
    fn markup_in_a_directory_name_survives_normalization() {
        let s = snap(json!({"sessions": [
            {"id": "x", "dir": "[bold]repo[/]", "status": "done", "pane": "%1"}
        ]}));
        assert_eq!(s.sessions.present().unwrap().entries[0].dir, "[bold]repo[/]");
    }

    #[test]
    fn trend_rows_cross_the_same_trust_boundary() {
        let s = snap(json!({"trends": ["peak \u{1b}]52;c;x\u{7}hour"]}));
        let rows = s.trends.present().unwrap();
        assert!(!rows[0].contains('\u{1b}'));
    }

    #[test]
    fn the_trend_axis_is_optional_sanitized_and_bounded_per_tick() {
        let ticks = snap(json!({"trend_axis": ["60.0M/18%", "", "", "34.3M/10%", "", "", "", "0"]}))
            .trend_axis
            .unwrap();
        assert_eq!(ticks.len(), 8);
        assert_eq!(ticks[0], "60.0M/18%");
        assert_eq!(ticks[7], "0");
        /* Absent, null, an all-empty axis, and any non-array-of-strings -- including
        the bare string this field used to be -- all mean "no axis", never a malformed
        panel and never a half-drawn gutter. */
        assert!(snap(json!({})).trend_axis.is_none());
        assert!(snap(json!({"trend_axis": null})).trend_axis.is_none());
        assert!(snap(json!({"trend_axis": ["", "", ""]})).trend_axis.is_none());
        assert!(snap(json!({"trend_axis": "60.0M"})).trend_axis.is_none());
        assert!(snap(json!({"trend_axis": ["60.0M", 18]})).trend_axis.is_none());
        let hostile = snap(json!({"trend_axis": ["3\u{1b}]52;c;x\u{7}M"]})).trend_axis.unwrap();
        assert!(!hostile[0].contains('\u{1b}'));
        let long = snap(json!({"trend_axis": ["9".repeat(MAX_LABEL_CHARS + 50)]}))
            .trend_axis
            .unwrap();
        assert!(long[0].chars().count() <= MAX_LABEL_CHARS);
    }

    #[test]
    fn an_oversized_routing_value_rejects_its_entry_rather_than_being_truncated() {
        /* D-12: a clipped pane id focuses the wrong window. */
        let s = snap(json!({"sessions": [
            {"id": "x", "dir": "~/a", "status": "running", "pane": "%".repeat(MAX_ROUTE_CHARS + 1)}
        ]}));
        let sessions = s.sessions.present().unwrap();
        assert_eq!(sessions.rejected, 1);
        assert!(sessions.entries.is_empty());
    }

    #[test]
    fn focus_target_debug_never_prints_its_contents() {
        let target = FocusTarget {
            pane: "%SECRET".into(), tmux: "s".into(),
            title: "\u{1b}[2J".into(), term: "ghostty".into(),
        };
        let rendered = format!("{:?}", target);
        assert!(!rendered.contains("SECRET"), "Debug leaked a routing value: {}", rendered);
        assert!(!rendered.contains('\u{1b}'), "Debug leaked a control sequence");
        assert!(rendered.contains("pane_len"));
    }

    #[test]
    fn focusability_mirrors_the_python_rule() {
        let with_pane = FocusTarget { pane: "%1".into(), ..Default::default() };
        let zed = FocusTarget { term: "zed".into(), ..Default::default() };
        let neither = FocusTarget { term: "ghostty".into(), ..Default::default() };
        assert!(with_pane.focusable() && zed.focusable());
        assert!(!neither.focusable());
        assert_eq!(validate_focus(&neither).unwrap_err().code, ErrorCode::Focus);
        assert!(validate_focus(&with_pane).is_ok());
    }

    #[test]
    fn a_wrong_shaped_heatmap_is_malformed_not_reshaped() {
        for bad in [json!("grid"), json!([[]]), json!(vec![vec![Value::Null; 23]; 7])] {
            let s = snap(json!({ "heatmap": bad }));
            assert!(s.heatmap.is_malformed(), "reshaped a bad grid: {:?}", s.heatmap);
        }
    }

    #[test]
    fn a_null_heatmap_cell_is_no_data_not_zero() {
        let mut grid = vec![vec![Value::Null; 24]; 7];
        grid[0][0] = json!(0.0);
        let s = snap(json!({ "heatmap": grid }));
        let h = s.heatmap.present().unwrap();
        assert_eq!(h.grid[0][0], Some(0.0));
        assert_eq!(h.grid[0][1], None);
    }

    #[test]
    fn normalization_is_deterministic() {
        /* D-16: the same wire input must produce the same semantic state,
        every time, with no map-iteration-order dependence. */
        let wire = r#"{"usage":{"used_percentage":7.5,"resets_at_epoch":2,"burn_rate_per_min":3},
                       "sessions":[{"id":"a","dir":"~/x","status":"running","pane":"%1"},
                                   {"id":"b","dir":"~/y","status":"done","pane":"%2"}],
                       "trends":["r1","r2"]}"#;
        let first = Snapshot::from_json(wire).unwrap();
        for _ in 0..25 {
            assert_eq!(Snapshot::from_json(wire).unwrap(), first);
        }
    }

    #[test]
    fn malformed_json_is_a_decode_error() {
        let err = Snapshot::from_json("{\"usage\": ").expect_err("must reject");
        assert_eq!(err.code, ErrorCode::Decode);
    }

}
