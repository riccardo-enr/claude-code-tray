/*
The bounded Unix-socket transport.

The daemon's contract is fixed and this crate does not get to change it
(RTUI-03): one newline-terminated request line out, one newline-terminated
response line back, connection closed. No new verb, no new field, no
persistent connection. `claude-monitor.py::_handle_conn` is the authority and
is not modified by this phase.

Two bounds matter, and they are the ones `claude_monitor.core.read_line`
learned the hard way:

  - **A whole-operation deadline, not a per-recv timeout.** `set_read_timeout`
    bounds each individual `read`, so a peer dribbling one byte just under the
    timeout keeps the loop alive forever while the caller's 2-second refresh
    keeps firing -- a thread pile-up, not a hang. The deadline is checked on
    every iteration and covers connect, write and read together.

  - **A size cap.** A daemon that streams without ever sending a newline would
    otherwise grow the buffer until the process dies. Exceeding the cap is a
    `Framing` failure, which is a different thing from a `Timeout` and should
    read differently on screen.

EOF is not an error. A peer that closes mid-line returns whatever arrived, and
the JSON decoder then rejects it as `Decode` -- which is the honest
description. Treating EOF as a transport failure would report "cannot reach the
daemon" for a daemon we plainly did reach.

Concurrency, since RTUI-03 and RTUI-12 both raise it: `Client` holds no
connection and no mutable state. Every call opens its own socket and closes it
before returning, so calls are independent, `Client` is `Send + Sync`, and
concurrent or interrupted calls cannot corrupt each other. Nothing here mutates
caller state at all -- a failed fetch returns `Err` and leaves the caller's last
good snapshot untouched, because there is no path by which this module could
touch it (D-06). Phase 13 owns what to *show* after a failure; this module's
only obligation is not to destroy the evidence.
*/

use std::env;
use std::io::{ErrorKind, Read, Write};
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use crate::error::{ClientError, ErrorCode};
use crate::snapshot::{validate_focus, FocusTarget, Snapshot};

/* The exact request line the daemon's `"query"` branch matches on. Byte-for-byte
identical to `claude_monitor.core.query_snapshot`, including the space after the
colon -- the daemon parses JSON so the spacing is not semantically load-bearing,
but keeping it identical means a packet capture from either client is the same. */
const SNAPSHOT_REQUEST: &[u8] = b"{\"query\": \"snapshot\"}\n";

/* Whole-operation budget. Deliberately below the Python TUI's 2.0s refresh
interval so at most one fetch is ever in flight. */
pub const DEFAULT_TIMEOUT: Duration = Duration::from_millis(1500);

/* Response ceiling, matching read_line's 1 MiB. */
pub const DEFAULT_MAX_BYTES: usize = 1 << 20;

/* Per-read slice. Small enough that the deadline is checked often, large
enough that a real snapshot arrives in one or two reads. */
const READ_CHUNK: usize = 65536;

#[derive(Debug, Clone)]
pub struct Client {
    pub path: PathBuf,
    pub timeout: Duration,
    pub max_bytes: usize,
}

impl Default for Client {
    fn default() -> Self {
        Client::new()
    }
}

impl Client {
    pub fn new() -> Self {
        Client {
            path: default_socket_path(),
            timeout: DEFAULT_TIMEOUT,
            max_bytes: DEFAULT_MAX_BYTES,
        }
    }

    pub fn with_path(path: impl Into<PathBuf>) -> Self {
        Client { path: path.into(), ..Client::new() }
    }

    pub fn with_timeout(mut self, timeout: Duration) -> Self {
        self.timeout = timeout;
        self
    }

    pub fn with_max_bytes(mut self, max_bytes: usize) -> Self {
        self.max_bytes = max_bytes;
        self
    }

    /*
    Fetch and normalize one snapshot.

    Every failure mode is a typed `ClientError`: no daemon (`Transport`), hung
    daemon (`Timeout`), unterminated or oversized response (`Framing`),
    non-JSON line (`Decode`), non-object root (`Schema`). Once the root is an
    object this returns `Ok` even with bad sections -- section damage is
    reported inside the `Snapshot`, not as a fetch failure (D-02).
    */
    pub fn snapshot(&self) -> Result<Snapshot, ClientError> {
        let deadline = Instant::now() + self.timeout;
        let mut stream = self.connect(deadline)?;

        stream
            .write_all(SNAPSHOT_REQUEST)
            .map_err(|e| ClientError::from_io(&e, "request write"))?;

        let line = read_line(&mut stream, deadline, self.max_bytes)?;
        Snapshot::from_slice(&line)
    }

