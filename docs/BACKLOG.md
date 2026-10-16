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
- Rotate a page in the review UI (answer pages scanned upside down without PDF rotation metadata stay as scanned; cover sheets are turned upright automatically).
- Show `THIRD_PARTY_NOTICES.md` from an "About" page in the app.
- Per-student PDF files of the original scans (not needed until marked-PDF export in Phase 5, which builds from page images).
- Upload progress bar for large PDFs (the browser's `fetch` gives no upload progress; would need XMLHttpRequest).
- Printable teacher distribution list (code to name) for handing out cover sheets; Phase 2 shows it on screen only.
- Re-run AI marking for selected scripts with a new model or prompt version (results are versioned already; needs a UI and a deliberate "replace proposals" rule).
- Per-question marking when the model's context is too small for a whole script; send only the relevant pages per question (needs question regions).
- Show model output invalid rates and timings to admins (from the job table and evaluation reports).
- A real evaluation set: teacher-typed transcriptions of real (consented) scripts per subject. The Phase 3 sample set is synthetic.

## Deployment modes 2 and 3 (D-052; not built yet)
What a district hub (mode 2) and a Margin-hosted cloud (mode 3) will need beyond the school box:
- **TLS everywhere:** browser to server, server to model server, server to database; no plain-HTTP option in these modes.
- **Stronger authentication:** multi-factor sign-in for staff, optional single sign-on with the district or ministry identity provider, shorter sessions, account lockout reporting.
- **Per-school data separation:** every query scoped by school (tenant), tested like the class scoping; per-school storage folders or buckets; admins of one school can never see another's data; district-level roles defined explicitly.
- **Resumable, compressed uploads:** scans sent over slow or unreliable links in chunks that resume after a dropped connection, with compression and checksums.
- **Data retention and deletion:** a configurable retention period per school; deleting a school's, class's or student's data (database rows, page images, original PDFs, backups), with an audit record of the deletion.
- **A data processing agreement template** for schools, districts and Margin (who controls the data, where it is stored, sub-processors: none for AI, retention, breach notification).
- Mode 3 only: our own model servers sized for many schools (queueing, fair scheduling between schools), and monitoring that never includes student content.
- Mode 3 only: **replace `MARGIN_ALLOW_PUBLIC_MODEL_HOST` with an explicit allowlist of approved model hosts** (for example `MARGIN_APPROVED_MODEL_HOSTS`). Private and loopback hosts are accepted as today; a public host is accepted only if it is on the list, never through a general on/off switch. When built, add a test that an unlisted public host is refused at start-up, even in cloud mode.

## From the UI redesign (D-064)
- **"Scripts confirmed this week" on the dashboard:** needs each exam's confirmations dated in the exam list API (for example `scripts.confirmed_this_week`). The redesign changed no API, so the dashboard shows all confirmed scripts for now.
- **An "AI's short reason" per point:** the marker gives a category and evidence, not a written reason. A one-line reason field would need a prompt and schema change (and an evaluation).
