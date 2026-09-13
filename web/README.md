# JobPilot Web

Next.js 14 (App Router) dashboard for the JobPilot backend. Designed to
deploy to Vercel with the backend hosted separately.

## Layout

```
web/
├── app/
│   ├── layout.tsx        # shared shell + nav
│   ├── page.tsx          # landing
│   └── globals.css       # CSS variables + tailwind
├── vercel.json           # Vercel project config
├── next.config.mjs
├── tailwind.config.ts
├── postcss.config.js
├── tsconfig.json
├── package.json
└── .env.example
```

Search, queue, and job-detail pages arrive in follow-up PRs.

## Local development

```bash
cd web
cp .env.example .env.local     # set NEXT_PUBLIC_API_URL to your backend
npm install
npm run dev                    # → http://127.0.0.1:3000
```

The dashboard makes CORS-enabled requests to the backend named in
`NEXT_PUBLIC_API_URL`. If you're running the backend from `job-agent/`
locally, that's `http://127.0.0.1:8000` by default. Enable CORS on the
FastAPI service (see `docs/DEPLOYMENT.md`, added in a follow-up PR).

## Deploying to Vercel

1. On https://vercel.com, import this GitHub repository.
2. **Root Directory**: `web` (Vercel needs to know the project isn't at the
   repo root).
3. Framework preset: **Next.js** (auto-detected).
4. Add an Environment Variable: `NEXT_PUBLIC_API_URL` pointing at your
   deployed backend (Fly.io, Render, Railway, a Docker host, etc.).
5. Deploy.

Vercel is **frontend only** for JobPilot. The FastAPI backend has
long-running LLM calls and Playwright inside; serverless functions on
Vercel are the wrong host for that. Pick any container-friendly host
for the backend and point the frontend at it.

## Scripts

| Command | What |
| --- | --- |
| `npm run dev` | Local dev server with hot reload |
| `npm run build` | Production build |
| `npm run start` | Serve the production build |
| `npm run lint` | Next.js ESLint config |
| `npm run typecheck` | Strict TS check (`tsc --noEmit`) |
