# Phase 11: Rust Client Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-25
**Phase:** 11-rust-client-foundation
**Areas discussed:** Partial snapshots, Failure-state contract, Hostile session text, Fixture contract

---

## Partial snapshots

| Option | Description | Selected |
|--------|-------------|----------|
| Strict all-or-nothing | Any malformed field rejects the complete snapshot. | |
| Narrow salvage | Reject invalid framing/root data, then preserve valid sections and valid session entries. | ✓ |
| Permissive coercion | Invent defaults or coerce wrong JSON types so all data renders. | |

**User's choice:** Delegated to the agent: “You choose dude. What do you think it's best”

**Notes:** Selected section-level salvage without type coercion. Missing optional
fields become absence, malformed sessions are rejected individually, and unknown
fields are ignored for forward compatibility.

---

## Failure-state contract

| Option | Description | Selected |
|--------|-------------|----------|
| Generic failure | Collapse all errors into one unavailable state. | |
| Stable categories | Separate transport, timeout, framing/size, decoding, schema, rendering, and focus failures. | ✓ |
| Raw errors | Expose library/OS error strings directly to downstream rendering. | |

**User's choice:** Delegated to the agent.

**Notes:** Selected typed categories with safe structured context. Failed fetches
do not mutate the last good snapshot. Focus failures remain isolated action results,
and renderers own human-facing wording.

---

## Hostile session text

| Option | Description | Selected |
|--------|-------------|----------|
| Renderer-only escaping | Preserve raw strings until each widget renders them. | |
| Trust-boundary normalization | Produce safe display strings during normalization and still use non-markup render APIs. | ✓ |
| Daemon sanitization | Change the daemon contract to sanitize before transmission. | |

**User's choice:** Delegated to the agent.

**Notes:** Complete terminal escape/control sequences become one visible replacement
marker; remaining controls are replaced deterministically. Printable Unicode and
markup-looking text remain literal. Display values are bounded and separate from
opaque, validated focus-routing values.

---

## Fixture contract

| Option | Description | Selected |
|--------|-------------|----------|
| Rust-only builders | Construct test state inside Rust with no shared wire corpus. | |
| Shared semantic fixtures | Pair language-neutral raw wire inputs with normalized state or stable errors. | ✓ |
| Live captures/screenshots | Treat current daemon captures or terminal screenshots as the oracle. | |

**User's choice:** Delegated to the agent.

**Notes:** Hand-authored fixtures are canonical and use a frozen clock. Coverage
includes valid, partial, malformed, oversized, invalid UTF-8, hostile-text, and
focus cases. Assertions target semantic state and stable codes, not debug strings
or implementation serialization.

---

## the agent's Discretion

- The user explicitly delegated all four gray areas to the agent.
- Rust crate/module organization and dependency selection.
- Exact enum/type names and internal state representation.
- Exact timeout, response-size, field-length, replacement-marker, and truncation values.
- Optional fuzz/property testing beyond the required deterministic corpus.

## Deferred Ideas

None. Discussion stayed within the Phase 11 boundary.
