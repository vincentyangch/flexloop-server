# FlexLoop VPS Deployment (Caddy + systemd)

Production deployment to a single Ubuntu/Debian VPS using **Caddy** for
HTTPS termination and **systemd** to run uvicorn.

Architecture: **one process, one port**. FastAPI serves `/api/*` and the
built admin SPA at `/admin/*` itself — there is no separate static file
server. Caddy just forwards every request to `127.0.0.1:8000`.

```
browser ─HTTPS─▶ Caddy :443 ─HTTP─▶ uvicorn :8000 ─▶ FastAPI
                                                      ├─ /api/*
                                                      └─ /admin/* (SPA from src/flexloop/static/admin/)
```

## Files in this directory

| File              | Installed to                                | Purpose                          |
|-------------------|---------------------------------------------|----------------------------------|
| `Caddyfile`       | `/etc/caddy/Caddyfile`                      | Reverse proxy + HTTPS            |
| `flexloop.service`| `/etc/systemd/system/flexloop.service`      | systemd unit for uvicorn         |
| `README.md`       | —                                           | This walkthrough                 |

## 1. Prerequisites

- Ubuntu 22.04+ or Debian 12+
- A domain with A/AAAA records pointing at the VPS
- **Python 3.12+**: `sudo apt install python3.12 python3.12-venv`
- **uv** (any install location — only needed during setup):
  `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Node.js 20+ and npm** (for building the admin SPA):
  `curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs`
- **Caddy v2** — see <https://caddyserver.com/docs/install#debian-ubuntu-raspbian>

## 2. Create the system user

```bash
sudo useradd --system --create-home --shell /bin/bash flexloop
sudo mkdir -p /opt/flexloop
sudo chown flexloop:flexloop /opt/flexloop
```

## 3. Clone and install Python deps

```bash
sudo -u flexloop -H bash <<'EOF'
cd /opt/flexloop
git clone <your-repo-url> flexloop-server
cd flexloop-server
uv sync --all-extras
mkdir -p data backups logs
EOF
```

Notes:
- **`--all-extras` is required**. Plain `uv sync` skips deps that
  imports resolve to at runtime.
- `data/` / `backups/` / `logs/` must exist before first boot — SQLite
  will create the DB file but not the parent directory.

## 4. Build the admin SPA

```bash
sudo -u flexloop -H bash <<'EOF'
cd /opt/flexloop/flexloop-server/admin-ui
npm ci --legacy-peer-deps
npm run build
mkdir -p ../src/flexloop/static/admin
rm -rf ../src/flexloop/static/admin/*
cp -r dist/* ../src/flexloop/static/admin/
EOF
```

Notes:
- **`--legacy-peer-deps` is required** due to a TypeScript 6 /
  openapi-typescript peer conflict.
- The build output MUST be copied into `src/flexloop/static/admin/` —
  FastAPI mounts from there (see `src/flexloop/main.py`). Without this
  step, `/admin` returns 404 "admin UI not built".

## 5. Configure `.env`

```bash
sudo -u flexloop cp /opt/flexloop/flexloop-server/.env.example /opt/flexloop/flexloop-server/.env
sudo -u flexloop nano /opt/flexloop/flexloop-server/.env
```

Recommended changes:
- `DATABASE_URL=sqlite+aiosqlite:///./data/flexloop.db` — puts the DB
  alongside backups under `data/`.
- `AI_API_KEY=<your key>` — or leave empty and set via the admin Config
  page after first login.

All AI-related settings (provider, model, key, temperature, allowed
origins) are **DB-backed and hot-reloaded** from the `app_settings`
row. `.env` values are just cold-start defaults. After first boot,
edit them from the admin **Config** page — no restart needed.

## 6. First boot (runs migrations)

```bash
sudo -u flexloop -H bash -c 'cd /opt/flexloop/flexloop-server && ./.venv/bin/uvicorn flexloop.main:app --host 127.0.0.1 --port 8000'
```

Wait for `Application startup complete.`, then Ctrl-C. This runs
`init_db()` which creates all tables and applies Alembic migrations.
Verify `data/flexloop.db` was created.

## 7. Create the first admin user

```bash
sudo -u flexloop -H bash -c 'cd /opt/flexloop/flexloop-server && ./.venv/bin/python -m flexloop.admin.bootstrap create-admin <username>'
```

Prompts for a password twice (minimum 8 characters).

## 8. Install the systemd unit

```bash
sudo cp /opt/flexloop/flexloop-server/deploy/flexloop.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now flexloop.service
sudo systemctl status flexloop.service
```

Should show `active (running)`. If it fails:
- `sudo journalctl -u flexloop.service -n 50` to see the error
- Check `.venv/bin/uvicorn` exists (step 3 ran cleanly)
- Check `.env` is readable by the `flexloop` user

## 9. Install the Caddy config

```bash
sudo cp /opt/flexloop/flexloop-server/deploy/Caddyfile /etc/caddy/Caddyfile

# Option A (simple): hardcode the domain.
sudo sed -i 's/{$FLEXLOOP_DOMAIN}/flexloop.example.com/' /etc/caddy/Caddyfile

# Option B (env var): put the domain in /etc/default/caddy AND ensure
# Caddy's systemd unit has EnvironmentFile=/etc/default/caddy enabled.

sudo systemctl reload caddy
sudo systemctl status caddy
```

Caddy automatically obtains a Let's Encrypt cert on the first HTTPS
request — no certbot needed. Ensure ports 80 and 443 are open on the
VPS firewall (`sudo ufw allow 80,443/tcp` if using ufw).

Test:
```bash
curl -I https://flexloop.example.com/api/health
# Expect: HTTP/2 200
```

## 10. CRITICAL: add the production origin to `admin_allowed_origins`

**Until you do this, CSRF blocks every admin write request.** The
cold-start default is `[http://localhost:5173, http://localhost:8000]`
which excludes your production domain.

1. Visit `https://flexloop.example.com/admin` and log in with the
   user created in step 7.
2. Navigate to **Config** in the sidebar.
3. Under **Allowed origins**, add `https://flexloop.example.com`.
4. **Save**. The CSRF middleware hot-reloads — no restart needed.

## 11. Smoke test

- `https://flexloop.example.com/admin` → dashboard loads
- **Health** page → all rows green (AI provider check needs step 5
  `AI_API_KEY` set or the Config page equivalent)
- **Logs** page → live tail streams without buffering delays (confirms
  Caddy is not buffering SSE)
- Create a test user from **Users** page → succeeds (confirms CSRF
  allowed origin from step 10 took effect)

---

## Operations

### Logs

```bash
sudo journalctl -u flexloop.service -f       # uvicorn / app stderr
sudo tail -f /var/log/caddy/flexloop.log     # reverse proxy access log
```

In-app structured logs (7-day retention) also land at
`/opt/flexloop/flexloop-server/logs/flexloop.YYYY-MM-DD.jsonl` and are
viewable at `/admin/logs`.

### Updates

```bash
sudo -u flexloop -H bash <<'EOF'
cd /opt/flexloop/flexloop-server
git fetch origin && git checkout main && git pull
uv sync --all-extras
cd admin-ui && npm ci --legacy-peer-deps && npm run build
rm -rf ../src/flexloop/static/admin/* && cp -r dist/* ../src/flexloop/static/admin/
EOF
sudo systemctl restart flexloop.service
```

Alembic migrations run automatically on startup — no separate
`alembic upgrade` step.

### Backups

SQLite backups live at `/opt/flexloop/flexloop-server/backups/`. The
admin **Backup** page creates/downloads/restores/uploads manually, and
the admin **Triggers** page has a one-click "backup" trigger.

For automated daily backups, use cron + SQLite's consistent-snapshot
`.backup` command (safe while the app has the DB open):

```cron
0 3 * * * flexloop sqlite3 /opt/flexloop/flexloop-server/data/flexloop.db ".backup /opt/flexloop/flexloop-server/backups/flexloop_$(date +\%Y\%m\%d).db"
```

Pair with a retention job to prune old files if the backups directory
grows — e.g. `find /opt/flexloop/flexloop-server/backups -name 'flexloop_*.db' -mtime +30 -delete`.

### Rollback

If an update breaks things:

```bash
sudo -u flexloop -H bash <<'EOF'
cd /opt/flexloop/flexloop-server
git reset --hard <previous-commit>
uv sync --all-extras
cd admin-ui && npm ci --legacy-peer-deps && npm run build
rm -rf ../src/flexloop/static/admin/* && cp -r dist/* ../src/flexloop/static/admin/
EOF
sudo systemctl restart flexloop.service
```

For DB rollback, use the admin **Backup** page to restore a pre-update
snapshot (`POST /api/admin/backups/{name}/restore`).

---

## Notes and caveats

- **The `Dockerfile` in the repo is stale** — it does not build the
  `admin-ui/` SPA, so the docker path currently serves a broken admin.
  If you prefer docker-compose, patch the Dockerfile with a multi-stage
  node build before `COPY src/`. Otherwise use this systemd path.
- **No horizontal scaling.** The ring-buffer log handler and in-memory
  SSE client registry are per-process. This deployment assumes a single
  uvicorn worker on a single VPS. Do NOT add `--workers 2` to the
  `ExecStart` line without first reworking those components.
- **Single admin operator assumption.** The admin UI has no RBAC — any
  admin user has full control. Treat every `admin_users` row as root-
  equivalent and rotate passwords via
  `python -m flexloop.admin.bootstrap reset-admin-password <username>`.
