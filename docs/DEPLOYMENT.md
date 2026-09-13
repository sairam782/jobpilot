# Deployment

JobPilot deploys as **two separate services**: a Next.js dashboard on
Vercel (or any static host) and a FastAPI backend on a container host.
This document walks through both halves.

## Why the split

The FastAPI backend runs Playwright (a headed / headless Chromium),
issues multi-minute LLM calls, and keeps a durable SQLite queue.
Vercel's serverless runtime is a poor fit for any of those — cold
starts kill Playwright, function timeouts kill long LLM calls, and
the filesystem is ephemeral so a sqlite queue can't survive a
redeploy.

So:

- **Frontend** (`web/`) → **Vercel**. Static + client-side React.
- **Backend** (`job-agent/`) → any host that can run a long-lived
  Python process with disk. Options that work today:
  - **Docker anywhere** (Fly.io, Railway, Render, DigitalOcean, a VPS)
  - `docker compose up` on your own machine for local hacking

## 1. Deploy the backend

### Option A: Docker on any container host

`job-agent/Dockerfile` is Playwright-ready (based on
`mcr.microsoft.com/playwright/python`). Any host that runs a Dockerfile
will work:

```bash
cd job-agent
docker build -t jobpilot:latest .
docker run --rm -p 8000:8000 --env-file .env jobpilot:latest
```

Push the same image to the container registry your host uses.
`docker-compose.yml` mounts named volumes for `data/` (SQLite queue)
and `logs/` (audit log) so state survives restarts.

### Option B: Fly.io (example)

```bash
cd job-agent
fly launch --dockerfile Dockerfile --no-deploy
fly secrets set OPENAI_API_KEY=... \
                GREENHOUSE_PACKS=ai-labs,big-tech-ai,healthcare-ai \
                CORS_ALLOW_ORIGINS=https://YOUR-VERCEL-URL.vercel.app
fly volumes create jobpilot_data --size 1
fly deploy
```

### Backend env vars that matter for the split

| Var | Purpose |
| --- | --- |
| `CORS_ALLOW_ORIGINS` | Comma-separated list of frontend origins. **Required** when the frontend is on a different host than the backend. Example: `https://jobpilot-web.vercel.app`. |
| `API_HOST` | Bind address. Set to `0.0.0.0` inside a container. |
| `API_PORT` | Bind port. Usually 8000; Fly.io / Render inject `$PORT`. |
| `DRY_RUN`, `REQUIRE_APPROVAL`, `STOP_ON_CAPTCHA`, `MAX_APPLIES_PER_DAY` | Safety gates. Keep the defaults until you have read `logs/audit.log` for a few runs. |

## 2. Deploy the frontend to Vercel

1. On https://vercel.com, click **Add New → Project** and import
   `sairam782/jobpilot`.
2. In the import screen:
   - **Root Directory**: `web`  (the frontend lives in a subfolder;
     Vercel needs to be told).
   - **Framework Preset**: Next.js (auto-detected once root is right).
   - **Build Command**: leave default (`next build`).
3. Add one **Environment Variable**:
   - `NEXT_PUBLIC_API_URL` = your backend's public URL, no trailing
     slash. e.g. `https://jobpilot-api.fly.dev`.
4. Deploy. Vercel gives you a URL like
   `https://jobpilot-web.vercel.app` — paste **that exact origin** into
   the backend's `CORS_ALLOW_ORIGINS` and redeploy the backend.

### Verifying the split works

```bash
curl -s https://YOUR-BACKEND/health | jq .
```

Should return the safety-gate snapshot. Then, in the browser dev
console on the Vercel URL:

```js
await fetch(process.env.NEXT_PUBLIC_API_URL + "/health").then(r => r.json())
```

If that returns the same payload, CORS is wired correctly. If you get
a browser-side CORS error, the origin listed in the browser error is
usually the exact string you need in `CORS_ALLOW_ORIGINS`.

## 3. Custom domain (optional)

- Point a domain at Vercel following their DNS instructions.
- After the domain resolves, add it to `CORS_ALLOW_ORIGINS` on the
  backend (comma-separated with the `.vercel.app` URL — you can keep
  both).

## 4. Rolling updates

- **Frontend**: pushing to `main` triggers an automatic Vercel deploy
  (the root-directory setting means only changes under `web/` rebuild
  the frontend).
- **Backend**: whatever CI you set up around the Docker image. The
  bundled `.github/workflows/ci.yml` runs `pytest` + `ruff` + a Docker
  build on every push, and can be extended with a push-to-registry
  step once you pick a registry.

## 5. What runs where — cheat sheet

```
+-------------------+           +------------------------+
| Vercel (edge)     |           | Container host         |
| Next.js dashboard | --HTTPS-> | FastAPI + Playwright   |
| web/              |           | job-agent/             |
| static + client   |           | SQLite queue on disk   |
+-------------------+           +------------------------+
        |                                    |
        | NEXT_PUBLIC_API_URL                | CORS_ALLOW_ORIGINS
        | (build time, inlined)              | (runtime env var)
        v                                    v
   Dashboard hits the API             Backend permits that origin
```
