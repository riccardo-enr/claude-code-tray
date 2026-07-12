# Phase 4 — UI Review

**Audited:** 2026-07-12
**Baseline:** 04-UI-SPEC.md (approved design contract)
**Screenshots:** not captured (no dev server; static `file://` artifact audited from rendered HTML/CSS/SVG source + `render_dashboard` template)

> Scope calibration: this is a local, single-user, stdlib-only `file://` utility dashboard, not a marketing page. Scores judge against the UI-SPEC's *intent*, not an aspirational brand system. But the spec IS an approved, unusually concrete contract (exact tokens, copy, interaction items), and the implementation ignores most of its concrete values while keeping only the load-bearing chart math. That gap is what the scores below reflect.

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 2/4 | Page title wrong; heatmap legend, meta line, and empty-state body all missing from contract |
| 2. Visuals | 2/4 | No card surfaces/hierarchy; focal-point card 1 not distinguished; unexplained gray cells (no legend) |
| 3. Color | 2/4 | Heatmap ramp faithful (correct), but page palette is generic hardcoded hex, not the 210 system |
| 4. Typography | 1/4 | SVG text at 7px/9px directly violates the spec's explicit ">=12px, no cram sizes" rule; no 600 weight; em not the px scale |
| 5. Spacing | 2/4 | All em-based ad-hoc values; none of the declared 4px tokens; no card padding |
| 6. Experience Design | 2/4 | Null-gap breaks correct + range toggle works, but required `<title>` tooltips, focus ring, and hover states all absent |

**Overall: 11/24**

---

## Top 3 Priority Fixes

1. **SVG label text renders at 7px and 9px (`_DASH_JS` lines 487, 514, 516)** — the spec's Typography + Accessibility sections both explicitly forbid this ("12px for ticks/labels, no 10px 'cram' sizes"; "minimum 12px text"). Hour labels at 7px are unreadable at normal zoom. — Fix: raise all SVG `font-size` attributes to 12; if 24 hour columns crowd at 12px, widen the heatmap `viewBox` or label every 3rd hour.
2. **No native `<title>` tooltips anywhere** — the Interaction Contract requires a `<title>` child on every heatmap `<rect>` and each trend region (`"Mon 15:00 — 14.2k tok/hr"` / `"no data"`), serving as both hover tooltip and screen-reader context. Currently zero exist, so hovering a cell/point reveals nothing and the "gray = no data" cells are unexplained. — Fix: append an `el("title")` with `fmt_tokens`-style text to each rect and to trend markers.
3. **Copy contract gaps: wrong page title + missing legend and meta line** — title is `Claude Code Usage` vs contract `Claude Code — Usage Dashboard`; the heatmap `Low -> High / No data` legend and the `Generated {HH:MM} — refreshes every ~5 min` meta line (data is embedded as `D.generated` but never rendered) are both absent. Without the legend, gray cells read as ambiguous. — Fix: correct the `<h1>`, render a gradient+gray-swatch legend under the heatmap, and emit the meta line from `D.generated` in a muted foot.

---

## Detailed Findings

### Pillar 1: Copywriting (2/4)
- BLOCKER-ish (contract): page title `Claude Code Usage` (`_DASH_BODY` L460, `_DASH_EMPTY` L455) != contract `Claude Code — Usage Dashboard`.
- WARNING: heatmap legend (`Low -> High`, `No data` gray swatch) — required by Color + Copywriting contract — is not rendered at all. Gray empty cells (`hsl(0,0%,88%)`, L520) therefore have no on-page explanation.
- WARNING: meta line `Generated {HH:MM} — refreshes every ~5 min` missing. `generated` is embedded in the payload (L552) but never drawn.
- WARNING: empty state collapses the contract's heading + body into a single `Collecting usage history...` line (L456); the reassuring body sentence is dropped.
- Minor/acceptable: chart 2/3 titles reworded (`Daily burn rate (tok/hr)`, `Peak usage heatmap (mean burn tok/hr)`) — deviates from contract wording but is arguably clearer for a utility; not penalized heavily.
- Range labels `Day`/`Week`/`All` match (L462-464).

### Pillar 2: Visuals (2/4)
- The spec names card 1 (usage %) the focal anchor. Implementation renders three identical `<section>`s with no card chrome (`border-radius:8px`, white card on tinted bg) and no differentiation — card 1 does not out-weight the others; hierarchy is flat.
- `svg{border:1px solid #eee}` is the only surface treatment; the declared white-card-on-tinted-page system is absent.
- No legend/key for the heatmap harms interpretability (see Pillar 1).
- Charts do render correctly with populated data (14-day sample); trend + heatmap are legible in structure. `needs_human_review`: exact on-screen crowding of 24 hour labels at their current 7px in a real browser.

