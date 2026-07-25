# Phase 11: Rust Client Foundation - Context

**Gathered:** 2026-07-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the panic-free Rust boundary for the existing daemon protocol. The phase
delivers a bounded Unix-socket client, deterministic snapshot normalization,
safe session text, typed nonfatal failures, focus-request support, and a
language-neutral fixture corpus that does not require a running daemon.

The daemon and wire contract are fixed: one newline-delimited
`{"query":"snapshot"}` request returns one snapshot object, and focus uses the
existing `{"action":"focus",...}` message. No socket field, verb, daemon
behavior, TUI layout, event loop, installation default, or standalone data
source is added here. Visual parity belongs to Phase 12, interaction and outage
presentation to Phase 13, and installation/parity cutover to Phase 14.

</domain>

<decisions>
## Implementation Decisions

### Partial snapshot normalization

- **D-01:** Invalid framing, an oversized response, invalid JSON, or a
  non-object root rejects the fetch as a whole. Bytes from a failed fetch are
  never merged into previously accepted state.
- **D-02:** Once the root object is valid, `usage`, `trends`, `heatmap`, and
  `sessions` are normalized independently. A malformed section becomes
  explicitly unavailable while valid sibling sections remain usable.
  — **Reversibility: costly** — Phases 12-14 will build rendering and parity
  assertions around this section-level availability contract.
- **D-03:** Within `sessions`, reject only malformed entries. Preserve valid
  entries in daemon order and retain a deterministic rejected-entry count for
  diagnostics; do not invent renderable sessions from invalid data.
- **D-04:** Missing optional fields become explicit absence. Missing required
  fields invalidate only the narrowest affected section or entry. Unknown
  fields are ignored for forward compatibility. Wrong JSON types are not
  coerced: numeric strings do not become numbers, and arbitrary values do not
  become display strings.

### Failure-state contract

- **D-05:** Expose stable typed failure categories covering transport,
  timeout, framing/size, decoding, schema normalization, rendering, and
  focus-action failures. Do not collapse them into one boolean and do not make
  downstream code parse operating-system or library error strings.
  — **Reversibility: costly** — these codes become the shared contract for
  fixtures and the later TUI state machine.
- **D-06:** A failed fetch never mutates the last good normalized snapshot.
  Return the failure separately so Phase 13 can implement the already-decided
  split: unavailable on cold start, preserved/dimmed last frame after a later
  outage.
- **D-07:** Focus is an action-scoped result. A focus failure is nonfatal,
  testable, and never marks snapshot data stale or changes refresh state.
- **D-08:** Errors expose stable codes plus safe structured context. Human
  wording belongs to the renderer. Raw hostile payload text, raw control
  characters, and implementation-specific debug chains must not become UI
  messages.

### Hostile session text

- **D-09:** Sanitize every daemon-sourced display string at the normalization
  trust boundary. Renderers receive display-safe values; non-markup widget APIs
  remain defense in depth rather than the only protection.
  — **Reversibility: costly** — later renderers and parity fixtures will rely on
  normalized strings already being safe.
- **D-10:** Recognize complete terminal escape/control sequences, including
  ANSI CSI and OSC forms, and collapse each sequence to one visible replacement
  marker. Deterministically replace any remaining non-printable control
  characters. Never forward raw terminal-control bytes.
- **D-11:** Preserve ordinary printable Unicode and markup-looking strings such
  as `[bold]repo[/]` literally. The renderer must use plain/non-markup text APIs
  so printable user content is never interpreted as styling.
- **D-12:** Keep safe, length-bounded display values separate from bounded,
  type-validated opaque focus-routing values. A truncated display value gets a
  visible truncation marker. Raw routing values are never rendered, and raw
  hostile values are never echoed through diagnostics.

### Shared fixture contract

- **D-13:** Commit language-neutral raw wire inputs paired with expected
  normalized semantic state or stable error codes. Rust tests consume the
  corpus in Phase 11; the retained Python oracle and Phase 14 parity checks must
  be able to consume the same fixtures.
  — **Reversibility: costly** — Phase 14 will depend on this corpus as the
  cross-language parity substrate.
- **D-14:** Hand-authored, reviewable fixtures are canonical. A sanitized
  representative capture may supplement them, but machine-specific paths,
  private usage data, timestamps, or live-daemon state do not define expected
  behavior.
- **D-15:** The initial matrix covers: full valid data, missing optional fields,
  partial sections, unknown fields, wrong types, malformed/truncated JSON,
  invalid UTF-8, oversized responses, hostile terminal controls, markup-like
  printable text, and valid/invalid focus targets.
- **D-16:** Golden assertions compare semantic normalized values, section
  availability, rejected-entry counts, safe display text, and stable error
  codes under an injected/frozen clock. They do not lock debug wording, map
  iteration order, or implementation-specific serialization.

