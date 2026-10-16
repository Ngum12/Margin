# Dependencies and licences

Policy: permissive licences only (MIT, BSD, Apache-2.0, ISC or similar). No GPL/AGPL. **No PyMuPDF.** Every direct dependency is listed here with its licence, checked from the installed package metadata. Update this file in the same change that adds or upgrades a dependency.

Last audited: 2026-10-14 (Phase 2). Full licence texts of everything shipped: `THIRD_PARTY_NOTICES.md`.

## Backend runtime (`backend/pyproject.toml`)

| Package | Version | Licence | Purpose |
|---|---|---|---|
| fastapi | 0.143.0 | MIT | Web framework |
| uvicorn | 0.54.0 | BSD-3-Clause | ASGI server |
| pydantic | 2.14.1 | MIT | Validation and schemas |
| pydantic-settings | 2.15.0 | MIT | Configuration from env / `.env` |
| sqlalchemy | 2.1.4 | MIT | ORM / database access (Phase 1, approved 2026-10-14) |
| alembic | 1.20.0 | MIT | Database migrations (Phase 1, approved 2026-10-14) |
| argon2-cffi | 25.1.0 | MIT | Argon2id password hashing (Phase 1, approved 2026-10-14) |
| pypdfium2 | 5.14.0 | Apache-2.0 / BSD-3-Clause; bundles PDFium and its libraries (notices in THIRD_PARTY_NOTICES.md) | Render uploaded PDFs (Phase 2) |
| reportlab | 5.0.1 | BSD (ReportLab open-source licence) | Cover sheet PDFs; later marked PDFs (Phase 2) |
| segno | 1.6.6 | BSD-3-Clause | QR code generation (Phase 2) |
| zxing-cpp | 3.1.1 | Apache-2.0 | QR code reading (Phase 2) |
| pillow | 12.3.0 | MIT-CMU; bundles image libraries (notices in THIRD_PARTY_NOTICES.md) | Images (Phase 2) |

Notable transitive runtime packages: starlette 1.8.0 (BSD-3), anyio (MIT), h11 (MIT), click (BSD-3), python-dotenv (BSD-3), typing-extensions (PSF-2.0), annotated-doc / annotated-types / typing-inspection (MIT). Phase 1 transitive: mako 1.4.3 (MIT) and markupsafe 3.0.4 (BSD-3) via alembic; argon2-cffi-bindings 26.1.0 (MIT), cffi 2.1.1 (MIT-0), pycparser 3.11 (BSD-3) via argon2-cffi. Phase 2 transitive: charset-normalizer 3.5.2 (MIT) via reportlab. **opentelemetry-api 1.45.1 (Apache-2.0)**: required by FastAPI; API only, no exporter installed, FastAPI telemetry explicitly disabled (D-013).

## Backend development only

| Package | Version | Licence | Purpose |
|---|---|---|---|
| ruff | 0.17.0 | MIT | Formatter and linter |
| mypy | 2.4.0 | MIT | Type checker |
| pytest | 9.1.1 | MIT | Tests |
| httpx | 0.28.1 | BSD-3-Clause | FastAPI TestClient transport (D-010) |

Dev transitive: certifi (MPL-2.0, data file, via httpx), pathspec (MPL-2.0, via mypy). MPL-2.0 is weak file-level copyleft; acceptable for unmodified dev tools that are not shipped.

## Frontend runtime (bundled into `frontend/dist`)

| Package | Version | Licence | Purpose |
|---|---|---|---|
| react | 19.3.0 | MIT | UI |
| react-dom | 19.3.0 | MIT | UI |
| i18next | 26.4.4 | MIT | Internationalisation |
| react-i18next | 17.0.16 | MIT | React bindings for i18next |
| react-router | 8.4.0 | MIT | Client-side routing (Phase 1, approved 2026-10-14) |

Transitive runtime: scheduler, use-sync-external-store, @babel/runtime, html-parse-stringify, cookie-es 3.1.1, @remix-run/route-pattern 0.22.1 (all MIT). All shipped code is MIT.

## Frontend development only

