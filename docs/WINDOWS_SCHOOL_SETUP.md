# Windows school setup

Windows is the owner's selected school deployment target (16 October 2026).
Use a supported Windows edition and a dedicated school computer with an SSD,
reliable power and enough disk space for original scans and local backups.
Follow [INSTALL.md](INSTALL.md) for Python/Node/Ollama, the local model, application
installation, first administrator, HTTPS and starting the app and worker.
Do not use mock marking for real exams. Keep one worker process running.

## Copier: configure once

1. Sign in as administrator. Open **Settings → Scanner and printer**. Copy the
   absolute scan inbox path. The application creates this directory.
2. Open PowerShell **as administrator** on the school box. From the repository:

   ```powershell
   .\scripts\setup-scan-share.ps1 -InboxPath "C:\MarginData\scan-inbox\1"
   ```

   Replace the example with the actual path. The script creates a dedicated local
   scanner account, prompts securely for its password, grants access to this inbox
   only, and permits SMB from the local subnet on Private/Domain network profiles.
   It preserves existing accounts and refuses a conflicting share. It does not
   grant access to the database, archive, model or backups.
3. On the copier, add an SMB2/SMB3 destination named **Margin**. Use the printed
   UNC path (`\\SCHOOL-BOX\Margin`), account (`SCHOOL-BOX\MarginScanner`) and the
   password just set. A reserved LAN IP is preferable where hostname lookup fails.
   Keep that password in the school's password manager and update the copier if it
   changes. Do not use the administrator's account or enable guest/SMB1 access.
4. In Settings enable **Watch the scan inbox**, then **Save settings**.
5. Choose **Send test scan**, then scan a fresh page at the copier. The status
   changes only when a new file is archived by the worker. A page without a known
   QR goes to the administrator's attention list; it still verifies delivery.

Accepted: PDF, JPEG, PNG and TIFF (including multipage TIFF). The worker observes
unchanged size and modification time for at least five seconds, verifies the copy
again, and archives the original before removing the inbox file. Configure the
copier to rename its temporary file to its final name only after writing finishes
where supported. A copier that pauses for long periods must be tested at installation.
Exact duplicates do not create another batch. Unreadable files are quarantined.
Oversized files remain in the inbox with a Settings warning; split them into batches.

If no scan arrives: check the worker is running, the school box is awake, the
destination/password are correct, both devices are on the school network, the
network profile is Private/Domain, and Windows Firewall allows local SMB.
Do not open port 445 on the internet router. Never share the whole data directory.

## Printer: configure once

1. Obtain the printer's LAN IPv4 address and IPP path from its configuration page.
   Reserve the address in the school router. A typical URI is
   `ipp://192.168.1.50:631/ipp/print`; paths differ by manufacturer.
2. Enter this URI in Settings. Select duplex or single-sided; the paper size is A4.
   Save, then **Check connection**. The printer must advertise native PDF support
   over IPP. For `ipps://`, its certificate must be trusted by the school box.
3. Choose **Print test page**, and check the physical output and the queue status.
   A successful connection alone does not prove that paper printed.

The Windows app talks IPP directly using the Python standard library. It needs
neither Samba nor a Python printing package. CUPS is not installed on Windows.
An older printer without IPP/PDF needs a compatible school-local print server or
the existing PDF download/Windows print fallback. Do not assume all printers
accept PDF just because they advertise IPP; Settings checks this capability.

## Teacher workflow currently implemented

- Prepare an exam, then open **Answer sheets**. Choose the number of pages per
  student and any spare sheets. Print directly, or prepare a PDF as a fallback.
  Each answer page has its own anonymous QR, student identification and page number.
  Pages can be shuffled or rotated; QR tokens route them to the correct exam/student.
- Spares have a Name line. The local model may suggest a student, but the teacher
  must confirm the student and physical page number. Missing numbered pages and
  duplicates remain blocked from marking/confirmation until resolved.
- A4 stickers use 40-label stock, 45.7 × 25.4 mm (4 columns × 10 rows), with
  9.85 mm side margins and 21.5 mm top/bottom margins. Print at 100% and test alignment
  on plain paper first. Place labels upright at the top of the answer page. Labels
  use student codes; the default answer sheets show names.
- In **cover-sheet mode**, keep each student's cover and plain answers together.
  Different exams may appear in one scan, but plain pages must follow their cover.
  Use the default per-page QR sheets for arbitrary page order.
