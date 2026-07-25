# Research Agent — Autonomous Research/Data Analyst Agent

An enterprise-grade AI agent platform that plans, executes, and self-corrects multi-step research tasks using tool calling, structured data access, and (coming soon) RAG and long-term memory — built to demonstrate production AI engineering practices, not just a demo chatbot.

## Tech Stack

- **Backend:** FastAPI (async), Python 3.12
- **Agent orchestration:** LangGraph — explicit state machine, not an implicit agent-executor loop
- **LLM inference:** Groq (`llama-3.3-70b-versatile`), via `langchain-groq`
- **Tools:** Tavily (real-time web search), a safety-validated SQL query tool against our own Postgres data — RAG/Qdrant coming later
- **Database:** PostgreSQL + async SQLAlchemy 2.0 + Alembic
- **Cache / Queue broker:** Redis + Celery
- **Auth:** Clerk (JWT / RS256)
- **Package management:** uv
- **Containerization:** Docker + Docker Compose
- **CI:** GitHub Actions (Postgres + Redis as real service containers)

## Project Structure

```
research-agent/
├── api/              # Route handlers only — no business logic
├── services/         # Business logic layer
├── repositories/      # Database access layer
├── core/             # Config, DI providers, security, DB engine, cache, models
├── schemas/          # Pydantic request/response models
├── workers/           # Celery tasks (background jobs + agent execution)
├── agent/            # LangGraph orchestration: graphs, tools, LLM client, schemas
├── migrations/         # Alembic migrations (schema AND database roles)
├── tests/
├── scripts/           # dev.bat — wraps common Docker/migration/test commands
├── Dockerfile
└── docker-compose.yml
```

This follows Clean Architecture / Repository Pattern conventions: routes call services, services call repositories, nothing talks directly to the database except the repository layer. `agent/` is kept separate from the CRUD layers since orchestration logic is a genuinely different kind of code — see the decisions section below for why.

## Getting Started

**Prerequisites:** Docker Desktop, `uv`

```bash
git clone <your-repo-url>
cd research-agent
docker compose up --build
uv run alembic upgrade head
```

Once running:
- API: http://localhost:8000
- Interactive docs (Swagger UI): http://localhost:8000/docs
- Health check: http://localhost:8000/health

**Running tests:**
```bash
uv run pytest -v
```

**Local dev without Docker** (for quick iteration on agent graphs specifically, no DB/Redis needed):
```bash
uv sync
uv run python -m agent.graphs.run_llm_router
```

**Dev script shortcuts** (`scripts\dev.bat` on Windows):
```bash
scripts\dev.bat up        # start the stack
scripts\dev.bat build     # rebuild after dependency changes
scripts\dev.bat reset     # WARNING: full clean-slate wipe (down -v), rebuild, re-migrate
scripts\dev.bat test      # run the test suite
scripts\dev.bat logs worker   # tail a specific service's logs
```

**Windows-specific notes:**
- Use `pwsh` (PowerShell 7+), not the built-in `powershell` (5.1).
- Docker Desktop must be running before any `docker` command works.
- Any dependency change (`uv add`/`uv remove`) requires `docker compose up --build`, not just a restart.
- The `worker` service does **not** use `--reload` — code changes to anything the worker imports (`agent/`, `workers/`) need `docker compose restart worker` at minimum, or a full rebuild if dependencies also changed.

---

## Why These Decisions Were Made

This section exists because a build log documents *what happened*, but doesn't always make the *underlying reasoning* easy to find later. These are the decisions that shape the whole codebase — worth reading before extending any of them.

### Why async everywhere, not just "where convenient"

