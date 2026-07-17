---
phase: 01-usage-quota-monitoring-in-the-tray
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - claude-monitor.py
autonomous: true
requirements: [POLL-01, POLL-02, USAGE-01, USAGE-02, USAGE-03, ALERT-01]

must_haves:
  truths:
    - "USAGE-01: menu shows 'tokens_used / token_limit (pct%)' via k/M formatting and integer percent, rendering over-limit values correctly (used_percentage 473.5 -> '474%', never clamped to 100)."
    - "USAGE-02: menu shows a 'resets in Xh Ym' row derived from resets_at_epoch - now, and it stays live between polls via a light Gtk timer (no re-shelling to update the countdown)."
    - "USAGE-03: menu shows 'burn: <k/M> tok/hr' computed as burn_rate_tokens_per_minute * 60 (per-minute field converted to per-hour)."
    - "ALERT-01: when usage is available the icon label always leads with usage %, appends '!' when used_percentage > 80, then appends the existing waiting badge space-separated ('47% 2!', '83%! 2!'); when unavailable it falls back to the waiting-only badge exactly as today."
    - "POLL-01: usage is polled on a background daemon thread at ~30s and results are marshaled to the Gtk main thread via GLib.idle_add; the multi-second CLI never runs on the Gtk main loop."
    - "POLL-02: degradation does NOT gate on returncode == 0 — exit code 11 with valid JSON is treated as available; only timeout / empty stdout / json parse error / FileNotFoundError / missing limits.five_hour yield the 'usage unavailable' row, and session rows + click-to-focus keep working in that state."
  artifacts:
    - "claude-monitor.py (extended in place; no new runtime files, stdlib + PyGObject only)"
    - "parse_usage(), fetch_usage(), fmt_tokens(), fmt_countdown(), build_label(), poll_loop(), Monitor.apply_usage(), demo() + --selfcheck guard"
  key_links:
    - "poll_loop (bg thread) -> GLib.idle_add(mon.apply_usage, usage) -> rebuild_menu: the thread->main-loop marshal boundary."
    - "rebuild_menu is the single redraw path and owns BOTH the usage rows and set_label, reading self.usage for each."
    - "parse_usage() takes only stdout text and is independent of the subprocess returncode — this is what makes exit-code-11 read as available."
    - "burn rate * 60 conversion (per-minute source field -> per-hour display)."
---

<objective>
Extend the existing 128-line `claude-monitor.py` tray helper so the top bar surfaces
Claude Code quota usage sourced from the installed `claude-monitor` CLI: a tokens/percent
row (USAGE-01), a live reset countdown (USAGE-02), a burn-rate row (USAGE-03), a high-usage
icon badge (ALERT-01), all fed by a non-blocking background poll (POLL-01) that degrades to
a "usage unavailable" state without breaking session status or click-to-focus (POLL-02).

Purpose: know how much quota is left and when it resets at a glance, without opening a
terminal monitor.
Output: an extended `claude-monitor.py` with the pure usage logic (parse/format/label) plus
its `--selfcheck` and the Gtk wiring (poll thread, idle_add apply, live countdown, menu rows,
icon label). No new dependencies, no new runtime files.
</objective>

## Phase Goal (user story)

**As a** Claude Code user with the tray running, **I want to** see current 5-hour-window
usage, reset countdown, and burn rate in the tray menu with a high-usage badge on the icon,
**so that** I know how much quota is left and when it resets without launching a separate
terminal monitor.

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/01-usage-quota-monitoring-in-the-tray/01-RESEARCH.md
@claude-monitor.py
</context>

## Artifacts this phase produces

All added to `claude-monitor.py` (no new files):

Module-level constants:
- `USAGE_CLI` — absolute path to the CLI, `os.path.expanduser("~/.local/bin/claude-monitor")`.
- `PLAN_TIER` — `"max5"` (hardcoded plan tier, passed as `--plan max5`).
- `POLL_INTERVAL` — poll seconds, default `30`, env override `CLAUDE_TRAY_POLL_INTERVAL` (existing `CLAUDE_TRAY_*` style).
- `POLL_TIMEOUT` — subprocess timeout seconds (e.g. `15`).
- `USAGE_THRESHOLD` — `80`, hardcoded. NO env knob (ALERT-F1 is deferred — do not add one).

