# End-to-end school workflow: implementation audit

Initial audit: 16 October 2026 against `591fa70`. The approved Windows build
is now implemented in the requested order. The original gap table below is kept
as the baseline, not a list of outstanding work.

| Item | Delivered commit / scope |
|---|---|
| 1 | `04957d1`: inbox routing, attention fixes, direct IPP and durable print queue |
| 2 | `a8d649d`: per-page QR sheets, spares, covers and labels |
| 3 | `2a85047`: local scheme drafts, GCE rules and school library |
| 4 | `918ff19`: automatic marking, restart checkpoints and review guards |
| 5 | `04cfbdf`: browser phone capture and colour-original preservation |
| 6 | `ff8ddd4`: release, private student portal, remarks, HOD and optional home host |
| 7 | `04aab5a`: confirmed class imports, Excel results and history |
| 8 | Final reliability commit: validated backup/restore, Windows scheduled backup, three-subject demo, private training statistics and deployment guides |

Acceptance still requires the school's Windows machine, actual SMB copier and
IPP printer, a cheap Android phone, and (for home access) its DNS/TLS/router.
Automated checks use mock AI; real handwriting accuracy is not established.
Legacy binary DOC/XLS need conversion to supported DOCX/XLSX/PDF/CSV; embedded
DOCX images need a PDF/image export. The experimental marks-only overprint onto
original sheets remains deferred as specified in the blueprint. Training exports
are anonymous aggregate correction/remark statistics, not raw images or OCR text.

## Build order and acceptance boundaries

| Order | Existing foundation | Work required |
|---|---|---|
| 1. Scan inbox and printing | Per-exam PDF upload, archived source, hash deduplication within an exam, QR cover splitting, unassigned-page tray, downloadable marked PDFs | School hardware settings; restricted SMB inbox provisioning; stable-file polling; PDF/JPEG/PNG/TIFF ingestion; global batch deduplication; mixed-exam routing; quarantine and actionable problems; absence records; notifications; feedback slips; durable IPP print queue, single/selected/all/unprinted in register order; test scan and test print with useful diagnostics. |
| 2. Answer sheets | Random checked QR tokens, cover-sheet PDF generation | Per-page token mapping, expected page counts, named answer sheets, spare sheets and confirmed identification, A4 label layouts, print instructions and direct printing. Preserve cover fallback. |
| 3. Schemes | Manual editing and CSV import, alternatives, basic totals/readiness checks | Local PDF/DOCX/image/text extraction; original alongside editor; explicit versioned confirmation; library; optional question paper; rejects, capped groups, M/A dependencies, ecf, meaning-based acceptance, teacher-only items; consistent question numbering and deterministic rule validation. Legacy binary Office formats require a separate converter. |
| 4. Automatic marking | Persistent jobs, heartbeat/stale-lock recovery, bounded retries, progress/ETA, confidence-based review, audited confirmation/reopening | Default-on eligible-script scheduling; page/problem eligibility instead of an exam-wide manual gate; restart-safe checkpoints for new jobs; teacher-only exclusion and confirmation guard; handwriting confidence; complete lifecycle labels. |
| 5. Phone capture | Image processing and review rotation primitives | Responsive browser camera, secure-context permissions, crop/straighten/clean preview, retake and multi-page intake through the same routing service. Retain colour originals separately from processing derivatives. |
| 6. Release, portal, remarks | Staff sessions, password hashing, CSRF, class-scoped staff access, audit infrastructure | Separate student authentication and sessions; code/one-time PIN setup/reset/slips/lockout; release/unrelease and visibility controls; school portal switch; own-record scans/overlays/progress; remark windows/limits/reasons/recalculation/replies; HOD role and escalation; notifications; permission tests on every route and file download; optional secure home access. |
| 7. Classes and results | Admin student editing, stable school student code, results matrix, question averages/zero counts, CSV export | Confirmed CSV/XLSX/pasted/photo imports, teacher-authorized roster changes, enrollment/term history, register positions, absent rather than zero, Excel report-card layout, printable results and student history. |
| 8. Phase 6 | Compose deployment, installation documentation and existing demo/export infrastructure | Revalidate fresh installation with all additions; nightly consistent local backup, retention and tested restore of database plus files; mock Chemistry/Mathematics/Economics demo; offline operation after installation; hardware and home-access troubleshooting. |

Primary evidence: `backend/app/db/models/{accounts,classes,exams,scans,ai,exports}.py`,
`backend/app/services/{uploads,splitting,cover_sheets,mark_scheme,mark_scheme_import,ai_marking,review,results,exports,students,access}.py`,
`backend/app/worker/runner.py`, staff authentication and security headers,
`frontend/src/routes/`, `deploy/Caddyfile`, and `docs/INSTALL.md`.

## Rules applying across stages

- Lifecycle: awaiting scan, scanned, needs attention when blocked, marking, ready
  for review, confirmed, released. Printing is independent; an unresolved remark
  is an additional visible status. Absence never produces a zero mark.
- Shuffled plain pages cannot be identified by a QR on a different cover page.
  Cover-sheet mode requires ordered student stacks. Full arbitrary ordering is
  available with the per-page codes introduced in stage 2.
- Original files and colour page images remain immutable audit evidence. Crops,
  rotation, cleanup and marking overlays are derivatives. Mixed-exam batches need
  a new intake model: today's upload requires one exam and one staff uploader.
