# Backlog

Ideas and features deliberately not built yet. Add here instead of expanding scope. Brief section 4 items are out of scope for the first build.

## Out of scope for the first build (brief section 4)
- Student or parent portals and logins
- Payments, billing, multi-school cloud hosting
- Model fine-tuning pipelines (this build only exports the dataset)
- Mobile apps
- Automatic segmentation of handwriting into question regions with trained detectors
- Analytics beyond the class results table

## Candidates
- Half marks in the UI and API (storage already supports them, D-018).
- Structured-text mark scheme import format in addition to CSV (owner chose CSV only for v1).
- Native-speaker review of French translations; track draft strings in `docs/TRANSLATIONS.md`.
- Install `make` on Windows dev machines, or document `winget install GnuWin32.Make` (optional; `python scripts/check.py` is equivalent).
- Licence audit script that fails `check` if a new dependency has a non-permissive licence.
- Teacher-facing read-only view of their class's students (the API exists: `GET /api/classes/{id}/students`); Phase 1 shows students in the admin screens only.
- Users changing their own password; "sign out of all devices"; list of active sessions.
- Sign-in throttling per client IP in addition to per username.
- Admin audit-log viewer and export.
- Real-browser end-to-end tests (for example Playwright; needs dependency approval). Phase 1 UI is covered by jsdom component tests plus an HTTP end-to-end script.
- Editing exam details after `ready` (for example fixing a title typo during marking).
- Rendering of maths and chemistry notation in transcriptions and mark schemes: superscripts (x^2,
  Na^+), subscripts (H_2O), fractions ((a+b)/(c-d)), square roots and reaction arrows, shown as formatted
  text in the review screen while the stored text keeps the agreed plain notation. Must be bundled
  locally (no CDN), and its licence approved like any dependency.
