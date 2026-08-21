# JobPilot

> Safety-first autonomous job-application platform.
>
> Search across 11 public job sources → score every result against your
> resume → drive a Playwright-controlled browser through each application
> → pause at a human-in-the-loop gate before anything is submitted.
> Every step lands in a durable audit trail.

---

## What it does today

**Part 1 — Discovery + scoring (production-ready).**

`POST /search` takes 2–3 target roles, optional locations, and an
employment-type filter (full-time / part-time / contract / internship /
temporary), fans that query out to every enabled source concurrently,
deduplicates matches across sources, and ranks everything against a
resume you supply. `POST /discover` does the same fanout and persists
matches above a threshold into a durable queue.

**Part 2 — Application filling (scaffolded, in progress).**

A LangGraph loop drives a Playwright-controlled browser through one
application at a time (observe → plan → execute → validate → recover →
memorize), stops at the first CAPTCHA / ambiguity / error, and — under
the default gate — parks the run at `needs_approval` so a human reviews
the filled fields + generated answers before anything is submitted.

Everything is behind a small FastAPI service so the pipeline is
scriptable, dashboardable, and testable.

---

## Safety posture

**Defaults are conservative on purpose.** You are responsible for
complying with each site's Terms of Service and for reviewing every
application before submission. Scraping ToS-protected sites (LinkedIn,
Indeed) is out of scope — every discovery adapter here talks to a
publisher-blessed public API or feed.

| Gate | Default | Effect |
| --- | --- | --- |
| `DRY_RUN=true` | on | The agent fills, but never submits. |
| `REQUIRE_APPROVAL=true` | on | Ready-to-submit runs land in `needs_approval`. |
| `STOP_ON_CAPTCHA=true` | on | Any CAPTCHA / anti-bot page hard-stops the run. |
| `STOP_ON_AMBIGUOUS=true` | on | The planner returns "done, blocked" on unclear fields. |
| `MAX_APPLIES_PER_DAY=10` | on | Rolling-24h submission cap enforced in the queue. |

Only turn these off after you have read `logs/audit.log` for the last
few runs. The SQLite `submission_log` table is the source of truth for
the daily budget.

---

## Discovery coverage

| Tier | Adapter | Auth | Notes |
| --- | --- | --- | --- |
| Per-company ATS | `greenhouse`, `lever`, `ashby`, `workable`, `smartrecruiters` | none | Poll one company at a time; use the curated packs to warm-start with 50+ AI/ML/DS-hiring companies. |
| No-key search | `themuse`, `remoteok`, `remotive` | none | Global search. |
| Federal | `usajobs` | free key + email UA | Tens of thousands of open US federal roles. |
| Aggregators | `adzuna`, `jooble` | free API keys | Broad US coverage across job boards. |

Adapters whose prerequisites (keys / company lists) are missing are
skipped silently — turning one off is one env var away.

### Curated company packs

Rather than research 100 slugs by hand, enable packs in `.env` and the
per-company adapters expand automatically. Packs live in
`discovery/companies.py` — patches welcome.

```env
GREENHOUSE_PACKS=ai-labs,big-tech-ai,ai-tooling,healthcare-ai,robotics,data-infra
LEVER_PACKS=ai-labs,big-tech-ai,ai-tooling,healthcare-ai,robotics,data-infra
ASHBY_PACKS=ai-labs,ai-tooling,healthcare-ai,robotics
WORKABLE_PACKS=ai-labs,healthcare-ai
```

That single expansion resolves to ~73 vetted AI/ML/DS companies
(OpenAI, Anthropic, Cohere, Hugging Face, Pinecone, Databricks, Scale,
Cruise, Skydio, Tempus, Insitro, Abridge, Recursion, …).

---

## Scoring

Every discovered job gets a `[0, 1]` score from four deterministic
signals plus an exclusion gate. No LLM in the triage hot path — the
score is fully explainable and test-covered.

| Signal | Weight (default) | What it measures |
| --- | --- | --- |
| `title` | 0.30 | Fuzzy ratio of the job title against each configured `role`. |
| `location` | 0.15 | Configured-location substring hit, with remote-preference lift. |
| `skills` | 0.40 | Overlap between the extracted resume skill vocabulary and JD skills (~180 curated terms across ML/AI, data, infra, backend, frontend, methods). |
| `resume` | 0.15 | General token overlap across the full JD body. |

Weights come from `SCORE_*_WEIGHT` env vars. An exclusion keyword in
the title or description zeroes the score. A seniority mismatch
(`senior` resume vs `intern` posting) applies a soft penalty, never a
hard exclude. Employment-type mismatch zeroes the score when the source
publishes a type — unknown types pass through, since many boards don't
say.

