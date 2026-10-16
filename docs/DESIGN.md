# Design: Margin editorial studio

Margin feels like a carefully composed academic publication and a teacher’s working desk.
Its identity comes from warm paper, aubergine ink, generous literary headings, a restrained
citron accent and the red pen. Decision D-067 supersedes the sidebar and motion restrictions
of D-064, following the owner’s request for a distinctive, animated product experience.

## Visual system

- **Palette:** aubergine `--ink` (#302833), warm `--paper` (#F4F1E9), ivory `--surface`
  (#FFFEFA) and citron `--accent` (#D9E5A2). Muted plum and warm grey define secondary surfaces.
  Colours are centralized in `frontend/src/styles/tokens.css`.
- **Meaning:** marking red stays exclusive to marks, annotations and the paper margin.
  Confirmed green means teacher confirmation. Citron draws attention to assisted work; it
  never means a mark has been confirmed. Errors and warnings retain distinct labelled states.
- **Typography:** bundled Literata provides the wordmark and editorial headings; bundled
  Atkinson Hyperlegible Next handles controls and reading; Caveat represents handwriting in
  the illustrative script and red-pen feedback. Small uppercase labels organize secondary
  metadata. Core form text stays readable. No remote fonts or assets.
- **Depth:** paper layers and small annotation cards cast soft shadows in the sign-in
  demonstration. Working surfaces remain flat, with fine warm rules and restrained corners.
- **Contrast:** `src/styles/tokens.test.ts` checks text/background pairs at 4.5:1 and control
  borders/focus at 3:1, including the citron and plum surfaces. Colour always has a word,
  icon, border or position alongside it.

## Sign-in experience

A split composition pairs a dark editorial story with a quiet ivory form. An original
open-book/margin monogram accompanies the Margin wordmark. The story is “Less marking.
More possibility.” The form keeps the existing sign-in behavior and administrator guidance.

The animated document is explicitly labelled as an illustration. It moves through Scan,
Read, Propose and Review, showing a scanning line, selected evidence, proposed ticks and a
teacher’s annotation. It contains only synthetic copy, never real student data, and does not
claim that an actual job is running. Stage buttons are keyboard accessible; selecting a stage
pauses playback. Pause/play controls stop automatic changes. Reduced-motion preferences
stop automatic progression and CSS animation while preserving manual exploration.

On phones, the sign-in form comes first and the illustrative story follows. On larger
screens, both sit beside one another. English and French have identical translation coverage.

## Workspace and dashboard

- A horizontal workspace bar places Exams, Marking queue, administrator-only Classes and
  Settings in a compact navigation group, with the wordmark and school identity at its edges.
- A quiet context strip holds breadcrumbs, language, identity and sign-out. Keyboard users
  retain a skip link and clear focus states. Narrow screens wrap navigation without hiding
  feature labels or relying on hover.
- The dashboard opens with a large editorial heading and the date. Three work trays hold
  real counts and links for scans, review and confirmed scripts. The dark middle tray gives
  teacher review visual priority. No invented activity, progress or statistics.
- The exam collection remains a semantic table with real class, subject, status and counts;
  it scrolls horizontally on narrow screens. Page titles and shared controls inherit the
  same palette and typography across setup, scanning, review, results and administration.
- Exam workflow tabs remain in the order of the work, with their states in words.
- `styles.css` supplies functional component layouts; `styles/studio.css` supplies the
  editorial shell and responsive presentation. The latter is imported after the base styles.

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
