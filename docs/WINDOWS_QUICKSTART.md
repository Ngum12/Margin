# Windows quick start

Margin is an on-premise exam-marking assistant for schools. It reads handwritten
scripts with a local model, proposes marks against a teacher-confirmed scheme,
and leaves every final mark to the teacher. The interface is available in English
and French. **Windows is the primary school installation path.**

After an exam: **Scan on the photocopier → review in Margin → Print**. Uploads and
PDF downloads remain fallbacks. Student results stay private until the teacher
releases them. Optional home access serves each student's own released work over
HTTPS from the school box; storage and AI never move to a third-party service.

![Margin marking desk](images/marking-desk.png)

*The screenshot uses synthetic demonstration data.*

## 1. Install once on the school Windows computer

Use a dedicated Windows account and a local SSD. A practical starting point is
16 GB RAM, with enough disk space for the model, scans and backups. A GPU improves
marking speed. Install Git, Python 3.12, uv, Node.js/npm, and—when using real AI—
Ollama. Caddy provides HTTPS for school-network and optional home access.
Approved versions and licences are in [DEPENDENCIES](DEPENDENCIES.md).

Open **PowerShell**. These installation commands need internet access once:

```powershell
git clone https://github.com/Ngum12/Margin.git
Set-Location Margin
Copy-Item .env.example .env
$env:UV_PYTHON_PREFERENCE = "only-managed"
uv python install 3.12
Set-Location backend
uv sync --frozen
Set-Location ..\frontend
npm ci
npm run build
Set-Location ..
```

Choose one mode in the new `.env` file:

| Purpose | Settings |
|---|---|
| Demonstration on this computer, without a GPU | `MARGIN_ENV=development`, `MARGIN_AI_BACKEND=mock` |
| Real school use | `MARGIN_ENV=production`, `MARGIN_AI_BACKEND=ollama`, `MARGIN_HOST=127.0.0.1` |

For real AI, install the local model once:

```powershell
ollama pull qwen3-vl:4b-instruct
```

