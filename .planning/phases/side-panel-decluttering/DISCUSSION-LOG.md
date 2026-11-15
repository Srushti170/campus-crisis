# Discussion Log — Side Panel De-Cluttering

**Session:** 2026-11-15
**Mode:** discuss-phase (adaptive run — no GSD planning initialized; no phase number on roadmap)

## Context
User request: "create a better side bar it is still too cluttered and too much information is there no way to make it better". Prior session (commit 8362c25) added dividers, icons, threat tint, wider bars — styling fixes. Residual problem is information density.

## Areas discussed

### Panel Architecture (4 questions)
| Question | Options presented | Decision |
|---|---|---|
| Restructure mechanism | Tabs / Collapsible sections / Single-focus panel | **Tabs** (recommended) |
| Tab switching | Click + F5-F7 / Single cycle key / Auto-switching | **Click + F5-F7** (recommended) |
| Pinned info | Header+threat / Nothing / Header+threat+team | **Header + threat** (recommended) |
| LOG depth | Last 10 / Scrollable full log / Last 3 | **Last 10, newest first** (recommended) |

### Content Pruning (4 questions)
| Question | Options presented | Decision |
|---|---|---|
| Objective + task scores | Cut both / Cut scores only / Keep | **Cut both** (recommended) |
| AI task line format | Short names / Two-word gist / Full text | **Short task names** (recommended) |
| Controls location | TACTICS only / Pinned / Under map | **TACTICS only** (recommended) |
| Student intel line | Keep pinned / STATUS only / Fold into team list | **Keep pinned** (recommended) |

### Alerts over the Map (4 questions)
| Question | Options presented | Decision |
|---|---|---|
| Urgent event delivery | Toast strip on map / Panel-only urgency / Critical-only toasts | **Toast strip on map** (recommended) |
| Multi-alert behavior | Max 3 fade+persist / Queue one at a time / Stay until dismissed | **Max 3, fade + persist** (recommended) |
| Pinned THREAT line fate | Keep both / Drop line / Threat into STATUS | **Keep both** (recommended) |
| Toast sounds | Reuse tones / New critical tone / None | **Reuse existing tones** (recommended) |

Note: one "pinned THREAT line" question returned an empty answer; retried once per answer-validation rule and was answered.

## Agent discretion items
- Pinned-zone pixel budget and tab-strip styling within existing palette.
- Toast typography and stacking offsets.

## Deferred ideas
- Role-adaptive panel content (own future phase).
- Tab auto-switching on relevance (rejected for state complexity, revisit later).
