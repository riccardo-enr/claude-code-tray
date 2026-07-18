---
status: diagnosed
trigger: "UAT gap G-07-2 (phase 07 live-session-view): 'Now I have two running session when I know one is done. Also the progress is still increasing when waiting dude.' / 'Again dude. One session is still running. It increases once per second but the status is incorrect'"
created: 2026-07-18T00:00:00.000Z
updated: 2026-07-18T00:00:00.000Z
---

## Current Focus

hypothesis: CONFIRMED - self.sessions has no liveness/staleness mechanism; the only removal path is the `end` socket event (fired by the SessionEnd hook), and Claude Code's SessionEnd hook is known-unreliable (does not fire on /exit or /clear, and cannot fire at all when the pane/terminal/process is killed externally). A session that stops sending events lingers forever, frozen at whatever status it last received, while the dashboard's client-side ticker (`sessDur(now - entered)`) counts up unbounded because it has no signal the backing process is gone.
test: read Monitor.handle/write_dashboard, dashboard.py's client JS, settings.hooks.json wiring, and Claude Code's own hook reliability docs/issues
expecting: n/a - root cause confirmed
next_action: none - goal is find_root_cause_only; return diagnosis to caller for gap-closure planning

## Symptoms

expected: When a Claude Code session actually finishes, its dashboard row transitions to status "done" (dimmed) and its duration counter stops (or is bounded to reality).
actual: A session the user knows has finished stays displayed with a stale status ("running", per the second report; ambiguously "waiting" language in the first) and its duration keeps ticking up every second indefinitely. User sees phantom/duplicate "running" sessions.
errors: None - no exceptions, no crash. Purely a stale-display bug.
reproduction: UAT Test 2 and Test 3 in phase 07 (07-live-session-view), gap id G-07-2. Practical repro: start a Claude Code session tracked by the tray, then end it via a path that does not run the SessionEnd hook to completion (e.g. `/exit`, `/clear`, closing the tmux pane/terminal, Ctrl-C, or killing the process) instead of a clean shutdown that reliably fires SessionEnd. The dashboard/tray keeps the session's last-known status forever.
started: Phase 07 (added the live Sessions panel to the dashboard) is what made this pre-existing gap *visible* - the underlying self.sessions lingering behavior predates phase 07 (tray menu already had it) but had no live duration ticker to expose it as clearly.

## Eliminated

- hypothesis: hooks in settings.hooks.json / installed ~/.claude/settings.json are mis-wired (wrong command, wrong event name) so "done"/"end" never gets sent at all
  evidence: Verified both the repo's settings.hooks.json template and the actual installed ~/.claude/settings.json - Stop -> `claude-send.py done`, SessionEnd -> `claude-send.py end`, correctly wired, matching the hook event names Monitor.handle() expects. Wiring is correct; the problem is upstream (Claude Code itself not firing SessionEnd reliably), not local misconfiguration.
  timestamp: 2026-07-18

- hypothesis: Monitor.handle()'s status-transition/entered-stamp logic (D-01, this phase) is buggy and fails to update status on a real transition
  evidence: Read handle() fully - `old = s.get("status")` captured before `s.update(...)`, `if old != event: s["entered"] = time.time()`. This logic is correct for any event that DOES arrive; it only fails to help when no event arrives at all (the actual bug). Not the root cause.
  timestamp: 2026-07-18

## Evidence

- timestamp: 2026-07-18
  checked: claude-monitor.py Monitor.handle() (session dict mutation) and Monitor.write_dashboard() (snapshot into dashboard payload)
  found: The ONLY code path that removes an entry from self.sessions is `event == "end"` -> `self.sessions.pop(sid, None)`. There is no TTL, no last-seen expiry, no liveness/pid/pane check anywhere in Monitor or core.py. write_dashboard() unconditionally snapshots every entry currently in self.sessions into the dashboard payload every tick, verbatim status included.
  implication: once an entry stops receiving hook events, it is permanently displayed with its last-known status forever - there is no self-correction.

- timestamp: 2026-07-18
  checked: settings.hooks.json (repo template) + installed ~/.claude/settings.json hooks block
  found: UserPromptSubmit -> claude-send.py running; Notification -> claude-send.py waiting; Stop -> claude-send.py done; SessionEnd -> claude-send.py end. Wiring matches exactly what Monitor.handle() expects (event in {running, waiting, done, end}).
  implication: the local hook wiring is correct; if "end" is not arriving, the gap is in whether Claude Code actually invokes SessionEnd, not in this repo's hook registration.

