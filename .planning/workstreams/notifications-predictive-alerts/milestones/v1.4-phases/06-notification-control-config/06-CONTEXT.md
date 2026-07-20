# Phase 6: Notification Control & Config - Context

**Gathered:** 2026-07-16
**Status:** Ready for planning

<domain>
## Phase Boundary

The user decides what fires: per-event tray toggles (waiting / done / 5h alert /
7d alert), one global mute, and a configurable badge threshold -- all persisted
in a small JSON config under `~/.claude/`, corruption-tolerant, no restart
required for a toggle to take effect.

- **CFG-01** -- four independent on/off toggles, one per event type.
- **CFG-02** -- one global "mute all" toggle.
- **CFG-03** -- persistence across restarts.
- **CFG-04** -- total tolerance for a missing/corrupt/malformed config (same bar
  as `parse_history`, per the `260713-fry` precedent).
- **CFG-05** -- badge threshold becomes configurable, replacing the hardcoded
  `USAGE_THRESHOLD = 80` at `claude-monitor.py:51` (comment there currently says
  "do NOT add an env lookup" -- that comment is now stale and must be updated or
  removed as part of this phase).

Does NOT include: new event types, quiet hours (NOTIF-F1), per-event sound/urgency
(NOTIF-F2), a hard-threshold push alert (ALERT-F1), new polling, new dependencies,
Wayland support.

</domain>

<decisions>
## Implementation Decisions

### Config file scope and relationship to existing env vars (CFG-03)
- **D-01:** **Env vars stay the default; the config file is an additive
  override layer, not a replacement.** `CLAUDE_TRAY_ICON`, `CLAUDE_TRAY_PLAN`,
  `CLAUDE_TRAY_POLL_INTERVAL`, `CLAUDE_TRAY_WM_CLASS`, `CLAUDE_TRAY_HISTORY_DAYS`
  keep their current meaning and behavior unchanged. The new config file governs
  only the settings this phase introduces: the four event toggles, global mute,
  and badge threshold. It does not fold in or migrate any existing env var.
- **D-02:** **File location and name: `~/.claude/tray-config.json`.** Sibling to
  `~/.claude/usage-history.jsonl`; the `tray-` prefix matches the existing
  `CLAUDE_TRAY_*` env var naming convention.

### Tray menu shape for toggles (CFG-01, CFG-02)
- **D-03:** **One "Notifications" submenu, not flat top-level rows.** The
  existing top-level menu (sessions, usage rows, trend rows, dashboard, quit) is
  already long; a single submenu entry keeps it flat. Inside the submenu: 4
  `Gtk.CheckMenuItem` rows (waiting / done / 5h alert / 7d alert) plus a "Mute
  all" checkbox.
- **D-04:** **Per-event toggles keep their own state while muted; mute wins at
  the gate, not in the UI.** Turning "Mute all" on does NOT grey out or hide the
  per-event checkboxes -- they stay interactive and reflect whatever the user
  last set. The `notif_allowed(kind)` gate (currently a stub returning `True` at
  `claude-monitor.py:63-65`) becomes: `not muted and per_event_flags[kind]`.
  Turning mute back off instantly restores prior per-event state with no
  re-sync step, because nothing was ever changed in the toggles themselves.

