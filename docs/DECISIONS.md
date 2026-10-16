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
- **Reason:** making `httpx` a runtime dependency also ships `certifi` (MPL-2.0, weak copyleft) whose CA bundle is useless for plain HTTP to a local Ollama. The standard library does everything needed (one JSON POST, timeouts) with no new shipped code. The owner dropped the `httpx` runtime approval (2026-10-14).

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
- **Approved by the owner 2026-10-14.**
- **Reason:** brief screen 6 ("button to start AI marking"). Marking locks a script's pages, so starting before the tray is cleared would stop the teacher from adding stray pages to it. The brief's Phase 3 test ("a full exam goes from upload to ai_marked automatically") is met from the moment marking starts: no further human step is needed.

### D-043 · 2026-10-14 · Evaluation metrics
- **Decision:** `python -m app.cli evaluate` runs the configured Reader on `<subject>/<page>.jpg|png` with `<page>.txt` ground truth and reports, per subject, CER and WER (Levenshtein over characters and whitespace-separated words, micro-averaged over pages), key-token recall (numbers, formulae such as `H_2O`/`x^2`/`Na^+`, and operators, as multisets), invalid outputs and seconds per page, plus a JSON report naming the model, its version and the prompt version. Case, spelling and punctuation are compared as written; only line endings and trailing spaces are normalised. The ground truth is never given to the Reader.
- **Reason:** owner requirement: every model change must be measurable.

