# Phase 4: Usage Web Dashboard - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-12
**Phase:** 4-usage-web-dashboard
**Areas discussed:** Chart rendering, Refresh timing, Heatmap encoding
**Areas offered but not selected:** Delivery shape (user deferred to lazy default + planner per SEED-001)

---

## Chart rendering

| Option | Description | Selected |
|--------|-------------|----------|
| Python-generated SVG | stdlib builds `<svg>` strings server-side; 3 ranges pre-rendered, toggled with pure CSS, zero JS | |
| Embed JSON + inline JS | emit `<script>const data=[...]</script>` + inline JS that draws charts and switches ranges client-side | ✓ |

**User's choice:** Embed JSON + inline JS.
**Notes:** Keeps range switching (DASH-02) fully client-side from one embedded dataset; still self-contained (no CDN, no charting lib) per DASH-06.

---

## Refresh timing

| Option | Description | Selected |
|--------|-------------|----------|
| In poll_loop, throttled | generate HTML off the Gtk main thread on a ~5min throttle; menu item just opens the file | ✓ |
| On click, off a spawned thread | regenerate at click time via a worker thread, then open; freshest but more moving parts | |

**User's choice:** In poll_loop, throttled.
**Notes:** Upholds the mandatory "no file I/O on the Gtk main thread" posture (HIST-03 / POLL-02 / Phase 3 D-05); mirrors the existing `last_prune`/`last_trend` throttle pattern.

---

## Heatmap encoding

| Option | Description | Selected |
|--------|-------------|----------|
| Mean burn rate tok/hr | cell = mean(burn*60) per (hour, weekday) bucket; matches Phase 3 peak-hour | ✓ |
| Mean usage % | cell = mean(pct) per bucket | |

**User's choice:** Mean burn rate (tok/hr).

| Option | Description | Selected |
|--------|-------------|----------|
| Single-hue light->dark | one hue, lightness scaled by value; empty cell neutral gray | ✓ |
| Multi-stop blue->red | cool->warm ramp; needs legend, less colorblind-safe | |

**User's choice:** Single-hue light->dark.
**Notes:** Empty buckets render distinct neutral gray so "no data" != "low usage" (mirrors Phase 3 D-03 gap handling).

---

## Claude's Discretion

- Delivery shape defaulted to static `.html` via `file://` (laziest; no server/port/thread). Planner may revisit vs loopback `http.server` per SEED-001, but DASH-F1 (live refresh) is deferred, removing the main reason to serve.
- Output file location (`~/.cache/claude-tray/dashboard.html`), throttle constant (~5min), browser-open mechanism (`webbrowser.open()` vs `xdg-open`), chart dimensions / preset boundaries, embedded record fields, pure-function-vs-method placement, and empty-history page state.

## Deferred Ideas

- DASH-F1 — live in-browser auto-refresh (keeps static `file://` viable).
- DASH-F2 — raw data export from the dashboard.
- DASH-F3 — configurable ranges/aggregation windows.
- Loopback `http.server` delivery shape — set aside in favor of static `file://`.
