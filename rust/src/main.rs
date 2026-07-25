/*
`claude-tui` -- the Rust terminal dashboard.

Scope note: Phase 11 delivers the *client* -- socket, normalization,
sanitization, typed failures. This binary exists so that foundation can be run
and compared against the Python oracle before committing to the rewrite. It
renders the same three panels in the same order (usage, trends, sessions) using
the mirrored `format` helpers, so the numbers on screen are the tray's numbers.

Full visual parity is Phase 12 and interaction parity is Phase 13. What is
deliberately not here yet: the hour-of-day heatmap, keyboard session
navigation, and click-to-focus.

`claude-tui.py` remains the oracle and is never invoked from this process --
this binary talks to the daemon socket directly, exactly as the Python TUI does.

Refresh follows the Python cadence: a snapshot fetch every 2s, a local re-render
every 1s so a running session's counter ticks between fetches. On an outage the
last good frame is preserved and dimmed rather than blanked; a cold start with
no good frame yet shows the established unavailable message.
*/

use std::io::{self, Stdout};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use crossterm::event::{self, Event, KeyCode, KeyEventKind};
use crossterm::execute;
use crossterm::terminal::{
    disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen,
};
use ratatui::backend::CrosstermBackend;
use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, BorderType, Borders, Cell, Paragraph, Row, Table};
use ratatui::{Frame, Terminal};

use claude_tui::format::{
    band, fmt_countdown, fmt_countdown_wk, fmt_elapsed, fmt_tokens, gauge_fill, sess_elapsed,
    sess_rank, Band,
};
use claude_tui::{Client, ClientError, Section, Snapshot};

/* Matches claude_monitor.core.TUI_FETCH_INTERVAL / TUI_TICK_INTERVAL. */
const FETCH_INTERVAL: Duration = Duration::from_secs(2);
const TICK_INTERVAL: Duration = Duration::from_secs(1);

/* Change both: claude-monitor.py carries the same string. */
const USAGE_UNAVAILABLE: &str = "usage unavailable";
const TRENDS_COLLECTING: &str = "trends: collecting history...";
const NO_SESSIONS: &str = "No active Claude Code sessions";

/*
The last good frame, plus whatever went wrong since.

This is the D-06 split made concrete: a failed fetch never overwrites `snapshot`.
Cold start (`snapshot` still None) and a later outage (`snapshot` present,
`error` set) are different screens, and keeping them in separate fields is what
makes them impossible to confuse.
*/
struct App {
    client: Client,
    snapshot: Option<Snapshot>,
    error: Option<ClientError>,
    fetched_at: Option<Instant>,
}

impl App {
    fn new() -> Self {
        App { client: Client::new(), snapshot: None, error: None, fetched_at: None }
    }

    fn refresh(&mut self) {
        match self.client.snapshot() {
            Ok(snapshot) => {
                self.snapshot = Some(snapshot);
                self.error = None;
                self.fetched_at = Some(Instant::now());
            }
            /* The last good snapshot survives untouched. */
            Err(err) => self.error = Some(err),
        }
    }

    fn degraded(&self) -> bool {
        self.error.is_some() && self.snapshot.is_some()
    }
}

fn main() -> io::Result<()> {
    /* `--once` fetches one snapshot, prints a plain-text dump and exits. No
    terminal, no raw mode -- so the client can be smoke-tested from a pipe, a
    CI job, or a `just` recipe. Phase 14's parity harness wants this seam too. */
    if std::env::args().skip(1).any(|a| a == "--once") {
        return dump_once();
    }
    let mut terminal = enter_terminal()?;
    let result = run(&mut terminal);
    leave_terminal(&mut terminal)?;
    /* Report after the terminal is restored, so an error is readable. */
    if let Err(err) = &result {
        eprintln!("claude-tui: {}", err);
    }
    result
}

