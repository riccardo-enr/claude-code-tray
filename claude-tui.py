#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["textual>=8,<9"]
# ///
"""Terminal dashboard for claude-code-tray -- the third consumer of claude_monitor.core.

This is the ONLY file in the repo that imports textual, and the boundary runs both
ways. Nothing importable by /usr/bin/python3 may import it: that interpreter is PEP 668
externally-managed, it is the one `just selfcheck`, `just start` and `just restart` run
on, and it must never gain textual. Runtime resolution happens in uv's own environment
via the PEP 723 block above, so the daemon's interpreter never sees the dependency.
`uv run --script` resolves that block against the committed claude-tui.py.lock (regenerate
with `uv lock --script claude-tui.py`), which pins the full transitive set with hashes --
the T-09-SC supply-chain mitigation, in force for the interpreter that actually runs here.

The consequence is a rule rather than a preference: anything worth asserting belongs in
claude_monitor.core, where --selfcheck can prove it. What is left here is layout, CSS,
two timers, one thread worker and the degraded-mode presentation -- none of which a
unit test on that interpreter can reach. Every string rendered below was already
formatted by core; this file adds no formatting logic of its own.

The daemon's read-only snapshot socket verb, reached through core.query_snapshot, is the
only data source (D-04). No file is read, no process is spawned, no trend is recomputed,
and the snapshot query is the only message ever written to the socket.
"""

import time

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, Static


from claude_monitor import core

# Width in cells of a usage gauge bar (TUI-07). Render-only: the fill-cell count is
# core.gauge_fill(pct, GAUGE_WIDTH), the glyphs/colors are applied below.
GAUGE_WIDTH = 20


