# Deployment

Windows school installation: [Windows setup](../docs/WINDOWS_SCHOOL_SETUP.md) and
[installation/restore guide](../docs/INSTALL.md). The app and worker are started by
`python scripts/run.py`; use one launcher per database. Nightly Windows backup task:
`scripts/windows-install-backup-task.ps1`.

Docker alternative: the repository Dockerfile and `docker-compose.yml` provide
web, worker, local Ollama and Caddy. Copy `compose.env.example` to `.env.docker`,
set the school's LAN HTTPS address, and follow the installation guide. Download
images/packages/models during installation; keep model inference and stored files local.

`Caddyfile` serves the private school site with a local certificate. The optional
`Caddyfile.student` site block exposes student routes only on a separate public
hostname. Configure `MARGIN_STUDENT_PUBLIC_HOST` in the app as defence in depth.
Do not publish staff, SMB, IPP, database or model ports.
