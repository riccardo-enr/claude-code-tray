# Archived: the Python terminal dashboard

Superseded by the Rust `claude-tui` (see `../rust/`), which is now the installed
default. These files are kept rather than deleted because they were the
behavioural and visual reference the Rust implementation was built against, and
because restoring them is a two-line change if the rewrite turns out to have
missed something.

| File               | What it was                                                    |
| ------------------ | -------------------------------------------------------------- |
| `claude-tui.py`    | The Textual TUI. A PEP 723 script — `uv` resolved `textual` on first run, so it needed no venv. |
| `claude-tui.py.lock` | `uv`'s exact pin for that inline dependency block.            |
| `test_tui.py`      | Interaction-level checks, driven through Textual's test harness. |

Nothing else imports these. They were removed from `install.sh`, the `justfile`
and `pyproject.toml`'s optional `tui` extra at the same time.

## What did NOT move

`claude_monitor/core.py` keeps every formatter and quantizer these files used —
`tui_usage_rows`, `band`, `gauge_fill`, `spark_levels`, `heatmap_levels`,
`sess_rows`, `fmt_elapsed` and the rest. That is deliberate:

- They are asserted by `claude_monitor/test_claude_monitor.py`, which is what
  `just selfcheck` runs. Removing them would quietly shrink the verification
  gate.
- The Rust `format` module mirrors them function for function and cites them by
  name in its `change both` comments. They are the reference those claims point
  at; deleting them would turn a checkable parity contract into a memory.

So the Python side still holds the definition of what every number means. What
was archived is the *application* that drew them, not the arithmetic.

## Restoring

```sh
git mv archive/claude-tui.py archive/claude-tui.py.lock .
git mv archive/test_tui.py claude_monitor/
```

Then re-add the `tui = ["textual>=8,<9"]` optional dependency to
`pyproject.toml`, and a recipe to run `./claude-tui.py`. It talks to the same
unchanged socket verb, so it will work against the current daemon as-is.
