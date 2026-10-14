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
- **Decision:** Every response carries `Content-Security-Policy: default-src 'self'` (plus related directives) and standard hardening headers. Swagger UI (`/api/docs`), which loads from a CDN, is enabled only when `MARGIN_ENV=development`.
- **Alternatives:** add headers at deployment time via a reverse proxy.
- **Reason:** non-negotiable "no external fonts, CDNs or third-party scripts" is then enforced by the browser, not only by convention.

### D-009 · 2026-10-14 · i18n with i18next / react-i18next, introduced in Phase 0
- **Decision:** Frontend strings go through i18next with `en.json` and `fr.json` from the first screen. A test asserts both locales have identical key sets. Backend errors will return stable codes for the frontend to translate (Phase 1).
- **Alternatives:** FormatJS/react-intl; Lingui; waiting until Phase 1.
- **Reason:** widely used, MIT, simple JSON catalogues that non-developers can translate. Even the Phase 0 placeholder has user-facing text, so the non-negotiable applies now.

### D-010 · 2026-10-14 · Keep `httpx` for the test client (pending owner decision)
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

Proposed for Phase 1 (detailed in `docs/PLAN.md`, confirmed when built): D-014 mark scheme validation rules, D-015 DB-backed sessions with per-session CSRF token, D-016 `Secure` cookie flag configurable and HTTPS on the LAN in Phase 6, D-017 subjects as TOML config files rather than a DB table.