Every scored result carries a full breakdown so you can see why:

```json
{
  "score": 0.72,
  "breakdown": {
    "title": 1.0, "location": 1.0, "skills": 0.67, "resume": 0.13,
    "matched_skills": ["fastapi", "kubernetes", "python", "rag"],
    "missing_skills": ["airflow", "spark", "..."],
    "reasons": ["title:1.0", "location:1.0", "skills:0.67", "resume:0.13"]
  }
}
```

---

## REST API

| Method | Path | Description |
| --- | --- | --- |
| `GET`  | `/health` | Liveness + safety-gate snapshot + queue counts. |
| `GET`  | `/sources` | Registered vs enabled adapters. |
| `GET`  | `/target-config` | Active `target_config.json`. |
| `GET`  | `/rate-limit` | Rolling 24-hour submission budget. |
| `POST` | `/search` | Ranked results only; no queue writes. |
| `POST` | `/discover` | Same fanout, but enqueues matches ≥ `min_score`. |
| `POST` | `/resume_qa` | Resume-grounded Q&A; offline fallback if no LLM key. |
| `GET`  | `/queue?status=queued,needs_approval&limit=100` | List queue rows. |
| `POST` | `/queue` | Manually enqueue a URL. |
| `GET`  | `/queue/{id}` | Row detail + filled fields + answer previews + audit. |
| `POST` | `/queue/{id}/approve` | `needs_approval` → `approved`. |
| `POST` | `/queue/{id}/reject` | `needs_approval` → `rejected`. |
| `POST` | `/queue/{id}/skip`   | Skip a queued or needs-approval row. |
| `POST` | `/queue/{id}/requeue` | Retry a failed row. |
| `POST` | `/runs/next` | Pick the next queued row and drive the agent. |
| `GET`  | `/docs` | OpenAPI (Swagger) UI. |
| `GET`  | `/` | Minimal HTML dashboard. |

### `POST /search` example

```bash
curl -s -X POST http://127.0.0.1:8000/search \
  -H "Content-Type: application/json" -d '{
    "roles": ["AI Engineer", "Machine Learning Engineer", "Data Scientist",
              "Robotics ML Engineer", "Healthcare AI Engineer"],
    "locations": ["Remote", "New York, NY", "San Francisco"],
    "remote_preference": "remote_or_hybrid",
    "employment_types": ["full_time", "part_time", "contract"],
    "exclusion_keywords": ["sales development representative", "recruiter"],
    "per_source_limit": 50,
    "min_score": 0.5,
    "top_n": 25
  }'
```

Response shape:

```json
{
  "total_before_dedup": 84,
  "total_after_dedup": 71,
  "per_source": [
    { "name": "greenhouse", "ok": true, "returned": 22, "took_ms": 412 },
    { "name": "usajobs",    "ok": true, "returned": 18, "took_ms": 611 },
    { "name": "adzuna",     "ok": false, "returned": 0, "took_ms": 25000, "error": "timeout" }
  ],
  "results": [{ "job": { … }, "score": 0.83, "breakdown": { … } }, …]
}
```

---

## CLI

```bash
# One-off search, no queue writes.
python main.py search \
    --role "AI Engineer" --role "ML Engineer" --role "Data Scientist" \
    --location Remote --location "New York, NY" \
    --employment-type full_time --employment-type contract \
    --top-n 30

# Same fanout but persist matches to the queue.
python main.py discover --min-score 0.55

# Inspect the queue.
python main.py queue --status queued --limit 50

# Serve the API + dashboard.
python main.py serve --host 0.0.0.0 --port 8000

# List adapters + their enabled state.
python main.py sources

# Drive the browser against the top queued job (Part 2).
python main.py run-next
```

---

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]" pypdf
playwright install chromium          # only for `run-next` / `run-url`
cp .env.example .env
```

Edit `.env` — at minimum:

```env
# Discovery
GREENHOUSE_PACKS=ai-labs,big-tech-ai,ai-tooling,healthcare-ai,robotics,data-infra
LEVER_PACKS=ai-labs,big-tech-ai,ai-tooling,healthcare-ai,robotics,data-infra
ASHBY_PACKS=ai-labs,ai-tooling,healthcare-ai,robotics

