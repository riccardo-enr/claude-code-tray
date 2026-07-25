/*
Value formatters, mirrored from `claude_monitor.core`.

D-05 of the v1.6 milestone made `claude_monitor.core` the single source of every
formatted value, so the tray and the Python TUI could not disagree. The Rust
client cannot import Python, so parity has to be re-established by mirroring --
and mirroring is only trustworthy if it is pinned. Every function here carries
the exact examples from its Python docstring as a test, so a drift in either
direction fails a build rather than showing a different number on screen than
the tray does.

The Python source of each function is named in its comment. Change both.

These are pure and total: no clock is read inside, every input maps to an
output, and none of them can panic. `now` is always a parameter, matching the
repo's synthetic-epoch test discipline.
*/

use crate::snapshot::Usage;

/* claude_monitor.core.fmt_tokens */
pub fn fmt_tokens(n: f64) -> String {
    if n >= 1e6 {
        format!("{:.1}M", n / 1e6)
    } else {
        format!("{}k", (n / 1000.0).round() as i64)
    }
}

/* claude_monitor.core.fmt_countdown */
pub fn fmt_countdown(secs: f64) -> String {
    let secs = secs.max(0.0) as i64;
    if secs <= 0 {
        return "resets now".to_string();
    }
    format!("resets in {}h {}m", secs / 3600, (secs % 3600) / 60)
}

/* claude_monitor.core.fmt_countdown_wk -- separate from fmt_countdown, whose
"Xh Ym" would render "98h 0m" for a week. */
pub fn fmt_countdown_wk(secs: f64) -> String {
    let secs = secs as i64;
    if secs <= 0 {
        return "week resets now".to_string();
    }
    if secs >= 86400 {
        return format!("week resets in {}d {}h", secs / 86400, (secs % 86400) / 3600);
    }
    format!("week resets in {}h {}m", secs / 3600, (secs % 3600) / 60)
}

/* claude_monitor.core.fmt_elapsed */
pub fn fmt_elapsed(secs: f64) -> String {
    let secs = secs.max(0.0) as i64;
    if secs >= 86400 {
        return format!("{}d {:02}h", secs / 86400, (secs % 86400) / 3600);
    }
    if secs >= 3600 {
        return format!("{}h {}m", secs / 3600, (secs % 3600) / 60);
    }
    format!("{}m {:02}s", secs / 60, secs % 60)
}

/*
Proximity-to-cap band (claude_monitor.core.band).

The cutoffs are literals, deliberately separate from the user's mutable badge
threshold: "band" means proximity to the cap, not "warn me here". Total -- an
over-limit percent (473.5) or a negative one still classifies.
*/
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Band {
    Green,
    Yellow,
    Red,
}

pub fn band(pct: f64) -> Band {
    if pct < 70.0 {
        Band::Green
    } else if pct < 90.0 {
        Band::Yellow
    } else {
        Band::Red
    }
}

/*
Filled-cell count for a gradient gauge (claude_monitor.core.gauge_fill).

Clamps to 0..100 first, so an over-limit percent cannot index past the bar.
*/
pub fn gauge_fill(pct: f64, width: usize) -> usize {
    let pct = pct.clamp(0.0, 100.0);
    (pct / 100.0 * width as f64).round() as usize
}

/*
Sort rank for a session status (claude_monitor.core.sess_rank).
An unrecognised status sorts last rather than raising.
*/
pub fn sess_rank(status: &str) -> u8 {
    match status {
        "waiting" => 0,
        "running" => 1,
        "done" => 2,
        _ => 99,
    }
}

/*
Seconds to display for one session (claude_monitor.core.sess_elapsed).

Only a running session ticks live off the caller's clock; waiting and done
show the snapshot's frozen duration, so the counter stops climbing once the
session stops working. `None` means the caller renders a dash.
*/
pub fn sess_elapsed(status: &str, entered: Option<f64>, frozen: Option<f64>, now: f64) -> Option<f64> {
    if status == "running" {
        if let Some(entered) = entered {
            return Some((now - entered).max(0.0));
        }
    }
    frozen
}

/* Quota-window lengths in seconds. claude_monitor.core carries the same
literals, as does the dashboard JS; move all three together. */
pub const WIN5: f64 = 18000.0; /* 5 hours */
pub const WIN7: f64 = 604800.0; /* 7 days */

