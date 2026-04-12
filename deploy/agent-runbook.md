# FlexLoop VPS Deployment — Agent Runbook

## Audience

You are an AI coding agent (OpenClaude, Codex, Aider, or similar) running in
a Linux shell on a **fresh** Ubuntu 22.04+ / Debian 12+ VPS. Your job is to
deploy FlexLoop end-to-end with minimal human involvement.

This file is a companion to `README.md`. The README is for humans reading
top-to-bottom; **this file is the machine-readable version**. Every step
has an explicit `cmd:` block and a `verify:` block. Stop and report if any
verification fails.

## Prompt to paste into your agent session

```
You are deploying FlexLoop to this VPS. Read and execute
flexloop-server/deploy/agent-runbook.md top-to-bottom.

Before starting, ask me for every <CAPITALIZED_PLACEHOLDER> value.
After each step, run its `verify:` block and confirm the expected
output. If verification fails, stop and report the failing step.
Do not skip verifications.

All steps are idempotent — re-running the runbook on a partially
deployed VPS is safe.
```

## Placeholders — collect from the human BEFORE starting

| Placeholder         | Example                                        | Notes                                                         |
|---------------------|------------------------------------------------|---------------------------------------------------------------|
| `<DOMAIN>`          | `flexloop.example.com`                         | Must have A/AAAA records pointing at this VPS                 |
| `<REPO_URL>`        | `https://github.com/yourorg/flexloop-server.git` | Public repo, or private with an SSH deploy key            |
| `<ADMIN_USERNAME>`  | `admin`                                        | Username for the first admin account                         |
| `<ADMIN_PASSWORD>`  | 16+ char random string                         | Generate if not provided: `openssl rand -base64 24`           |
| `<AI_API_KEY>`      | `sk-…` (optional)                              | OpenAI API key. Can be set later via the admin Config page.   |

## Pre-flight — run BEFORE step 1

```bash
# 1. Confirm Ubuntu 22.04+ or Debian 12+
grep -E 'VERSION_ID' /etc/os-release

# 2. Confirm sudo works without a password prompt (agent-friendly)
sudo -n true && echo "sudo: ok" || echo "sudo: FAILED - not passwordless"

# 3. Confirm DNS points at this VPS (so Caddy can get a Let's Encrypt cert)
VPS_IP=$(curl -4 -sS https://ifconfig.me)
DNS_IP=$(dig +short <DOMAIN> | tail -n1)
echo "VPS public IP: $VPS_IP"
echo "DNS resolves to: $DNS_IP"
test "$VPS_IP" = "$DNS_IP" && echo "dns: ok" || echo "dns: MISMATCH - fix before step 10"
```

```bash
# 4. Codex session (soft check — doesn't block deploy)
if [ -f /home/ubuntu/.codex/auth.json ]; then
    echo "codex: ~/.codex/auth.json present (Codex CLI format)"
elif [ -f /home/ubuntu/.openclaw/agents/main/agent/auth-profiles.json ]; then
    echo "codex: OpenClaw auth-profiles.json present (OpenClaw format)"
else
    echo "codex: no auth file found — run 'codex login' or configure OpenClaw if you plan to use openai-codex provider"
fi
```

**If the DNS check fails**, stop and ask the human to point DNS first.
Don't proceed — step 10 (Caddy) will fail to issue a cert and lock you
out of HTTPS.

---

## Step 1 — Install prerequisites

**cmd:**
```bash
sudo apt-get update
sudo apt-get install -y \
  python3.12 python3.12-venv git curl \
  debian-keyring debian-archive-keyring apt-transport-https gpg

# uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo install "$HOME/.local/bin/uv" /usr/local/bin/uv

# Node.js 20 LTS (needed to build the admin SPA)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Caddy v2
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update && sudo apt-get install -y caddy
```

**verify:**
```bash
python3.12 --version && uv --version && node --version && caddy version
```
All four commands must print valid versions. On failure: report which
tool failed to install.