This wasn't a style preference — it was empirically proven necessary. On Day 2, load-testing `/slow-sync` vs `/slow-async` under 60 concurrent requests showed sync routes split into two batches (a ~3.0s group and a ~5.0–5.2s group) once FastAPI's threadpool was exhausted, while async routes stayed flat at ~3.0s regardless of load. Agent runs make several sequential LLM and tool calls per execution — under real concurrent usage, a sync implementation would degrade in exactly this way. Every route, service function, and agent node touching the database, an LLM, or an external API is `async def` with real `await`, for this reason specifically, not convention.

### Why LangGraph over a plain LangChain AgentExecutor

Plain agent-executor loops are implicit — you can't easily inspect what happens between steps, interrupt mid-run, or control state transitions explicitly. LangGraph models the agent as a real state machine: nodes are units of work, edges (including conditional ones) control flow, and state flows through as explicit, typed data. This is what made the Day 16–17 circuit breaker possible to bolt on cleanly (checking limits at the top of a node, forcing an existing exit path) rather than requiring a restructure of an opaque loop. It's also what will make the Week 4+ live-trace streaming feasible — you can observe and stream state transitions because they're explicit.

### Why the Repository Pattern / service layer, even for a project this size

It would be faster, short-term, to have routes talk directly to the database. This was deliberately avoided from Day 5 onward because agent logic (starting Week 3) needs to reuse the same data-access and business-decision logic that routes use — duplicating "check if X exists, otherwise create it" logic across routes, Celery tasks, and agent tool functions would create drift. The layering also made services genuinely unit-testable with mocked repositories (proven Day 5, tests run in milliseconds, zero database needed) — a different and complementary kind of correctness check from the real-database integration tests added Day 10.

### Why every external credential goes through `docker-compose.yml`'s `environment:` block, not just `.env`

This bit the project directly on Day 6: Docker Compose's automatic `.env` reading only affects **variable substitution inside the compose file itself** (`${VAR}` syntax) — it does not automatically inject arbitrary host environment variables into a running container. `DATABASE_URL` never surfaced this problem because it was hardcoded directly in Compose from Day 3; `CLERK_JWKS_URL` did, because it relied on `.env` passthrough that doesn't actually happen automatically. Every credential added since (Groq, Tavily, the readonly DB role) follows the explicit `${VAR}` pattern in `environment:` for both `api` and `worker`, specifically because of this lesson.

### Why database roles/permissions are managed via Alembic migrations, not manual `psql` commands

Discovered the hard way on Day 18: a `readonly_agent` Postgres role created manually via `psql` does not survive a `docker compose down -v` volume wipe, while the schema (managed by Alembic) is automatically and correctly recreated every time via `alembic upgrade head`. Anything that needs to exist reliably across environments — including roles and grants, not just tables — now goes through a migration (using `op.execute()` with idempotent `DO $$ IF NOT EXISTS` guards), so `scripts\dev.bat reset` regenerates a fully working environment, permissions included, not just tables.

### Why the SQL tool has two independent layers of safety, not one

An LLM given free rein to write and execute SQL is a real risk — a model trying to be "helpful" could generate a `DELETE` or `DROP`. The design deliberately uses two independent layers: application-level validation (regex-based rejection of non-SELECT statements, forbidden keywords, and stacked statements) **and** a database-level read-only role as defense in depth. The reasoning: application-level validation can have bugs or blind spots; a database permission genuinely cannot be bypassed by clever prompting, regardless of what application code does or doesn't catch. Neither layer alone was considered sufficient.

### Why every LLM-calling node has a fail-safe fallback, not a bare `except`

Starting Day 12, every node making an LLM or tool call follows the same pattern: catch the exception, log it, and degrade to a safe default (e.g., planning fails → treat the whole query as one step; routing fails → default to no tool) rather than letting the exception propagate and crash the whole graph run. This is a deliberate, consistent design philosophy applied uniformly — not a one-off decision per node — because external API calls (Groq, Tavily, Postgres) can and do fail, and a multi-step agent run is expensive enough (in time and cost) that a transient failure shouldn't discard all prior progress.

### Why the circuit breaker reuses the existing loop-exit path instead of adding new control flow