# Free federal + aggregator keys (recommended)
USAJOBS_USER_AGENT=you@example.com          # https://developer.usajobs.gov/APIRequest
USAJOBS_API_KEY=xxxxxxxxxxxxxxxxxxxxxxx
ADZUNA_APP_ID=xxxxxx
ADZUNA_APP_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Only needed for Part 2 (auto-fill)
OPENAI_API_KEY=sk-...
```

Then drop your expanded resume into `data/resume_expanded.txt`, or set
`RESUME_PDF_PATH` and expand it once:

```bash
python -c "import asyncio; from pathlib import Path; \
           from services.resume_processor import expand_resume; \
           asyncio.run(expand_resume(Path('path/to/resume.pdf')))"
```

---

## Docker

```bash
docker build -t jobpilot:latest .
docker run --rm -p 8000:8000 --env-file .env jobpilot:latest
# or
docker compose up -d
open http://127.0.0.1:8000
docker compose logs -f jobpilot
```

The image is based on `mcr.microsoft.com/playwright/python`, so
Chromium runtime deps are already inside. `/app/data` and `/app/logs`
are mounted as named volumes.

---

## Project tree

```text
job-agent/
├── agent/                # LangGraph nodes + schemas (Part 2)
│   ├── graph.py
│   ├── router.py
│   ├── schemas.py
│   └── nodes/            # observer, planner, executor, validator, recovery, memory, rag, cover
├── discovery/            # Part 1
│   ├── base.py           # SearchQuery + Job contract
│   ├── http.py           # Retry + backoff + Retry-After
│   ├── aggregator.py     # Concurrent fanout + per-source telemetry
│   ├── dedup.py          # Cross-adapter deduplication
│   ├── companies.py      # Curated per-ATS company packs
│   ├── greenhouse.py, lever.py, ashby.py, workable.py, smartrecruiters.py
│   ├── themuse.py, remoteok.py, remotive.py
│   ├── usajobs.py, adzuna.py, jooble.py
│   └── registry.py
├── scoring/              # Part 1
│   ├── matcher.py        # Deterministic 4-signal score + breakdown
│   └── skills.py         # ~180-term vocabulary + extraction + seniority
├── orchestrator/
│   ├── queue.py          # SQLite queue + state machine
│   ├── rate_limiter.py   # Rolling 24h submission cap
│   └── service.py        # search_jobs, discover_and_enqueue, process_next
├── services/
│   ├── api.py            # FastAPI app (REST + dashboard)
│   ├── dashboard.html
│   ├── browser_controller.py
│   ├── logging_config.py
│   └── resume_processor.py
├── db/sqlite_memory.py   # Audit log for every graph iteration
├── config/
│   ├── settings.py       # All env-backed knobs
│   └── target_config.json
├── prompts/              # planner, rag, recovery, cover_letter
├── tests/                # 56 pytests
├── eval/                 # Scripted eval checks
├── scripts/smoke_test.py # Offline end-to-end without a browser
├── main.py               # CLI entry point
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

---

## Testing

```bash
pytest -q                    # 56 unit + integration tests
ruff check .                 # lint
python scripts/smoke_test.py # offline end-to-end
```

Every adapter is covered by an `httpx.MockTransport` test so nothing
touches the network. The aggregator has concurrent-success,
exception-isolation, per-adapter-timeout, and cross-source-dedup tests.
Scoring covers the breakdown shape, matched/missing skills, and
exclusion gating. CI (`.github/workflows/ci.yml`) runs pytest + ruff +
`docker build` on every push and PR.

---

## Roadmap

Short-term:

- **Part 2 hardening** — dynamic-form + iframe support in the browser
  agent, LLM cost/token tracking, per-run trace export.
- **More per-company packs** — a broader `discovery/companies.py` seed
  set based on user submissions.
- **Structured resume ingestion** — parse `Resume/CV` PDFs into
  typed sections (experience, education, skills) so scoring can weight
  recency + seniority.

Longer-term:

- Weekly cron discovery, incremental (only what's new since last run).
- Alerting hooks (Slack / email) when a very high-score match lands.
- Optional LLM re-ranking of the top N to catch nuance the deterministic
  scorer misses.

---

## Legal / TOS note

- LinkedIn and Indeed are **not** scraped. Their ToS forbids automated
  scraping and their operators actively block it.
- Every discovery adapter here uses a publisher-blessed endpoint (an
  ATS's public boards API, an aggregator's free JSON API, or a company's
  own JSON feed).
- Automated form submission on a jobs site can violate that site's ToS
  even when the fetch does not. That's why every default here is
  dry-run + human-in-the-loop until you deliberately loosen the gate.
- You are responsible for what you submit. Read `logs/audit.log` before
  turning `DRY_RUN` off.
