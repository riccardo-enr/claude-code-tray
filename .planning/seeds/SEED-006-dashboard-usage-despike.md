---
id: SEED-006
status: sprouted
sprouted_into: 260718-hgm
planted: 2026-07-18
planted_during: v1.4 Phase 7 plan-phase (user flagged the live dashboard chart)
trigger_when: next dashboard-facing milestone, or sooner if the spikes annoy
scope: small
---

# SEED-006: Despike the dashboard usage-% trend chart

## Why This Matters

The "Usage % over time" line chart plots **raw `pct`** and shows spurious 100%
spikes at the left edge -- readings that jump to 100% for a sample or two and
drop straight back. They are not real usage; the upstream `claude-monitor` CLI
pins `pct=100` (burn spikes with it), already documented in the existing
`ponytail:` comment at `claude-monitor.py:584`.

The chart is the only surface that still shows them raw:

- **Heatmap** already rejects them -- `heatmap_buckets` drops any rise > `RISE_MAX`
  (25.0), `claude-monitor.py:561`.
- **Line chart** does not -- `claude-monitor.py:1055`:
  `with_gaps([[int(r["t"]), r["pct"]] for r in records])`.

So the fix is consistency, not new machinery: apply the same outlier rejection
the heatmap already trusts to the chart series (and the weekly `usage7` series).

## NOT a Kalman filter

Considered and rejected at flag time:

- The defect is **outliers** (discrete garbage samples), not Gaussian noise on a
  smooth signal. A KF smooths noise; it does not reject outliers -- fed the raw
  series it chases the 100% pin as a huge innovation and smears it into
  neighbors.
- Quota % is a **sawtooth** (ramp, then reset-to-0 at window roll). A KF's linear
  process model has no clean form for that; every reset is a discontinuity the
  filter fights, so you tune Q/R forever and still lag real ramps.
- Hard project constraint: **stdlib only, no new deps** -- numpy/scipy/filterpy
  are out. A hand-rolled KF is far more code than the problem is worth.

## Scope Estimate

**Small** -- one helper on the read side, no new state, no new polling.

Lean fix (pick one, both ~one function):

1. **Reuse RISE_MAX rejection** on the chart series -- drop samples whose jump
   from the previous kept sample exceeds `RISE_MAX`, mirroring the heatmap.
   Most consistent with existing code.
2. **Rolling median-of-3** on the series before `with_gaps` -- textbook robust
   despike, preserves the reset edges and the ramp, no tuning.

Keep it off the Gtk main thread (chart is already built in the poll tick) and
add one `--selfcheck` assert: a `[..., 100, ...]` pin between low samples is
removed while a genuine ramp is preserved.

## Open Questions (decide at implement time)

1. Reject-and-drop vs. median-smooth -- dropping keeps the line honest (real
   samples only, gap-broken); median invents a synthesized midpoint. Lean drop.
2. Whether to also despike the tray sparkline (TREND-01) or leave it (it is
   already 24h-scaled and less spike-sensitive). Lean leave.
