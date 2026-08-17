# OER Social — User Guide

## Run

```bash
cd oer-social
cp backend/.env.example backend/.env
# Set secrets in .env (API key, JWT, admin email/password)
docker compose up --build
```

Open http://localhost:3000

## Public access (Cloudflare Tunnel)

To share the app over HTTPS (learners, Instagram `PUBLIC_BASE_URL`), see **[docs/CLOUDFLARE_TUNNEL.md](CLOUDFLARE_TUNNEL.md)**.

**Local URL to put in Cloudflare** (Public Hostname → Service):

```
http://localhost:3000
```

Example public hostname: `https://oer.yourdomain.com` → then set in `backend/.env`:

```env
CORS_ORIGINS=http://localhost:3000,https://oer.yourdomain.com
PUBLIC_BASE_URL=https://oer.yourdomain.com
```

## Admin

1. Set admin email/password in `backend/.env` (not in the UI).
2. Set `CIRCUITNOTION_API_KEY` and `OPENAI_BASE_URL=https://api.circuitnotion.com/v1` ([API docs](https://circuitnotion.com/Api_Documentation)). Text: `circuit-2-turbo`. Images: `OPENAI_IMAGE_MODEL=gpt-image-2` and `OPENAI_IMAGE_QUALITY=low` (medium/high cost much more). Do not use `dall-e-2` — CircuitNotion routes it to gpt-image-2 at expensive default quality. Never send `response_format`.
3. Log in → **Admin** → **Generate pack** (poster image via CircuitNotion + caption + elaboration + case + questions).
4. **Publish to feed** so learners see it.
5. **Post to IG & X** — posts live when API keys are set; otherwise returns ready-to-export status with the reason.

### Maintain the OER program brief

Open **Brief** in the admin navigation. Review the values initially derived from
`accademy3.txt`, then add the approved clinical references, local protocols,
training context, safety boundaries, language, and responsible educator.

Select **Save and activate** to create a new version. Previous versions remain in
the history for audit purposes. The active version is automatically injected into
all new poster/content generation and learner grading; learners do not edit this
platform-wide brief.

### Social API keys (optional)

In `backend/.env`:

```env
X_API_KEY=
X_API_SECRET=
X_ACCESS_TOKEN=
X_ACCESS_TOKEN_SECRET=
INSTAGRAM_ACCESS_TOKEN=
INSTAGRAM_USER_ID=
PUBLIC_BASE_URL=https://your-public-api.example.com
```

Instagram requires a **public HTTPS** image URL (`PUBLIC_BASE_URL`), not localhost.

## Learner

1. **Sign up** with cadre and training site.
2. Open **Feed** → open a pack → answer questions → get AI score and feedback.

## Security notes

- Credentials live only in environment / `.env`.
- Do not publish admin passwords in README, UI, or chat.
- Use a strong `JWT_SECRET` in production.
- After initial setup you may set `BOOTSTRAP_ADMIN_SYNC=false`.

## Persistent admin memory

ChatGPT export conversations can be imported as admin memory (stores history in
Postgres and indexes embeddings for Space / History search).

### On the VPS

1. Download your ChatGPT data export ZIP from OpenAI (Settings → Data controls).
2. Copy it onto the server, e.g. `~/exports/chatgpt.zip`.
3. Use the **same admin email** as `BOOTSTRAP_ADMIN_EMAIL` / your login:

```bash
cd ~/oer-social

# Ensure API key + DB are set in backend/.env (CIRCUITNOTION_API_KEY, MEMORY_EMBED_ENABLED=true)
docker compose up -d db api

docker compose run --rm \
  -v "$HOME/exports/chatgpt.zip:/import/admin-export.zip:ro" \
  api python -m app.scripts.import_admin_memory \
  /import/admin-export.zip \
  --admin-email "your-admin@example.com"
```

4. If embeddings were skipped (bad API key), re-run:

```bash
docker compose run --rm api python -m app.scripts.embed_admin_memory
```

5. In the app: **Space → History** — search imports and use **Continue** to start a live chat.

The importer stores **full threads** (your messages and GPT replies), recovers
truncated ZIP batches when possible, and indexes them for search. Click
**Continue** in History to open the original back-and-forth in Space.

**ChatGPT Projects** are imported into **Space → Projects** (name, instructions,
and which conversations belong together). Re-run the same import after pulling
this update — you do not need a new ZIP. Uploaded Project files are not in
OpenAI's export (names only). Then use **View conversations** on a project and
**Continue** to pick up a thread in that project.