Functions / methods:
- `parse_usage(stdout)` — pure: `json.loads` the text, require `limits.five_hour`, return a small normalized dict `{tokens_used, token_limit, used_percentage, resets_at_epoch, burn_rate_per_min}` or `None`. Never sees the returncode.
- `fetch_usage()` — shells out to `USAGE_CLI --plan max5 --output json --once` with `POLL_TIMEOUT`, hands stdout to `parse_usage`, returns its result or `None` on timeout / empty / FileNotFoundError.
- `fmt_tokens(n)` — k/M formatter (`417000 -> "417k"`, `18936912 -> "18.9M"`).
- `fmt_countdown(secs_remaining)` — `"resets in Xh Ym"` / `"resets now"`.
- `build_label(usage, waiting)` — reconciles usage-% badge + high-usage `!` + waiting badge into one ASCII label string.
- `poll_loop(mon)` — daemon-thread loop: `fetch_usage()`, then `GLib.idle_add(mon.apply_usage, usage)`, then `time.sleep(POLL_INTERVAL)`.
- `Monitor.apply_usage(usage)` — idle_add target on the Gtk thread: store `self.usage`, `rebuild_menu()`, return `False`.
- `Monitor.usage_rows()` — small helper returning the usage menu-row label strings from `self.usage`.
- `demo()` + `--selfcheck` guard in `__main__` — assert-based self-check over a sample JSON fixture.

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Usage parse + format + label logic with a runnable self-check</name>
  <files>claude-monitor.py</files>
  <read_first>
    - claude-monitor.py (the whole file — reuse its env-var-with-default style, defensive error swallowing, ASCII-only, stdlib-first patterns)
    - .planning/phases/01-usage-quota-monitoring-in-the-tray/01-RESEARCH.md (JSON schema, field mapping, exit-code-11 gotcha, k/M and burn-*60 rules)
  </read_first>
  <behavior>
    Self-check asserts (embedded SAMPLE dict mirrors 01-RESEARCH.md: limits.five_hour with
    tokens_used 417000, token_limit 88000, used_percentage 473.5, resets_at_epoch = now + 7380;
    local.burn_rate_tokens_per_minute 315615.2; status.code 11):
    - parse_usage(json.dumps(SAMPLE)) returns a dict with used_percentage 473.5 — proving parse
      is independent of the (11) exit code, since parse_usage never receives a returncode.
    - parse_usage("") is None; parse_usage("not json") is None; parse_usage of a JSON doc with no
      limits.five_hour is None.
    - fmt_tokens(417000) == "417k"; fmt_tokens(88000) == "88k"; fmt_tokens(18936912) == "18.9M".
    - burn per-hour = round(315615.2 * 60) formats via fmt_tokens to "18.9M" (per-minute -> per-hour).
    - fmt_countdown(7380) == "resets in 2h 3m"; fmt_countdown(0) == "resets now".
    - percent render: round(473.5) == 474 (over-limit renders "474%", never clamped to 100).
    - build_label(SAMPLE_usage(pct=47), 2) == "47% 2!"; build_label(pct=83, 2) == "83%! 2!";
      build_label(pct=47, 0) == "47%"; build_label(None, 2) == "2!"; build_label(None, 0) == "".
  </behavior>
  <action>
    Add the module-level constants (USAGE_CLI via os.path.expanduser, PLAN_TIER "max5",
    POLL_INTERVAL from env CLAUDE_TRAY_POLL_INTERVAL default 30, POLL_TIMEOUT 15, USAGE_THRESHOLD 80
    hardcoded with a note that env-configurability is deferred per ALERT-F1).

    Implement parse_usage(stdout): json.loads inside try; on any exception return None; require a
    dict at limits.five_hour, else None; return the normalized dict pulling tokens_used, token_limit,
    used_percentage, resets_at_epoch from five_hour and burn_rate_per_min from local
    (burn_rate_tokens_per_minute, defaulting to 0 if absent). Do NOT inspect any returncode here.

    Implement fetch_usage(): subprocess.run of [USAGE_CLI, "--plan", PLAN_TIER, "--output", "json",
    "--once"] as an arg list (never shell=True), capture_output, text, timeout=POLL_TIMEOUT; wrap in
    try that swallows subprocess.TimeoutExpired and FileNotFoundError to None; pass result.stdout to
    parse_usage regardless of result.returncode; return parse_usage's value.

    Implement fmt_tokens(n): values >= 1e6 render as one-decimal M ("%.1fM"); otherwise integer k
    ("%dk" via round(n/1000)). fmt_countdown(secs): clamp negatives to 0; when <= 0 return
    "resets now"; else "resets in %dh %dm" from hours and minutes.

    Implement build_label(usage, waiting): when usage present, seg = "%d%%" % round(used_percentage),
    append "!" when used_percentage > USAGE_THRESHOLD; wseg = "%d!" % waiting when waiting else "";
    join the non-empty segments with a single space and return (usage-first, then waiting). When usage
    is None, return the existing waiting-only string ("%d!" % waiting or "").

    Add demo() building the SAMPLE dict and running the asserts in the behavior block, printing "ok".
    In __main__, dispatch to demo() when "--selfcheck" is in sys.argv, otherwise call main() (import
    sys where needed). Keep everything ASCII; use codedoc-style triple-quoted docstrings for prose
    doc blocks per project CLAUDE.md.
  </action>
  <verify>
    <automated>python3 claude-monitor.py --selfcheck</automated>
  </verify>
  <acceptance_criteria>
    - `python3 claude-monitor.py --selfcheck` exits 0 and prints ok.
    - claude-monitor.py contains `def parse_usage(`, `def fetch_usage(`, `def fmt_tokens(`, `def fmt_countdown(`, `def build_label(`, and `def demo(`.
    - parse_usage of the exit-code-11 sample (used_percentage 473.5) returns a dict, and round of that percentage renders "474%" (not clamped).
    - burn-rate assertion multiplies the per-minute field by 60 before formatting ("18.9M").
    - USAGE_THRESHOLD is a hardcoded literal 80 with no env lookup around it.
    - fetch_usage builds an argument list (no shell=True) and never branches on returncode.
  </acceptance_criteria>
  <done>All pure usage logic exists and its assert-based self-check passes via `--selfcheck`, with the exit-code-11 degradation and burn-*60 conversion pinned by asserts.</done>
