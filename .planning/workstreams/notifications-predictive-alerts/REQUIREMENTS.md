# Requirements: claude-code-tray v2.0 Rust TUI

**Defined:** 2026-07-25
**Core Value:** At a glance from the top bar, know how much Claude Code quota is left and when it resets — without launching a separate terminal monitor.

## v2.0 Requirements

### Runtime and Installation

- [ ] **RTUI-01**: User can launch the compiled `claude-tui` binary without Python, Textual, or `uv` installed.
- [ ] **RTUI-02**: User can install the Rust TUI through `install.sh`, making it the default `claude-tui` command while retaining `claude-tui.py` as the reference implementation.
- [ ] **RTUI-03**: The Rust TUI consumes the existing read-only daemon snapshot and focus protocol without requiring daemon or socket-schema changes.

### Visual and Data Parity

- [ ] **RTUI-04**: User sees both quota gauges with the same percentages, token counts when available, reset countdowns, burn rates, projections or exhaustion times, proximity colors, and gradients.
- [ ] **RTUI-05**: User sees the same eight-row usage trend, daily and weekly burn, peak-usage hour, and Monday-Sunday hourly heatmap with equivalent quantization and colors.
- [ ] **RTUI-06**: User sees live sessions with the same status, project, elapsed time, waiting-to-running-to-done ordering, status colors, zebra striping, and empty state.
- [ ] **RTUI-07**: User sees the same panel order, titled rounded borders, terminal-derived palette, header clock, footer, spacing, and responsive allocation.

### Interaction Parity

- [ ] **RTUI-08**: Data refreshes automatically at the existing cadence while countdowns and session durations advance every second.
- [ ] **RTUI-09**: User can navigate and activate a session to focus its terminal, with selection and scroll position retained across refreshes.
- [ ] **RTUI-10**: `q` remains the sole advertised exit binding, with no command palette or independent theme toggle.

### Resilience and Verification

- [ ] **RTUI-11**: An unreachable daemon shows the same cold-start message; later outages preserve and dim the last good frame while retrying indefinitely.
- [ ] **RTUI-12**: Socket, decoding, rendering, and focus failures never crash the TUI or expose an unhandled traceback.
- [ ] **RTUI-13**: Untrusted session text cannot inject terminal controls or markup.
- [ ] **RTUI-14**: Automated parity checks compare Rust output and behavior against shared fixtures derived from the retained Python oracle.

## Future Requirements

### Standalone Operation

- **STAND-01**: User can run the TUI without the daemon by reading `usage-history.jsonl` directly.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Rust daemon or shared-core rewrite | v2.0 is a frontend rewrite over the existing daemon contract. |
| Socket schema changes or a new query verb | The shipped snapshot and focus protocol already provides the required data and action. |
| New polling or a second usage data source | The daemon remains the single source of truth. |
| TUI-side configuration mutation | Strict parity preserves the current read-only TUI boundary. |
| New product features beyond parity | v2.0 succeeds by replacing the runtime without changing behavior. |
| Deleting `claude-tui.py` | The Python implementation remains the behavioral and visual oracle. |
| Wayland support | The surrounding tray application remains X11-only. |

## Traceability

Populated during roadmap creation. Every v2.0 requirement must map to exactly one phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| RTUI-01 | TBD | Pending |
| RTUI-02 | TBD | Pending |
| RTUI-03 | TBD | Pending |
| RTUI-04 | TBD | Pending |
| RTUI-05 | TBD | Pending |
| RTUI-06 | TBD | Pending |
| RTUI-07 | TBD | Pending |
| RTUI-08 | TBD | Pending |
| RTUI-09 | TBD | Pending |
| RTUI-10 | TBD | Pending |
| RTUI-11 | TBD | Pending |
| RTUI-12 | TBD | Pending |
| RTUI-13 | TBD | Pending |
| RTUI-14 | TBD | Pending |

**Coverage:**
- v2.0 requirements: 14 total
- Mapped to phases: 0
- Unmapped: 14

---
*Requirements defined: 2026-07-25*
*Last updated: 2026-07-25 after v2.0 scope confirmation*
