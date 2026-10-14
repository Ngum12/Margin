# Decision log

Each entry: date, decision, alternatives considered, reason. Newest at the bottom. Deviations from `PROJECT_BRIEF.md` are marked **Deviation**.

---

### D-001 · 2026-10-14 · Repository layout and package name
- **Decision:** Monorepo with `backend/` (Python package `app`), `frontend/`, `docs/`, `deploy/`, `scripts/`. Backend package named `app` so the brief's paths (`backend/app/ai/`) hold.
- **Alternatives:** separate repos; a named package such as `marking_assistant`.
- **Reason:** one machine, one release, one version. Matches the brief.

### D-002 · 2026-10-14 · Python 3.12 managed by uv
- **Decision:** Use `uv` for the Python environment, dependency resolution and lockfile (`backend/uv.lock`). Python 3.12 is a uv-managed interpreter (`python-preference = "only-managed"`).
- **Alternatives:** pip + venv + pip-tools; Poetry.
- **Reason:** fast, reproducible lockfile, installs the right Python itself. The dev machine has a broken system `python3.12` shim (Chocolatey), so managed-only avoids picking it up. uv is a dev/deploy tool (MIT/Apache-2.0), not shipped as a runtime dependency.

### D-003 · 2026-10-14 · Exact version pins
- **Decision:** Direct dependencies pinned with `==` in `pyproject.toml` and exact versions in `package.json`; transitive dependencies locked in `uv.lock` and `package-lock.json`.
- **Alternatives:** ranges plus lockfiles only.
- **Reason:** brief section 0.7. Upgrades become explicit, reviewed changes.

### D-004 · 2026-10-14 · `make check` implemented as a Python script
- **Decision:** `scripts/check.py` (standard library only) runs every check; the `Makefile` is a thin wrapper (`make check` → `python scripts/check.py`). Same for `scripts/run.py` / `make run`.
- **Alternatives:** Makefile only; shell scripts; `just`/`task`.
- **Reason:** the owner's Windows machine has no `make`. A stdlib Python script runs identically on Windows, Linux and in Docker, while `make check` still works where make exists.

### D-005 · 2026-10-14 · Environment variable prefix `MARGIN_`
- **Decision:** All settings use the `MARGIN_` prefix, loaded with pydantic-settings from the environment or a git-ignored `.env` at the repo root.
- **Alternatives:** `MA_`, `MARKING_`, no prefix.
- **Reason:** repository name; avoids collisions with other software on a shared school machine. Easy to rename before first release if the product name changes.

### D-006 · 2026-10-14 · Formatting and linting tools
- **Decision:** Backend: ruff (format + lint, incl. bandit `S` rules), mypy strict with the pydantic plugin, pytest. Frontend: Prettier, ESLint with `typescript-eslint` strict type-checked rules, TypeScript strict (plus `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`), Vitest with jsdom.
- **Alternatives:** black + flake8 + isort; Biome for the frontend.
- **Reason:** brief section 9 names ruff, mypy, pytest, eslint, TS strict, vitest; Prettier added for the "formatting" step.

### D-007 · 2026-10-14 · Frontend served by FastAPI with SPA fallback
- **Decision:** In production FastAPI serves `frontend/dist`: real files directly, any other non-`/api` path returns `index.html` (client-side routes). Unknown `/api/*` returns JSON 404; missing `/assets/*` returns 404; path traversal outside `dist` is refused. In development Vite serves the frontend and proxies `/api`.
- **Alternatives:** nginx/Caddy in front; FastAPI `StaticFiles(html=True)` (no SPA fallback).
- **Reason:** one process to run on a school machine, as the brief requires.

### D-008 · 2026-10-14 · Strict Content-Security-Policy from day one
- **Decision:** Every response carries `Content-Security-Policy: default-src 'self'` (plus related directives) and standard hardening headers. Swagger UI and ReDoc load from a CDN, so they are never served (changed in Phase 1; the CSP would block them anyway). The raw schema `/api/openapi.json` is served only when `MARGIN_ENV=development`.
- **Alternatives:** add headers at deployment time via a reverse proxy.
- **Reason:** non-negotiable "no external fonts, CDNs or third-party scripts" is then enforced by the browser, not only by convention.

