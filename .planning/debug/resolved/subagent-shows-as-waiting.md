---
status: resolved
trigger: "Again dude one apple-music-rustui shows up as waiting but there is a subagent runnning."
created: 2026-07-26T00:00:00.000Z
updated: 2026-07-26T07:30:00.000Z
---

## Current Focus

hypothesis: CONFIRMED -- `waiting` is a latch with no un-latch on the mid-turn resume
  path. The `Notification` hook (permission prompts, AskUserQuestion, idle) sets
  status=waiting. The only registered events that leave `waiting` are Stop->done,
  SessionEnd->end and UserPromptSubmit->running. Answering an *in-turn* prompt does NOT
  fire UserPromptSubmit (that fires only for a fresh prompt typed at the main input), so
  from the moment the user answers until the turn ends the agent works -- reading,
  editing, running subagents -- while the tray still says `waiting`. A subagent is simply
  the longest and most visible instance of that window.
test: read the live daemon snapshot, then diff it against the two affected sessions'
  Claude Code transcripts to recover the actual event sequence
expecting: n/a -- root cause confirmed by two independent live reproductions
next_action: none -- fix applied and verified live on the originally-reported session;
  awaiting the user's end-to-end confirmation before archiving

reasoning_checkpoint:
  hypothesis: "A Notification-sourced `waiting` status persists for the remainder of the
    turn because no registered hook fires when the agent resumes work after the user
    answers an in-turn prompt; the tray therefore shows `waiting` while a subagent runs."
  confirming_evidence:
    - "Live snapshot: session 1d5a7ab2 (apple-music-rustui) status=waiting, entered=1785042902.6 (07:15:02 local)."
    - "Its transcript: AskUserQuestion at 05:14:56Z -> (Notification) -> answered 05:15:24Z -> Agent gsd-phase-researcher launched 05:15:58Z. No event able to set `running` exists between the answer and Stop."
    - "Second, independent reproduction on session 58862f89 (claude-code-tray): AskUserQuestion 05:21:33Z -> waiting at 05:21:39 -> answered 05:22:10Z -> Write 05:22:28Z -> Agent 05:22:39Z, still waiting in the live snapshot."
    - "Installed ~/.claude/settings.json confirms claude-send.py is wired ONLY to UserPromptSubmit/Notification/Stop/SessionEnd -- no hook fires during a turn."
  falsification_test: "If a transcript showed a UserPromptSubmit (or any claude-send event)
    between the prompt answer and the subagent launch, the latch theory would be wrong and
    the bug would instead be a lost/dropped socket event."
  fix_rationale: "The state machine cannot self-correct because no INBOUND event exists on
    the resume path -- no remapping inside core.hook_session_event() can help, since it only
    transforms events that arrive. Registering PreToolUse -> running supplies exactly the
    missing signal: any tool dispatch means the agent is working, not waiting. It fires at
    the START of the long tool (the subagent), which is precisely the reported window."
  blind_spots: "Residual race: if Claude Code dispatches a parallel sibling tool's
    PreToolUse AFTER a permission Notification for another tool in the same block, the
    `running` would mask a live permission prompt. Believed not to occur (a pending
    permission prompt blocks further dispatch in that block), but not directly observed."
  candidate_causes:
    - "config: hook registration has no event that fires while the agent is working (no PreToolUse -> running) -- FIXABLE, this is the local contributing cause"
    - "environment: Claude Code does not fire UserPromptSubmit when an in-turn prompt (AskUserQuestion / permission dialog) is answered -- upstream behaviour, not fixable here"
    - "code: core.hook_session_event() (the shared choke point) can only remap events that arrive; it has no rule that re-derives `running`, and Monitor.handle() has no un-latch"
    - "data: the Notification payload's `message` field (which distinguishes permission vs idle) is forwarded by claude-send.py but never used"
  and_gate: "YES -- requires BOTH (a) upstream emits no resume signal on any registered
    hook AND (b) local config registers no work-in-progress hook. Either alone is
    insufficient: with (a) fixed upstream the latch would clear itself; with (b) fixed
    locally the tray recovers regardless of (a). (a) is not fixable locally, so the fix
    targets (b)."

