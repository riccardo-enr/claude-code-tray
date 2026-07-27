/*
`claude-tui` -- the Rust terminal dashboard.

Renders the same three panels, in the same order, from the same daemon socket as
`claude-tui.py`, which remains the oracle and is never invoked from this process.
Every displayed value comes from `claude_tui::format`, which mirrors
`claude_monitor.core` function for function; this file applies only glyphs,
colours and layout. Introducing a number formatter here is exactly the tray/TUI
divergence that D-05 exists to prevent.

**Theme.** The Python TUI sets `theme = "ansi-dark"` so it renders through the
host terminal's own sixteen ANSI colours and its default foreground and
background, inheriting whatever the terminal is themed with and following any
later change. This file does the same, which means one hard rule: **no
`Color::Rgb` anywhere.** A single hardcoded RGB value is enough to make one
element ignore the user's theme, and it will look wrong on exactly the setups
that are not the author's. `Color::Reset` means "the terminal's own default" and
is used deliberately, not as a fallback.

The cost is the same one the Python accepts: sixteen colours give the dim/stale
mode no RGB to blend, so a preserved frame reads flatter than a true opacity
fade would. That is the correct trade for a mode signal.

**Glyph parity.** The block, shade and braille codepoints below are the exact
ones the oracle draws and the daemon emits. They are the one deliberate break
from the repo's ASCII-only rule -- substituting ASCII would not be a cosmetic
difference, it would decode every sparkline column to a blank.

Not yet implemented, and Phase 13's scope: keyboard session navigation, click to
focus, and selection/scroll retention across refreshes. The socket-side support
for focus already exists in the client.
*/

use std::io::{self, Stdout};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use chrono::{Local, TimeZone};
use crossterm::event::{self, Event, KeyCode, KeyEventKind};
use crossterm::execute;
use crossterm::terminal::{
    disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen,
};
use ratatui::backend::CrosstermBackend;
use ratatui::layout::{Alignment, Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span, Text};
use ratatui::widgets::{Block, BorderType, Borders, Paragraph};
use ratatui::{Frame, Terminal};

use claude_tui::format::{
    band, fmt_elapsed, gauge_fill, heatmap_levels, project, sess_elapsed, sess_rank, spark_levels,
    tui_usage_rows, Band, Projection, WIN5, WIN7,
};
use claude_tui::{Client, ClientError, Section, Session, Snapshot, Usage};

/* Matches claude_monitor.core.TUI_FETCH_INTERVAL / TUI_TICK_INTERVAL. */
const FETCH_INTERVAL: Duration = Duration::from_secs(2);
const TICK_INTERVAL: Duration = Duration::from_secs(1);

/* Width in cells of a usage gauge bar. Render-only: the fill count is
format::gauge_fill, this is just how wide the track is drawn. */
const GAUGE_WIDTH: usize = 20;

/* Rows in the decoded trends column graph. 8 == the eight sparkline levels, so
a decoded level L fills rows 0..L from the bottom. Level 0 still shows one cell,
so a low-but-present hour never looks identical to an empty one. */
const TREND_ROWS: usize = 8;

/* Terminal equivalents of the dashboard's dark-theme blue ramp. Four levels,
matching HEAT_GLYPHS in claude-tui.py. All four are ANSI names, so they follow
the terminal's palette. */
const HEAT_DAYS: [&str; 7] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const HEAT_GLYPHS: [char; 4] = ['\u{2591}', '\u{2592}', '\u{2593}', '\u{2588}'];
const HEAT_COLORS: [Color; 4] = [Color::Blue, Color::LightBlue, Color::Cyan, Color::LightCyan];
/* Blank braille, not a space: it survives right-alignment of the multiline
heatmap instead of being stripped. */
const BRAILLE_BLANK: char = '\u{2800}';
/* Full block for the trend graph, light shade for an empty gauge track. */
const BLOCK_FULL: char = '\u{2588}';
const BLOCK_LIGHT: char = '\u{2591}';
/* A no-data heatmap cell. */
const HEAT_EMPTY: &str = "\u{b7}\u{b7}";

/* Change both: claude-monitor.py carries these strings. */
const USAGE_UNAVAILABLE: &str = "usage unavailable";
const TRENDS_COLLECTING: &str = "trends: collecting history...";
const NO_SESSIONS: &str = "No active Claude Code sessions";
/* The cold-start message, shown only when no good frame has ever arrived. */
const COLD_START: &str = "waiting for the claude-code-tray daemon...";

/* The heatmap block is a fixed 4 + 24*2 cells wide. */
const HEATMAP_WIDTH: u16 = 4 + 24 * 2;

/*
The last good frame, plus whatever went wrong since.

The D-06 split made concrete: a failed fetch never overwrites `snapshot`. Cold
start (`snapshot` still None) and a later outage (`snapshot` present, `error`
set) are different screens, and keeping them in separate fields is what makes
them impossible to confuse.
*/
struct App {
    source: Source,
    snapshot: Option<Snapshot>,
    error: Option<ClientError>,
    /*
    The selected session, held as its stable key rather than a row index.

    An index would silently point at a different session the moment a refresh
    reorders the list -- and it reorders constantly, because rows are sorted by
    status and a session's status is exactly what changes. Pressing Enter would
    then focus whatever slid into that slot. Keying by identity means the
    selection follows its session across refreshes, or disappears with it.
    */
    selected: Option<String>,
    /* Transient feedback for the last focus attempt. A focus failure is
    action-scoped: it belongs in the footer, and must never mark snapshot data
    stale or disturb the refresh state. */
    focus_note: Option<(String, Instant)>,
}

/* How long a focus note stays on screen before the footer returns to its
bindings. Long enough to read, short enough not to become furniture. */
const FOCUS_NOTE_TTL: Duration = Duration::from_secs(4);

/*
Where frames come from.

`Fixture` exists because a healthy daemon can only ever show the happy path. The
states most likely to render wrong -- a malformed section, an oversized session
list, a directory name full of escape sequences, a cold start -- never occur on a
working machine, so without a way to inject them they get reviewed by reading
rather than by looking. Pointing the real renderer at a corpus file closes that
gap: it is the same draw code, the same normalization, just a different byte
source.
*/
enum Source {
    Daemon(Box<Client>),
    /* Raw wire bytes, replayed on every refresh. */
    Fixture(Vec<u8>),
}

impl App {
    fn new(source: Source) -> Self {
        App { source, snapshot: None, error: None, selected: None, focus_note: None }
    }

    fn refresh(&mut self) {
        let fetched = match &self.source {
            Source::Daemon(client) => client.snapshot(),
            Source::Fixture(bytes) => Snapshot::from_slice(bytes),
        };
        match fetched {
            Ok(snapshot) => {
                self.snapshot = Some(snapshot);
                self.error = None;
            }
            /* The last good snapshot survives untouched. */
            Err(err) => self.error = Some(err),
        }
        self.reconcile_selection();
    }

    /* A preserved-but-stale frame. Distinct from a cold start. */
    fn stale(&self) -> bool {
        self.error.is_some() && self.snapshot.is_some()
    }

    /*
    The sessions to draw, in display order.

    Sorted by status rank with a stable sort, so two sessions sharing a status
    stay in the daemon's order. Normalization deliberately does not sort --
    ordering is presentation, and this is the only place that decides it, which
    is what lets the key handler and the renderer agree on what row N is.
    */
    fn ordered_sessions(&self) -> Vec<&Session> {
        let Some(Section::Present(sessions)) = self.snapshot.as_ref().map(|s| &s.sessions) else {
            return Vec::new();
        };
        let mut ordered: Vec<&Session> = sessions.entries.iter().collect();
        ordered.sort_by_key(|s| sess_rank(&s.status));
        ordered
    }

