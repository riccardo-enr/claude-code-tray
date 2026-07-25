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

#[cfg(test)]
mod tests {
    use super::*;

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
    fn only_a_running_session_ticks_live() {
        assert_eq!(sess_elapsed("running", Some(100.0), None, 160.0), Some(60.0));
        /* Waiting and done show the frozen duration, not the live clock. */
        assert_eq!(sess_elapsed("done", Some(100.0), Some(42.0), 999.0), Some(42.0));
        assert_eq!(sess_elapsed("waiting", None, None, 999.0), None);
        /* Clock skew clamps to zero rather than going negative. */
        assert_eq!(sess_elapsed("running", Some(200.0), None, 100.0), Some(0.0));
    }
}
