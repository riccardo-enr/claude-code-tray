---
id: SEED-008
status: dormant
planted: 2026-07-25
planted_during: unknown
trigger_when: next terminal-workflow itch, or when scoping the milestone after SEED-007 (TUI dashboard) is considered
scope: small
---

# SEED-008: tmux/powerline statusline segment showing Claude Code usage (current usage against plan limit) on the left side of the prompt

## Why This Matters

The tray already computes everything this needs (`claude_monitor/core.py`) and the
daemon already exposes it over a query protocol (`core.query_snapshot`,
`claude-monitor.py:602-614`) — this is much closer to "wire up a formatter" than
"build a feature." Right now getting a usage glance costs a context switch to the
top bar or a browser tab; a tmux segment puts it where a terminal-first workflow
already looks, with zero added polling (reuses the daemon's existing 15s poll —
see Data Source below).

**Important correction discovered during research:** [[SEED-007]]'s note that
"the socket is RECEIVE-ONLY today" is now **stale**. The daemon added a
`{"query": "snapshot"}` verb answered in `_handle_conn` on its own thread, off
the GTK main loop, returning `{heatmap, sessions, usage, trends}` — including
live extras (`cost_usd`, `cost_per_hour`, `pace_*`, `model_mix`) that never hit
the history file. Anything blocked on "no daemon query protocol exists" (this
seed, SEED-007's live-sessions question) should be re-evaluated with that in
mind.

## When to Surface

**Trigger:** next time there's a terminal-workflow itch (checking usage via a
separate command feels like friction), or when scoping the milestone after
v1.4 / alongside SEED-007's TUI dashboard consideration — the two overlap
(both are "core.py gets a text renderer") and could plausibly be scoped
together or share a formatting layer.

This seed will also surface during `/gsd-new-milestone` when the milestone
scope matches.

## Scope Estimate

**Small.** The expensive parts (usage computation, live daemon query, history
fallback, threshold/percent formatting) already exist. New work is:
1. One segment script (`segments/claude_usage.sh` or `.py`) that calls
   `core.query_snapshot()`, falls back to `parse_history`/`latest_state` on
   disk if the daemon is down, and prints a short formatted line.
2. Threshold-to-color/glyph logic (green/yellow/red + a suppressible `!`
   marker), following this project's existing `band()`/`build_label()` idioms
   in `core.py`.
3. Wiring into the user's actual tmux config (see Research Findings — this is
   NOT a `status-left` override, it's a plugin segment).

Live sessions, cost/model-mix display, and any "second data source" concerns
are already solved by the existing socket protocol — no new IPC needed.

## Research Findings (5 parallel Opus agents, 2026-07-25)

**1. tmux mechanics.** `#()` in modern tmux (3.6, confirmed via `man tmux`) is
**asynchronous** — it does not block redraw; it reuses the last output line
until the command finishes, gated by `status-interval` (this machine: 2s). The
real cost is a process fork every tick, not latency. Idiomatic zero-poll
pattern: daemon writes a pre-rendered line to a file, tmux reads it via
`#{F:/path}` (no fork) or a `#()` that just `cat`s it. Escaping: literal `#` ->
`##`, literal `%` -> `%%` (status strings pass through `strftime`).

**2. This machine's actual tmux setup (the load-bearing finding).** The live
config (`~/.config/tmux/tmux.conf:107`) runs **`erikw/tmux-powerline`** via
tpm, and `status-left` is already fully owned by it. **Do not set
`status-left` directly — it would delete the existing powerline.** Instead,
ship a segment script following tmux-powerline's `run_segment()` contract
(echo text only; framework applies theme fg/bg + separators; see
`segments/lan_ip.sh` for the exact shape already in this user's config), then
add `"claude_usage <fg> <bg>"` to `TMUX_POWERLINE_LEFT_STATUS_SEGMENTS` in the
theme. Caching is the segment's own job (tmux-powerline's `weather.sh`
mtime-checks a temp file before refetching — same idiom applies here). Segment
can echo inline `#[fg=...]` for dynamic (threshold-based) coloring. Clickable
segments are supported via `#[range=user|name]` + `MouseDown1Status` binding
(config already uses this idiom at `tmux.conf:120`) if click-to-open-dashboard
is ever wanted.

**3. Data source (confirms Why This Matters above).** Two valid, zero-new-poll
options:
   - **Primary:** `core.query_snapshot(path=SOCK_PATH)` (`core.py:926`) — live
     daemon state including cost/pace/model-mix.
   - **Fallback (daemon down):** read `~/.claude/usage-history.jsonl`
     (`core.HISTORY_PATH`, `core.py:252`) with `core.parse_history` +
     `core.latest_state` (`core.py:482`, `:862`) — same pattern
     `Monitor.write_dashboard` already uses (`claude-monitor.py:378-397`).
     Gives pct/reset/pct7/reset7 fresh to <=15s; burn/tokens available from
     the raw record (not `latest_state`).
   - **Do not call `core.fetch_usage()`** from the segment — that shells out
     to the CLI and takes 5-10s; it's daemon-internal only.
   - Closest existing one-line formatter: `core.build_label(usage, attention)`
     (`core.py:443`) already produces something like `'83%! 2!'`.
   - `claude-send.py` is precedent for a second root script talking to the
     daemon over the socket, but it's fire-and-forget (send-only, no reply
     read) — `core.query_snapshot` is the better model for a read.