    /*
    Drop a selection whose session is gone, and select the first row when
    nothing is selected yet.

    A session ending should not leave the cursor pointing at nothing, and the
    first frame should arrive with a usable selection rather than requiring an
    arrow press to bootstrap one.
    */
    fn reconcile_selection(&mut self) {
        let keys: Vec<String> = self.ordered_sessions().iter().map(|s| stable_key(s)).collect();
        if keys.is_empty() {
            self.selected = None;
            return;
        }
        let still_present = self
            .selected
            .as_ref()
            .is_some_and(|sel| keys.iter().any(|k| k == sel));
        if !still_present {
            self.selected = keys.first().cloned();
        }
    }

    fn selected_index(&self) -> Option<usize> {
        let selected = self.selected.as_ref()?;
        self.ordered_sessions().iter().position(|s| &stable_key(s) == selected)
    }

    /* Move the selection by `delta` rows, clamped at both ends. Clamping rather
    than wrapping: a held-down arrow key should come to rest at the edge, not
    cycle past it. */
    fn move_selection(&mut self, delta: isize) {
        let ordered = self.ordered_sessions();
        if ordered.is_empty() {
            return;
        }
        let current = self.selected_index().unwrap_or(0) as isize;
        let next = (current + delta).clamp(0, ordered.len() as isize - 1) as usize;
        self.selected = ordered.get(next).map(|s| stable_key(s));
    }

    /*
    Ask the daemon to focus the selected session. Returns true when the daemon
    accepted the request, which is the caller's cue to leave.

    Nonfatal and action-scoped by contract: every outcome becomes a footer note,
    and none of them touches `snapshot`, `error` or the refresh cadence. A focus
    that fails because the pane is gone must not make the quota gauges look
    stale.

    Only an accepted focus returns true. Every refusal -- nothing selected, no
    focusable target, a daemon error, fixture replay -- keeps the app running so
    its note stays on screen; exiting would take the explanation with it.
    */
    fn focus_selected(&mut self) -> bool {
        let Some(index) = self.selected_index() else {
            self.note("no session selected");
            return false;
        };
        let ordered = self.ordered_sessions();
        let Some(session) = ordered.get(index) else {
            self.note("no session selected");
            return false;
        };
        let target = session.focus.clone();
        let label = session.dir.clone();

        if !target.focusable() {
            /* Same refusal as the Python client: no pane, and not Zed. */
            self.note(format!("{}: no focusable terminal target", label));
            return false;
        }
        match &self.source {
            Source::Daemon(client) => match client.focus(&target) {
                Ok(()) => {
                    self.note(format!("focusing {}", label));
                    true
                }
                /* Context is payload-free by construction, so it is safe to show. */
                Err(err) => {
                    self.note(format!("focus failed [{}]: {}", err.code, err.context));
                    false
                }
            },
            /* Replaying a fixture: say so rather than dialling a daemon that has
            nothing to do with the frame on screen. */
            Source::Fixture(_) => {
                self.note(format!("fixture mode: would focus {}", label));
                false
            }
        }
    }

    fn note(&mut self, text: impl Into<String>) {
        self.focus_note = Some((text.into(), Instant::now()));
    }

    fn live_note(&self) -> Option<&str> {
        match &self.focus_note {
            Some((text, at)) if at.elapsed() < FOCUS_NOTE_TTL => Some(text.as_str()),
            _ => None,
        }
    }
}

/*
A stable identity for one session.

Prefers the daemon's `id`. Falls back to the routing tuple when it is empty,
mirroring how claude-tui.py builds its row keys -- two sessions in the same
directory are still distinct if they are different panes.
*/
fn stable_key(session: &Session) -> String {
    if !session.id.is_empty() {
        return session.id.clone();
    }
    format!(
        "{}\u{1f}{}\u{1f}{}\u{1f}{}",
        session.focus.tmux, session.focus.pane, session.focus.term, session.dir
    )
}

const USAGE_TEXT: &str = "\
claude-tui -- terminal dashboard for claude-code-tray

  claude-tui                    run the dashboard against the daemon socket
  claude-tui --once             fetch once, print a plain-text dump, exit
  claude-tui --fixture <path>   read frames from a fixture file instead of the
                                daemon, so failure states can be rendered on a
                                healthy machine; combine with --once
  claude-tui --help             this message
";

fn main() -> io::Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.iter().any(|a| a == "--help" || a == "-h") {
        print!("{}", USAGE_TEXT);
        return Ok(());
    }

    /* `--fixture <path>` replays raw wire bytes in place of the socket. The
    renderer, normalization and error handling are all the real ones. */
    let source = match args.iter().position(|a| a == "--fixture") {
        Some(i) => match args.get(i + 1) {
            Some(path) => Source::Fixture(load_fixture_wire(path)?),
            None => {
                eprintln!("claude-tui: --fixture needs a path");
                return Ok(());
            }
        },
        None => Source::Daemon(Box::new(Client::new())),
    };

    /* `--once` fetches one snapshot, prints a plain-text dump and exits. No
    terminal, no raw mode -- so the client can be smoke-tested from a pipe, a
    CI job, or a `just` recipe. Phase 14's parity harness wants this seam too. */
    if args.iter().any(|a| a == "--once") {
        return dump_once(source);
    }
    let mut terminal = enter_terminal()?;
    let result = run(&mut terminal, source);
    leave_terminal(&mut terminal)?;
    if let Err(err) = &result {
        eprintln!("claude-tui: {}", err);
    }
    result
}

/*
Extract the raw wire bytes from a fixture file.

Accepts the shared corpus format (`wire` as a string, or `wire_bytes` as an
array for inputs that are not valid UTF-8), and falls back to treating the file
as a raw wire line. The fallback matters for the fastest debugging loop there
is: pipe a hand-edited blob straight in without wrapping it in the corpus
envelope first.
*/
fn load_fixture_wire(path: &str) -> io::Result<Vec<u8>> {
    let raw = std::fs::read(path)?;

    if let Ok(doc) = serde_json::from_slice::<serde_json::Value>(&raw) {
        if let Some(text) = doc.get("wire").and_then(|v| v.as_str()) {
            return Ok(text.as_bytes().to_vec());
        }
        if let Some(bytes) = doc.get("wire_bytes").and_then(|v| v.as_array()) {
            return Ok(bytes.iter().filter_map(|b| b.as_u64()).map(|b| b as u8).collect());
        }
    }
    Ok(raw)
}

