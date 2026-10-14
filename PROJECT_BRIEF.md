# Project Brief: On-Premise AI Marking Assistant for African Secondary Schools

Working name: Marking Assistant. Owner: Dieudonne Ngum.
Status: greenfield build. First milestone: working demo for the MIT Solve 2027 Global Learning Challenge (application deadline 2 November 2026; demo must be working by 26 October 2026).

---

## 0. How to work on this project (read first)

You are the lead engineer on a production product, not a demo. Schools will trust this system with children's exam scripts. Work accordingly.

1. Read this entire brief before writing any code.
2. Create `CLAUDE.md` at the repo root that summarises the non-negotiables (section 3), the architecture (section 5), the commands to run checks, and the current phase. Keep it updated as the project evolves.
3. Create `docs/DECISIONS.md`. Record every significant technical decision as a short entry: date, decision, alternatives considered, reason. If you must deviate from this brief, record why there first.
4. Produce a written plan for the phase you are about to build: files to create, data model changes, tests to write. Then build it.
5. Build strictly one phase at a time (section 9). At the end of each phase: run the full check suite, fix every failure, commit, then **stop and report** what was built, what was tested, what is incomplete and any risks. Do not start the next phase until the owner says so.
6. Never claim something works unless you ran it. If you could not run something (for example, no GPU or no Ollama model available), say so explicitly and keep it covered by the mock model path.
7. Do not guess library APIs. Check the installed version's documentation or source when unsure. Pin dependency versions.
8. Stay in scope. If you think a feature is missing, add it to `docs/BACKLOG.md` instead of building it.
9. Ask the owner only when a decision is genuinely blocking and cannot be resolved by this brief or a sensible default. Otherwise choose the conservative option and record it in `docs/DECISIONS.md`.

---

## 1. What we are building

A system that lets a secondary school mark handwritten exam scripts with AI assistance, entirely on the school's own premises.

The loop:

1. A teacher creates an exam in the dashboard: subject, questions, mark scheme points and maximum marks.
2. The system generates a printable cover sheet for each student, carrying a QR code that identifies the exam and the student. Sheets are printed on the school's existing printer.
3. Students write their answers. The cover sheet goes on top of each script.
4. The teacher scans the whole class stack on the school's existing scanner or multifunction printer into one PDF and uploads it to the dashboard.
5. The system reads the QR codes, splits the PDF into one script per student and stores page images.
6. A background worker runs the AI pipeline, usually overnight:
   - **Reader**: a vision model transcribes each page exactly as written, including the student's errors.
   - **Marker**: a model compares the transcription with the mark scheme, point by point, and proposes marks with quoted evidence.
7. The teacher reviews each script in the dashboard: scan on one side, transcription and proposed marks on the other. The teacher accepts, edits or overrides. Nothing is final until a teacher confirms it.
8. The system exports a marked PDF per student (marks and short comments overlaid on the original scan, ready to print) and class results as CSV.
9. Every teacher correction is stored as labelled data. With consent, this data is used to fine-tune our own models, which are then shipped back to schools as model updates.

Subjects in the first version: Chemistry, Mathematics, Economics (Cameroon GCE O-Level style). The design must make adding subjects and curricula a configuration task, not a code change.

---

## 2. Why this product wins (this shapes design decisions)

Big technology companies will add AI grading features to their platforms. We win where they structurally cannot follow. Every design decision should strengthen at least one of these:

1. **Data never leaves the school.** No cloud dependency for marking. Schools, parents and ministries can trust it in a way no foreign cloud API can offer.
2. **Works where the internet does not.** Fully offline on a school's local network, tolerant of power cuts, runs on modest hardware.
3. **Teacher in control.** The AI proposes, the teacher decides. Every mark is explainable with evidence from the student's own words. This is what makes it acceptable to schools and exam authorities.
4. **Fluent in African classrooms.** Curriculum-native mark schemes (GCE, WAEC, KNEC, REB and others later), English and French interfaces from day one, and the ability to tell a weak-English answer apart from a wrong-concept answer. That distinction is a core feature, not a detail.
5. **The data flywheel.** Every teacher correction produces labelled African handwriting paired with expert marks. Over time this becomes a dataset and a fine-tuned model no competitor has. The system must capture this data cleanly, with full provenance and consent, from the first day.

