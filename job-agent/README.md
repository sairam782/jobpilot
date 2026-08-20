# JobPilot

> Autonomous, safety-first job application platform.

JobPilot discovers relevant openings on public job boards, ranks them
against your resume, drives a Playwright-controlled browser through each
application, and pauses at a human-in-the-loop gate before submitting.
Every step lands in a durable audit trail.

---

## Safety posture

**Defaults are conservative on purpose.** You are responsible for
complying with each job board's Terms of Service and for reviewing every
application before submission.

| Gate | Default | Effect |
| --- | --- | --- |
| `DRY_RUN=true` | on | The agent fills, but never submits. |
| `REQUIRE_APPROVAL=true` | on | Ready-to-submit applications land in `needs_approval`. |
| `STOP_ON_CAPTCHA=true` | on | Any CAPTCHA / anti-bot page hard-stops the run. |
| `STOP_ON_AMBIGUOUS=true` | on | The planner returns "done, blocked" on unclear fields. |
| `MAX_APPLIES_PER_DAY=10` | on | Rolling-24h submission cap enforced in the queue. |

Turn these off only when you have read the audit log for the last few
runs and are confident about what the agent will do. `audit.log` and the
SQLite `submission_log` table are the source of truth.

---

## Architecture

```
                  ┌───────────────┐
                  │ Discovery     │  Greenhouse / Lever public APIs
                  │  Adapters     │  → normalized job dicts
                  └──────┬────────┘
                         │ score_jobs()  (title × location × resume)
                         ▼
                  ┌───────────────┐
                  │ SQLite Queue  │  states: queued → running →
                  │  + Rate Limit │           needs_approval → approved
                  │               │           → submitted / failed / skipped
                  └──────┬────────┘
                         │ pick_next()
                         ▼
   ┌─────────────────────────────────────────────────┐
   │ Orchestrator                                    │
   │   process_next(dry_run, require_approval)       │
   └─────────────────────────────────────────────────┘
                         │
                         ▼
           ┌──────────────────────────────┐
           │ LangGraph agent loop         │
           │  observe → plan → execute →  │
           │  validate → recover → mem    │
           └──────────────────────────────┘
                         │
                         ▼
                 ┌───────────────┐
                 │ FastAPI + UI  │  /health /queue /discover /runs/next
                 │  dashboard    │  /queue/{id}/approve|reject|skip|requeue
                 └───────────────┘
```

The queue is the single source of truth. Discovery, the browser loop,
and the dashboard all read and write through it.

---

## Project tree

```text
job-agent/
├── agent/                # LangGraph nodes and shared schemas
│   ├── graph.py
│   ├── router.py
│   ├── schemas.py
│   └── nodes/            # observer, planner, executor, validator, recovery, memory, rag, cover
├── config/
│   ├── settings.py       # pydantic-settings; every knob has an env alias
│   └── target_config.json
├── discovery/            # public-API adapters
│   ├── base.py
│   ├── greenhouse.py
│   ├── lever.py
│   └── registry.py
├── orchestrator/
│   ├── queue.py          # SQLite queue + state machine
│   ├── rate_limiter.py
│   └── service.py        # discover_and_enqueue, process_next
├── scoring/
│   └── matcher.py        # deterministic title × location × resume score
├── services/
│   ├── api.py            # FastAPI app (REST + dashboard)
│   ├── dashboard.html
│   ├── browser_controller.py
│   ├── logging_config.py
│   ├── rag_api.py        # legacy shim → imports services.api:app
│   └── resume_processor.py
├── db/
│   └── sqlite_memory.py  # audit log for every graph iteration
├── prompts/              # planner / rag / recovery / cover_letter
├── tests/                # unit + integration (pytest)
├── eval/                 # scripted eval checks
├── scripts/
│   └── smoke_test.py     # offline end-to-end without a browser
├── main.py               # CLI entry point (`jobpilot` script)
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

---

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
cp .env.example .env
```

Then either drop your expanded resume text into `data/resume_expanded.txt`,
or set `RESUME_PDF_PATH` in `.env` and expand it once:

```bash
python -c "import asyncio; from pathlib import Path; from services.resume_processor import expand_resume; \
           asyncio.run(expand_resume(Path('path/to/resume.pdf')))"
```

---

## Running

### API + dashboard

```bash
python main.py serve --host 127.0.0.1 --port 8000
# → open http://127.0.0.1:8000
```

The dashboard lists queue state, lets you enqueue a manual URL, run
discovery, and approve or reject anything sitting in `needs_approval`.

