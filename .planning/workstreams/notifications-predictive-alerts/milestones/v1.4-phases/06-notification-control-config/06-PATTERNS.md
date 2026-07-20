# Phase 6: Notification Control & Config - Pattern Map

**Mapped:** 2026-07-16
**Files analyzed:** 1 (single-file project: `claude-monitor.py`)
**Analogs found:** 5 / 5 (all patterns found in-file; no cross-file analogs since this is a single-script project)

## File Classification

Only one file is created or modified this phase: `claude-monitor.py` (existing, 1898 lines).
Since there's no second file to compare against, "analog" here means the closest existing
pattern *within the same file* that the new code should mirror.

| New/Modified Region | Role | Data Flow | Closest Analog (same file) | Match Quality |
|---|---|---|---|---|
| `notif_allowed(kind)` gate rewrite | pure function / gate | request-response | `sess_should_notify` (:68-73), `alert_should_fire` (:122-132) — small pure predicate functions | exact |
| Config file load (`~/.claude/tray-config.json`, tolerant) | utility / file I/O | CRUD (read) | `parse_history` (:285-301) — tolerant line-by-line JSON parse | exact |
| Config file save (atomic write) | utility / file I/O | CRUD (write) | `prune_history` (:313-335) — temp file + `os.replace` atomic write pattern | exact |
| Numeric/threshold config value parsing | utility | transform | `HISTORY_DAYS` env-parse (:136-140) — `try/except ValueError` with fallback | exact |
| `Monitor.__init__` config load | provider / init | request-response | existing `self.sessions = {}`, `self.notif_slots = {}` init block (:1440-1450) | exact |
| Notifications submenu + threshold radio items | component (menu builder) | request-response | `rebuild_menu` (:1564-1593) — existing `Gtk.MenuItem` + `.connect("activate", ...)` idiom (`dash`, `q` items) | exact |
| Self-check assertions for gate/config parsing | test | transform | `demo()` (:999-1018+, extends to ~:1348) — assert-based `--selfcheck` block, `_hostile` corruption-tolerance assertions (:1332-1348) | exact |

## Pattern Assignments

### `notif_allowed(kind)` rewrite (pure gate function)

**Current stub** (`claude-monitor.py:63-65`):
```python
def notif_allowed(kind):
    """Mute gate. `kind` is one of "waiting", "done", "5h", "7d". Currently always open."""
    return True  # ponytail: seam only; a config-driven mute replaces this body.
```

**Analog for shape** — `alert_should_fire` (:122-132), a small pure predicate taking explicit
state as args rather than reaching into globals implicitly:
```python
def alert_should_fire(armed_reset, reset, p, now):
    """One alert per cap per window, re-armed when the window rolls. Pure.
    `armed_reset` is the reset epoch of the window this cap last alerted in (None if
    never). A reset epoch identifies the window, so a changed epoch re-arms the cap.
    """
    if not _is_num(reset):
        return False  # the 7d cap is absent on an older CLI -> silence
    if armed_reset == reset:
        return False  # already alerted in THIS window
    return alert_due(p, now)
```

Per CONTEXT.md D-04, the new body is: `return not muted and per_event_flags[kind]`.
Keep it pure/testable — read from a module-level or passed-in config dict, don't do file I/O
inside the gate itself (config should already be loaded into memory, e.g. on `Monitor`).

**Call site (unchanged, already wired by Phase 5)** — `emit_notif` (:1503):
```python
if self.notif is None or not notif_allowed(kind):
    return
```

### Config load: `~/.claude/tray-config.json` (CFG-03, CFG-04)

**Analog:** `parse_history` (`claude-monitor.py:285-301`)
```python
def parse_history(text):
    """Tolerant loader: JSON objects with a numeric "t", in order. Skips blank, unparseable
    (a half-written line from a killed process) and wrong-shape lines. Every reader routes
    through here, so a downstream history_keep(rec["t"]) cannot raise on garbage.
    """
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict) and isinstance(rec.get("t"), (int, float)):
            out.append(rec)
    return out
```
Copy the shape: `try: json.load(...) except Exception: return DEFAULTS`. Since the config is a
single JSON object (not JSONL), the tolerant-parse function should be even shorter — a single
`try/except (OSError, Exception)` around `json.loads` + a per-key `isinstance`/type check
against a defaults dict, falling back to per-key defaults rather than failing the whole file on
one bad key (mirrors `HISTORY_DAYS` bad-env fallback below, applied per-field).

**Numeric-with-fallback precedent** — `HISTORY_DAYS` (`claude-monitor.py:136-140`):
```python
try:
    HISTORY_DAYS = int(os.environ.get("CLAUDE_TRAY_HISTORY_DAYS", "30"))
except ValueError:
    HISTORY_DAYS = 30  # bad env -> default
```
Use this shape for validating the badge-threshold value loaded from config (must be one of the
preset ints; anything else -> default 80).

**Corruption-tolerance test precedent** — `_hostile` block (`claude-monitor.py:1332-1348`),
shows the project's established style for a "garbage in, silence out" assertion:
```python
_hostile = {
    ...
}
assert history_numeric([_hostile]) == [_hostile]  # it does pass that gate
assert usage7_series([_hostile]) == []
```
Follow this style for a `--selfcheck` assertion that a malformed `tray-config.json` (missing
keys, wrong types, truncated file) yields the default config rather than raising.

### Config save: atomic write (CFG-03)

