# CLAUDE.md

On-premise AI marking assistant for secondary schools. Full requirements: `PROJECT_BRIEF.md` (read it). Plan: `docs/PLAN.md`. Decisions: `docs/DECISIONS.md`. Out-of-scope ideas: `docs/BACKLOG.md`. Dependency licences: `docs/DEPENDENCIES.md`.

## Current phase
The owner approved the eight-item end-to-end blueprint and dependencies on 2026-10-16,
with Windows as the school deployment target. The blueprint supersedes the original
brief's portal exclusion, pseudonymous-only printed sheets and phase-stop rule.
Build items 1–6 are committed; item 7 is in progress. Document import currently
supports PDF/DOCX/images/text, with legacy binary DOC conversion still unavailable.
Continue the approved build order without requesting approval between items.
Run `python scripts/check.py` in full, read its output and commit after each item.
Keep EN/FR, school-local AI/storage and teacher confirmation mandatory. Optional
home student access means encrypted delivery of only the signed-in student's
released records from the school box, never external AI or third-party storage.

## Commit and test-failure rules (permanent, set by the owner)
- **Never commit until `python scripts/check.py` has passed in full and its output has been read.** Run the suite as its own step, read the summary, then commit in a separate step. Never chain a commit after a test command whose result has not been checked.
- **A test that fails even once must be investigated, not just re-run.** Find the cause, fix it, and record the cause (or, if it cannot be reproduced, what was tried and the most likely cause) in the commit message and in `docs/DECISIONS.md` if it changes how tests are written.

## Dependency and package rules (permanent, set by the owner)
- **Never run unvetted packages.** No `npx --yes`, no `npx <pkg>` for packages not already in the lockfile, no `pip install`/`uv tool run`/`uvx` of ad hoc tools, no curl/wget downloads of scripts or binaries.
- **Never add a new dependency (runtime or dev, backend or frontend) without owner approval.** First list each package with version, licence, purpose, and its new transitive packages and their licences; then wait for explicit approval. Only then install, pin exactly, and record it in `docs/DEPENDENCIES.md`.
- Upgrades of existing dependencies follow the same rule.
- **At the start of each phase**, list every new dependency the phase needs in one table (package, version, licence, purpose, transitive packages) for approval together. Anything not on that approved list still needs separate approval.
- Commit both lockfiles (`backend/uv.lock`, `frontend/package-lock.json`).

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
- Business logic in `app/services/` (no FastAPI imports); HTTP in `app/api/`. Queries only through SQLAlchemy (PostgreSQL-swappable).
- **Access scoping** lives in `app/services/access.py`: every class, exam and student query goes through the `visible_*` scopes; out-of-scope ids raise `NotFoundError` (404).
- **Errors:** services raise `app.errors.DomainError` subclasses with a stable `code`; the API returns `{code, detail, issues}`; the frontend translates `errors.<code>` and `issues.<code>`. Add en and fr text for every new code (a test enforces it).
- **Audit:** every change to users, classes, students, consent and exams goes through `app.services.audit.record` (append-only, guarded in the ORM). Never put names or passwords in audit values.
- **Marks:** stored as integer half marks (`app/marks.py`, D-018); the API and UI use whole marks.
- **Schema changes:** edit models, run `cd backend && uv run alembic revision --autogenerate -m "..."`, review the file (delete the duplicate enum CHECK constraints Alembic emits), and keep `tests/test_migrations.py` passing.
- **Scans (Phase 2):** cover sheets carry `MA1-<token>-<check>` QR codes, never ids (`app/sheets/`). Uploads are streamed raw (`application/pdf`), stored unchanged with SHA-256 (`uploads/<id>/original.pdf`), and rendered by a child process with a timeout (`app/pdf/render_worker.py`, `runner.py`; never import PDFium in the web process). `app/services/splitting.py` is the pure placement logic: never assign by guess; anything uncertain goes to the tray with a reason (`UnassignedReason`, translated under `scans.reason.*`). Processing is idempotent and resumed on start-up (`upload_processor.py`) until Phase 3 moves it to the job table.
- **AI pipeline (Phase 3):** long work runs only in the worker (`python -m app.worker`, `app/worker/`) from the `job` table (`app/services/jobs.py`); handlers must stay idempotent. Models sit behind `Reader`/`Marker` (`app/ai/types.py`); pick with `MARGIN_AI_BACKEND=mock|ollama`. Prompts are versioned files (`app/ai/prompts/`). Model output is validated strictly (`app/ai/validation.py`); after retries the script is flagged for manual marking, never guessed. Only `app/ai/ollama_client.py` may open network connections (tests enforce it). Measure any model or prompt change with `uv run python -m app.cli evaluate --data <folder> --backend ollama --report r.json`.
- **Deployment modes (D-052):** school box now; district hub and Margin-hosted cloud later, same code. Never assume the model server or the database is on the browser's machine; keep the model host configurable.
- **When to evaluate (owner, 2026-10-15):** no more evaluations on the synthetic set until real handwritten scripts exist. Re-evaluate only when the prompt or the model changes, always overnight, with only the design in use and cached transcriptions.
- **Evaluation reports** must give, per subject: exact agreement, agreement within 1 mark, mean absolute difference, and over- versus under-marking counts (owner, 2026-10-15).
- **Deployment (D-065, D-066):** `docs/INSTALL.md`; Caddy HTTPS (`deploy/Caddyfile`); Docker images pinned exactly (`Dockerfile`, `docker-compose.yml`). After a backend dependency change, regenerate `backend/requirements.lock.txt` with `uv export --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.lock.txt` (a test checks it matches `uv.lock`).
- **Third-party notices:** after any dependency change run `cd backend && uv run python ../scripts/third_party_notices.py`; the check suite verifies it.
- Request DB transactions commit before the response is sent (`Depends(..., scope="function")`, D-021).
- Frontend: React + TypeScript strict, plain CSS, same-origin `fetch` only (`src/api/client.ts`). **Design system "Marking desk": `docs/DESIGN.md`.** Every colour, size and radius is a token in `src/styles/tokens.css` (contrast checked by `tokens.test.ts`); marking red only for marks, confirmed green only for teacher confirmation. Fonts and icons are bundled files listed in `src/assets/assets.json`.

