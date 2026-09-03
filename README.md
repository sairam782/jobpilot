# 🚀 JobPilot

### AI-Powered Autonomous Job Search & Application Agent

**JobPilot** is a safety-first AI job application platform that automates the repetitive parts of the job search — from discovering relevant opportunities and matching them against your resume to preparing applications through a browser-controlled agent.

Instead of manually searching dozens of job boards, evaluating every job description, and repeatedly filling out application forms, JobPilot creates an intelligent pipeline that **discovers → scores → queues → prepares → reviews → applies**.

> **Search smarter. Match better. Apply with confidence.**

---

## ✨ What is JobPilot?

JobPilot combines job discovery, resume intelligence, deterministic matching, browser automation, and human-in-the-loop approval into a single workflow.

The system currently consists of two major components:

### Part 1 — Job Discovery & Matching

JobPilot searches across multiple public job sources concurrently, removes duplicate listings, and ranks opportunities against your resume and preferences.

### Part 2 — Intelligent Application Agent

A LangGraph-powered agent controls a Playwright browser to navigate application workflows, fill fields, generate answers, recover from errors, and stop whenever human intervention is required.

The application workflow is intentionally conservative: **the default configuration never submits an application without human approval.**

---

## 🎯 Key Features

### 🔎 Multi-Source Job Discovery

Search multiple job sources simultaneously, including:

* Greenhouse
* Lever
* Ashby
* Workable
* SmartRecruiters
* The Muse
* Remote OK
* Remotive
* USAJOBS
* Adzuna
* Jooble

Adapters that require credentials are automatically skipped when their prerequisites are unavailable.

---

### 🧠 Resume-Based Job Matching

Every job is scored against your resume using an explainable scoring system.

The default score combines:

| Signal    | Weight | Description                                    |
| --------- | -----: | ---------------------------------------------- |
| Job Title |    30% | Similarity between target roles and job title  |
| Location  |    15% | Location and remote preference                 |
| Skills    |    40% | Resume skills matched against job requirements |
| Resume    |    15% | Overall resume/JD vocabulary overlap           |

The scoring system is deterministic and does not require an LLM for the triage process.

Each result includes a detailed breakdown:

```json
{
  "score": 0.72,
  "breakdown": {
    "title": 1.0,
    "location": 1.0,
    "skills": 0.67,
    "resume": 0.13,
    "matched_skills": [
      "fastapi",
      "kubernetes",
      "python",
      "rag"
    ],
    "missing_skills": [
      "airflow",
      "spark"
    ]
  }
}
```

This makes the ranking **transparent and explainable** rather than simply producing an unexplained AI score.

---

### 🤖 Autonomous Application Agent

The application agent uses a LangGraph workflow with specialized stages:

```text
Observe
   ↓
Plan
   ↓
Execute
   ↓
Validate
   ↓
Recover
   ↓
Memorize
```

The agent can:

* Inspect application pages
* Determine required fields
* Generate application answers
* Fill forms using Playwright
* Validate entered information
* Recover from expected failures
* Maintain application state
* Record an audit trail

When the agent encounters a CAPTCHA, ambiguous question, or unexpected error, it stops instead of attempting to bypass the problem.

---

### 🛡️ Human-in-the-Loop Safety

JobPilot is designed around controlled automation.

Default safety settings:

```text
DRY_RUN=true
REQUIRE_APPROVAL=true
STOP_ON_CAPTCHA=true
STOP_ON_AMBIGUOUS=true
MAX_APPLIES_PER_DAY=10
```

This means:

**The agent prepares the application → pauses → you review → you approve.**

Applications are not automatically submitted under the default configuration.

---

### 📋 Application Queue

Applications move through a persistent queue with states such as:

```text
queued
   ↓
needs_approval
   ↓
approved
   ↓
processing
   ↓
submitted
```

Failed applications can be requeued, while rejected or skipped applications remain part of the audit history.

---

### 🧾 Audit Trail

JobPilot maintains persistent records of agent activity using SQLite.

The system records:

* Application state
* Filled fields
* Generated answers
* Agent iterations
* Errors
* Approval decisions
* Submission history
* Rate-limit information

This makes the application process traceable instead of being a black box.

---

## 🏗️ Architecture