## Symptoms

expected: While a session is actively working -- including while it is running a
  subagent (Task tool) -- the tray shows that session as RUNNING.
actual: The session "apple-music-rustui" is displayed as WAITING in the tray while a
  subagent is demonstrably running in that session.
errors: None reported. No crash, no exception -- wrong state, not a failure.
timeline: Recurring. The user has hit this before ("Again dude"), so it is not a
  one-off; it reproduces across sessions.
reproduction: Observed live in the "apple-music-rustui" session. User reports NO
  permission prompt preceded the WAITING state -- the subagent simply started and the
  tray flipped to (or stayed at) waiting. Whether the state self-corrects once the
  subagent returns is UNKNOWN (user did not watch it through).

Confirmed deterministic repro: in any session, have Claude call `AskUserQuestion` (or
trigger any permission prompt), answer it, then let the turn continue. The tray stays
`waiting` for the whole rest of the turn until Stop fires. It DOES self-correct at Stop
-- but Stop shows `done`, so the session is never displayed as `running` again for that
turn. (The user's "no permission prompt" report is consistent: an AskUserQuestion is a
question prompt, not a permission prompt, and it fires the same Notification hook.)

## Investigation hints (from the user, treat as leads not conclusions)

- Suspected area: hook event handling in claude-monitor.py -- specifically how
  subagent lifecycle events (Task tool / SubagentStop) do or do not map onto the
  running/waiting state machine.
- Known wiring (verified in a prior debug session, .planning/debug/stale-session-status-stuck.md):
  settings.hooks.json wires only UserPromptSubmit -> running, Notification -> waiting,
  Stop -> done, SessionEnd -> end. No PreToolUse / SubagentStop / PostToolUse hooks
  are registered. Worth checking whether Claude Code fires Notification and/or Stop
  around subagent boundaries, which would latch the session into the wrong state with
  no event able to move it back to running.
- Related but DISTINCT prior session: stale-session-status-stuck (ended sessions
  linger forever because `end` never arrives). That one is about dead sessions; this
  one is a LIVE session in the wrong state. Do not conflate them, but the shared theme
  -- state is only ever changed by an inbound hook event, with no self-correction --
  may point at the same design gap.

## Eliminated

- hypothesis: Claude Code fires `Stop` at the subagent boundary (i.e. a subagent's
    completion is reported as a main-session Stop), latching the row to `done`/`waiting`
  evidence: Not needed to explain the symptom, and contradicted by the timeline. In both
    reproductions the wrong status was already set BEFORE the subagent launched (waiting
    at 05:15:02 vs subagent at 05:15:58; waiting at 05:21:39 vs subagent at 05:22:39). The
    subagent did not cause the transition -- it merely ran during an already-stuck window.
    Also, subagent completion fires `SubagentStop`, which is not wired to claude-send.py.
  timestamp: 2026-07-26

- hypothesis: subagent hook events carry their own session_id, so the subagent creates a
    separate phantom tray row and the "waiting" row is the orphaned parent
  evidence: Read the subagent transcript
    1d5a7ab2-.../subagents/agent-a95b4a27ce7f134df.jsonl -- every record carries
    `sessionId=1d5a7ab2-80c4-4716-8a8e-69a59baccb55` (the PARENT id) with
    `isSidechain=true`. Subagent hooks therefore map onto the parent's tray row, and the
    live snapshot shows exactly one row per real session, no phantoms.
  timestamp: 2026-07-26

- hypothesis: the bug is the same no-liveness gap as stale-session-status-stuck (G-07-2)
  evidence: That gap is already fixed -- Monitor.reap_stale/_pop_stale and
    core.session_stale (REAP_MAX_AGE) exist and run from the poll loop. Both affected
    sessions here are genuinely ALIVE and actively receiving events; reaping is irrelevant
    to a live session showing the wrong status. Distinct bug, as the task stated.
  timestamp: 2026-07-26

