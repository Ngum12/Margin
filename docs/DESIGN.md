# Design: "Marking desk"

Margin is a serious academic tool for teachers. Its visual language comes from the exam script,
the teacher's red pen and the red margin line of an exercise book: calm, professional and
distinctive, never playful and never a generic software template. This file is the reference for
anyone changing the interface. Decision: D-064.

## Rules

- **One source of truth.** Colours, type sizes, spacing, radii and shadows are CSS custom
  properties in `frontend/src/styles/tokens.css`. `styles.css` uses only those tokens: no colour
  is written anywhere else.
- **Marking red (`--mark-red`) only for marks:** ticks, crosses, scores, deductions, red-pen
  annotations and the margin line. Never for buttons, errors or decoration. The marked PDF uses
  the same red (`app/redpen/draw_pdf.py`).
- **Confirmed green (`--confirmed`) only for "confirmed by the teacher":** the confirmed badge,
  the confirmed total and the "Marks confirmed." message.
- **Problems have their own tones.** Errors and destructive actions use `--danger` text on
  `--danger-bg`, with explicit wording. Warnings use `--warn` on `--warn-bg`.
- **Shape and depth.** Radius 4 px for controls, 6 px for panels and 0 on the scanned page.
  Shadows only on overlays (dialogs, the skip link). No gradients, no blur or glass, no emoji.
- **Colour is never the only signal.** Every state also has a word or a shape:
  - exam tab states are written out ("Done", "Needs action");
  - ✓ and ✗ carry spoken labels;
  - the current rail item is bold, filled and marked with a bar;
  - "worth reteaching" has an icon and screen-reader text.
- **Motion.** Confirming a script is the one animated moment: the total settles in green with a
  260 ms stamp. Otherwise there are only short transitions that show what changed. Everything is
  turned off under `prefers-reduced-motion`.
- **Offline.** Fonts and icons are bundled. Nothing is loaded from another host.

## Colour and contrast (WCAG AA)

Every pair below is checked by `src/styles/tokens.test.ts`, which reads `tokens.css`, so a token
change that breaks contrast fails the check suite. The minimum is 4.5:1 for text and 3:1 for
control borders and focus rings.

| Foreground | Background | Ratio | Minimum | Used for |
|---|---|---|---|---|
| `--ink` #1B2A41 | `--surface` #FFFFFF | 14.44:1 | 4.5:1 | Body text on panels |
| `--ink` #1B2A41 | `--paper` #F4F6F8 | 13.33:1 | 4.5:1 | Body text on the app background |
| `--ink-2` #44546A | `--surface` #FFFFFF | 7.71:1 | 4.5:1 | Secondary text on panels |
| `--ink-2` #44546A | `--paper` #F4F6F8 | 7.12:1 | 4.5:1 | Secondary text on the background |
| `--ink-3` #5C6B80 | `--surface` #FFFFFF | 5.43:1 | 4.5:1 | Disabled and line-number text |
| `--ink-3` #5C6B80 | `--paper` #F4F6F8 | 5.01:1 | 4.5:1 | Disabled text in disabled fields |
| `--ink` #1B2A41 | `--info-bg` #EAF0F7 | 12.59:1 | 4.5:1 | Notices |
| `--ink` #1B2A41 | `--selected` #DCE6F1 | 11.44:1 | 4.5:1 | Selected rows, evidence lines |
| `--link` #24538F | `--surface` #FFFFFF | 7.75:1 | 4.5:1 | Links |
| `--link` #24538F | `--paper` #F4F6F8 | 7.16:1 | 4.5:1 | Links on the background |
| `--surface` #FFFFFF | `--ink` #1B2A41 | 14.44:1 | 4.5:1 | Primary buttons; active exam tab number |
| `--rail-text` #E8EDF3 | `--ink` #1B2A41 | 12.27:1 | 4.5:1 | Side rail items |
| `--rail-muted` #A9B6C6 | `--ink` #1B2A41 | 7.01:1 | 4.5:1 | Side rail secondary text |
| `--rail-text` #E8EDF3 | `--rail-active` #2A3B57 | 9.58:1 | 4.5:1 | Current side rail item |
| `--mark-red` #B3261E | `--surface` #FFFFFF | 6.54:1 | 4.5:1 | Marks, ticks, crosses, deductions |
| `--mark-red` #B3261E | `--paper` #F4F6F8 | 6.03:1 | 4.5:1 | Marks on the background |
| `--confirmed` #2F5D4A | `--surface` #FFFFFF | 7.54:1 | 4.5:1 | Confirmed state text |
| `--confirmed` #2F5D4A | `--confirmed-bg` #E7F0EB | 6.48:1 | 4.5:1 | Confirmed badge and total |
| `--danger` #8C2F14 | `--danger-bg` #FBEDE8 | 7.26:1 | 4.5:1 | Errors, test-model warnings |
| `--danger` #8C2F14 | `--surface` #FFFFFF | 8.29:1 | 4.5:1 | Destructive buttons |
| `--warn` #8A5A00 | `--warn-bg` #FFF6E0 | 5.51:1 | 4.5:1 | Warnings |
| `--warn` #8A5A00 | `--surface` #FFFFFF | 5.93:1 | 4.5:1 | "Needs action" tab state |
| `--field-border` #7D8DA3 | `--surface` #FFFFFF | 3.38:1 | 3:1 | Form control borders (non-text) |
| `--focus` #2F6FB3 | `--surface` #FFFFFF | 5.19:1 | 3:1 | Focus ring (non-text) |
| `--focus` #2F6FB3 | `--paper` #F4F6F8 | 4.79:1 | 3:1 | Focus ring on the background |
| `--rail-focus` #9CC3F0 | `--ink` #1B2A41 | 7.89:1 | 3:1 | Focus ring on the side rail |

