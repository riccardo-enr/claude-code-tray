/*
Drive the shared fixture corpus (D-13, D-15, D-16).

Every file in `fixtures/snapshot/` is a raw wire input paired with the semantic
state a correct client must produce from it. The corpus is language-neutral on
purpose: Phase 14's parity harness runs the Python oracle against these same
files, so a disagreement between the two implementations surfaces as a failing
fixture rather than as a difference someone has to notice on screen.

Assertions are semantic. They compare normalized values, section availability,
rejected-entry counts, sanitized display text and stable error codes. They do
not lock debug wording, map iteration order or serialization details, so an
internal refactor in either language does not churn the corpus.

The harness fails loudly on a corpus it cannot read -- an unparseable fixture, an
unknown expectation key, or an empty directory is an error, never a silent skip.
A test suite that quietly runs zero cases is worse than no test suite, because it
reports success.
*/

use std::fs;
use std::path::{Path, PathBuf};

use serde_json::Value;

use claude_tui::{ErrorCode, Section, Snapshot};

fn corpus_dir() -> PathBuf {
    /* CARGO_MANIFEST_DIR is `<repo>/rust`; the corpus is shared, so it lives at
    the repo root where the Python oracle can reach it too. */
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("crate dir has a parent")
        .join("fixtures/snapshot")
}

struct Fixture {
    name: String,
    wire: Vec<u8>,
    expect: Value,
}

fn load_all() -> Vec<Fixture> {
    let dir = corpus_dir();
    let mut fixtures = Vec::new();

    let entries = fs::read_dir(&dir)
        .unwrap_or_else(|e| panic!("cannot read fixture corpus at {:?}: {}", dir, e));

    for entry in entries {
        let path = entry.expect("readable dir entry").path();
        if path.extension().and_then(|e| e.to_str()) != Some("json") {
            continue;
        }
        let text = fs::read_to_string(&path)
            .unwrap_or_else(|e| panic!("cannot read {:?}: {}", path, e));
        let doc: Value = serde_json::from_str(&text)
            .unwrap_or_else(|e| panic!("{:?} is not valid JSON: {}", path, e));

        let name = doc["name"].as_str().unwrap_or_else(|| panic!("{:?} has no name", path));
        /* The filename is the id. A fixture whose name disagrees with its file
        is a fixture someone will later fail to find. */
        let stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or_default();
        assert_eq!(name, stem, "fixture name and filename disagree in {:?}", path);

        let wire = match (doc.get("wire"), doc.get("wire_bytes")) {
            (Some(Value::String(s)), None) => s.as_bytes().to_vec(),
            (None, Some(Value::Array(bytes))) => bytes
                .iter()
                .map(|b| {
                    let n = b.as_u64().unwrap_or_else(|| panic!("{:?}: wire_bytes must be integers", path));
                    assert!(n <= 255, "{:?}: wire_bytes value {} is not a byte", path, n);
                    n as u8
                })
                .collect(),
            _ => panic!("{:?} must carry exactly one of `wire` or `wire_bytes`", path),
        };

        let expect = doc
            .get("expect")
            .cloned()
            .unwrap_or_else(|| panic!("{:?} has no `expect`", path));

        fixtures.push(Fixture { name: name.to_string(), wire, expect });
    }

    fixtures.sort_by(|a, b| a.name.cmp(&b.name));
    fixtures
}

#[test]
fn the_corpus_is_non_empty_and_well_formed() {
    /* Guards against the failure mode where a path change makes every other
    test in this file vacuously pass. */
    let fixtures = load_all();
    assert!(
        fixtures.len() >= 15,
        "expected the full D-15 matrix, found {} fixtures",
        fixtures.len()
    );
}

#[test]
fn every_fixture_produces_its_expected_semantic_state() {
    let fixtures = load_all();
    let mut failures = Vec::new();

    for fixture in &fixtures {
        if let Err(why) = check(fixture) {
            failures.push(format!("  {}: {}", fixture.name, why));
        }
    }

    assert!(
        failures.is_empty(),
        "{} of {} fixtures failed:\n{}",
        failures.len(),
        fixtures.len(),
        failures.join("\n")
    );
}