- Scan to **Margin**. Recognised stacks appear in their exams automatically.
  The dashboard lists pages needing attention. Administrators assign pages with
  no identifiable exam; teachers can resolve pages already scoped to their exams.
- Review and confirm using the existing marking desk. Results and confirmed
  scripts offer feedback slips or full marked reprints, sent to the configured
  printer. Class printing uses student creation order until explicit register
  ordering is introduced with roster imports.
- **Print not yet printed** excludes only versions whose printer reported
  completion. A new confirmation after editing is eligible to print again.

Queue meanings: **Queued**, **Sending**, **Sent to printer**, **Printed**,
**Failed**, and **Check printer output**. A lost response or interrupted sending
does not cause an automatic duplicate. Check the physical output before selecting
the acknowledgement and retrying. Printer cancellation can leave partial output.
Restart recovery can take two minutes before an interrupted submission is shown
as uncertain. Failed jobs caused by changed marks require a fresh print request.

## Internet access and remaining build items

The student portal and public student HTTPS hostname are not implemented yet.
Do not forward the current application directly to the internet. Keep SMB, IPP,
Ollama, database and staff access private. The planned home portal will still
store data and run models at school; it requires a domain, trusted TLS and inbound
connectivity. An ISP using CGNAT needs a separate connectivity solution.

See [BLUEPRINT_AUDIT.md](BLUEPRINT_AUDIT.md) for the remaining implementation order.
Do not treat this guide as evidence of a real-device acceptance test. Verify
large ADF batches, duplex orientation, interrupted writes, QR readability,
printer completion reporting and power-cut recovery with the school's equipment.

Feedback slips, blank answer sheets and labels print single-sided. Full marked
reprints can use duplex; Margin pads odd-length scripts with a blank reverse so
two students never share one physical sheet. Inspect paper handling on the actual
printer during installation.

## Phone fallback

On school Wi-Fi, open the same Margin address and choose **Photograph scripts**.
Use the phone's browser camera/photo chooser; there is no app to install. For the
HTTPS installation, first trust the school's local certificate on that phone as
explained in INSTALL.md. Hold the camera above the paper, keep the QR and all four
corners visible, and avoid shadows. Compare the prepared page with the original,
adjust cropping if needed and press **Use this page**. Test this on the school's
lowest-cost Android phone; a desktop browser test cannot verify camera quality.

## Optional student access from home

The portal is disabled initially. Enable it in **Settings → Student portal**. Teachers
print private code/PIN slips from **Student sign-in slips**. Each initial PIN must be
changed before any work is visible. Confirming a script is not publication: use
**Results → Release results** after confirming the class and recording absences.

For home access, the school needs a domain, a reachable public IP (not carrier-grade
NAT), reliable power/internet, and a maintained HTTPS endpoint. Data and AI remain
on the school box; released work travels encrypted to the authenticated student's
browser. No hosted relay, external AI, SMS or email is used.

1. Set the domain's DNS to the school's public IP. Forward **TCP 443 only** to Caddy
   on the school box. Use an existing certificate or Caddy's HTTPS certificate
   issuance; Caddy needs outbound access to its certificate authority for renewal.
2. Add the site block in `deploy/Caddyfile.student` to the Caddy configuration. Set
   `MARGIN_STUDENT_SITE=students.your-school.example` in Caddy's environment and
   `MARGIN_STUDENT_PUBLIC_HOST=students.your-school.example` in Margin's `.env`.
3. Keep the app bound to `127.0.0.1:8000` behind Caddy and secure cookies enabled.
   Do not forward SMB 445, IPP 631, Ollama 11434, the app port, or the staff hostname.
4. Restart the app and Caddy. From an external phone connection, check the trusted
   certificate, initial-PIN change, own released pages, sign-out and timeouts.
   `/api/classes`, `/api/auth/login` and `/settings` on the public hostname must
   return 404. LAN staff sign-in should still work on its private hostname.
5. Check that unrelease immediately blocks new student requests and that a PIN
   reset revokes existing sessions. Test with two different student accounts.

Domain/router/certificate setup is school-specific and has not been performed in
this cloud workspace. Keep LAN-only access until those external checks pass.
Private PIN PDFs are sensitive credentials: protect the data directory and backups
with Windows account permissions and BitLocker; hand slips directly to students.
