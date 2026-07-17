---
phase: 06-notification-control-config
verified: 2026-07-16T12:42:34Z
status: passed
score: 16/22 must-haves verified
behavior_unverified: 3 # present + wired, live-behavior invariant not exercised by an automated test
overrides_applied: 0
human_verification:

  - test: "Uncheck 'Waiting for input' in the Notifications submenu, then trigger a session entering the waiting state with no restart of the helper."
    expected: "No popup fires, but the session still appears in the tray menu with a waiting status and its '!' indicator. Re-checking the box and triggering waiting again makes the popup fire (ROADMAP SC1, CFG-01)."
    why_human: "Requires a live GTK indicator + a real hook event; cannot be exercised headlessly."

  - test: "Check 'Mute all', trigger a waiting or done event, observe the session row / usage rows / icon badge; then uncheck 'Mute all' and inspect the four event checkboxes."
    expected: "No popup fires while muted, but session rows, usage rows, and the icon badge keep updating. Unmuting restores exactly the four event checkboxes' prior states, with no re-sync step (ROADMAP SC2, CFG-02, D-04)."
    why_human: "Requires live GTK interaction and observing the running daemon; the mute-wins gate logic itself is already proven by an automated mutation test, but 'rows/badge keep working' is a live-render property."

  - test: "Open 'Badge threshold', pick a value other than the current one, observe the tray icon's badge on the next poll tick; restart the helper and reopen the menu."
    expected: "Exactly one radio stays active (no double-select), the badge threshold changes on the next poll, and the picked value is still selected after a restart (ROADMAP SC3 + SC5, CFG-05)."
    why_human: "Requires a live GTK menu, a real poll tick, and a helper restart; cannot be exercised headlessly."

  - test: "Simulate a process kill mid-write of tray-config.json (e.g. SIGKILL the helper between os.fdopen's json.dump and os.replace, or fuzz-inject a crash there) and inspect the resulting file."
    expected: "The previous tray-config.json (or no file, on a first-ever write) is intact -- never a truncated/partial JSON file (CFG-03 concurrency probe)."
    why_human: "Tagged verification: backstop in 06-01-PLAN.md -- this is a runtime/OS-level atomicity claim (os.replace() semantics) that no wired test in the codebase exercises. Symbol presence (the temp-file + os.replace shape mirroring prune_history) is not explicit evidence of the claim; a held-out crash-injection test is needed."
    reason: insufficient_spec

  - test: "Have one process call load_config() while another concurrently calls save_config() (racing os.replace()) and confirm the reader never observes a half-written file."
    expected: "load_config() sees either the whole old file or the whole new file, never a partial one (CFG-04 concurrency probe)."
    why_human: "Tagged verification: backstop -- same reasoning as above; no wired concurrent-access test exists in this codebase."
    reason: insufficient_spec

  - test: "Drive poll_loop's thread (notif_allowed reads) concurrently with a Gtk main-thread menu toggle (self.config mutation) under real thread scheduling, and confirm no torn read/write and no observed gate-order violation."
    expected: "CPython's GIL makes a single dict key read/write atomic; the mute-check-before-per-event-lookup order (Python's `and` short-circuit) holds under concurrent access (CFG-01/CFG-02 concurrency + ordering probe)."
    why_human: "Tagged verification: backstop. The short-circuit ORDER is directly confirmed by reading `notif_allowed`'s source (`not config[\"mute_all\"] and config[NOTIF_KEYS[kind]]`) -- Python's `and` is a language guarantee, not runtime-dependent. The GIL cross-thread-atomicity half of this claim is not exercised by any wired concurrency test, so the compound truth is abstained rather than partially graded."
    reason: insufficient_spec
---

# Phase 6: Notification Control & Config Verification Report