---

## 3. Non-negotiables

Breaking any of these is a critical bug.

**Privacy and security**
- No student data, script image, transcription or mark ever leaves the school server. The only network calls the application makes are to the configured local model server (default: Ollama on localhost or the local network).
- No telemetry, analytics, external fonts, CDNs or third-party scripts. All frontend assets are bundled and served locally.
- Add an automated test that fails if application code attempts an outbound connection to any host other than the configured model host.
- Students are identified on paper and to the models only by a pseudonymous code. Real names are optional, stored only in the local database, and never sent to any model.
- Passwords hashed with Argon2. Authenticated sessions with secure, httpOnly cookies. CSRF protection on state-changing requests. Role-based access: `admin` and `teacher`. A teacher sees only their own classes and exams.
- Uploaded files and generated images are stored outside any publicly served directory and served only through authenticated endpoints. Validate upload type and size. Treat uploaded PDFs as untrusted input.
- Secrets come from environment variables or a local config file excluded from git. No secrets in code.

**Trust and correctness**
- The AI never finalises a mark. Every script requires teacher confirmation before export.
- Every AI output stores the model name, model version, prompt version and timestamp.
- Every change to a mark or transcription is written to an append-only audit log: who, when, old value, new value, reason (optional).
- Model output must be validated against a strict schema. Invalid output is retried a bounded number of times, then the item is flagged for manual marking. Never silently drop or invent data.

**Resilience**
- Long-running work runs in a background worker backed by a database job table. Jobs survive restarts and power cuts and resume without duplicating work (idempotent steps).
- The web app stays usable while the worker is busy or the model server is down. The UI shows clear status instead of failing.

**Licensing**
- The product will be sold commercially. Use only dependencies under permissive licences (MIT, BSD, Apache 2.0 or similar). Do not use AGPL or GPL libraries. In particular, do not use PyMuPDF (AGPL). Record each dependency and its licence in `docs/DEPENDENCIES.md`.

**Product quality**
- All user-facing strings go through an internationalisation layer with English and French. French translations may be marked as draft, but the structure must exist from the start.
- The UI must work well on modest laptops and on a tablet-sized screen, over a local network.

---

## 4. Out of scope for this first build

Do not build these now. Note ideas in `docs/BACKLOG.md`.
- Student or parent portals and logins
- Payments, billing, multi-school cloud hosting
- Model fine-tuning pipelines (we only export the training dataset in this build)
- Mobile apps
- Automatic handwriting segmentation into question regions using trained detectors
- Analytics dashboards beyond the class results table

---

## 5. Architecture

One machine per school runs everything.

```
[School scanner] --PDF--> [Browser: teacher dashboard]
                                 |
                          [FastAPI app] ---- [SQLite database]
                                 |               [Local file store]
                          [Worker process] ---- [Ollama: local vision model]
```

**Backend**
- Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x with Alembic migrations.
- Database: SQLite in WAL mode for single-school deployments. Write all queries through SQLAlchemy so PostgreSQL can be swapped in later without code changes.
- Worker: a separate Python process that polls the jobs table. No Redis or external broker.
- PDF and image handling with permissively licensed libraries only, for example: `pypdfium2` for rendering pages, `pypdf` for splitting and merging, `reportlab` for generating cover sheets and annotation overlays, `segno` for QR generation, `zxing-cpp` for QR decoding, `Pillow` for images. Verify each licence before adding.
- Render scanned pages at 200 to 300 dpi and store as PNG or high-quality JPEG.

**Model layer (the most important abstraction)**
- Define two interfaces in `backend/app/ai/`:
  - `Reader.transcribe(pages: list[PageImage], subject: SubjectConfig) -> Transcription`
  - `Marker.mark(transcription: Transcription, exam: ExamSpec) -> MarkingProposal`
- Implementations:
  - `OllamaReader` and `OllamaMarker`, calling the Ollama HTTP API on the configured host. Model names come from configuration (defaults: a Qwen3-VL 8B vision model; confirm the exact tag available in Ollama and record it in `docs/DECISIONS.md`).
  - `MockReader` and `MockMarker`, deterministic, used in tests, development and demos without a GPU.