```text
                    ┌─────────────────────┐
                    │     JobPilot CLI    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │     FastAPI API     │
                    │   + Dashboard       │
                    └──────────┬──────────┘
                               │
                ┌──────────────┴──────────────┐
                │                             │
                ▼                             ▼
       ┌─────────────────┐          ┌─────────────────┐
       │ Job Discovery   │          │ Application     │
       │ Engine          │          │ Agent           │
       └────────┬────────┘          └────────┬────────┘
                │                            │
                ▼                            ▼
       ┌─────────────────┐          ┌─────────────────┐
       │ Job Adapters    │          │ LangGraph       │
       │                 │          │ Agent           │
       │ Greenhouse      │          └────────┬────────┘
       │ Lever           │                   │
       │ Ashby           │                   ▼
       │ Workable        │          ┌─────────────────┐
       │ SmartRecruiters │          │ Playwright      │
       │ USAJOBS         │          │ Browser         │
       │ Adzuna          │          └────────┬────────┘
       │ Jooble          │                   │
       │ RemoteOK        │                   ▼
       │ Remotive        │          ┌─────────────────┐
       └────────┬────────┘          │ Human Approval  │
                │                   └─────────────────┘
                ▼
       ┌─────────────────┐
       │ Deduplication   │
       │ + Scoring       │
       └────────┬────────┘
                │
                ▼
       ┌─────────────────┐
       │ SQLite Queue    │
       │ + Audit Log     │
       └─────────────────┘
```

---

## 🧩 Project Structure

```text
job-agent/
│
├── agent/
│   ├── graph.py
│   ├── router.py
│   ├── schemas.py
│   └── nodes/
│       ├── observer
│       ├── planner
│       ├── executor
│       ├── validator
│       ├── recovery
│       ├── memory
│       ├── rag
│       └── cover
│
├── discovery/
│   ├── base.py
│   ├── http.py
│   ├── aggregator.py
│   ├── dedup.py
│   ├── companies.py
│   ├── greenhouse.py
│   ├── lever.py
│   ├── ashby.py
│   ├── workable.py
│   ├── smartrecruiters.py
│   ├── themuse.py
│   ├── remoteok.py
│   ├── remotive.py
│   ├── usajobs.py
│   ├── adzuna.py
│   ├── jooble.py
│   └── registry.py
│
├── scoring/
│   ├── matcher.py
│   └── skills.py
│
├── orchestrator/
│   ├── queue.py
│   ├── rate_limiter.py
│   └── service.py
│
├── services/
│   ├── api.py
│   ├── dashboard.html
│   ├── browser_controller.py
│   ├── logging_config.py
│   └── resume_processor.py
│
├── db/
│   └── sqlite_memory.py
│
├── config/
│   ├── settings.py
│   └── target_config.json
│
├── prompts/
│
├── tests/
│
├── eval/
│
├── scripts/
│   └── smoke_test.py
│
├── main.py
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

---

## ⚙️ Tech Stack

| Technology      | Purpose                          |
| --------------- | -------------------------------- |
| **Python 3.12** | Core application                 |
| **FastAPI**     | REST API and dashboard           |
| **LangGraph**   | Agent orchestration              |
| **Playwright**  | Browser automation               |
| **SQLite**      | Persistent queue and audit trail |
| **Pydantic**    | Data validation                  |
| **httpx**       | HTTP requests                    |
| **Docker**      | Containerized deployment         |
| **Pytest**      | Testing                          |
| **Ruff**        | Linting                          |

---

# 🚀 Getting Started

## 1. Clone the repository

```bash
git clone https://github.com/sairam782/jobpilot.git
cd jobpilot/job-agent
```

## 2. Create a virtual environment

Python 3.12 is recommended.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

On Windows:

```powershell
.venv\Scripts\activate
```

---

## 3. Install dependencies

```bash
pip install -e ".[dev]" pypdf
```

Install Chromium for browser-based application workflows:

```bash
playwright install chromium
```

---

## 4. Configure environment variables

Create your environment file:

```bash
cp .env.example .env
```

Configure the discovery sources you want to use.

Example:

```env
GREENHOUSE_PACKS=ai-labs,big-tech-ai,ai-tooling,healthcare-ai,robotics,data-infra
LEVER_PACKS=ai-labs,big-tech-ai,ai-tooling,healthcare-ai,robotics,data-infra
ASHBY_PACKS=ai-labs,ai-tooling,healthcare-ai,robotics
WORKABLE_PACKS=ai-labs,healthcare-ai
```

Optional USAJOBS configuration:

```env
USAJOBS_USER_AGENT=your-email@example.com
USAJOBS_API_KEY=your-api-key
```

Optional Adzuna configuration:

```env
ADZUNA_APP_ID=your-app-id
ADZUNA_APP_KEY=your-app-key
```

For the browser application agent:

```env
OPENAI_API_KEY=your-api-key
```

---

## 5. Add your resume

Place your expanded resume at:

```text
data/resume_expanded.txt
```

Alternatively, configure a PDF resume:

```env
RESUME_PDF_PATH=/path/to/resume.pdf
```

You can then expand the resume using:

```bash
python -c "import asyncio; from pathlib import Path; from services.resume_processor import expand_resume; asyncio.run(expand_resume(Path('path/to/resume.pdf')))"
```

---

# 🔍 Usage

## Search for jobs

Perform a one-time search without modifying the queue:

```bash
python main.py search \
    --role "AI Engineer" \
    --role "Machine Learning Engineer" \
    --role "Data Scientist" \
    --location Remote \
    --location "New York, NY" \
    --employment-type full_time \
    --employment-type contract \
    --top-n 30
