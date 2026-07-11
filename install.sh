#!/usr/bin/env bash
# Install claude-code-tray: copy the helper + sender into ~/.claude/hooks,
# register the autostart entry, and print the hook config to merge into
# ~/.claude/settings.json.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
HOOKS="$HOME/.claude/hooks"
AUTOSTART="$HOME/.config/autostart"

mkdir -p "$HOOKS" "$AUTOSTART"
install -m 0755 "$SRC/claude-monitor.py" "$HOOKS/claude-monitor.py"
install -m 0755 "$SRC/claude-send.py"    "$HOOKS/claude-send.py"

cat > "$AUTOSTART/claude-monitor.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Claude Code Monitor
Comment=Tray indicator and click-to-focus for Claude Code sessions
Exec=python3 $HOOKS/claude-monitor.py
Icon=claude-desktop
X-GNOME-Autostart-enabled=true
NoDisplay=true
EOF

echo "Installed:"
echo "  $HOOKS/claude-monitor.py"
echo "  $HOOKS/claude-send.py"
echo "  $AUTOSTART/claude-monitor.desktop"
echo
echo "Now merge these into the \"hooks\" object in ~/.claude/settings.json:"
echo
cat "$SRC/settings.hooks.json"
echo
echo "Start it now without logging out:"
echo "  setsid python3 $HOOKS/claude-monitor.py >/tmp/claude-monitor.log 2>&1 < /dev/null &"
