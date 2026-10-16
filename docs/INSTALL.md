# Installing Margin on a school computer

This guide is for the person setting up Margin in a school: one computer (the "school box")
runs Margin and the AI model, and teachers use it from their browsers over the school network.
Student data never leaves this computer.

## 1. What the school box needs

- Windows 10/11, Ubuntu 22.04+ or macOS, with 16 GB of memory. A GPU with 6 GB or more makes
  AI marking much faster; without one it still works, overnight.
- 20 GB of free disk space, plus about 1 GB per 300 scanned pages.
- Installed once, from their official sites:
  - **uv** (the Python manager): https://docs.astral.sh/uv/
  - **Node.js 22 LTS**: https://nodejs.org (needed to build the web app)
  - **Ollama**: https://ollama.com (runs the AI model on this computer)
  - **Git**, to download Margin.

## 2. Download Margin and the AI model

```
git clone https://github.com/Ngum12/Margin.git
cd Margin
uv python install 3.12
cd backend && uv sync --frozen && cd ..
cd frontend && npm ci && npm run build && cd ..
ollama pull qwen3-vl:4b-instruct
```

## 3. Settings

Copy `.env.example` to `.env` (in the `Margin` folder) and change only these lines:

```
MARGIN_ENV=production
MARGIN_HOST=127.0.0.1          # only Caddy (HTTPS, below) talks to Margin directly
MARGIN_PORT=8000
MARGIN_AI_BACKEND=ollama
MARGIN_MODEL_BASE_URL=http://127.0.0.1:11434
```

`.env` is private to this computer and is never uploaded anywhere.

### Sign-in over the school network: HTTPS with Caddy

In production, Margin's sign-in cookie is "secure": browsers send it only over HTTPS. Caddy
(Apache-2.0, approved) adds HTTPS on the school box with its **own local certificate**. It never
contacts the internet.

1. Download `caddy_2.11.7_windows_amd64.zip` (or the Linux `.tar.gz`) from
   https://github.com/caddyserver/caddy/releases/tag/v2.11.7, and unzip `caddy.exe` into the
   `Margin` folder.
2. Keep `MARGIN_HOST=127.0.0.1` in `.env`, so only Caddy can reach Margin.
3. Decide the address teachers will type: the school box's fixed IP address (for example
   `192.168.1.20`), or a name your network knows (for example `margin.lan`).
4. Start Caddy from the `Margin` folder (PowerShell):
   ```
   $env:MARGIN_SITE = "192.168.1.20"
   .\caddy.exe run --config deploy\Caddyfile
   ```
   The first time, run `.\caddy.exe trust` once, as administrator, so the school box itself
   trusts the certificate.
5. Teachers open `https://192.168.1.20`.

### Trust the certificate on each teacher computer (once per computer)

Caddy's root certificate is in
`%AppData%\Caddy\pki\authorities\local\root.crt` on the school box. With Docker, get it with
`docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt .`. Copy it to a USB drive
or a shared folder, then:

- **Windows:** double-click `root.crt`, choose Install Certificate, then Local Machine, then
  "Place all certificates in the following store": Trusted Root Certification Authorities. Or,
  as administrator: `certutil -addstore -f Root root.crt`.
- **macOS:** open `root.crt` in Keychain Access (System keychain), then set Trust to Always
  Trust.
- **Android or ChromeOS tablets:** Settings, then Security, then Install a certificate, then CA
  certificate.
- **Firefox:** Settings, then Privacy & Security, then Certificates, then View certificates,
  then Authorities, then Import.

Without this step browsers show a warning. Do not ask teachers to click through it; install the
certificate instead. The certificate stays valid while the `caddy` data folder is kept, so back
it up with Margin's backups.

### Fallback for a closed network only (not recommended)

If HTTPS is impossible, add both lines to `.env`:
```
MARGIN_COOKIE_SECURE=false
MARGIN_ALLOW_INSECURE_COOKIES_IN_PRODUCTION=true
```
Margin refuses to start with the first line alone, and logs a warning at every start while the
fallback is on. Anyone on the network can then read sign-in traffic, so use it only on a network
the school controls, and switch to HTTPS as soon as you can.

## 4. First start