### D-009 · 2026-10-14 · i18n with i18next / react-i18next, introduced in Phase 0
- **Decision:** Frontend strings go through i18next with `en.json` and `fr.json` from the first screen. A test asserts both locales have identical key sets. Backend errors will return stable codes for the frontend to translate (Phase 1).
- **Alternatives:** FormatJS/react-intl; Lingui; waiting until Phase 1.
- **Reason:** widely used, MIT, simple JSON catalogues that non-developers can translate. Even the Phase 0 placeholder has user-facing text, so the non-negotiable applies now.

### D-010 · 2026-10-14 · Keep `httpx` for the test client (owner confirmed 2026-10-14: keep httpx, do not add httpx2)
- **Decision:** Starlette 1.8 emits a deprecation warning recommending `httpx2` for `TestClient`. We keep `httpx` 0.28.1 (dev-only) and filter that one warning; all other warnings are errors in pytest.
- **Alternatives:** switch to `httpx2`.
- **Reason:** adding a new package was blocked by the session's permission policy pending owner review. `httpx` works; revisit when the owner approves `httpx2` or Starlette drops `httpx` support.

### D-011 · 2026-10-14 · No component library; plain CSS with design tokens
- **Decision:** Plain CSS with custom properties, system font stack, no Tailwind or component library for now.
- **Alternatives:** Tailwind (bundled), MUI, Mantine.
- **Reason:** small bundle for modest laptops and LAN; calm, plain design; fewer dependencies to audit. Revisit if screen 7 (review) needs complex widgets.

### D-012 · 2026-10-14 · Default vision model tag (open, resolve in Phase 3)
- **Decision:** Configuration default for the reader model will be a Qwen3-VL 8B tag; the exact tag is to be confirmed against the Ollama library in Phase 3.
- **Current state:** Ollama 0.40.3 is installed on the dev machine with only `qwen2.5:7b` and `llama3.2:latest` (text-only). No vision model is present yet; Phase 3 needs one pulled (internet required once).
- **Reason:** brief section 5. Recorded now so it is not forgotten.

### D-013 · 2026-10-14 · FastAPI native telemetry explicitly disabled
- **Decision:** FastAPI 0.143 depends on `opentelemetry-api` and has built-in OpenTelemetry hooks that `FASTAPI_OTEL_AUTO_CONFIGURE=true` plus `OTEL_EXPORTER_OTLP_ENDPOINT` can switch on. `create_app` passes `telemetry={...all False, auto_configure: False}`. A test sets those env vars and asserts nothing is enabled, and asserts the OpenTelemetry SDK/exporters are not installed.
- **Alternatives:** pin an older FastAPI without telemetry; rely on the env var being unset.
- **Reason:** non-negotiable "no telemetry". `opentelemetry-api` alone is a no-op API (Apache-2.0) with no exporter; explicit disabling plus a test guards against future changes.

---

### D-014 · 2026-10-14 · Mark scheme validation rules
- **Decision:** as in `docs/PLAN.md` Phase 1: every question has max ≥ 1 and at least one point; every point ≥ 1 mark; a question's point marks must sum to at least its max (more is allowed, "any N of M", with awards capped at max); labels unique per exam; `draft` → `ready` only when valid; structural edits only in `draft`.
- **Alternatives:** require points to sum exactly to max (cannot express "any 3 of 5").
- **Reason:** matches how GCE mark schemes are written. Approved by owner with the plan.

### D-015 · 2026-10-14 · DB-backed sessions with per-session CSRF token
- **Decision:** random 32-byte session token in an httpOnly, SameSite=Lax cookie; only its SHA-256 hash is stored (`user_session`). Idle and absolute expiry. A per-session CSRF token is returned by `GET /api/auth/me` and required in `X-CSRF-Token` for unsafe methods; login is guarded by a same-origin Origin/Referer check.
- **Alternatives:** signed stateless cookies (cannot revoke), JWT (same, plus no benefit here).
- **Reason:** revocable (sign-out, deactivated users), no server secret to manage, works offline.

### D-016 · 2026-10-14 · Secure cookies configurable; production refuses to start insecure
- **Decision:** `MARGIN_COOKIE_SECURE` (unset → true in production, false in development/test). In production the app **refuses to start** if secure cookies are off, unless `MARGIN_ALLOW_INSECURE_COOKIES_IN_PRODUCTION=true`, in which case it starts and logs a warning. Implemented in `app/startup_checks.py`, tested in `tests/test_startup_checks.py`. Local HTTPS (locally generated certificate) ships in Phase 6.
- **Alternatives:** always Secure (breaks plain-HTTP LAN installs); silently allow insecure in production.
- **Reason:** owner decision 2026-10-14. Safe by default, with an explicit, logged escape hatch.