fn run(terminal: &mut Terminal<CrosstermBackend<Stdout>>, source: Source) -> io::Result<()> {
    let mut app = App::new(source);
    app.refresh();
    let mut last_fetch = Instant::now();

    loop {
        terminal.draw(|frame| draw(frame, &app))?;

        /* Poll for at most one tick, so countdowns and running-session counters
        re-render every second without busy-waiting between snapshots. */
        if event::poll(TICK_INTERVAL)? {
            if let Event::Key(key) = event::read()? {
                /* Release events are delivered on terminals with the kitty
                keyboard protocol; acting on both would move two rows per
                press. */
                if key.kind == KeyEventKind::Press && !handle_key(&mut app, key.code) {
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

/*
Apply one keypress. Returns false to quit.

`q` stays the sole exit binding -- no command palette, no theme toggle, matching
the oracle, which switches the palette off for exactly that reason. Navigation
is arrows plus j/k, and Enter activates, which is what the oracle's row-cursor
DataTable does.
*/
fn handle_key(app: &mut App, code: KeyCode) -> bool {
    match code {
        KeyCode::Char('q') => return false,
        KeyCode::Up | KeyCode::Char('k') => app.move_selection(-1),
        KeyCode::Down | KeyCode::Char('j') => app.move_selection(1),
        KeyCode::Home => app.move_selection(isize::MIN / 2),
        KeyCode::End => app.move_selection(isize::MAX / 2),
        KeyCode::PageUp => app.move_selection(-10),
        KeyCode::PageDown => app.move_selection(10),
        /* Enter is a picker, not a toggle: the usual home is a tmux popup (`popup
        -E`), which covers the very pane the focus just moved to until this process
        exits. Leaving on a successful focus is what makes the jump visible. */
        KeyCode::Enter => return !app.focus_selected(),
        _ => {}
    }
    true
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

/* Local wall-clock formatters (claude_monitor.core.hhmm / weekday_hhmm). These
live in the binary rather than the library so the parity substrate stays free of
a timezone dependency -- rendering an epoch in the viewer's local time is a
presentation concern, and Phase 14 compares epochs, not clock strings. */
fn hhmm(epoch: f64) -> String {
    match Local.timestamp_opt(epoch as i64, 0).single() {
        Some(dt) => dt.format("%H:%M").to_string(),
        None => "--:--".to_string(),
    }
}

fn weekday_hhmm(epoch: f64) -> String {
    match Local.timestamp_opt(epoch as i64, 0).single() {
        Some(dt) => dt.format("%a %H:%M").to_string(),
        None => "--:--".to_string(),
    }
}

fn band_color(b: Band) -> Color {
    match b {
        Band::Green => Color::Green,
        Band::Yellow => Color::Yellow,
        Band::Red => Color::Red,
    }
}

/* Dim the whole body when the last frame is stale, so a preserved frame is
never mistaken for a live one. */
fn body_style(app: &App) -> Style {
    if app.stale() {
        Style::default().add_modifier(Modifier::DIM)
    } else {
        Style::default()
    }
}

/*
A titled rounded panel.

The border colour is static and theme-derived (`Color::Reset` = the terminal's
own foreground), never band-coupled: the threshold signal belongs in the row
text and the gauge fill, never on the chrome.
*/
fn panel(title: &str) -> Block<'_> {
    Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Color::Reset))
        .title(Span::styled(
            format!(" {} ", title),
            Style::default().add_modifier(Modifier::BOLD),
        ))
}

fn draw(frame: &mut Frame, app: &App) {
    /* Cold start is a sibling of the body, never inside it, so its message is
    never dimmed by the stale modifier. */
    if app.snapshot.is_none() {
        draw_cold_start(frame, app);
        return;
    }

    let usage_height = usage_panel_height(app);
    let trends_height = trends_panel_height(app);
    let areas = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1),             /* header */
            Constraint::Length(usage_height),  /* usage: sizes to content */
            Constraint::Length(trends_height), /* trends: sizes to content */
            Constraint::Min(3),                /* sessions: absorbs the rest */
            Constraint::Length(1),             /* footer */
        ])
        .split(frame.area());

    let now = now_epoch();
    draw_header(frame, areas[0], app);
    draw_usage(frame, areas[1], app, now);
    draw_trends(frame, areas[2], app);
    draw_sessions(frame, areas[3], app, now);
    frame.render_widget(footer_widget(app), areas[4]);
}

fn draw_cold_start(frame: &mut Frame, app: &App) {
    let areas = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(1), Constraint::Min(1), Constraint::Length(1)])
        .split(frame.area());
    draw_header(frame, areas[0], app);

    let mut lines = vec![Line::from(""), Line::from(COLD_START)];
    if let Some(err) = &app.error {
        /* Error context is payload-free by construction, so it is safe to show
        verbatim. */
        lines.push(Line::from(Span::styled(
            format!("({})", err),
            Style::default().add_modifier(Modifier::DIM),
        )));
    }
    frame.render_widget(
        Paragraph::new(lines).alignment(Alignment::Center),
        areas[1],
    );
    frame.render_widget(footer_widget(app), areas[2]);
}

fn draw_header(frame: &mut Frame, area: Rect, app: &App) {
    let (label, style) = if app.snapshot.is_none() {
        ("connecting...", Style::default().add_modifier(Modifier::DIM))
    } else if app.stale() {
        ("stale -- retrying", Style::default().fg(Color::Yellow))
    } else {
        ("live", Style::default().fg(Color::Green))
    };
    let left = Line::from(vec![
        Span::styled(" claude-tui ", Style::default().add_modifier(Modifier::BOLD)),
        Span::styled(label, style),
    ]);
    frame.render_widget(Paragraph::new(left), area);

    /* Header clock, matching the oracle's `Header(show_clock=True)`. A live
    clock beside a frozen frame is precisely what makes staleness visible. */
    let clock = Local::now().format("%H:%M:%S").to_string();
    frame.render_widget(
        Paragraph::new(Line::from(Span::styled(
            format!("{} ", clock),
            Style::default().add_modifier(Modifier::DIM),
        )))
        .alignment(Alignment::Right),
        area,
    );
}

fn footer_widget(app: &App) -> Paragraph<'static> {
    let dim = Style::default().add_modifier(Modifier::DIM);
    /* A focus note takes the footer while it is live; the bindings return
    afterwards. Feedback matters more than a reminder the user just used. */
    match app.live_note() {
        Some(note) => Paragraph::new(Line::from(Span::styled(
            format!(" {}", note),
            Style::default().fg(Color::Cyan),
        ))),
        None => Paragraph::new(Line::from(vec![
            Span::styled(" up/down", dim),
            Span::styled(" select   ", dim),
            Span::styled("enter", dim),
            Span::styled(" focus+exit   ", dim),
            Span::styled("q", dim),
            Span::styled(" quit", dim),
        ])),
    }
    .style(dim)
}

/* --- usage ------------------------------------------------------------- */

fn snapshot_usage(app: &App) -> Option<&Usage> {
    match app.snapshot.as_ref().map(|s| &s.usage) {
        Some(Section::Present(u)) => Some(u),
        _ => None,
    }
}

fn usage_rows_for(app: &App, now: f64) -> Vec<String> {
    tui_usage_rows(snapshot_usage(app), now)
}

fn usage_panel_height(app: &App) -> u16 {
    let rows = usage_rows_for(app, now_epoch()).len() as u16;
    rows + 2 /* rounded border */
}

/*
A GAUGE_WIDTH-cell gradient meter.

Cells below the fill count are a full block coloured by their *position* along
the bar, not by the overall percentage, so the bar always sweeps green to red
like btop's meter. The remainder is a dim light-shade track, so an empty gauge
still shows where the bar would go. The fill count itself comes from
`format::gauge_fill`; this applies only glyphs and per-cell colour.
*/
fn gauge_spans(pct: f64) -> Vec<Span<'static>> {
    let filled = gauge_fill(pct, GAUGE_WIDTH);
    (0..GAUGE_WIDTH)
        .map(|i| {
            if i < filled {
                Span::styled(
                    BLOCK_FULL.to_string(),
                    Style::default().fg(band_color(band(i as f64 / GAUGE_WIDTH as f64 * 100.0))),
                )
            } else {
                Span::styled(
                    BLOCK_LIGHT.to_string(),
                    Style::default().add_modifier(Modifier::DIM),
                )
            }
        })
        .collect()
}

/*
Band-colour a pre-formatted usage row by its cap's proximity band.

The percentage, countdown and burn segments take the band colour; the cap label
and any token-count segment stay at the terminal default. Reformats nothing --
the cells are split back out of the string `format::tui_usage_rows` already
produced, which is why that separator is pinned by a test.
*/
fn cap_row_spans(row: &str, pct: f64) -> Vec<Span<'static>> {
    let colour = Style::default().fg(band_color(band(pct)));
    let mut spans = Vec::new();
    for (i, cell) in row.split("  ").enumerate() {
        if i > 0 {
            spans.push(Span::raw("  "));
        }
        let coloured = i == 1
            || cell.starts_with("resets")
            || cell.starts_with("week resets")
            || cell.starts_with("burn:");
        spans.push(if coloured {
            Span::styled(cell.to_string(), colour)
        } else {
            Span::raw(cell.to_string())
        });
    }
    spans
}

