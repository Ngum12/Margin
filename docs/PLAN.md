<!-- Updated implementation status: the approved 2026-10-16 blueprint items 1–8
are implemented. Historical phase descriptions below are retained as design
context; current acceptance boundaries are in BLUEPRINT_AUDIT.md and README.md. -->

# Current approved blueprint (2026-10-16)

All eight approved build items are implemented: scanner/printer workflow, QR
sheets, scheme rules/imports, resumable marking, phone capture, student
release/remarks, registers/results/history, and deployment/backup reliability.
See BLUEPRINT_AUDIT.md for commit evidence and hardware acceptance boundaries.
The historical phase plan below is retained for design context; its old
approval/status lines are superseded by this paragraph.

# Plan: Phase 0 and Phase 1

Status: Phases 0 and 1 complete and approved (2026-10-14). Phase 2 complete and approved (2026-10-14). Phase 3 built; model evaluation running. Phase 4 planned, awaiting approval. Refinements made while building are recorded in DECISIONS (D-021 to D-026).
Source of truth for requirements: `PROJECT_BRIEF.md`. Decisions referenced here are recorded in `docs/DECISIONS.md`.

---

## Phase 0: Foundation

### Goal
A repository with working tooling, a FastAPI backend and a React frontend, the frontend served by the backend in production mode, configuration from the environment, and one command (`make check`, or `python scripts/check.py` where `make` is unavailable) that runs every check.

### Files to create

```
Margin/
├── PROJECT_BRIEF.md
├── CLAUDE.md                     # non-negotiables, architecture, commands, current phase
├── Makefile                      # thin wrapper over scripts/*.py (check, run, dev, install)
├── .env.example                  # every setting, documented
├── .gitignore
├── scripts/
│   ├── check.py                  # stdlib-only check runner (format, lint, types, tests, build)
│   └── run.py                    # one command: build frontend if needed, start the app
├── backend/
│   ├── pyproject.toml            # pinned deps, ruff/mypy/pytest config
│   ├── uv.lock
│   ├── .python-version           # 3.12
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py               # create_app(): API router, security headers, SPA static serving
│   │   ├── config.py             # Settings (pydantic-settings, MARGIN_ prefix)
│   │   ├── logging_config.py     # rotating file logs under data dir
│   │   ├── security_headers.py   # CSP default-src 'self' and related headers
│   │   ├── spa.py                # serves frontend/dist with SPA fallback
│   │   └── api/
│   │       ├── __init__.py
│   │       └── health.py         # GET /api/health
│   └── tests/
│       ├── conftest.py
│       ├── test_health.py
│       ├── test_config.py
│       ├── test_security_headers.py
│       └── test_spa.py
├── frontend/
│   ├── package.json              # pinned (exact) versions
│   ├── package-lock.json
│   ├── index.html
│   ├── vite.config.ts            # dev proxy /api -> backend; vitest config
│   ├── tsconfig*.json            # strict
│   ├── eslint.config.js
│   ├── .prettierrc.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx               # placeholder screen showing backend status
│       ├── App.test.tsx
│       ├── api.ts                # fetch wrapper (same-origin only)
│       ├── i18n/                 # i18next setup, en.json, fr.json
│       ├── styles.css            # system font stack, no external assets
│       └── test/setup.ts
├── deploy/README.md              # placeholder: Docker Compose arrives in Phase 6
└── docs/
    ├── PLAN.md, DECISIONS.md, BACKLOG.md, DEPENDENCIES.md
```

### Data model changes
None. The database arrives in Phase 1.

### Tests
- Backend: health endpoint returns ok plus version; settings load from env with the `MARGIN_` prefix; security headers present on API and static responses; SPA fallback serves `index.html` for client routes, returns 404 JSON for unknown `/api/*`, refuses path traversal; when no frontend build exists, `/` explains how to build it.
- Frontend: App renders the translated title, shows backend status from a mocked fetch, and switches to French.

### Done when
`make check` (or `python scripts/check.py`) passes and `python scripts/run.py` starts the app serving the built frontend.

---

## Phase 1: Accounts, classes, exams, mark schemes

### Goal
A teacher can sign in, switch language, see their exams, and create a complete exam (questions and mark scheme points) in English or French. Admins manage users, classes and students. Tests prove auth, permission boundaries and mark scheme validation.

### New backend dependencies (licences checked before adding)
- `sqlalchemy` 2.x (MIT), `alembic` (MIT): ORM and migrations.
- `argon2-cffi` (MIT): password hashing.

### New frontend dependencies
- `react-router` (MIT): client routing.
- No component library. Plain CSS with design tokens (decision D-011).

### Proposed file tree additions

```
backend/
├── alembic.ini
├── migrations/
│   ├── env.py
│   └── versions/0001_initial.py
├── app/
│   ├── cli.py                    # init-school, create-user (admin bootstrap), reset-password
│   ├── db/
│   │   ├── base.py               # DeclarativeBase, naming convention, timestamp mixin
│   │   ├── session.py            # engine factory, SQLite WAL + foreign_keys pragmas
│   │   └── models/               # one module per aggregate (see data model)
│   ├── auth/
│   │   ├── passwords.py          # argon2 hash/verify/needs_rehash
│   │   ├── sessions.py           # create/lookup/revoke DB-backed sessions
│   │   ├── csrf.py               # token check for unsafe methods
│   │   ├── throttle.py           # failed-login throttling per username
│   │   └── deps.py               # current_user, require_admin, require_teacher
│   ├── services/                 # business logic, no FastAPI imports
│   │   ├── users.py
│   │   ├── classes.py
│   │   ├── students.py
│   │   ├── exams.py              # create/update, status transitions
│   │   ├── mark_scheme.py        # validation rules
│   │   ├── mark_scheme_import.py # CSV parsing to a validated structure
│   │   └── audit.py              # append-only audit writer (used from Phase 1 for admin actions)
│   ├── subjects/
│   │   ├── registry.py           # loads subject configs, validated with Pydantic
│   │   └── configs/              # chemistry.toml, mathematics.toml, economics.toml
│   ├── schemas/                  # Pydantic request/response models
│   └── api/
│       ├── auth.py               # POST /login, POST /logout, GET /me, PUT /me/language
│       ├── classes.py
│       ├── students.py
│       ├── exams.py              # incl. POST /exams/{id}/import (CSV)
│       ├── subjects.py
│       └── users.py              # admin only
└── tests/
    ├── factories.py
    ├── test_passwords.py
    ├── test_auth_api.py          # login, logout, wrong password, throttle, session expiry
    ├── test_csrf.py              # unsafe request without/with wrong token is rejected
    ├── test_permissions.py       # teacher A cannot read/edit teacher B's class, exam, students
    ├── test_mark_scheme_validation.py
    ├── test_mark_scheme_import.py
    ├── test_exam_status.py
    ├── test_migrations.py        # upgrade head on empty DB matches models (autogenerate diff empty)
    └── test_subjects.py

frontend/src/
├── routes/                       # SignIn, Home, ExamSetup, admin/{Users,Classes,Students}
├── components/                   # Layout, LanguageSwitch, FormField, Table, StatusBadge, ErrorMessage
├── api/                          # typed client, CSRF header, error mapping to i18n keys
├── auth/                         # AuthContext, RequireAuth, RequireRole
└── i18n/locales/{en,fr}.json
```

### Data model (Phase 1 tables)

All tables: integer primary key `id`, `created_at`, `updated_at` (UTC). Foreign keys enforced (`PRAGMA foreign_keys=ON`). Only portable SQLAlchemy types, so PostgreSQL can be swapped in.

