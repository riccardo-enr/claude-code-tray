/*
Typed, stable failure categories for the daemon client (D-05, D-08).

Every fallible boundary in this crate returns a `ClientError` carrying an
`ErrorCode` from a closed set. The codes are the contract: fixtures assert on
them, and the Phase 13 state machine will branch on them. Downstream code must
never have to parse an operating-system message or a library error chain to
decide what happened -- that is what collapsing failures into one boolean, or
into a stringly-typed `Box<dyn Error>`, would force.

`context` is deliberately narrow. It is built only from values that are safe to
put on a terminal: byte counts, field names, `io::ErrorKind` discriminants,
element indices. Raw payload text never reaches it. A hostile daemon (or a
hostile repository name that reached the daemon) must not be able to smuggle a
terminal escape sequence into a UI error line by way of a diagnostic -- that is
the same trust boundary `sanitize` defends, and an error path is the easiest
place to forget it.

Human wording is the renderer's job, not this crate's. `Display` here produces a
stable, machine-greppable `code: context` form for logs and test failures, not
UI copy.
*/

use std::fmt;
use std::io;

/* The closed set of failure categories. Stable: fixture files and later phases
name these strings, so a variant may be added but never silently renamed. */
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ErrorCode {
    /* Could not reach the daemon at all: no socket file, refused, broken pipe. */
    Transport,
    /* The whole-operation deadline elapsed. Distinct from Transport because a
    hung daemon and an absent daemon call for different UI wording and different
    retry behaviour. */
    Timeout,
    /* The response violated the wire framing: no newline before the size cap,
    or a payload larger than the configured limit. */
    Framing,
    /* The response line was not valid JSON. */
    Decode,
    /* The response was valid JSON but not the shape the contract requires --
    at the root level only. A malformed *section* does not produce this; it
    degrades that section to `Section::Malformed` and leaves siblings usable
    (D-02). */
    Schema,
    /* Reserved for the Phase 12/13 render layer so it can report a controlled
    failure through the same channel instead of panicking (D-05). */
    Render,
    /* A focus action failed. Action-scoped and nonfatal: it never marks
    snapshot data stale (D-07). */
    Focus,
}

impl ErrorCode {
    /* The stable wire/fixture spelling. */
    pub fn as_str(self) -> &'static str {
        match self {
            ErrorCode::Transport => "transport",
            ErrorCode::Timeout => "timeout",
            ErrorCode::Framing => "framing",
            ErrorCode::Decode => "decode",
            ErrorCode::Schema => "schema",
            ErrorCode::Render => "render",
            ErrorCode::Focus => "focus",
        }
    }

    /* Parse the stable spelling back. Used by the fixture harness so the corpus
    can name expected codes in plain text. */
    pub fn parse_code(s: &str) -> Option<ErrorCode> {
        match s {
            "transport" => Some(ErrorCode::Transport),
            "timeout" => Some(ErrorCode::Timeout),
            "framing" => Some(ErrorCode::Framing),
            "decode" => Some(ErrorCode::Decode),
            "schema" => Some(ErrorCode::Schema),
            "render" => Some(ErrorCode::Render),
            "focus" => Some(ErrorCode::Focus),
            _ => None,
        }
    }
}

impl fmt::Display for ErrorCode {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClientError {
    pub code: ErrorCode,
    /* Safe structured context. Never contains payload bytes. */
    pub context: String,
}

impl ClientError {
    pub fn new(code: ErrorCode, context: impl Into<String>) -> Self {
        ClientError { code: code.into_code(), context: context.into() }
    }

    pub fn transport(context: impl Into<String>) -> Self {
        ClientError { code: ErrorCode::Transport, context: context.into() }
    }

    pub fn timeout(context: impl Into<String>) -> Self {
        ClientError { code: ErrorCode::Timeout, context: context.into() }
    }

    pub fn framing(context: impl Into<String>) -> Self {
        ClientError { code: ErrorCode::Framing, context: context.into() }
    }

    pub fn decode(context: impl Into<String>) -> Self {
        ClientError { code: ErrorCode::Decode, context: context.into() }
    }

    pub fn schema(context: impl Into<String>) -> Self {
        ClientError { code: ErrorCode::Schema, context: context.into() }
    }

    pub fn focus(context: impl Into<String>) -> Self {
        ClientError { code: ErrorCode::Focus, context: context.into() }
    }

    /* Map an io::Error without letting its message escape.

    `ErrorKind` is a fixed Rust enum, so its Debug form is bounded and
    attacker-independent; `io::Error`'s Display is an OS string and is dropped
    on purpose (D-08). A timed-out or would-block read is Timeout, not
    Transport, so callers keep the "hung daemon" / "no daemon" distinction
    without string matching. */
    pub fn from_io(err: &io::Error, during: &str) -> Self {
        let code = match err.kind() {
            io::ErrorKind::TimedOut | io::ErrorKind::WouldBlock => ErrorCode::Timeout,
            _ => ErrorCode::Transport,
        };
        ClientError { code, context: format!("{} failed: {:?}", during, err.kind()) }
    }
}

/* Small helper so `ClientError::new` cannot be handed something that is not
already a code. Exists only to keep the constructor signature honest. */
trait IntoCode {
    fn into_code(self) -> ErrorCode;
}

impl IntoCode for ErrorCode {
    fn into_code(self) -> ErrorCode {
        self
    }
}

impl fmt::Display for ClientError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.code, self.context)
    }
}

impl std::error::Error for ClientError {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codes_round_trip_through_their_stable_spelling() {
        for code in [
            ErrorCode::Transport,
            ErrorCode::Timeout,
            ErrorCode::Framing,
            ErrorCode::Decode,
            ErrorCode::Schema,
            ErrorCode::Render,
            ErrorCode::Focus,
        ] {
            assert_eq!(ErrorCode::parse_code(code.as_str()), Some(code));
        }
        assert_eq!(ErrorCode::parse_code("nope"), None);
    }

    #[test]
    fn io_timeout_maps_to_timeout_not_transport() {
        let err = io::Error::new(io::ErrorKind::TimedOut, "connection timed out to /run/x.sock");
        let mapped = ClientError::from_io(&err, "connect");
        assert_eq!(mapped.code, ErrorCode::Timeout);
        /* The OS message must not survive into the context. */
        assert!(!mapped.context.contains("/run/x.sock"), "context leaked the io message");
    }

    #[test]
    fn io_not_found_maps_to_transport() {
        let err = io::Error::new(io::ErrorKind::NotFound, "no such file");
        assert_eq!(ClientError::from_io(&err, "connect").code, ErrorCode::Transport);
    }
}