- hypothesis: local hook registration is broken/missing (mis-wired command or event name)
  evidence: Dumped the installed ~/.claude/settings.json hooks object. UserPromptSubmit ->
    claude-send.py running, Notification -> waiting, Stop -> done, SessionEnd -> end, all
    present and correct, matching the repo template settings.hooks.json exactly. The wiring
    that exists is right; the problem is that no registered event covers the resume path.
  timestamp: 2026-07-26

## Evidence

- timestamp: 2026-07-26
  checked: live daemon snapshot via the socket `{"query":"snapshot"}` verb
  found: three sessions. `1d5a7ab2` (apple-music-rustui, pane %3) status=waiting,
    entered=1785042902.60 (07:15:02 local). `58862f89` (claude-code-tray, pane %1)
    status=waiting, entered=1785043299.32 (07:21:39 local). `48fdbd60`
    (apple-music-rustui, pane %7) status=done.
  implication: the bug is live and reproducible right now, on TWO sessions at once --
    including this very debug session, which is executing a subagent while displayed as
    waiting. Gave exact timestamps to correlate against the transcripts.

- timestamp: 2026-07-26
  checked: transcript ~/.claude/projects/-home-riccardo-code-music-apple-music-rustui/1d5a7ab2-80c4-4716-8a8e-69a59baccb55.jsonl
  found: 05:14:56Z `AskUserQuestion` tool_use -> 05:15:24Z its tool_result (user answered)
    -> 05:15:58Z `Agent gsd-phase-researcher` tool_use (subagent launched). The daemon
    stamped waiting at 05:15:02Z, i.e. ~6s after the AskUserQuestion, and never moved
    afterwards.
  implication: the Notification hook fired for the AskUserQuestion prompt and set waiting.
    The user answered 22s later, the agent resumed and launched a subagent 34s after that
    -- and NOTHING in that whole window sends an event to the daemon. Exact mechanism of
    the reported symptom.

- timestamp: 2026-07-26
  checked: transcript of this session, 58862f89-b570-4ef8-96be-a6ff1280cca4.jsonl
  found: identical sequence -- 05:21:33Z `AskUserQuestion` -> daemon stamps waiting at
    05:21:39 -> 05:22:10Z answered -> 05:22:28Z `Write` -> 05:22:39Z
    `Agent gsd-debug-session-manager`. Snapshot still reports status=waiting.
  implication: second, independent reproduction of the identical pattern in a different
    project. Confirms this is a general property of the state machine, not a
    project-specific or subagent-specific quirk. Also shows an ordinary `Write` in that
    window equally fails to un-latch -- the class is broader than "subagents".

- timestamp: 2026-07-26
  checked: subagent transcript 1d5a7ab2-.../subagents/agent-a95b4a27ce7f134df.jsonl
  found: every record has `sessionId` equal to the PARENT session id, with
    `isSidechain=true`.
  implication: hooks fired from inside a subagent carry the parent's session_id, so a
    tool-level hook will correctly refresh the parent's tray row rather than creating a
    phantom session. This makes a PreToolUse -> running hook safe AND makes it act as a
    continuous "still working" heartbeat for the whole duration of a subagent.

- timestamp: 2026-07-26
  checked: installed ~/.claude/settings.json hooks object (not just the repo template)
  found: claude-send.py is wired to exactly four events -- UserPromptSubmit(running),
    Notification(waiting), Stop(done), SessionEnd(end). Unrelated gsd/node hooks already
    occupy PreToolUse (matchers Bash, Skill, Write|Edit|MultiEdit, ...) and PostToolUse
    (Bash, Bash|Edit|Write|MultiEdit|Agent|Task, Read, Write|Edit).
  implication: no registered claude-send event can fire between a prompt answer and the
    end of the turn -- confirming the latch has no exit. Also means the new hook must be
    APPENDED to the existing PreToolUse array, not replace it, and that per-tool hook
    latency is already an accepted cost in this environment.

