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
MARGIN_HOST=0.0.0.0            # teachers' computers can reach it; 127.0.0.1 = this computer only
MARGIN_PORT=8000
MARGIN_AI_BACKEND=ollama
MARGIN_MODEL_BASE_URL=http://127.0.0.1:11434
```

`.env` is private to this computer and is never uploaded anywhere.

### Sign-in over the school network (important)

In production, Margin's sign-in cookie is marked "secure", so browsers send it **only over
HTTPS**. On the school box itself (`http://127.0.0.1:8000`) this works as it is. For teachers on
other computers or tablets, choose one:

- **Recommended:** put HTTPS in front of Margin with a local reverse proxy that has a
  certificate for the school box. This needs a small extra program, which must be approved
  first.
- **Trusted closed network only:** add `MARGIN_COOKIE_SECURE=false` to `.env`. Teachers then use
  `http://<school-box-address>:8000`. Anyone on the same network can read traffic, so use this
  only on a network the school controls.

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

## 5. Check it works

- On the exam's **Marking** tab, the AI panel shows any problem: worker not running, model server
  not reachable, model not installed.
- **Settings → Models and training data** shows the models in use. It must say `ollama`, never
  "Test model".

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
| Teachers on other computers are sent back to sign-in | The sign-in cookie needs HTTPS: see section 3. |
| A page took too long | It is retried once, then the script is flagged for marking by hand. |