When any of the three limits (iterations, cost, runtime) is hit, `router_node` doesn't throw an exception or add a new graph edge — it sets `stopped_early: True`, records why, and forces `current_step_index` to the end of the plan, so the graph's existing `has_more_steps` conditional edge naturally routes to `synthesize` on its own. This was a deliberate minimal-footprint design choice: the safety net integrates with existing termination logic rather than fighting or duplicating it, keeping the graph's control flow easier to reason about as more limits or checks get added later.

### Why the agent is honest about partial results and gaps, not just "handled" errors

This shows up throughout the synthesis prompt design (Day 15 onward) and was verified repeatedly under real failure conditions, not just designed in theory: when the circuit breaker cuts a run short, or a tool genuinely fails (auth errors, event-loop bugs, irrelevant search results), the synthesis step is explicitly instructed to say so rather than presenting an incomplete or wrong answer with false confidence. This was proven multiple times — a forced iteration-limit test (Day 16), a forced cost-limit and timeout test (Day 17), a real SQL auth failure (Day 18), and a real async event-loop bug (Day 18) all produced honest, accurate acknowledgments of what went wrong, never a fabricated number. This is treated as a genuine safety property of the system, not an incidental nicety — a research agent that confidently states wrong information is worse than one that admits uncertainty.

---

## Build Log

Documenting real decisions and real bugs as they happened — including the ones that didn't work on the first try. Treating this as a learning artifact, not a highlight reel.

### Day 1 — FastAPI Skeleton + Docker

Built a minimal FastAPI app (`/health` endpoint), proven first on bare Windows, then containerized with a multi-stage Dockerfile.

**Why multi-stage Docker:** the `builder` stage installs dependencies via `uv sync`; the final runtime image only copies the resulting `.venv` and application code — no build tooling ships in production, keeping the image smaller and reducing attack surface.

**Bug — `--reload` watching the entire project by default.** Uvicorn's `--reload` flag watches the whole working directory unless scoped, which meant it was picking up file-timestamp changes inside `.venv/` and triggering endless, pointless server restarts. Fixed by scoping the watcher: `--reload-dir api`.