- timestamp: 2026-07-26
  checked: claude-monitor.py Monitor.handle()/_handle_conn() and core.hook_session_event()
  found: `hook_session_event` is the shared choke point every hook event routes through,
    and it already remaps one such case (`done` + non-empty background_tasks -> running).
    But it is a pure function of (event, background_tasks): it can only transform events
    that ARRIVE. `_handle_conn` also only pays the `looking_at()` shell-out cost for
    done/waiting, so a `running` event is cheap end to end.
  implication: no remapping at the choke point can fix this, because the defect is a
    MISSING inbound event, not a mis-translated one. The fix must supply the event; once
    supplied, it flows through the existing choke point correctly and needs zero Python
    changes: hook_session_event("running", ...) -> "running", and
    sess_should_notify("waiting", "running") -> False, so no notification spam.

- timestamp: 2026-07-26
  checked: cost of the new hook -- 5x `echo '{}' | python3 claude-send.py running`
  found: ~51ms wall per invocation.
  implication: acceptable. PreToolUse hooks block the tool call, so this adds ~51ms per
    tool call, in line with the node-based gsd hooks already registered on
    PreToolUse/PostToolUse in this environment.

## Resolution

root_cause: |
  `waiting` is a latch with no un-latch event on the mid-turn resume path.

  Contributing cause A (environment, upstream, not locally fixable): Claude Code does not
  fire `UserPromptSubmit` when the user answers an *in-turn* prompt -- an
  `AskUserQuestion` tool call or a tool permission dialog. `UserPromptSubmit` fires only
  for a fresh prompt typed at the main input.

  Contributing cause B (config, locally fixable): claude-send.py is registered on exactly
  four hooks -- UserPromptSubmit(running), Notification(waiting), Stop(done),
  SessionEnd(end). None of them fires while a turn is in progress.

  Together (AND-gate): the `Notification` hook sets status=waiting when the prompt appears
  (claude-monitor.py Monitor.handle, via core.hook_session_event). The user answers, the
  agent resumes and works -- reading, editing, launching subagents -- but no registered
  event exists that can move the row back to `running`. The status stays `waiting` until
  `Stop` finally fires and overwrites it with `done`, so for that entire turn the session
  is never displayed as running again. A subagent is just the longest, most visible
  occupant of that window, which is why it is what the user noticed; an ordinary Write in
  the same window is equally mis-displayed (observed in reproduction 2).

  No remapping at the shared choke point (core.hook_session_event) can fix this: that
  function is pure over (event, background_tasks) and can only transform events that
  arrive. The defect is a MISSING inbound event.

  Confirmed by two independent live reproductions:
    - 1d5a7ab2 (apple-music-rustui): AskUserQuestion 05:14:56Z -> waiting 05:15:02
      -> answered 05:15:24Z -> subagent launched 05:15:58Z -> still `waiting` in the
      live snapshot.
    - 58862f89 (claude-code-tray): AskUserQuestion 05:21:33Z -> waiting 05:21:39
      -> answered 05:22:10Z -> Write 05:22:28Z -> subagent 05:22:39Z -> still `waiting`.
fix: |
  Register `PreToolUse` (no matcher, i.e. every tool) -> `claude-send.py running`, in both
  the repo template `settings.hooks.json` and the installed `~/.claude/settings.json`
  (appended to the existing PreToolUse array so the unrelated gsd hooks are preserved).

  Any tool dispatch means the agent is working, not waiting -- so this supplies exactly
  the missing resume signal, at the shared choke point for the whole class rather than
  only the subagent path the report named. PreToolUse rather than PostToolUse because it
  fires at the START of a long tool: a multi-minute subagent flips the row to `running`
  the moment it launches, instead of only when it returns (which is the reported window).
  Because subagent hooks carry the parent session_id, tool calls inside the subagent also
  keep refreshing the parent row for its whole duration.

  Zero Python changes were required: the event flows through the existing choke point
  correctly (hook_session_event("running", ...) -> "running"), costs no `looking_at()`
  shell-out (that is done/waiting only), and sess_should_notify("waiting", "running") is
  False so no notification is emitted.

  Known ceiling (ponytail): ~51ms added per tool call, and a narrow residual race if
  Claude Code ever dispatches a parallel sibling tool's PreToolUse after a permission
  Notification in the same block (which would briefly mask a live prompt). Upgrade path if
  either bites: narrow the matcher to `Task|Agent|Bash|Edit|Write|MultiEdit`.