    /*
    Ask the daemon to focus one session target.

    Fire-and-forget by contract: `_handle_conn`'s focus branch sends no
    response, so there is nothing to read back and success means "the request
    was written". A failure here is action-scoped and never touches snapshot
    state (D-07).

    The target is validated before the socket is touched, so an unfocusable
    session costs no I/O.
    */
    pub fn focus(&self, target: &FocusTarget) -> Result<(), ClientError> {
        validate_focus(target)?;

        let message = serde_json::json!({
            "action": "focus",
            "pane": target.pane,
            "tmux": target.tmux,
            "title": target.title,
            "term": target.term,
        });
        let mut payload = serde_json::to_vec(&message)
            .map_err(|_| ClientError::focus("focus request could not be encoded"))?;
        payload.push(b'\n');

        let deadline = Instant::now() + self.timeout;
        let mut stream = self.connect(deadline).map_err(as_focus_failure)?;
        stream
            .write_all(&payload)
            .map_err(|e| as_focus_failure(ClientError::from_io(&e, "focus write")))?;
        Ok(())
    }

    fn connect(&self, deadline: Instant) -> Result<UnixStream, ClientError> {
        let stream = UnixStream::connect(&self.path)
            .map_err(|e| ClientError::from_io(&e, "connect"))?;
        /* Bound each individual read too. The deadline is the real limit, but
        without this a single blocking read could park past it. */
        let remaining = remaining_or_timeout(deadline, "connect")?;
        stream
            .set_read_timeout(Some(remaining))
            .and_then(|_| stream.set_write_timeout(Some(remaining)))
            .map_err(|e| ClientError::from_io(&e, "socket timeout setup"))?;
        Ok(stream)
    }
}

/*
Read one newline-terminated line under a whole-operation deadline and a size cap.

Public so tests can drive it over a plain `UnixStream` pair without a daemon,
the same way `--selfcheck` drives the Python `read_line` over a socketpair.
*/
pub fn read_line<R: Read>(
    reader: &mut R,
    deadline: Instant,
    max_bytes: usize,
) -> Result<Vec<u8>, ClientError> {
    let mut buf: Vec<u8> = Vec::with_capacity(4096);
    let mut chunk = [0u8; READ_CHUNK];

    while !buf.ends_with(b"\n") {
        if Instant::now() > deadline {
            return Err(ClientError::timeout("snapshot read exceeded its deadline"));
        }
        let read = match reader.read(&mut chunk) {
            Ok(0) => break, /* EOF: return what arrived, let the decoder judge it. */
            Ok(n) => n,
            Err(e) if e.kind() == ErrorKind::Interrupted => continue,
            Err(e) => return Err(ClientError::from_io(&e, "response read")),
        };
        buf.extend_from_slice(&chunk[..read]);
        if buf.len() > max_bytes {
            return Err(ClientError::framing(format!(
                "response exceeded {} bytes",
                max_bytes
            )));
        }
    }
    Ok(buf)
}

/* Remaining budget, or a Timeout if it is already spent. Never returns zero:
a zero read timeout means "block forever" on a Unix socket, which is the exact
opposite of what a spent deadline should do. */
fn remaining_or_timeout(deadline: Instant, during: &str) -> Result<Duration, ClientError> {
    let now = Instant::now();
    if now >= deadline {
        return Err(ClientError::timeout(format!("{} exceeded its deadline", during)));
    }
    Ok(deadline - now)
}

/* Re-label a transport-level failure that happened during a focus action.
Focus failures are action-scoped (D-07): the caller must not read one as
"the daemon is gone" and mark snapshot data stale. */
fn as_focus_failure(err: ClientError) -> ClientError {
    match err.code {
        ErrorCode::Focus => err,
        other => ClientError::focus(format!("focus {}: {}", other.as_str(), err.context)),
    }
}

/* The daemon's socket path. Restates the expression at claude-monitor.py:32,
claude-send.py:17 and claude_monitor/core.py:799 -- change all four. */
pub fn default_socket_path() -> PathBuf {
    let runtime_dir = env::var_os("XDG_RUNTIME_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/tmp"));
    runtime_dir.join("claude-monitor.sock")
}