## Step 2 — Ensure `ubuntu` owns `/opt/flexloop`

**cmd:**
```bash
sudo mkdir -p /opt/flexloop
sudo chown ubuntu:ubuntu /opt/flexloop
```

**verify:**
```bash
test "$(stat -c '%U' /opt/flexloop)" = "ubuntu" && echo "owner: ok"
```

## Step 3 — Clone and install Python dependencies

**cmd:**
```bash
sudo -u ubuntu -H bash -c '
set -euo pipefail
cd /opt/flexloop
if [ -d flexloop-server/.git ]; then
    cd flexloop-server && git fetch --all && git checkout main && git pull
else
    git clone <REPO_URL> flexloop-server && cd flexloop-server
fi
uv sync --all-extras
mkdir -p data backups logs
'
```

**verify:**
```bash
test -x /opt/flexloop/flexloop-server/.venv/bin/uvicorn && echo "uvicorn: ok"
test -d /opt/flexloop/flexloop-server/data && echo "data dir: ok"
```

**Critical flags:**
- `uv sync --all-extras` is required — plain `uv sync` skips dev deps that some imports need.

## Step 4 — Build the admin SPA

**cmd:**
```bash
sudo -u ubuntu -H bash -c '
set -euo pipefail
cd /opt/flexloop/flexloop-server/admin-ui
npm ci --legacy-peer-deps
npm run build
'
```

Vite is configured to output directly into `src/flexloop/static/admin/`
(`build.outDir` + `emptyOutDir` in `vite.config.ts`), so no manual
copy step is needed.

**verify:**
```bash
test -f /opt/flexloop/flexloop-server/src/flexloop/static/admin/index.html && echo "spa: ok"
test -d /opt/flexloop/flexloop-server/src/flexloop/static/admin/assets && echo "assets: ok"
```

**Critical flags:**
- `npm ci --legacy-peer-deps` is required — a TypeScript 6 / openapi-typescript peer conflict will break plain `npm ci`.
- FastAPI reads `/admin` from `src/flexloop/static/admin/`. If the build didn't produce files there, `/admin` will return 404 "admin UI not built" at smoke-test time.

## Step 5 — Write the .env file

**cmd:**
```bash
sudo -u ubuntu tee /opt/flexloop/flexloop-server/.env > /dev/null <<'EOF'
DATABASE_URL=sqlite+aiosqlite:///./data/flexloop.db
AI_PROVIDER=openai
AI_MODEL=gpt-4o-mini
AI_API_KEY=<AI_API_KEY>
AI_BASE_URL=
AI_TEMPERATURE=0.7
AI_MAX_TOKENS=2000
AI_REVIEW_FREQUENCY=block
AI_REVIEW_BLOCK_WEEKS=6
HOST=127.0.0.1
PORT=8000
EOF
sudo chmod 600 /opt/flexloop/flexloop-server/.env
sudo chown ubuntu:ubuntu /opt/flexloop/flexloop-server/.env
```
If the human didn't provide `<AI_API_KEY>`, leave it empty — it can be
set via the admin Config page after first login.

**verify:**
```bash
sudo -u ubuntu grep -q 'DATABASE_URL=sqlite+aiosqlite:///./data/flexloop.db' /opt/flexloop/flexloop-server/.env && echo "env: ok"
test "$(stat -c '%a' /opt/flexloop/flexloop-server/.env)" = "600" && echo "perms: ok"
```

## Step 6 — First boot to run migrations and seed `app_settings`

The app must boot once before step 8 can set allowed origins, because
step 8 needs the `app_settings` singleton row which the seed migration
creates on first boot.

**cmd:**
```bash
sudo -u ubuntu -H bash -c '
set -euo pipefail
cd /opt/flexloop/flexloop-server
PYTHONPATH=src ./.venv/bin/uvicorn flexloop.main:app --host 127.0.0.1 --port 8000 \
  > /tmp/flexloop-first-boot.log 2>&1 &
echo $! > /tmp/flexloop-first-boot.pid
'
sleep 12
```