**Analog:** `prune_history` (`claude-monitor.py:313-335`) — temp file + `os.replace`:
```python
tmp = None
try:
    ...
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(HISTORY_PATH))
    with os.fdopen(fd, "w") as f:
        for r in survivors:
            f.write(json.dumps(r) + "\n")
    os.replace(tmp, HISTORY_PATH)
    tmp = None  # replace succeeded; nothing to clean up
except OSError:
    return
finally:
    if tmp is not None:
        try:
            os.remove(tmp)
        except OSError:
            pass
```
Reuse this exact temp+replace+cleanup shape for writing `~/.claude/tray-config.json` whenever a
toggle or threshold changes (menu item `activate` handler calls save immediately — no explicit
"Save" button, matches the "no restart required" requirement).

### `Monitor.__init__` config load (CFG-01..05 wiring)

**Analog:** existing init block (`claude-monitor.py:1440-1450`):
```python
def __init__(self):
    self.sessions = {}  # session_id -> {dir,status,pane,tmux,cwd}
    self.usage = None
    self.usage_misses = 0
    self.trends = None
    self.dash_ready = False

    self.notif_slots = {}
    self.notif_acts = {}
    self.alert_armed = {}
    self.notif = None
    ...
```
Add `self.config = load_config()` (or similar) in this same init block, before
`self.rebuild_menu()` is called at :1474, since the submenu's checkbox/radio initial states
need `self.config` populated first. Comment style: one-line purpose comment per attribute,
matching the existing lines.

### Notifications submenu + threshold radio items (CFG-01, CFG-02, CFG-05)

**Analog:** `rebuild_menu` (`claude-monitor.py:1564-1593`), existing `Gtk.MenuItem` idiom used
for `dash` and `q`:
```python
dash = Gtk.MenuItem.new_with_label("Open Usage Dashboard")
dash.connect("activate", self.open_dashboard)
dash.set_sensitive(self.dash_ready)
self.menu.append(dash)
self.menu.append(Gtk.SeparatorMenuItem.new())
q = Gtk.MenuItem.new_with_label("Quit monitor")
q.connect("activate", lambda _w: Gtk.main_quit())
self.menu.append(q)
```
The full menu-teardown-and-rebuild pattern at the top of the function:
```python
def rebuild_menu(self):
    for c in self.menu.get_children():
        self.menu.remove(c)
    ...
    self.menu.show_all()
```
New code: build a `Gtk.Menu()` for the "Notifications" submenu, attach `Gtk.CheckMenuItem` rows
(bound to `self.config["notify_waiting"]` etc. via `.set_active()` on build and
`.connect("toggled", ...)` for write-back + `rebuild_menu()`), and a nested `Gtk.RadioMenuItem`
group for the threshold presets (group members share a `Gtk.RadioMenuItem.new_with_label_from_widget`
chain — standard PyGObject, no new dependency). Attach the submenu via
`Gtk.MenuItem.new_with_label("Notifications"); mi.set_submenu(sub)`. Since `rebuild_menu` fully
tears down and rebuilds every call (no incremental diffing anywhere in this file), rebuild the
submenu from `self.config` on every call too — do not try to preserve GTK widget identity.

Since `rebuild_menu` is called after every mutation elsewhere in this class (`apply_usage`,
`handle`, `on_click`), a toggle's `"toggled"` handler should: write `self.config`, persist to
disk, then call `self.rebuild_menu()` — same pattern already used everywhere else in this class
for "state changed -> redraw".

### `USAGE_THRESHOLD` constant -> configurable (CFG-05)

**Current** (`claude-monitor.py:50-51`):
```python
# High-usage badge threshold (percent). Hardcoded on purpose: do NOT add an env lookup.
USAGE_THRESHOLD = 80
```
This comment is stale per CONTEXT.md D-05 and must be updated/removed. `USAGE_THRESHOLD` is read
at :257-258 in a pure function (`hot = usage["used_percentage"] > USAGE_THRESHOLD or ...`) — that
call site takes the module constant directly. Converting to configurable means either (a)
replacing the module-level constant with a value read from `self.config` at the one call site
that needs it, or (b) keeping a module-level mutable default that the config loader overwrites
at startup and the radio-item handler overwrites at runtime — pick whichever keeps the pure
function pure (prefer passing threshold as an explicit function arg where it's already a pure
function, matching this file's existing style of pure functions taking explicit args rather than
reading globals, e.g. `alert_should_fire(armed_reset, reset, p, now)`).

## Shared Patterns

### Total tolerance at the edges (CFG-04)
**Source:** `parse_history` (:285-301), `append_history` (:304-310, bare `except OSError: return`),
`prune_history` (:313-335)
**Apply to:** config load and config save functions
```python
def append_history(record):
    """Append one record as a JSON line. OSError -> history just doesn't persist."""
    try:
        with open(HISTORY_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        return
```
Every file-I/O function in this codebase degrades silently rather than raising. Config
read/write must match: a missing file, corrupt JSON, wrong-type value, or unwritable directory
all degrade to "use the in-memory default" / "skip this write," never a crash or traceback.

### `ponytail:` comments for deliberate simplification
**Source:** e.g. `claude-monitor.py:65` (the current stub), `:131`, `:1500`, `:1654`
```python
return True  # ponytail: seam only; a config-driven mute replaces this body.
```
Use this convention for any deliberate shortcut introduced this phase — e.g. fixed threshold
presets (no free-text entry), no incremental menu diffing, no debounce on rapid toggle clicks.

### Menu rebuild-on-mutation
**Source:** `apply_usage` (:1644 `self.rebuild_menu()`), `handle` (:1690, :1707+),
`on_click` (:1561)
**Apply to:** every toggle/radio "activate"/"toggled" handler — write config, then
`self.rebuild_menu()`, same as every other state mutation in `Monitor`.

## No Analog Found

None — every new region has a clear same-file precedent to mirror (single-file project, no
missing architectural pattern).

## Metadata

**Analog search scope:** `claude-monitor.py` (only file in project; no `src/`, no other modules)
**Files scanned:** 1
**Pattern extraction date:** 2026-07-16
</content>