### D-017 · 2026-10-14 · Subjects as config files; CSV-only mark scheme import
- **Decision:** subjects (code, names in en/fr, curriculum, reader notation hints) are TOML files in `backend/app/subjects/configs/`, validated with Pydantic at startup (TOML read with stdlib `tomllib`, no new dependency). Exams reference `subject_code`. Mark scheme import is CSV only in v1.
- **Alternatives:** subjects table edited in the admin UI; YAML (needs a dependency); structured-text import.
- **Reason:** adding a subject or curriculum is a configuration change, not code. Owner approved 2026-10-14.

### D-018 · 2026-10-14 · Marks stored as integer half-mark units
- **Decision:** every stored mark (question maximum, mark scheme point marks, and later proposed and final marks) is an integer count of **half marks** (`*_half_marks` columns; 1 mark = 2 units). Conversion lives in one module (`app/marks.py`). The API and UI use whole marks for now: inputs must be whole numbers and are converted on the way in and out. Enabling half marks later is a validation and UI change, with no data migration.
- **Alternatives:** integer whole marks (needs a migration later); floats or decimals (rounding issues, awkward in SQLite).
- **Reason:** owner decision 2026-10-14. Integers keep totals exact and portable to PostgreSQL.

### D-019 · 2026-10-14 · Dependency approval rule
- **Decision:** no new or upgraded dependency is installed without the owner's approval of a list showing each package, version, licence, purpose and new transitive packages. No unvetted tools are run (`npx --yes`, `uvx`, ad hoc downloads). Recorded permanently in `CLAUDE.md`.
- **Reason:** owner decision 2026-10-14, after an `npx --yes license-checker-rseidelsohn` run in Phase 0 (its npx cache entry was deleted the same day).

### D-020 · 2026-10-14 · CSV import sent as a raw request body
- **Decision:** the frontend reads the CSV file locally and POSTs its text (`Content-Type: text/csv`, size-limited) instead of a multipart upload, so Phase 1 does not need `python-multipart`.
- **Reason:** one less dependency now. Phase 2 (PDF uploads) will request `python-multipart` (Apache-2.0) for approval.

### D-021 · 2026-10-14 · Request transaction runs before the response is sent
- **Decision:** the DB session dependency is declared with `Depends(..., scope="function")`, so commit or rollback happens before FastAPI sends the response. FastAPI 0.143's default for `yield` dependencies ends them after the response is sent, which would hide a failed commit from the client.
- **Reason:** never report success for a change that was not stored. Checked in the installed FastAPI source (`param_functions.py`).

### D-022 · 2026-10-14 · Student names and passwords never enter the audit log
- **Decision:** audit snapshots for students record `code`, `class_id`, `has_display_name` and consent, not the name. Password resets are logged as an action with no values. Tests assert neither appears in audit rows. Sign-in outcomes go to the app log with the staff username only.
- **Alternatives:** full before/after snapshots.
- **Reason:** names are optional, local-only data; the audit log may later be exported for review.

### D-023 · 2026-10-14 · Out-of-scope ids return 404; admin-only actions return 403
- **Decision:** a teacher requesting another teacher's class, exam or student gets the same 404 as for a missing id. Admin-only endpoints answer 403 `auth.admin_required` (their existence is not secret).
- **Reason:** prevents probing for other teachers' data while keeping clear messages for role errors. Scoping is enforced in `app/services/access.py` queries, not in route handlers.

### D-024 · 2026-10-14 · Mark scheme saved as a whole; drafts may be incomplete
- **Decision:** the editor sends the full mark scheme (`PUT /api/exams/{id}/mark-scheme`), replacing questions and points in one transaction and one audit event. Saving is refused only for blocking problems (missing or duplicate labels, marks out of range); incomplete schemes save as drafts and must be completed before "ready". The frontend mirrors the rules (`src/exam/markScheme.ts`) with the same issue codes; the server stays authoritative.
- **Alternatives:** per-question and per-point endpoints.
- **Reason:** simpler and atomic; mark schemes are small. Nothing references questions while an exam is a draft, so replacing rows is safe. Revisit before Phase 3 if edits after marking starts are needed.

### D-025 · 2026-10-14 · Admin setup through a CLI; migrations on start
- **Decision:** `python -m app.cli migrate | init-school | create-user` (from `backend/`). Passwords are prompted, or read from a named environment variable, never passed as arguments. `scripts/run.py` runs `migrate` before starting the server.
- **Reason:** first-run setup without exposing an unauthenticated setup page on the school network.