| Package | Version | Licence |
|---|---|---|
| vite | 8.3.4 | MIT |
| @vitejs/plugin-react | 6.1.2 | MIT |
| typescript | 6.0.3 | Apache-2.0 |
| @types/react, @types/react-dom | 19.3.0 | MIT |
| @types/node | 26.6.5 | MIT |
| eslint | 10.12.0 | MIT |
| @eslint/js | 10.0.1 | MIT |
| typescript-eslint | 8.71.2 | MIT |
| eslint-plugin-react-hooks | 7.1.1 | MIT |
| eslint-plugin-react-refresh | 0.5.7 | MIT |
| globals | 17.13.0 | MIT |
| prettier | 3.9.10 | MIT |
| vitest | 5.0.4 | MIT |
| jsdom | 30.1.2 | MIT |
| @testing-library/react | 16.3.3 | MIT |
| @testing-library/jest-dom | 7.0.1 | MIT |
| @testing-library/user-event | 14.6.8 | MIT |

Dev transitive licences (from `package-lock.json`): MIT 203, Apache-2.0 18, ISC 11, BSD-2 8, BSD-3 3, MIT-0 2, CC0 1, BlueOak-1.0.0 4 (lru-cache, minimatch; permissive), CC-BY-4.0 1 (caniuse-lite data), MPL-2.0 12 (lightningcss and its platform binaries, CSS tooling used by Vite at build time; not shipped).

## Tooling (not shipped)
- uv 0.12.x (MIT/Apache-2.0): Python environment and lockfile.
- Node.js 24 / npm: frontend build.

## Planned
- **Phase 2:** installed as approved. python-multipart was approved but not needed (D-027) and has been removed from the approved list (owner, 2026-10-14); adding it later needs a new approval.
- **Phase 3:** `httpx` stays dev-only (D-037); the runtime approval was dropped by the owner (2026-10-14). No new packages.
- **Phase 4** (approved 2026-10-14): `@playwright/test` 1.64.1, dev only, Apache-2.0; transitive `playwright` and `playwright-core` 1.64.1 (Apache-2.0); no install scripts. Tests drive the installed Microsoft Edge (`channel: "msedge"`), so no browser download. The lockfile also lists `fsevents` 2.3.3 (MIT) as an optional, macOS-only dependency of `playwright`; it is never installed on Windows or Linux. Approved by the owner on 2026-10-15.

## Bundled font files (Phase 5, approved by the owner 2026-10-15)

| Font | Version | Licence | Files | Source | Purpose |
|---|---|---|---|---|---|
| Noto Sans | 2.013 | SIL Open Font License 1.1 | `NotoSans-Regular.ttf`, `NotoSans-Bold.ttf` | github.com/notofonts/latin-greek-cyrillic, release `NotoSans-v2.013` (hinted TTF) | Text in marked PDFs, all French characters |
| Noto Sans Symbols 2 | 2.008 | SIL Open Font License 1.1 | `NotoSansSymbols2-Regular.ttf` | github.com/notofonts/symbols, release `NotoSansSymbols2-v2.008` (hinted TTF) | ✓ and ✗ in marked PDFs |
| Caveat | googlefonts/caveat commit 59745e8 | SIL Open Font License 1.1 | `Caveat-Regular.ttf` (backend for PDFs, frontend for the screen) | github.com/googlefonts/caveat, `fonts/ttf` at commit 59745e818ef7973e11e70cb1358d0e902b56c5fc (no packaged releases) | Red pen handwriting: comments, scores, total (approved 2026-10-15). SHA-256 `7af58d70e539c9195cc328617a68c9961ed804a4404b0b818989ba7c013e8776` |

- Stored in `backend/app/exports/fonts/` with their licence texts and SHA-256 checksums (`fonts.json`). A test checks the files against the checksums.
- Before use, both ✓ (U+2713) and ✗ (U+2717) were checked to render. Noto Sans does not contain them; Noto Sans Symbols 2 does.
- Embedded through ReportLab's built-in TrueType support: no new Python package.
- Listed in `THIRD_PARTY_NOTICES.md` by `scripts/third_party_notices.py`.

## Bundled web fonts and icons (UI redesign, requested by the owner 2026-10-16)

The owner's redesign brief asked for these, bundled locally with their licences. No package was added. The files are copied into `frontend/src/assets/` and listed with SHA-256 checksums in `frontend/src/assets/assets.json`; `backend/tests/test_web_assets.py` checks them.

