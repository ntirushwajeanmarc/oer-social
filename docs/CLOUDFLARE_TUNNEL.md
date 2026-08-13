# Cloudflare Tunnel — OER Social

Expose your local Docker stack on a public HTTPS URL without opening router ports. Cloudflare Tunnel (`cloudflared`) connects **from your machine to Cloudflare**; visitors hit your tunnel hostname and traffic is forwarded to localhost.

## Local services (Docker Compose)

After `docker compose up --build`:

| Service           | Local URL                    | Purpose                                 |
| ----------------- | ---------------------------- | --------------------------------------- |
| **Web (Next.js)** | `http://localhost:3000`      | Main app — learners & admin UI          |
| **API (FastAPI)** | `http://localhost:8000`      | REST API + `/media` poster files        |
| **API docs**      | `http://localhost:8000/docs` | Swagger (optional, dev only)            |
| **Postgres**      | `localhost:5434`             | Database — **do not** expose via tunnel |

The frontend proxies `/api/*` and `/media/*` to the backend, so **one tunnel to port 3000 is enough** for normal use and Instagram image URLs.

---

## What to enter in Cloudflare

In [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → **Networks** → **Tunnels** → your tunnel → **Public Hostname**:

### Recommended (single hostname)

| Field         | Value                                                       |
| ------------- | ----------------------------------------------------------- |
| **Subdomain** | `oer` (or any name you prefer)                              |
| **Domain**    | Your zone, e.g. `yourdomain.com`                            |
| **Path**      | _(leave empty)_                                             |
| **Type**      | HTTP                                                        |
| **URL**       | `http://web:3000` when `cloudflared` runs in Docker Compose |

Public URL example: `https://oer.yourdomain.com`

If you run `cloudflared` on the host instead of Docker, use `http://localhost:3000`.

### Optional (direct API hostname)

Only needed if you want Swagger or API access without the Next.js app:

| Public hostname                  | Local URL               |
| -------------------------------- | ----------------------- |
| `https://api.oer.yourdomain.com` | `http://localhost:8000` |

If you use only the web hostname, set `PUBLIC_BASE_URL` to the **web** URL — Next.js forwards `/media/...` to the API.

---

## Docker Compose (recommended with your tunnel token)

1. Put the token in both places (Compose reads project `.env`; API stack uses `backend/.env`):

```env
# oer-social/.env  and  oer-social/backend/.env
CLOUDFLARE_TUNNEL_TOKEN=your_token_from_zero_trust
```

2. In Zero Trust → Tunnels → your tunnel → **Public Hostname**, set Service URL to:

```
http://web:3000
```

(`web` is the Compose service name on the Docker network.)

3. Start the stack (includes `cloudflared`):

```bash
cd oer-social
docker compose up -d --build
docker compose logs -f cloudflared
```

4. Set public URL in `backend/.env`, then recreate API:

```env
CORS_ORIGINS=http://localhost:3000,https://oer.yourdomain.com
PUBLIC_BASE_URL=https://oer.yourdomain.com
```

```bash
docker compose up -d --force-recreate api
```

---

## Install and run cloudflared on the host (optional)

### 1. Install

```bash
# Debian/Ubuntu
curl -L https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update && sudo apt install cloudflared
```

Or download from [Cloudflare tunnel docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).

### 2. Log in and create a tunnel

```bash
cloudflared tunnel login
cloudflared tunnel create oer-social
```

Note the tunnel UUID from the output.

### 3. Config file

Create `~/.cloudflared/config.yml` (adjust hostname and tunnel UUID):

```yaml
tunnel: oer-social
credentials-file: /home/YOUR_USER/.cloudflared/TUNNEL_UUID.json

ingress:
  - hostname: oer.yourdomain.com
    service: http://localhost:3000
  # Optional direct API:
  # - hostname: api.oer.yourdomain.com
  #   service: http://localhost:8000
  - service: http_status:404
```

You can also add the public hostname in the Cloudflare dashboard instead of this file — both work.

### 4. DNS

If you use the config file, route DNS to the tunnel:

```bash
cloudflared tunnel route dns oer-social oer.yourdomain.com
```

If you configured the hostname in Zero Trust UI, DNS is usually created for you.

### 5. Start stack + tunnel

Terminal 1:

```bash
cd /path/to/oer-social
docker compose up --build
```

Terminal 2:

```bash
cloudflared tunnel run oer-social
```

Open `https://oer.yourdomain.com` — you should see the app.

### 6. Run tunnel as a service (optional)

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

---

## Update `backend/.env` for the public URL

Replace `yourdomain.com` with your real domain:

```env
# Comma-separated — include localhost for local dev AND your tunnel URL
CORS_ORIGINS=http://localhost:3000,https://oer.yourdomain.com

# Public HTTPS base for Instagram poster URLs (/media/posters/...)
PUBLIC_BASE_URL=https://oer.yourdomain.com
```

Restart the API after changing env:

```bash
docker compose up -d --build api
```

Instagram and Meta must fetch poster images over HTTPS; `PUBLIC_BASE_URL` cannot stay `localhost`.

---

## Quick reference — copy/paste for Cloudflare UI

**Public Hostname → Service URL (cloudflared in Docker):**

```
http://web:3000
```

**`.env` values (example):**

```env
CORS_ORIGINS=http://localhost:3000,https://oer.yourdomain.com
PUBLIC_BASE_URL=https://oer.yourdomain.com
```

---

## Troubleshooting

| Symptom                               | Fix                                                                           |
| ------------------------------------- | ----------------------------------------------------------------------------- |
| 502 / connection refused              | Ensure `docker compose up` is running and port 3000 is listening              |
| Login works locally but not on tunnel | Add tunnel URL to `CORS_ORIGINS` and restart `api`                            |
| Instagram post fails                  | Set `PUBLIC_BASE_URL=https://oer.yourdomain.com` (HTTPS, no trailing slash)   |
| API calls fail on tunnel URL          | Use the **web** hostname (3000), not 8000, unless frontend env is changed     |
| Mixed content errors                  | Tunnel URL must be `https://`; do not hardcode `http://localhost` in frontend |

---

## Security notes

- Do not tunnel Postgres (`5434`).
- Use a strong `JWT_SECRET` before sharing the public URL.
- Set `BOOTSTRAP_ADMIN_SYNC=false` after first login if you do not want env to reset the admin password.
- Restrict admin access if the tunnel is on the open internet (Cloudflare Access policies optional).