### D-026 · 2026-10-14 · Every backend error and issue code must be translated
- **Decision:** `backend/tests/test_translations.py` scans the backend for error and issue codes and fails if `en.json` or `fr.json` lacks text for any of them. A frontend test asserts the two locales have identical keys.
- **Reason:** teachers must never see a raw code. It already caught one missing string.

### D-027 · 2026-10-14 · Uploads streamed as a raw PDF body; python-multipart not installed
- **Decision:** `POST /api/exams/{id}/uploads` takes the PDF as the raw request body (`Content-Type: application/pdf`) with the file name URL-encoded in `X-Filename`. The server streams it straight into `MARGIN_DATA_DIR/uploads/incoming/`, enforcing `MARGIN_MAX_UPLOAD_MB` and computing SHA-256 on the way, then checks for `%PDF-`. One request per file.
- **Alternatives:** multipart form upload with `python-multipart` (approved 2026-10-14).
- **Reason:** with multipart, Starlette spools file parts to the system temp folder before our code sees them, with no size limit on file parts; streaming the raw body keeps the size limit, the checksum and the storage location under our control. `python-multipart` is therefore not installed, and the owner removed it from the approved list (2026-10-14).

### D-028 · 2026-10-14 · PDF rendering and QR reading in a child process with a timeout
- **Decision:** `app/pdf/render_worker.py` runs as `python -m app.pdf.render_worker` (started by `app/pdf/runner.py` with `subprocess.run(..., timeout=MARGIN_RENDER_TIMEOUT_SECONDS)`). It opens the PDF with PDFium, renders every page, reads QR codes and detects the cover frame, writes JPEGs and finally `manifest.json` atomically. Exit codes map to `upload.pdf_unreadable`, `upload.too_many_pages`; a missing manifest or other exit code is `upload.render_crashed`; a timeout kills the child and gives `upload.render_timeout`. Renders are capped at 40 megapixels per page.
- **Reason:** owner requirement. A crash, hang or memory blow-up in native code affects only that file. Tests cover a malformed PDF, a hanging worker, a crashing worker, the page limit and that the worker really runs in another process.
- **Note:** if one page cannot be rendered the whole upload fails with a clear reason (rescan), rather than silently dropping that page.

### D-029 · 2026-10-14 · Cover sheet QR codes: random token + checksum; never assign by guess
- **Decision:** payload `MA1-<16 base32>-<4 base32>`: 80 random bits per (exam, student) sheet, stable across reprints, plus a 20-bit SHA-256 checksum. No database ids. Each sheet carries the code twice (level H) and a thick frame. A page is assigned only when it is a valid sheet of this exam for a student with no pages yet, or an answer page following such a sheet. Otherwise the page and the pages after it (until the next good sheet) go to the tray with a reason: `qr_damaged`, `qr_unreadable` (frame but no code), `qr_conflict`, `qr_not_ours` (foreign code on a framed page), `qr_bad_checksum`, `unknown_sheet`, `other_exam`, `duplicate_in_upload`, `already_uploaded`, `before_first_cover`. A foreign QR on an unframed page is treated as part of an answer page.
- **Reason:** owner requirement; wrong assignment is worse than asking the teacher.
- **Residual risk:** a cover sheet whose two codes and frame are all unreadable looks like an answer page and would be appended to the previous student. The teacher sees every script's pages, cover first, before marking (Phase 4).

### D-030 · 2026-10-14 · Originals kept byte-for-byte
- **Decision:** each upload is stored as `uploads/<id>/original.pdf`, unchanged, with SHA-256 and size in the `upload` row; the same file uploaded twice for one exam is refused (`upload.duplicate_file`). Page images and thumbnails live beside it in `uploads/<id>/pages/`. Files are served only through authenticated endpoints that resolve paths from the database and refuse anything outside `MARGIN_DATA_DIR`.
- **Reason:** owner requirement: the original is the record of what was scanned.

