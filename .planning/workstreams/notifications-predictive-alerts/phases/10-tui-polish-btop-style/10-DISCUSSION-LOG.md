# Phase 10: TUI Polish (btop-style) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-24
**Phase:** 10-TUI Polish (btop-style)
**Areas discussed:** Threshold color bands, Gauge / meter style, Richer trends graph, Sessions + panel styling

---

## Threshold color bands (TUI-06)

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed btop bands, shared | Fixed cutoffs independent of the badge threshold (e.g. <70 green / 70-90 yellow / >=90 red), shared by 5h and 7d; pure core `band()` proven by --selfcheck | ✓ |
| Reuse badge threshold | Configurable USAGE_THRESHOLD as the yellow->red cutoff | |
| Threshold = red, derived yellow | USAGE_THRESHOLD is red cutoff; yellow a fixed band below | |

**User's choice:** Fixed btop bands, shared
**Notes:** Keeps proximity-to-cap coloring decoupled from the mutable tray-badge warn line — colors don't move when the user retunes the badge.

---

## Gauge / meter style (TUI-07)

| Option | Description | Selected |
|--------|-------------|----------|
| Per-cell gradient | Each filled cell colored along green->yellow->red by position — btop's signature meter | ✓ |
| Single band color | Whole fill one color set by the TUI-06 band | |

**User's choice:** Per-cell gradient
**Notes:** Coexists with the band-colored row text (band = which zone, gradient = the sweep). Fill-cell count stays a pure core function.

---

## Richer trends graph (TUI-08)

| Option | Description | Selected |
|--------|-------------|----------|
| Taller decoded bars | Decode sparkline glyphs to level 0-7, render taller multi-row block/braille graph colored by height; pure decode in core | ✓ |
| Colorize existing sparkline | Single-row 24-glyph sparkline, colored by height | |
| Both | Taller decoded bars AND colored | |

**User's choice:** Taller decoded bars
**Notes:** Constraint-bound — snapshot shape is fixed, so no new numeric series; graph re-renders the existing SPARK_GLYPHS levels (no new trend math), height-colored on the same green->red ramp.

---

## Sessions + panel styling (TUI-09 / TUI-10)

| Option | Description | Selected |
|--------|-------------|----------|
| Status color + zebra | Status-colored rows (waiting yellow / running green / done dim) + subtle zebra striping; static rounded titled borders | ✓ |
| Status color only | Status-colored rows, no striping | |
| Status color + tinted borders | Rows colored AND usage-panel border tinted by worst band | |

**User's choice:** Status color + zebra
**Notes:** Borders stay static (rounded, titled); the threshold signal lives in row text + gauge, not panel chrome. Tinted-border variant noted as a deferred idea.

---

## Claude's Discretion

- Exact band cutoff numbers (within the fixed three-band shape), color hex / textual
  theme-var mapping, gauge bar width, glyph sets, and border/striping/title CSS.
- Gauge glyph mechanism (custom string vs widget), provided the fill-cell count is a
  pure core function proven by --selfcheck.
- Whether band/gauge/decode helpers are one function each or a shared small module.

## Deferred Ideas

- Threshold-tinted panel borders — considered under TUI-10, rejected (borders stay static).
- Terminal-width / taller sparkline fed by a real numeric series — needs a snapshot-shape
  change, out of scope this milestone.
- TUI click-to-focus and standalone no-daemon mode — carried deferred from v1.5.