**Cross-platform dependency resolution surprised me.** `uv add fastapi uvicorn[standard]` installed 19 packages on bare Windows — no `uvloop` (it doesn't support Windows). The exact same `uv.lock` file, built inside the Linux-based Docker image, correctly added `uvloop` since the container runs Linux. Same lockfile, different resolved packages, per-platform — `uv` working as intended.

### Day 2 — Async Patterns, Pydantic Settings, Dependency Injection

**Load-tested sync vs. async routes empirically instead of just trusting the theory.** At 15 concurrent requests, both performed identically (~3.0–3.5s each) — contradicting the initial assumption that sync would visibly block, since FastAPI runs sync `def` routes in a threadpool, not on a single blocking thread. Pushed to 60 concurrent requests and found the real boundary: sync routes split into two batches (~3.0s and ~5.0–5.2s) once the threadpool was exhausted; async routes stayed flat at ~3.0s regardless.

**Bug — dependency changes don't hot-reload through Docker volume mounts.** `uv add pydantic-settings` updated the host's `pyproject.toml`/`uv.lock`, but the running container's `.venv` was baked in at image-build time. Got `ModuleNotFoundError` despite the package clearly being installed on the host. Code changes hot-reload live via volume mounts; dependency changes require `docker compose up --build`.

**Bug — pytest couldn't resolve `api.main` imports.** Fixed with `pythonpath = ["."]` under `[tool.pytest.ini_options]`.

**Proved dependency injection's value with a real test**, not just by asserting it — `app.dependency_overrides[get_settings] = fake_settings` swaps a route's config without touching route code, something a direct import could never support cleanly.

### Day 3 — PostgreSQL + Async SQLAlchemy + Alembic Migrations

**Docker Compose healthcheck prevents a real race condition** — `depends_on: condition: service_healthy` ensures `api` waits for genuine Postgres readiness (`pg_isready`), not just container start.

**Named volume (`pgdata`) proven to persist data across restarts** — confirmed via Postgres's own "Skipping initialization" log message after a restart.

**Bug — reload scope didn't cover new folders as the project grew.** Adding `repositories/user_repository.py` caused `ModuleNotFoundError` on the next restart — looked like a missing-file bug, was actually a reload-scope gap. Fixed with a `--reload-dir` flag per source folder.

**Proved the full stack round-trip** with a real create-then-dedupe test via `/test-create-user`, verified independently via `psql \dt`.

### Day 4 — Full Schema Design (AgentRun, AgentStep, Report, AuditLog)

Built the complete data model — `orgs`, `agent_runs`, `agent_steps`, `reports`, `audit_log` — with JSON columns for variable-shaped tool payloads, a Postgres enum for `RunStatus`, explicit `ondelete="CASCADE"` on every child FK, and a database-enforced one-to-one `AgentRun`↔`Report` relationship via `unique=True`.

**False alarm caught and resolved.** `\dt` output through `docker exec` appeared to be missing tables entirely — turned out to be `psql`'s interactive pager silently truncating output (`--More--`), not real data loss. Confirmed via targeted `\d <table>` checks and a clean `alembic history`. Lesson: verify with a targeted query before concluding data is missing.

### Day 5 — Repository Pattern + Service Layer, Formalized

Built `services/user_service.py` holding the "check existence, otherwise create" decision, refactoring `/test-create-user` to stop calling the repository directly. Proved the service testable in complete isolation with mocked-repository unit tests — no database, no Docker, milliseconds to run.

### Day 6 — Clerk JWT Authentication + Protected Routes

Built `core/security.py`: cached `PyJWKClient`, RS256 signature verification, issuer validation. Added protected `/me` route.

**Bug — Docker Compose's `.env` handling and Pydantic Settings' `.env` handling don't automatically talk to each other.** `CLERK_JWKS_URL`/`CLERK_ISSUER` weren't reaching the container; Compose only auto-reads `.env` for in-file variable substitution, not automatic container env injection. Fixed by explicitly listing both in the `environment:` block. (See "Why These Decisions Were Made" above — this became a standing project convention afterward.)

### Day 7 — Redis Basics + Week 1 Revision

**Bug — dependency cycle from a misplaced YAML block.** A `depends_on`/`environment` block landed inside the wrong service (`redis` depending on itself). Docker's error named the symptom, not the location — had to read the full file to find it.

**Cache correctness proven with real hit/miss/expiry behavior**, not just code review.

**Week 1 cold-start verification** — `docker compose down -v`, full rebuild, fresh migrations, every endpoint re-verified. Proved the README's setup instructions are genuinely sufficient for a stranger's first clone.

### Day 8 — Celery + Redis Broker, Background Task Basics

**Bug — worker never registered the task.** `@celery_app.task` alone isn't enough; the worker process needs `include=["workers.tasks"]` to actually import and register task modules on startup, since the worker never otherwise imports `api/main.py` (which is what triggered task registration on the API side).

Verified full async job lifecycle: instant route response, `PENDING → SUCCESS` transition, real progress logs in an isolated worker process.

### Day 9 — Full Docker Compose Integration

Confirmed all four services (api, db, redis, worker) correctly healthchecked and dependency-ordered. Added `.dockerignore` and `scripts\dev.bat`.

**Bug — migrations aren't automatically reapplied after a volume wipe.** After `down -v`, `/test-create-user` failed with `Internal Server Error` because the fresh database had no `users` table. A real, easy-to-forget onboarding gap — fixed by scripting `alembic upgrade head` into `scripts\dev.bat reset`.

### Day 10 — Pytest Fixtures, Celery Eager Mode, GitHub Actions CI

Added `db_session` fixture using transaction rollback for test isolation (fast, no leftover state between tests, no second database needed) and real integration tests hitting live Postgres — a genuinely different check from Day 5's mocked tests. Added Celery eager-mode testing (`task_always_eager`) so task logic can be tested without a real broker round trip.

Fixed a real `datetime.utcnow()` deprecation warning across all models before it could spread further.

**GitHub Actions CI, verified green** — Postgres and Redis as real service containers, migrations run automatically, full suite executed on every push.

### Day 11 — LangGraph Fundamentals

Learned nodes, fixed edges, state merging, and two flavors of conditional routing (`set_conditional_entry_point` vs. `add_conditional_edges` from a node) with deliberately trivial, non-agent graphs before building anything real. Built a 3-node dummy-decision graph as a direct structural precursor to the real router.

### Day 12 — Real Groq LLM Wired Into LangGraph

Replaced hardcoded routing logic with a genuine async LLM call (`llm.ainvoke`, temperature=0 for deterministic classification), with mandatory try/except fail-safe.

**Bug — `core/config.py` lost its `pydantic_settings` import**, causing `NameError: BaseSettings is not defined` — a reminder that edits to files not recently touched deserve a full read, not just an addition.

### Day 13 — The Planner Node

Built `Plan` (Pydantic structured output via `with_structured_output`) with the same fail-safe pattern as every LLM-calling node since.

**Quality bug, not a crash bug — caught by reading output critically.** The initial prompt's "2 to 5 steps" minimum forced an absurd 3-step research plan for "what is the capital of France," even though the router correctly recognized the same query needed no tool at all. Fixed by adding an explicit single-step escape hatch for trivially simple queries, verified the fix didn't degrade quality on genuinely complex queries.

### Day 14 — Per-Step Router with Looping Graph

Restructured the graph to process `plan_steps` one at a time via a genuine loop (`router` node conditionally routing back to itself via `current_step_index`), replacing Day 12's single whole-query decision.

**Architectural gap caught by reading output critically.** The router initially judged every step in isolation, routing all steps to `web_search` even when later steps were clearly reasoning-over-already-gathered-data tasks. Fixed by threading `state["step_results"]` from prior iterations into the router's prompt — verified the fix produced a genuinely sensible gather→gather→analyze→compare pattern.

### Day 15 — Real Web Search Tool + First End-to-End Run

Wired in real async Tavily search, replacing the fake placeholder. **First complete end-to-end agent run** — planner → per-step router loop → real search → synthesis — against a genuinely current real-world query.

**Bug — `synthesize_node` was pure string concatenation, not real synthesis.** Fixed with a genuine LLM call and an explicit instruction to note gaps rather than fabricate. Verified the agent correctly reported a real data gap (missing Max pricing) as missing rather than hallucinating a plausible number — the first proof of the project's honesty property under real conditions.

### Day 16 — Circuit Breaker Part 1: Iteration, Cost, Runtime Limits

Added soft cost estimation (explicitly labeled as approximate, not billing-accurate) and three tracked limits checked at the top of every router iteration. On limit hit: forces `current_step_index` to plan end, reusing the existing loop-exit path rather than new control flow.

**Verified with a forced trigger** (`MAX_ITERATIONS=2`) — breaker correctly stopped a 5-step plan after 2 iterations, final answer explicitly and accurately flagged both the early stop and the incompleteness of even the partial data gathered.

### Day 17 — Circuit Breaker Fully Verified + Agent Wired Into Real HTTP Route

Force-tested the cost breaker (`MAX_COST_USD=0.0001`) and timeout breaker (`MAX_RUNTIME_SECONDS=1`) independently — both confirmed triggering correctly with honest partial answers.

**Bug — `agent/` folder never added to Dockerfile `COPY` list or Compose volume mounts**, since it didn't exist when those files were originally written. `ModuleNotFoundError` in both `api` and `worker`. Same "new folder, multiple places to update" category as Day 3's reload-scope bug and Day 8's Celery `include` bug.

Added `workers/agent_tasks.py` (Celery task, `asyncio.run()` bridging the sync Celery boundary into async LangGraph) and `POST /agent/run` / `GET /agent/run/{job_id}` routes. **Full end-to-end verification via real HTTP**: a genuine multi-iteration run with real cost, correctly stopped-early runs when limits hit, and a normal complete run producing an honest, gap-aware synthesized answer.

### Day 18 — SQL Tool: Two-Layer Safety, Three Real Bugs Found and Fixed

Built `agent/tools/sql_query.py` with regex-based SELECT-only validation plus a database-level read-only Postgres role (`readonly_agent`) as independent defense in depth.

**Bug 1 — the read-only role didn't survive a volume reset.** Created manually via `psql`, it isn't tracked as code the way the schema is via Alembic. Fixed by moving role creation into a proper migration with an idempotent `DO $$ IF NOT EXISTS` guard — now genuinely reproducible, not a fragile manual step.

**Bug 2 — the router generated syntactically valid but semantically wrong SQL.** Lowercase `'failed'`/`'completed'` against the actual uppercase `RunStatus` enum values. A different category of prompt bug from Day 13's vagueness issue — this one about factual precision regarding the real schema, not reasoning quality. Fixed by specifying exact enum casing in the router's prompt.

**Bug 3 — a genuinely subtle async architecture bug.** A module-level SQLAlchemy engine, created once at import time, broke on the second Celery task execution: `asyncpg` connections bind to a specific event loop, and `asyncio.run()` (used to bridge sync Celery into async LangGraph) creates a fresh loop per task. Fixed by creating and disposing the engine fresh per call rather than as a shared singleton — a transferable lesson about event-loop-bound resources in any Celery-plus-async context.

**Verified full correctness end-to-end** with real data: all four SQL-driven plan steps succeeded, synthesis correctly computed a failure rate and average cost from genuine query results. Reconfirmed the honesty property under two different real infrastructure failures (an auth failure, then the event-loop bug) — the agent never fabricated data, always correctly diagnosed and reported the actual failure both times.

---

## Roadmap

- [x] Day 1 — FastAPI + Docker skeleton
- [x] Day 2 — Async patterns, Pydantic Settings, dependency injection
- [x] Day 3 — PostgreSQL + async SQLAlchemy + Alembic
- [x] Day 4 — Full schema design
- [x] Day 5 — Repository Pattern + Clean Architecture
- [x] Day 6 — Clerk authentication + JWT middleware
- [x] Day 7 — Redis + Week 1 revision
- [x] Day 8 — Celery background jobs
- [x] Day 9 — Full Docker Compose integration
- [x] Day 10 — Testing + CI pipeline
- [x] Day 11 — LangGraph fundamentals
- [x] Day 12 — Real LLM wired into LangGraph
- [x] Day 13 — Planner node with structured output
- [x] Day 14 — Per-step router with looping graph
- [x] Day 15 — Real web search tool + first end-to-end run
- [x] Day 16 — Circuit breaker part 1 (iteration, cost, runtime limits)
- [x] Day 17 — Circuit breaker verified + agent wired into HTTP route
- [x] Day 18 — SQL tool with two-layer safety
- [ ] Day 19 — RAG tool (Qdrant + embeddings)
- [ ] Day 20 — Persist agent runs into the database schema
- [ ] Days 21–22 — Full agent execution already runs via Celery (done Day 17) — extending with proper run/step persistence
- [ ] Days 23–24 — Streaming the agent's live reasoning trace (WebSocket/SSE)
- [ ] Beyond Week 4 — long-term memory tiers, observability (LangSmith, OpenTelemetry, Prometheus, Grafana, Sentry), production deployment, load testing, Next.js frontend