- Duplicate whole files, duplicate page tokens and legitimate rescans are distinct
  cases. Missing-page issues reconcile as later pages arrive. Removing a batch
  containing confirmed scripts is blocked.
- Rules such as any-N groups and method dependencies must be applied in the score
  calculation, teacher review, exports, remarks and student view, not just prompts.
  Scheme versions used for marking must remain reproducible.
- Never equate printer acceptance with physical printing. Poll IPP completion;
  report uncertainty if the device cannot confirm. Reconcile an interrupted
  submission before retrying to avoid duplicate output.
- Released mark changes invalidate stale generated output and pending print
  content. Audit actor, old/new values and reason; preserve already-printed history.
- Named sheets and register/spare-name recognition extend the older brief's
  pseudonymous-paper policy. Names remain local; identification is separate from
  grading inputs and anonymised training exports.
- Local training remains opt-in and includes eligible teacher corrections and
  remark outcomes. No automatic transfer. All new visible strings need EN/FR.
- Server permissions must explicitly distinguish admin, HOD, teacher and student;
  adding another value to today's two-role enum is insufficient. Test cross-school,
  cross-class and cross-student access, including images, exports and guessed IDs.

## Approved dependency proposal

Reuse the existing PDFium, Pillow, ReportLab, Segno, ZXing, local Ollama and durable
job queue. Use standard-library polling rather than adding a watcher. Browser
capture requires no JavaScript package. Begin image correction with existing
Pillow and QR geometry, with a teacher-adjustable crop for uncertain detections.

| Addition | Version / licence | Purpose and new dependencies |
|---|---|---|
| openpyxl | 3.1.5 / MIT | XLSX roster import and report-card export; et-xmlfile 2.0.0 / MIT. |
| python-docx | 1.2.0 / MIT | DOCX scheme extraction; lxml 6.1.3 / BSD-3-Clause, existing typing-extensions. lxml wheels also include libxml2/libxslt (MIT); inspect platform wheel notices before locking. No optional lxml extras. |
| defusedxml | 0.7.1 / PSF | Harden XML handling for imported Office documents; no new Python dependencies. |
| SMB service | School OS dependent | Windows can use its native SMB service. Linux needs Samba (GPL-3.0-or-later), requiring an explicit exception for this separately installed system service under the project's permissive-only policy. Restricted copier credentials and LAN-only access. |
| CUPS print service/client tools | School OS dependent; modern CUPS is Apache-2.0 | Local IPP submission and job status. Avoid a new Python IPP dependency. OS package version and dependency inventory must be fixed for the selected installation target; Windows needs a documented supported local print-service arrangement. |
| Optional LibreOffice headless | School OS dependent; MPL-2.0/LGPL-3.0+ | Legacy binary .doc/.xls conversion, separately installed and sandboxed. Needs an explicit system-program licence exception and platform package inventory. Without this option, document support is PDF/DOCX/images/text/CSV and spreadsheet support is XLSX/CSV. |

At audit time, package metadata was inspected without installing anything. System versions and
transitive OS packages cannot be honestly pinned until the school installation OS
is chosen. Do not interpret this table as approval for arbitrary package additions.
No OpenCV, NumPy, cloud OCR, external AI, SMS or email service is proposed.

## Student access from home

Recommended: keep the application, database, files and model on the school box;
publish only student routes through a separate HTTPS hostname using the existing
Caddy deployment. Require publicly trusted TLS, explicit student-route allowlisting,
short sessions, account/IP throttling, secure PIN onboarding/reset, and the same
release and own-record guards as LAN access. Staff routes, SMB, IPP, database and
model ports stay private. Account for reverse-proxy trust and CSRF in tests.

This changes “no data leaves the school network”: an authenticated student's own
released work travels encrypted to their home browser. It does not require external
AI or third-party storage. The school needs working internet, a domain and inbound
reachability. Behind CGNAT, an ISP change, managed VPN or relay is necessary;
third-party relays are not assumed approved. Do not expose the current LAN-only
Caddy configuration unchanged. LAN access continues when the internet is down.

## Verification and documentation required for each implementation commit

Run `python scripts/check.py`, inspect every result, and commit each completed
build-order item. Make cloud browser/proxy configuration explicit so the actual
check entry point works here as well as on the school machine. New tests cover
stable-file intake, mixed routing, malicious/oversized files, dedupe, missing pages,
crash recovery, print reconciliation, scheme rules, teacher-only confirmation,
release visibility, student isolation, PIN lockout, remark limits/escalation,
result recalculation, export invalidation, enrollment history and backup restore.

Update README and installation guides alongside working features. Clearly separate
currently available functions from planned ones. Provide ordered installation,
first school/account setup, scanner credentials/destination/test, printer setup/test,
teacher workflow, student onboarding, optional home HTTPS, upgrades, backup/restore,
troubleshooting, and real hardware acceptance steps. No credentials in examples
should become deployment defaults.

Software tests cannot verify a real photocopier's SMB dialect, file-write behaviour,
ADF page handling, QR legibility, printer duplex/trays/status fidelity, school router
reachability or camera quality on the school's cheapest phone. Record these as
installation acceptance checks, not as automated-test passes.

The initial audit installed nothing. Each implementation commit subsequently ran
the complete check suite; see DECISIONS.md for failures investigated and corrected.

Windows implementation uses native SMB and direct IPP from the standard library;
Samba and CUPS are not required or installed on that target. No new Python package
is required for the first build item. The approved Office packages are reserved
for their import/export build items.
