---
phase: 260718-hgm-despike-dashboard-usage-trend-chart-seed
plan: 01
subsystem: dashboard
status: complete
tags: [dashboard, despike, seed-006]
requires: [with_gaps, RISE_MAX, heatmap_buckets]
provides: [despike]
affects: [claude-monitor.py]
tech-stack:
  added: none
  patterns: [reject-and-drop outlier rejection reusing RISE_MAX]
key-files:
  created: []
  modified:
    - claude-monitor.py
    - .planning/seeds/SEED-006-dashboard-usage-despike.md
decisions:
  - "Reject-and-drop (not median-smooth): kept points are real samples only, line stays honest."
  - "Share RISE_MAX with heatmap_buckets -- one ceiling, two consumers."
metrics:
  duration: ~5m
  completed: 2026-07-18
  tasks: 2
  files: 2
commit: 4ebec5e
---

# Phase 260718-hgm Plan 01: Despike Dashboard Usage-% Trend Chart Summary

Reuse the heatmap's existing RISE_MAX outlier rejection on the two dashboard line series
so upstream 100%-pins stop rendering as spurious spikes -- consistency, not new machinery.

## What Was Done

### Task 1: despike helper + wire both series + selfcheck assert

Added a pure stdlib `despike(series, max_rise=RISE_MAX)` immediately after `with_gaps`,
walking the series in order and dropping any sample whose pct rises more than `max_rise`
above the previous KEPT sample. Only positive jumps are bound; drops (window resets) and
sub-RISE_MAX ramps survive. Both `render_dashboard` payload series now read
`with_gaps(despike(...))` so gaps are computed on the cleaned series.

Diff hunks applied to `claude-monitor.py`:

```python
# new helper, after with_gaps (~line 606)
def despike(series, max_rise=RISE_MAX):
    """Drop upstream 100%-pin outliers from a [[t, pct], ...] series before with_gaps.

    Mirrors the `rise > RISE_MAX` rejection in heatmap_buckets so the line chart and the
    heatmap agree on a believable one-sample jump (see the ponytail: note at RISE_MAX for
    why upstream pins pct=100). Reject-and-drop, not median-smooth: kept points are real
    samples only -- no synthesized midpoints -- so the line stays honest.

    A sample is dropped only when its pct rises more than max_rise above the previous KEPT
    sample; the kept reference is left unchanged on a drop, so consecutive pins both go.
    Only positive jumps are bound -- drops (window resets to ~0) survive untouched. Must
    run BEFORE with_gaps so pen-up breaks are computed on the cleaned series. Input is
    already numeric (history_numeric / _is_num), so no None handling is needed.
    """
    out = []
    ref = None  # pct of the previous kept sample
    for t, v in series:
        if ref is not None and v - ref > max_rise:
            continue
        out.append([t, v])
        ref = v
    return out
```

```python
# render_dashboard payload (~line 1055)
-        "usage": with_gaps([[int(r["t"]), r["pct"]] for r in records]),
-        "usage7": with_gaps(usage7_series(records)),
+        "usage": with_gaps(despike([[int(r["t"]), r["pct"]] for r in records])),
+        "usage7": with_gaps(despike(usage7_series(records))),
```

```python
# demo() selfcheck, next to with_gaps / usage7_series asserts
+    # 100 pin between low samples dropped (measured against last KEPT sample), genuine
+    # sub-RISE_MAX ramp preserved whole.
+    assert despike([[0, 5.0], [15, 100.0], [30, 8.0]]) == [[0, 5.0], [30, 8.0]]
+    assert despike([[0, 5.0], [15, 15.0], [30, 25.0]]) == [[0, 5.0], [15, 15.0], [30, 25.0]]
```

### Task 2: SEED-006 marked sprouted

`.planning/seeds/SEED-006-dashboard-usage-despike.md` frontmatter: `status: planted` ->
`status: sprouted`, `sprouted_into:` -> `sprouted_into: 260718-hgm`. Body untouched.

## Verification

`python3 claude-monitor.py --selfcheck` -> printed `ok`, **exit code 0** (all asserts pass,
including the new despike assert).

- `grep -c 'with_gaps(despike(' claude-monitor.py` == 2
- `grep -n 'def despike(' claude-monitor.py` matches at line 606, default `max_rise=RISE_MAX`

## Deviations from Plan

None - plan executed exactly as written.

## Deliverable Commit

`4ebec5e` fix(dashboard): despike usage-% trend chart (SEED-006)

## Self-Check: PASSED

- FOUND: claude-monitor.py (def despike present, both series wrapped)
- FOUND: .planning/seeds/SEED-006-dashboard-usage-despike.md (sprouted)
- FOUND commit: 4ebec5e
- --selfcheck exit code: 0