`--rule` (#C9D6E3) is used only for decorative dividers and, at 35 % opacity, for the evidence
bands on the page. Neither carries meaning on its own.

## Type

| Role | Font | Use |
|---|---|---|
| Titles | Literata SemiBold (serif) | Page titles, exam titles and student names only |
| Interface | Atkinson Hyperlegible Next (variable weight) | All other text, tables and numbers |
| Fallback | Noto Sans | Any glyph the interface font lacks (downloaded only when needed) |
| Red pen | Caveat | Red-pen annotations on screen and in the marked PDF, nowhere else |

- **Scale:** 13 / 15 (body) / 17 / 21 / 28 px. Body line height is 1.5, and prose is limited to
  76 characters per line.
- **Numbers:** marks, totals and all tables use tabular figures (`font-variant-numeric:
  tabular-nums`).
- **Case:** sentence case everywhere. No all-caps labels and no letter-spaced "eyebrow" labels.

## Layout

- **Shell.** A narrow ink side rail holds the school name, Classes (administrators), Exams,
  Marking queue and Settings. A light top bar holds the breadcrumb (School / Class / Exam), the
  language menu and the user.
  - From 1280 px wide the rail shows labels.
  - From 1024 to 1279 px the rail shows icons only; the labels stay for screen readers and
    tooltips.
  - Tested at 1366×768 and 1024×768, in English and French.
- **Dashboard, "What needs you today".** Three steps in the order of the work, with real counts
  and links: exams waiting for scans, scripts waiting for review, scripts confirmed. There are no
  charts. "Confirmed this week" needs a confirmation date in the exam list, which the API does not
  give, so the dashboard shows all confirmed scripts (see the backlog).
- **Exam page.** Tabs in the order of the work: Mark scheme, Cover sheets, Scans, Marking,
  Results. Each tab states, in words and with a small icon, whether it is done, needs action, is
  in progress or comes later (`src/exam/workflow.ts`).
- **Mark scheme.** Laid out like a printed mark scheme: question, points, and marks on the right.
  Fields look like the dotted lines of a form and show their box on hover or focus.
- **Scans and page check.** One script per row with its page thumbnails (lazy-loaded). Unplaced
  pages show their reason and a one-click fix (Discard, Restore, Unassign).
- **Results.** A sortable class table with one column per question. Two footer rows: the class
  average, and the share of confirmed scripts that scored zero. Questions where 40 % or more
  scored zero are flagged as worth reteaching. A print style shows the table without the app
  around it.

## The marking desk (review)

- **Top bar:** the student's name (Literata), the script's position ("Script 3 of 28"), the
  total so far, the points decided, previous/next, the shortcuts, "Re-run AI marking" and
  "Confirm marks".
- **Left (about 60 %): the page.** The scan is shown large on a plain surface, with zoom, pan and
  rotation. A thin marking-red margin line runs down its left edge. The selected point's evidence
  lines appear as rule-blue bands, positioned from the red-pen layout. The AI's proposed marks are
  written in red Caveat in the margin; proposals not yet decided are lighter.
- **Right (about 40 %): the checklist** for the current question. Each point shows:
  - ✓, ✗ or a fraction;
  - the AI's proposal, its reason (category and confidence) and the evidence line numbers
    ("Lines 3–4, page 2");
  - the marks as one-click buttons, plus the category.

  Below the checklist are the comment and the numbered transcription, with the evidence lines
  shaded.
- **Keyboard** (`src/review/keyboard.ts`; `?` lists every key):

  | Key | Action |
  |---|---|
  | J / K | Next / previous script |
  | ← / → | Previous / next question |
  | ↑ / ↓ | Previous / next point |
  | 0–9 | Set the focused point's mark |
  | E | Show or hide the evidence |
  | Enter | Confirm marks (a focused button or link is pressed instead) |
  | T | Edit the transcription |
  | D, A, Shift+A, C, M | Next deduction, accept, accept all, category, comment |
  | [ ], + − F, R / Shift+R | Pages, zoom, rotate |

## Copy

- Plain words and active verbs.
- An action keeps the same name throughout: the button "Confirm marks" leads to "Marks
  confirmed."
- Errors say what happened and how to fix it.
- Empty states tell the teacher the next step.
- French runs about 20 % longer; every screen is checked in French at 1024 px.

## Quality floor

- Visible keyboard focus on everything: a 2 px focus ring, with a lighter ring on the rail.
- A skip link to the main content.
- Screen-reader labels on icon-only buttons.
- Colour is never the only signal.
- A print style for results.
- No UI or animation libraries; images are lazy-loaded.
- Icons: 34 Lucide icons copied as path data into `src/components/icons.ts` (ISC; icons derived
  from Feather are MIT), used sparingly.