**verify:**
```bash
test -f /opt/flexloop/flexloop-server/data/flexloop.db && echo "db: ok"
curl -sf http://127.0.0.1:8000/api/health | grep -q '"status":"ok"' && echo "startup: ok"
```

If the health check fails, print the log and stop:
```bash
cat /tmp/flexloop-first-boot.log
```

After verification, shut down the first-boot process (step 9 will
start it properly via systemd):
```bash
FB_PID=$(cat /tmp/flexloop-first-boot.pid)
sudo kill -TERM "$FB_PID" 2>/dev/null || true
sleep 2
sudo pkill -9 -u ubuntu -f 'uvicorn flexloop.main' 2>/dev/null || true
```

## Step 7 — Create the first admin user (non-interactive)

**cmd:**
```bash
sudo -u ubuntu -H bash -c "
set -euo pipefail
cd /opt/flexloop/flexloop-server
PYTHONPATH=src FLEXLOOP_ADMIN_PW='<ADMIN_PASSWORD>' ./.venv/bin/python -m flexloop.admin.bootstrap \
  create-admin '<ADMIN_USERNAME>' --password-env FLEXLOOP_ADMIN_PW
"
```

**Security note:** The password is visible in `ps auxww` on this
machine for the sub-second the command runs. On a single-operator VPS
this is acceptable. If you need to harden further, write the password
to a `0600` file and read it via `$(cat /path)` inside the subshell
instead of embedding it in the `FLEXLOOP_ADMIN_PW='…'` literal.

**Expected output:** `Created admin user '<ADMIN_USERNAME>' (id=1).`

**Idempotency:** If the admin already exists (re-running the runbook),
the command fails with `Error: admin user 'X' already exists`. That's
a **soft success** — keep going.

**verify:** The command above should print "Created…" OR fail with
"already exists". Any other output means something went wrong.

## Step 8 — Set `admin_allowed_origins` (non-interactive)

Without this step, CSRF will block every admin write request because
the default allowed-origins list contains only localhost.

**cmd:**
```bash
sudo -u ubuntu -H bash -c "
set -euo pipefail
cd /opt/flexloop/flexloop-server
PYTHONPATH=src ./.venv/bin/python -m flexloop.admin.bootstrap \
  set-allowed-origins 'https://<DOMAIN>,http://localhost:8000'
"
```

**Expected output:** `Set admin_allowed_origins to: ['https://<DOMAIN>', 'http://localhost:8000']`

**verify:** The command above should print the "Set admin_allowed_origins…" line. If it says
`app_settings row not found`, step 6 didn't complete — re-run step 6
with a longer sleep and check `/tmp/flexloop-first-boot.log`.

## Step 9 — Install and start the systemd unit

**cmd:**
```bash
sudo cp /opt/flexloop/flexloop-server/deploy/flexloop.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now flexloop.service
sleep 3
```

**verify:**
```bash
sudo systemctl is-active flexloop.service
# must print "active"

curl -sf http://127.0.0.1:8000/api/health | grep -q '"status":"ok"' && echo "local health: ok"
```

If the unit isn't active, print the last 50 journal lines and stop:
```bash
sudo journalctl -u flexloop.service -n 50 --no-pager
```

## Step 10 — Install the Caddyfile and reload Caddy

**cmd:**
```bash
sudo cp /opt/flexloop/flexloop-server/deploy/Caddyfile /etc/caddy/Caddyfile
sudo sed -i 's|{\$FLEXLOOP_DOMAIN}|<DOMAIN>|' /etc/caddy/Caddyfile
sudo systemctl reload caddy
sleep 8  # Caddy needs time to get a Let's Encrypt cert on first start
```

**verify:**
```bash
sudo systemctl is-active caddy
# must print "active"

curl -fsI https://<DOMAIN>/api/health
# must return HTTP/2 200 with a valid cert
```