### Badge threshold config (CFG-05)
- **D-05:** **Preset steps via `Gtk.RadioMenuItem`, not free-text entry.** A
  small submenu (likely nested under "Notifications" or a sibling "Badge
  threshold" submenu -- Claude's discretion) offers fixed choices, e.g. 70% /
  80% / 90% / 95%, as radio items. No text-entry widget -- GTK indicator menus
  handle those poorly, and a stepped choice is sufficient for "configurable."
  This replaces the hardcoded `USAGE_THRESHOLD = 80` constant; the stale
  "do NOT add an env lookup" comment at `claude-monitor.py:51` must be
  updated/removed since this phase intentionally makes it configurable (via
  config file + menu, not via env var, per D-01's scope).

### Claude's Discretion
- Exact preset values for the badge threshold submenu (70/80/90/95 suggested,
  not mandated).
- Whether the badge-threshold submenu nests inside "Notifications" or sits as
  its own top-level submenu -- either satisfies CFG-05's "configurable" bar.
- JSON schema/key names inside `tray-config.json`.
- Where in-memory config state lives (e.g. a `Config` dataclass vs a plain
  dict) and how/when it's read (once at startup vs re-read on menu rebuild) --
  as long as a toggle takes effect on the very next event with no restart
  (CFG-01's acceptance bar).
- Corrupt-config fallback mechanics -- mirror `parse_history`'s total-tolerance
  pattern; exact code shape is implementation detail.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and requirements
- `.planning/workstreams/notifications-predictive-alerts/ROADMAP.md` -- "Phase 6"
  section: Goal, Depends on, Success Criteria, and the three Notes (CFG-04's
  precedent bar, CFG-05 closing the deferred threshold item, the env-var open
  question this CONTEXT.md now settles).
- `.planning/workstreams/notifications-predictive-alerts/REQUIREMENTS.md` --
  CFG-01..05 full text; the "Configuration" Open Questions entry (now settled by
  D-01/D-02 above); Out of Scope list (no quiet hours, no per-event sound/urgency,
  no hard-threshold push).
- `.planning/PROJECT.md` -- standing constraints: stdlib + PyGObject only, X11
  only, one background poll, nothing blocking the Gtk main loop.

### Source (single file -- read these regions)
- `claude-monitor.py:51` -- `USAGE_THRESHOLD = 80`, the constant CFG-05 makes
  configurable. Comment here is stale post-phase and must be updated.
- `claude-monitor.py:63-65` -- `notif_allowed(kind)`, the mute-gate stub Phase 5
  left exactly for this phase to wire up. Currently `return True` unconditionally.
- `claude-monitor.py:1467` -- `self.menu = Gtk.Menu()` / `rebuild_menu` (starts
  `:1560`) -- where the new "Notifications" submenu and threshold radio items get
  built. Menu is fully rebuilt each call; no incremental diffing today.
- `claude-monitor.py:136-138` -- `HISTORY_DAYS` -- an example of the existing
  "env var with int-parse fallback on `ValueError`" pattern, useful precedent for
  config value parsing.
- `claude-monitor.py:1338` (`_hostile` assertion) and the surrounding
  `history_numeric` -- the corruption-tolerance pattern CFG-04 must match.
- `claude-monitor.py:1033` -- `demo()` / `--selfcheck` -- established location for
  pure-function assertions (e.g. gate logic, threshold parsing).

### Prior phase context (patterns that bind)
- `.planning/workstreams/notifications-predictive-alerts/phases/05-notification-path-event-producers/05-CONTEXT.md`
  -- the mute-hook handoff: "Phase 5 owns the hook point... Do not build the
  config file, the toggles, or persistence here" and "One gate function, four
  event-type keys (waiting / done / 5h / 7d) plus a global."
- `.planning/workstreams/notifications-predictive-alerts/phases/05-notification-path-event-producers/05-RESEARCH.md`
  -- D-Bus binding details and landmines relevant if the gate needs to reach the
  notification emit path.
- `.planning/codebase/OVERVIEW.md` (if present) -- general codebase map.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`notif_allowed(kind)`** (`:63-65`) -- the exact seam this phase fills.
  Signature already fixed: `kind` in `{"waiting", "done", "5h", "7d"}`.
- **`HISTORY_DAYS` env-parse pattern** (`:136-138`) -- `try/except ValueError`
  around `int(os.environ.get(...))`, falling back to a default. Reusable shape
  for any numeric config parsing, though CFG-05's actual input path is a menu
  radio item, not an env var (per D-01).
- **`rebuild_menu`** (`:1560+`) -- already the single place the whole menu is
  reconstructed; the Notifications submenu and threshold items are new children
  added here, following the existing `Gtk.MenuItem` / `mi.connect("activate", ...)`
  idiom already used for `dash` and `q` (quit).

### Established Patterns
- **Total tolerance at the edges.** `parse_history` swallows corruption;
  `poll_loop`'s body has a blanket `except` + `traceback.print_exc()`
  (`260713-fry`). Config read/write must follow the same posture -- CFG-04 is
  this pattern applied to a new file.
- **`ponytail:` comments** mark deliberate simplifications with their ceiling --
  follow this convention for any new shortcuts (e.g. fixed threshold presets).
- Menu items use plain `Gtk.MenuItem` today; `Gtk.CheckMenuItem` and
  `Gtk.RadioMenuItem` are new but standard GTK3/PyGObject widgets, no new
  dependency.

### Integration Points
- `notif_allowed(kind)` (`:63-65`) -- gate logic changes here; called from
  `emit_notif` (`:1490`), which already short-circuits on `not notif_allowed(kind)`.
- `rebuild_menu` (`:1560+`) -- new submenu construction point.
- `Monitor.__init__` (near `:1440`) -- likely where config is loaded once at
  startup (mirrors how `self.dash_ready`, `self.notif_slots` etc. are
  initialized there).

</code_context>

<specifics>
## Specific Ideas

- Config file: `~/.claude/tray-config.json`, additive over `CLAUDE_TRAY_*` env
  vars (D-01, D-02).
- Menu shape:
  ```
  Notifications >
    [x] Mute all
      ---
    [x] Waiting for input
    [x] Session finished
    [x] 5-hour quota alert
    [x] 7-day quota alert
  ```
  (submenu, D-03; mute-all does not disable the per-event rows, D-04)
- Badge threshold as radio steps, not free text (D-05): 70% / 80% / 90% / 95%
  suggested.

</specifics>

<deferred>
## Deferred Ideas

- **Migrating existing `CLAUDE_TRAY_*` env vars into the config file** --
  explicitly rejected for this phase (D-01). Config only covers CFG-01..05;
  existing env vars are untouched. Revisit only if a future phase wants unified
  settings.
- **Free-text/arbitrary numeric entry for the badge threshold** -- rejected in
  favor of preset radio steps (D-05); GTK tray menus handle text entry poorly.
- Everything already deferred in REQUIREMENTS.md (NOTIF-F1 quiet hours, NOTIF-F2
  per-event sound/urgency, ALERT-F1 hard-threshold push) -- unaffected by this
  discussion, still deferred.

### Reviewed Todos (not folded)
None -- `todo.match-phase` returned zero matches for Phase 6.

</deferred>

---

*Phase: 6-Notification Control & Config*
*Context gathered: 2026-07-16*