/*
One fetch, printed as plain text, no terminal involved.

Reports each section's state by name so a malformed section is visible as
malformed rather than silently rendering as empty -- the whole point of D-02
is lost if the diagnostic path flattens it back to "nothing there".
*/
fn dump_once() -> io::Result<()> {
    let client = Client::new();
    let snapshot = match client.snapshot() {
        Ok(s) => s,
        Err(err) => {
            println!("fetch failed: {}", err);
            return Ok(());
        }
    };
    let now = now_epoch();

    println!("usage:    {}", snapshot.usage.state_name());
    if let Section::Present(u) = &snapshot.usage {
        println!(
            "  5h  {:.0}%  {}  burn: {} tok/hr",
            u.used_percentage,
            fmt_countdown(u.resets_at_epoch - now),
            fmt_tokens((u.burn_rate_per_min * 60.0).round())
        );
        if let (Some(used), Some(limit)) = (u.tokens_used, u.token_limit) {
            println!("      tokens {} / {}", fmt_tokens(used), fmt_tokens(limit));
        }
        if let Some(pct7) = u.seven_day_pct {
            let when = u.seven_day_reset.map(|r| fmt_countdown_wk(r - now));
            println!("  7d  {:.0}%  {}", pct7, when.unwrap_or_default());
        }
    }

    println!("trends:   {}", snapshot.trends.state_name());
    if let Section::Present(rows) = &snapshot.trends {
        for row in rows {
            println!("  {}", row);
        }
    }

    println!("heatmap:  {}", snapshot.heatmap.state_name());

    println!("sessions: {}", snapshot.sessions.state_name());
    if let Section::Present(s) = &snapshot.sessions {
        for entry in &s.entries {
            let elapsed = sess_elapsed(&entry.status, entry.entered, entry.frozen, now)
                .map(fmt_elapsed)
                .unwrap_or_else(|| "-".to_string());
            println!(
                "  {:<8} {:<40} {:>9}  focusable={}",
                entry.status,
                entry.dir,
                elapsed,
                entry.focus.focusable()
            );
        }
        if s.rejected > 0 {
            println!("  ({} entries rejected as malformed)", s.rejected);
        }
        if s.entries.is_empty() {
            println!("  {}", NO_SESSIONS);
        }
    }
    Ok(())
}

fn run(terminal: &mut Terminal<CrosstermBackend<Stdout>>) -> io::Result<()> {
    let mut app = App::new();
    app.refresh();
    let mut last_fetch = Instant::now();

    loop {
        terminal.draw(|frame| draw(frame, &app))?;

        /* Poll for at most one tick, so the countdown re-renders every second
        without busy-waiting between snapshots. */
        if event::poll(TICK_INTERVAL)? {
            if let Event::Key(key) = event::read()? {
                if key.kind == KeyEventKind::Press && matches!(key.code, KeyCode::Char('q')) {
                    return Ok(());
                }
            }
        }
        if last_fetch.elapsed() >= FETCH_INTERVAL {
            app.refresh();
            last_fetch = Instant::now();
        }
    }
}

fn enter_terminal() -> io::Result<Terminal<CrosstermBackend<Stdout>>> {
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    Terminal::new(CrosstermBackend::new(stdout))
}

fn leave_terminal(terminal: &mut Terminal<CrosstermBackend<Stdout>>) -> io::Result<()> {
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()
}

fn now_epoch() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

/* Panel order is fixed and matches claude-tui.py: usage, trends, sessions. */
fn draw(frame: &mut Frame, app: &App) {
    let areas = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1), /* header */
            Constraint::Length(6), /* usage */
            Constraint::Length(5), /* trends */
            Constraint::Min(3),    /* sessions */
            Constraint::Length(1), /* footer */
        ])
        .split(frame.area());

    let now = now_epoch();
    draw_header(frame, areas[0], app);
    draw_usage(frame, areas[1], app, now);
    draw_trends(frame, areas[2], app);
    draw_sessions(frame, areas[3], app, now);
    draw_footer(frame, areas[4], app);
}