### D-044 · 2026-10-14 · Network guard test design
- **Decision:** the guard records every `socket.connect` in the test process while the full pipeline runs with the Ollama implementations against a fake model server, and requires the set of destinations to equal exactly the model host and port. Connects made inside `socket.socketpair()` are ignored (on Windows the event loop's internal socket pair is emulated with a loopback connect). A static test allows networking imports only in `app/ai/ollama_client.py` (plus `socket.gethostname` in the worker). The render worker child process does no networking and is covered by the static test.
- **Reason:** brief section 3.

### D-045 · 2026-10-14 · Evaluation covers several models and marking
- **Decision:** `evaluate` also accepts the script-folder layout (`<subject>/<student>/page*.jpg` + one `truth.txt` per script), runs any number of models in one go (`--models vision` = every installed Ollama model with the vision capability; each model reads and marks), and with `--mark-schemes` + `--expected-marks` compares proposed marks per question with a teacher's expected marks: exact agreement, mean absolute difference (over answered questions), failed questions, and the same figures for `language_expression` questions plus marks lost and how often such answers were labelled a conceptual error. Marking is measured both on the model's own transcription (the real pipeline) and on the true transcription (the marker alone). A question's proposed mark is the sum of its points, capped at the question maximum.
- **Reason:** owner requirement: compare models on reading and marking, and check that weak English is not penalised.

### D-046 · 2026-10-14 · Thinking models, output cap and context size
- **Finding:** the plain Ollama tags `qwen3-vl:4b` and `qwen3-vl:8b` are the *thinking* variants (same digests as `-thinking`; `qwen3-vl:4b` installed here is `1343d82ebee3`). They reason before answering and ignore both `think: false` and `/no_think`. On this machine (i7-1260P, 32 GB, T550 4 GB; the 4B runs about 53 % CPU / 47 % GPU) the first page read with `qwen3-vl:4b` generated reasoning until Ollama's default 4,096-token context was full, after 21 minutes, without ever producing the answer; a marking call did the same. No usable output.
- **Decision:** (1) default models are the *instruct* variants (`qwen3-vl:8b-instruct` until the evaluation picks the default for this hardware); (2) `MARGIN_MODEL_THINK=false` is sent to models that support switching thinking off; (3) every call carries `num_predict` = `MARGIN_MODEL_MAX_OUTPUT_TOKENS` (2048) and `num_ctx` = `MARGIN_MODEL_CONTEXT_TOKENS` (8192); (4) a reply that stops because of the cap (`done_reason = "length"`) is invalid output: retried, then flagged for manual marking. Tests cover the cut-off path.
- **Reason:** one misbehaving model must not occupy the school machine for many minutes per page, and a truncated reply must never be used.
- **Also:** evaluation runs are resumable (`--cache`, default next to the report): each finished call is appended to a JSON-lines file and skipped on rerun; keys include model, version, prompt versions, image size and thinking setting.

### D-047 · 2026-10-14 · Line-number evidence as an alternative marker design (under evaluation)
- **Decision:** a second marker design, `MARGIN_MARKER_EVIDENCE=lines`: the answer is shown with numbered lines (`L1:`, `L2:` …), the model cites evidence as line numbers (at most 6 per point), and Margin copies those lines itself, so evidence is always the student's own words. Validation rejects unknown line numbers, more than 6 lines, and marks awarded without cited lines. Prompt `marker_lines.md` (`marker-lines-v1`). The quote design (D-039) stays the default until the evaluation decides.
- **Alternatives:** keep only verbatim quotes (strict, but small models paraphrase and fail validation, using up retries); accept fuzzy quotes (weakens the "evidence from the student's own words" guarantee).
- **Trade-off:** evidence is whole lines, coarser than an exact phrase; the review screen highlights a line rather than a phrase.
- **Reason:** the 2B evaluation showed frequent `marker_invented_evidence` failures from paraphrased quotes; the owner asked for the 4B to be evaluated with both designs.

### D-048 · 2026-10-15 · Default model for this hardware
- **Decision:** default `MARGIN_READER_MODEL` and `MARGIN_MARKER_MODEL` = `qwen3-vl:4b-instruct`, evidence design `quote`, on a machine like the development laptop (i7-1260P, 32 GB, 4 GB GPU). Evidence: `docs/evaluation/2026-10-15-model-comparison.md` (best agreement 81–82 %, 1 failed question of 57, reading CER 0.8 %, one model in memory). Next step before changing the evidence design: per-question output schemas listing exact point ids, then re-evaluate quote and line designs.
- **Alternatives:** qwen3-vl:2b-instruct (marking fails on paraphrased evidence); qwen2.5:7b as marker (lower agreement, under-marks, second model competing for the GPU); qwen3-vl:8b-instruct (not evaluated; too large for this GPU).
- **Caveat:** synthetic data only; revisit with real scripts.

### D-049 · 2026-10-15 · Page orientation: one model for three layers
- **Decision:** page image files are never changed after rendering. Orientation is metadata on `page`, in clockwise degrees: `rotation_stack` (layer b, from the most recent cover sheet's QR orientation, carried to the answer pages after it up to the next cover; a cover without a readable code resets it to 0), `rotation_auto` (layer c, from the Reader), `rotation_teacher` (layer a, the rotate control; when set it is the final word). Effective rotation = `rotation_teacher` if set, otherwise `(rotation_stack + rotation_auto) mod 360`. The browser shows the image turned with CSS; the worker turns it in memory before sending it to the model. `rotation_baked` holds the angle Phase 2 already applied to legacy cover images (migration 0004 copies `rotation_applied` there) and is never applied again (owner change 3, tested).
- **Reader orientation (owner change 1):** prompt `reader-v2` asks for `orientation` and `orientation_confidence` in the same reply as the transcription. A page judged not upright with confidence ≥ `MARGIN_ORIENTATION_MIN_CONFIDENCE` (0.8) is turned and read once more; the second read is kept; its own judgement never triggers another turn. An invalid or missing judgement keeps the read and turns nothing (the transcription itself is still validated strictly; unknown keys are still rejected). Pages with a teacher rotation skip the judgement. `MARGIN_ORIENTATION_CHECK=off` ignores it. Every auto-rotation is audited with the system actor.
- **Fresh reads:** `transcription.rotation` records which way up the page was read. After a teacher corrects an orientation, the page is marked `rotated_after_transcription` and the teacher may ask for a fresh read (`transcribe_page` job; never automatic). The fresh read is stored beside the first (the uniqueness key includes the rotation).
- **Current text rule changed:** a page's current transcription is now its newest version, whoever made it (Phase 3 preferred any teacher version). A fresh read the teacher asked for must be able to supersede an earlier teacher edit.
- **Quarter turns only (live run, 2026-10-15):** zxing reports a QR code's exact angle, so a cover tilted about a degree (phone-scan look) gave `rotation_stack` 359. The angle is now snapped to the nearest quarter turn (`app/pdf/orientation.py`), with unit and end-to-end tests.
- **Live finding (2026-10-15):** with `qwen3-vl:4b-instruct`, the owner's upside-down chemistry page was read well (CER 8.7 %) but judged "upright" with confidence 1.0, so layer c did not act; layers a and b work. Measured with `evaluate --orientation` (`docs/evaluation/2026-10-15-orientation.md`): 0 of 30 turned pages detected, 0 wrong turns, 1 timeout. Layers a and b carry orientation. **Layer c is off by default (owner, 2026-10-15):** `MARGIN_ORIENTATION_CHECK=off`; the code and the setting stay, and it is re-enabled only when a model passes the orientation evaluation. Timeouts and model-server 5xx errors are recorded as results in that evaluation instead of stopping it.
- **Reason:** owner requirements of 2026-10-14 (orientation layers a, b, c) and owner changes on approval.

### D-050 · 2026-10-15 · Review screen details
- **Keyboard:** as planned, except **zoom to fit is `f`**, not `0`: the plan gave `0` both to "zoom fit" and to "0 marks". Marks win. Ctrl+Enter inside the transcription editor saves the text instead of confirming the script.
- **No key is ever dropped:** changes made while an earlier one is still saving join an ordered queue; each is worked out from the latest saved review when its turn comes (for example `c` after `0` cycles from the category the server just set, and Ctrl+Enter right after Shift+A confirms once accept-all is stored). Found by the browser test; a Vitest test guards it.
- **Edits return the whole review**, so the screen always shows what is stored.
- **A fresh decision needs a category:** setting marks without a category takes the AI's category, or "correct" for full marks when there is no proposal; otherwise the teacher chooses. Confirm requires a mark and a category for every point.
- **Accept all** copies AI proposals only to points the teacher has not decided; teacher decisions are kept. One audit event per point.
- **Review time:** the first heartbeat opens the session; confirming adds the time since the last heartbeat under the same rules (at most 60 s, nothing after a gap of more than 5 minutes). Viewing a confirmed script records nothing. Class averages are over confirmed scripts with recorded sessions.
- **Queue order** follows the plan exactly (manual marking, transcription-uncertain points, lowest confidence, page-count flag, student code), then scripts still with the AI, then confirmed. Deductions and auto-rotated pages are shown but do not change the order.
- **Export guard:** `services/exports.py` (`exportable_scripts`, `require_confirmed`), tested; Phase 5 exports must use it.

### D-051 · 2026-10-15 · Browser tests
- **Decision:** Playwright drives the installed Microsoft Edge (`channel: "msedge"`, headless, background networking switched off). `scripts/e2e_server.py` seeds a fresh temporary database (reusing the backend test builders and the Mock models) and serves the real app with the built frontend; Playwright starts it. Six scenarios: queue order; keyboard-only review and confirm; rotate and undo auto-rotation (image reloads rotated); manual marking; French; another teacher gets "not found". Part of `python scripts/check.py` as `frontend: browser tests`, after the build.
- **Note:** `fsevents` 2.3.3 (MIT) appears in `package-lock.json` as an optional dependency of `playwright`. It is macOS-only and is not installed on Windows or Linux. It was not in the approved table; approved by the owner on 2026-10-15.

### D-052 · 2026-10-15 · Three deployment modes, one code base
- **Decision (owner):** Margin will support three deployment modes with the same code:
  1. **School box, offline**: everything on one machine or the school LAN (the current build).
  2. **District hub**: one installation serving several schools over a network.
  3. **Margin-hosted cloud**: run by us with our own open models; never third-party AI APIs.
- **Now:** only mode 1 is built. Modes 2 and 3 are not built now (requirements in `docs/BACKLOG.md`).
- **Rule from Phase 4 onward:** nothing may assume the model server or the database is on the same machine as the browser. In practice:
  - the model host stays configurable (`MARGIN_MODEL_BASE_URL`, http or https). A non-private host stays refused unless `MARGIN_ALLOW_PUBLIC_MODEL_HOST=true` is set deliberately;
  - the browser talks only to the Margin server, never to the database or the model server;
  - all database access goes through SQLAlchemy (PostgreSQL-swappable);
  - no feature may rely on `localhost`, the local file system of the browser's machine, or the client and server sharing a clock or disk;
  - user-facing text says "this Margin installation", not "this computer" or "the school's server", where the mode could differ.
- **Checked on 2026-10-15:** the Phase 4 code meets this. One queue string ("stored on the school's own server") was made neutral.
- **Unchanged for every mode:** student data is never sent to third-party AI services, and the non-negotiables in `CLAUDE.md` still apply. Mode 3 changes who runs the server, not where student data may go.

### D-053 · 2026-10-15 · A model call that does not finish is invalid output
- **Decision (owner):** a model reply that does not finish within `MARGIN_MODEL_TIMEOUT_SECONDS` counts as invalid output for that page or question: retried once (whatever `MARGIN_MODEL_OUTPUT_RETRIES` says), then the script is flagged for manual marking. Reader time-outs have their own reason, `ai.reader_timeout`; a marking question that times out is a failed question, like any other invalid output. Only a server that cannot be reached (connection refused, or no connection within the time limit) is "model unavailable" and the job is retried later.
- **Default lowered from 900 to 300 seconds:** normal calls measured on the development laptop take 35-140 s to read a page and 40-60 s to mark a question; real handwriting will give longer transcriptions, and the first call also loads the model. 300 s is about twice the slowest normal call. Configurable.
- **Reason:** in the orientation evaluation an upside-down page made the model ramble until the 15-minute limit. As "model unavailable", the job would have been retried again and again, wasting an hour or more of a night run on one page.

### D-054 · 2026-10-15 · Per-question output schemas for marking
- **Decision (owner order):** each marking call sends a JSON schema built for that question. `points` is an object with one required property per mark scheme point, keyed `p<point id>`, and no other properties. `awarded_marks` is limited to 0 up to that point's marks. In the line design, cited lines are limited to the answer's real line numbers, at most 6. Both designs: prompts `marker-v2` and `marker-lines-v2` list the point keys and show the exact reply shape.
- **Validation unchanged:** the parsers turn the keyed reply into the earlier list shape and apply every existing rule: points mismatch, marks range, verbatim evidence or valid lines. The list shape is still accepted when parsing, for the Mock and older tests; the model is only ever asked for the keyed shape.
- **Reason:** most line-design failures in the model comparison were `marker_points_mismatch` (a point left out or repeated). A keyed, required-properties schema makes that output impossible at generation time. The evaluation is re-run with both designs before any default changes.

### D-055 · 2026-10-15 · Results and exports (Phase 5)
- **Results:** a question's mark is the sum of its points' final marks, capped at the question maximum; a total is the sum of question marks; averages are over confirmed scripts. Unconfirmed scripts are listed without marks.
- **CSV:**
  - **Rows:** confirmed scripts only, with the student name when recorded (owner default 1). Unconfirmed scripts are left out entirely and the screen says how many (default 2).
  - **Format:** UTF-8 with a byte-order mark; headings in the teacher's language.
  - **Safety:** cells starting with `=`, `+`, `-` or `@` are prefixed with `'` so they never run as formulas.
- **Marked PDFs (default 3):**
  - **Pages:** stored images turned upright by their effective rotation; the stored files are never changed.
  - **Marks:** the cover sheet carries a results box (total, marks per question, comments). Each answer page has a margin column with the marks of the questions whose evidence is on that page.
  - **Identity:** codes only, never names.
  - **Text:** built-in PDF fonts (Windows-1252); characters they cannot print, such as emoji, are left out. No font files are added.
  - **Generation:** a single student's PDF is built on request; the class file is built by the worker (`export_pdfs` job).
- **Training dataset:**
  - **Contents:** admin only; confirmed scripts of consenting students; a zip with upright images, `dataset.jsonl` and a README that describes every field (a test checks this).
  - **Privacy:** no names and no teacher comments, since comments are free text that could mention a name. The README warns that students may write names on answer pages.
  - **Generation and audit:** built by the worker (`export_dataset` job), audited with counts.
- **Exports table:** every export is recorded, with its status and file, and audited. A failed build is marked failed and shown to the teacher, not retried.
- **Exam completion:** an exam becomes `completed` when every script is confirmed, and returns to `reviewing` when one is reopened. Both changes are audited like other exam status changes.
- **Admin screen:** read-only model configuration and status (brief screen 9); models are changed in the configuration file.
- **Browser tests:** the e2e server now runs the real worker in a thread, so background exports are tested end to end.

### D-056 · 2026-10-15 · Test-model output is labelled everywhere; production refuses it
- **Finding (owner's manual review):** the owner's installation had no `.env` file, so it ran with the default `MARGIN_AI_BACKEND=mock`. The chemistry exam was read and marked by the Mock models, whose fixed transcription and keyword matching produced a wrong-looking review (every point 0, "Omitted"). Nothing on screen said so.
- **Decision (owner):**
  - **Labels:** output from a test model (model names starting `mock-`) is labelled "Test model: not real AI marking" wherever it appears:
    - a banner on the review, queue and results screens;
    - a badge on each queue and results row;
    - the model label on every proposal and transcription;
    - an "AI model" column in the CSV;
    - a red line on every page of a marked PDF.

    A script is flagged when any current mark decision, or the current transcription of any page, came from a test model.
  - **Production refusal:** the web app and the worker refuse to start in production mode with `MARGIN_AI_BACKEND=mock`.
  - **Model details:** the review screen shows the model name, version and prompt version for every proposal and every transcription version.
- **Unchanged:** the code default stays `mock`, so that development and tests never call a model by accident. `.env.example` now sets `ollama` and explains the choice.
- **Owner's installation:** a `.env` file was created with `MARGIN_AI_BACKEND=ollama` (models `qwen3-vl:4b-instruct`, D-048).

### D-057 · 2026-10-15 · Re-run AI marking
- **Decision (owner):** "Re-run AI marking" for one script or for a whole exam, only for unconfirmed scripts that the AI is not already working on. It is available in the review screen and on the queue, and for administrators as `python -m app.cli rerun-ai --exam <id>` (audited as the system).
- **Runs:** every script has a run number (`script.ai_run`), and every mark decision records its run (`mark_decision.ai_run`; part of its uniqueness key). A re-run increments the number and queues the script from the start. Only the current run's decisions are shown, used in results and exported. Earlier runs, including the teacher's decisions on them, stay in the database as history. Teacher comments are kept.
- **Reading:** pages are read again only when the reading model or prompt has changed, so a re-run with the same reader marks the teacher's edited text. A new reader's reads become the current transcription.
- **Audit:** one `rerun_ai` event per script (old and new run, status), and one per exam with the number of scripts.

### D-058 · 2026-10-15 · Check pages before AI marking; live AI progress
- **Finding (owner's review):** one upside-down answer page cost a weak-English student 3 marks (11 instead of 14). After the page was turned and the script re-marked, the AI gave exactly 14. The model cannot detect orientation (D-049).
- **Page check (owner):**
  - **Screen:** a "Check pages" step on the Marking tab shows a thumbnail of every page at its current orientation, with one-click rotate (teacher rotation, layer a; audited, stored images unchanged).
  - **Rule:** AI marking and re-runs are refused until a teacher confirms the pages are checked (`exam.pages_checked_at`; error `exam.pages_not_checked`). The AI panel says "Check page orientation first".
  - **New pages:** an upload or a tray assignment that adds pages clears the check.
- **Live progress (owner, all four parts):**
  1. **Progress bar:** counted in work units (answer pages plus questions), with the time left estimated from the average of the last 20 measured calls of each kind on this machine. No estimate is shown until those calls exist.
  2. **Each script's live step** in its queue row.
  3. **"Watch it read":** the page being read now and the latest transcription.
  4. **Finished signal:** in the tab title and a message.
- **How progress is recorded:**
  - **Worker steps:** the worker records its current step on the script (`ai_step`, number, total, page, start time), committed apart from the results.
  - **Timings:** each call's duration goes into `model_call` (role, model, seconds; no content).
  - **Marker hook:** the Marker interface gains an optional `on_question` callback.
- **Polling:** the queue polls `GET /api/exams/{id}/ai-progress` every 3 s while work runs and every 10 s otherwise. Starting a run from the screen makes it look at once, so a quick run is never missed.

### D-059 · 2026-10-15 · Line-number evidence by default; the owner's marking findings
- **Decision (owner):** `MARGIN_MARKER_EVIDENCE` defaults to `lines`; `quote` stays available as a setting.
- **Evidence** (`docs/evaluation/2026-10-15-per-question-schemas.md`, 57 questions, `qwen3-vl:4b-instruct`, per-question schemas), on the real pipeline (marking the model's own transcription):

  | Design | Exact | Within 1 mark | MAD | Failed questions | Seconds per script |
  |---|---|---|---|---|---|
  | lines | 81 % | 95 % | 0.25 | 0 | 212 |
  | quotes | 81 % | 89 % | 0.25 | 2 | 338 |

  On the true transcription, quotes 86 % exact and lines 79 %. Both designs lean towards under-marking; economics is the weakest subject.
- **Prompt changes from the owner's manual review** (`marker-v3`, `marker-lines-v3`):
  - **(a) Method marks:** a method point needs the mark scheme's method, used the right way round. The same numbers in an inverted method ("moles = 40 / 4.0") earn nothing.
  - **(b) Categories:** "omitted" means nothing relevant was written. A written but wrong answer is a "conceptual error".
  - **(c) Display:** the student's line breaks are kept in the evidence shown on screen and in comments on marked PDFs.
- **Evaluation of (a) and (b):** one short overnight check under the owner's evaluation rule: line design only, marking only, cached transcriptions.
- **Accept all (owner's review):** a point where the teacher had chosen a category but no mark was skipped, so "accept all" seemed to do nothing. It now fills the AI's mark on every point without a mark and keeps the teacher's category. Tested with the owner's sequence.
- **Upgrades on SQLite with data (restart of the owner's installation):** migration 0007 rebuilds the `exam` table, which SQLite refused while scripts referred to it. The migration runner now switches foreign keys off during upgrades and checks every reference afterwards (`PRAGMA foreign_key_check`); the upgrade fails if any is broken. The new test upgrades a database containing data through the app's own engine; it fails on the old runner and passes now. The owner's database was backed up, the two empty leftover tables were removed, and it was upgraded with everything intact.

### D-060 · 2026-10-15 · The red pen
- **Decision (owner):** marked scripts look as if a teacher marked them in red, on the page beside the answers:
  - a long ✓ (pen strokes, not a font character) at the end of the line that earned each point;
  - a ✗ beside the question for each point missed, and a fraction for a partly earned point;
  - the question score in the left margin and the total circled at the top of the first answer page;
  - the teacher's comments handwritten (Caveat, OFL, approved) in the blank space below the answer or beside its last line.

  The same layout is drawn over the page on the review screen (a "Red pen" switch, remembered per browser), where proposals not yet decided are lighter. The screen also shows a red ✓/✗ beside each point and offers "Suggest from the mark scheme" (a comment listing the points missed; the teacher edits it).
- **No model work:**
  - **Evidence lines:** the AI's line evidence (default design) gives the lines that earned each point. For quotes, Margin finds the lines containing the quote. They are stored on each decision (`mark_decision.evidence_refs`: page and line, migration 0008).
  - **Lines of writing:** Pillow finds them by thresholding the page (Otsu) and measuring ink row by row, ignoring printed margin and ruled lines. This takes about 40 ms per page.
  - **Matching:** a dynamic-programming match pairs transcription lines with lines of ink in order, using text length against ink width. One transcription line may cover up to three lines of ink, because the reader often joins a line the student wrapped.
- **Safety:** if the match is not confident (mean cost above 0.12 page widths, or more than two skips), the page keeps the marks in the margin column and its comments go there too. Marks are never put in the wrong place. Where a line runs to the edge, its marks go just below its end rather than over the student's words. The stored images are never changed.
- **Checked on the owner's synthetic pages:** the lines found match the written lines exactly on chemistry, economics and mathematics pages (11, 11 and 15 lines). The AI's joined line "…joined together." is matched to its two lines of ink.

### D-061 · 2026-10-15 · Back to the v2 marking prompts
- **Finding:** the short check of `marker-lines-v3` (`docs/evaluation/2026-10-15-prompt-v3.md`) was worse than v2:
  - exact agreement fell from 81 % to 75 %, and under-marking grew from 7 questions (−10 marks) to 11 (−19);
  - economics fell from 73 % to 60 %, and a correct weak-English answer got 0;
  - "omitted" was used more, not less, and the inverted-method case still earned the method mark.

  Stricter prompt rules made the small model under-mark.
- **Decision (owner):** the exact v2 prompts are restored (`marker-lines-v2#268bfe02` default, `marker-v2#6bf69283` for quotes); no new evaluation is needed. Method-mark and category judgements stay with teacher review, which the review screen makes quick. The planned fix is fine-tuning on teacher corrections (the training-data export) after the demo.
- **Owner's installation:** no script was marked with v3, so nothing is re-run.
- **D-059 (a)–(b)** are withdrawn; **(c)** (line breaks kept in the display) stays.

### D-062 · 2026-10-15 · Red pen refinements
- **Decision (owner):**
  - **Ticks** only beside lines that earned marks: a point with no evidence line gets no tick (the question score still counts it).
  - **Crosses, conservatively:** a ✗ only when it is unambiguous: the answer earned nothing (✗ beside its first line), or exactly one line of the answer earned nothing (✗ beside that line). Otherwise no ✗; the red score shows the lost marks. Never a ✗ on a line that earned a mark. Model-cited wrong lines wait until after the demo.
  - **"Show the mark scheme to students"**: one per-exam setting (exam setup page), off by default, audited. It controls both the printed "Missing: …" notes (the points not earned) and the "Suggest from the mark scheme" button on the review screen. Teachers' own comments always print. Migration 0009, `PUT /api/exams/{id}/settings`.
  - **Pages:** the summary column is on the cover page only; answer pages give the scan the full width. Notes with no room below or beside their answer are written, labelled ("4: …"), in the blank space below the last answer.
  - **Notation:** printed notes show `CH_4` as CH₄, `x^2` as x², `^-3` as ⁻³, `->` as → and `<=>` as ⇌ (`app/exports/notation.py`). Characters Caveat lacks fall back to Noto Sans, then Noto Sans Symbols 2; → and ⇌ are drawn as strokes.
  - **Footer** on every page: "Marked with Margin AI assistance, reviewed and confirmed by [teacher]" / "Corrigé avec l'aide de l'IA Margin, revu et confirmé par [teacher]", in the exporting teacher's language (class PDFs: the export's language).
- **Replaces part of D-060's safety rule:** with no column on answer pages, a page whose match is not confident gets no red pen at all; the cover's summary still lists every question score and the teacher's comments.
- **Caveat** is recorded in `docs/DEPENDENCIES.md` with its SHA-256 (also in `fonts/fonts.json`).


### D-063 · 2026-10-15 · Recover from a stale session token
- **Finding (owner's report, "discard is not working"):** after signing in again (here after the app restart), a tab opened earlier kept the old session's CSRF token in memory. The browser's cookie belonged to the new session, so pages still loaded but every change from that tab (discard, assign, upload) got 403 `auth.csrf_failed`. Discard itself works.
- **Decision:** when a change is refused with `auth.csrf_failed`, the client fetches `/api/auth/me` once, takes the current token and retries the request once. It does this only if the cookie still belongs to the same user. If someone else signed in from another tab, it shows `auth.session_changed` ("Someone else signed in… reload") and never acts as that user. Sign-in and sign-out requests are never retried. Security is unchanged: another site cannot read `/api/auth/me`, so it cannot get the token.
- **Browser tests (failures during this change, investigated):** two browser tests failed once. Real AI marking ran on the same laptop at the same time, on battery power (22:34–23:05), and every step ran 5–10× slower. The French test's language switch went past its 10 s limit and stopped before switching back to English. The next test then signed in and found the screen in French. **Rule from now on:** the browser tests' `signIn` helper always returns the teacher to English, so one test stopping early cannot break the next. A later run was stopped at its one-hour limit with the backend tests at about 75%. The tests near that point pass on their own. A full re-run on mains power with `faulthandler_timeout=240` (it prints where any test that takes over 4 minutes is stuck) passed in full with no stall. Most likely cause: the machine was slowed down (just back from battery, low charge), not a hanging test. If it happens again, run the suite with `PYTEST_ADDOPTS="-o faulthandler_timeout=240"`.

### D-064 · 2026-10-16 · UI redesign: "Marking desk"
- **Decision (owner's brief):** a visual and interaction redesign before Phase 6. Business logic, the API, the data model and marking behaviour are unchanged. The reference is `docs/DESIGN.md`.
  - **Tokens:** one tokens file (`frontend/src/styles/tokens.css`) holds every colour; a test checks every text/background pair for WCAG AA.
  - **Colours:** marking red only for marks; confirmed green only for "confirmed by the teacher"; separate tones for errors and warnings.
  - **Fonts:** Literata for titles, Atkinson Hyperlegible Next for the interface, Noto Sans as fallback, and Caveat only for the red pen. All are bundled as files: no package and no CDN (`docs/DEPENDENCIES.md`).
  - **Shell:** an ink side rail and a top bar with the breadcrumb.
  - **Dashboard:** "What needs you today".
  - **Exam tabs:** in workflow order, with their state in words.
  - **Mark scheme:** looks like a printed mark scheme.
  - **Scans:** one script per row.
  - **Results:** sortable, with each question's share of zero scores and a print style.
  - **Review:** becomes the marking desk, with the page and margin line on the left and the current question's checklist on the right.
- **Interaction changes:**
  - **Review keys:** J/K move between scripts (they used to move between points); arrow keys move between points and questions; E shows or hides the evidence (it used to edit the transcription; that is now T); Enter confirms the marks (Ctrl+Enter still does). Enter on a focused button or link presses it instead. N and P are no longer used.
  - **Wording:** "Confirm script" is now "Confirm marks", leading to "Marks confirmed." (FR « Valider les notes » / « Notes validées »).
  - **Review layout:** shows one question at a time, and the red-pen layout is always loaded, because it also positions the evidence bands.
  - **Marked PDF:** uses the same marking red (#B3261E instead of #D11212).
- **Bugs found and fixed during the redesign:**
  - While sign-in status was loading, the old layout showed a language menu whose choice was not saved to the account.
  - A first version of the new layout remounted the sign-in form when loading finished, losing what had been typed. Loading and signed-out now share one layout.
  - Opening a script scrolled the window to the focused point and hid the student's name. The first focus no longer scrolls.
- **Not done (the API gives no dates):** the dashboard shows all confirmed scripts rather than those "confirmed this week" (backlog).

### D-065 · 2026-10-16 · Phase 6, part 1: backup, restore and the install guide
- **Built:**
  - `python -m app.cli backup [--out file.zip]` and `restore --archive file.zip [--force]` (`app/backup.py`, standard library only). A backup holds the database, copied with SQLite's online backup so it is safe while Margin runs, plus every stored file; logs and earlier backups are left out.
  - Restore refuses to overwrite existing data without `--force`, refuses a zip that is not a Margin backup, and refuses any path that would land outside the data folder.
  - `docs/INSTALL.md` for the school box.
- **Test failure investigated:** the first backup test failed on Windows with PermissionError. The test's own `with sqlite3.connect(...)` commits but does not close the connection, so the file stayed locked. The tests now use `closing()`.
- **Found for going live:** in production the session cookie is secure, so teachers on other computers need HTTPS. Two options are documented: a local HTTPS reverse proxy (a new program, awaiting owner approval), or `MARGIN_COOKIE_SECURE=false` on a trusted closed network.
- **Waiting for approval before building:** Docker images for the Compose setup, and the HTTPS proxy.
- **Demo seed** (`python -m app.cli seed-demo`, `app/demo.py`): a teacher `demo`, a class of six students, and a ready chemistry exam with its cover sheets prepared, all created through the normal audited services. It refuses to run twice or without an administrator.

### D-066 · 2026-10-16 · Phase 6, part 3: HTTPS with Caddy and Docker Compose
- **Decision (owner):**
  - Caddy 2.11.7 (Apache-2.0) provides HTTPS with its own local certificate (`tls internal`, `deploy/Caddyfile`). Margin listens on 127.0.0.1 only, and Caddy faces the network.
  - `docs/INSTALL.md` explains how to install Caddy's root certificate on each teacher computer (Windows, macOS, Android/ChromeOS, Firefox).
  - `MARGIN_COOKIE_SECURE=false` stays a documented fallback for a closed network only. It is off by default, refused unless `MARGIN_ALLOW_INSECURE_COOKIES_IN_PRODUCTION=true` is also set, and logged as a warning at every start (existing behaviour, D-040).
- **Docker** (approved images pinned exactly: `python:3.12.15-slim`, `node:22.23.3-slim`, `ollama/ollama:0.40.5`, `caddy:2.11.7`):
  - `Dockerfile`: the web app is built in the Node stage. The runtime installs Python packages from `backend/requirements.lock.txt` (exported from `uv.lock`, exact versions with hashes, `pip --require-hashes`) and runs as a non-root user.
  - `docker-compose.yml`: services `web`, `worker`, `ollama` and `caddy`, with named volumes for data, models and certificates. Compose refuses to start without `MARGIN_SITE`.
  - `backend/tests/test_deploy_files.py` checks the pins, their record in DEPENDENCIES and that the requirements match the lockfile.
  - The non-Docker install stays the main path in `docs/INSTALL.md`, because many school Windows laptops cannot run Docker.
- **Verified:** `docker compose config` validates the Compose file. **Not verified here:** building and running the images. The Docker engine is not running on the development machine. The first `docker compose up --build` on a school box is the test.
- **Test failures while writing the pin test:** test errors, all fixed. The word "latest" in a comment matched the check, which now looks for `:latest`. A regex had an escaping slip. DEPENDENCIES.md was not yet updated.