/* Render a projection without duplicating projection math. */
fn projection_span(pct: Option<f64>, reset: Option<f64>, win: f64, now: f64) -> Span<'static> {
    let dim = Style::default().add_modifier(Modifier::DIM);
    match project(pct, reset, win, now) {
        Projection::Unknown => Span::styled("proj --", dim),
        Projection::Early => Span::styled("proj -- (early)", dim),
        Projection::Projected { pct: projected, exhaust } => {
            let stamp = |e: f64| if win == WIN7 { weekday_hhmm(e) } else { hhmm(e) };
            match exhaust {
                Some(when) => Span::styled(
                    format!("out ~{}", stamp(when)),
                    Style::default().fg(Color::Red),
                ),
                None => Span::styled(
                    format!("proj {}% @{}", projected.round() as i64, stamp(reset.unwrap_or(0.0))),
                    Style::default().fg(band_color(band(projected))),
                ),
            }
        }
    }
}

fn draw_usage(frame: &mut Frame, area: Rect, app: &App, now: f64) {
    let block = panel("usage");
    let inner = block.inner(area);
    frame.render_widget(block, area);

    let rows = usage_rows_for(app, now);
    let Some(usage) = snapshot_usage(app) else {
        frame.render_widget(
            Paragraph::new(USAGE_UNAVAILABLE).style(Style::default().add_modifier(Modifier::DIM)),
            inner,
        );
        return;
    };

    /* Left column holds gauge + row text; the right column right-aligns each
    cap's projection. */
    let caps: Vec<(f64, Option<f64>, f64)> = {
        let mut c = vec![(usage.used_percentage, Some(usage.resets_at_epoch), WIN5)];
        if rows.len() > 1 {
            if let Some(pct7) = usage.seven_day_pct {
                c.push((pct7, usage.seven_day_reset, WIN7));
            }
        }
        c
    };

    let proj_width: u16 = 22;
    let columns = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Min(10), Constraint::Length(proj_width)])
        .split(inner);

    let mut left_lines = Vec::new();
    let mut right_lines = Vec::new();
    for (i, row) in rows.iter().enumerate() {
        let Some(&(pct, reset, win)) = caps.get(i) else {
            left_lines.push(Line::from(row.clone()));
            right_lines.push(Line::from(""));
            continue;
        };
        let mut spans = gauge_spans(pct);
        spans.push(Span::raw("  "));
        spans.extend(cap_row_spans(row, pct));
        left_lines.push(Line::from(spans));
        right_lines.push(Line::from(projection_span(Some(pct), reset, win, now)));
    }

    let style = body_style(app);
    frame.render_widget(Paragraph::new(left_lines).style(style), columns[0]);
    frame.render_widget(
        Paragraph::new(right_lines).alignment(Alignment::Right).style(style),
        columns[1],
    );
}

/* --- trends + heatmap --------------------------------------------------- */

fn snapshot_trends(app: &App) -> Option<&Vec<String>> {
    match app.snapshot.as_ref().map(|s| &s.trends) {
        Some(Section::Present(rows)) if !rows.is_empty() => Some(rows),
        _ => None,
    }
}

/* Same read as snapshot_trends, for the second, independent cumulative-window
graph: only a non-empty Present section renders, everything else (absent,
malformed, or a daemon too old to send it) is a silent no-op. */
fn snapshot_cum_trend(app: &App) -> Option<&Vec<String>> {
    match app.snapshot.as_ref().map(|s| &s.cum_trend) {
        Some(Section::Present(rows)) if !rows.is_empty() => Some(rows),
        _ => None,
    }
}

fn snapshot_heatmap(app: &App) -> Option<Vec<Vec<Option<usize>>>> {
    match app.snapshot.as_ref().map(|s| &s.heatmap) {
        Some(Section::Present(h)) => heatmap_levels(&h.grid, HEAT_GLYPHS.len()),
        _ => None,
    }
}

fn trends_panel_height(app: &App) -> u16 {
    let Some(trends) = snapshot_trends(app) else {
        return 3; /* one message line + border */
    };
    /* The graph is TREND_ROWS tall with the remaining core-formatted rows
    below it; the heatmap is one hour-label row plus seven day rows. */
    let mut left = TREND_ROWS + trends.len().saturating_sub(1);
    if let Some(cum) = snapshot_cum_trend(app) {
        /* The leading 1 is the "window usage" label row separating the two graphs. */
        left += 1 + TREND_ROWS + cum.len().saturating_sub(1);
    }
    let right = if snapshot_heatmap(app).is_some() { 1 + HEAT_DAYS.len() } else { 0 };
    (left.max(right) as u16) + 2
}

/*
The decoded trend column graph.

`trends[0]` is the sparkline the daemon already built; `spark_levels` inverts it
back to per-column heights, so no trend math is recomputed here. A level L fills
rows 0..L from the bottom, and each cell takes the band colour of its own height
-- so a tall column shades toward red exactly as the gauge does. A `None` column
stays blank, which is what keeps an unsampled hour visually distinct from an
hour of genuinely zero usage.
*/
fn trend_graph_lines(trends: &[String], axis: Option<&[String]>) -> Vec<Line<'static>> {
    let levels = spark_levels(trends.first().map(String::as_str).unwrap_or(""));
    let mut lines = Vec::with_capacity(TREND_ROWS + trends.len());

    /* Y-axis gutter. The daemon sends one tick per graph row, top row first, and
    decides which rows carry a number -- the renderer only right-aligns them, so the
    ticks stay true to the rows they label. Gutter width is the widest tick, and with
    no axis at all it collapses to nothing rather than reserving blank columns. The
    text rows below are indented to match, so the graph and the numbers under it share
    a left edge. */
    let tick = |row: usize| -> &str {
        /* Row 0 is the FLOOR here, but the daemon sends the top row first. */
        axis
            .and_then(|ticks| ticks.get(TREND_ROWS - 1 - row))
            .map(String::as_str)
            .unwrap_or("")
    };
    let axis_width = axis
        .map(|ticks| ticks.iter().map(|t| t.chars().count()).max().unwrap_or(0) + 1)
        .unwrap_or(0);
    let dim = Style::default().add_modifier(Modifier::DIM);
    let gutter = |row: usize| -> Option<Span<'static>> {
        axis?;
        Some(Span::styled(
            format!("{:>width$} ", tick(row), width = axis_width.saturating_sub(1)),
            dim,
        ))
    };

    for r in (0..TREND_ROWS).rev() {
        let mut spans: Vec<Span> = gutter(r).into_iter().collect();
        spans.extend(levels
            .iter()
            .map(|lv| match lv {
                Some(l) if *l >= r => Span::styled(
                    BLOCK_FULL.to_string(),
                    Style::default()
                        .fg(band_color(band(*l as f64 / (TREND_ROWS - 1) as f64 * 100.0))),
                ),
                _ => Span::raw(" "),
            })
            .collect::<Vec<Span>>());
        lines.push(Line::from(spans));
    }
    /* The remaining core-formatted rows, verbatim, indented under the graph. */
    let indent = " ".repeat(axis_width);
    for row in trends.iter().skip(1) {
        lines.push(Line::from(format!("{}{}", indent, row)));
    }
    lines
}

