# Backlog

Ideas and features deliberately not built yet. Add here instead of expanding scope. Brief section 4 items are out of scope for the first build.

## Out of scope for the first build (brief section 4)
- Student or parent portals and logins
- Payments, billing, multi-school cloud hosting
- Model fine-tuning pipelines (this build only exports the dataset)
- Mobile apps
- Automatic segmentation of handwriting into question regions with trained detectors
- Analytics beyond the class results table

## Candidates
- Half marks in mark schemes (v1 uses whole marks only).
- Structured-text mark scheme import format in addition to CSV.
- Switch test client to `httpx2` when approved (see D-010).
- Native-speaker review of French translations; track draft strings in `docs/TRANSLATIONS.md`.
- Install `make` on Windows dev machines, or document `winget install GnuWin32.Make` (optional; `python scripts/check.py` is equivalent).
- Licence audit script that fails `check` if a new dependency has a non-permissive licence.