| Table | Columns | Notes |
|---|---|---|
| `school` | name, country, curriculum (e.g. `cm_gce_ol`) | One row per installation, created by `cli init-school`. |
| `user` | school_id, username (unique, case-insensitive), display_name, password_hash, role (`admin`/`teacher`), preferred_language (`en`/`fr`), is_active, last_login_at | Email optional field `email`; username is the login key because many school staff share or lack email. |
| `user_session` | user_id, token_hash (SHA-256, unique), csrf_token, created_at, last_seen_at, expires_at, revoked_at, user_agent | Raw token only in the cookie. Idle timeout and absolute lifetime from config. |
| `login_attempt` | username, succeeded, attempted_at, client_ip | For throttling and the audit trail. |
| `school_class` | school_id, name, academic_year, teacher_id (user) | Named `school_class` because `class` is a reserved word in Python. Unique (school, name, academic_year). |
| `student` | school_id, class_id, code (unique per school), display_name (nullable, local only), training_consent (bool), consent_recorded_at, consent_recorded_by_id | `code` is generated (e.g. `S-7K3QX`, unambiguous alphabet). Display names never leave the DB; enforced in Phase 3 by the model layer taking only codes. |
| `exam` | class_id, subject_code, title, exam_date, status (`draft`/`ready`/`marking`/`reviewing`/`completed`), created_by_id | `subject_code` references a subject config file, not a table (D-017). |
| `question` | exam_id, label (e.g. `1(a)`), prompt_text, max_half_marks, position | Unique (exam, position) and (exam, label). Marks stored in half-mark units (D-018). |
| `mark_scheme_point` | question_id, description, half_marks, alternatives (JSON list of strings), position | Half-mark units (D-018). |
| `audit_event` | actor_id (nullable for system), entity_type, entity_id, action, old_value (JSON), new_value (JSON), reason, created_at | Append-only. No update or delete path in code; a test asserts the service exposes none. Phase 1 writes events for user, class, student and consent changes and exam edits. |

Later phases add, each by migration: `upload`, `script`, `page`, `transcription`, `mark_decision`, `job`, `model_version` (as in brief section 6).

### Business rules (tested)

Mark scheme validation (D-014):
- Every question has `max_marks` ≥ 1 and at least one point.
- Every point has `marks` ≥ 1. Whole marks only in v1 API/UI; stored as half-mark units so half marks need no migration (D-018).
- Sum of a question's point marks must be ≥ `max_marks` (otherwise full marks are unreachable). A sum greater than max is allowed ("any 3 of 5 points"); awarded marks are capped at `max_marks`. The UI shows this as an informational note.
- Labels unique within an exam.
- Exam total = sum of question `max_marks`.
- An exam can move `draft` → `ready` only when validation passes. Structural edits (questions, points, marks) are allowed only in `draft`; moving `ready` back to `draft` is allowed until marking starts.

Permissions:
- Admin: all users, classes, students, exams in the school.
- Teacher: only classes where `teacher_id` = self, and exams/students in those classes. Access to anything else returns 404 (not 403) so IDs cannot be probed.
- Enforced in the service layer queries (scoped by user), not only in route handlers.

Auth (D-015, D-016):
- Argon2id via `argon2-cffi` defaults; rehash on login if parameters change.
- DB-backed sessions; cookie `margin_session`: httpOnly, SameSite=Lax, Secure when `MARGIN_COOKIE_SECURE=true`.
- CSRF: per-session token returned by `GET /api/auth/me`; required in `X-CSRF-Token` on POST/PUT/PATCH/DELETE. Login is protected by an Origin/Referer same-origin check.
- Throttle: after 5 failed attempts for a username within 15 minutes, further attempts are refused for 15 minutes (settings).
- Generic "username or password is incorrect" message.

CSV import (exam setup):
- Columns: `question_label, question_prompt, question_max_marks, point_description, point_marks, point_alternatives` (alternatives separated by `|`). One row per point; question columns repeated.
- Sent as raw `text/csv` body read in the browser (D-020).
- Parsed into the same Pydantic structure as the editor, validated with the same rules, previewed in the UI before saving. Errors reported per row as translated messages.
- Treated as untrusted: size limit, UTF-8 (with BOM tolerated), row limit.

i18n:
- Frontend: all strings via i18next keys; `fr.json` entries marked draft in `docs/TRANSLATIONS.md` until reviewed by a native speaker.
- Backend: API errors return a stable `code` (e.g. `auth.invalid_credentials`) plus English `detail`; the frontend translates by code. No user-facing prose generated in the backend for Phase 1.
- Language preference stored on the user; switch on sign-in screen (stored locally until sign-in) and in the header.

### Screens
1. Sign in with language switch.
2. Home: teacher's exams, status, and placeholder counts (scripts arrive in Phase 2, counts show 0).
3. Exam setup: create exam (class, subject, title, date), add/reorder/edit questions and points, live validation, total marks, CSV import with preview, "Mark as ready".
9 (partial). Admin: users (create, deactivate, reset password, role), classes (create, assign teacher), students (add one, bulk add by count or names list, generated codes, consent toggle with recorded by/at).

### Done when
- Tests cover: password hashing, login/logout, session expiry, throttling, CSRF rejection, teacher-cannot-see-other-teacher (class, exam, student, by list and by ID), admin access, mark scheme validation rules, CSV import, exam status transitions, migrations match models.
- Manually verified (and reported): a teacher signs in and creates a complete exam in English and in French.
- `make check` passes; committed.

### Risks and open points for Phase 1
- **Secure cookies on a school LAN.** `Secure` cookies are not sent over plain HTTP, and most school servers will be reached by IP over HTTP. Proposed: `MARGIN_COOKIE_SECURE` defaults to true in production; Phase 6 ships HTTPS with a locally generated certificate. Until then development runs with it false. Recorded as D-016; owner may want to weigh in.
- French translations are draft until reviewed.

---

## Phase 2: Cover sheets, upload, split

Status: built 2026-10-14. Refinements while building: D-027 to D-035.

### Goal
A teacher prints one cover sheet per student for a ready exam, scans the class stack into one or more PDFs, uploads them, and the system stores the original PDFs unchanged, renders every page to an image, reads the QR codes, and splits pages into one script per student. Anything it cannot place with certainty goes to an unassigned tray with a clear reason, where the teacher assigns or discards it by hand.

### Dependencies (approved 2026-10-14)
pypdfium2 5.14.0, reportlab 5.0.1, segno 1.6.6, zxing-cpp 3.1.1, pillow 12.3.0 (+ charset-normalizer 3.5.2). `python-multipart` was approved but is **not installed**: uploads are streamed as a raw `application/pdf` body (D-027). No new frontend packages.

### Owner requirements for this phase
1. **Render in a separate process with a timeout** (D-028). PDF rendering and QR reading run in a child process (`python -m app.pdf.render_worker`). A crash, hang or memory blow-up in PDFium kills only that child; the web server marks the upload `failed` with a reason. Tests: malformed PDF, worker that hangs (timeout), worker that crashes.
2. **QR codes carry a random token plus a checksum, never a database id** (D-029). On upload, a page whose QR is from a different exam, unknown, or damaged goes to the unassigned tray with a reason. Never assign by guess. Tests: sheet from another exam, duplicated sheet (same upload and earlier upload), damaged QR, unknown token, bad checksum.
3. **Original PDF stored unchanged with a checksum** (D-030), next to the page images, as the record of what was scanned. SHA-256 recorded; test asserts stored bytes are identical.
4. **`ready -> draft` refused once any upload exists for the exam** (`409 exam.has_scripts`). Test included.
5. **THIRD_PARTY_NOTICES** generated from installed licence files of everything shipped (Python runtime packages, including the native libraries bundled in pypdfium2 and Pillow, and frontend runtime packages). `scripts/third_party_notices.py --check` runs in the check suite so the file cannot go stale.
6. Report the **disk space per 50-script class** at the chosen image settings.