If Caddy fails: `sudo journalctl -u caddy -n 50 --no-pager`. The most
common failure is that DNS isn't yet pointing at the VPS — Caddy can't
complete the ACME challenge without it. The pre-flight DNS check
should have caught this; if you got here anyway, go back and re-check.

---

## Smoke test (agent runs autonomously)

```bash
# 1. Admin SPA loads
curl -fsI https://<DOMAIN>/admin && echo "admin spa: ok"

# 2. Health endpoint returns ok
curl -fsS https://<DOMAIN>/api/health \
  | python3 -c 'import sys, json; r = json.load(sys.stdin); assert r["status"] == "ok", r; print("health: ok")'

# 3. No errors in the last minute of logs
ERRORS=$(sudo journalctl -u flexloop.service --since '1 minute ago' --no-pager 2>/dev/null | grep -iE 'error|traceback|exception' || true)
if [ -z "$ERRORS" ]; then
    echo "logs: clean"
else
    echo "logs: WARNINGS FOUND"
    echo "$ERRORS"
fi
```

Report all three results to the human. If health is not ok or errors
are in logs, stop and ask for guidance.

---

## Hand-off to the human

Report this to the human when the runbook completes successfully:

```
FlexLoop is deployed at https://<DOMAIN>.

Admin login:
  URL:      https://<DOMAIN>/admin
  Username: <ADMIN_USERNAME>
  Password: <ADMIN_PASSWORD>   ← change this via the Sessions page

Next steps for you (human):
1. Log in at https://<DOMAIN>/admin with the credentials above.
2. Check Health → all rows should be green. If AI provider is not ok,
   set AI_API_KEY via the Config page (or update .env and restart).
3. Rotate the admin password via the Sessions page.
4. Consider setting up automated backups — see README.md "Operations → Backups".
```

---

## Failure recovery cheatsheet

| Symptom                                              | Likely cause                          | Fix                                                             |
|------------------------------------------------------|---------------------------------------|-----------------------------------------------------------------|
| Step 1: `apt-get install caddy` fails                | Cloudsmith repo not added cleanly     | Re-run the `curl … dl.cloudsmith.io … tee` + `apt update`        |
| Step 3: `uv sync` fails on a compiled dep            | Missing build tools                   | `sudo apt install -y build-essential python3.12-dev` then retry |
| Step 4: `npm ci` fails with peer-dep errors          | Forgot `--legacy-peer-deps`           | Re-run step 4 verbatim                                          |
| Step 6: health check fails after first boot          | Migration crash, bad .env, missing dir | `cat /tmp/flexloop-first-boot.log`                              |
| Step 7: `create-admin` errors "already exists"       | Runbook re-run                        | Soft success — keep going                                        |
| Step 8: `app_settings row not found`                 | Step 6 never booted far enough        | Re-run step 6 with a longer sleep, verify log                   |
| Step 9: `systemctl is-active` shows `inactive`       | uvicorn crashes at start              | `journalctl -u flexloop -n 100 --no-pager`                      |
| Step 10: Caddy inactive or cert error                | DNS not pointed, port 80/443 blocked  | `dig <DOMAIN>`, `sudo ufw status`, `journalctl -u caddy`        |
| Smoke: `/admin` returns 404 "admin UI not built"     | Step 4 didn't copy                    | Re-run step 4                                                   |
| Smoke: admin writes blocked with 403                 | Step 8 didn't run                     | Re-run step 8 with the correct domain                           |

## Nuking and restarting

For a clean slate on a partially-deployed VPS:

```bash
sudo systemctl stop flexloop caddy 2>/dev/null || true
sudo systemctl disable flexloop 2>/dev/null || true
sudo rm -f /etc/systemd/system/flexloop.service /etc/caddy/Caddyfile
sudo systemctl daemon-reload
sudo rm -rf /opt/flexloop
```

Then re-run the runbook from step 1.