```
cd backend
uv run python -m app.cli migrate
uv run python -m app.cli init-school --name "GBHS Example" --country Cameroon
uv run python -m app.cli create-user --username admin --display-name "Administrator" --role admin
cd ..
python scripts/run.py
```

Open http://127.0.0.1:8000 and sign in as `admin`. Then, under Settings:
1. Add teachers (Staff accounts).
2. Create classes, assign a teacher to each, and add students. Names are optional; students
   appear to the AI and on paper by code only.

`python scripts/run.py` starts the web app and the AI worker together, and applies any database
updates first. Keep that window open, or run it as a service (section 7).

### Demo data (optional, for showing Margin)

```
cd backend
uv run python -m app.cli seed-demo
```

This creates a teacher `demo` (you choose the password), the class "Form 5 Demo" with six students, and a
ready chemistry exam with its cover sheets prepared. Print the cover sheets, have students (or
colleagues) write answers, scan the stack and upload it, then start AI marking. It runs once.

## 5. Check it works

- On the exam's **Marking** tab, the AI panel shows any problem: worker not running, model server
  not reachable, model not installed.
- **Settings → Models and training data** shows the models in use. It must say `ollama`, never
  "Test model".

## Alternative: Docker (computers that can run it)

Many school Windows laptops cannot run Docker; the steps above work without it. Where Docker
Desktop (Windows/macOS) or Docker Engine (Linux) runs:

```
git clone https://github.com/Ngum12/Margin.git
cd Margin
copy deploy\compose.env.example .env      # Linux/macOS: cp deploy/compose.env.example .env
# edit .env: MARGIN_SITE = the address teachers will type
docker compose up -d --build
docker compose exec ollama ollama pull qwen3-vl:4b-instruct
docker compose exec web python -m app.cli init-school --name "GBHS Example" --country Cameroon
docker compose exec web python -m app.cli create-user --username admin --display-name "Administrator" --role admin
```

Teachers open `https://<MARGIN_SITE>`, after installing Caddy's certificate (above).

- **Backups:** `docker compose exec web python -m app.cli backup --out /data/backups/latest.zip`,
  then `docker compose cp web:/data/backups/latest.zip .`
- **Updates:** back up, `git pull`, then `docker compose up -d --build`.

The images are pinned to exact versions (`docs/DEPENDENCIES.md`).

## 6. Backups (do this every week, and before every update)

```
cd backend
uv run python -m app.cli backup                       # writes data/backups/margin-backup-<date>.zip
uv run python -m app.cli backup --out E:\margin-backup.zip   # or straight to a USB drive
```

A backup can be taken while Margin runs. It holds the database and every stored scan and export.
Copy it off the school box (to a USB drive kept somewhere else). **It contains student data:**
store it as carefully as the exam papers.

To restore, on a new or repaired school box: stop Margin, then

```
cd backend
uv run python -m app.cli restore --archive E:\margin-backup.zip --force
uv run python -m app.cli migrate
```

`--force` replaces the current data, so only use it when that is what you want.

## 7. Start Margin automatically

- **Windows:** Task Scheduler → Create task → "At startup", action
  `python C:\path\to\Margin\scripts\run.py`, start in `C:\path\to\Margin`, and "Run whether user
  is logged on or not". Ollama installs itself as a startup service.
- **Linux:** a systemd service running `python3 scripts/run.py` in the Margin folder, plus
  `systemctl enable ollama`.

## 8. Updating

1. Back up (section 6).
2. Stop Margin.
3. Run `git pull`, then `cd backend && uv sync --frozen`, then
   `cd ../frontend && npm ci && npm run build`.
4. Start Margin again (database updates run automatically).

## Troubleshooting

| What you see | What to do |
|---|---|
| "The background worker is not running" | Margin was started without the worker: start it with `python scripts/run.py`. |
| "The AI model server (Ollama) cannot be reached" | Start Ollama; check `MARGIN_MODEL_BASE_URL`. |
| "The AI model … is not installed" | `ollama pull qwen3-vl:4b-instruct` |
| Teachers on other computers are sent back to sign-in | Use the HTTPS address (Caddy, section 3), not `http://`. |
| The browser warns about the certificate | Install Caddy's root certificate on that computer (section 3). |
| A page took too long | It is retried once, then the script is flagged for marking by hand. |