/*
The eight sparkline glyphs, lowest to highest (claude_monitor.core.SPARK_GLYPHS).

These are the one place the ASCII-only house rule is deliberately broken. The
daemon already emits these exact codepoints in `trends[0]`, and the whole point
of `spark_levels` is to invert that mapping -- substituting ASCII here would
decode every column to None and draw an empty graph.
*/
pub const SPARK_GLYPHS: [char; 8] = ['\u{2581}', '\u{2582}', '\u{2583}', '\u{2584}',
                                     '\u{2585}', '\u{2586}', '\u{2587}', '\u{2588}'];

/*
Decode a sparkline back to per-column levels (claude_monitor.core.spark_levels).

The exact inverse of the mapping `trend_sparkline` produced: each glyph maps to
its index 0..7, which *is* the column height an eight-row graph draws from the
bottom. The gap character, and any other character, decodes to `None` -- a blank
column, never an index past the ramp. That total-ness is what lets a malformed
or hostile `trends[0]` reach this function without raising.
*/
pub fn spark_levels(sparkline: &str) -> Vec<Option<usize>> {
    sparkline
        .chars()
        .map(|ch| SPARK_GLYPHS.iter().position(|g| *g == ch))
        .collect()
}

/*
Quantize a 7x24 heatmap onto `levels` integer steps
(claude_monitor.core.heatmap_levels).

Mirrors the dashboard's relative intensity scale: the maximum starts at 1 and
rises to the largest populated cell, then each value is scaled against it. The
floor of 1 is what stops a day of near-zero usage from being renormalized into
a full-brightness grid.

`None` survives as a distinct no-data state -- an unsampled hour must not render
like a genuinely idle one. Non-finite values degrade to `None` rather than
poisoning the maximum. Returns `None` when there is no data at all, which is the
caller's signal to draw no heatmap.
*/
pub fn heatmap_levels(grid: &[Vec<Option<f64>>], levels: usize) -> Option<Vec<Vec<Option<usize>>>> {
    if levels < 1 {
        return None;
    }
    let mut fixed: Vec<Vec<Option<f64>>> = Vec::with_capacity(7);
    let mut values: Vec<f64> = Vec::new();

    for day in 0..7 {
        let source = grid.get(day);
        let mut row = Vec::with_capacity(24);
        for hour in 0..24 {
            let value = source
                .and_then(|r| r.get(hour))
                .copied()
                .flatten()
                .filter(|v| v.is_finite());
            if let Some(v) = value {
                values.push(v);
            }
            row.push(value);
        }
        fixed.push(row);
    }
    if values.is_empty() {
        return None;
    }

    let maximum = values.iter().fold(1.0f64, |acc, v| acc.max(*v));
    let top = (levels - 1) as f64;
    Some(
        fixed
            .iter()
            .map(|row| {
                row.iter()
                    .map(|cell| {
                        cell.map(|v| (v.clamp(0.0, maximum) / maximum * top).round() as usize)
                    })
                    .collect()
            })
            .collect(),
    )
}

/*
Linear extrapolation of a usage percent to its value at the window reset
(claude_monitor.core.project).

Three outcomes, and keeping them distinct is the point: there is no data,
it is too early to say anything honest, or here is a projection. Below 5%
elapsed, `pct / e` explodes -- a single early sample would project 900% and
raise an alarm about nothing. That branch is also the clock-skew guard, since a
negative elapsed fraction lands in it.

`exhaust` is set only when the projection strictly exceeds 100 *and* the
crossing lands inside the window, so "you will run out" is never claimed for a
crossing that happens after the quota has already reset.
*/
#[derive(Debug, Clone, PartialEq)]
pub enum Projection {
    /* No usable input. */
    Unknown,
    /* Too early in the window for an honest extrapolation. */
    Early,
    Projected { pct: f64, exhaust: Option<f64> },
}

pub fn project(pct: Option<f64>, reset: Option<f64>, win: f64, now: f64) -> Projection {
    let (Some(pct), Some(reset)) = (pct, reset) else {
        return Projection::Unknown;
    };
    if !pct.is_finite() || !reset.is_finite() {
        return Projection::Unknown;
    }
    let start = reset - win;
    let mut elapsed = (now - start) / win;
    if elapsed <= 0.05 {
        return Projection::Early;
    }
    if elapsed > 1.0 {
        elapsed = 1.0; /* window already over -> degrade to the current pct */
    }
    let projected = pct / elapsed;
    let mut exhaust = None;
    if projected > 100.0 && pct > 0.0 {
        let crossing = start + (100.0 / pct) * (now - start);
        if crossing < reset {
            exhaust = Some(crossing);
        }
    }
    Projection::Projected { pct: projected, exhaust }
}

