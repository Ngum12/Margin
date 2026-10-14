# CLAUDE.md

On-premise AI marking assistant for secondary schools. Full requirements: `PROJECT_BRIEF.md` (read it). Plan: `docs/PLAN.md`. Decisions: `docs/DECISIONS.md`. Out-of-scope ideas: `docs/BACKLOG.md`. Dependency licences: `docs/DEPENDENCIES.md`.

## Current phase
**Phase 0 (Foundation): complete.** Phase 1 (accounts, classes, exams, mark schemes) planned in `docs/PLAN.md`; do not start it until the owner says so.

Workflow: one phase at a time → plan → build → `python scripts/check.py` passes → commit → stop and report. Never claim something works without running it. Record decisions and deviations in `docs/DECISIONS.md` first. Out-of-scope ideas go to `docs/BACKLOG.md`.

## Non-negotiables (breaking any is a critical bug)
- **Data stays in the school.** The only outbound network calls go to the configured model server (`MARGIN_MODEL_BASE_URL`, default local Ollama). No telemetry, analytics, external fonts, CDNs or third-party scripts; all assets bundled locally. A test must fail on any other outbound connection (Phase 3).
- **Pseudonymous codes only** on paper and to models. Real names optional, local DB only, never sent to a model, never logged.
- **Auth:** Argon2 passwords, httpOnly secure session cookies, CSRF on unsafe methods, roles `admin`/`teacher`; a teacher sees only their own classes and exams.
- **Files:** uploads and images stored outside served directories (`MARGIN_DATA_DIR`), served only through authenticated endpoints; validate type and size; PDFs are untrusted input.
- **Secrets** from env or git-ignored `.env`, never in code.
- **AI never finalises a mark.** Teacher confirmation required before export.
- Every AI output stores model name, model version, prompt version, timestamp.
- **Append-only audit log** for every change to a mark or transcription (who, when, old, new, reason).
- Model output validated against a strict schema; bounded retries; then flag for manual marking. Never drop or invent data.
- **Resilience:** background worker on a DB job table; jobs survive restarts, steps idempotent. Web app usable when worker or model server is down.
- **Licences:** permissive only (MIT/BSD/Apache-2.0 or similar). No GPL/AGPL. **No PyMuPDF.** Record every dependency in `docs/DEPENDENCIES.md`.
- **i18n:** every user-facing string through i18next (`frontend/src/i18n/locales/{en,fr}.json`); keys must match across locales.
- Never log transcriptions or images. Works on modest laptops and tablets over LAN.

## Architecture
```
Browser (React/TS, Vite build) --> FastAPI app (backend/app) --> SQLite (WAL) via SQLAlchemy 2 + Alembic
                                          |                    --> local file store (MARGIN_DATA_DIR)
                                   Worker process (polls DB jobs table) --> Ollama (local vision model)
```
- `backend/app/main.py` `create_app(settings)`: API under `/api`, security headers (strict CSP), SPA served from `frontend/dist` with client-route fallback.
- `backend/app/config.py`: `Settings` (pydantic-settings, `MARGIN_` prefix). Document every setting in `.env.example`.
- `backend/app/ai/` (Phase 3): `Reader` / `Marker` interfaces; `Ollama*` and `Mock*` implementations; versioned prompts in `ai/prompts/`. The app depends only on the interfaces.
- Business logic in services, not HTTP handlers. Queries only through SQLAlchemy (PostgreSQL-swappable).
- Frontend: React + TypeScript strict, plain CSS with tokens (`src/styles.css`), same-origin `fetch` only (`src/api.ts`).

## Commands
Run from the repository root. Requires `uv` and Node/npm. Python 3.12 is uv-managed (`uv python install 3.12`).

| Task | Command (`make` equivalent) |
|---|---|
| Install deps | `cd backend && uv sync --frozen` and `cd frontend && npm ci` (`make install`) |
| **All checks** | `python scripts/check.py` (`make check`) |
| Auto-fix formatting | `python scripts/check.py --fix` (`make fix`) |
| One side only | `python scripts/check.py backend` / `frontend` |
| Run app (prod mode) | `python scripts/run.py` → http://127.0.0.1:8000 (`make run`) |
| Dev (reload + Vite) | `python scripts/run.py --dev` → Vite at http://localhost:5173 (`make dev`) |
| Backend tests only | `cd backend && uv run pytest` |
| Frontend tests only | `cd frontend && npm test` |

Checks = ruff format, ruff lint, mypy strict (app, tests, scripts), pytest (warnings are errors); prettier, eslint, tsc, vitest, vite build.

Note: set `UV_PYTHON_PREFERENCE=only-managed` if running `uv` by hand on the owner's Windows machine (a broken system `python3.12` shim exists); the scripts set it automatically.