fn panel(title: &str, dim: bool) -> Block<'_> {
    let border = if dim { Color::DarkGray } else { Color::Gray };
    Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border))
        .title(Span::styled(
            format!(" {} ", title),
            Style::default().add_modifier(Modifier::BOLD),
        ))
}

fn band_color(b: Band) -> Color {
    match b {
        Band::Green => Color::Green,
        Band::Yellow => Color::Yellow,
        Band::Red => Color::Red,
    }
}

/* Dim everything when the last frame is stale, so a preserved frame is never
mistaken for a live one. */
fn frame_style(app: &App) -> Style {
    if app.degraded() {
        Style::default().add_modifier(Modifier::DIM)
    } else {
        Style::default()
    }
}

fn draw_header(frame: &mut Frame, area: Rect, app: &App) {
    let state = if app.snapshot.is_none() {
        Span::styled("connecting", Style::default().fg(Color::DarkGray))
    } else if app.degraded() {
        Span::styled("stale", Style::default().fg(Color::Yellow))
    } else {
        Span::styled("live", Style::default().fg(Color::Green))
    };
    let line = Line::from(vec![
        Span::styled(" claude-tui ", Style::default().add_modifier(Modifier::BOLD)),
        Span::raw("["),
        state,
        Span::raw("]"),
    ]);
    frame.render_widget(Paragraph::new(line), area);
}

fn draw_footer(frame: &mut Frame, area: Rect, app: &App) {
    /* Error context is already payload-free by construction (D-08), so it is
    safe to put on screen verbatim. */
    let text = match (&app.error, &app.snapshot) {
        (Some(err), Some(_)) => format!(" q quit   |   retrying: {}", err.code),
        (Some(err), None) => format!(" q quit   |   {}", err),
        _ => " q quit".to_string(),
    };
    frame.render_widget(
        Paragraph::new(text).style(Style::default().fg(Color::DarkGray)),
        area,
    );
}

fn draw_usage(frame: &mut Frame, area: Rect, app: &App, now: f64) {
    let block = panel("usage", app.degraded());
    let inner = block.inner(area);
    frame.render_widget(block, area);

    let usage = match app.snapshot.as_ref().map(|s| &s.usage) {
        Some(Section::Present(u)) => u,
        _ => {
            frame.render_widget(
                Paragraph::new(USAGE_UNAVAILABLE).style(Style::default().fg(Color::DarkGray)),
                inner,
            );
            return;
        }
    };

    let width = (inner.width as usize).saturating_sub(28).clamp(8, 40);
    let mut lines = Vec::new();

    /* 5h cap. */
    let mut head = vec![
        Span::raw("5h  "),
        gauge_span(usage.used_percentage, width),
        Span::styled(
            format!(" {:>3}%  ", usage.used_percentage.round() as i64),
            Style::default().fg(band_color(band(usage.used_percentage))),
        ),
    ];
    /* --api reports percentages only; the P90 path carries token counts. */
    if let (Some(used), Some(limit)) = (usage.tokens_used, usage.token_limit) {
        head.push(Span::raw(format!("{} / {}  ", fmt_tokens(used), fmt_tokens(limit))));
    }
    lines.push(Line::from(head));
    lines.push(Line::from(format!(
        "    {}   burn: {} tok/hr",
        fmt_countdown(usage.resets_at_epoch - now),
        fmt_tokens((usage.burn_rate_per_min * 60.0).round())
    )));

    /* 7d cap. An older CLI omits the block entirely -> one row only. */
    if let Some(pct7) = usage.seven_day_pct {
        lines.push(Line::from(""));
        lines.push(Line::from(vec![
            Span::raw("7d  "),
            gauge_span(pct7, width),
            Span::styled(
                format!(" {:>3}%  ", pct7.round() as i64),
                Style::default().fg(band_color(band(pct7))),
            ),
        ]));
        if let Some(reset7) = usage.seven_day_reset {
            lines.push(Line::from(format!("    {}", fmt_countdown_wk(reset7 - now))));
        }
    }

    frame.render_widget(Paragraph::new(lines).style(frame_style(app)), inner);
}