</task>

<task type="auto">
  <name>Task 2: Wire usage into the tray — poll thread, idle_add apply, live countdown, menu rows, icon label</name>
  <files>claude-monitor.py</files>
  <read_first>
    - claude-monitor.py (Monitor.__init__, rebuild_menu, handle, serve, main — reuse the serve() daemon-thread + GLib.idle_add pattern verbatim; rebuild_menu is the single redraw path and currently owns set_label)
    - .planning/phases/01-usage-quota-monitoring-in-the-tray/01-RESEARCH.md (threading/refresh section, icon-label conflict, menu-row placement)
  </read_first>
  <action>
    In Monitor.__init__ initialize self.usage = None before the first rebuild_menu.

    Add Monitor.usage_rows(): when self.usage is None return a single-item list with "usage unavailable";
    otherwise return three strings — the USAGE-01 line "%s / %s (%d%%)" via fmt_tokens on tokens_used and
    token_limit plus round of used_percentage; the USAGE-02 line from fmt_countdown(resets_at_epoch - now)
    using time.time(); the USAGE-03 line "burn: %s tok/hr" via fmt_tokens(round(burn_rate_per_min * 60)).

    In rebuild_menu, after the session rows and before the existing SeparatorMenuItem/Quit, append one
    insensitive Gtk.MenuItem per string from usage_rows() (set_sensitive(False)). Replace the existing
    set_label line so it calls build_label(self.usage, waiting) instead of the waiting-only expression —
    this reconciles the usage badge and waiting badge on the single label surface. Session rows and their
    activate->focus wiring stay exactly as they are.

    Add Monitor.apply_usage(usage): assign self.usage = usage, call rebuild_menu(), return False (one-shot
    idle_add). Add poll_loop(mon): a while-True loop that calls fetch_usage(), then
    GLib.idle_add(mon.apply_usage, result), then time.sleep(POLL_INTERVAL) — mirroring serve()'s
    daemon-thread + idle_add marshaling. Never call fetch_usage on the Gtk main loop.

    In main(), after starting the serve thread, start threading.Thread(target=poll_loop, args=(mon,),
    daemon=True) and register a light live-countdown timer with GLib.timeout_add_seconds(POLL_INTERVAL,
    tick) where tick calls mon.rebuild_menu() and returns True so the "resets in Xh Ym" row recomputes
    locally from the cached resets_at_epoch between polls (no re-shelling).
  </action>
  <verify>
    <automated>python3 claude-monitor.py --selfcheck && rg -q "apply_usage" claude-monitor.py && rg -q "target=poll_loop" claude-monitor.py && rg -q "GLib.timeout_add_seconds" claude-monitor.py && rg -q "build_label\(self.usage" claude-monitor.py && rg -q "self.usage = None" claude-monitor.py && python3 -c "import ast; ast.parse(open('claude-monitor.py').read()); print('parse-ok')"</automated>
    <human-check>Run the tray (`python3 claude-monitor.py`): confirm the menu shows the three usage rows and the icon label leads with usage % (with `!` above 80%), session rows still focus on click, and killing/renaming the CLI flips the rows to a single "usage unavailable" while sessions keep working.</human-check>
  </verify>
  <acceptance_criteria>
    - `python3 claude-monitor.py --selfcheck` still exits 0 (task 1 logic intact) and the file parses (`ast.parse` -> parse-ok).
    - claude-monitor.py contains `self.usage = None`, `def apply_usage(`, `def usage_rows(`, `target=poll_loop`, `GLib.timeout_add_seconds`, and `build_label(self.usage`.
    - rebuild_menu appends usage rows above the existing separator/Quit and calls build_label for set_label.
    - poll_loop marshals results with GLib.idle_add (fetch_usage never called on the Gtk main loop).
    - Observable: with a valid sample applied, three usage rows render ("417k / 88k (474%)", "resets in Xh Ym", "burn: 18.9M tok/hr"); with usage None, exactly one insensitive "usage unavailable" row renders and the session rows + Quit remain.
    - A subprocess timeout / missing CLI leaves session rows and click-to-focus working (apply_usage(None) path).
  </acceptance_criteria>
  <done>Usage is polled off the Gtk main loop, applied via idle_add, rendered as menu rows with a live countdown, and badged onto the icon label; every failure mode degrades to "usage unavailable" without touching session status or click-to-focus.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| helper -> claude-monitor CLI (subprocess) | the helper execs an external binary at a user-home absolute path |