| Asset | Version | Licence | Files | Source | Purpose |
|---|---|---|---|---|---|
| Literata | 3.103 | SIL Open Font License 1.1 | `Literata-SemiBold.woff2` | github.com/googlefonts/literata, release `3.103` (`3.103.zip`, `fonts/webfonts`) | Page titles, exam titles, student names |
| Atkinson Hyperlegible Next | googlefonts/atkinson-hyperlegible-next commit 7925f50 | SIL Open Font License 1.1 | `AtkinsonHyperlegibleNext-Variable.woff2` (variable weight) | github.com/googlefonts/atkinson-hyperlegible-next, `fonts/webfonts/AtkinsonHyperlegibleNext[wght].woff2` at commit 7925f50f649b3813257faf2f4c0b381011f434f1 (no packaged releases) | All interface text, tables and numbers |
| Noto Sans (web fallback) | 2.013 | SIL Open Font License 1.1 | `NotoSans-Regular.ttf` (same file as the PDF font) | as the PDF font above | Glyphs the interface font lacks; downloaded only when needed |
| Caveat (web) | googlefonts/caveat commit 59745e8 | SIL Open Font License 1.1 | `Caveat-Regular.ttf` (already bundled) | as above | Red-pen annotations on screen |
| Lucide icons | 1.58.0 | ISC (icons derived from Feather: MIT) | 34 icons copied as SVG path data into `src/components/icons.ts`; licence in `assets/icons/LICENSE-lucide.txt` | github.com/lucide-icons/lucide, `icons/*.svg` at tag `1.58.0` | Navigation and tool icons, used sparingly |

- They are downloaded once from the official repositories above, and only the files listed are kept.
- `scripts/third_party_notices.py` lists them in `THIRD_PARTY_NOTICES.md` from the manifest.

## Deployment: container images and HTTPS (Phase 6, approved by the owner 2026-10-16)

| Item | Version (exact) | Licence | Purpose | Notes |
|---|---|---|---|---|
| `python:3.12.15-slim` | 3.12.15 on Debian slim | PSF-2.0 (Python); Debian packages under their free licences | Runtime image for the web app and worker | Python packages are installed from `backend/requirements.lock.txt` (exported from `uv.lock`, exact versions with hashes, `pip --require-hashes`) |
| `node:22.23.3-slim` | 22.23.3 | MIT (Node.js) | Build stage only: builds the web app; not in the final image | `npm ci --ignore-scripts` from `package-lock.json` |
| `ollama/ollama:0.40.5` | 0.40.5 | MIT | Local AI model server in Docker Compose | Models are pulled on the school box (`qwen3-vl:4b-instruct`) |
| `caddy:2.11.7` | 2.11.7 | Apache-2.0 | HTTPS on the school network with its own local certificate authority (`tls internal`) | Also used without Docker: the official `caddy_2.11.7_windows_amd64.zip` / `linux_amd64.tar.gz` release from github.com/caddyserver/caddy |

- Pins are checked by `backend/tests/test_deploy_files.py`: no `latest`, the same versions as this table, and `requirements.lock.txt` matching `uv.lock`.
- After any backend dependency change, regenerate with `cd backend && uv export --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.lock.txt`.

## Blueprint document import (approved 2026-10-16)

| Package | Version | Licence | Purpose / dependencies |
|---|---|---|---|
| python-docx | 1.2.0 | MIT | Read DOCX locally; lxml and existing typing-extensions |
| lxml | 6.1.3 | BSD-3-Clause | Office XML; bundled libxml2/libxslt MIT notices retained in wheel |
| defusedxml | 0.7.1 | PSF-2.0 | Reject entities and DTDs before DOCX parsing; no dependencies |

No external Office/OCR service. Legacy binary DOC conversion requires separately
installed LibreOffice; it is not installed by Python package setup.

## Approved register and report-card packages (2026-10-16)

Owner-approved with the blueprint: openpyxl **3.1.5** (MIT), and its pinned dependency
et-xmlfile **2.0.0** (MIT). XLSX import/export only; no macros, external links or
formulas are accepted during register import. Existing defusedxml guards XML parsing.
