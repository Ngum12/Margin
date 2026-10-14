# Plan: Phase 0 and Phase 1

Status: Phase 0 complete and approved (2026-10-14). Phase 1 approved; waiting on dependency approval (D-019).
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
