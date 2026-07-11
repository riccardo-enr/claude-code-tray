# Phase 1 Research: Usage & Quota Monitoring in the Tray

**Researched:** 2026-07-11
**Method:** Direct verification against the installed `claude-monitor` CLI (v4.0.0) on this machine, plus reading the existing `claude-monitor.py` tray helper. This is verified ground truth, not web research.

## CLI invocation

Invoke by absolute path (PROJECT.md naming caution — the CLI shares the name `claude-monitor` with our helper `claude-monitor.py`):

```
~/.local/bin/claude-monitor --plan max5 --output json --once
```

Ran in a few seconds on a populated `~/.claude/projects`. Emits a single JSON document to stdout. `--once` makes it print-and-exit (no TUI).

## CRITICAL gotcha: exit code encodes usage status, NOT call success

Observed: the CLI exited with **code 11** while printing **complete, valid JSON**. `status.code = 11`, `status.label = "limit_hit"`. The exit code reflects the *usage state* (e.g. limit hit), not whether the call succeeded.

**Implication for POLL-02 error handling:** do NOT gate on `returncode == 0`. That would show "usage unavailable" precisely when usage is highest (limit hit) — the worst possible time. Correct degradation logic:

1. Run with a timeout (subprocess timeout, e.g. 15s).
2. Attempt `json.loads(stdout)` regardless of exit code.
3. Treat as **available** if JSON parses and `limits.five_hour` is present.
4. Treat as **unavailable** only on: timeout, empty stdout, `json.loads` failure, `FileNotFoundError` (CLI missing), or missing `limits.five_hour`.

## JSON schema (fields this phase consumes)

```
limits.five_hour.tokens_used        int    tokens against the 5h limit (== input+output tokens)
limits.five_hour.token_limit        int    e.g. 88000 for max5
limits.five_hour.used_percentage    float  CAN EXCEED 100 (observed 473.5) — do not assume <= 100
limits.five_hour.resets_at_epoch    int    unix seconds; source of the reset countdown
local.burn_rate_tokens_per_minute   float  PER MINUTE (observed ~315615.2)
status.code / status.label          int/str usage status (e.g. 11 / "limit_hit")
```

`limits.seven_day.*` is all `null` for this account — out of scope (USAGE-F1, deferred). `local.cost_usd`, `local_history` — out of scope (billing).

## Field -> requirement mapping

| Requirement | Source field(s) | Display example |
|-------------|-----------------|-----------------|
| USAGE-01 tokens + % | `tokens_used`, `token_limit`, `used_percentage` | `417k / 88k (474%)` |
| USAGE-02 reset countdown | `resets_at_epoch` - now | `resets in 2h 3m` |
| USAGE-03 burn rate | `burn_rate_tokens_per_minute` * 60 | `burn: 18.9M tok/hr` |
| ALERT-01 high-usage badge | `used_percentage` vs threshold (default 80) | icon label badge |

Formatting notes:
- **k/M formatting:** `tokens_used / 1000` -> `417k`; scale to `M` above ~1e6. Apply to burn rate too (values are large because sessions are token-heavy).
- **Burn rate unit conversion:** the field is per-MINUTE; USAGE-03 wants per-HOUR -> multiply by 60.
- **Percentage:** round to integer; must render values > 100 correctly (over-limit is normal).
- **Countdown:** `max(0, resets_at_epoch - now)` -> `Xh Ym`; show `resets now` / `0m` when <= 0.

## Threading + refresh (POLL-01)

- The CLI is multi-second; it MUST run on a background thread, never the Gtk main loop.
- Marshal results back to the main thread with `GLib.idle_add(...)` — the exact pattern `serve()` already uses to hand socket events to `mon.handle`. Reuse it; do not invent a new mechanism.
- Poll usage numbers on an interval (recommend ~30s; the CLI parses jsonl each call, so don't hammer it). The reset **countdown** should be recomputed locally from the cached `resets_at_epoch` on a light Gtk timer (`GLib.timeout_add_seconds`) so it stays live between polls without re-shelling the CLI.
- A single reusable poll function + `threading.Thread(daemon=True)` loop with `time.sleep(interval)` mirrors the existing stdlib-first, daemon-thread style.

## Icon-label conflict (design decision, feeds ALERT-01)

`rebuild_menu` currently owns the icon label:
```python
self.ind.set_label(("%d!" % waiting) if waiting else "", "")
```
ALERT-01's high-usage badge shares that single label surface. The plan must reconcile the waiting-count badge and the high-usage badge into one label string. Resolved per the design decision captured for this phase (see planner context).

## Existing patterns to reuse (keep the diff small)

- Env-var config with defaults (`CLAUDE_TRAY_ICON`, `CLAUDE_TRAY_WM_CLASS`) — add the poll interval / threshold as env vars in the same style if configurable.
- Defensive-by-default: swallow subprocess/parse errors into the "unavailable" state, never crash the helper.
- ASCII-only, stdlib-only for logic (`subprocess`, `json`, `threading`, `time`), PyGObject for UI.
- `rebuild_menu` is the single redraw path — usage rows belong there, above the existing separator/Quit, alongside session rows.

## Out of scope (confirmed against the CLI)

- seven_day limits: `null` for this account.
- cost/dollar fields: present in JSON but explicitly out of scope (usage %, not billing).