fn check(fixture: &Fixture) -> Result<(), String> {
    let result = Snapshot::from_slice(&fixture.wire);

    /* A fixture expecting a whole-fetch rejection names the stable code and
    carries no section expectations. */
    if let Some(expected) = fixture.expect.get("error").and_then(|v| v.as_str()) {
        let want = ErrorCode::parse_code(expected)
            .ok_or_else(|| format!("unknown error code {:?} in fixture", expected))?;
        return match result {
            Err(err) if err.code == want => Ok(()),
            Err(err) => Err(format!("expected error {}, got {}", want, err.code)),
            Ok(_) => Err(format!("expected error {}, but normalization succeeded", want)),
        };
    }

    let snapshot = result.map_err(|e| format!("expected a snapshot, got error {}", e))?;

    for (key, expected) in fixture.expect.as_object().ok_or("`expect` is not an object")? {
        match key.as_str() {
            "usage" => check_usage(&snapshot, expected)?,
            "trends" => check_trends(&snapshot.trends, expected, "trends")?,
            "cum_trend" => check_trends(&snapshot.cum_trend, expected, "cum_trend")?,
            "heatmap" => check_heatmap(&snapshot, expected)?,
            "sessions" => check_sessions(&snapshot, expected)?,
            other => return Err(format!("unknown expectation key {:?}", other)),
        }
    }
    Ok(())
}

/* A section expectation is either a state name ("absent" / "malformed") or an
object of values, which implies "present". */
fn check_state<T>(section: &Section<T>, expected: &Value, name: &str) -> Result<bool, String> {
    if let Some(want) = expected.as_str() {
        let got = section.state_name();
        return if got == want {
            Ok(false)
        } else {
            Err(format!("{}: expected {}, got {}", name, want, got))
        };
    }
    if !section.is_present() {
        return Err(format!("{}: expected present, got {}", name, section.state_name()));
    }
    Ok(true)
}

/* Float comparison with a tolerance: the corpus carries decimal literals and
both languages round-trip them through their own JSON readers. */
fn near(a: f64, b: f64) -> bool {
    (a - b).abs() < 1e-9
}

fn check_optional_number(
    got: Option<f64>,
    expected: &Value,
    field: &str,
) -> Result<(), String> {
    match (got, expected) {
        (None, Value::Null) => Ok(()),
        (Some(g), Value::Number(_)) => {
            let want = expected.as_f64().unwrap_or(f64::NAN);
            if near(g, want) {
                Ok(())
            } else {
                Err(format!("{}: expected {}, got {}", field, want, g))
            }
        }
        (g, e) => Err(format!("{}: expected {}, got {:?}", field, e, g)),
    }
}

fn check_optional_string(
    got: Option<&str>,
    expected: &Value,
    field: &str,
) -> Result<(), String> {
    match (got, expected) {
        (None, Value::Null) => Ok(()),
        (Some(g), Value::String(want)) if g == want => Ok(()),
        (g, e) => Err(format!("{}: expected {}, got {:?}", field, e, g)),
    }
}

