# Roadmap: v1.4 VS Code Usage Surface

Workstream: `vscode`. Runs in parallel with v1.3 in `notifications-predictive-alerts`.

## Overview

v1.4 puts the tray's quota and session picture inside VS Code. It is a **second frontend
over the same data**, not a second data pipeline: the extension reads
`~/.claude/usage-history.jsonl` — the store the tray has written since v1.1 — directly.
No CLI shell-out, no socket, no second poll.

The journey has three steps. First a TypeScript extension has to exist at all: that is a
genuinely new deployment target in a Python + PyGObject repo, and it comes bundled with
the history reader and the status bar item that proves the reader works — usage % and
reset countdown in the editor's own field of view. Second, the v1.2 dashboard, already
self-contained by assertion (DASH-06), gets dropped into a VS Code webview tab — a cheap
surface with one real unknown (the webview CSP is stricter than `file://`). Third, session
state escapes the tray process for the first time (a ~10-line mirror to
`~/.claude/sessions.json`) so VS Code can show session status and push in-editor
notifications, including the predictive quota alert off a TypeScript port of `project()`.

Closes SEED-005.

## Constraints Carried Into Every Phase

- **Data source is settled.** Read `~/.claude/usage-history.jsonl`. Accepted consequence:
  no tray running, no usage in VS Code (VSC-F2 is deferred, not a bug).
- **One Python edit in this milestone**, and only in Phase 3: the session mirror (VSCN-01).
  `claude-monitor.py` is also written by v1.3's Phase 06 (config toggles) in the other
  workstream. Keeping v1.4's Python diff confined to the session mirror is what keeps that
  merge trivial. Do not let anything else in this milestone touch the tray.
- **`project()` will have three copies** after this milestone (Python poll thread,
  dashboard JS, TS extension). VSCN-05 exists to make drift detectable, not to prevent the
  third copy.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [ ] **Phase 1: Extension Foundation & Usage in the Status Bar** - A TypeScript extension that installs locally, reads the history store safely, and shows usage % + reset countdown with both caps on hover
- [ ] **Phase 2: Usage Dashboard in a VS Code Tab** - The existing v1.2 self-contained dashboard opened as a webview, surviving the stricter CSP and following the editor theme
- [ ] **Phase 3: Session Mirror & In-Editor Notifications** - The tray mirrors session state to a file; VS Code shows session status and pushes de-duped session + predictive-quota notifications

## Phase Details

### Phase 1: Extension Foundation & Usage in the Status Bar
**Goal**: The user sees live Claude Code usage inside VS Code, in the same visual field as the code
**Depends on**: Nothing (first phase)
**Requirements**: EXT-01, EXT-02, EXT-03, EXT-04, VSC-01, VSC-02, VSC-03, VSC-04
**Success Criteria** (what must be TRUE):
  1. User builds the extension from the repo and installs it into VS Code without a marketplace publish; a usage item appears in the status bar.
  2. User sees current usage % and time-to-reset in the status bar, refreshing as the tray appends new samples — with no perceptible startup cost and no blocking I/O on the extension host.
  3. User hovers the status bar item and sees both caps (5-hour and 7-day), the burn rate, and the projected usage at reset for each cap.
  4. The status bar item warns visibly when *either* cap is high — the in-editor analogue of the tray's ALERT-01 badge.
  5. With no tray running, no history file, or a corrupt / half-written trailing line, the item reads an explicit "usage unavailable" rather than erroring, blanking, or showing a stale number.
**Plans**: TBD

**Notes**: The scaffold (EXT-01) has no user-visible value alone, and the reader guarantees
(EXT-02/03/04) are properties of a reader that only exists once something consumes it — so
foundation and first surface ship together. This is the phase that establishes the whole
new deployment target; the two after it are additive surfaces on top of it. VSC-02's "both
caps" is not optional polish: a 95%-weekly / 10%-five-hour state showing no warning is the
exact QUOTA-01 failure v1.2 had to fix.