| CLI stdout -> parse_usage | untrusted external process output is parsed as JSON |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-01-01 | Tampering | fetch_usage subprocess exec | low | mitigate | Invoke as a fixed argument list (no shell=True); all args are hardcoded constants (`--plan max5 --output json --once`) with zero user-input interpolation. |
| T-01-02 | Denial of Service | fetch_usage / parse_usage | low | mitigate | Bound the call with POLL_TIMEOUT (subprocess timeout) and swallow TimeoutExpired; parse_usage wraps json.loads in try/except so malformed or oversized output yields the "usage unavailable" state, never a crash of the long-lived helper. |
| T-01-03 | Tampering | USAGE_CLI resolved from ~/.local/bin | low | accept | The binary lives under the user's own home at the same trust level as the tray helper itself; if that path is attacker-controlled the whole session is already compromised. No elevation beyond the invoking user. |

No package-manager installs this phase (stdlib + already-present PyGObject only), so no supply-chain (T-01-SC) row applies. No network calls, no privileged operations, no untrusted user input reach this code.
</threat_model>

<verification>
- `python3 claude-monitor.py --selfcheck` passes (pure parse/format/label logic, incl. exit-code-11 degradation and burn-*60).
- Structural: file parses; contains parse_usage/fetch_usage/fmt_tokens/fmt_countdown/build_label/poll_loop/apply_usage/usage_rows; poll runs on a daemon thread and marshals via GLib.idle_add; icon label uses build_label; live countdown via GLib.timeout_add_seconds.
- Manual (human-check): running the tray shows the three usage rows + high-usage icon badge, degrades to "usage unavailable" on CLI failure, and keeps session rows + click-to-focus in every state.
</verification>

<success_criteria>
All six phase requirements are satisfied in `claude-monitor.py`:
- USAGE-01 tokens/percent row (over-limit rendered correctly), USAGE-02 live reset countdown, USAGE-03 per-hour burn rate.
- ALERT-01 icon label leads with usage %, appends `!` above 80%, then the waiting badge; falls back to waiting-only when unavailable.
- POLL-01 background daemon-thread poll (~30s) marshaled via GLib.idle_add, Gtk never blocks.
- POLL-02 timeout/empty/parse-error/missing-CLI/missing-five_hour -> "usage unavailable" with session status + click-to-focus intact; degradation never gates on returncode == 0.
</success_criteria>

<output>
Create `.planning/phases/01-usage-quota-monitoring-in-the-tray/01-01-SUMMARY.md` when done.
</output>