**4. Prior art (avoid reinventing).**
   - Claude Code ships a **native `statusLine` hook**
     (`~/.claude/settings.json`, `{"statusLine": {"type": "command", ...}}`)
     that pipes session JSON — including `rate_limits.five_hour/seven_day
     .used_percentage` and `.resets_at` — on stdin, sourced directly from
     Anthropic. This is a second, officially-supported way to get quota
     numbers that doesn't depend on this project's own `fetch_usage()` CLI
     shell-out. Worth a follow-up seed on its own: a tiny statusLine script
     that forwards stdin JSON into the daemon's socket could eventually
     replace/augment the CLI-scraping poll in `poll_loop`.
   - **ccusage** (`ccusage.com/guide/statusline`) — de facto format string
     precedent: `model | $session / $today / $block (2h45m left) | $/hr |
     context%`.
   - **ohugonnot/claude-code-statusline** — reference design for the
     stdin-first/OAuth-endpoint-fallback + shared cache file with `flock` so
     concurrent sessions share one fetch.
   - **worldnine/tmux-claude-live** — daemon writes ~30 `@ccusage_*` tmux
     user-variables every 5s; segment references `#{@var}` directly, an
     alternative to the file-read idiom above.
   - **jimmyliao/agent-status-tmux**, **claude-tmux-status (zenn/long910)** —
     both land on the same `5h:78%(2h47m) 7d:84%!` shape independently.
   - **pcvelz/ccstatusline-usage** — full powerline widget set if richer
     display (session/weekly bars, pace pendulum) is ever wanted.
   - Nothing found reads a local daemon socket the way this project's design
     would — that part is genuinely novel to this project, not reinventable
     from prior art.

**5. UX / format recommendation.** Show exactly two facts — percent used +
time to reset — everything else (burn rate, cost, model mix) stays in the
tray dropdown/dashboard, following the git-segment convention of suppressing
fields at their default/uninteresting value:
```
+ 62% 2h14m       (normal, ~13 chars, no alarm glyph)
+ 91% 0h48m !     (red + glyph once past threshold)
```
Color threshold: green <75%, yellow 75-90%, red >90% is the idiomatic split
(matches tmux-cpu/battery conventions), but the *honest* trigger is projected
exhaustion before reset (mirrors `core.alert_due`/`project()` already in this
codebase), not raw percent alone — 60% with 4h left is fine, 60% with 20min of
burn left isn't. Color + glyph, not color-only (mono/custom-themed terminals,
colorblind-safe). Prefer digits over a block-glyph bar/sparkline at this width
— sparklines encode history, which isn't the question ("am I about to be cut
off?") this segment answers; leave sparklines to the dashboard, which already
has them.

## Open Questions (decide at discuss time)

1. Segment script language — bash (matches tmux-powerline's other segments,
   zero new interpreter cost per tick) vs. a thin Python wrapper importing
   `core.py` directly (reuses `build_label`/`fmt_countdown` instead of
   reimplementing formatting in shell, at the cost of a `python3` fork per
   tick unless caching is used).
2. Whether to also pursue the native `statusLine` hook path (see Research
   Findings #4) as a complementary or even alternative data source to
   `fetch_usage()`'s CLI shell-out — separate scope from the tmux segment
   itself, possibly its own seed.
3. Click-to-dashboard binding (tmux-powerline supports `#[range=user|...]` +
   `MouseDown1Status`, already used elsewhere in this user's config) — nice-to
   -have, not required for MVP.

## Breadcrumbs

- `claude_monitor/core.py:926` — `query_snapshot()`, the live daemon query.
- `claude_monitor/core.py:443` — `build_label()`, closest existing formatter.
- `claude_monitor/core.py:482,862` — `parse_history()` / `latest_state()`,
  disk fallback.
- `claude_monitor/core.py:252` — `HISTORY_PATH`.
- `claude-monitor.py:602-614` — daemon's socket query handler (confirms
  socket is no longer receive-only; [[SEED-007]]'s assumption there is
  stale).
- `claude-monitor.py:378-397` — `Monitor.write_dashboard`, precedent for
  history-file -> render pattern.
- `claude-send.py` — precedent for a second root script talking to the
  daemon over its unix socket (send-only; `query_snapshot` is the better
  model for a read).
- `~/.config/tmux/tmux.conf:107,120` — user's actual `erikw/tmux-powerline`
  setup; segment must plug into `TMUX_POWERLINE_LEFT_STATUS_SEGMENTS`, not
  override `status-left`.
- [[SEED-007]] — TUI dashboard seed; both are "new text renderer over
  `core.py`" and may be worth scoping together.

## Notes

Captured via `/gsd-capture --seed`, then enriched via 5 parallel Opus research
agents (tmux mechanics, powerline plugin conventions, this codebase's actual
data-source options, prior-art web search, UX/threshold design) run
2026-07-25. Findings synthesized above rather than left as raw agent output.