/*
The weekday-by-hour heatmap, in terminal cells.

Mirrors the HTML dashboard: Monday..Sunday rows by 00..23 columns, intensity
normalized against the dataset maximum by `format::heatmap_levels`. Each cell is
two glyphs wide so the grid reads as a grid rather than a stripe. Hour labels
appear every three columns; the gaps between them are blank braille rather than
spaces so right-alignment cannot strip them.
*/
fn heatmap_lines(levels: &[Vec<Option<usize>>]) -> Vec<Line<'static>> {
    let dim = Style::default().add_modifier(Modifier::DIM);
    let mut lines = Vec::with_capacity(1 + HEAT_DAYS.len());

    let mut header = vec![Span::styled("    ", dim)];
    for hour in 0..24 {
        let label = if hour % 3 == 0 {
            format!("{:02}", hour)
        } else {
            BRAILLE_BLANK.to_string().repeat(2)
        };
        header.push(Span::styled(label, dim));
    }
    lines.push(Line::from(header));

    for (day, name) in HEAT_DAYS.iter().enumerate() {
        let mut spans = vec![Span::styled(format!("{} ", name), dim)];
        for hour in 0..24 {
            match levels.get(day).and_then(|row| row.get(hour)).copied().flatten() {
                Some(level) => {
                    let glyph = HEAT_GLYPHS.get(level).copied().unwrap_or(HEAT_GLYPHS[0]);
                    let colour = HEAT_COLORS.get(level).copied().unwrap_or(Color::Blue);
                    spans.push(Span::styled(
                        glyph.to_string().repeat(2),
                        Style::default().fg(colour),
                    ));
                }
                /* No data for this hour: distinct from a genuine zero. */
                None => spans.push(Span::styled(HEAT_EMPTY, dim)),
            }
        }
        lines.push(Line::from(spans));
    }
    lines
}

fn draw_trends(frame: &mut Frame, area: Rect, app: &App) {
    let block = panel("trends");
    let inner = block.inner(area);
    frame.render_widget(block, area);
    let style = body_style(app);

    let Some(trends) = snapshot_trends(app) else {
        /* Collecting or degraded: render the message verbatim and never draw a
        heatmap beside it. */
        frame.render_widget(
            Paragraph::new(TRENDS_COLLECTING).style(Style::default().add_modifier(Modifier::DIM)),
            inner,
        );
        return;
    };

    let mut graph = trend_graph_lines(
        trends,
        app.snapshot.as_ref().and_then(|s| s.trend_axis.as_deref()),
    );
    /* Second, independent graph: cumulative usage within the current 5h window.
    Additive only -- when absent, `graph` is exactly what it was before this
    change, so the existing bar chart renders byte-identically. */
    if let Some(cum) = snapshot_cum_trend(app) {
        graph.push(Line::from(Span::styled(
            "window usage (0-100%)",
            Style::default().add_modifier(Modifier::DIM),
        )));
        graph.extend(trend_graph_lines(
            cum,
            app.snapshot.as_ref().and_then(|s| s.cum_trend_axis.as_deref()),
        ));
    }
    let heatmap = snapshot_heatmap(app);

    /* Side by side when the heatmap fits; graph alone when it does not, so a
    narrow terminal loses the heatmap rather than wrapping it into noise. */
    match heatmap {
        Some(levels) if inner.width > HEATMAP_WIDTH + 12 => {
            let columns = Layout::default()
                .direction(Direction::Horizontal)
                .constraints([Constraint::Min(10), Constraint::Length(HEATMAP_WIDTH)])
                .split(inner);
            frame.render_widget(Paragraph::new(graph).style(style), columns[0]);
            frame.render_widget(
                Paragraph::new(Text::from(heatmap_lines(&levels)))
                    .alignment(Alignment::Right)
                    .style(style),
                columns[1],
            );
        }
        _ => frame.render_widget(Paragraph::new(graph).style(style), inner),
    }
}

/* --- sessions ----------------------------------------------------------- */

/* ANSI status colours, matching claude_monitor.core.SESS_STATUS_BAND: waiting
yellow, running green, done dim, anything unknown at the terminal default. */
fn status_style(status: &str) -> Style {
    match status {
        "waiting" => Style::default().fg(Color::Yellow),
        "running" => Style::default().fg(Color::Green),
        "done" => Style::default().add_modifier(Modifier::DIM),
        _ => Style::default().fg(Color::Reset),
    }
}

fn draw_sessions(frame: &mut Frame, area: Rect, app: &App, now: f64) {
    let block = panel("sessions");
    let inner = block.inner(area);
    frame.render_widget(block, area);
    let dim = Style::default().add_modifier(Modifier::DIM);

    let ordered = app.ordered_sessions();
    if ordered.is_empty() {
        let message = match app.snapshot.as_ref().map(|s| &s.sessions) {
            /* An empty list is data: no sessions are running. A missing or
            malformed section is not, and saying "no sessions" for it would be
            a confident lie about a thing we do not know. */
            Some(Section::Present(_)) => NO_SESSIONS,
            Some(Section::Malformed(_)) => "sessions unreadable",
            _ => "sessions unavailable",
        };
        frame.render_widget(Paragraph::new(message).style(dim), inner);
        return;
    }

    let rejected = match app.snapshot.as_ref().map(|s| &s.sessions) {
        Some(Section::Present(s)) => s.rejected,
        _ => 0,
    };

    let mut lines: Vec<Line> = Vec::with_capacity(ordered.len() + 1);
    if rejected > 0 {
        /* "3 sessions" and "3 sessions, 1 unreadable" are different states and
        the second must be visible. */
        lines.push(Line::from(Span::styled(
            format!("  {} unreadable entries dropped", rejected),
            Style::default().fg(Color::Yellow),
        )));
    }

    let selected = app.selected_index();
    let dir_width = (inner.width as usize).saturating_sub(24).clamp(12, 60);

    for (i, s) in ordered.iter().enumerate() {
        let is_selected = selected == Some(i);
        let elapsed = sess_elapsed(&s.status, s.entered, s.frozen, now)
            .map(fmt_elapsed)
            .unwrap_or_else(|| "-".to_string());

        /* The cursor is REVERSED rather than given a background colour. Reverse
        swaps the terminal's own foreground and background, so the highlight is
        legible on any theme -- a fixed background would be invisible on the
        themes that happen to share it. */
        let row_style = if is_selected {
            Style::default().add_modifier(Modifier::REVERSED)
        } else {
            Style::default()
        };
        let marker = if is_selected { "> " } else { "  " };

        lines.push(Line::from(vec![
            Span::styled(marker, row_style),
            Span::styled(format!("{:<9}", s.status), status_style(&s.status).patch(row_style)),
            /* Already sanitized at the normalization boundary; truncated here
            only so a long path cannot push the duration off the panel. */
            Span::styled(
                format!("{:<width$}", truncate_cell(&s.dir, dir_width), width = dir_width),
                row_style,
            ),
            Span::styled(format!("{:>9}", elapsed), row_style.patch(dim)),
        ]));
    }

    /*
    Scroll so the cursor stays visible, derived rather than stored.

    Keeping an independent scroll offset in App would mean two pieces of state
    that can disagree -- the classic "cursor is selected but off-screen" bug.
    Deriving the offset from the selection each frame makes that state
    unrepresentable.
    */
    let height = inner.height as usize;
    let offset = match selected {
        Some(sel) => {
            let row = sel + usize::from(rejected > 0);
            row.saturating_sub(height.saturating_sub(1))
        }
        None => 0,
    };

    frame.render_widget(
        Paragraph::new(lines).scroll((offset as u16, 0)).style(body_style(app)),
        inner,
    );
}

/* Bound one display cell, marking the cut. The value is already sanitized and
globally bounded; this is the per-column fit. */
fn truncate_cell(text: &str, width: usize) -> String {
    if text.chars().count() <= width {
        return text.to_string();
    }
    let keep = width.saturating_sub(3);
    text.chars().take(keep).chain("...".chars()).collect()
}

/* --- non-TTY dump ------------------------------------------------------- */