### D-031 · 2026-10-14 · Page image settings: 200 dpi colour JPEG, quality 90
- **Decision:** defaults `MARGIN_PAGE_DPI=200`, `MARGIN_PAGE_JPEG_QUALITY=90`, colour, plus 400 px-wide thumbnails (quality 80). Pages are rendered as a PDF viewer shows them (the page's `/Rotate` is applied; pypdfium2 does not do this by default, which the acceptance test caught); cover sheets are turned upright from the QR orientation.
- **Measured (simulated scanner output, 50 students x 5 pages = 250 pages):** original PDF 71 MB, page images 58 MB, thumbnails 8 MB, **about 137 MB per 50-script class**; rendering and QR reading 0.35 s per page (about 1.5 minutes per class) on the development laptop. Real scans may be larger depending on scanner settings (colour, 300 dpi); plan for 150 to 400 MB per class.
- **Reason:** brief (200 to 300 dpi); 200 dpi keeps handwriting legible for review and vision models while halving storage compared with 300 dpi.

### D-032 · 2026-10-14 · Upload processing in the web process until Phase 3
- **Decision:** after the upload response, a background task hands the upload to a single-thread processor in the web process, which starts the render child process. Processing is idempotent (one transaction replaces an upload's pages and scripts). On start-up, uploads left `pending`/`processing` are processed again. Tests run processing inline.
- **Reason:** the job table and worker are Phase 3 in the brief; this keeps restarts and power cuts safe meanwhile. Phase 3 moves upload processing onto the job table.
- **Superseded (Phase 3):** upload processing is now a `process_upload` job run by the worker (D-038).

### D-033 · 2026-10-14 · Untyped native libraries in mypy
- **Decision:** `reportlab` and `pypdfium2` ship without type information; mypy treats them as untyped (`ignore_missing_imports` for those two only). Their use is confined to `app/sheets/cover_pdf.py`, `app/pdf/render_worker.py` and test helpers.
- **Alternatives:** `types-reportlab` (an extra dependency, not approved).

### D-034 · 2026-10-14 · Third-party notices generated and checked
- **Decision:** `scripts/third_party_notices.py` writes `THIRD_PARTY_NOTICES.md` from the licence files installed with every shipped component (Python runtime closure, including the libraries bundled in pypdfium2's PDFium build and in Pillow, plus frontend runtime packages). The check suite runs it with `--check`, which fails if any shipped package or version is missing. Regenerate after any dependency change.
- **Reason:** owner requirement; bundled native libraries (FreeType, libjpeg-turbo, OpenJPEG, ICU, zlib and others) require their notices to ship.

### D-035 · 2026-10-14 · Exams with uploads cannot return to draft
- **Decision:** `ready -> draft` is refused with `409 exam.has_scripts` once any upload exists for the exam.
- **Reason:** owner requirement; the mark scheme must not change under scanned work.

### D-036 · 2026-10-14 · Unreadable covers and unusual page counts (owner fix after Phase 2)
- **Decision:** a page with the cover frame but no readable QR goes to the tray with its following pages, reason "Cover sheet found but code unreadable" (`qr_unreadable`; this was already the behaviour, now worded as the owner asked and covered by a dedicated real-image test). In addition, every script gets a page-count check: typical = median pages per script (cover included) once the exam has at least 3 scripts; a script is flagged when it has only a cover sheet, or its count is at least `max(2, round(typical / 2))` pages above or below typical. The Scans screen shows a "check this script" note; nothing is changed automatically.
- **Reason:** owner requirement. Catches the residual risk in D-029 (cover with codes *and* frame unreadable, merged into the previous script), tested end to end.

### D-037 · 2026-10-14 · Ollama client on the standard library; httpx stays dev-only
- **Decision:** `app/ai/ollama_client.py` uses `http.client` (standard library). `httpx` remains a development dependency (test client only).
- **Alternatives:** `httpx` as a runtime dependency (approved 2026-10-14).
- **Reason:** making `httpx` a runtime dependency also ships `certifi` (MPL-2.0, weak copyleft) whose CA bundle is useless for plain HTTP to a local Ollama. The standard library does everything needed (one JSON POST, timeouts) with no new shipped code. The `httpx` runtime approval is unused.

### D-038 · 2026-10-14 · Job queue and worker
- **Decision:** `job` table with a unique idempotency key per step (`upload:<id>`, `transcribe:<script>`, `mark:<script>`). Claiming is a conditional `UPDATE ... WHERE status='queued'`, committed immediately, so two workers can never take the same job. Failed attempts back off exponentially (30 s doubling, capped at 15 min) up to `MARGIN_JOB_MAX_ATTEMPTS` (default 6), then the job is `failed` with a code (never content). The worker heartbeats every `MARGIN_JOB_STALE_SECONDS / 3`; jobs whose heartbeat is older than `MARGIN_JOB_STALE_SECONDS` (default 120) are re-queued, at worker start **and whenever the worker is idle** (the kill-and-restart test found that start-up alone missed a job abandoned moments before a restart). `scripts/run.py` starts the worker next to the web app; `python -m app.worker` runs it alone.
- **Handlers are idempotent:** transcription commits page by page and skips pages already transcribed with the same model, version and prompt; marking writes all of a script's decisions in one transaction and skips if they exist. Unique constraints back this up.
- **Reason:** brief section 3 (database job table, survives restarts, no duplicated work).

### D-039 · 2026-10-14 · What counts as valid model output
- **Decision:** Reader: exactly `{"text": string}`. Marker, per question: exactly one entry per mark scheme point; whole marks from 0 to the point's marks (a string or 2.0 is rejected); confidence 0 to 1; category from the brief's list; evidence required when marks are awarded and it must be a verbatim quote of the transcription (whitespace and letter case aside; a "corrected" quote is rejected). Invalid output is requested again up to `MARGIN_MODEL_OUTPUT_RETRIES` (default 2) times. If the Reader still fails, the script is flagged `ai.reader_invalid_output` and nothing is stored. If the Marker fails on some questions, the valid questions' proposals are kept, nothing is stored for the failed ones, and the script is flagged `ai.marker_invalid_output`. A script with no answer pages is flagged `ai.no_answer_pages`.
- **Reason:** brief section 3: never silently drop or invent data. The verbatim-evidence rule makes the "evidence from the student's own words" promise checkable.

### D-040 · 2026-10-14 · Start-up refuses a model host outside the school network
- **Decision:** the app and worker refuse to start unless `MARGIN_MODEL_BASE_URL` points at a loopback, private (RFC 1918) or link-local address, `localhost`, a single-label name (Docker's `ollama`) or a `.local`/`.lan` name. `MARGIN_ALLOW_PUBLIC_MODEL_HOST=true` overrides deliberately.
- **Reason:** a configuration typo must not send student work to a cloud endpoint (non-negotiable: data never leaves the school).

### D-041 · 2026-10-14 · Prompt versions include a content hash
- **Decision:** prompts live in `app/ai/prompts/*.md` with a `version:` first line; the stored prompt version is `<declared>#<8 hex of SHA-256 of the file>`.
- **Reason:** brief: every output stores the prompt version. With the hash, an edit is always distinguishable in the data even if nobody bumps the declared version.

### D-042 · 2026-10-14 · AI marking is started explicitly, then runs automatically
- **Decision:** after uploading and clearing the unassigned tray, the teacher presses "Start AI marking" (Phase 3 shows it on the Scans screen; Phase 4 builds the full queue screen). That queues transcription for every waiting script; transcription then queues marking automatically, and the exam moves `ready -> marking -> reviewing` on its own. Uploads are processed automatically on arrival.
- **Alternatives:** start AI marking automatically after each upload.
- **Reason:** brief screen 6 ("button to start AI marking"). Marking locks a script's pages, so starting before the tray is cleared would stop the teacher from adding stray pages to it. The brief's Phase 3 test ("a full exam goes from upload to ai_marked automatically") is met from the moment marking starts: no further human step is needed.

### D-043 · 2026-10-14 · Evaluation metrics
- **Decision:** `python -m app.cli evaluate` runs the configured Reader on `<subject>/<page>.jpg|png` with `<page>.txt` ground truth and reports, per subject, CER and WER (Levenshtein over characters and whitespace-separated words, micro-averaged over pages), key-token recall (numbers, formulae such as `H_2O`/`x^2`/`Na^+`, and operators, as multisets), invalid outputs and seconds per page, plus a JSON report naming the model, its version and the prompt version. Case, spelling and punctuation are compared as written; only line endings and trailing spaces are normalised. The ground truth is never given to the Reader.
- **Reason:** owner requirement: every model change must be measurable.

### D-044 · 2026-10-14 · Network guard test design
- **Decision:** the guard records every `socket.connect` in the test process while the full pipeline runs with the Ollama implementations against a fake model server, and requires the set of destinations to equal exactly the model host and port. Connects made inside `socket.socketpair()` are ignored (on Windows the event loop's internal socket pair is emulated with a loopback connect). A static test allows networking imports only in `app/ai/ollama_client.py` (plus `socket.gethostname` in the worker). The render worker child process does no networking and is covered by the static test.
- **Reason:** brief section 3.