### Phase 2: Usage Dashboard in a VS Code Tab
**Goal**: The v1.2 usage dashboard is browsable inside the editor, without a second renderer
**Depends on**: Phase 1
**Requirements**: VSCD-01, VSCD-02, VSCD-03
**Success Criteria** (what must be TRUE):
  1. User runs a command from the palette and the existing generated v1.2 dashboard HTML opens in a VS Code tab.
  2. Charts, heatmap, range switching, and reset markers render and behave the same as the browser page — no CSP-blocked inline script or style, no blank panel.
  3. Switching VS Code between light and dark theme flips the dashboard to match, including the inverted heatmap ramp — the panel follows the editor, not only its own `prefers-color-scheme`.
**Plans**: TBD
**UI hint**: yes

**Notes**: Cheapest slice in the milestone — DASH-06's assertion-enforced self-containment
means there is nothing to fetch. The one real unknown is VSCD-02: the webview CSP is
stricter than `file://`, so self-containment is necessary but may not be sufficient and
inline script/style may need a nonce. Budget the phase around that, not around the charts.
Independent of Phase 3 — the two can swap order if the v1.3 merge makes it convenient to
land the Python edit sooner.

### Phase 3: Session Mirror & In-Editor Notifications
**Goal**: Session state leaves the tray process, and VS Code pulls the user back when a session or the quota needs them
**Depends on**: Phase 1 (independent of Phase 2)
**Requirements**: VSCN-01, VSCN-02, VSCN-03, VSCN-04, VSCN-05, VSCN-06
**Success Criteria** (what must be TRUE):
  1. The tray writes live session state to `~/.claude/sessions.json` on every transition, and a failure to write it never crashes or blocks the tray (HIST-03 precedent).
  2. User sees per-session status (running / waiting / done) inside VS Code, read from that mirror.
  3. User gets exactly one VS Code notification per session transition to *waiting* or *done* — once per transition, never once per file-change event.
  4. User gets a VS Code notification when either cap is projected to hit 100% before its window resets, and the TypeScript `project()` port is shown to agree with the Python implementation on the same inputs.
  5. User can turn each notification type off individually, and mute all of them at once.
**Plans**: TBD

**Notes**: **Sequencing is forced.** VSCN-01 is the entire Python diff for v1.4 (~10 lines
mirroring `self.sessions`, `claude-monitor.py:1554`) and it *blocks* VSCN-02/03 — nothing
outside the tray process can observe session state until it lands. It must be the first
plan of this phase, and it must stay confined to the mirror so the merge with v1.3's
Phase 06 (which also edits `claude-monitor.py`) stays trivial. VSCN-05 is the drift guard
for the third copy of `project()`; a check that fails when the copies disagree is the
deliverable, not a one-time eyeball.

## Progress

**Execution Order:** Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Extension Foundation & Usage in the Status Bar | 0/TBD | Not started | - |
| 2. Usage Dashboard in a VS Code Tab | 0/TBD | Not started | - |
| 3. Session Mirror & In-Editor Notifications | 0/TBD | Not started | - |

## Coverage

All 17 v1.4 requirements mapped to exactly one phase.

| Category | Requirements | Phase |
|----------|--------------|-------|
| EXT | EXT-01, EXT-02, EXT-03, EXT-04 | 1 |
| VSC | VSC-01, VSC-02, VSC-03, VSC-04 | 1 |
| VSCD | VSCD-01, VSCD-02, VSCD-03 | 2 |
| VSCN | VSCN-01, VSCN-02, VSCN-03, VSCN-04, VSCN-05, VSCN-06 | 3 |

**Mapped: 17/17. No orphans, no duplicates.**

Deferred, not in this milestone: VSC-F1 (click-to-focus from the status bar), VSC-F2
(standalone with no tray), VSC-F3 (marketplace publish).