/*
The usage rows, as strings (claude_monitor.core.tui_usage_rows).

Reproduced verbatim rather than reassembled from parts, because the renderer
band-colours these rows by splitting them back on the double-space separator --
exactly as `claude-tui.py::_cap_row_text` does. Building the string here and
splitting it there keeps one definition of what a row *is*, so the two surfaces
cannot drift into different spacing.

Every number goes through a formatter above; introducing a new one here is
precisely the tray/TUI divergence that D-05 exists to prevent.
*/
pub fn tui_usage_rows(usage: Option<&Usage>, now: f64) -> Vec<String> {
    /* Change both: claude-monitor.py carries the same string. */
    let Some(usage) = usage else {
        return vec!["usage unavailable".to_string()];
    };
    let (pct, reset, burn) = (
        usage.used_percentage,
        usage.resets_at_epoch,
        usage.burn_rate_per_min,
    );
    let (tokens_used, token_limit) = (usage.tokens_used, usage.token_limit);
    let (seven_day_pct, seven_day_reset) = (usage.seven_day_pct, usage.seven_day_reset);

    let mut row = vec![format!("5h"), format!("{}%", pct.round() as i64)];
    /* --api carries no token counts -> percent only; the P90 path has them. */
    if let (Some(used), Some(limit)) = (tokens_used, token_limit) {
        row.push(format!("{} / {}", fmt_tokens(used), fmt_tokens(limit)));
    }
    row.push(fmt_countdown(reset - now));
    row.push(format!("burn: {} tok/hr", fmt_tokens((burn * 60.0).round())));
    let mut rows = vec![row.join("  ")];

    /* An older CLI omits the whole weekly block -> one row only. */
    if let Some(pct7) = seven_day_pct {
        let mut wrow = vec![format!("7d"), format!("{}%", pct7.round() as i64)];
        if let Some(reset7) = seven_day_reset {
            wrow.push(fmt_countdown_wk(reset7 - now));
        }
        rows.push(wrow.join("  "));
    }
    rows
}

#[cfg(test)]
mod tests {
    use super::*;

    /* Terse constructor so a row test reads as its inputs, not as struct syntax. */
    #[allow(clippy::too_many_arguments)]
    fn usage_of(
        used_percentage: f64, resets_at_epoch: f64, burn_rate_per_min: f64,
        tokens_used: Option<f64>, token_limit: Option<f64>,
        seven_day_pct: Option<f64>, seven_day_reset: Option<f64>,
    ) -> Usage {
        Usage {
            used_percentage, resets_at_epoch, burn_rate_per_min,
            tokens_used, token_limit, seven_day_pct, seven_day_reset,
        }
    }

    #[test]
    fn fmt_tokens_matches_the_python_docstring_examples() {
        assert_eq!(fmt_tokens(417_000.0), "417k");
        assert_eq!(fmt_tokens(18_936_912.0), "18.9M");
    }

    #[test]
    fn fmt_countdown_matches_the_python_docstring_examples() {
        assert_eq!(fmt_countdown(7380.0), "resets in 2h 3m");
        assert_eq!(fmt_countdown(0.0), "resets now");
        assert_eq!(fmt_countdown(-500.0), "resets now");
    }

    #[test]
    fn fmt_countdown_wk_matches_the_python_docstring_examples() {
        assert_eq!(fmt_countdown_wk(352_800.0), "week resets in 4d 2h");
        assert_eq!(fmt_countdown_wk(7380.0), "week resets in 2h 3m");
        assert_eq!(fmt_countdown_wk(0.0), "week resets now");
    }

    #[test]
    fn fmt_elapsed_matches_the_python_docstring_examples() {
        assert_eq!(fmt_elapsed(134.0), "2m 14s");
        assert_eq!(fmt_elapsed(4920.0), "1h 22m");
        assert_eq!(fmt_elapsed(266_400.0), "3d 02h");
        /* Clock skew clamps rather than rendering a negative counter. */
        assert_eq!(fmt_elapsed(-5.0), "0m 00s");
    }

    #[test]
    fn band_cutoffs_match_the_python_literals() {
        assert_eq!(band(69.9), Band::Green);
        assert_eq!(band(70.0), Band::Yellow);
        assert_eq!(band(89.9), Band::Yellow);
        assert_eq!(band(90.0), Band::Red);
        /* Total: over-limit and negative still classify. */
        assert_eq!(band(473.5), Band::Red);
        assert_eq!(band(-1.0), Band::Green);
    }