```

---

## Discover and queue jobs

Persist high-quality matches:

```bash
python main.py discover --min-score 0.55
```

---

## View queued applications

```bash
python main.py queue --status queued --limit 50
```

---

## Start the API and dashboard

```bash
python main.py serve --host 0.0.0.0 --port 8000
```

Then open:

```text
http://127.0.0.1:8000
```

Swagger API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

---

## Run the application agent

To process the next queued application:

```bash
python main.py run-next
```

The agent will navigate the application using Playwright and stop whenever human intervention is required.

---

# 🔌 REST API

| Method | Endpoint              | Description                         |
| ------ | --------------------- | ----------------------------------- |
| GET    | `/health`             | Health and safety status            |
| GET    | `/sources`            | Available job sources               |
| GET    | `/target-config`      | Current job targeting configuration |
| GET    | `/rate-limit`         | Submission budget                   |
| POST   | `/search`             | Search and rank jobs                |
| POST   | `/discover`           | Search and enqueue jobs             |
| POST   | `/resume_qa`          | Resume-grounded Q&A                 |
| GET    | `/queue`              | List application queue              |
| POST   | `/queue`              | Add job to queue                    |
| GET    | `/queue/{id}`         | Get application details             |
| POST   | `/queue/{id}/approve` | Approve application                 |
| POST   | `/queue/{id}/reject`  | Reject application                  |
| POST   | `/queue/{id}/skip`    | Skip application                    |
| POST   | `/queue/{id}/requeue` | Retry application                   |
| POST   | `/runs/next`          | Process next queued job             |
| GET    | `/docs`               | Swagger API documentation           |

---

# 🐳 Docker

Build the image:

```bash
docker build -t jobpilot:latest .
```

Run JobPilot:

```bash
docker run --rm \
    -p 8000:8000 \
    --env-file .env \
    jobpilot:latest