### Key design

**QR payload** (`app/sheets/tokens.py`): `MA1-<16 base32 chars>-<4 base32 chars>`.
- 80 random bits from `secrets`; the checksum is the first 20 bits of SHA-256 over `MA1-<token>`, base32. Uppercase base32 and `-` fit the compact QR alphanumeric mode (version 3 at level H, 30 % error correction).
- `MA1` is a format version so the layout can change later without ambiguity.
- The checksum catches misreads and hand-typed tokens; it is not a secret (the token's randomness is what makes sheets unguessable).

**Cover sheet** (`app/sheets/cover_pdf.py`, reportlab, A4): thick black frame 10 mm inside the page edge (detectable even when the QR is unreadable), the same QR printed twice (top right, bottom left, 40 mm, level H), student code in large type, exam title, subject (English and French names), class, date, and a short bilingual instruction ("Put this sheet on top of your answer pages. Do not write on it." / French). **No real names on paper.** One page per student, students sorted by code. Fonts: built-in Helvetica (covers French accents; no font files to ship).

**Tokens are stable per (exam, student)**: preparing cover sheets again reprints the same tokens, so a reprinted sheet is recognised and duplicates are detectable. Students added later get new tokens on the next prepare.

**Image settings** (configurable): 200 dpi, colour JPEG quality 90 for page images; 400 px-wide JPEG thumbnails for the tray and lists. Pages larger than A3 are scaled down so that no render exceeds 40 megapixels (protects memory on modest machines).

**Page classification** (inside the worker, per page):
1. Decode QR codes (`read_barcodes(..., return_errors=True)`, any rotation).
2. One or more *valid* decodes with the same text → cover candidate; the page is rotated upright using the barcode orientation. Different valid texts on one page → `qr_conflict`.
3. Only decodes with errors (checksum/format) → cover with `qr_damaged`.
4. No QR at all but the cover frame is present (dark band on all four edges, rotation-independent) → cover with `qr_unreadable`.
5. Otherwise → answer page.

**Splitting** (`app/services/splitting.py`, pure function, tested in isolation): walk pages in scan order.
- Cover with a valid token for this exam and a student with no pages yet → starts that student's script; the cover page is stored as page 1 of the script (`is_cover`).
- Following answer pages → appended to that script, in order.
- Every other cover outcome starts an **unassigned run**: that cover and every following answer page up to the next good cover go to the tray with the run's reason. Reasons: `qr_damaged`, `qr_unreadable`, `qr_conflict`, `qr_not_ours` (a QR that is not our format), `qr_bad_checksum`, `unknown_sheet` (well-formed token not in the database), `other_exam` (token belongs to another exam; the tray names that exam if the teacher can see it), `duplicate_in_upload` (same sheet twice in this upload; the second copy is not merged), `already_uploaded` (the student already has pages from an earlier upload).
- Answer pages before the first cover → `before_first_cover`.
- Pages that follow a problem cover carry `follows_unassigned_cover` plus the id of that cover page, so the tray shows them grouped.

**Processing pipeline** (`app/services/uploads.py`):
1. `POST /api/exams/{id}/uploads` (body `application/pdf`, header `X-Filename`): exam must be visible and not `draft`. Streamed to `data/uploads/<id>/original.pdf` with a size limit (`MARGIN_MAX_UPLOAD_MB`, default 500) and SHA-256 computed while streaming; must start with `%PDF-`. The same file (same SHA-256) uploaded twice for one exam → `409 upload.duplicate_file`. Status `pending`.
2. After the response is sent, a background task hands the upload to a single-thread processor (one upload at a time keeps a modest machine responsive).
3. The processor runs the worker with a timeout (`MARGIN_RENDER_TIMEOUT_SECONDS`, default 900; page limit `MARGIN_MAX_PDF_PAGES`, default 1000). The worker writes images to a fresh `pages/` folder and a `manifest.json` last.
4. The splitter turns the manifest into page rows, scripts and tray entries **in one database transaction**, so processing is idempotent: re-running an upload replaces that upload's pages and nothing else.
5. On server start, uploads left `pending` or `processing` (power cut) are processed again. Phase 3 moves this onto the job table.

**Files** are stored under `MARGIN_DATA_DIR` only and served through authenticated endpoints that resolve paths from the database, never from request input.

### Data model changes (migration 0002)
| Table | Columns | Notes |
|---|---|---|
| `cover_sheet` | exam_id, student_id, token (unique), created_at | unique (exam_id, student_id). |
| `upload` | exam_id, uploaded_by_id, original_filename, stored_path, sha256, size_bytes, page_count, status (`pending`/`processing`/`processed`/`failed`), error_code, created_at, processed_at | unique (exam_id, sha256). |
| `script` | exam_id, student_id, status (`waiting`/`transcribed`/`ai_marked`/`in_review`/`confirmed`), confirmed_by_id, confirmed_at, timestamps | unique (exam_id, student_id). |
| `page` | upload_id, source_page_index, image_path, thumb_path, width, height, rotation_applied, is_cover, script_id (nullable), position (nullable), state (`assigned`/`unassigned`/`discarded`), unassigned_reason, related_page_id, detected_exam_id | unique (upload_id, source_page_index). |

### API
- `GET/POST /api/exams/{id}/cover-sheets`: list students with sheet status / prepare missing sheets. `GET /api/exams/{id}/cover-sheets.pdf`: the printable PDF.
- `POST/GET /api/exams/{id}/uploads`, `POST /api/uploads/{id}/retry` (failed only), `GET /api/uploads/{id}/original`.
- `GET /api/exams/{id}/scripts` (with page lists), `GET /api/exams/{id}/unassigned-pages`.
- `POST /api/exams/{id}/pages/assign` `{page_ids, student_id}` (appends in scan order, creates the script if needed), `/pages/unassign` `{page_ids}`, `/pages/discard` `{page_ids}`. All audited.
- `GET /api/pages/{id}/image?size=thumb|full`.
- Exam summaries gain real script counts.

### Screens
- **Cover sheets** (screen 4): students and their codes (names shown on screen for the teacher only), "Prepare and download cover sheets". Explains that the exam must be ready.
- **Scans** (screen 5): upload one or more PDFs; uploads list with live status (polls while processing); scripts list (code, name, pages, thumbnails); students with no script yet; unassigned tray grouped by reason with thumbnails, multi-select, "Assign to student" and "Discard"; on a script, "Return page to tray" to undo.

### Tests
- Unit: token format and checksum (single-character changes detected), parse rejects foreign payloads; cover-frame detector on cover vs ruled answer page; splitter cases for every reason.
- Cover sheets: one page per student, tokens stable on re-prepare, new student gets a sheet, rendered pages decode back to their tokens, no real names anywhere in the PDF text, draft exam refused.
- Worker isolation: malformed PDF → `failed` `upload.pdf_unreadable` and the server still answers; hanging worker → killed after the timeout, `upload.render_timeout`; crashing worker → `upload.render_crashed`; page limit.
- Upload API: original stored byte-identical with matching SHA-256; duplicate file 409; non-PDF 422; too large 413; other teacher 404; draft exam 409; images require sign-in and scope.
- **Acceptance (brief section 9)**: generate cover sheets, build a synthetic scanned PDF (covers + handwritten-style answer pages, a cover rotated 180°, a cover rotated 90°, an answer page with PDF `/Rotate`, one cover with damaged QR, one with the QR erased, a sheet from another exam, a duplicated sheet), upload, assert every page's destination and reason.
- Duplicates across uploads; tray assign/unassign/discard and audit; resume of an interrupted upload with no duplicated pages; `ready -> draft` refused after upload.
- Frontend: cover sheets screen, upload sends `application/pdf` with filename, tray shows translated reasons, assign sends the selected pages.
- Translations: every new error code and every tray reason in English and French (extends the existing test).

### Done when
The acceptance test passes; `python scripts/check.py` passes and its output has been read; the flow is run end to end against a live server with a real generated scan; disk usage per 50-script class is measured and reported.

### Risks
- A cover sheet with both QR codes destroyed **and** its frame unreadable would look like an answer page and be appended to the previous student. Two QR codes plus the frame make this unlikely; the teacher still sees every script's pages in Phase 4 review. Recorded in D-029.
- Rendering speed on real scanned PDFs (large embedded images) is unmeasured until real scans exist; synthetic scans are measured and reported.
- Upside-down answer pages without PDF rotation metadata stay as scanned (no OCR-based orientation in this phase); page rotation in the UI is in the backlog.

## Phase 3: AI pipeline

Status: built 2026-10-14 (Mock path proven; real model pending). Refinements: D-036 to D-044.

### Goal
A background worker process runs all long work from a database job table: upload processing, then per script transcription (Reader) and marking (Marker). Jobs survive restarts and power cuts and never duplicate results. Models sit behind two interfaces with Ollama and Mock implementations; their output is validated against strict schemas, retried a bounded number of times, and otherwise the script is flagged for manual marking. Nothing is ever invented or silently dropped. A CLI evaluates any Reader against typed ground truth.

### Dependencies
`httpx` moves from dev to runtime (approved 2026-10-14) for the Ollama client. No other new packages.

### Owner requirements for this phase
1. **Evaluation CLI** (`python -m app.cli evaluate`): given a folder of page images with typed ground-truth transcriptions, run the configured Reader and report character error rate (CER), word error rate (WER) and key-token recall (numbers, formulae, operators), per subject, plus model name, model version, prompt version and seconds per page. JSON report for comparing model changes.
2. **Report the real model's time per page and the hardware** (CPU, RAM, GPU) once `qwen3-vl:8b` is pulled.
3. Brief: done when, with Mock models, a full exam goes from upload to `ai_marked`; killing the worker mid-run and restarting completes the run with no duplicated results; with Ollama, one real script is transcribed and marked (reported honestly).

### Design

**Job table and worker** (`app/services/jobs.py`, `app/worker/`):
- `job`: type (`process_upload`, `transcribe_script`, `mark_script`), payload (ids only, never student content), status (`queued`/`running`/`succeeded`/`failed`), attempts, max_attempts, run_after, idempotency_key (unique), locked_by, heartbeat_at, last_error (code and exception type only), timestamps.
- Enqueue is idempotent: the key (`upload:<id>`, `transcribe:<script id>`, `mark:<script id>`) is unique; enqueuing an existing key returns the existing job (or re-queues it when explicitly retried).
- Claiming is one atomic `UPDATE ... WHERE status='queued'` so two workers can never take the same job.
- The worker (`python -m app.worker`) polls, heartbeats every 15 s, and on start-up re-queues jobs left `running` by a dead worker (stale heartbeat). `scripts/run.py` starts the web app and the worker together; Docker gets a separate `worker` service in Phase 6.
- Model server unavailable → the job is retried with exponential backoff (capped) up to `MARGIN_JOB_MAX_ATTEMPTS`, then marked failed with a clear reason; the teacher can retry.
- Upload processing moves from the Phase 2 in-process thread to a `process_upload` job (D-032 superseded).
- The worker writes a heartbeat row so the UI can say "worker not running" instead of spinning.

**Idempotent handlers** (each step commits its own results; re-running skips what exists):
- `transcribe_script`: one Reader call per answer page (cover sheets are not transcribed). Each page's transcription is committed as soon as it is validated, so a restart resumes at the next page. Then the script becomes `transcribed` and a `mark_script` job is queued.
- `mark_script`: one Marker call per question, all decisions for the script written in one transaction. Then the script becomes `ai_marked`. When every script of the exam is done (marked or flagged), the exam moves to `reviewing`.
- Unique constraints back this up: one model transcription per (page, model, model version, prompt version); one model proposal per (script, mark scheme point, model, model version, prompt version).

**Model layer** (`app/ai/`):
- `Reader.transcribe(pages: list[PageImage], subject: SubjectConfig) -> Transcription` and `Marker.mark(transcription: Transcription, exam: ExamSpec) -> MarkingProposal`, as in the brief. Every result carries model name, model version (Ollama digest), prompt version and timestamp.
- What a model sees: page images and the subject's notation hints (Reader); the transcription text and the exam's questions and mark scheme (Marker). Never student names or codes.
- `OllamaReader` / `OllamaMarker`: Ollama `/api/chat`, temperature 0, JSON output constrained by a JSON schema (`format`), images sent as base64 JPEG resized to at most `MARGIN_READER_MAX_IMAGE_PX` on the long side.
- `MockReader` / `MockMarker`: deterministic. MockReader returns a ground-truth sidecar text file when one exists (demos and evaluation tests), otherwise fixed text. MockMarker awards a point when its key words appear in the transcription and quotes them as evidence.
- **Prompts** are files in `app/ai/prompts/` (`reader.md`, `marker.md`) with a declared version line; the stored prompt version is `<declared>#<first 8 hex of SHA-256 of the file>`, so any edit is distinguishable even if someone forgets to bump the version.
- **Validation** (Pydantic, strict): Reader → `{"text": str}`. Marker → exactly one entry per mark scheme point of the question, awarded marks a whole number from 0 to the point's marks, confidence 0 to 1, error category from the brief's list, and evidence that is an exact quote from the transcription (whitespace-normalised) whenever marks are awarded. Invalid output is re-requested up to `MARGIN_MODEL_OUTPUT_RETRIES` times; then the script is flagged for manual marking with a reason (`ai.reader_invalid_output` / `ai.marker_invalid_output`) and the job completes. Nothing partial is stored for a failed question.
- `model_version` table: registered on first use (name, role, digest, source, installed_at).

**Network guard**:
- A test runs the full pipeline with the Ollama implementations against a fake Ollama server on 127.0.0.1 and records every outbound socket connection made by application code; it fails if any goes anywhere but the configured model host. A second test proves the guard catches a connection to another host.
- A static test: only `app/ai/ollama_client.py` may import an HTTP client or `socket`.
- Start-up check: the model host must be loopback, a private (RFC 1918 / link-local) address, or a single-label or `.local`/`.lan` hostname (e.g. Docker's `ollama`). Otherwise the app and worker refuse to start, unless `MARGIN_ALLOW_PUBLIC_MODEL_HOST=true` is set deliberately. Keeps student work from being sent to a cloud endpoint by a configuration mistake.

**API and screens (minimal; the full queue and review screens are Phase 4)**:
- `POST /api/exams/{id}/ai-marking`: queue transcription for every `waiting` script and re-queue failed AI jobs; exam moves to `marking`.
- `GET /api/exams/{id}/ai-status`: counts by script status, flagged scripts with reasons, failed jobs, worker online, model server reachable.
- `GET /api/scripts/{id}/ai-results`: transcriptions and proposed marks (read-only, for checking).
- Scans screen: "Start AI marking" button, progress counts, worker and model status, flagged scripts.

**Evaluation** (`app/ai/evaluation.py`, pure, tested):
- Folder layout: `<root>/<subject_code>/<name>.jpg|png` with `<name>.txt` holding the exact typed transcription in the agreed notation.
- CER and WER: Levenshtein distance over characters / whitespace-separated words, summed over pages, divided by reference length (micro-average). Line breaks normalised; case and spelling preserved (errors must be kept, not corrected).
- Key-token recall: tokens in the reference that are numbers (`12`, `3.5`, `1/2`), formulae (`H_2O`, `x^2`, `Na^+`, `CO_2`) or operators (`=`, `+`, `-`, `×`, `÷`, `->`, `<=>`, `^`, `/`, `√`, `<`, `>`); recall = matched / total (multiset).
- `python -m app.cli evaluate --data <folder> [--subject <code>] [--backend mock|ollama] [--report report.json]`.

### Data model changes (migration 0003)
`job`, `worker_heartbeat`, `transcription`, `mark_decision`, `model_version`; `script` gains `manual_reason` (nullable code) and `ai_started_at`.

### Tests
- Jobs: idempotent enqueue, atomic claim, retry with backoff, failure after max attempts, stale job re-queue.
- Pipeline with Mock models: upload → processed → transcribed → `ai_marked`, exam `reviewing`; every output stores model, version, prompt version, timestamp.
- **Kill and restart**: the worker runs as a real subprocess with a slowed Mock model, is killed mid-run, restarted, and the run completes with no duplicate transcriptions or decisions.
- Validation: malformed JSON, missing points, marks out of range, invented evidence → retried, then flagged for manual marking; nothing stored for the failed question.
- Ollama client against a fake Ollama server (request shape: schema, temperature, base64 images; digest lookup; connection refused → retryable error).
- Network guard (dynamic and static) and model-host start-up check.
- Model server down: web app still answers; AI status reports it; jobs back off.
- Evaluation metrics on known strings; CLI end to end with MockReader sidecars.
- Frontend: start button, progress, worker/model status, flagged scripts.

### Done when
Mock pipeline and kill/restart tests pass; full check suite passes and is read; with `qwen3-vl:8b` pulled, one real script transcribed and marked, evaluation run on a sample set, time per page and hardware reported (or, if the model is not available yet, reported honestly and kept covered by the Mock path).

### Risks
- **This machine's GPU (NVIDIA T550, 4 GB) cannot hold an 8B vision model**; Ollama will split it between GPU and CPU, so pages may take tens of seconds or more. Measured and reported; overnight runs are the intended use.
- No real handwriting ground truth exists yet; the sample evaluation set will be synthetic and clearly labelled so. Real teacher-typed transcriptions are needed for meaningful numbers.
- Qwen3-VL's adherence to the JSON schema at temperature 0 is unknown until measured; invalid-output rates are reported by the evaluation and the job logs.

---

## Phase 4: Teacher review

Status: built 2026-10-15, waiting for owner approval (deviations in D-049 to D-051). Approved 2026-10-14 with changes (orientation from the Reader, review time, legacy covers; see "Owner changes" below). `@playwright/test` 1.64.1 approved (dev, installed Edge). Building starts after the evaluation queues finish and the combined report is sent. Phase 4 does not depend on which model wins the evaluation: models are configuration.

### Goal
A teacher works through a class's scripts in the order that most needs attention, sees each page beside its transcription and the AI's proposed marks with evidence, corrects anything (marks, categories, transcription, page orientation), adds short comments, and confirms the script. Every change is audit-logged. Nothing is final, and nothing can be exported, until a teacher confirms it. The whole review can be done from the keyboard.

### Dependency (for approval)

| Package | Version | Licence | Purpose | Transitive packages |
|---|---|---|---|---|
| `@playwright/test` (dev only) | 1.64.1 | Apache-2.0 | Real-browser tests of the review screen | `playwright` 1.64.1 (Apache-2.0), `playwright-core` 1.64.1 (Apache-2.0) |

- No install scripts: installing it downloads nothing else.
- **No browser download:** the tests drive the Microsoft Edge already installed on this machine (`channel: "msedge"`, Edge 155 found). Downloading Playwright's own Chromium (`npx playwright install`) is not planned and would need separate approval.
- Phase 6 note: a Linux/Docker test environment has no Edge; browser tests there would need a browser install, to be approved then. On school machines the browser tests never run.
- No new backend dependencies. Zoom, pan and keyboard handling are plain browser code.

### Owner changes on approval (2026-10-14); these override the design below where they differ
1. **No separate orientation model call.** The Reader returns an orientation judgement with a confidence in the same call as the transcription. Pages it flags as not upright with confidence of at least 0.8 are rotated and read again (once). Teacher undo and the off switch stay.
2. **Review time per script**, from opening to confirming, stored locally only and never sent anywhere; the class average is shown on the results screen. It is the impact measure for MIT Solve.
3. **Legacy covers:** pages uploaded before Phase 4 whose cover images were already turned upright in Phase 2 are recorded so they are never rotated twice. Tested.
4. **AI deductions easy to spot (2026-10-15):** in the review screen, every point where the AI proposed fewer marks than the point's maximum is clearly marked (a visible "−N" badge and highlight), and the question shows how many marks the AI deducted, so the teacher checks those first. Keyboard: `d` jumps to the next point with a deduction.

### Owner requirements for this phase
1. Screens 6 (marking queue) and 7 (script review), audit log, confirm flow, uncertainty-first ordering, keyboard shortcuts (brief).
2. Tests prove every edit is audited and unconfirmed scripts cannot be exported; a teacher can review and confirm a script using only the keyboard (brief).
3. Page orientation in three layers (owner, 2026-10-14), each tested:
   a. a rotate control per page, stored and audit-logged, original image unchanged;
   b. stack rotation: when a cover sheet's QR shows the stack was scanned rotated, the following answer pages are corrected the same way;
   c. an automatic orientation check per answer page before transcription, marked "auto-rotated" so the teacher can undo it.
4. Real-browser tests with Playwright (owner).

### Design

**Page orientation (one model for all three layers).** Page image files are never modified after rendering; they stay exactly as rendered from the scanned PDF. Orientation is metadata on the page:
- `rotation_stack` (layer b): set during splitting from the cover sheet's QR orientation, for the cover and every answer page after it up to the next cover (including tray pages that follow a problem cover).
- `rotation_auto` (layer c) with `auto_rotation_confidence`: set by the orientation check before transcription.
- `rotation_teacher` (layer a): set by the rotate control; when present it is the final word.
- **Effective rotation** = `rotation_teacher` if set, otherwise `(rotation_stack + rotation_auto) mod 360`. The browser displays the image rotated by it (CSS transform); the worker rotates in memory before sending a page to the model.
- Change from Phase 2: cover sheets are currently stored already turned upright (`rotation_applied` baked into the file). From Phase 4 nothing is baked; the migration turns existing `rotation_applied` into `rotation_stack` and re-renders nothing (on existing data the stored cover images stay as they are and keep their recorded value, so the effective rotation for those is 0; new uploads follow the new rule).
- Rotate control: rotate left / rotate right / reset (`POST /api/pages/{id}/rotation`), audited with old and new effective rotation. Undo for an auto-rotation sets `rotation_auto` to 0 and is audited. If the script has not been transcribed yet the corrected orientation is used; if it has, the page is marked "rotated after transcription" and the teacher can request a fresh transcription of that page (queued job), never automatic.

**Automatic orientation check (layer c), inside the Reader (owner change 1).** No separate model call:
- The Reader's output schema gains `orientation` (`upright`, `upside_down`, `rotated_clockwise`, `rotated_counterclockwise`) and `orientation_confidence` (0 to 1), returned with the transcription. Prompt `reader.md` becomes `reader-v2` (the version and hash change, so evaluation results stay comparable by version).
- If the page is judged not upright with confidence at least `MARGIN_ORIENTATION_MIN_CONFIDENCE` (default 0.8), the worker rotates the page in memory by the matching angle and reads it **once more**; the second transcription is the one kept, and the page records `rotation_auto`, the confidence, model and prompt version. The second read's own orientation judgement is recorded but never triggers a further rotation (no loops). Below the threshold, or with an invalid judgement, nothing is rotated and the first transcription is kept.
- Pages with a teacher rotation skip the judgement. Cover sheets are not transcribed, so never auto-rotated.
- `MARGIN_ORIENTATION_CHECK=reader|off` (default `reader`). With `off`, the orientation fields are ignored.
- Cost: no extra call for upright pages; one extra read only for pages flagged as rotated. The evaluation command gains `--orientation`: each synthetic page also fed rotated 90/180/270 (plus the owner's upside-down test page) to measure how often the judgement is right, wrongly confident, or missed, and the time of the re-read.

**Legacy covers (owner change 3).** In Phase 2, cover images were stored already turned upright and the angle recorded in `rotation_applied`. Migration 0004 copies that angle into a new `rotation_baked` column, sets `rotation_stack` to 0 for those pages, and the effective-rotation rule subtracts nothing further for them: `rotation_baked` means "already applied to the image file, never apply again". Answer pages from those uploads were never rotated and get no retroactive stack rotation. If such an upload is processed again (retry), it is re-rendered under the new rule (nothing baked, `rotation_baked` reset to 0). Test: a pre-Phase-4 page row with `rotation_applied = 180` upgrades to `rotation_baked = 180`, effective rotation 0, displayed and sent to the model without further rotation.

**Review time (owner change 2).**
- A `review_session` row is opened when a teacher opens a script for review and closed when they confirm it: `script_id`, `user_id`, `opened_at`, `confirmed_at`. Wall time = confirmed minus opened, exactly as specified. Reopening and confirming again starts a new session; a script's review time is the sum of its sessions.
- **Active time** is recorded next to it, because a script left open overnight would otherwise count as hours of review: while the review screen is visible and the teacher has used it in the last 5 minutes, the page sends a heartbeat every 30 seconds and the server adds the elapsed time (capped at 60 s per heartbeat) to `active_seconds`. Both figures are stored; the report shows both and labels them clearly.
- Stored in the school database only, like everything else; never sent anywhere; no new network call (heartbeats go to the local app).
- The class average (wall and active, over confirmed scripts) is shown on the marking queue screen in Phase 4 and on the results screen when Phase 5 builds it.

**Marking queue (screen 6).** Per exam: every script with student code and name, status, page count flag, manual-marking flag, lowest proposed-mark confidence, number of `transcription_uncertain` points, and AI progress. Sorted uncertainty first: needs manual marking → has `transcription_uncertain` points → lowest confidence first → page-count flag → the rest; confirmed scripts last. "Start AI marking" and the worker/model status move here from the Scans screen. Live progress (polling).

**Script review (screen 7).**
- Left: page images with zoom (buttons, mouse wheel, keyboard) and pan (drag), a page strip, rotate controls and an "auto-rotated" badge with undo.
- Right: per page, the transcription (editable; saving creates a new teacher version; earlier versions stay and are viewable). Per question: each mark scheme point with proposed marks, evidence (highlighted in the transcription), confidence, error category; the teacher's marks and category; a short comment per question (at most 300 characters); the question total (capped at the maximum).
- Accept a point (copies the proposal into the final fields), accept all, edit marks (0 to the point's marks, whole marks), change category, comment.
- Scripts flagged for manual marking show the mark scheme with empty final fields; the teacher enters every mark.
- Confirm: only when every point of every question has a final mark and category. Confirming sets `confirmed_by` / `confirmed_at` and status `confirmed`. "Reopen" returns a confirmed script to review (audited). Opening a script for editing moves it from `ai_marked` to `in_review`.
- If the teacher edits a transcription after AI marking, the screen notes that the proposals were made on the earlier text; re-running AI marking for one script is in the backlog, not in this phase.
- Previous/next script in queue order without leaving the screen.

**Keyboard shortcuts** (shown with `?`; ignored while typing in a text field):
- `j` / `k` next / previous mark scheme point; `0`–`9` set marks for the focused point; `a` accept the focused point; `Shift+A` accept all; `c` cycle category; `m` focus the comment of the current question.
- `e` edit the transcription of the visible page; `Esc` leave the text field.
- `[` / `]` previous / next page; `+` / `-` / `0` zoom in / out / fit; `r` / `Shift+R` rotate right / left.
- `n` / `p` next / previous script; `Ctrl+Enter` confirm script.

**Audit.** Every change writes one append-only audit event with actor, time, old value and new value (reason optional): final marks, category, accept and accept-all (one event per point), comments, transcription edits (old and new text; the audit log is in the database, never in log files), rotations and auto-rotation undo, confirm, reopen. Model actions (auto-rotation, transcriptions, proposals) are recorded with the system actor.

**Export guard.** `services/exports.py` gains `exportable_scripts(exam)` and `require_confirmed(script)`; Phase 5's CSV and marked-PDF exports must use them. Tested now.

### Data model changes (migration 0004)
- `page`: `rotation_stack`, `rotation_auto`, `auto_rotation_confidence`, `auto_rotation_model`, `auto_rotation_prompt_version`, `rotation_teacher` (nullable), `rotated_after_transcription` (bool), `rotation_baked` (angle already applied to the stored image by Phase 2; never applied again); `rotation_applied` migrated into `rotation_baked` and dropped.
- `review_session`: `script_id`, `user_id`, `opened_at`, `confirmed_at` (nullable), `active_seconds`, `last_heartbeat_at`.
- `mark_decision`: proposal fields nullable, for points the teacher marks without an AI proposal (manual scripts); a check constraint keeps final marks within 0 and the point's marks (enforced in the service, since the point's marks live in another table).
- `question_comment`: `script_id`, `question_id`, `text`, `updated_by_id`, `updated_at`; unique (script, question).
- `script`: `reviewed_at` (first teacher edit), keeps `confirmed_by_id` / `confirmed_at`.

### API
- `GET /api/exams/{id}/queue`: scripts in review order with flags and confidence summary, plus the class's average review time (wall and active).
- `POST /api/scripts/{id}/review-heartbeat`: adds active review time (local only).
- `GET /api/scripts/{id}/review`: pages (with effective rotation), latest and earlier transcriptions, questions with points, proposals, finals, comments, totals, navigation (previous/next script ids).
- `PUT /api/scripts/{id}/decisions/{point_id}` (marks, category), `POST /api/scripts/{id}/accept-all`, `PUT /api/scripts/{id}/questions/{question_id}/comment`, `POST /api/pages/{id}/transcription` (new teacher version), `POST /api/pages/{id}/rotation`, `POST /api/pages/{id}/undo-auto-rotation`, `POST /api/scripts/{id}/confirm`, `POST /api/scripts/{id}/reopen`.
- All scoped to the teacher's own classes (404 otherwise); edits on confirmed scripts refused (`script.confirmed`) until reopened.

### Tests
- Reader orientation (owner change 1): a page judged upside down at confidence 0.8 or more is rotated and read again once, the second transcription kept and `rotation_auto` recorded; confidence below 0.8 or an invalid judgement keeps the first read and rotates nothing; the second read never triggers another rotation; `off` ignores the judgement (Mock and fake Ollama).
- Legacy covers (owner change 3): migration test from a Phase 2 page with `rotation_applied = 180` to `rotation_baked = 180` and effective rotation 0; never rotated again.
- Review time (owner change 2): a session opens on first view and closes on confirm; reopen starts a new one; heartbeats add capped active time and ignore idle gaps; class averages computed over confirmed scripts; no network call other than to the local app.
- Orientation (a): rotate stores the value, audit event, image file bytes and SHA-256 unchanged, model receives the rotated page. (b): a stack scanned upside down (covers and answer pages) gets `rotation_stack` 180 throughout; a mixed upload keeps each stack's own rotation. (c): undo of an auto-rotation restores the page and is audited; teacher rotation overrides auto.
- Review: accept, accept all, edit marks and categories, comments, transcription versions kept, manual-marking scripts, confirm requires every point decided, reopen, question totals capped, confirmed scripts locked.
- **Every edit audited:** a test performs each review action and asserts exactly the expected audit event with old and new values.
- **Unconfirmed scripts cannot be exported:** `exportable_scripts` and `require_confirmed` tests.
- Queue ordering: scripts with each kind of uncertainty sort ahead as specified.
- Permissions: another teacher gets 404 on every review endpoint.
- Translations: every new string and code in English and French (existing tests extend automatically).
- Frontend unit tests (Vitest): keyboard handling (including "ignored while typing"), zoom and rotation state, review state updates.
- **Browser tests (Playwright, Edge):** `scripts/e2e_seed.py` creates a fresh database with a Mock-marked exam; Playwright starts the real app on a free port against it. Scenarios: (1) a teacher reviews and confirms a script **using only the keyboard**; (2) rotate a page and undo an auto-rotation, image reloads rotated; (3) mark a manual-marking script; (4) the review screen in French; (5) another teacher cannot open the script. Added to the check suite as `frontend: browser tests`.

### Done when
All of the above pass in `python scripts/check.py` (output read before committing); a teacher can review and confirm a script quickly using only the keyboard (browser test plus a manual run reported); the three orientation layers work on the owner's upside-down test page in a live run; the orientation check's accuracy and time per page on this machine are reported.

### Risks
- The orientation check adds one model call per page; on this machine that is tens of seconds per page. If the evaluation shows it is too slow or inaccurate with the chosen model, it can be switched off (`MARGIN_ORIENTATION_CHECK=off`) and teachers rely on layers a and b.
- Small models may be unreliable at orientation judgement; the confidence threshold and teacher undo limit the harm, and the accuracy is measured before relying on it.
- Browser tests depend on Edge being installed on the development machine.

---

## Phase 5: Results and exports

Status: built 2026-10-15, waiting for owner approval (D-054, D-055). Planned 2026-10-15; Phase 4 approved the same day. Order of work agreed for the demo on 26 October: Phase 5 now; per-question output schemas alongside it, with the evaluation re-run overnight; then Phase 6; whole-script marking only if time allows.

### Dependencies
**None new.** Marked PDFs use ReportLab, approved in Phase 2 for "cover sheets; later marked PDFs". Images use Pillow; CSV, JSON lines and zip files use the Python standard library; tests read the PDFs back with pypdfium2 (already installed).

### Goal
The teacher sees the class's results, downloads a CSV and marked PDFs (one per student and one combined file for printing). An admin exports the training dataset, consented students only. Nothing unconfirmed ever leaves the system.

### Design
**Results (screen 8).** Per exam:
- a table with one row per student and a column per question, plus the total and a percentage;
- per-question class averages;
- status counts, with the scripts not yet confirmed listed (they are shown but never exported);
- the class's average review time, wall and active, as on the queue (owner change 2).

The screen is reached from a new **Results** tab.
- **Marks:** a question's mark is the sum of its points' final marks, capped at the question maximum, as on the review screen. Totals add up the capped question marks.
- **Rounding:** whole marks today; half marks would show as .5 (D-018).

**CSV export.**
- **Encoding:** UTF-8 with a byte-order mark, so Excel opens accents correctly. Comma-separated.
- **Columns:** student code, student name (if recorded), one column per question label, total, maximum, percentage, confirmed at.
- **Rows:** confirmed scripts only, via `exportable_scripts`. A note in the screen says how many are not included.
- **Formulas:** cells that start with `=`, `+`, `-` or `@` are prefixed with `'`, so a student's name can never run as a spreadsheet formula.
- **Audit:** every export writes an audit event.

**Marked PDFs.**
- **Content:** built from the stored page images, turned upright by each page's effective rotation. The original scans are never changed.
  - **Cover sheet:** stamped with a results box (total, per-question marks, the teacher's comments).
  - **Each answer page:** a margin column showing the marks for the questions whose evidence is on that page. Positions on the page are not known (there are no question regions), so marks go in the margin, not next to the words.
- **Identity:** student code only on paper, never names (non-negotiable).
- **Files:** one PDF per student, and one combined PDF for the class in student-code order.
- **Generation:** the combined file is built by the worker, as a new `export_pdfs` job, so the web app stays responsive. A single student's PDF is built on request.
- **Storage and audit:** files are stored under `MARGIN_DATA_DIR/exports/` and downloaded only through authenticated endpoints. Every export is audited.

**Training-data export (brief section 8).**
- **Who and what:** admin only. Covers confirmed scripts of students with training consent only.
- **Contents:** a zip with `images/` (upright page images, file names from student code and page number), `dataset.jsonl` and `README.md`. Each line of `dataset.jsonl` holds:
  - subject, curriculum, exam, question text and mark scheme;
  - the page images;
  - the final transcription per page;
  - per point: the final marks and category next to the model's original proposal (marks, evidence, confidence, category);
  - the model and prompt versions.
- **Privacy:** pseudonymous codes only. No names anywhere, checked by a test that searches the whole zip for every student name.
- **Generation:** built by the worker as an `export_dataset` job. Audited with the number of students and scripts.
- **Admin screen:** a training-data section in the admin area (choose exams, see consent counts, export, download), and a read-only view of the model configuration and model server status (brief screen 9).

**Exports table.** `export` stores id, kind (`csv`, `student_pdf`, `class_pdf`, `dataset`), exam (null for datasets across exams), requested by, status, file path, size, created and finished times, error. Old files can be deleted by an admin. Retention rules for modes 2 and 3 are in the backlog (D-052).

**Exam completion.** When every script of an exam is confirmed, the exam moves to `completed`. Reopening a script moves it back to `reviewing`. Both are audited.

**Per-question output schemas (alongside, owner order).**
- **Schema:** each marking call's JSON schema lists exactly that question's points as required object properties keyed by point id, for both evidence designs. Prompts become `marker-v2` and `marker-lines-v2`.
- **Validation:** unchanged.
- **Evaluation:** re-run overnight on the synthetic set with both designs. The report gives the per-subject figures the owner asked for.
- **Default:** changes only with the owner's approval after the report.

### Decisions for the owner (defaults used unless told otherwise)
1. **Names in the CSV:** included when recorded. They are the school's own data, already shown on screen, and the CSV goes to the teacher. Never on PDFs or in the dataset.
2. **Unconfirmed scripts in the CSV:** left out entirely, with the count shown on screen. The alternative is rows with status and empty marks.
3. **Marked-PDF overlay:** results box on the cover sheet plus per-page margin marks, as above.

### Data model changes (migration 0005)
- New table `export`.
- Job types `export_pdfs` and `export_dataset`.

### API
- `GET /api/exams/{id}/results`
- `GET /api/exams/{id}/results.csv`
- `GET /api/scripts/{id}/marked.pdf`
- `POST /api/exams/{id}/exports/class-pdf`
- `GET /api/exports/{id}` (status)
- `GET /api/exports/{id}/file`
- `POST /api/admin/training-export` (admin)
- `GET /api/admin/training-export/preview` (counts per exam, admin)

All are scoped like the rest (404 outside the teacher's classes).

### Tests
- **CSV:** totals and per-question marks equal the stored final marks (capped). Only confirmed scripts appear. Formula-like values are neutralised. UTF-8 with BOM.
- **Marked PDFs:** require confirmed scripts. Page count equals the script's pages. The student code is in the text and the name is not. The stored page images are byte-for-byte unchanged. The combined file holds every confirmed script.
- **Dataset:** excludes non-consented students and unconfirmed scripts. No student name appears anywhere in the zip. The manifest fields match the README. Images are upright. The export is audited. Admin only.
- **Exam completion:** the exam completes when the last script is confirmed and returns to reviewing on reopen.
- **Permissions:** another teacher gets 404 on every endpoint; a teacher gets 403 on the training export.
- **Frontend:** Vitest tests for the results screen and admin export. A browser test exports the CSV and one marked PDF from the seeded exam.
- **Per-question schemas:** each schema requires exactly the question's point ids. Validation and evaluation tests updated.

### Done when
- All of the above pass in `python scripts/check.py`, and its output has been read before committing.
- A teacher can download the CSV and the marked PDFs, and an admin the dataset, in the browser.
- The overnight evaluation with per-question schemas has been reported.

---

## Before the demo: page check and live AI progress (owner, 2026-10-15)

Approved by the owner on 2026-10-15 (all five parts). Built after the schema evaluation and the ✓ ✗ PDF change. No new dependencies.

**Why the page check comes first.** In the owner's review, one upside-down answer page cost a weak-English student 3 marks (11 instead of 14). After the page was rotated and re-marked, the AI gave exactly 14. The model cannot detect orientation (D-049), so a teacher checks the pages before any AI time is spent.

### 5. Check pages before AI marking
- **Screen:** a "Check pages" step on the exam's Marking tab, above the AI panel.
  - **Thumbnails:** every page of every script, grouped by student, shown with its current orientation. Cover sheets are marked as such.
  - **Rotate:** one-click left and right buttons on each page, plus reset. This uses the existing teacher rotation (layer a), so it is audited and the stored image is never changed.
  - **Confirm:** a "Pages checked" button records who checked and when.
- **Rule:** "Start AI marking" and "Re-run AI marking" are refused until the exam's pages are checked (`exam.pages_not_checked`). The AI panel says "Check page orientation first", with a link to the step.
- **New uploads:** an upload that adds pages to the exam clears the check, so the new pages are looked at too.
- **Data:** `exam.pages_checked_at` and `exam.pages_checked_by_id`; the check is audited.

### 1–4. Live AI progress (on the Marking tab)
1. **Progress bar with time left.**
   - **Progress:** counted in work units (pages to read plus questions to mark), so it moves every 30–60 seconds.
   - **Time left:** from the average duration of the recent model calls on this machine (reading and marking measured separately). It is shown only once there is at least one measured call of each kind needed.
2. **What each script is doing**, in its queue row: "Reading page 1 of 2…", "Marking question 3 of 6…", then "Ready to review" with a link.
3. **"Watch it read":**
   - **Current page:** a panel shows a thumbnail of the page being read now.
   - **Latest result:** beside it, the most recently finished transcription.
   - **Granularity:** updates page by page and question by question; no word-by-word streaming.
4. **Finished signal:** the browser tab title changes (for example "✓ 4 ready · Margin") and a message gives the counts (ready, needing manual marking). No sound by default.

**Design.**
- **Worker progress:** the worker records its current step on the script (`ai_step`, step number, total, start time) and commits it before each page and each question. These fields are saved apart from the results and never affect marks.
- **Marker hook:** the Marker interface gains an optional progress callback, called before each question.
- **Timings:** each model call's duration is stored in `model_call` (role, seconds, time).
- **Endpoint:** `GET /api/exams/{id}/ai-progress`. The queue polls it every few seconds while AI work is running.

### Tests
- **Page check:** start and re-run are refused until the pages are checked; a new upload clears the check; the check is audited; another teacher gets 404.
- **Progress:** progress units and the time-left estimate (unit tests); worker steps recorded for reading and marking (Mock).
- **Frontend:** progress screen behaviour and the finished signal (Vitest).
- **Browser:** check pages and start marking, then follow the progress until "ready", with the Mock model.

---

## After Phase 4 (owner, 2026-10-15; in this order, each after Phase 4 is approved)
1. **Per-question output schemas:** each marking call gets a schema listing exactly that question's point ids (each required once), for both evidence designs. Then re-run the evaluation overnight with both designs.
2. **Whole-script marking in one call** as a third marker design: all questions in one reply, validated per question, re-asking only the failed questions. Evaluated against the per-question designs on agreement, failures and time.

**Evaluation reports from now on** also give, per subject: agreement within 1 mark, mean absolute difference, and the direction of disagreements (over- versus under-marking).

## Blueprint item 3 — approved 2026-10-16

Build local document extraction and school scheme reuse after per-page sheets.
- Persist extended point rules (rejects, dependencies, ECF, meaning, teacher-only)
  and any-N groups; centralise totals for review/results/exports.
- Preserve uploaded originals and extraction drafts separately from confirmed schemes.
  Document jobs run locally through the durable queue; document and library APIs use
  existing teacher/school scopes. Confirming the scheme remains an explicit teacher action.
- Add DOCX/XML dependencies from the approved list; no cloud OCR or Office service.
- Add EN/FR original-versus-editor UI and school library controls.
- Test rule graphs/caps, teacher-only exclusion, document limits, permission boundaries,
  migration parity and preservation of confirmed scheme requirements. Run full checks.

## Blueprint item 4 — automatic marking and restart recovery

Add per-exam automatic start (default on), eligible-script scheduling after inbox
processing, per-question marking checkpoints, and explicit lifecycle labels.
Per-page QR orientation allows automatic start; plain-paper fallback keeps the
teacher orientation check. Missing pages, identity problems and duplicates block
marking. Keep teacher confirmation and manual items mandatory. Test interrupted
marking, queue idempotency, eligibility and settings permissions; run all checks.

## Blueprint item 5 — phone capture

Add a browser camera/photo screen, school-local original archiving, bounded child
image preparation, crop/QR deskew/colour cleanup, and a teacher preview before
routing. Persist preparation states across restarts. Scope unknown captures to
their uploader; classified pages retain exam access checks. Test cropping, original
preservation, QR routing, duplicate handling and access boundaries. No new packages.