    #[test]
    fn gauge_fill_is_clamped_monotonic_and_never_past_the_width() {
        assert_eq!(gauge_fill(0.0, 20), 0);
        assert_eq!(gauge_fill(100.0, 20), 20);
        assert_eq!(gauge_fill(50.0, 20), 10);
        /* An over-limit percent must not index past the bar. */
        assert_eq!(gauge_fill(473.5, 20), 20);
        assert_eq!(gauge_fill(-10.0, 20), 0);
        let mut prev = 0;
        for p in 0..=100 {
            let fill = gauge_fill(p as f64, 32);
            assert!(fill >= prev && fill <= 32);
            prev = fill;
        }
    }

    #[test]
    fn sess_rank_sorts_unknown_statuses_last() {
        assert_eq!(sess_rank("waiting"), 0);
        assert_eq!(sess_rank("running"), 1);
        assert_eq!(sess_rank("done"), 2);
        assert_eq!(sess_rank("something-new"), 99);
    }

    #[test]
    fn spark_levels_inverts_the_glyph_ramp_exactly() {
        let line: String = SPARK_GLYPHS.iter().collect();
        assert_eq!(
            spark_levels(&line),
            (0..8).map(Some).collect::<Vec<_>>()
        );
    }

    #[test]
    fn spark_levels_decodes_gaps_and_junk_to_blank_columns() {
        /* A hostile trends[0] must produce blank columns, never an index past
        the ramp. This is the T-10-03 case. */
        let decoded = spark_levels("\u{2588} x\u{2581}");
        assert_eq!(decoded, vec![Some(7), None, None, Some(0)]);
        assert!(spark_levels("").is_empty());
    }

    #[test]
    fn heatmap_levels_normalizes_against_the_populated_maximum() {
        let mut grid = vec![vec![None; 24]; 7];
        grid[0][0] = Some(0.0);
        grid[0][1] = Some(5.0);
        grid[0][2] = Some(10.0);
        let levels = heatmap_levels(&grid, 4).expect("populated grid");
        assert_eq!(levels[0][0], Some(0));
        assert_eq!(levels[0][1], Some(2)); /* 5/10 * 3 = 1.5 -> 2 */
        assert_eq!(levels[0][2], Some(3));
        /* No-data stays distinct from a genuine zero. */
        assert_eq!(levels[0][3], None);
    }

    #[test]
    fn heatmap_levels_floors_the_maximum_at_one() {
        /* Without the floor, a day of 0.1% usage would renormalize to full
        brightness and read as a hammered week. */
        let mut grid = vec![vec![None; 24]; 7];
        grid[3][12] = Some(0.5);
        let levels = heatmap_levels(&grid, 4).expect("populated grid");
        assert_eq!(levels[3][12], Some(2)); /* 0.5/1.0 * 3 = 1.5 -> 2 */
    }

    #[test]
    fn heatmap_levels_returns_none_for_an_empty_or_nonfinite_grid() {
        assert!(heatmap_levels(&vec![vec![None; 24]; 7], 4).is_none());
        let mut grid = vec![vec![None; 24]; 7];
        grid[0][0] = Some(f64::NAN);
        grid[0][1] = Some(f64::INFINITY);
        assert!(heatmap_levels(&grid, 4).is_none(), "non-finite values must not count as data");
    }

    #[test]
    fn heatmap_levels_tolerates_a_short_grid_without_panicking() {
        /* A malformed same-user payload degrades to no-data cells, never an
        out-of-bounds index. */
        let grid = vec![vec![Some(1.0), None]];
        let levels = heatmap_levels(&grid, 4).expect("one populated cell");
        assert_eq!(levels.len(), 7);
        assert_eq!(levels[0].len(), 24);
        assert_eq!(levels[6][23], None);
    }

    #[test]
    fn project_refuses_to_extrapolate_too_early() {
        /* pct/e explodes below 5% elapsed; a single early sample must not
        project 900%. */
        let reset = 18000.0;
        assert_eq!(project(Some(1.0), Some(reset), WIN5, 100.0), Projection::Early);
        /* Clock skew (negative elapsed) lands in the same branch. */
        assert_eq!(project(Some(1.0), Some(reset), WIN5, -500.0), Projection::Early);
    }