### the agent's Discretion

- Rust crate/workspace layout, module names, and dependency selection, provided
  the client/normalization logic is independently testable from the eventual
  terminal renderer.
- Exact enum/type names, safe structured error fields, required-versus-optional
  field table derived from the shipped daemon contract, and the internal
  representation of section availability.
- Exact response and per-field limits, timeout constants, replacement marker,
  and truncation widths. Preserve the existing posture: bounded reads, visible
  sanitization, and no silent coercion.
- Whether to add fuzz/property tests beyond the mandatory deterministic fixture
  matrix.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and locked milestone boundaries

- `.planning/PROJECT.md` — project architecture, retained Python oracle, and
  established resilience decisions.
- `.planning/workstreams/notifications-predictive-alerts/ROADMAP.md` — Phase 11
  goal and success criteria, plus Phase 12-14 boundaries.
- `.planning/workstreams/notifications-predictive-alerts/REQUIREMENTS.md` —
  RTUI-03, RTUI-12, RTUI-13 and the v2.0 out-of-scope table.

### Shipped protocol and behavioral precedent

- `.planning/workstreams/notifications-predictive-alerts/milestones/v1.5-phases/08-daemon-socket-query-verb/08-CONTEXT.md`
  — fixed one-shot snapshot protocol, payload scope, concurrency, and
  read-only-daemon decisions.
- `.planning/workstreams/notifications-predictive-alerts/milestones/v1.5-phases/09-terminal-dashboard-claude-tui-py/09-CONTEXT.md`
  — socket-only data source, error-boundary posture, cold-start/stale behavior,
  refresh precedent, and Python TUI oracle.
- `.planning/workstreams/notifications-predictive-alerts/milestones/v1.6-phases/10-tui-polish-btop-style/10-CONTEXT.md`
  — pure-core versus rendering-boundary split and parity constraints.

### Existing wire implementation and Python oracle

- `claude-monitor.py` — `_handle_conn` defines the shipped snapshot and focus
  wire behavior; this phase must consume it without modification.
- `claude_monitor/core.py` — `read_line`, `query_snapshot`, `request_focus`,
  `_safe_cell`, and session helpers provide the current timeout, size,
  validation, and sanitization precedents.
- `claude-tui.py` — fetch/focus error boundaries, last-good-frame handling, and
  plain `Text` cells define the behavior the Rust rewrite must preserve.
- `claude_monitor/test_claude_monitor.py` — current socket, focus,
  sanitization, timeout-ordering, and hostile-text assertions.
- `claude_monitor/test_tui.py` — current interaction-level Python TUI checks.

No external specification was selected during discussion. Rust library choices
and their official documentation are research inputs, not locked decisions.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `claude_monitor.core.read_line`: reference for whole-read deadline, 1 MiB
  response cap, newline/EOF handling, and UTF-8 degradation.
- `claude_monitor.core.query_snapshot`: exact request bytes and current
  top-level-object validation.
- `claude_monitor.core.request_focus`: exact focus payload and current target
  validation.
- `claude_monitor.core._safe_cell`: current Python behavior for hostile control
  characters; Rust intentionally strengthens it by recognizing complete escape
  sequences at normalization.
- `claude_monitor/test_claude_monitor.py`: ready-made edge cases that can seed
  the language-neutral fixture corpus.

### Established Patterns

- Low-level client helpers return/raise failures; the application boundary
  decides presentation and keeps retrying.
- Pure deterministic logic lives above the rendering framework and is tested
  without launching the UI.
- A failed refresh preserves the last good bound snapshot.
- Untrusted printable text is passed to non-markup renderables, never parsed as
  styling.
- Socket I/O is bounded, one-shot, newline-delimited, and closes after each
  request.

### Integration Points

- The Rust client connects to the same
  `$XDG_RUNTIME_DIR/claude-monitor.sock`; `claude-monitor.py` is not changed.
- The new normalized state becomes Phase 12's only rendering input.
- Focus requests reuse the daemon action verb and remain separate from snapshot
  refresh state.
- Shared fixtures become Phase 14's Python-versus-Rust parity substrate.
- There is no existing Cargo project. Crate scaffolding is part of Phase 11;
  `install.sh` cutover remains Phase 14.

</code_context>

<specifics>
## Specific Ideas

- Favor narrow failure containment: one bad session should not blank valid
  quota/trend data, but the client must never hide contract drift through type
  coercion.
- Treat normalized state as the trust boundary and rendering input, not as a
  thin alias over unvalidated JSON.
- Keep fixtures human-reviewable and semantic so they survive internal Rust
  refactors and can later be shared with the Python oracle.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 11-rust-client-foundation*
*Context gathered: 2026-07-25*
