# Plan: Phase 0 and Phase 1

Status: Phases 0 and 1 complete and approved (2026-10-14). Phase 2 built (2026-10-14), awaiting owner review. Refinements made while building are recorded in DECISIONS (D-021 to D-026).
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
