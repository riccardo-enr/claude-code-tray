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

# Open the terminal dashboard (needs a real TTY -- textual drives the terminal directly).
tui:
    ./claude-tui.py
