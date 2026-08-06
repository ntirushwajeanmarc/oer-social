# OER Social Learning (Program 1)

AI-generated OER packs for anesthesia, perioperative medicine, and critical care.

## Quick start

```bash
cd oer-social
cp backend/.env.example backend/.env
# Fill CIRCUITNOTION_API_KEY, JWT_SECRET, BOOTSTRAP_ADMIN_EMAIL, BOOTSTRAP_ADMIN_PASSWORD

docker compose up --build
```

- App: http://localhost:3000  
- API docs: http://localhost:8000/docs  

## AI provider (CircuitNotion)

Uses the OpenAI-compatible CircuitNotion API ([docs](https://circuitnotion.com/Api_Documentation)):

```env
OPENAI_BASE_URL=https://api.circuitnotion.com/v1
CIRCUITNOTION_API_KEY=your_key
OPENAI_MODEL=circuit-2-turbo
```

Other chat models: `deepseek-v4-pro`, `circuit-3`, `gpt-4.1`, `gpt-4o-mini`.

Poster images use CircuitNotion `images.generate` with `OPENAI_IMAGE_MODEL=gpt-image-2` and `OPENAI_IMAGE_QUALITY=medium`. Requests never include `response_format` (`dall-e-3` currently fails on CircuitNotion’s proxy for that reason).

Note: use `api.circuitnotion.com` (not `apis.` — that hostname does not resolve).

## Admin credentials (production)

Admin accounts are **not** shown in the UI. Configure them only in `backend/.env`:

```env
BOOTSTRAP_ADMIN_EMAIL=your-admin@yourdomain.com
BOOTSTRAP_ADMIN_PASSWORD=your-strong-password
BOOTSTRAP_ADMIN_SYNC=true
JWT_SECRET=long-random-secret
```

On startup the API creates that admin if missing, or syncs the password when `BOOTSTRAP_ADMIN_SYNC=true`. Set `BOOTSTRAP_ADMIN_SYNC=false` after go-live if you prefer not to overwrite the password from env.

Never commit `backend/.env`.

## Learner

Use **Learner signup** on the home page, then open **Feed**.

## Docs

- [User guide](docs/USER_GUIDE.md)
- [Cloudflare Tunnel](docs/CLOUDFLARE_TUNNEL.md) — public HTTPS URL for learners and Instagram