fn check_usage(snapshot: &Snapshot, expected: &Value) -> Result<(), String> {
    if !check_state(&snapshot.usage, expected, "usage")? {
        return Ok(());
    }
    let usage = snapshot.usage.present().ok_or("usage: not present")?;

    for (field, want) in expected.as_object().ok_or("usage: expectation is not an object")? {
        match field.as_str() {
            "used_percentage" => check_optional_number(Some(usage.used_percentage), want, field)?,
            "resets_at_epoch" => check_optional_number(Some(usage.resets_at_epoch), want, field)?,
            "burn_rate_per_min" => {
                check_optional_number(Some(usage.burn_rate_per_min), want, field)?
            }
            "tokens_used" => check_optional_number(usage.tokens_used, want, field)?,
            "token_limit" => check_optional_number(usage.token_limit, want, field)?,
            "seven_day_pct" => check_optional_number(usage.seven_day_pct, want, field)?,
            "seven_day_reset" => check_optional_number(usage.seven_day_reset, want, field)?,
            "cost_usd" => check_optional_number(usage.cost_usd, want, field)?,
            "cost_per_hour" => check_optional_number(usage.cost_per_hour, want, field)?,
            "pace_used_pct" => check_optional_number(usage.pace_used_pct, want, field)?,
            "pace_elapsed_pct" => check_optional_number(usage.pace_elapsed_pct, want, field)?,
            "pace_label" => check_optional_string(usage.pace_label.as_deref(), want, field)?,
            "model_mix" => check_optional_string(usage.model_mix.as_deref(), want, field)?,
            other => return Err(format!("usage: unknown field {:?}", other)),
        }
    }
    Ok(())
}

fn check_trends(section: &Section<Vec<String>>, expected: &Value, name: &str) -> Result<(), String> {
    if !check_state(section, expected, name)? {
        return Ok(());
    }
    let rows = section.present().ok_or_else(|| format!("{}: not present", name))?;
    let want = expected
        .get("rows")
        .and_then(|v| v.as_array())
        .ok_or_else(|| format!("{}: expectation needs a `rows` array", name))?;

    if rows.len() != want.len() {
        return Err(format!("{}: expected {} rows, got {}", name, want.len(), rows.len()));
    }
    for (i, expected_row) in want.iter().enumerate() {
        let expected_row = expected_row.as_str().ok_or_else(|| format!("{}: rows must be strings", name))?;
        let got = rows.get(i).map(String::as_str).unwrap_or_default();
        if got != expected_row {
            return Err(format!("{}[{}]: expected {:?}, got {:?}", name, i, expected_row, got));
        }
    }
    Ok(())
}

fn check_heatmap(snapshot: &Snapshot, expected: &Value) -> Result<(), String> {
    if !check_state(&snapshot.heatmap, expected, "heatmap")? {
        return Ok(());
    }
    let heatmap = snapshot.heatmap.present().ok_or("heatmap: not present")?;

    for (field, want) in expected.as_object().ok_or("heatmap: expectation is not an object")? {
        match field.as_str() {
            "rows" => {
                let n = want.as_u64().unwrap_or(0) as usize;
                if heatmap.grid.len() != n {
                    return Err(format!("heatmap: expected {} rows, got {}", n, heatmap.grid.len()));
                }
            }
            "cols" => {
                let n = want.as_u64().unwrap_or(0) as usize;
                for (i, row) in heatmap.grid.iter().enumerate() {
                    if row.len() != n {
                        return Err(format!("heatmap row {}: expected {} cols, got {}", i, n, row.len()));
                    }
                }
            }
            /* `cell_<row>_<col>` pins one cell, so a fixture can assert that a
            null stayed distinct from a zero without spelling out 168 values. */
            other if other.starts_with("cell_") => {
                let mut parts = other.trim_start_matches("cell_").split('_');
                let r: usize = parts
                    .next()
                    .and_then(|s| s.parse().ok())
                    .ok_or_else(|| format!("heatmap: malformed cell key {:?}", other))?;
                let c: usize = parts
                    .next()
                    .and_then(|s| s.parse().ok())
                    .ok_or_else(|| format!("heatmap: malformed cell key {:?}", other))?;
                let got = heatmap.grid.get(r).and_then(|row| row.get(c)).copied().flatten();
                check_optional_number(got, want, other)?;
            }
            other => return Err(format!("heatmap: unknown field {:?}", other)),
        }
    }
    Ok(())
}