### Discovery + queue from the CLI

```bash
# 1. Configure a few boards in .env, e.g.:
#    GREENHOUSE_COMPANIES=stripe,notion
#    LEVER_COMPANIES=palantir,figma
python main.py discover --limit-per-source 30 --min-score 0.55
python main.py queue --status queued

# 2. Drive the agent against the top-scoring queued job.
python main.py run-next
```

### One-shot URL (bypasses queue/discovery)

```bash
python main.py run-url --target-url "https://example.com/apply" --dry-run
```

---

## REST API surface

| Method | Path | Description |
| --- | --- | --- |
| GET | `/health` | Liveness + safety gate snapshot |
| GET | `/target-config` | The active target config JSON |
| GET | `/rate-limit` | Rolling 24-hour submission cap status |
| POST | `/resume_qa` | Resume-grounded Q&A (LLM-backed; offline fallback) |
| POST | `/discover` | Run discovery adapters and enqueue matches |
| GET | `/queue?status=queued,needs_approval&limit=100` | List queue rows |
| POST | `/queue` | Enqueue a direct URL (bypasses discovery) |
| GET | `/queue/{id}` | Row detail + filled fields + answer previews + audit |
| POST | `/queue/{id}/approve` | `needs_approval` → `approved` |
| POST | `/queue/{id}/reject` | `needs_approval` → `rejected` |
| POST | `/queue/{id}/skip` | Skip a queued or needs-approval row |
| POST | `/queue/{id}/requeue` | Retry a failed row |
| POST | `/runs/next` | Pick the next queued row and drive the agent |
| GET | `/docs` | OpenAPI (Swagger) UI |

---

## Configuration

Every knob has an env alias. See `.env.example` for the full list. Notable ones:

| Env var | Default | Effect |
| --- | --- | --- |
| `PLANNER_MODEL` | `gpt-4o` | Model used for browser action planning |
| `RAG_MODEL` | `gpt-4o-mini` | Model used for resume Q&A |
| `EMBEDDING_PROVIDER` | `openai` | `openai` or `bge` |
| `BROWSER_HEADLESS` | `true` | Set false when you want to watch runs locally |
| `SCORE_TITLE_WEIGHT` | `0.45` | Weights are normalized before combination |
| `SCORE_LOCATION_WEIGHT` | `0.20` | |
| `SCORE_RESUME_WEIGHT` | `0.35` | |
| `SCORE_MIN_ACCEPT` | `0.55` | Below this, discovery does not enqueue |
| `GREENHOUSE_COMPANIES` | (empty) | Comma-separated Greenhouse board slugs |
| `LEVER_COMPANIES` | (empty) | Comma-separated Lever board slugs |

---

## Deployment

### Docker

```bash
docker build -t jobpilot:latest .
docker run --rm -p 8000:8000 --env-file .env jobpilot:latest
```

### docker-compose

```bash
docker compose up -d
# open http://127.0.0.1:8000
docker compose logs -f jobpilot
```

The image is based on `mcr.microsoft.com/playwright/python`, so Chromium
runtime dependencies ship with the container. Application data
(`/app/data`) and audit logs (`/app/logs`) are mounted as named volumes.

### Health check

Both the `Dockerfile` and `docker-compose.yml` wire up `GET /health` as
the health probe. It reports the safety flags, queue counts, and the
rolling-24h submission budget.

---

## Testing

```bash
pytest -q                  # unit + integration
ruff check .               # lint
python scripts/smoke_test.py   # offline end-to-end
```

The smoke test does not require an OpenAI key or a browser install; it
stubs the discovery adapter and the graph runner.

CI runs pytest + ruff + `docker build` on every push and PR — see
`.github/workflows/ci.yml`.

---

## How the graph works

```
User goal → ObserverAgent → PlannerAgent [router] → ExecutionAgent
          → ValidatorAgent → RecoveryEngine → MemoryAgent → repeat or stop
```

- **ObserverAgent** compresses the DOM into `PageState` and takes a screenshot.
- **PlannerAgent** emits exactly one strict-JSON `PlannerAction`.
- **ExecutionAgent** maps the action to deterministic Playwright commands.
- **ValidatorAgent** stops on CAPTCHA, execution errors, ambiguity, or approval gates.
- **RecoveryEngine** produces one revised action after a failure; two consecutive failures are a hard stop.
- **MemoryAgent** writes each iteration to SQLite and to `logs/audit.log`.

Prompts live in `prompts/`.
