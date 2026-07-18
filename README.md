# News Report Agent

Ingests news from newsletters (IMAP), classifies and synthesizes each story with an LLM,
and publishes a filterable, password-protected static dashboard.

**Status:** v1 implemented. Fixed pipeline (collect → parse → cluster → classify →
synthesize → export) plus a static dashboard. 51 offline tests pass; real LLM/embeddings
end-to-end verification happens on the VPS. See [docs/v1-architecture.md](docs/v1-architecture.md) §9 for the Definition of Done.

## Documentation

- **Architecture diagrams (interactive):** https://fulviodeg.github.io/NewsReportAgent/ — generated from the LikeC4 model, auto-published on every push.
- **Architecture diagrams (inline):** [docs/diagrams.md](docs/diagrams.md) — Mermaid, rendered on GitHub.
- **Architecture model (source of truth):** [docs/architecture/](docs/architecture/) — LikeC4 `.c4` files.
- **Design spec & Definition of Done:** [docs/v1-architecture.md](docs/v1-architecture.md)
- **Build task & locked/open decisions:** [docs/build-prompt.md](docs/build-prompt.md)
- **Coding-agent rules:** [CLAUDE.md](CLAUDE.md)

### Updating the architecture docs

The diagrams are architecture-as-code (LikeC4). To change them, edit the model and regenerate:

```bash
npm install                # once; installs likec4
npm run docs:serve         # live interactive preview while editing docs/architecture/*.c4
# edit docs/architecture/{specification,model,views}.c4
npm run docs:validate      # check the model
npm run docs:mermaid       # regenerate docs/diagrams.md
```

CI (`.github/workflows/docs.yml`) validates the model, fails if `docs/diagrams.md` is out of
date, and deploys the interactive site to GitHub Pages on push to `main`.

## Layout

```
pipeline/            Python service (collect → parse → cluster → classify → synthesize → export)
  config.toml        cadences, sources, model-per-task, thresholds (no secrets)
  src/               pipeline modules (see docs/v1-architecture.md §10)
web/                 static dashboard served by nginx + HTTP basic auth
data/                shared runtime volume (SQLite + export.json) — gitignored
docker-compose.yml   two services: pipeline + web
```

## Try it locally (no VPS, no Docker)

Run the whole pipeline against sample newsletters and open the dashboard in your browser.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r pipeline/requirements.txt tomli   # tomli only for Python < 3.11

cd pipeline
python local_demo.py            # OFFLINE: fake embeddings + fake LLM (no keys/network)
# or:
python local_demo.py --real     # REAL: OpenRouter + embeddings from ../.env (needs keys)

cd ../web/site && python -m http.server 8000
# open http://localhost:8000
```

`local_demo.py` ingests the `.eml` files in [demo/newsletters/](demo/newsletters/) (drop your
own real newsletter exports there to test parsing), runs collect → cluster → classify →
synthesize → export, and writes `web/site/export.json` for the dashboard. Offline mode uses
deterministic stand-ins so you can explore the UI and flow without any API key; `--real`
exercises the actual APIs end-to-end.

## Setup (development)

1. `cp .env.example .env` and fill in the values (never commit `.env`).
2. The open decisions in [docs/build-prompt.md](docs/build-prompt.md) are set in
   `pipeline/config.toml` (OpenRouter model, embeddings provider/model/endpoint, themes).
3. Run the offline test suite (no network needed):
   ```bash
   python -m venv .venv && . .venv/bin/activate
   pip install -r pipeline/requirements.txt tomli   # tomli only for Python < 3.11
   cd pipeline && python -m pytest
   ```

## Deploy (VPS, Docker Compose)

Two services share one volume; the pipeline writes `news.db` + `export.json`, nginx serves
them read-only. Data lives at `/data` inside the containers (`DATA_DIR`, default `/data`).

1. `cp .env.example .env` and fill in real secrets (OpenRouter key, IMAP creds, embeddings
   key, dashboard user/password).
2. Generate the nginx basic-auth file from the env (never committed):
   ```bash
   set -a && . ./.env && set +a
   printf "%s:%s\n" "$DASHBOARD_USER" "$(openssl passwd -apr1 "$DASHBOARD_PASSWORD")" > web/.htpasswd
   ```
3. `docker compose up -d --build`
4. Open `http://<host>:8080` — the dashboard is behind HTTP basic auth.
5. Trigger a processing run on demand (same code path as the scheduled clock):
   ```bash
   docker compose exec pipeline python -m src.main run-processing
   ```

CLI commands inside the container: `python -m src.main` (scheduler / two clocks),
`run-collection`, `run-processing`.

## Automated deploy (GitHub Actions, manual approval)

Push-to-deploy with a human gate: every push to `main` starts the [`deploy`
workflow](.github/workflows/deploy.yml), which **pauses for your approval** before
touching the VPS. On approval, a GitHub runner SSHes into the VPS and runs
`git pull && docker compose up -d --build` (the VPS builds the image itself).

**One-time setup** (run from a machine that *can* SSH to the VPS — a corporate
laptop may block outbound SSH):

1. **Clone the repo on the VPS** and create its `.env` + `.htpasswd` (steps 1–2 of
   the manual deploy above):
   ```bash
   ssh root@<host>
   git clone https://github.com/fulviodeg/NewsReportAgent.git /opt/NewsReportAgent
   cd /opt/NewsReportAgent
   cp .env.example .env   # then fill in real secrets
   set -a && . ./.env && set +a
   printf "%s:%s\n" "$DASHBOARD_USER" "$(openssl passwd -apr1 "$DASHBOARD_PASSWORD")" > web/.htpasswd
   ```
2. **Create a dedicated deploy key** (separate from your personal key) and authorize
   it on the VPS:
   ```bash
   ssh-keygen -t ed25519 -f deploy_key -N "" -C "github-deploy"
   ssh-copy-id -i deploy_key.pub root@<host>   # or append deploy_key.pub to ~/.ssh/authorized_keys
   ```
3. **Add GitHub repo secrets** (Settings → Secrets and variables → Actions):
   - `SSH_HOST` — VPS IP/hostname
   - `SSH_USER` — `root`
   - `SSH_KEY` — the **private** key (contents of `deploy_key`)
   - `SSH_PORT` — optional, defaults to `22`
   - `DEPLOY_PATH` — optional, defaults to `/opt/NewsReportAgent`
4. **Create the approval gate** (Settings → Environments → New environment →
   `production`) and add yourself under **Required reviewers**. This is what makes the
   deploy wait for your click.

**Deploying:** push to `main` (or run the workflow manually from the Actions tab).
The run stops at *Waiting for approval* → review it → **Approve**. Nothing reaches the
VPS until then. `WEB_PORT` in the VPS `.env` controls the published port (default 8080).

## Note on restricted networks


OpenRouter (LLM) and the embeddings API may be unreachable from corporate/restricted
networks. The dev machine only builds and pushes; the whole test suite runs offline via
mocks/fakes. Real end-to-end LLM/embeddings calls happen on the VPS at runtime.