- timestamp: 2026-07-18
  checked: claude_monitor/dashboard.py client-side JS (_DASH_JS): sessDur(), renderSessions()
  found: `td3.textContent = sessDur(now - s.entered)` runs in a `setInterval(renderSessions, 1000)` loop with no cap and no check that the session is still alive - it is a pure clock diff against the last-stamped `entered` epoch.
  implication: explains the exact symptom "it increases once per second" even for a session that has actually terminated - the ticker has no way to know the process is gone, it just keeps computing now() - entered.

- timestamp: 2026-07-18
  checked: web search - official Claude Code hooks docs + anthropics/claude-code GitHub issues for SessionEnd reliability
  found: Two open upstream bugs - anthropics/claude-code#17885 "SessionEnd hook doesn't fire on /exit command" and anthropics/claude-code#6428 "SessionEnd hook does not fire with /clear as documentation states". SessionEnd is also documented as unable to fire at all for external termination (killed pane, closed terminal, SIGKILL, crash) since there is no process left to run it.
  implication: this is not a local config bug. SessionEnd (the sole trigger for the `end` socket event that pops a session out of self.sessions) is unreliable/missing for exactly the exit paths a real user takes most often (/exit, /clear, closing a terminal/tmux pane). Combined with zero staleness handling locally, a missed SessionEnd = a permanently stale row.

- timestamp: 2026-07-18
  checked: prior code-review finding referenced in task hints (07-REVIEW.md WR-03) - file does not exist in this worktree, so only the hint's paraphrase was available
  found: WR-03 reportedly flagged lingering entries only in the "done" (dimmed) state, i.e. assumed the last hook to fire before an untracked exit is always Stop/"done". The user's actual reports show status stuck at "running" (and possibly "waiting"), not "done".
  implication: this is the SAME root cause (self.sessions has no expiry, relies solely on `end`), just a broader manifestation than WR-03 anticipated - the stale status can be whatever event last arrived before the session went dark (running if killed mid-turn/before Stop, waiting if killed while a permission prompt was outstanding, done if killed right after Stop but before SessionEnd). WR-03 under-scoped the fix to "done rows linger" when the real gap is "any status can linger, unbounded, forever, with no visibility into staleness."

## Resolution

root_cause: |
  claude-monitor.py's `self.sessions` dict has no expiry/liveness mechanism - the ONLY way an
  entry is ever removed is the `end` socket event, which is fired exclusively by the Claude
  Code `SessionEnd` hook (see settings.hooks.json + Monitor.handle(), claude-monitor.py:373-379).
  Claude Code's SessionEnd hook is upstream-unreliable for the most common ways a user actually
  ends a session: it does not fire on `/exit` (anthropics/claude-code#17885) or on `/clear`
  (anthropics/claude-code#6428), and it structurally cannot fire when the terminating pane,
  terminal window, or process is killed externally (no process left to run the hook). When the
  `end` event never arrives, the session's dict entry is frozen forever at whatever status
  (`running` / `waiting` / `done`) it last received via UserPromptSubmit/Notification/Stop - and
  Monitor.write_dashboard() snapshots that stale entry into the dashboard payload on every poll
  tick unconditionally. dashboard.py's client-side `sessDur(now - s.entered)` ticker
  (claude_monitor/dashboard.py ~line 471, driven by `setInterval(renderSessions, 1000)`) then
  counts the duration up every second indefinitely, since it is a pure clock diff with no
  liveness signal of its own. This produces exactly the reported symptoms: a session the user
  knows has ended keeps showing a stale, incorrect status (often "running" if the session was
  killed/exited before Stop, or if /exit or /clear silently ate the SessionEnd hook), with its
  duration counter climbing forever, and can visually present as "two running sessions" when
  only one is truly active.

  This confirms and generalizes the WR-03 finding from the prior review referenced in the task
  hints: it is not narrowly "done rows linger" - it is "self.sessions has no staleness/liveness
  check at all, so ANY status can get stuck forever," and the visible status depends purely on
  which hook last fired before the real process went away.
fix: (not applied - goal is find_root_cause_only; a gap-closure plan will design the fix)
verification: (not applicable - no fix applied)
files_changed: []
