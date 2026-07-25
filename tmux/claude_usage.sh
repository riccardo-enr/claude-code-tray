# shellcheck shell=bash
#
# tmux-powerline segment: Claude Code quota on the left status line.
# Format: "CC 62% 2h14m" -- 5h usage percent and time until that window resets,
# with a peach/red tint and a trailing "!" once usage nears the cap.
#
# All the work happens in claude-status.py, which reads the already-running tray
# daemon (socket first, history file as fallback). This wrapper exists only because
# tmux-powerline requires a run_segment() in segments/*.sh; keep it dumb.
#
# The segment emits a #[range=user|claude_usage] marker, so a MouseDown1Status binding
# can open the claude-tui popup on click. That is open-ONLY, and deliberately so: do not
# try to make a second click close it. tmux's popup_key_cb() bounds-checks the pointer and
# returns 0 ("handled, do nothing") for any click outside the popup rect, before the key
# tables are consulted -- verified byte-identical in tmux 3.2 through 3.6, and confirmed
# by driving synthetic SGR mouse events at a real pty client. With -E, keyboard bindings
# do not fire from inside a popup either, and re-issuing display-popup while one is open
# is a silent no-op. No format exposes popup state, so config cannot branch on it.
# Closing is `q`, inside claude-tui.
#
# Install: ./install.sh symlinks this into ~/.config/tmux-powerline/segments/, then add
#   "claude_usage 238 189"
# to TMUX_POWERLINE_LEFT_STATUS_SEGMENTS in your theme. Those are background then
# foreground, in that order. Pick a DARK background: claude-status.py overrides the
# foreground with peach/red in the high bands, and those wash out on a light chip.

CLAUDE_STATUS_BIN="${CLAUDE_STATUS_BIN:-$HOME/.claude/hooks/claude-status.py}"

run_segment() {
	# Not installed -> hide the segment rather than reporting an error every 2 seconds.
	[ -x "$CLAUDE_STATUS_BIN" ] || return 1
	# Exits 1 without printing when there is no usage yet; that hides it too.
	"$CLAUDE_STATUS_BIN" 2>/dev/null || return 1
}
