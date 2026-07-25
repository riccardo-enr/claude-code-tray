# claude-code-tray -- task runner
#
# Run a recipe with `just <name>`, or via overseer.nvim (it auto-discovers just
# recipes). The tray is a GNOME GUI daemon, so run these from inside your desktop
# session (an interactive shell or overseer.nvim) so DISPLAY / DBUS are inherited.

# Deployed entry: a symlink -> this repo's claude-monitor.py; what gnome-session launches.
entry := env_var('HOME') / ".claude/hooks/claude-monitor.py"
dash  := env_var_or_default('XDG_CACHE_HOME', env_var('HOME') / ".cache") / "claude-tray/dashboard.html"

# List recipes.
default:
    @just --list

# Restart the tray (kill + relaunch detached). Run after any code change -- no hot-reload.
restart:
    -pkill -f claude-monitor.py
    sleep 1
    setsid -f /usr/bin/python3 {{entry}}
    @echo "tray restarted"

# Start the tray daemon (detached).
start:
    setsid -f /usr/bin/python3 {{entry}}
    @echo "tray started"

# Stop the tray daemon.
stop:
    -pkill -f claude-monitor.py
    @echo "tray stopped"

# Show the tray PID (or "not running").
status:
    @pgrep -af claude-monitor.py || echo "not running"

# Run the assert-based self-check suite -- the GSD verification gate; keep it green.
selfcheck:
    python3 {{entry}} --selfcheck

# Lint (ruff, scoped by pyproject.toml).
lint:
    ruff check .

# Open the generated dashboard in the browser.
dashboard:
    xdg-open "{{dash}}"

# --- terminal dashboard (Rust) --------------------------------------------
# Talks to the same daemon socket as the tray. The Python TUI it replaced is in
# archive/; see archive/README.md.

# Open the terminal dashboard from the build tree (needs a real TTY).
rust-tui:
    cd rust && cargo run --release --quiet

# Open the installed dashboard in a tmux popup (needs tmux 3.2+, inside tmux).
popup:
    #!/usr/bin/env bash
    set -euo pipefail
    command -v tmux >/dev/null || { echo "tmux is not installed"; exit 1; }
    tmux has-session 2>/dev/null || { echo "no tmux server running -- start tmux first"; exit 1; }
    command -v claude-tui >/dev/null || {
      echo "claude-tui is not on PATH -- run ./install.sh, and make sure ~/.local/bin is on PATH"
      exit 1
    }
    # -E closes the popup when the command exits, so `q` dismisses it.
    tmux popup -E -w 90% -h 85% -T " claude-tui " claude-tui

# Build and install everything, including the Rust dashboard as the default.
install:
    ./install.sh

# Run the Rust test suite -- the verification gate for the Rust client.
rust-test:
    cd rust && cargo test --quiet

# Lint the Rust crate.
rust-lint:
    cd rust && cargo clippy --all-targets -- -D warnings

# Render one fixture instead of the live daemon: `just rust-fixture partial-sections`.
rust-fixture name *args:
    cd rust && cargo run --release --quiet -- --fixture ../fixtures/snapshot/{{name}}.json {{args}}

# Dump every fixture through the real renderer. Quick eyeball over all states.
rust-states:
    #!/usr/bin/env bash
    for f in fixtures/snapshot/*.json; do
      echo "### $(basename "$f" .json)"
      ./rust/target/release/claude-tui --fixture "$f" --once
      echo
    done

# Both verification gates in one shot.
check: selfcheck rust-test
