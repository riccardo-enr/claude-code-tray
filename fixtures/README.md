# Shared snapshot fixtures

Language-neutral wire inputs paired with the semantic state a correct client
must produce from them (D-13). The Rust client consumes this corpus in
`rust/tests/fixtures.rs`; the retained Python oracle and the Phase 14 parity
harness consume the same files. That is the point: a fixture is the one artifact
both implementations can be wrong against.

These are hand-authored and reviewable (D-14). A sanitized capture from a live
daemon may be added alongside them, but machine-specific paths, private usage
numbers and live timestamps never define expected behaviour -- a fixture whose
expectation is "whatever the daemon happened to send" tests nothing.

## Format

One JSON object per file:

```json
{
  "name":  "kebab-case-id, matching the filename",
  "note":  "what this fixture pins, and why it matters",
  "wire":  "the raw response line, as a JSON string",
  "expect": { ... }
}
```

Use `wire_bytes` (an array of byte values) instead of `wire` when the input is
not valid UTF-8 and therefore cannot be written as a JSON string.

### Expectations

`expect.error` names a whole-fetch rejection by its stable code, and no section
keys are then present:

```json
{ "expect": { "error": "decode" } }
```

Otherwise each section key carries either a state name -- `"absent"` or
`"malformed"` -- or an object describing the normalized values:

| key        | object form                                                        |
|------------|--------------------------------------------------------------------|
| `usage`    | any subset of the seven usage fields; `null` asserts explicit absence |
| `trends`   | `{"rows": ["..."]}` -- the sanitized row strings                    |
| `heatmap`  | `{"rows": 7, "cols": 24}`                                           |
| `sessions` | `{"rejected": N, "entries": [{...}]}`                               |

A session entry may assert `id`, `dir`, `status`, `entered`, `frozen` and
`focusable`. Omitted keys are not checked, so a fixture stays focused on the one
behaviour it exists to pin.

Assertions are semantic on purpose (D-16). They compare normalized values,
section availability, rejected-entry counts, safe display text and stable error
codes. They deliberately do **not** lock debug wording, map iteration order or
any implementation-specific serialization, so the corpus survives internal
refactors in either language.

## What is not covered here

The response size cap is exercised in `rust/src/client.rs` with a small
`max_bytes` override rather than by committing a megabyte-long fixture. Storing
1 MiB of padding in git to assert a number that the test can set directly would
be a fixture that costs more to carry than it proves.