- The rest of the application depends only on the interfaces. Swapping to a fine-tuned model later must be a configuration change.
- Prompts live in versioned files (`backend/app/ai/prompts/`), each with a version identifier stored alongside every output.
- Reader rules: transcribe exactly, preserve spelling, grammar and subject errors, keep line breaks, use the agreed notation (`H_2O`, `x^2`, `->`, `[?]` for unreadable, `[DIAGRAM]` for diagrams). Never correct the student.
- Marker output, per mark scheme point: awarded marks, a short quoted evidence span from the transcription, a confidence value, and an error category from: `correct`, `conceptual_error`, `language_expression` (the idea is right but the English is weak), `transcription_uncertain`, `omitted`. Use JSON output constrained by schema where the model server supports it.
- Low-confidence items and `transcription_uncertain` items are surfaced first in the teacher review queue.

**Frontend**
- React with TypeScript, built with Vite, served as static files by the FastAPI app. No runtime dependency on the internet.
- A component library or Tailwind is acceptable if bundled locally. Design must be plain, calm and professional: high readability, clear hierarchy, no decorative gradients.
- i18n with English and French from the first screen.

**Deployment**
- Docker Compose with three services: `app`, `worker`, `ollama`. Also document a non-Docker path for development.
- One `.env.example` documenting every setting.
- A `make check` (or equivalent script) that runs formatting, linting, type checks and all tests for backend and frontend.

---

## 6. Data model (starting point; refine and record changes)

- `School`: name, country, curriculum.
- `User`: name, email or username, password hash, role, preferred language.
- `Class`: name, academic year, teacher.
- `Student`: pseudonymous code (unique per school), optional display name (local only), class, consent flag for training-data use, consent recorded date and by whom.
- `Exam`: class, subject, title, date, status (`draft`, `ready`, `marking`, `reviewing`, `completed`).
- `Question`: exam, number or label, prompt text, maximum marks, order.
- `MarkSchemePoint`: question, description, marks, acceptable alternatives, order.
- `Upload`: exam, original PDF reference, uploaded by, time, processing status, errors.
- `Script`: exam, student, status (`waiting`, `transcribed`, `ai_marked`, `in_review`, `confirmed`), confirmed by, confirmed at.
- `Page`: script, page number, image reference, source upload, source page index.
- `Transcription`: script or page, text, source (`model` or `teacher`), model and prompt version, created at. Keep all versions; never overwrite.
- `MarkDecision`: script, mark scheme point, proposed marks, evidence, confidence, error category, model and prompt version, final marks, final category, decided by, decided at.
- `Job`: type, payload, status, attempts, last error, timestamps, idempotency key.
- `AuditEvent`: actor, entity, entity id, action, old value, new value, time.
- `ModelVersion`: name, role (`reader` or `marker`), source, installed at, notes.

Uploads with pages that have no readable QR code go into an "unassigned pages" tray, where the teacher assigns them manually. Never guess.

---

## 7. Screens (first build)

1. **Sign in** and language switch (English and French).
2. **Home**: the teacher's exams with status and counts (scripts waiting, AI marked, confirmed).
3. **Exam setup**: questions and mark scheme points, editable, with a simple import from a structured text or CSV format. Validation for totals.
4. **Cover sheets**: generate a single print-ready PDF with one cover sheet per student (QR code, student code, exam title, subject, date, short instruction).
5. **Upload scans**: upload one or more PDFs, see split results, see and resolve unassigned pages.
6. **Marking queue**: list of scripts with status, sorted with uncertain items first. Button to start AI marking (queues jobs) and live progress.
7. **Script review** (the core screen): page images with zoom on the left; on the right, the transcription (editable, versioned) and, per question, each mark scheme point with proposed marks, evidence quote, confidence and error category. Teacher can accept all, adjust marks, change category, add a short comment. Keyboard shortcuts for fast review. Confirm script.
8. **Results**: class table of total and per-question marks; export CSV; export marked PDFs (single file per student and one combined file for printing).
9. **Admin**: users, classes and students (including consent flags), model configuration and model server status, training-data export.

---

## 8. Training-data export (the flywheel)

