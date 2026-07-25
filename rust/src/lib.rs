/*
`claude_tui` -- the Rust client foundation for the claude-code-tray daemon.

This crate is Phase 11 of the v2.0 Rust TUI milestone. It is deliberately
*only* the boundary: a bounded socket client, deterministic normalization,
sanitized display text, typed nonfatal failures, and the fixture corpus that
pins all of it. There is no terminal renderer here and no event loop -- those
are Phases 12 and 13, and keeping them out is what lets every rule below be
tested without a terminal or a running daemon.

The daemon is not modified by this crate and its wire contract is fixed
(RTUI-03). `claude-tui.py` remains the behavioural and visual oracle and is
never invoked from here.

Layering, outermost first:

    client   -- Unix socket transport, deadlines, size caps
    snapshot -- Value -> typed state, section independence, no coercion
    sanitize -- the display trust boundary
    error    -- the stable failure vocabulary shared by all three

The design property that makes "panic-free" (RTUI-12) structural rather than
aspirational: nothing above `snapshot` ever sees a `serde_json::Value`. By the
time a renderer holds a `Snapshot`, every field has already been type-checked,
every display string sanitized and bounded, and every failure turned into a
typed value. There is no unwrap left for a hostile payload to reach.
*/

/* The panic-free rule is enforced by the compiler in shipped code, not by
review. Tests are exempt: an assertion that cannot fail loudly is not a test. */
#![forbid(unsafe_code)]
#![cfg_attr(not(test), deny(clippy::unwrap_used, clippy::expect_used, clippy::panic))]

pub mod client;
pub mod error;
pub mod format;
pub mod sanitize;
pub mod snapshot;

pub use client::{default_socket_path, read_line, Client, DEFAULT_MAX_BYTES, DEFAULT_TIMEOUT};
pub use error::{ClientError, ErrorCode};
pub use sanitize::{sanitize_display, sanitize_display_bounded, MAX_DISPLAY_CHARS, REPLACEMENT};
pub use snapshot::{
    validate_focus, FocusTarget, Heatmap, Section, Session, Sessions, Snapshot, Usage,
    HEATMAP_COLS, HEATMAP_ROWS,
};