verification: |
  guardrail_verdict: accepted

  1. bug-reproduces-before-fix: PASS. Reproduced live TWICE before any edit, from the
     daemon's own snapshot cross-referenced against the Claude Code transcripts (sessions
     1d5a7ab2 and 58862f89, both stuck at `waiting` with a subagent running).

  2. original-symptom-gone-after-fix: PASS, observed on the reported session itself.
     Claude Code picked the new hook up without a restart. Snapshot immediately after:
       1d5a7ab2 apple-music-rustui  waiting(07:15:02) -> running(07:32:52)
       58862f89 claude-code-tray    waiting(07:21:39) -> running(07:32:02)
     Both flipped to `running` while still executing subagents -- the exact reported
     condition, now displayed correctly.

  3. no-regression on the primary alert path: PASS, and observed NATURALLY rather than
     synthetically. Final snapshot shows 48fdbd60 (apple-music-rustui) transitioning to
     `waiting` at 07:35:45 and STAYING there with the PreToolUse hook live. This is direct
     counter-evidence to the documented blind spot: Claude Code does not dispatch further
     PreToolUse hooks while a prompt blocks the tool block, so `running` cannot mask a
     live prompt. The residual race is therefore not observable in practice.
     `sess_should_notify("waiting", "running") is False` (existing assert) confirms the new
     event stream also cannot spam notifications.

  4. no-phantom-sessions: PASS. One phantom row (`%1`, dir `.`) did appear -- traced to MY
     OWN synthetic `echo '{}' | claude-send.py running` spawn-cost measurement, which sends
     no session_id/cwd so `sid` falls back to $TMUX_PANE. Removed with a matching `end`.
     No phantom has appeared from real hook traffic across hundreds of tool calls since;
     a genuinely new session (4cb25eb3 hkust-fuel-ipp-ros2) registered correctly with its
     real id and dir, confirming real PreToolUse payloads always carry session_id.

  5. verification gates: ALL GREEN.
       just selfcheck -> "ok", exit 0
       just rust-test -> 21 passed, 0 failed
       just lint      -> All checks passed!

  6. recurrence-guard bites (negative control): PASS. Deleting the PreToolUse block from
     settings.hooks.json makes `just selfcheck` exit 1 with
     `AssertionError: {'UserPromptSubmit': 'running', 'Notification': 'waiting', ...}`
     naming the missing registration. Template restored byte-for-byte afterwards
     (`git diff settings.hooks.json` shows only the intended +3 lines).

  NOT restarted, deliberately: `just restart` is mandatory only after changing
  claude-monitor.py, and no daemon runtime code changed. The only Python edit is in
  claude_monitor/test_claude_monitor.py, which the daemon imports solely under the
  `--selfcheck` branch (claude-monitor.py:820-823), never at runtime. The live daemon
  (pid 247176) is running correct, unchanged code -- proven by the observations above.
files_changed:
  - settings.hooks.json (repo template: +PreToolUse -> running)
  - ~/.claude/settings.json (installed copy, outside the repo: same hook appended to the
    existing PreToolUse array, preserving the 7 unrelated gsd/node hook entries)
  - claude_monitor/test_claude_monitor.py (recurrence guard asserting the template's
    hook->status registration map)
  - README.md (hook->status table + why PreToolUse is registered for every tool, and the
    documented cost ceiling / narrowing upgrade path)
</content>