Admin-only action that exports, for confirmed scripts of students with training consent only:
- page images (or answer crops when available),
- the final teacher-approved transcription,
- the final marks and error categories per mark scheme point, alongside the model's original proposal,
- question text and mark scheme, subject, curriculum,
- model and prompt versions.

Format: a folder with images and a `dataset.jsonl` manifest, plus a `README` describing fields. Pseudonymous codes only, no names. Log every export in the audit log.

---

## 9. Build phases and acceptance criteria

Build in this order. Stop after each phase and report.

**Phase 0: Foundation**
- Repository structure (`backend/`, `frontend/`, `docs/`, `deploy/`), `CLAUDE.md`, `docs/DECISIONS.md`, `docs/BACKLOG.md`, `docs/DEPENDENCIES.md`.
- Tooling: ruff, mypy, pytest; eslint, TypeScript strict, vitest. One `make check` command.
- FastAPI app and React app running locally, frontend served by backend in production mode.
- Configuration via environment, `.env.example`.
- Done when: `make check` passes and the app starts with one command.

**Phase 1: Accounts, classes, exams, mark schemes**
- Models, migrations, auth (Argon2, sessions, CSRF, roles), i18n scaffolding.
- Screens 1, 2, 3 and the class and student parts of screen 9.
- Done when: tests cover auth, permission boundaries (a teacher cannot read another teacher's exam) and mark scheme validation; a teacher can sign in and create a complete exam in English or French.

**Phase 2: Cover sheets, upload, split**
- Cover sheet PDF generation with QR codes.
- PDF upload, page rendering, QR decoding, splitting into scripts, unassigned pages tray.
- Done when: an automated test generates cover sheets, builds a synthetic scanned PDF (cover sheets plus answer pages, including rotated pages and one page with an unreadable QR), uploads it and asserts correct splitting and correct handling of the bad page.

**Phase 3: AI pipeline**
- Job table and worker with retries, idempotency and resume after restart.
- Reader and Marker interfaces, Ollama and Mock implementations, versioned prompts, schema validation, bounded retries, flag-for-manual on failure.
- The outbound network guard test.
- Done when: with the Mock models, a full exam goes from upload to `ai_marked` automatically; killing the worker mid-run and restarting completes the run with no duplicated results; with Ollama available, one real script can be transcribed and marked (report honestly if Ollama could not be tested).

**Phase 4: Teacher review**
- Screens 6 and 7, audit log, confirm flow, uncertainty-first ordering, keyboard shortcuts.
- Done when: tests prove every edit is audited and that unconfirmed scripts cannot be exported; a teacher can review and confirm a script quickly using only the keyboard.

**Phase 5: Results and exports**
- Screen 8: results table, CSV, marked PDF generation with overlays on original scans.
- Training-data export (section 8), consent-filtered.
- Done when: tests check CSV totals against stored marks and that the dataset export excludes non-consented students and contains no names.

**Phase 6: Deployment and demo readiness**
- Docker Compose for app, worker and Ollama. Installation guide for a school machine written for a non-specialist. Backup and restore script for the database and file store.
- Seed script that creates a demo school, class and exam in each of Chemistry, Mathematics and Economics, using the Mock models so the full flow can be demonstrated without a GPU.
- Done when: a fresh machine can go from clone to working demo by following the guide, with no internet needed after installation.

---

## 10. Engineering standards

- Type hints everywhere in Python; TypeScript strict mode.
- Small, focused modules. Business logic separate from HTTP handlers.
- Tests for every business rule, permission boundary and data transformation. Use the Mock models for AI paths.
- Clear error messages for teachers, in plain language, translated.
- Structured logging to local files with rotation. Never log student transcriptions or images in plain logs.
- Database migrations for every schema change. No manual schema edits.
- Commit after each completed phase with a clear message describing what was built.

---

## 11. Start now

1. Read this brief fully.
2. Create `CLAUDE.md`, `docs/DECISIONS.md`, `docs/BACKLOG.md` and `docs/DEPENDENCIES.md`.
3. Write the plan for Phase 0 and Phase 1, including the proposed file tree and data model, in `docs/PLAN.md`.
4. Ask any genuinely blocking questions. If none, build Phase 0, run `make check`, commit, and stop with a report.