    #[test]
    fn project_extrapolates_linearly_over_the_window() {
        /* Half the window elapsed at 30% -> 60% projected. */
        let reset = WIN5;
        let now = WIN5 / 2.0;
        match project(Some(30.0), Some(reset), WIN5, now) {
            Projection::Projected { pct, exhaust } => {
                assert!((pct - 60.0).abs() < 1e-9, "got {}", pct);
                assert_eq!(exhaust, None);
            }
            other => panic!("expected a projection, got {:?}", other),
        }
    }

    #[test]
    fn project_reports_exhaustion_only_when_the_crossing_is_inside_the_window() {
        let reset = WIN5;
        /* 80% used at the 10% mark projects far past 100 and crosses early. */
        match project(Some(80.0), Some(reset), WIN5, WIN5 * 0.1) {
            Projection::Projected { pct, exhaust } => {
                assert!(pct > 100.0);
                let crossing = exhaust.expect("crossing lands inside the window");
                assert!(crossing < reset);
            }
            other => panic!("expected a projection, got {:?}", other),
        }
        /* A projection at exactly 100 is not exhaustion. */
        match project(Some(50.0), Some(reset), WIN5, WIN5 / 2.0) {
            Projection::Projected { exhaust, .. } => assert_eq!(exhaust, None),
            other => panic!("expected a projection, got {:?}", other),
        }
    }

    #[test]
    fn project_degrades_past_the_window_end_instead_of_shrinking() {
        /* Elapsed clamps at 1.0, so a stale reset epoch reports the current
        pct rather than a projection that falls below it. */
        match project(Some(42.0), Some(WIN5), WIN5, WIN5 * 3.0) {
            Projection::Projected { pct, .. } => assert!((pct - 42.0).abs() < 1e-9),
            other => panic!("expected a projection, got {:?}", other),
        }
    }

    #[test]
    fn project_is_unknown_without_usable_input() {
        /* Stricter than the dashboard JS, which coerces: an absent 7d cap on an
        older CLI degrades to silence rather than raising. */
        assert_eq!(project(None, Some(1.0), WIN5, 0.0), Projection::Unknown);
        assert_eq!(project(Some(1.0), None, WIN5, 0.0), Projection::Unknown);
        assert_eq!(project(Some(f64::NAN), Some(1.0), WIN5, 0.0), Projection::Unknown);
    }

    #[test]
    fn tui_usage_rows_matches_the_python_row_shape() {
        let rows = tui_usage_rows(Some(&usage_of(42.4, 7380.0, 1200.0,
            Some(417_000.0), Some(880_000.0), Some(15.0), Some(352_800.0))), 0.0);
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0], "5h  42%  417k / 880k  resets in 2h 3m  burn: 72k tok/hr");
        assert_eq!(rows[1], "7d  15%  week resets in 4d 2h");
    }

    #[test]
    fn tui_usage_rows_omits_token_counts_under_api_mode() {
        let rows = tui_usage_rows(Some(&usage_of(7.0, 3600.0, 0.0, None, None, None, None)), 0.0);
        assert_eq!(rows, vec!["5h  7%  resets in 1h 0m  burn: 0k tok/hr"]);
    }

    #[test]
    fn tui_usage_rows_reports_unavailable_when_the_required_trio_is_incomplete() {
        /* Change both: claude-monitor.py carries the same string. */
        let rows = tui_usage_rows(None, 0.0);
        assert_eq!(rows, vec!["usage unavailable"]);
    }

    #[test]
    fn usage_rows_split_back_into_band_colourable_cells() {
        /* The renderer colours by splitting on the double space, so the
        separator is load-bearing and pinned here. */
        let rows = tui_usage_rows(Some(&usage_of(50.0, 7380.0, 60.0, None, None, None, None)), 0.0);
        let cells: Vec<&str> = rows[0].split("  ").collect();
        assert_eq!(cells[0], "5h");
        assert_eq!(cells[1], "50%");
        assert!(cells[2].starts_with("resets"));
        assert!(cells[3].starts_with("burn:"));
    }

    #[test]
    fn only_a_running_session_ticks_live() {
        assert_eq!(sess_elapsed("running", Some(100.0), None, 160.0), Some(60.0));
        /* Waiting and done show the frozen duration, not the live clock. */
        assert_eq!(sess_elapsed("done", Some(100.0), Some(42.0), 999.0), Some(42.0));
        assert_eq!(sess_elapsed("waiting", None, None, 999.0), None);
        /* Clock skew clamps to zero rather than going negative. */
        assert_eq!(sess_elapsed("running", Some(200.0), None, 100.0), Some(0.0));
    }
}
