# Requirements — v1.4 VS Code Usage Surface

Workstream: `vscode`. Runs in parallel with v1.3 in `notifications-predictive-alerts`.

**Scope basis:** SEED-005. A second *frontend* over the data the tray already writes —
explicitly not a second data pipeline. The extension reads
`~/.claude/usage-history.jsonl` directly; the only change to the tray is mirroring
session state to a file that does not exist yet.

## v1.4 Requirements

### Extension Foundation (EXT)

- [ ] **EXT-01**: A VS Code extension lives in the repo (TypeScript, its own package
      manifest and build) and installs into VS Code from a local build — no marketplace
      publish required.
- [ ] **EXT-02**: The extension activates without a visible startup cost and does no
      blocking I/O on the extension host — history reads are async and off the UI path
      (the VS Code analogue of the POLL-01 constraint that shaped every tray feature).
- [ ] **EXT-03**: With no tray running and no history file present, the extension
      degrades to an explicit "usage unavailable" state rather than erroring, blanking,
      or showing a stale number (the POLL-02 lesson, ported).
- [ ] **EXT-04**: The extension tolerates a corrupt or partially-written history line
      without crashing — the store is append-only and may be read mid-write (the
      `260713-fry` lesson, ported).

### Status Bar & Hover (VSC)

- [ ] **VSC-01**: User sees current usage % and time-to-reset in the VS Code status bar,
      refreshed as the tray appends new samples.
- [ ] **VSC-02**: User sees both caps (5-hour and 7-day) on hover, so a hot weekly cap is
      visible even when the 5-hour cap is cold (the QUOTA-01 failure that v1.2 fixed).
- [ ] **VSC-03**: User sees burn rate and projected usage at reset for both caps on hover.
- [ ] **VSC-04**: The status bar item warns visibly when either cap is high — the
      in-editor analogue of the ALERT-01 icon badge.

### Webview Dashboard (VSCD)

- [ ] **VSCD-01**: User can open the existing v1.2 usage dashboard in a VS Code tab from
      a command, reusing the generated self-contained HTML rather than a new renderer.
- [ ] **VSCD-02**: The dashboard renders correctly under the VS Code webview CSP, which
      is stricter than `file://` — self-containment (DASH-06) is necessary but may not be
      sufficient; inline script/style may need a nonce.
- [ ] **VSCD-03**: The webview follows the VS Code light/dark theme rather than only its
      own `prefers-color-scheme` toggle (DASH-07).

### Session Mirror & Notifications (VSCN)

- [ ] **VSCN-01**: The tray mirrors session state to `~/.claude/sessions.json` on each
      transition — `self.sessions` (`claude-monitor.py:1554`) is in-memory only today, so
      nothing outside the tray process can see it. Written defensively: a failure here
      must never crash or block the tray (HIST-03 precedent).
- [ ] **VSCN-02**: User sees per-session status (running / waiting / done) in VS Code,
      read from that mirror.
- [ ] **VSCN-03**: User gets a VS Code notification when a session needs them (waiting)
      or finishes (done), de-duped per state transition — fires once per transition, never
      once per file-change event.
- [ ] **VSCN-04**: User gets a VS Code notification when either cap is projected to hit
      100% before its window resets, off a TypeScript port of `project()` (QUOTA-03).
- [ ] **VSCN-05**: The TypeScript `project()` port is verified against the Python
      implementation — three copies of this formula now exist (Python, dashboard JS, TS)
      and they must not drift.
- [ ] **VSCN-06**: User can turn each notification type off, and mute all of them.

## Future Requirements (deferred)

- **VSC-F1**: Click status bar to focus the originating session (the tray's tmux/Ghostty
  focus action has no meaning inside VS Code — needs its own answer).
- **VSC-F2**: Extension works standalone with no tray running (would require the CLI
  shell-out or tray-endpoint data source, both rejected for v1.4).
- **VSC-F3**: Marketplace publish.

## Out of Scope

- **A second data pipeline.** The extension does not poll `claude-monitor`, does not
  reimplement the rolling-window/cap math, and does not open a socket to the tray. It
  reads the file the tray already writes. Accepted consequence: no tray, no usage.
- **Replacing the GNOME tray.** VS Code is an additional surface, not a migration; the
  tray remains the primary one.
- **Cost/dollar tracking**, **Wayland**, **hosted/multi-user** — unchanged from PROJECT.md.

## Traceability

Filled by the roadmapper.
