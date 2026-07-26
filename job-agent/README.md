# JobPilot

JobPilot is a safety-first autonomous job-application agent scaffold. It uses Playwright for browser control, LangGraph for the application loop, Pydantic-AI for structured model actions, FastAPI for resume Q&A, SQLite for audit memory, and a JSON Q&A cache.

Disclaimer: You are responsible for complying with each job board's Terms of Service and for reviewing every application before submission. Defaults are `DRY_RUN=true`, `REQUIRE_APPROVAL=true`, `STOP_ON_CAPTCHA=true`, and `MAX_APPLIES_PER_DAY=10`. Always review `audit.log` before enabling `DRY_RUN=false`.

## Project Tree

```text
job-agent/
├── config/
│   ├── settings.py
│   └── target_config.json
├── data/
│   ├── resume_expanded.txt
│   ├── qa_cache.json
│   └── vector_db/
├── agent/
│   ├── graph.py
│   ├── router.py
│   ├── nodes/
│   │   ├── observer.py
│   │   ├── planner.py
│   │   ├── executor.py
│   │   ├── rag_agent.py
│   │   ├── cover_agent.py
│   │   ├── validator.py
│   │   ├── recovery.py
│   │   └── memory.py
│   └── schemas.py
├── services/
│   ├── rag_api.py
│   ├── browser_controller.py
│   └── resume_processor.py
├── db/
│   └── sqlite_memory.py
├── prompts/
│   ├── planner.md
│   ├── rag.md
│   ├── recovery.md
│   └── cover_letter.md
├── eval/
│   ├── test_planner_json.py
│   ├── test_validator_captcha.py
│   └── test_recovery_stop.py
└── main.py
```

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env`, replace `data/resume_expanded.txt` with your expanded resume, and update `config/target_config.json`.

Model routing lives in `agent/router.py`. Defaults are `PLANNER_MODEL=gpt-4o`, `EXTRACTION_MODEL=gpt-4o-mini`, and `RAG_MODEL=gpt-4o-mini`; the router adds provider prefixes for Pydantic-AI where needed. Embeddings default to OpenAI via `EMBEDDING_PROVIDER=openai` and `EMBEDDING_MODEL=text-embedding-3-small`. To use BGE locally, install `pip install -e ".[bge]"` and set `EMBEDDING_PROVIDER=bge` plus `EMBEDDING_MODEL=BAAI/bge-small-en-v1.5`.

Stealth browser settings are controlled by `STEALTH_MODE=true` and optional `PROXY_URL`. When enabled, the Playwright context rotates user agents, randomizes common desktop viewport sizes, spoofs a US geolocation, and hides `navigator.webdriver`.

## Run

Start the RAG API:

```bash
uvicorn services.rag_api:app --reload
```

Run a dry-run browser pass:

```bash
python main.py --target-url "https://example.com/application" --dry-run
```

List configured targets without launching Playwright:

```bash
python main.py --list-targets
```

Audit logs are written to `logs/audit.log` and `data/jobpilot.sqlite3`.

Run tests and eval checks:

```bash
pytest -q
pytest -q eval
ruff check .
```

## How It Works

The graph loop is:

User goal -> ObserverAgent -> PlannerAgent [router] -> ExecutionAgent -> ValidatorAgent -> RecoveryEngine -> MemoryAgent -> repeat or stop.

ObserverAgent compresses the DOM and takes a screenshot. PlannerAgent emits one strict JSON action. ExecutionAgent maps that action to deterministic Playwright commands. ValidatorAgent stops on CAPTCHA, errors, ambiguity, or approval gates. RecoveryEngine stops after two recovery attempts and writes the hard stop to SQLite plus `audit.log`. MemoryAgent writes every iteration to SQLite and a readable audit log.

## Prompts

PlannerAgent: `prompts/planner.md`
RAGAgent: `prompts/rag.md`
RecoveryEngine: `prompts/recovery.md`
CoverLetterAgent: `prompts/cover_letter.md`
