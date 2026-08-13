# Cloudflare Tunnel — OER Social

Expose the Docker stack on a public HTTPS URL without opening router ports.
`cloudflared` connects **outbound** from your server to Cloudflare; visitors hit
your hostname and traffic is forwarded to the `web` container.

## Critical rule (avoids 502 Bad Gateway)

**One tunnel token = one running connector.**

If the same `CLOUDFLARE_TUNNEL_TOKEN` runs on the VPS **and** a laptop (or any
other host), Cloudflare load-balances across connectors. Requests that hit the
laptop (where `http://web:3000` often does not exist) return **502**.

Symptoms: site works sometimes, fails sometimes; `curl http://127.0.0.1:3000`
on the VPS is always fine.

### Fix checklist

1. Stop cloudflared everywhere except the VPS  
   (`docker compose --profile tunnel down` / stop other hosts).
2. Zero Trust → **Networks** → **Tunnels** → your tunnel → **Connectors**  
   Remove stale connectors; keep only the VPS one.
3. Prefer **rotating the tunnel token** (Configure → refresh token) so old
   connectors die immediately. Put the new token **only** in the VPS `.env`.
4. On laptops: leave `CLOUDFLARE_TUNNEL_TOKEN` and `COMPOSE_PROFILES` empty.

---

## Public Hostname (Zero Trust)

| Field | Value |
| --- | --- |
| **Hostname** | `roitoteducation.com` (and optionally `www`) |
| **Type** | HTTP |
| **URL** | `http://web:3000` |

DNS for that hostname must be proxied through Cloudflare (orange cloud),
normally a CNAME to `<tunnel-id>.cfargotunnel.com` created when you save the
Public Hostname.

---

## VPS setup (production)

1. Project root `.env` (Compose auto-loads this):

```env
COMPOSE_PROFILES=tunnel
CLOUDFLARE_TUNNEL_TOKEN=eyJ...your_token...
```

2. `backend/.env` public URL / CORS:

```env
CORS_ORIGINS=http://localhost:3000,https://roitoteducation.com
PUBLIC_BASE_URL=https://roitoteducation.com
```

3. Start (either form is fine):

```bash
cd ~/oer-social
git pull
chmod +x scripts/vps-up.sh
./scripts/vps-up.sh
# or:
# docker compose up -d --build
```

With `COMPOSE_PROFILES=tunnel` in `.env`, a normal `docker compose up -d`
starts `cloudflared` after `web` is healthy.

4. Verify:

```bash
docker compose ps
docker compose logs --tail=50 cloudflared
# Expect: Registered tunnel connection … and no "Unable to reach the origin"

for i in 1 2 3 4 5; do
  curl -s -o /dev/null -w "%{http_code}\n" https://roitoteducation.com/
  sleep 1
done
# Expect: 200 on every line
```

---

## Local development

Do **not** put the production tunnel token in your laptop `.env`.

```bash
docker compose up --build
# web http://localhost:3000 — no public tunnel
```

If you need a **separate** temporary public URL for local testing, create a
**different** Cloudflare tunnel + token (never reuse production).

---

## Local services (no tunnel)

| Service | URL | Purpose |
| --- | --- | --- |
| Web | `http://localhost:3000` | Next.js app |
| API | `http://localhost:8000` | FastAPI |
| Postgres | `localhost:5434` | DB — do not tunnel |

The frontend proxies `/api/*` and `/media/*` to the API, so one hostname on
port 3000 is enough.

---

## Optional: cloudflared on the host (not Docker)

Only if you are **not** using the Compose `cloudflared` service. Point the
Public Hostname at `http://localhost:3000` instead of `http://web:3000`, and
do not also run the Compose tunnel profile with the same token.
