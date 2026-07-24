#!/usr/bin/env python3
"""Headless interaction checks for the Textual TUI."""

import asyncio
import importlib.util
import pathlib


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
