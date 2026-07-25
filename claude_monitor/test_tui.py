#!/usr/bin/env python3
"""Headless interaction checks for the Textual TUI."""

import asyncio
import importlib.util
import pathlib

from rich.console import Console
from rich.table import Table


def _load_tui():
    path = pathlib.Path(__file__).resolve().parent.parent / "claude-tui.py"
    spec = importlib.util.spec_from_file_location("_claude_tui", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def demo():
    tui = _load_tui()
    snapshot = {
        "usage": None,
        "trends": None,
        "heatmap": None,
        "sessions": [
            {
                "id": f"sid-{index}",
                "dir": f"project-{index}",
                "status": "running",
                "entered": 100.0,
                "frozen": None,
                "pane": f"%{index}",
                "tmux": "/tmp/tmux",
                "term": "ghostty",
            }
            for index in range(3)
        ],
    }
    tui.core.query_snapshot = lambda: snapshot

    app = tui.ClaudeTui()
    heatmap = app._heatmap_renderable([[1.0] * 24 for _ in range(7)])
    heatmap_table = Table.grid(expand=True, padding=0)
    heatmap_table.add_column(justify="right", no_wrap=True)
    heatmap_table.add_row(heatmap)
    console = Console(width=60, color_system=None)
    with console.capture() as capture:
        console.print(heatmap_table)
    heatmap_lines = capture.get().splitlines()
    assert heatmap_lines[0].index("00") == heatmap_lines[1].index("██")

    reset5 = 1_000_000
    now5 = reset5 - tui.core.WIN5 // 2
    normal5 = app._projection_text(10.0, reset5, tui.core.WIN5, now5)
    assert normal5.plain == f"proj 20% @{tui.core.hhmm(reset5)}"
    exhaust5 = tui.core.project(60.0, reset5, tui.core.WIN5, now5)["exhaust"]
    assert app._projection_text(60.0, reset5, tui.core.WIN5, now5).plain == (
        "out ~%s" % tui.core.hhmm(exhaust5)
    )

    reset7 = 2_000_000
    now7 = reset7 - tui.core.WIN7 // 2
    normal7 = app._projection_text(10.0, reset7, tui.core.WIN7, now7)
    assert normal7.plain == f"proj 20% @{tui.core.weekday_hhmm(reset7)}"
    exhaust7 = tui.core.project(60.0, reset7, tui.core.WIN7, now7)["exhaust"]
    assert app._projection_text(60.0, reset7, tui.core.WIN7, now7).plain == (
        "out ~%s" % tui.core.weekday_hhmm(exhaust7)
    )

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        table = app.query_one("#sessions", tui.SessionTable)
        table.focus()
        await pilot.press("down")
        await pilot.pause()

        before = table.coordinate_to_cell_key(table.cursor_coordinate)[0].value
        assert (table.cursor_row, before) == (1, "sid-1")

        app.tick()

        after = table.coordinate_to_cell_key(table.cursor_coordinate)[0].value
        assert (table.cursor_row, after) == (1, "sid-1")


if __name__ == "__main__":
    asyncio.run(demo())
    print("ok")
