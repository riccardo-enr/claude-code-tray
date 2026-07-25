#!/usr/bin/env bash
# Install claude-code-tray: copy the helper + sender into ~/.claude/hooks,
# build and install the terminal dashboard, register the autostart entry, and
# print the hook config to merge into ~/.claude/settings.json.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
HOOKS="$HOME/.claude/hooks"
AUTOSTART="$HOME/.config/autostart"
BIN="$HOME/.local/bin"

mkdir -p "$HOOKS" "$AUTOSTART"
ln -sf "$SRC/claude-monitor.py" "$HOOKS/claude-monitor.py"
ln -sf "$SRC/claude-send.py"    "$HOOKS/claude-send.py"
ln -sf "$SRC/claude-status.py"  "$HOOKS/claude-status.py"

# --- tmux status-bar segment -------------------------------------------------
#
# Only installed when a tmux-powerline segments directory already exists: this is
# an opt-in extra for people who run that plugin, and creating the directory here
# would leave a stray segment in the config of everyone who does not.
TPL_SEGMENTS="${XDG_CONFIG_HOME:-$HOME/.config}/tmux-powerline/segments"
TMUX_SEGMENT_INSTALLED=""
if [ -d "$TPL_SEGMENTS" ]; then
  ln -sf "$SRC/tmux/claude_usage.sh" "$TPL_SEGMENTS/claude_usage.sh"
  TMUX_SEGMENT_INSTALLED="yes"
fi

# --- terminal dashboard ------------------------------------------------------
#
# `claude-tui` is a standalone Rust binary. The Python/Textual TUI it replaced is
# in archive/ and is no longer installed; see archive/README.md.
#
# There is deliberately no fallback. A machine without cargo gets no dashboard
# and is told why, rather than getting a different program under the same name --
# "claude-tui" must mean one thing everywhere.
#
# The daemon install above is untouched by any of this. The dashboard is a client
# of the daemon socket, so a missing dashboard costs you a view, never the tray.
TUI_INSTALLED=""
TUI_NOTE=""

if [ ! -d "$BIN" ]; then
  TUI_NOTE="$BIN does not exist -- skipping the terminal dashboard."
elif ! command -v cargo >/dev/null 2>&1; then
  TUI_NOTE="no cargo on PATH -- skipping the terminal dashboard."
else
  echo "Building the terminal dashboard (first build takes a minute)..."
  # --locked so an install reproduces the committed dependency versions rather
  # than silently resolving newer ones.
  if cargo build --release --locked --manifest-path "$SRC/rust/Cargo.toml"; then
    # Copied, not symlinked: a binary is a build artifact, and `cargo clean` must
    # not uninstall the user's tool. Re-run this script after changing the source.
    install -m 0755 "$SRC/rust/target/release/claude-tui" "$BIN/claude-tui"
    TUI_INSTALLED="yes"
  else
    TUI_NOTE="the Rust build FAILED -- no dashboard was installed."
  fi
fi

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

echo
echo "Installed:"
echo "  $HOOKS/claude-monitor.py"
echo "  $HOOKS/claude-send.py"
echo "  $HOOKS/claude-status.py"
echo "  $AUTOSTART/claude-monitor.desktop"
if [ -n "$TMUX_SEGMENT_INSTALLED" ]; then
  echo "  $TPL_SEGMENTS/claude_usage.sh   (tmux-powerline segment)"
fi
if [ -n "$TUI_INSTALLED" ]; then
  echo "  $BIN/claude-tui      (terminal dashboard)"
fi

if [ -n "$TUI_NOTE" ]; then
  echo
  echo "  NOTE: $TUI_NOTE"
  echo "        The tray itself is installed and works. For the dashboard,"
  echo "        install a Rust toolchain (https://rustup.rs) and re-run this script."
fi

if [ -n "$TUI_INSTALLED" ] && ! command -v claude-tui >/dev/null 2>&1; then
  echo
  echo "  NOTE: $BIN is not on your PATH, so 'claude-tui' will not resolve."
  echo "        Add it:  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

if [ -n "$TMUX_SEGMENT_INSTALLED" ]; then
  echo
  echo "To show usage on the tmux status line, add this segment to your theme's"
  echo "TMUX_POWERLINE_LEFT_STATUS_SEGMENTS array, then reload tmux:"
  echo "      \"claude_usage 238 189\"   (background then foreground; keep the bg dark)"
fi

echo
echo "Now merge these into the \"hooks\" object in ~/.claude/settings.json:"
echo
cat "$SRC/settings.hooks.json"
echo
echo "Start it now without logging out:"
echo "  setsid python3 $HOOKS/claude-monitor.py >/tmp/claude-monitor.log 2>&1 < /dev/null &"
echo
echo "Open the dashboard in a tmux popup (tmux 3.2+), from inside tmux:"
echo "  tmux popup -E -w 90% -h 85% -T ' claude-tui ' claude-tui"
echo
echo "To bind it to prefix + u, add this to ~/.tmux.conf:"
echo "  bind-key u popup -E -w 90% -h 85% -T ' claude-tui ' claude-tui"