/* A gradient gauge: filled cells take the band colour of the percentage they
represent, so the bar shades green to red as it fills. */
fn gauge_span(pct: f64, width: usize) -> Span<'static> {
    let filled = gauge_fill(pct, width);
    let mut bar = String::with_capacity(width + 2);
    bar.push('[');
    for _ in 0..filled {
        bar.push('|');
    }
    for _ in filled..width {
        bar.push(' ');
    }
    bar.push(']');
    Span::styled(bar, Style::default().fg(band_color(band(pct))))
}

fn draw_trends(frame: &mut Frame, area: Rect, app: &App) {
    let block = panel("trends", app.degraded());
    let inner = block.inner(area);
    frame.render_widget(block, area);

    let text = match app.snapshot.as_ref().map(|s| &s.trends) {
        Some(Section::Present(rows)) if !rows.is_empty() => rows.join("\n"),
        _ => TRENDS_COLLECTING.to_string(),
    };
    frame.render_widget(Paragraph::new(text).style(frame_style(app)), inner);
}

fn draw_sessions(frame: &mut Frame, area: Rect, app: &App, now: f64) {
    let block = panel("sessions", app.degraded());
    let inner = block.inner(area);
    frame.render_widget(block, area);

    let sessions = match app.snapshot.as_ref().map(|s| &s.sessions) {
        Some(Section::Present(s)) => s,
        _ => {
            frame.render_widget(
                Paragraph::new(NO_SESSIONS).style(Style::default().fg(Color::DarkGray)),
                inner,
            );
            return;
        }
    };
    if sessions.entries.is_empty() {
        frame.render_widget(
            Paragraph::new(NO_SESSIONS).style(Style::default().fg(Color::DarkGray)),
            inner,
        );
        return;
    }

    /* Ordering is the renderer's job; normalization preserved daemon order. */
    let mut ordered: Vec<_> = sessions.entries.iter().collect();
    ordered.sort_by_key(|s| sess_rank(&s.status));

    let rows: Vec<Row> = ordered
        .iter()
        .enumerate()
        .map(|(i, s)| {
            let colour = match s.status.as_str() {
                "waiting" => Color::Yellow,
                "running" => Color::Green,
                "done" => Color::DarkGray,
                _ => Color::Reset,
            };
            let elapsed = sess_elapsed(&s.status, s.entered, s.frozen, now)
                .map(fmt_elapsed)
                .unwrap_or_else(|| "-".to_string());
            /* Striping. */
            let base = if i % 2 == 1 {
                Style::default().bg(Color::Rgb(24, 24, 24))
            } else {
                Style::default()
            };
            Row::new(vec![
                Cell::from(s.status.clone()).style(Style::default().fg(colour)),
                /* Already sanitized at the normalization boundary (D-09). */
                Cell::from(s.dir.clone()),
                Cell::from(elapsed),
            ])
            .style(base)
        })
        .collect();

    let mut table = Table::new(
        rows,
        [Constraint::Length(9), Constraint::Min(20), Constraint::Length(10)],
    )
    .style(frame_style(app));

    /* Retained reject count: "3 sessions" and "3 sessions, 1 unreadable" are
    different states and the second must be visible (D-03). */
    if sessions.rejected > 0 {
        table = table.header(
            Row::new(vec![
                Cell::from(""),
                Cell::from(format!("{} unreadable entr(y/ies) dropped", sessions.rejected)),
                Cell::from(""),
            ])
            .style(Style::default().fg(Color::Yellow)),
        );
    }

    frame.render_widget(table, inner);
}