Keep `MARGIN_MODEL_BASE_URL=http://127.0.0.1:11434` when Ollama is on the same
computer. Production requires HTTPS and secure cookies. Follow the
[HTTPS installation guide](INSTALL.md#sign-in-over-the-school-network-https-with-caddy)
before signing in from another computer. No public AI API key is required.

Create the school and administrator; the commands prompt privately for passwords:

```powershell
Set-Location backend
uv run python -m app.cli migrate
uv run python -m app.cli init-school --name "Your School" --country Cameroon
uv run python -m app.cli create-user --username admin --display-name "Administrator" --role admin
Set-Location ..
python scripts/run.py
```

Keep the launcher running: it starts **both the web app and background worker**.
Run only one launcher/worker for the school database. On the same computer in
demonstration mode, open `http://127.0.0.1:8000`. In production, open the HTTPS
school address configured in Caddy. Startup uses the installed packages offline;
updates and dependency installation are separate administrator actions.

## 2. Connect the photocopier and printer

Follow [Windows school setup](WINDOWS_SCHOOL_SETUP.md) in order:

1. In Settings, create the scan inbox. Run the supplied Windows SMB setup script
   with a dedicated copier account and add the share as a copier shortcut named
   **Margin**. Send a test scan and check its arrival in Settings.
2. Enter the printer's private IP/IPP address, choose A4 and duplex defaults, and
   print a test page. The printer must support direct PDF over IPP.
3. Test a small shuffled, rotated, mixed-exam pile before using a whole class.

QR answer sheets identify each page independently. Cover-sheet fallback stacks
must stay together because their plain answer pages do not have page QR codes.
Original scans are archived; unreadable files are quarantined with a reason.

## 3. Teachers: class → exam → return

1. **Class registers:** import XLSX/CSV (`Name` or `Nom`, optional `Code`), paste
   one name per line, or select a register photo/PDF for local reading. Edit the
   preview and confirm it. An existing student code preserves the same record;
   blank codes create new records. Similar names never merge automatically.
2. Arrange register order with the up/down buttons. Remove/restore students
   without losing history. Exam membership is preserved once scanning starts.
3. **New exam:** choose the subject and class. Import a scheme from PDF, DOCX,
   photo/scan, pasted text or CSV. Compare the original and editable scheme, fix
   highlighted problems, and confirm it. Reuse confirmed schemes from the school
   library. Accepted alternatives, reject lists, any-N groups, M/A dependencies,
   ecf and teacher-only items are supported.
4. **Answer sheets:** print named per-page QR sheets, spare sheets, cover sheets
   or A4 sticker labels. QR codes contain random checked tokens, not personal
   details. Set the number of pages per student.
5. **After the exam:** scan to **Margin**. Alternatively, open **Phone capture**
   on school Wi-Fi, check the crop/straightening preview and accept it. Resolve
   missing/unreadable/duplicate pages and match spare sheets. Record absences.
6. Marking starts automatically by default when the scheme and pages are ready.
   The background queue resumes completed page/question work after interruption.
   Review the least-confident scripts first; teacher-only items need a human mark.
7. **Confirm marks**, then **Print** or **Print all confirmed**. The default is
   original papers plus one feedback slip per student. Full marked reprints,
   selected students and not-yet-printed copies are available. Class output follows
   the saved register order. Check uncertain jobs physically before retrying.
8. **Results:** inspect question averages and zero-score shares, print the table,
   set the term and export report-card Excel. Absent/unconfirmed totals stay blank.
   Student history is available from the register.

Legacy binary `.doc` and `.xls` need conversion to DOCX/XLSX or PDF/CSV before
import. Embedded images inside DOCX are not OCRed; submit their pages as PDF or
photos. Long or doubtful model extractions remain editable drafts. Photo capture
handles crop, rotation and modest skew; retake blurred or strongly distorted pages.

## 4. Students and home access

Admins enable **Settings → Student portal**. Teachers print private code/initial-PIN
slips from **Student sign-in slips**; students choose their own PIN at first sign-in.
Forgotten PINs can be reset, revoking existing sessions. Shared-computer sessions
expire after inactivity. There is a visible sign-out button.

**Confirmation does not publish results.** Use **Results → Release results** after
the class is confirmed or absent. Choose marks only, marks and notes (default), or
marks, notes and scheme. Unrelease blocks further student access. Students see only
their own released pages, marks, feedback and progress; no rankings are shown.

Students can request a question remark within the school window (default 7 days,
maximum 3 questions per exam), select a page/location and write up to 500 characters.
Teachers reply at the marking desk. Changes update totals and invalidate old print
versions. Optional department heads handle one escalation, scoped by subject.
Notifications stay inside Margin.

For home internet access, follow
[the public student-host instructions](WINDOWS_SCHOOL_SETUP.md#optional-student-access-from-home).
The school needs DNS, a reachable public IP/router and a trusted HTTPS certificate.
Only student routes are public; staff, SMB, IPP and model ports stay private.

## 5. Back up nightly and rehearse restore

Use a separate encrypted disk/location. To run a backup manually:

```powershell
Set-Location backend
uv run python -m app.cli backup --out E:\MarginBackups\manual.zip
```

From the repository root, register the nightly Windows task once in elevated
PowerShell under the school's Margin Windows account:

```powershell
.\scripts\windows-install-backup-task.ps1 -BackupDirectory E:\MarginBackups
```

The task runs at 02:00, keeps 30 days, and prunes only after a successful backup.
Test it in Task Scheduler and check **Last Run Result = 0**. Keep an offline copy.
Backups include a SQLite snapshot and checksummed stored files. In-progress copier
inbox files and logs are excluded; finish importing the pile before the nightly run.

To restore, **stop Margin and its worker first**. From `backend`:

```powershell
uv run python -m app.cli restore --archive E:\MarginBackups\manual.zip --force
```

Restore validates paths, checksums and database integrity before replacing data.
It keeps the previous directory beside the restored one as `data.before-restore-*`.
Start Margin, check a known script and its marks, and print a test slip. Restore
uses the standard data directory containing `margin.db`. Keep `.env`, Caddy's
configuration/certificate storage and the Ollama model separately; they are not
in the application-data backup. See [the restore checklist](INSTALL.md#6-backups-and-restore).

## 6. Demonstrate and verify

In demonstration mode (`development` + `mock`), run once from `backend`:

```powershell
uv run python -m app.cli seed-demo
```

This creates the `demo` teacher, six fictional students and ready Chemistry,
Mathematics and Economics exams. Mock results are labelled and do not represent
real handwriting recognition or marking accuracy. No GPU is needed for this flow.

For developers, run **all checks** from the repository root:

```powershell
python scripts/check.py
```

This runs Python formatting/lint/types/tests, licence notices, frontend
formatting/lint/types/tests/build and browser tests. Browser checks use installed
Edge; `MARGIN_BROWSER_PATH` can select another installed Chromium browser.

## Privacy and deployment notes

- School-local storage and inference; bundled fonts/assets; no telemetry or external AI.
- Teacher changes, confirmations, imports, printing and deletions are audited.
- School training opt-in and individual consent are off by default. Local correction
  records support future school-side learning. Export contains anonymous correction
  statistics only, suppressing groups below five students; handwriting, names,
  identifiers and free text are excluded. Nothing is sent automatically. Legacy
  training archives are blocked from download.
- Windows SMB/Task Scheduler, copier feeding, IPP job completion/duplex, cheap Android
  cameras and public DNS/TLS/router access require acceptance tests at the school.
  Automated checks in this workspace do not establish real model accuracy or prove
  physical printer completion.

More: [Windows setup](WINDOWS_SCHOOL_SETUP.md) · [Installation](INSTALL.md) ·
[Blueprint audit](BLUEPRINT_AUDIT.md) · [Decisions](DECISIONS.md) ·
[Architecture and rules](../CLAUDE.md) · [Dependencies](DEPENDENCIES.md).
