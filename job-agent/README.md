# JobPilot

JobPilot is a safety-first autonomous job-application agent scaffold. It uses Playwright for browser control, LangGraph for the application loop, Pydantic-AI for structured model actions, FastAPI for resume Q&A, SQLite for audit memory, and a JSON Q&A cache.

Disclaimer: You are responsible for complying with each job board's Terms of Service and for reviewing every application before submission. Defaults are `DRY_RUN=true`, `REQUIRE_APPROVAL=true`, `STOP_ON_CAPTCHA=true`, and `MAX_APPLIES_PER_DAY=10`.

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
│   ├── nodes/
│   │   ├── observer.py
│   │   ├── planner.py
│   │   ├── executor.py
│   │   ├── rag_agent.py
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
│   └── recovery.md
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
Pydantic-AI model names should include the provider prefix, for example `openai:gpt-4o` and `openai:gpt-4o-mini`.

## Run

Start the RAG API:

```bash
uvicorn services.rag_api:app --reload
```

Run a dry-run browser pass:

```bash
python main.py --target-url "https://example.com/application" --dry-run
```

Audit logs are written to `logs/audit.log` and `data/jobpilot.sqlite3`.

## How It Works

The graph loop is:

User goal -> ObserverAgent -> PlannerAgent -> ExecutionAgent -> ValidatorAgent -> MemoryAgent -> repeat or stop.

ObserverAgent compresses the DOM and takes a screenshot. PlannerAgent emits one strict JSON action. ExecutionAgent maps that action to deterministic Playwright commands. ValidatorAgent stops on CAPTCHA, errors, ambiguity, or approval gates. RecoveryEngine gets one revised-action attempt after an exception. MemoryAgent writes every iteration to SQLite and a readable audit log.

## Prompts

PlannerAgent: `prompts/planner.md`
RAGAgent: `prompts/rag.md`
RecoveryEngine: `prompts/recovery.md`