class ClaudeTui(App):
    """The whole application: three stacked panels, two timers, one socket worker.

    Panel order is fixed and there is no navigation (D-01) -- the screen is glanceable
    like the tray menu. The usage and trends blocks size to their content; the sessions
    table absorbs whatever is left and scrolls internally.
    """

    TITLE = "claude-tui"

    CSS = """
    Screen { layout: vertical; }

    #body { height: 1fr; }

    /* D-10's dimming. `opacity` is declared FractionalProperty(children=True) in
       textual 8.2.8 and multiplies down the ancestor chain; `text-opacity` is not,
       so it would leave the three panels inside #body at full brightness. */
    #body.stale { opacity: 60%; }

    #usage    { height: auto; padding: 0 1; border-bottom: solid $panel; }
    #trends   { height: auto; padding: 0 1; border-bottom: solid $panel; }
    #sessions { height: 1fr; }

    /* Sibling of #body, never inside it, so the cold-start message is never dimmed. */
    #coldstart { display: none; height: 1fr; content-align: center middle; }
    """

    # D-02: exactly one binding, and no theme toggle. ENABLE_COMMAND_PALETTE defaults to
    # True, which binds ctrl+p and advertises it in the Footer, exposing action_change_theme
    # (the theme toggle D-02 rejected); switch it off so "q" is genuinely the only binding.
    ENABLE_COMMAND_PALETTE = False
    # Footer() renders this table itself, so the footer needs no code.
    BINDINGS = [("q", "quit", "quit")]

    # The bound snapshot being None is exactly the D-11 cold-start predicate.
    snapshot: dict | None = None
    last_ok: float | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="body"):
            yield Static(id="usage", markup=False)
            yield Static(id="trends", markup=False)
            yield DataTable(id="sessions")
        yield Static(id="coldstart", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        """Columns once, both timers, and one immediate fetch so frame 1 is not blank."""
        # Inherit the host terminal's palette (e.g. Ghostty/Catppuccin) instead of
        # textual's fixed dark theme: ansi-dark renders through the terminal's own 16
        # ANSI colors + default fg/bg, so the TUI matches whatever the terminal is themed
        # with and follows any later change. ponytail: 16-color only, so #body.stale's
        # opacity dim has no RGB to blend and reads flatter -- acceptable for a mode signal.
        self.theme = "ansi-dark"
        table = self.query_one("#sessions", DataTable)
        table.cursor_type = "none"  # D-01: nothing here is navigable
        table.add_columns("status", "project", "time")
        self.sub_title = "connecting..."
        self.set_interval(core.TUI_FETCH_INTERVAL, self.fetch)  # D-08
        self.set_interval(core.TUI_TICK_INTERVAL, self.tick)  # D-09
        self.fetch()

    @work(thread=True, exclusive=True, exit_on_error=False)
    def fetch(self) -> None:
        """Query the daemon off the event loop; a failure is a state change, not a raise.

        core.query_snapshot raises on every failure mode by design, and both textual
        doors out of a failed callback lead to app exit: @work defaults to
        exit_on_error=True, and App._handle_exception is documented "Always results in
        the app exiting". Both are closed here and neither is redundant -- the decorator
        closes the worker door, the blanket except closes the callback door.

        A thread worker must never touch a widget directly, so every mutation is
        marshaled back onto the event loop with call_from_thread.
        """
        # ponytail: blanket except, the same posture poll_loop / serve / _handle_conn
        # already use. D-12's contract is retry forever on the same interval -- no
        # backoff, no failure cap, no exit -- so there is nothing to add here.
        try:
            snap = core.query_snapshot()
            self.call_from_thread(self.apply_snapshot, snap)
        except Exception:
            self.call_from_thread(self.mark_stale)

    def apply_snapshot(self, snap) -> None:
        """Bind a fresh snapshot, clear any stale presentation, re-render.

        The two rebinds are single assignments, which is what makes a 1s render tick
        landing on the same beat safe: it observes either the whole old snapshot or the
        whole new one, never a half-applied one.

        The render goes through tick(), not render_all() directly, so a render-time
        exception is caught by the same guard the 1s tick uses and surfaced as
        "render error", not routed to the worker's except and mislabelled "daemon
        unreachable" while the daemon is healthy (WR-03). The "live" header is committed
        only after that render succeeds, so a partial failure never leaves new state under
        a "live" header.
        """
        self.snapshot = snap
        self.last_ok = time.time()
        self.query_one("#coldstart").display = False
        body = self.query_one("#body")
        body.display = True
        body.set_class(False, "stale")
        self.tick()  # renders under the same guard as the 1s tick
        if self.sub_title != "render error -- frame may be stale":
            self.sub_title = "live"

    def mark_stale(self) -> None:
        """Degraded presentation: D-11 on a cold start, D-10 once data has been seen."""
        cold = self.query_one("#coldstart", Static)
        body = self.query_one("#body")
        if self.snapshot is None:
            # D-11: never reached the daemon. One centered message, never a traceback.
            body.display = False
            cold.display = True
            cold.update("claude-monitor is not running.\n\nStart it with:  just start")
            self.sub_title = "daemon unreachable"
            return
        # D-10: keep the last good data on screen, dim it, and say so in the one place
        # freshness is communicated -- stale data under a live header would be a lie.
        body.set_class(True, "stale")
        self.sub_title = "daemon unreachable -- last update %s" % time.strftime(
            "%H:%M:%S", time.localtime(self.last_ok)
        )
        # D-12: nothing is scheduled and nothing is counted; the 2s timer comes round
        # again on its own, and the next success clears the class silently.

    def tick(self) -> None:
        """The 1s local re-render (D-09), so a running session's counter advances."""
        try:
            self.render_all()
        except Exception:
            # This callback runs under Timer._tick too, so an unguarded raise exits the
            # app. Not a silent swallow: a frozen frame under a live header clock is the
            # stale-presented-as-live failure the header exists to prevent.
            self.sub_title = "render error -- frame may be stale"

    def _gauge(self, pct) -> Text:
        """A GAUGE_WIDTH-cell gradient meter Text (TUI-07, D-03): cells below the fill
        count are a filled block colored by their POSITION along the bar
        (core.band(cell/width*100)), so the bar always sweeps green->yellow->red like
        btop's meter; the rest are a dim empty track. Fill count is core.gauge_fill --
        this applies only glyphs and per-cell colors (D-04)."""
        n = core.gauge_fill(pct, GAUGE_WIDTH)
        bar = Text()
        for i in range(GAUGE_WIDTH):
            if i < n:
                bar.append("█", style=core.band(i / GAUGE_WIDTH * 100))  # full block
            else:
                bar.append("░", style="dim")  # light-shade empty track
        return bar

    def _cap_row_text(self, row, pct) -> Text:
        """Band-color a pre-formatted tui_usage_rows string by its cap's proximity band
        (D-02): the %, reset-countdown and burn segments take the band color, the cap
        label and any token-count segment stay default. Reformats nothing (D-05) -- the
        cells are split back out of the string core.tui_usage_rows already produced."""
        b = core.band(pct)
        t = Text()
        for i, cell in enumerate(row.split("  ")):
            if i:
                t.append("  ")
            colored = i == 1 or cell.startswith(("resets", "week resets", "burn:"))
            t.append(cell, style=b if colored else "")
        return t

    def _usage_renderable(self, usage, now) -> Text:
        """The #usage panel as a rich Text (the Static is markup=False, so a Text
        renderable is the correct no-markup-parse path). Every displayed number still
        comes from core.tui_usage_rows (D-05); this applies only band colors and gauge
        glyphs -- no new formatter. Each present cap renders as one line: its gradient
        gauge (the headline visual, D-03) followed by the band-colored row text (D-02).
        """
        rows = core.tui_usage_rows(usage, now)
        if usage is None or rows == ["usage unavailable"]:
            return Text("\n".join(rows))
        # rows[0] is always the 5h cap, rows[1] (when present) the 7d cap; pair each with
        # the percent core banded on. used_percentage is non-None here (else the guard
        # above caught it); seven_day_pct is non-None whenever the 7d row exists.
        pcts = [usage["used_percentage"]]
        if len(rows) > 1:
            pcts.append(usage["seven_day_pct"])
        out = Text()
        for i, row in enumerate(rows):
            if i:
                out.append("\n")
            out.append_text(self._gauge(pcts[i]))
            out.append("  ")
            out.append_text(self._cap_row_text(row, pcts[i]))
        return out

    def render_all(self) -> None:
        """Push every panel from the bound snapshot. Formats nothing itself."""
        snap = self.snapshot
        if snap is None:
            return
        now = time.time()
        self.query_one("#usage", Static).update(
            self._usage_renderable(snap.get("usage"), now)  # TUI-01 / TUI-06 / TUI-07
        )
        self.query_one("#trends", Static).update(core.trend_text(snap.get("trends")))
        table = self.query_one("#sessions", DataTable)
        scroll_y = table.scroll_y  # DataTable.clear() zeroes scroll_x/scroll_y (8.2.8)
        table.clear()  # keeps the column definitions
        for status, proj, elapsed in core.sess_rows(snap.get("sessions") or [], now):
            # Every cell is a rich Text, never a str: DataTable runs a str cell through
            # Text.from_markup with no per-widget opt-out, so a project directory named
            # [bold]x is injection and one named [/] raises MarkupError inside a timer
            # callback -- which exits the app. A Text instance takes the renderable
            # passthrough branch and never reaches the markup parser. Same mitigation
            # shape as the v1.3 Pango body and the v1.4 dashboard's textContent panel.
            table.add_row(Text(status), Text(proj), Text(elapsed))
        # D-01: the 1s rebuild must not steal the scroll the user set; clear() zeroed it
        # above, so restore it. validate_scroll_y re-clamps if the session list shrank.
        table.scroll_y = scroll_y


if __name__ == "__main__":
    ClaudeTui().run()