fn check_sessions(snapshot: &Snapshot, expected: &Value) -> Result<(), String> {
    if !check_state(&snapshot.sessions, expected, "sessions")? {
        return Ok(());
    }
    let sessions = snapshot.sessions.present().ok_or("sessions: not present")?;

    if let Some(want) = expected.get("rejected").and_then(|v| v.as_u64()) {
        if sessions.rejected as u64 != want {
            return Err(format!(
                "sessions: expected {} rejected, got {}",
                want, sessions.rejected
            ));
        }
    }

    let Some(want_entries) = expected.get("entries").and_then(|v| v.as_array()) else {
        return Ok(());
    };
    if sessions.entries.len() != want_entries.len() {
        return Err(format!(
            "sessions: expected {} entries, got {}",
            want_entries.len(),
            sessions.entries.len()
        ));
    }

    /* Order is asserted positionally: survivors must keep daemon order (D-03). */
    for (i, want) in want_entries.iter().enumerate() {
        let got = sessions.entries.get(i).ok_or("sessions: missing entry")?;
        for (field, expected_value) in
            want.as_object().ok_or("sessions: entry expectation is not an object")?
        {
            let mismatch = |actual: String| {
                format!("sessions[{}].{}: expected {}, got {:?}", i, field, expected_value, actual)
            };
            match field.as_str() {
                "id" => {
                    if Some(got.id.as_str()) != expected_value.as_str() {
                        return Err(mismatch(got.id.clone()));
                    }
                }
                "dir" => {
                    if Some(got.dir.as_str()) != expected_value.as_str() {
                        return Err(mismatch(got.dir.clone()));
                    }
                }
                "status" => {
                    if Some(got.status.as_str()) != expected_value.as_str() {
                        return Err(mismatch(got.status.clone()));
                    }
                }
                "entered" => check_optional_number(got.entered, expected_value, field)?,
                "frozen" => check_optional_number(got.frozen, expected_value, field)?,
                "focusable" => {
                    if Some(got.focus.focusable()) != expected_value.as_bool() {
                        return Err(mismatch(got.focus.focusable().to_string()));
                    }
                }
                other => return Err(format!("sessions: unknown entry field {:?}", other)),
            }
        }
    }
    Ok(())
}

#[test]
fn no_fixture_output_ever_contains_a_raw_escape_byte() {
    /*
    The corpus-wide safety property, asserted independently of any single
    fixture's expectations: whatever the input, no display string that comes out
    of normalization may carry an ESC or a C1 introducer. A future fixture that
    forgets to assert its sanitized text is still covered by this.
    */
    for fixture in load_all() {
        let Ok(snapshot) = Snapshot::from_slice(&fixture.wire) else {
            continue;
        };
        let mut display: Vec<&str> = Vec::new();
        if let Section::Present(rows) = &snapshot.trends {
            display.extend(rows.iter().map(String::as_str));
        }
        if let Section::Present(sessions) = &snapshot.sessions {
            for s in &sessions.entries {
                /* `id` is deliberately excluded: it is identity-only, never rendered
                (see the Session struct doc), and is kept raw so two daemon-distinct
                ids cannot collapse onto the same stable_key. */
                display.extend([s.dir.as_str(), s.status.as_str()]);
            }
        }
        for text in display {
            for bad in ['\u{1b}', '\u{9b}', '\u{9d}', '\u{7}'] {
                assert!(
                    !text.contains(bad),
                    "fixture {}: display string {:?} carries {:?}",
                    fixture.name,
                    text,
                    bad
                );
            }
        }
    }
}

#[test]
fn normalization_of_the_whole_corpus_is_deterministic() {
    /* D-16: same input, same semantic state, every run. */
    let fixtures = load_all();
    for fixture in &fixtures {
        let first = Snapshot::from_slice(&fixture.wire);
        for _ in 0..10 {
            let again = Snapshot::from_slice(&fixture.wire);
            match (&first, &again) {
                (Ok(a), Ok(b)) => assert_eq!(a, b, "fixture {} is not deterministic", fixture.name),
                (Err(a), Err(b)) => {
                    assert_eq!(a.code, b.code, "fixture {} error is not stable", fixture.name)
                }
                _ => panic!("fixture {} flipped between success and failure", fixture.name),
            }
        }
    }
}