### Pillar 3: Color (2/4)
- Faithful: heatmap ramp `hsl(210,80%, 92-(v/vmax)*62 %)` (L521) matches the LOCKED D-07 formula exactly; empty bucket `hsl(0,0%,88%)` (L520) matches the neutral-gray rule. This is the load-bearing color decision and it is correct.
- Divergent: page background `#fafafa` (L444) is neutral, not the specced `hsl(210,20%,98%)`; text `#222`; gridlines `#ccc`; axis text `#888`/`#777`/`#555` — all generic grays, not the 210 family the spec built for coherence with the heatmap hue.
- Accent: trend stroke + active button both `#1a6cae` (L448, L493) — internally consistent and close to the specced `hsl(210,80%,45%)`, but hardcoded hex rather than the contract token. Accent is correctly reserved (strokes + active button only), which the spec asked for.
- No hardcoded-color violation beyond the palette substitution itself; all colors are intentional, just off-contract.

### Pillar 4: Typography (1/4)
- Direct violation of an explicit, twice-stated rule: SVG text at `font-size:9` (L487 axis max label), `font-size:7` (L514 hour labels), `font-size:9` (L516 day labels). Spec: "12px for ticks/labels, no 10px 'cram' sizes" and "minimum 12px text at typical screen zoom." 7px is roughly half the floor.
- No 600 weight used anywhere; `h2` differentiates by color (`#444`) instead of the specced semibold. Contract = exactly 2 weights (400/600); implementation ships 1.
- Sizes expressed as `em` (`h1 1.3em`, `h2 1em`) rather than the declared 20/14/12px scale; body/button text falls back to UA default.
- No `font-variant-numeric: tabular-nums` on numeric labels (spec called for it on tick/legend digits).
- Score 1 reflects a concrete accessibility-floor breach, not perfectionism.

### Pillar 5: Spacing (2/4)
- All spacing is ad-hoc em: `padding:1.5em` (~24px, roughly matches page-padding intent), `section margin 0 0 1.8em`, button `padding:.2em .7em`, `margin-right:.4em`. None use the declared 4px-grid tokens (4/8/16/24/32).
- No card inner padding (16px token) because there are no cards.
- SVG-internal geometry (`cw=20,ch=18`) is exempt drawing math per the spec — not penalized — though `ch=18` is off the "24px square cell" the spec suggested; acceptable as drawing math.
- Not broken, just uncalibrated against the scale.

### Pillar 6: Experience Design (2/4)
- Correct: polylines break across `null` gaps (`pen=false`, L490) rather than drawing false zeros — matches the Phase 3 gap posture and the Chart-line-breaks contract. Burn series `null` days break correctly (visible in sample payload).
- Correct: range toggle is client-side over one embedded dataset (L495-503), active-class toggles, real `<button>` elements (keyboard-focusable for free).
- Missing (contract items): native `<title>` tooltips on rects/trend regions — none exist (grep confirms only the `<head>` title). No hover styling on buttons (spec defines a hover bg + text change). No focus ring (`outline:2px solid accent`) — buttons fall back to UA default outline, and the spec explicitly declared an accent focus style.
- Missing: heatmap legend doubles as the spec's "prevent gray = zero misread" a11y affordance — absent.
- Present: single `<h1>`, `<h2>` per section (semantics OK); empty-state cutover works.

---

## Registry Safety
`components.json` not present and UI-SPEC declares zero third-party registries (all markup hand-generated by stdlib). Registry audit skipped — not applicable.

Note on the one injection surface: the embedded payload is escaped via `_embed_json` (per plan threat T-04-01); `render_dashboard` also routes records through `history_numeric` first. This is a code-safety concern, verified present, not a UI-registry gate.

---

## Files Audited
- claude-monitor.py — `_DASH_STYLE` (L443), `_DASH_EMPTY` (L452), `_DASH_BODY` (L459), `_DASH_JS` (L472), `render_dashboard` (L533)
- /tmp/.../scratchpad/dash_sample.html — rendered 336-record (14-day) populated output
- .planning/phases/04-usage-web-dashboard/04-UI-SPEC.md (baseline), 04-CONTEXT.md
