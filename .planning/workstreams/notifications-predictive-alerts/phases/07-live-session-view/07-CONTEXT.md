# Phase 07: Live Session View - Context

**Gathered:** 2026-07-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Embed the tray's in-memory session list (`self.sessions` in `class Monitor`) into
the generated dashboard as a **session panel** -- read-only, rendered on the
existing poll-tick regeneration and browser meta-refresh. No new IPC, socket, or
persistence (SESSVIEW-03). The dashboard stays fully self-contained (SESSVIEW-05 /
DASH-06). Requirements: SESSVIEW-01..05.

**In scope:** a panel listing tracked sessions with status + project dir + time in
current state; a clean empty state; live duration counter. **Out of scope:** any
new data source, per-session token/usage detail, session history/persistence,
clickable focus-from-browser (browser cannot focus a tmux pane) -- those are future.
</domain>

<decisions>
## Implementation Decisions

### Duration / freshness (SESSVIEW-02, SESSVIEW-03)
- **D-01:** Add a per-session `entered` epoch (unix seconds) to the `self.sessions`
  dict. Set it in `Monitor.handle()` **only when the status actually changes**
  (old status != new event), not on every message -- otherwise the counter resets
  on every keepalive. This is the ONE new piece of in-memory state; nothing is
  persisted (upholds SESSVIEW-03).
- **D-02:** Duration renders as a **client-side JS live ticker**: embed `entered`
  in the JSON payload and let inline JS compute `now - entered` every second and
  format it (e.g. "waiting 3m 20s"). No server round-trip; the panel's add/remove
  of sessions still rides the existing meta-refresh cadence -- only the counter is
  live between refreshes.

### Panel layout (SESSVIEW-01)
- **D-03:** Compact **table**: columns `project dir | status | duration`.
- **D-04:** Sort **waiting -> running -> done** (attention-first).
- **D-05:** Status shown as a **CSS colored dot** (a `border-radius` span, NOT a
  unicode glyph -- keep code ASCII per project rule), colors matching the tray's
  running/waiting/done semantics and the existing dashboard palette.

### Which sessions shown (SESSVIEW-01)
- **D-06:** Show **all** sessions currently in `self.sessions` (running/waiting/
  done). `done` rows linger until their `end` event pops them -- render them
  **dimmed**. Mirrors what the tray menu already shows.

### Empty state (SESSVIEW-04)
- **D-07:** The panel is **always present**; when there are no sessions it renders
  "No active Claude Code sessions" inside it. The panel never disappears or reflows
  the rest of the page.

### Security + self-contained (SESSVIEW-05, DASH-06)
- **D-08:** Pass the session snapshot **into** `render_dashboard` as data and emit
  it in the JSON payload (exactly like `usage`/`usage7` via `_embed_json`); render
  the rows **client-side via DOM `textContent`**, NOT server-side HTML string
  interpolation. This keeps a project dir named `<b>x</b>` inert (no markup
  injection -- same class of hazard the notifier avoided by keeping `dir` out of the
  Pango-markup body) and keeps the page self-contained: inline JS only, no external
  refs. The existing `--selfcheck` no-external-ref assertion must still pass.

### Claude's Discretion
- Exact duration format strings, the dot colors (match existing palette), column
  widths, and where the panel sits on the page (planner picks a sensible spot --
  e.g. above the usage chart).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope
- `.planning/workstreams/notifications-predictive-alerts/ROADMAP.md` -- Phase 7 section (goal + 5 success criteria)
- `.planning/workstreams/notifications-predictive-alerts/REQUIREMENTS.md` -- SESSVIEW-01..05
- `.planning/seeds/SEED-005-live-session-view-in-dashboard.md` -- scouting notes + the open questions this discussion settled

### Code being touched (post-restructure layout)
- `claude-monitor.py` -- `class Monitor`: `self.sessions` init (line ~60), `handle()` (line ~365, where `entered` is added), `write_dashboard()` (calls `render_dashboard`)
- `claude_monitor/dashboard.py` -- `render_dashboard(records, now)` + the `_DASH_*` HTML/CSS/JS blob + `_embed_json`; the JSON payload dict is where `sessions` gets added
- `claude_monitor/test_claude_monitor.py` -- where the new `--selfcheck` assertions land

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_embed_json` + the `payload` dict in `render_dashboard` (dashboard.py): the exact
  mechanism to ship `sessions` to the client safely -- reuse it, don't hand-roll.
- The existing inline `_DASH_JS` block + `<meta http-equiv="refresh">`: the session
  panel's markup, dot CSS, and live-ticker JS all live inline here (self-contained).
- Tray menu row format `"%s  [%s]" % (s["dir"], s["status"])` (claude-monitor.py
  ~line 250): the semantic model for what a session row shows.

### Established Patterns
- **Self-contained dashboard (DASH-06):** no `<link>`, no `src=`, no external URLs;
  `--selfcheck` asserts this -- the new panel/JS must not break it.
- **Off-Gtk generation on the poll tick:** the dashboard is regenerated on the
  existing tick; `dashboard.py` is pure (no gi/GTK). `Monitor` (which owns
  `self.sessions` and runs on the Gtk thread) must snapshot the sessions into a plain
  list and pass it into `render_dashboard` -- do NOT import GTK into dashboard.py.
- **Markup-safety precedent (notif T-05-04):** untrusted `dir` strings must never be
  interpolated into unescaped markup -- D-08's JSON+textContent path is the safe shape.

### Integration Points
- `Monitor.handle()` -- add `entered` timestamp on status change (D-01).
- `Monitor.write_dashboard()` -- build `sessions = [{dir, status, entered}, ...]` from
  `self.sessions` and pass to `render_dashboard(records, now, sessions=...)`.
- `render_dashboard` signature gains a `sessions` param (default empty for the
  existing `--selfcheck` callers / empty-state test).

</code_context>

<specifics>
## Specific Ideas

"See all live sessions at a glance without opening the tray menu." The tray menu
already lists `dir [status]`; the dashboard panel is the same information, always
visible, with a live duration counter added.

</specifics>

<deferred>
## Deferred Ideas

- Click-a-session-in-browser to focus its tmux pane -- a browser `file://` page
  cannot focus a pane; would need the notification/IPC path. Future.
- Per-session token/usage detail in the panel -- no per-session usage data source
  exists; out of scope (no new data source).

None else -- discussion stayed within phase scope.

</deferred>

---

*Phase: 07-live-session-view*
*Context gathered: 2026-07-18*
