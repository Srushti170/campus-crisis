# Phase: Side Panel De-Cluttering - Context

**Gathered:** 2026-11-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Restructure the in-game Mission Control side panel (256×640, drawn in `main.py`)
so no more than ~4 information blocks compete for attention at once. Deliver
three mechanisms: a tabbed panel architecture, pruned low-value content, and
map-anchored toast alerts for urgent events. Pure Pygame rendering
(`pygame.draw`, `pygame.font`, `Surface.blit`) — no new dependencies.

</domain>

<decisions>
## Implementation Decisions

### Panel Architecture
- **D-01:** Tabbed panel — 3 fixed tabs sharing the 256px column: `STATUS`
  (stats row, intel line, team health bars), `TACTICS` (AI decisions,
  resources, controls/command buttons), `LOG` (field comms history).
  — **Reversibility:** reversible — redraw-only change; simulation state untouched.
- **D-02:** Tab switching = clickable tab strip in the panel header (~22px) plus
  keyboard F5/F6/F7.
- **D-03:** Pinned zone above tabs = header band (mission title, clock, stats
  icons) + THREAT line. Always visible regardless of tab. Tabs get ~490px.
- **D-04:** LOG tab holds the last ~10 comms messages, newest first, oldest
  fading out. No scrolling/navigation code.

### Content Pruning
- **D-05:** Cut the `[task_score]` numbers from AI decision lines and the
  mission objective sentence from the panel. STATUS becomes: stats row, intel
  line, team bars.
- **D-06:** AI tasks read as short task names (`Scout: Explore Sector 1`),
  clipped to one line, the controlled agent highlighted amber.
- **D-07:** Controls box / Commander's Rescue-Follow-Hold buttons live in
  TACTICS only — not pinned.
- **D-08:** Keep the student-intel line pinned (`SCOUT SEARCHING FOR STUDENT` /
  `STUDENT LOCATED`, amber→green). It fills the line the objective vacated.

### Alerts over the Map
- **D-09:** Toast strip just under the map's top edge (over the fog):
  teammate critical, zombie lock-on, student located, key pickups. Fades after
  ~4s or when resolved.
- **D-10:** Max 3 toasts stacked, newest on top; oldest fades after ~4s;
  critical ones (teammate critical, lock-on) persist until the condition
  clears.
- **D-11:** Keep the pinned THREAT line alongside lock-on toasts — toast =
  the event, pinned line = ongoing pursuit state.
- **D-12:** Toast sounds reuse existing procedural tones: 'hit' for
  critical/lock-on, 'pickup' for pickups. No new audio.

### the agent's Discretion
- Exact pinned-zone pixel budget and tab-strip styling (keep PANEL/GREEN/AMBER
  palette and divider language from the previous pass).
- Toast typography and stacking offsets.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Implementation surface
- `main.py` — all panel rendering lives in `draw()` (side-panel block) and
  `draw_menu()` helpers (`clip_text`, `wrap_line`, `draw_icon_*`, `draw_divider`);
  input handling in the main loop (F5/F6/F7 and tab-strip click handling attach here).
- `world.py` — `game.logs` source for the LOG tab and toasts; actor/zombie state
  for threat detection.

### Prior design decisions (visual language to preserve)
- Palette and reserved-accent rules from the 2026-11-15 UI redesign commit
  (`8362c25`): GREEN for CTA/headers only, AMBER for player-you, red for threats.

No external specs — requirements fully captured in decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `clip_text()` / `wrap_line()` — truncation and wrapping already exist; reuse
  for one-line AI tasks and LOG entries.
- `draw_icon_*` / `draw_star` / `draw_warning_icon` — drawn icon set for stats
  rows and toast glyphs.
- `SOUNDS` dict + `play_sound()` — toast audio without new tone generation.
- `buttons`-style Rect registration pattern — extend for tab strip clicks.

### Established Patterns
- Single `draw()` with state-driven branches (screen_state, full_map) — tabs
  slot in as another state dimension (`active_panel_tab`).
- Panel coordinates are literal constants; keep that convention.

### Integration Points
- `game.controlled_actor()` — amber highlight for "you" rows.
- `game.zombies[*].target_name` — lock-on toast trigger.
- `actor.hp / game.max_hp(a)` — teammate-critical toast trigger (< 35%).
- Existing mute flag (`audio_muted`) gates toast sounds too.

</code_context>

<specifics>
## Specific Ideas

- The user's core complaint: "still too cluttered and too much information" —
  success is judged by *fewer things visible at once*, not smaller text.
- Toast strip sits just under the map's top edge, over the fog, so urgent
  events are seen where the eyes already are.

</specifics>

<deferred>
## Deferred Ideas

- Role-adaptive panel content (Commander vs field-role layouts) — discussed,
  not selected; belongs in its own pass if tabs still feel generic after play.
- Tab auto-switching on relevance (e.g., threat flashes STATUS tab) — noted
  during architecture discussion, rejected for state complexity; revisit later.

</deferred>

---

*Phase: side-panel-decluttering*
*Context gathered: 2026-11-15*