## Commands
Run from the repository root. Requires `uv` and Node/npm. Python 3.12 is uv-managed (`uv python install 3.12`).

| Task | Command (`make` equivalent) |
|---|---|
| Install deps | `cd backend && uv sync --frozen` and `cd frontend && npm ci` (`make install`) |
| **All checks** | `python scripts/check.py` (`make check`) |
| Auto-fix formatting | `python scripts/check.py --fix` (`make fix`) |
| One side only | `python scripts/check.py backend` / `frontend` |
| First-time setup | `cd backend`, then `uv run python -m app.cli migrate`, `uv run python -m app.cli init-school --name ... --country ...`, `uv run python -m app.cli create-user --username ... --display-name ... --role admin` |
| Run app (prod mode) | `python scripts/run.py` → http://127.0.0.1:8000 (`make run`; applies migrations first) |
| Dev (reload + Vite) | `python scripts/run.py --dev` → Vite at http://localhost:5173 (`make dev`) |
| Backend tests only | `cd backend && uv run pytest` |
| Frontend tests only | `cd frontend && npm test` |
| Browser tests only | `cd frontend && npm run build && npm run e2e` (installed Edge; fresh seeded database from `scripts/e2e_server.py`) |
| Orientation evaluation | `cd backend && uv run python -m app.cli evaluate --data <folder> --backend ollama --orientation [--orientation-extra chemistry:upside_down:<image>]` |

Checks = ruff format, ruff lint, mypy strict (app, tests, scripts), pytest (warnings are errors); prettier, eslint, tsc, vitest, vite build, Playwright browser tests (Edge).

Note: set `UV_PYTHON_PREFERENCE=only-managed` if running `uv` by hand on the owner's Windows machine (a broken system `python3.12` shim exists); the scripts set it automatically.