**Phase Goal:** The user decides what fires -- per-event toggles, one global mute, and a configurable badge threshold, persisted across restarts and safe against a corrupt config.
**Verified:** 2026-07-16T12:42:34Z
**Status:** human_needed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Toggle states survive a helper restart (ROADMAP SC3, CFG-03) | VERIFIED | Ran the plan's temp-dir round-trip script directly: `save_config(cfg)` -> `load_config()` returns `cfg` exactly, for a cfg with every key changed from default. |
| 2 | Missing/unreadable/malformed config file falls back to defaults, never crashes (ROADMAP SC4, CFG-04) | VERIFIED | Same script: `load_config()` against a nonexistent path, then against a file containing `'{not json'`, both return `DEFAULT_CONFIG`, no exception. |
| 3 | `mute_all=True` + a per-event flag `True` -> gate returns `False` (D-04, CFG-02) | VERIFIED | `notif_allowed` source: `return not config["mute_all"] and config[NOTIF_KEYS[kind]]` (claude-monitor.py:138). Mutation test: changing `and` to `or` makes `--selfcheck` fail on `notif_allowed("waiting", {**DEFAULT_CONFIG, "mute_all": True}) is False`; reverted, tree clean. |
| 4 | Badge threshold read from config, not a fixed constant (data-model half of SC5, CFG-05) | VERIFIED | `build_label(usage, attention, threshold=USAGE_THRESHOLD)` (claude-monitor.py:320); `rebuild_menu` calls it with `self.config["usage_threshold"]` (claude-monitor.py:1755), confirmed via grep count == 1. |
| 5 | `notif_allowed(kind, config)` is pure -- no side effect on config | VERIFIED | Source: a single `return` expression, no assignment to `config` anywhere in the function body. |
| 6 | A config missing any of the six keys falls back per-key, not whole-file (CFG-01/02/05 empty-input probes) | VERIFIED | `--selfcheck` assertion `parse_config(json.dumps({"mute_all": True}))["notify_waiting"] is True` (line 1518) -- ran and passed. |
| 7 | A hand-edited non-preset `usage_threshold` is rejected, falls to default 80, never snapped to nearest preset (CFG-05 adjacency probe) | VERIFIED | `--selfcheck` assertion `parse_config('{"usage_threshold": 85}')["usage_threshold"] == 80` -- ran and passed. |
| 8 | `build_label` at exactly the threshold is NOT hot (strict `>`, CFG-05 boundary probe) | VERIFIED | `--selfcheck` assertion `build_label({"used_percentage": 80}, 0, 80) == "80%"` -- ran and passed. Mutation test: `>` -> `>=` makes this assertion fail; reverted, tree clean. |
| 9 | Badge threshold comparison is a direct float>int comparison, no rounding step (CFG-05 precision probe) | VERIFIED | Source: `hot = usage["used_percentage"] > threshold or (pct7 is not None and pct7 > threshold)` (claude-monitor.py:331-333) -- no `round()` in the comparison (only in the display string). |
| 10 | Flipping one event-type key does not change any other (CFG-01 adjacency probe) | VERIFIED | `parse_config`'s per-key loop (`for key in (...): if isinstance(raw.get(key), bool): cfg[key] = raw[key]`) only ever writes the key it is iterating; confirmed structurally and by the empty-input assertion above. |
| 11 | `save_config(cfg)` called twice unchanged -> byte-identical file (CFG-03 idempotency probe) | VERIFIED | Round-trip script: wrote `cfg` twice, `b1 == b2` on the raw file bytes -- ran and passed. |
| 12 | `load_config()` called twice against a malformed file -> same default both times, no exception (CFG-04 idempotency probe) | VERIFIED | Round-trip script: two consecutive `load_config()` calls against `'{not json'`, both equal `DEFAULT_CONFIG` -- ran and passed. |
| 13 | [backstop] `save_config`'s atomic write survives a mid-write process kill -- never a truncated file (CFG-03 concurrency probe) | INSUFFICIENT_SPEC (abstained) | No wired crash-injection/concurrency test exists in the codebase or was run by the verifier. `save_config` does use `tempfile.mkstemp` + `os.replace` (claude-monitor.py:110-129, mirroring `prune_history`), but per the honest-verifier protocol, symbol presence/pattern-match is not explicit evidence for a `verification: backstop` truth. |
| 14 | [backstop] `load_config()` never observes a half-written file under concurrent `os.replace()` (CFG-04 concurrency probe) | INSUFFICIENT_SPEC (abstained) | Same reasoning as #13 -- relies on `os.replace()`'s POSIX atomic-rename guarantee, not independently exercised by a concurrent-access test. |
| 15 | [backstop] `self.config` cross-thread GIL-atomic access + fixed gate evaluation order (CFG-01/02 concurrency + ordering probe) | INSUFFICIENT_SPEC (abstained) | The short-circuit ORDER half is directly confirmed by reading `notif_allowed`'s source (Python's `and` short-circuits `not config["mute_all"]` before the `NOTIF_KEYS[kind]` lookup). The GIL cross-thread-atomicity half is not exercised by any wired concurrency test -- the compound truth is abstained rather than partially graded. |
| 16 | Each of the four event types can be toggled from the tray menu; the next event honors the change with no restart (ROADMAP SC1, CFG-01) | PRESENT_BEHAVIOR_UNVERIFIED | `on_notif_toggle` / `notif_submenu` exist, are wired into `rebuild_menu`, and read/write `self.config` live (confirmed structurally: `self.config[key] = item.get_active(); save_config(self.config); self.rebuild_menu()`, claude-monitor.py:1658-1665). No automated test exercises an actual live toggle + subsequent event; this is exactly the `<human-check>` the plan itself deferred to end-of-phase. |
| 17 | A single "Mute all" toggle silences every notification while tray rows and icon badge keep working (ROADMAP SC2, CFG-02) | PRESENT_BEHAVIOR_UNVERIFIED | The gate logic (truth #3) is proven by mutation test. `mute_all` is referenced in exactly two places in the file outside test/menu code -- `notif_allowed` (line 138) and the menu checkbox (lines 1684-1685) -- confirmed via full-file grep, so it structurally cannot leak into `build_label`, session rows, or the attention counter. But "rows/badge keep updating while muted" is a live-render property no automated check exercises. |
| 18a | Badge threshold chosen from four fixed presets, never free text (CFG-05, D-05) | VERIFIED | `grep -c 'Gtk.Entry' claude-monitor.py` == 0; the only threshold input surface is four `Gtk.RadioMenuItem`s built from `THRESHOLD_CHOICES`. |
| 18b | The badge follows the threshold selection and the selection persists across a restart, completing ROADMAP SC5 | PRESENT_BEHAVIOR_UNVERIFIED | Structurally wired (`rebuild_menu` reads `self.config["usage_threshold"]` into `build_label` on every rebuild; `on_threshold_toggle` persists via `save_config`), but the live "badge glyph changes on next poll tick" + "survives an actual helper restart" behavior is the plan's own deferred `<human-check>`. |
| 19 | [backstop] Four event-toggle checkboxes render in fixed order (waiting, done, 5h, 7d) on every rebuild (CFG-01 ordering probe) | VERIFIED | Ran the plan's AST source-position check: the four config-key string literals appear inside `notif_submenu` in ascending source order matching the declared order -- exits 0. |
| 20 | [backstop] The mute-all checkbox handler writes only `self.config['mute_all']`, never a `notify_*` key (D-04, CFG-02 idempotency probe) | VERIFIED | Ran the plan's AST check: `on_notif_toggle`'s body contains exactly one `Assign` node with a `Subscript` target -- exits 0. |
| 21 | [backstop] Four badge-threshold radios render in fixed ascending order (70/80/90/95) on every rebuild (CFG-05 ordering probe) | VERIFIED | `grep -c 'for val in THRESHOLD_CHOICES' claude-monitor.py` == 1 and `grep -c 'sorted(THRESHOLD_CHOICES)' claude-monitor.py` == 0 -- iterates the literal tuple directly, in its declared order. |

**Score:** 16/22 truths verified (3 present-but-behavior-unverified, 3 abstained as insufficient_spec)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `CONFIG_PATH`, `THRESHOLD_CHOICES`, `DEFAULT_CONFIG`, `NOTIF_KEYS` | module constants (06-01) | VERIFIED | All four present at claude-monitor.py:65-77, exactly as specified (literal tuple order, `usage_threshold` sourced from `USAGE_THRESHOLD`, no second literal `80`). |
| `parse_config(text)` / `load_config()` / `save_config(cfg)` | module functions (06-01) | VERIFIED | Signatures match exactly (AST-checked); tolerant/atomic behavior confirmed by round-trip script. |
| `notif_allowed(kind, config)` | rewritten, config-driven (06-01) | VERIFIED | Two-arg signature, mute-wins semantics confirmed by mutation test. Single call site inside `emit_notif` passes `self.config`. |
| `build_label(usage, attention, threshold=USAGE_THRESHOLD)` | rewritten signature (06-01) | VERIFIED | Third param present with default; single call site inside `rebuild_menu` passes `self.config["usage_threshold"]`. |
| `Monitor.config` | instance attribute, loaded before first `rebuild_menu()` (06-01) | VERIFIED | `self.config = load_config()` is the first statement in `__init__` (claude-monitor.py:1534); AST check confirms it precedes the `rebuild_menu()` call. |
| `~/.claude/tray-config.json` | new runtime artifact (06-01) | VERIFIED (by construction) | Written by `save_config` via `CONFIG_PATH`; exercised against a temp dir in the round-trip script, never the real path. |
| `Monitor.on_notif_toggle(item, key)` | CheckMenuItem handler (06-02) | VERIFIED | Present at claude-monitor.py:1658, exact signature, single-key-write confirmed by AST check. |
| `Monitor.on_threshold_toggle(item, val)` | RadioMenuItem handler (06-02) | VERIFIED | Present at claude-monitor.py:1667, exact signature, double-fire guard (`if not item.get_active(): return`) is its first statement. |
| `Monitor.notif_submenu()` | builds Notifications + nested Badge threshold submenu (06-02) | VERIFIED | Present at claude-monitor.py:1676; mute-all + separator + 4 checkboxes + separator + nested threshold radio submenu, all built fresh from `self.config`. |
| `rebuild_menu()` -- "Notifications" MenuItem | wired after dashboard item (06-02) | VERIFIED | claude-monitor.py:1741-1743, positioned immediately after the `dash` item and before the closing separator/Quit block, unchanged surrounding lines. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `notif_allowed`'s call site | `self.config` | `emit_notif` first line | VERIFIED | `grep -c 'notif_allowed(kind, self.config)'` == 1. |
| `build_label`'s call site | `self.config["usage_threshold"]` | `rebuild_menu`'s `set_label` call | VERIFIED | `grep -c 'build_label(self.usage, attention, self.config\["usage_threshold"\])'` == 1. |
| `notif_submenu()` | `self.config` | reads config to set every widget's initial `set_active()` state | VERIFIED | Source inspection: every `set_active()` call reads `self.config[...]` before its matching `connect("toggled", ...)`. |
| toggle handlers | `save_config` / `rebuild_menu()` | mutate-persist-redraw sequence | VERIFIED | `on_notif_toggle` and `on_threshold_toggle` both follow `self.config[...] = ...; save_config(self.config); self.rebuild_menu()`. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `--selfcheck` passes with all new assertions | `python3 claude-monitor.py --selfcheck` | `ok`, exit 0 | PASS |
| Config round-trip + tolerance (missing file, malformed x2, full round-trip, byte-identical double-write) | plan's temp-dir script | `config roundtrip ok` | PASS |
| Mutation (a): loosen `isinstance(..., bool)` guard | edit + `--selfcheck` | non-zero exit (KeyError) | PASS (load-bearing confirmed) |
| Mutation (b): loosen threshold membership test | edit + `--selfcheck` | non-zero exit (AssertionError) | PASS (load-bearing confirmed) |
| Mutation (c): `notif_allowed`'s `and` -> `or` | edit + `--selfcheck` | non-zero exit (AssertionError) | PASS (load-bearing confirmed) |
| Mutation (d): `build_label`'s `>` -> `>=` | edit + `--selfcheck` | non-zero exit (AssertionError) | PASS (load-bearing confirmed) |
| Working tree clean after all four mutation reverts | `git status --short` / `diff` | no output | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| CFG-01 | 06-02 (data model in 06-01) | Per-event tray toggles, effective without restart | human_needed | Data model + UI wiring VERIFIED structurally; live "next event honors it" behavior deferred to human UAT (truth #16). |
| CFG-02 | 06-01 + 06-02 | Global mute toggle | human_needed | Mute-wins gate logic VERIFIED by mutation test; "rows/badge keep working while muted" deferred to human UAT (truth #17). |
| CFG-03 | 06-01 | Persistence across restarts | VERIFIED | Round-trip script proves save/load symmetry; one setting (badge threshold) also has a live restart UAT item as a real-tray sanity check. |
| CFG-04 | 06-01 | Corruption tolerance | VERIFIED | Round-trip script proves missing-file and malformed-file fallback, twice, no exception. |
| CFG-05 | 06-01 + 06-02 | Configurable badge threshold | human_needed | Data model, fixed-preset-only input surface, and ordering VERIFIED; live "badge follows selection" deferred to human UAT (truth #18b). |

**No orphaned requirements** -- REQUIREMENTS.md maps CFG-01..05 to Phase 6; both plans' frontmatter `requirements:` fields (06-01: CFG-02/03/04/05, 06-02: CFG-01/02/05) together cover all five with no gaps.

### Anti-Patterns Found

None. `LC_ALL=C grep -nP '[^\x00-\x7F]' claude-monitor.py` returns only the pre-existing `SPARK_GLYPHS` sparkline glyphs (unrelated to this phase, present before it started). No `TODO`/`FIXME`/`HACK`/`XXX`/`TBD`/`PLACEHOLDER` markers in the file. No empty-return stubs, no hardcoded-empty data flowing to render paths.

### Prohibitions Checked (judgment tier)

| Statement | Plan | Disposition |
|-----------|------|-------------|
| MUST NOT migrate/fold `CLAUDE_TRAY_*` env vars into the new config file (D-01) | 06-01 | Confirmed by source inspection: `parse_config`/`load_config`/`save_config` never read or write any `CLAUDE_TRAY_*` name; those env vars remain independently read elsewhere in the file, unchanged. Non-authoritative LLM-judge verdict -- flagged for human confirmation alongside the other human-verification items. |
| MUST NOT let corrupt-config recovery silently persist recovered defaults back to disk (CFG-04) | 06-01 | Confirmed: `load_config()` calls only `parse_config`, never `save_config` -- a tolerant read cannot trigger a write. Non-authoritative LLM-judge verdict. |
| MUST NOT let "Mute all" suppress anything beyond notification delivery (ROADMAP SC2) | 06-02 | Confirmed structurally: `mute_all` appears only inside `notif_allowed` and the menu checkbox code, never near `build_label`, session rows, or the attention counter. Non-authoritative LLM-judge verdict. |
| MUST NOT let badge-threshold selection grow into free-text entry (D-05) | 06-02 | Confirmed: zero `Gtk.Entry` occurrences in the file. Non-authoritative LLM-judge verdict. |

All four prohibitions pass judgment-tier verification with structural evidence; none is a hard blocker. Flagged for human awareness per the never-silent-pass rule, not because evidence is missing.

### Human Verification Required

See the `human_verification` frontmatter list above -- 3 live-tray UAT items (already anticipated by the plans' own deferred `<human-check>` blocks) plus 3 `insufficient_spec` (abstained `backstop`-tagged) concurrency/atomicity claims that no automated test in this codebase exercises.

### Gaps Summary

No gaps. Every artifact exists, is substantive, and is wired exactly as the plans specify; every automatable truth (pure-function behavior, persistence, corruption tolerance, mute-wins gate semantics, fixed-order rendering, no-free-text input surface) was independently re-derived and confirmed by the verifier -- not merely trusted from SUMMARY.md. The only reasons this phase is not `passed` are (1) three genuinely live-UI/live-daemon behaviors the plans themselves correctly deferred to end-of-phase human UAT, and (2) three `verification: backstop`-tagged concurrency/atomicity claims that are architecturally sound (mirroring `prune_history`'s existing, previously-shipped pattern) but have no wired test proving the runtime guarantee in this codebase -- per the honest-verifier protocol, these must be abstained rather than confidently passed on symbol presence alone.

---

*Verified: 2026-07-16T12:42:34Z*
*Verifier: Claude (gsd-verifier)*