/*
One fetch, printed as plain text, no terminal involved.

Reports each section's state by name, so a malformed section is visible as
malformed rather than silently rendering as empty -- the whole point of section
independence is lost if the diagnostic path flattens it back to "nothing there".
*/
fn dump_once(source: Source) -> io::Result<()> {
    let mut app = App::new(source);
    app.refresh();
    let Some(snapshot) = app.snapshot.as_ref() else {
        /* Print the code AND its context: a bare "failed" would send me back to
        the socket to find out which of five failure modes it was. */
        match app.error {
            Some(err) => println!("fetch failed [{}]: {}", err.code, err.context),
            None => println!("fetch failed: no snapshot and no error (should be impossible)"),
        }
        return Ok(());
    };
    let now = now_epoch();

    println!("usage:    {}", snapshot.usage.state_name());
    if let Section::Present(u) = &snapshot.usage {
        let rows = tui_usage_rows(Some(u), now);
        let caps = [
            (Some(u.used_percentage), Some(u.resets_at_epoch), WIN5),
            (u.seven_day_pct, u.seven_day_reset, WIN7),
        ];
        for (i, row) in rows.iter().enumerate() {
            let proj = caps
                .get(i)
                .map(|&(p, r, w)| projection_span(p, r, w, now).content.to_string())
                .unwrap_or_default();
            println!("  {}   {}", row, proj);
        }
    }

    println!(
        "trends:   {} (y-axis {})",
        snapshot.trends.state_name(),
        match &snapshot.trend_axis {
            Some(ticks) => ticks
                .iter()
                .filter(|t| !t.is_empty())
                .cloned()
                .collect::<Vec<_>>()
                .join(" .. "),
            None => "unlabelled".to_string(),
        }
    );
    if let Section::Present(rows) = &snapshot.trends {
        for row in rows {
            println!("  {}", row);
        }
    }

    println!("heatmap:  {}", snapshot.heatmap.state_name());
    if let Section::Present(h) = &snapshot.heatmap {
        match heatmap_levels(&h.grid, HEAT_GLYPHS.len()) {
            Some(levels) => {
                for (day, name) in HEAT_DAYS.iter().enumerate() {
                    let row: String = (0..24)
                        .map(|hour| {
                            match levels.get(day).and_then(|r| r.get(hour)).copied().flatten() {
                                Some(l) => HEAT_GLYPHS.get(l).copied().unwrap_or(HEAT_GLYPHS[0]),
                                None => '.',
                            }
                        })
                        .collect();
                    println!("  {} {}", name, row);
                }
            }
            None => println!("  (no populated cells)"),
        }
    }

    println!("sessions: {}", snapshot.sessions.state_name());
    if let Section::Present(s) = &snapshot.sessions {
        /* Same ordering the TUI applies, so the dump is a faithful stand-in
        for what is on screen rather than raw daemon order. */
        let mut ordered: Vec<_> = s.entries.iter().collect();
        ordered.sort_by_key(|e| sess_rank(&e.status));
        for entry in ordered {
            let elapsed = sess_elapsed(&entry.status, entry.entered, entry.frozen, now)
                .map(fmt_elapsed)
                .unwrap_or_else(|| "-".to_string());
            println!(
                "  {:<8} {:<40} {:>9}  focusable={}",
                entry.status, entry.dir, elapsed, entry.focus.focusable()
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

/* --- render smoke tests ------------------------------------------------- */

/*
Draw every corpus fixture into an off-screen buffer at several terminal sizes.

Normalization is covered by the library tests and the fixture harness; this
covers the half they cannot reach -- the drawing code. A panic here is a real
crash on a real terminal, and the states most able to cause one (a malformed
section, a rejected-entry banner, a hostile directory name, a terminal too
narrow for the heatmap) are exactly the ones a healthy daemon never produces.

The width sweep is the point. Layout arithmetic is where an off-by-one becomes a
subtract-with-overflow, so the sizes below deliberately include a terminal too
small for the heatmap and one too small for anything.
*/
#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::backend::TestBackend;

    fn corpus() -> Vec<std::path::PathBuf> {
        let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .expect("crate dir has a parent")
            .join("fixtures/snapshot");
        let mut paths: Vec<_> = std::fs::read_dir(&dir)
            .unwrap_or_else(|e| panic!("cannot read corpus at {:?}: {}", dir, e))
            .filter_map(|e| e.ok().map(|e| e.path()))
            .filter(|p| p.extension().and_then(|x| x.to_str()) == Some("json"))
            .collect();
        paths.sort();
        assert!(!paths.is_empty(), "corpus is empty -- this test would pass vacuously");
        paths
    }

    fn app_for(path: &std::path::Path) -> App {
        let wire = load_fixture_wire(path.to_str().expect("utf-8 path")).expect("readable fixture");
        let mut app = App::new(Source::Fixture(wire));
        app.refresh();
        app
    }

    #[test]
    fn every_fixture_renders_at_every_size_without_panicking() {
        for path in corpus() {
            let app = app_for(&path);
            for (w, h) in [(120, 40), (100, 30), (80, 24), (60, 20), (40, 12), (20, 8)] {
                let backend = TestBackend::new(w, h);
                let mut terminal = Terminal::new(backend).expect("test terminal");
                terminal
                    .draw(|frame| draw(frame, &app))
                    .unwrap_or_else(|e| panic!("{:?} at {}x{}: {}", path, w, h, e));
            }
        }
    }

    #[test]
    fn a_cold_start_and_an_outage_render_differently() {
        /* The D-06 split, checked on screen rather than only in the struct:
        a preserved frame must not be mistaken for a first connection. */
        let cold = App::new(Source::Fixture(b"not json".to_vec()));
        let mut cold = cold;
        cold.refresh();
        assert!(cold.snapshot.is_none() && cold.error.is_some());
        assert!(!cold.stale(), "a cold start is not a stale frame");

        let mut outage = app_for(&corpus()[0]);
        assert!(outage.snapshot.is_some());
        outage.source = Source::Fixture(b"not json".to_vec());
        outage.refresh();
        assert!(outage.snapshot.is_some(), "a failed fetch destroyed the last good frame");
        assert!(outage.stale(), "a preserved frame must read as stale");

        let render = |app: &App| {
            let mut terminal = Terminal::new(TestBackend::new(100, 30)).expect("test terminal");
            terminal.draw(|frame| draw(frame, app)).expect("draw");
            let buffer = terminal.backend().buffer().clone();
            buffer.content().iter().map(|c| c.symbol()).collect::<String>()
        };
        assert!(render(&cold).contains("waiting for"), "cold start lost its message");
        assert!(!render(&outage).contains("waiting for"), "an outage showed the cold-start screen");
    }

    #[test]
    fn no_rendered_cell_ever_contains_a_control_character() {
        /*
        The end-to-end statement of RTUI-13: not "normalization sanitizes", but
        "nothing hostile reaches the screen". Asserted on the actual buffer, so
        a future renderer that formats a raw value straight from the wire fails
        here even if normalization is still correct.
        */
        for path in corpus() {
            let app = app_for(&path);
            let mut terminal = Terminal::new(TestBackend::new(120, 40)).expect("test terminal");
            terminal.draw(|frame| draw(frame, &app)).expect("draw");
            for cell in terminal.backend().buffer().content() {
                for ch in cell.symbol().chars() {
                    assert!(
                        !ch.is_control(),
                        "{:?} rendered control character {:?}",
                        path,
                        ch
                    );
                }
            }
        }
    }

    #[test]
    fn the_renderer_uses_no_rgb_so_the_terminal_palette_always_wins() {
        /*
        RTUI-07 as a test rather than a convention. The oracle renders through
        the terminal's sixteen ANSI colours; one hardcoded RGB value would make
        that element ignore the user's theme, and it would only look wrong on
        setups that are not the author's -- the kind of bug review does not catch.
        */
        for path in corpus() {
            let app = app_for(&path);
            let mut terminal = Terminal::new(TestBackend::new(120, 40)).expect("test terminal");
            terminal.draw(|frame| draw(frame, &app)).expect("draw");
            for cell in terminal.backend().buffer().content() {
                for colour in [cell.fg, cell.bg] {
                    assert!(
                        !matches!(colour, Color::Rgb(..) | Color::Indexed(_)),
                        "{:?} used a non-ANSI colour {:?}",
                        path,
                        colour
                    );
                }
            }
        }
    }

    #[test]
    fn the_trend_graph_draws_every_tick_the_daemon_sends_at_its_own_row() {
        /* The daemon owns which rows carry a number and what they say; the renderer
        only right-aligns them into a gutter as wide as the widest tick. Ticks arrive
        top row first, which is the reverse of the bottom-up draw order -- getting that
        backwards would silently label the floor with the peak. */
        let trends = vec!["\u{2581}\u{2588}".to_string(), "today 1M/hr".to_string()];
        let axis: Vec<String> = ["60.0M/18%", "", "", "34.3M/10%", "", "", "", "0"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        let text = |line: &Line| {
            line.spans.iter().map(|s| s.content.as_ref()).collect::<String>()
        };

        let labelled = trend_graph_lines(&trends, Some(&axis));
        assert!(text(&labelled[0]).starts_with("60.0M/18% "), "peak tick missing from the top row");
        assert!(
            text(&labelled[3]).starts_with("34.3M/10% "),
            "a middle tick must land on its own row, not the top"
        );
        assert!(text(&labelled[1]).starts_with("          "), "an unticked row grew a label");
        assert!(
            text(&labelled[TREND_ROWS - 1]).starts_with("        0 "),
            "floor tick missing from the bottom row"
        );
        assert_eq!(
            text(&labelled[TREND_ROWS]),
            "          today 1M/hr",
            "text rows must be indented under the graph, not under the gutter"
        );

        let plain = trend_graph_lines(&trends, None);
        assert_eq!(plain.len(), labelled.len(), "the gutter changed the row count");
        assert_eq!(text(&plain[TREND_ROWS]), "today 1M/hr");
        /* One cell per sparkline column and nothing else: a blank gutter would show
        up here as extra leading cells (the top row's own columns can be blank). */
        assert_eq!(text(&plain[0]).chars().count(), 2, "an absent axis still reserved a gutter");
        assert_eq!(text(&labelled[0]).chars().count(), 2 + 10);
    }

    fn buffer_text(app: &App, w: u16, h: u16) -> String {
        let mut terminal = Terminal::new(TestBackend::new(w, h)).expect("test terminal");
        terminal.draw(|frame| draw(frame, app)).expect("draw");
        terminal.backend().buffer().content().iter().map(|c| c.symbol()).collect::<String>()
    }

    #[test]
    fn cum_trend_adds_a_second_graph_below_the_hourly_bars() {
        /* Both keys present: the original hourly bar chart's rows must render
        byte-identically to the no-cum_trend case, and the new window-usage
        graph must appear below it -- additive, never a replacement. */
        let wire_with = r#"{"trends":["▁█","today 1M/hr"],"cum_trend":["▂▃"]}"#;
        let app_with = sessions_app(wire_with);
        let wire_without = r#"{"trends":["▁█","today 1M/hr"]}"#;
        let app_without = sessions_app(wire_without);

        let render_trends_rows = |app: &App| -> Vec<String> {
            let width = 60u16;
            let mut terminal = Terminal::new(TestBackend::new(width, 40)).expect("test terminal");
            terminal
                .draw(|frame| {
                    let area = frame.area();
                    draw_trends(frame, area, app);
                })
                .expect("draw");
            terminal
                .backend()
                .buffer()
                .content()
                .chunks(width as usize)
                .map(|row| row.iter().map(|c| c.symbol()).collect::<String>())
                .collect()
        };

        let rows_with = render_trends_rows(&app_with);
        let rows_without = render_trends_rows(&app_without);

        /* Row 0 is the panel's top border; the original graph's content rows
        start at row 1 and run for TREND_ROWS + trends.len() - 1 rows (trends
        here has 2 entries: the sparkline plus "today 1M/hr"). */
        let content_rows = TREND_ROWS + 2 - 1;
        for i in 1..=content_rows {
            assert_eq!(
                rows_with[i], rows_without[i],
                "row {} of the original bar chart changed when cum_trend was added", i
            );
        }
        assert!(
            rows_with[content_rows + 1].contains("window usage"),
            "the new cum_trend graph label is missing"
        );
        assert!(
            !rows_without[content_rows + 1].contains("window usage"),
            "the label appeared even though cum_trend is absent"
        );

        assert!(
            trends_panel_height(&app_with) > trends_panel_height(&app_without),
            "a second graph must grow the panel, never shrink or leave it unchanged"
        );
    }

    #[test]
    fn cum_trend_absent_is_a_true_no_op_on_render_and_layout() {
        /* Regression guard: the pre-existing formula and rendering must be exactly
        what they were before this change whenever cum_trend never shows up. */
        let wire_without = r#"{"trends":["▁█","today 1M/hr"]}"#;
        let app_without = sessions_app(wire_without);
        let text = buffer_text(&app_without, 60, 30);
        assert!(!text.contains("window usage"), "cum_trend label leaked in with no cum_trend data");
        let trends_len = 2; /* the two rows in wire_without's "trends" array */
        assert_eq!(
            trends_panel_height(&app_without),
            (TREND_ROWS + trends_len - 1 + 2) as u16,
            "absent cum_trend must be a true no-op on the pre-existing height formula"
        );
    }

    fn sessions_app(wire: &str) -> App {
        let mut app = App::new(Source::Fixture(wire.as_bytes().to_vec()));
        app.refresh();
        app
    }

    const THREE_SESSIONS: &str = r#"{"sessions":[
        {"id":"a","dir":"~/alpha","status":"running","pane":"%1"},
        {"id":"b","dir":"~/bravo","status":"waiting","pane":"%2"},
        {"id":"c","dir":"~/charlie","status":"done","pane":"%3"}]}"#;

    #[test]
    fn the_first_row_is_selected_as_soon_as_sessions_arrive() {
        /* Requiring an arrow press to bootstrap a selection would make Enter
        do nothing on a freshly opened dashboard. */
        let app = sessions_app(THREE_SESSIONS);
        assert_eq!(app.selected_index(), Some(0));
        /* Row 0 is the waiting session: display order is by status rank. */
        assert_eq!(app.ordered_sessions()[0].dir, "~/bravo");
    }

    #[test]
    fn arrows_move_the_selection_and_clamp_at_both_ends() {
        let mut app = sessions_app(THREE_SESSIONS);
        assert!(handle_key(&mut app, KeyCode::Down));
        assert_eq!(app.selected_index(), Some(1));
        assert!(handle_key(&mut app, KeyCode::Char('j')));
        assert_eq!(app.selected_index(), Some(2));
        /* Clamp, never wrap: a held arrow should rest at the edge. */
        handle_key(&mut app, KeyCode::Down);
        handle_key(&mut app, KeyCode::Down);
        assert_eq!(app.selected_index(), Some(2));
        for _ in 0..10 {
            handle_key(&mut app, KeyCode::Up);
        }
        assert_eq!(app.selected_index(), Some(0));
    }

    #[test]
    fn q_quits_and_navigation_keys_do_not() {
        let mut app = sessions_app(THREE_SESSIONS);
        assert!(!handle_key(&mut app, KeyCode::Char('q')), "q must quit");
        assert!(handle_key(&mut app, KeyCode::Down));
        /* Enter leaves only on an ACCEPTED focus. A fixture source never dials a
        daemon, so the app must stay up with its note rather than vanishing --
        same contract as a focus the daemon refuses. */
        assert!(handle_key(&mut app, KeyCode::Enter));
    }

    #[test]
    fn the_selection_follows_its_session_when_a_refresh_reorders_the_list() {
        /*
        The reason selection is keyed by identity and not by row index. Here
        the selected session changes status, which moves it from the last row
        to the first. An index-based cursor would stay on row 2 and quietly
        point at a different session -- so Enter would focus the wrong window.
        */
        let mut app = sessions_app(THREE_SESSIONS);
        handle_key(&mut app, KeyCode::End);
        assert_eq!(app.ordered_sessions()[app.selected_index().unwrap()].id, "c");

        app.source = Source::Fixture(
            br#"{"sessions":[
                {"id":"a","dir":"~/alpha","status":"done","pane":"%1"},
                {"id":"b","dir":"~/bravo","status":"done","pane":"%2"},
                {"id":"c","dir":"~/charlie","status":"waiting","pane":"%3"}]}"#
                .to_vec(),
        );
        app.refresh();
        assert_eq!(app.selected_index(), Some(0), "selection did not follow the session");
        assert_eq!(app.ordered_sessions()[0].id, "c", "still the same session");
    }

    #[test]
    fn a_selection_whose_session_ended_falls_back_to_the_first_row() {
        let mut app = sessions_app(THREE_SESSIONS);
        handle_key(&mut app, KeyCode::End);
        app.source = Source::Fixture(
            br#"{"sessions":[{"id":"a","dir":"~/alpha","status":"running","pane":"%1"}]}"#.to_vec(),
        );
        app.refresh();
        assert_eq!(app.selected_index(), Some(0));

        /* And an empty list leaves nothing selected rather than a dangling key. */
        app.source = Source::Fixture(br#"{"sessions":[]}"#.to_vec());
        app.refresh();
        assert_eq!(app.selected, None);
        assert_eq!(app.selected_index(), None);
    }

    #[test]
    fn enter_on_an_unfocusable_session_reports_instead_of_dialling() {
        /* Same refusal as the Python client: no pane and not Zed. */
        let mut app = sessions_app(
            r#"{"sessions":[{"id":"a","dir":"~/x","status":"running","pane":"","term":"ghostty"}]}"#,
        );
        handle_key(&mut app, KeyCode::Enter);
        let note = app.live_note().expect("a note explaining why nothing happened");
        assert!(note.contains("no focusable"), "got {:?}", note);
    }

    #[test]
    fn enter_with_no_sessions_is_a_no_op_not_a_panic() {
        let mut app = sessions_app(r#"{"sessions":[]}"#);
        assert!(handle_key(&mut app, KeyCode::Enter));
        assert!(handle_key(&mut app, KeyCode::Down));
        assert_eq!(app.selected, None);
    }

    #[test]
    fn stable_key_uses_the_raw_id_not_the_sanitized_display_string() {
        /*
        Regression for keying on the sanitized display id: sanitize_display
        collapses any complete terminal control sequence to one '?' marker, so
        "a<ESC>[2Jsame" and "a<ESC>[31msame" used to both sanitize to "a?same" --
        stable_key(a) == stable_key(b) then made selected_index's `position` always
        resolve to the first of the two, so the second session could never be
        selected. Session::id is now kept raw (identity-only, never rendered), so
        two daemon-distinct ids stay distinct keys.
        */
        let wire = "{\"sessions\":[\
            {\"id\":\"a\\u001b[2Jsame\",\"dir\":\"~/one\",\"status\":\"running\",\"pane\":\"%1\"},\
            {\"id\":\"a\\u001b[31msame\",\"dir\":\"~/two\",\"status\":\"running\",\"pane\":\"%2\"}]}";
        let app = sessions_app(wire);
        let keys: Vec<String> = app.ordered_sessions().iter().map(|s| stable_key(s)).collect();
        assert_eq!(keys.len(), 2);
        assert_ne!(keys[0], keys[1], "two distinct daemon ids collapsed onto the same stable_key");
    }

    #[test]
    fn a_focus_attempt_never_disturbs_snapshot_state() {
        /*
        D-07 as a test: a focus failure is action-scoped. If it could mark the
        frame stale, a dead pane would make the quota gauges dim for no reason.
        */
        let mut app = sessions_app(THREE_SESSIONS);
        let before = app.snapshot.clone();
        app.source = Source::Daemon(Box::new(Client::with_path("/nonexistent/focus-test.sock")));
        handle_key(&mut app, KeyCode::Enter);
        assert_eq!(app.snapshot, before, "focus mutated the snapshot");
        assert!(app.error.is_none(), "focus failure leaked into the fetch error state");
        assert!(!app.stale(), "focus failure marked the frame stale");
        assert!(app.live_note().is_some(), "focus failure was silent");
    }

    #[test]
    fn the_selected_row_is_visible_and_marked_on_screen() {
        let mut app = sessions_app(THREE_SESSIONS);
        handle_key(&mut app, KeyCode::Down);
        let mut terminal = Terminal::new(TestBackend::new(100, 30)).expect("test terminal");
        terminal.draw(|frame| draw(frame, &app)).expect("draw");
        let buffer = terminal.backend().buffer().clone();
        let screen: String = buffer.content().iter().map(|c| c.symbol()).collect();
        assert!(screen.contains("> "), "no cursor marker on screen");
        /* REVERSED, not a fixed background: legible on any terminal theme. */
        assert!(
            buffer.content().iter().any(|c| c.modifier.contains(Modifier::REVERSED)),
            "the selected row is not highlighted"
        );
    }

    #[test]
    fn the_footer_advertises_navigation_and_yields_to_a_focus_note() {
        let mut app = sessions_app(THREE_SESSIONS);
        let screen = |app: &App| {
            let mut terminal = Terminal::new(TestBackend::new(100, 30)).expect("test terminal");
            terminal.draw(|frame| draw(frame, app)).expect("draw");
            terminal
                .backend()
                .buffer()
                .content()
                .iter()
                .map(|c| c.symbol())
                .collect::<String>()
        };
        let idle = screen(&app);
        assert!(idle.contains("enter") && idle.contains("quit"), "bindings not advertised");
        app.note("focusing ~/alpha");
        assert!(screen(&app).contains("focusing"), "the focus note did not reach the footer");
    }

    #[test]
    fn a_narrow_terminal_drops_the_heatmap_instead_of_wrapping_it() {
        /* Wrapped, the heatmap is noise that displaces the trend graph.

        Deliberately NOT the valid-full fixture: its grid is all-null, so
        heatmap_levels correctly returns no data and nothing is drawn at any
        width. This needs a fixture with a populated cell AND trend rows -- the
        heatmap only renders beside a graph. */
        let path = corpus()
            .into_iter()
            .find(|p| p.to_string_lossy().contains("heatmap-and-trends-populated"))
            .expect("heatmap-and-trends-populated fixture");
        let app = app_for(&path);

        let rendered = |w: u16| {
            let mut terminal = Terminal::new(TestBackend::new(w, 40)).expect("test terminal");
            terminal.draw(|frame| draw(frame, &app)).expect("draw");
            terminal
                .backend()
                .buffer()
                .content()
                .iter()
                .map(|c| c.symbol())
                .collect::<String>()
        };
        /* Count day labels rather than looking for one: a weekly projection
        renders a single weekday too ("proj 15% @Mon 18:06"), so `contains("Mon")`
        is satisfied by a screen with no heatmap on it at all. Only the heatmap
        puts all seven on screen at once. */
        let day_labels = |w: u16| {
            let screen = rendered(w);
            HEAT_DAYS.iter().filter(|d| screen.contains(**d)).count()
        };
        assert_eq!(day_labels(120), HEAT_DAYS.len(), "a wide terminal should show the heatmap");
        assert!(day_labels(50) < HEAT_DAYS.len(), "a narrow terminal should drop the heatmap");
    }
}