/* True when a socket file exists at `path`. Cheap pre-check for a cold start;
not a guarantee, since the file can be stale. */
pub fn socket_exists(path: &Path) -> bool {
    path.exists()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;
    use std::thread;

    fn far_deadline() -> Instant {
        Instant::now() + Duration::from_secs(30)
    }

    #[test]
    fn a_complete_line_is_read_whole() {
        let mut src = Cursor::new(b"{\"usage\":null}\n".to_vec());
        let line = read_line(&mut src, far_deadline(), 1024).unwrap();
        assert_eq!(line, b"{\"usage\":null}\n");
    }

    #[test]
    fn eof_before_the_newline_returns_what_arrived() {
        /* Not a transport failure: we reached the daemon, it just closed
        early. The decoder gets to call it malformed. */
        let mut src = Cursor::new(b"{\"usage\":".to_vec());
        let line = read_line(&mut src, far_deadline(), 1024).unwrap();
        assert_eq!(line, b"{\"usage\":");
        assert_eq!(Snapshot::from_slice(&line).unwrap_err().code, ErrorCode::Decode);
    }

    #[test]
    fn an_empty_response_is_a_decode_failure_not_a_panic() {
        let mut src = Cursor::new(Vec::new());
        let line = read_line(&mut src, far_deadline(), 1024).unwrap();
        assert!(line.is_empty());
        assert_eq!(Snapshot::from_slice(&line).unwrap_err().code, ErrorCode::Decode);
    }

    #[test]
    fn an_oversized_response_is_a_framing_failure() {
        /* A daemon streaming without ever sending a newline. */
        let flood = vec![b'x'; 8192];
        let mut src = Cursor::new(flood);
        let err = read_line(&mut src, far_deadline(), 64).expect_err("must reject");
        assert_eq!(err.code, ErrorCode::Framing);
        assert!(err.context.contains("64"));
    }

    #[test]
    fn a_spent_deadline_is_a_timeout_failure() {
        let mut src = Cursor::new(b"no newline ever".to_vec());
        let past = Instant::now() - Duration::from_secs(1);
        let err = read_line(&mut src, past, 1024).expect_err("must reject");
        assert_eq!(err.code, ErrorCode::Timeout);
    }

    #[test]
    fn a_dribbling_peer_is_bounded_by_the_whole_read_deadline() {
        /* The Pitfall-2 case: a per-read timeout would never fire because
        every individual read succeeds. Only a whole-operation deadline
        stops this. */
        struct Dribble;
        impl Read for Dribble {
            fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
                thread::sleep(Duration::from_millis(5));
                buf[0] = b'x';
                Ok(1)
            }
        }
        let deadline = Instant::now() + Duration::from_millis(60);
        let err = read_line(&mut Dribble, deadline, 1 << 20).expect_err("must time out");
        assert_eq!(err.code, ErrorCode::Timeout);
    }

    #[test]
    fn an_interrupted_read_is_retried_not_failed() {
        struct OnceInterrupted(bool);
        impl Read for OnceInterrupted {
            fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
                if !self.0 {
                    self.0 = true;
                    return Err(std::io::Error::new(ErrorKind::Interrupted, "signal"));
                }
                buf[..3].copy_from_slice(b"{}\n");
                Ok(3)
            }
        }
        let line = read_line(&mut OnceInterrupted(false), far_deadline(), 1024).unwrap();
        assert_eq!(line, b"{}\n");
    }

    #[test]
    fn a_missing_socket_is_a_transport_failure_not_a_panic() {
        let client = Client::with_path("/nonexistent/claude-monitor-test.sock");
        let err = client.snapshot().expect_err("must fail");
        assert_eq!(err.code, ErrorCode::Transport);
        /* D-08: no OS message text in the context. */
        assert!(!err.context.contains("nonexistent"));
    }

    #[test]
    fn focus_rejects_an_unfocusable_target_without_touching_the_socket() {
        /* Path is deliberately invalid: a Focus code proves we never dialled. */
        let client = Client::with_path("/nonexistent/claude-monitor-test.sock");
        let unfocusable = FocusTarget { term: "ghostty".into(), ..Default::default() };
        assert_eq!(client.focus(&unfocusable).unwrap_err().code, ErrorCode::Focus);
    }

    #[test]
    fn a_focus_transport_failure_still_reports_as_focus() {
        /* D-07: a focus failure must never be mistaken for the daemon being
        gone, or the caller will mark snapshot data stale. */
        let client = Client::with_path("/nonexistent/claude-monitor-test.sock");
        let target = FocusTarget { pane: "%1".into(), ..Default::default() };
        assert_eq!(client.focus(&target).unwrap_err().code, ErrorCode::Focus);
    }

    #[test]
    fn the_request_line_matches_the_python_client_byte_for_byte() {
        assert_eq!(SNAPSHOT_REQUEST, b"{\"query\": \"snapshot\"}\n");
    }

    #[test]
    fn the_default_socket_path_follows_xdg_runtime_dir() {
        /* Not asserted against the live env: the fallback is the contract. */
        let path = default_socket_path();
        assert!(path.ends_with("claude-monitor.sock"));
    }

    #[test]
    fn client_is_send_and_sync_so_concurrent_calls_are_safe() {
        /* RTUI-03 / RTUI-12 concurrency edge: the client holds no connection
        and no mutable state, so parallel or interrupted calls are independent
        and cannot corrupt each other. */
        fn assert_send_sync<T: Send + Sync>() {}
        assert_send_sync::<Client>();
    }

    #[test]
    fn concurrent_failing_fetches_stay_independent() {
        let client = Client::with_path("/nonexistent/claude-monitor-test.sock");
        let handles: Vec<_> = (0..8)
            .map(|_| {
                let c = client.clone();
                thread::spawn(move || c.snapshot().expect_err("must fail").code)
            })
            .collect();
        for h in handles {
            assert_eq!(h.join().unwrap(), ErrorCode::Transport);
        }
    }
}