```

Or use Docker Compose:

```bash
docker compose up -d
```

View logs:

```bash
docker compose logs -f jobpilot
```

The container uses the Playwright Python image so Chromium dependencies are available for browser automation.

---

# 🧪 Testing

Run the complete test suite:

```bash
pytest -q
```

Run linting:

```bash
ruff check .
```

Run the offline smoke test:

```bash
python scripts/smoke_test.py
```

The test suite covers:

* Job source adapters
* HTTP error handling
* Concurrent discovery
* Adapter isolation
* Timeouts
* Cross-source deduplication
* Job scoring
* Skill matching
* Missing skills
* Exclusion rules
* Queue behavior
* Safety gates

Tests use mocked HTTP transports so discovery tests do not need to contact real job boards.

---

# 🛡️ Responsible Automation

JobPilot is intentionally designed to avoid unsafe or uncontrolled automation.

### Default safety controls

```env
DRY_RUN=true
REQUIRE_APPROVAL=true
STOP_ON_CAPTCHA=true
STOP_ON_AMBIGUOUS=true
MAX_APPLIES_PER_DAY=10
```

### CAPTCHA protection

If the browser encounters a CAPTCHA or anti-bot page, the agent stops rather than attempting to bypass it.

### Ambiguous applications

If a required question cannot be confidently answered from the user's information, the agent stops and requests human intervention.

### Human approval

Applications remain in:

```text
needs_approval
```

until the user explicitly approves them.

---

# ⚠️ Terms of Service & Legal Notice

JobPilot is designed to use public APIs, ATS feeds, and publisher-provided endpoints for job discovery.

LinkedIn and Indeed are **not scraped by the discovery system**.

Automated interaction with job application websites may still be restricted by individual websites' Terms of Service. Users are responsible for ensuring their use of JobPilot complies with applicable laws, website policies, and employment-platform rules.

Never use generated application answers to provide false information.

**Always review an application before submission.**

---

# 🗺️ Roadmap

## Short Term

* [ ] Improve dynamic form support
* [ ] Improve iframe handling
* [ ] Add LLM token and cost tracking
* [ ] Add per-run agent trace export
* [ ] Expand curated company packs
* [ ] Improve structured resume parsing
* [ ] Improve application recovery

## Long Term

* [ ] Scheduled weekly job discovery
* [ ] Incremental job discovery
* [ ] Slack notifications
* [ ] Email notifications
* [ ] High-match job alerts
* [ ] Optional LLM re-ranking
* [ ] More ATS integrations
* [ ] Application analytics dashboard
* [ ] Resume version management

---

# 📊 Current Architecture Status

| Component                       | Status         |
| ------------------------------- | -------------- |
| Multi-source discovery          | ✅              |
| Concurrent search               | ✅              |
| Job deduplication               | ✅              |
| Resume-based scoring            | ✅              |
| Explainable matching            | ✅              |
| Persistent queue                | ✅              |
| FastAPI API                     | ✅              |
| CLI                             | ✅              |
| SQLite audit trail              | ✅              |
| Docker support                  | ✅              |
| Automated testing               | ✅              |
| LangGraph agent                 | 🚧 In progress |
| Playwright application workflow | 🚧 In progress |
| Human approval workflow         | ✅              |
| Dynamic form handling           | 🚧 Roadmap     |

---

# 🤝 Contributing

Contributions are welcome.

If you would like to add a new job source:

1. Implement the discovery adapter.
2. Follow the common job contract.
3. Add adapter tests using mocked HTTP responses.
4. Register the adapter.
5. Run the test suite.
6. Submit a pull request.

```bash
pytest -q
ruff check .
```

---

# ⭐ Why JobPilot?

Traditional job searching requires candidates to repeatedly:

```text
Search
  ↓
Open job
  ↓
Read JD
  ↓
Compare resume
  ↓
Decide whether to apply
  ↓
Customize resume
  ↓
Fill application
  ↓
Answer questions
  ↓
Submit
  ↓
Track application
```

JobPilot turns that into:

```text
                    ┌───────────────┐
                    │ Target Roles  │
                    └───────┬───────┘
                            ↓
                    ┌───────────────┐
                    │ Job Discovery │
                    └───────┬───────┘
                            ↓
                    ┌───────────────┐
                    │ Deduplication │
                    └───────┬───────┘
                            ↓
                    ┌───────────────┐
                    │ Resume Match  │
                    └───────┬───────┘
                            ↓
                    ┌───────────────┐
                    │ Job Queue     │
                    └───────┬───────┘
                            ↓
                    ┌───────────────┐
                    │ AI Agent      │
                    └───────┬───────┘
                            ↓
                    ┌───────────────┐
                    │ Human Review  │
                    └───────┬───────┘
                            ↓
                    ┌───────────────┐
                    │ Application   │
                    └───────────────┘
```

The goal is not simply to **apply to more jobs**.

The goal is to **spend less time searching and more time preparing for the opportunities that actually match you.**

---

## 📄 License

See the repository license for licensing information.

---

## 👨‍💻 Author

**Sairam**

GitHub: [@sairam782](https://github.com/sairam782)

---

<p align="center">
  Built with Python, FastAPI, LangGraph, Playwright, and a lot of automation 🤖
</p>
