# Research Agent — Autonomous Research/Data Analyst Agent

An enterprise-grade AI agent platform that plans, executes, and self-corrects multi-step research tasks using tool calling (web search, structured SQL access, RAG), persistence, live streaming, and observability — built to demonstrate production AI engineering practices, not just a demo chatbot.

## Tech Stack

- **Backend:** FastAPI (async), Python 3.12
- **Agent orchestration:** LangGraph — explicit state machine, not an implicit agent-executor loop
- **LLM inference:** Groq (`llama-3.3-70b-versatile`), via `langchain-groq`
- **Observability:** LangSmith (full trace visibility into every LLM call, tool call, and decision)
- **Tools:** Tavily (real-time web search), a safety-validated SQL query tool against our own Postgres data, RAG retrieval via Qdrant + local BGE embeddings
- **Database:** PostgreSQL + async SQLAlchemy 2.0 + Alembic (schema *and* database roles/permissions)
- **Vector DB:** Qdrant (self-hosted)
- **Cache / Queue broker / Pub-Sub:** Redis (three distinct roles: caching, Celery broker, live-progress broadcasting)
- **Real-time streaming:** WebSocket + Redis Pub/Sub, relaying live agent progress from the Celery worker to any connected client
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
├── core/             # Config, DI providers, security, DB engine, cache, pubsub, models
├── schemas/          # Pydantic request/response models
├── workers/           # Celery tasks (background jobs + agent execution + persistence)
├── agent/            # LangGraph orchestration: graphs, tools, LLM client, schemas
├── migrations/         # Alembic migrations (schema AND database roles)
├── tests/
├── scripts/           # dev.bat — wraps common Docker/migration/test commands
├── test_ws.py         # Standalone WebSocket test client (curl can't test WebSockets)
├── Dockerfile
└── docker-compose.yml
```

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
- The `worker` service does **not** use `--reload` — code changes to anything the worker imports need `docker compose restart worker` at minimum, or a full rebuild if dependencies also changed.
- `uv` only exists in the Dockerfile's *builder* stage, not the runtime image — for one-off scripts inside a running container, use `.venv/bin/python -m <module>` directly, not `uv run`.
- On this project's setup, Docker Desktop's memory is managed by WSL2, not a Docker Desktop UI slider — configure via a `.wslconfig` file in the Windows user folder if memory limits ever need adjusting.

---

## Why These Decisions Were Made

### Why async everywhere, not just "where convenient"
Empirically proven necessary on Day 2: sync routes hit a hard threadpool ceiling under 60 concurrent requests (a ~3.0s vs. ~5.2s split), while async routes stayed flat. Agent runs make many sequential LLM/tool calls — every route, service, and agent node touching the database, an LLM, or an external API is `async def` with real `await`, for this reason specifically.

### Why LangGraph over a plain LangChain AgentExecutor
Plain agent-executor loops are implicit and hard to inspect or interrupt. LangGraph models the agent as a real state machine — explicit nodes, explicit conditional edges, explicit state. This is what made the Day 16–17 circuit breaker possible to bolt on cleanly, and what made Day 23's live-trace streaming feasible — you can observe and broadcast state transitions because they're explicit, not buried inside an opaque loop.

### Why the Repository Pattern / service layer, even for a project this size
Agent logic (Week 3+) needs to reuse the same data-access and business-decision logic that routes use. The layering also made services genuinely unit-testable with mocked repositories (Day 5) — a different, complementary kind of correctness check from the real-database integration tests (Day 10).

### Why every external credential goes through `docker-compose.yml`'s `environment:` block, not just `.env`
Discovered on Day 6: Compose's automatic `.env` reading only affects in-file variable substitution, not automatic container env injection. Every credential since (Groq, Tavily, LangSmith, the readonly DB role) follows the explicit `${VAR}` pattern in `environment:` because of this lesson.

### Why database roles/permissions are managed via Alembic migrations, not manual `psql` commands
Discovered on Day 18: a `readonly_agent` Postgres role created manually via `psql` does not survive a `docker compose down -v` volume wipe, while Alembic-managed schema does. **Confirmed fixed on Day 24** — after moving role creation into a proper idempotent migration, a genuine full reset (`scripts\dev.bat reset`) recreated the role automatically, with zero manual intervention, for the first time.

### Why the SQL tool has two independent layers of safety, not one
Application-level regex validation (reject non-SELECT, forbidden keywords, stacked statements) **and** a database-level read-only role as defense in depth — because application-level validation can have bugs or blind spots, while a database permission genuinely cannot be bypassed by clever prompting.

### Why every LLM-calling node has a fail-safe fallback, not a bare `except`
Starting Day 12, every node calling an LLM or tool degrades to a safe default on failure (plan fails → treat the query as one step; router fails → default to no tool) rather than crashing the whole graph run — because external API calls fail, and a multi-step run is expensive enough that a transient failure shouldn't discard all prior progress.

### Why any SQLAlchemy engine used inside a Celery task must be created fresh per call, never as a module-level singleton
This bit the project **twice** — Day 18 (the SQL tool's readonly engine) and again on Day 20 (`core/db.py`'s main engine, the first time it was ever exercised from inside a Celery task). `asyncpg` connections bind to the event loop active when they're created, and Celery's `asyncio.run()`-per-task pattern creates a fresh loop every execution. This is now a standing project rule, not a one-off patch: `core/db.py`'s shared engine remains correctly safe for FastAPI routes (one persistent loop for the process's life), but anything touching Celery's execution boundary creates and disposes its own engine per call.

### Why the circuit breaker reuses the existing loop-exit path instead of adding new control flow
When any limit (iterations, cost, runtime) is hit, `router_node` sets `stopped_early: True` and forces `current_step_index` to the plan's end, letting the graph's existing `has_more_steps` edge route to `synthesize` naturally — rather than throwing an exception or adding a parallel exit path.

**Known gap, surfaced Day 24:** the runtime check only fires *between* router iterations. A single internally-slow iteration (confirmed on Day 24: a cold embedding-model load consumed ~109 seconds inside one iteration) can blow past the time budget before the check ever gets a chance to catch it. The breaker protects against *too many* slow steps; it doesn't yet protect against one catastrophically slow step. Flagged as a real hardening candidate, not fixed yet.

### Why the agent is honest about partial results and gaps, not just "handled" errors
Verified repeatedly under real failure conditions — forced circuit-breaker triggers (Days 16–17), a real SQL auth failure (Day 18), a real async event-loop bug (Day 18/20), and even a case of genuinely limited but not-failed data (Day 21's synthesis correctly distinguishing which retrieved documents were actually relevant to the question asked) — the agent has never once fabricated a plausible-sounding answer when it should have expressed uncertainty. Treated as a genuine, demonstrated safety property of the system.

### Why Redis serves three distinct roles (cache, Celery broker, Pub/Sub) rather than three separate systems
All three usage patterns are legitimately different (store-and-retrieve, task-queue, broadcast) but Redis handles all three well, and running three separate pieces of infrastructure for a project this size would be unjustified complexity. Each usage lives in its own module (`core/cache.py`, `workers/celery_app.py`, `core/pubsub.py`) specifically so the *purpose* of each piece of code is obvious from its location, even though they share one underlying Redis instance.

### Why the embedding model needs a persistent cache volume, discovered the hard way
Day 24's full cold-start verification revealed that `sentence-transformers` re-downloads and reloads its ~133MB model on every fresh container, costing upward of 100 seconds — enough to consume nearly the entire circuit breaker budget on a single RAG-triggering step before any real work happened. Fixed with a shared `hf_cache` named volume mounted into both `api` and `worker`, so the cost is paid once per volume lifetime, not once per container rebuild.

---

## Build Log

Documenting real decisions and real bugs as they happened — including the ones that didn't work on the first try. Treating this as a learning artifact, not a highlight reel.

### Days 1–10 (Weeks 1–2 Summary)

Foundation work: FastAPI + Docker skeleton, empirically-proven async patterns, PostgreSQL + async SQLAlchemy + Alembic, full schema design, Repository Pattern + service layer formalized, Clerk JWT authentication, Redis caching, Celery background jobs, full Docker Compose integration with a dev script, and GitHub Actions CI — all independently verified via multiple full cold-start tests (`docker compose down -v` → rebuild → migrate → re-verify every endpoint). Real bugs found and fixed along the way included reload-scope gaps as new folders were added, Docker's dependency-vs-code-change distinction, a YAML self-dependency cycle, a Celery task-registration gap, and a forgotten post-reset migration step — each fixed and then folded into either code, config, or the dev script so it couldn't silently recur. *(Full day-by-day detail preserved in git history and earlier README versions.)*

### Days 11–17 (Week 3 Summary)

Built the actual agent: LangGraph fundamentals with deliberately trivial practice graphs, a real async Groq LLM wired into decision nodes with consistent fail-safe fallbacks, a structured-output planner (catching and fixing a real prompt-quality bug where trivial queries got forced into unnecessary multi-step plans), a genuinely looping per-step router (catching and fixing a real architectural gap where steps were judged in isolation with no awareness of prior results), a real Tavily web search tool proving the first complete end-to-end run, and a three-limit circuit breaker (iterations, cost, runtime) — each limit independently force-tested to confirm it actually triggers and produces an honest partial answer, not just reviewed as code. Closed the week by wiring the whole graph into a real Celery-backed HTTP route, catching a real Dockerfile/Compose gap (`agent/` never added to the `COPY`/volume lists) along the way.

### Day 18 — SQL Tool: Two-Layer Safety, Three Real Bugs Found and Fixed

Built a SQL query tool with regex-based SELECT-only validation plus a database-level read-only Postgres role as independent defense in depth.

**Bug 1** — the read-only role, created manually via `psql`, didn't survive a volume reset (unlike the Alembic-managed schema). Fixed by moving role creation into a proper idempotent migration.

**Bug 2** — the router generated syntactically valid but semantically wrong SQL (lowercase `'failed'` against the actual uppercase `RunStatus` enum values) — a prompt-precision bug, fixed by specifying exact enum casing in the router's prompt.

**Bug 3** — a subtle async architecture bug: a module-level SQLAlchemy engine broke on the second Celery task execution, since `asyncpg` connections bind to a specific event loop and `asyncio.run()` creates a fresh loop per task. Fixed by creating and disposing the engine fresh per call — this became a standing project rule (see decisions section above).

Verified full correctness end-to-end with real data, and reconfirmed the agent's honesty property under two different real infrastructure failures.

### Day 19 — RAG Tool (Qdrant + Embeddings)

Added Qdrant, a cached local BGE embedder, and document indexing/retrieval, giving the agent its third and final tool.

**Real infrastructure incident, correctly diagnosed rather than assumed:** a Postgres healthcheck failure after a genuine unclean shutdown looked alarming, but reading the actual logs showed normal WAL crash-recovery completing successfully — the healthcheck just ran out of retries slightly before recovery finished. Fixed the timing gap with `start_period: 30s`, not by touching anything data-related.

**Bug** — `AsyncQdrantClient.search()` was deprecated in the installed `qdrant-client` version in favor of `.query_points()` — a library API drift, not a code mistake, caught by reading the actual error rather than assuming the original code was right.

**Bug** — `uv` doesn't exist in the Dockerfile's runtime image (only the builder stage) — one-off in-container scripts need `.venv/bin/python -m <module>` directly.

Verified the full three-tool agent working together for the first time: correct tool selection across web search, SQL, and RAG within a single 5-step run, genuine cross-document synthesis, and the agent honestly flagging its own low-relevance-score uncertainty — unprompted.

### Day 20 — Persist Agent Runs Into the Database

Wired the graph into the `agent_runs`/`agent_steps`/`reports` schema (built Day 4, unused until now), following the same repository/service layering as every other table in the project.

**Bug (recurrence)** — `core/db.py`'s main engine hit the exact same event-loop-binding issue as Day 18's SQL tool engine, the first time it was ever exercised from inside a Celery task via `asyncio.run()`. Recognized as the same root-cause pattern rather than treated as a new mystery.

**Investigated and correctly ruled out a false lead** — an apparent OOM crash (exit code 137) was checked directly with `docker stats` before touching any system-level memory config, and genuinely ruled out (memory usage was well within limits) before the real cause (the event-loop bug above, and separately, a data-integrity bug below) was found.

**Bug** — a placeholder `org_id or user.id` fallback silently substituted a user's own ID where an org ID was required, correctly rejected by the `agent_runs_org_id_fkey` foreign key constraint — the database catching a real integrity problem exactly as designed. Fixed with a genuine get-or-create-default-org function, not another shortcut.

Verified full persistence correctness by cross-referencing the HTTP response's `run_id`, cost, and iteration count directly against independent database queries — exact match.

### Day 21 — Query Endpoints for Agent Run History

Added `GET /agent/runs` (list) and `GET /agent/runs/{run_id}` (detail) — the first time the project reads its own persisted history back through a typed API instead of only ever writing to Postgres and checking via raw `psql`. Introduced `selectinload` for relationship loading (avoiding lazy-load errors and N+1 queries) and the first real Pydantic response models in `schemas/agent_run.py`.

**Bug, likely resolved but not 100% conclusively root-caused** — the list route returned an empty reply with no visible server-side traceback, most likely an enum-vs-str mismatch during automatic ORM-to-Pydantic serialization. Fixed by switching to explicit response object construction (matching the pattern already proven correct on the detail route) — documented honestly as a principled fix for a strongly-suspected cause, not a definitively proven one.

### Day 22 — LangSmith Tracing

Wired in full observability via environment-variable configuration at `agent/llm.py`'s import time — no changes needed to any graph or node code, since LangGraph traces automatically once the right env vars are set.

**Real finding on the very first trace inspected:** a `web_search` step took 46.92 seconds total while its own LLM decision call took only 0.41 seconds — proving the bottleneck was Tavily's tool latency, not agent reasoning. By comparison, a `rag_retrieval` step completed a full iteration (LLM decision + real vector search) in 0.77 seconds. A genuine, evidence-backed performance characteristic of the system, discovered rather than assumed, and flagged as a candidate for a future per-tool timeout distinct from the whole-run circuit breaker.

### Day 23 — Streaming the Agent's Live Reasoning Trace

Built `core/pubsub.py` (Redis Pub/Sub, deliberately kept separate from the caching module despite sharing the same Redis instance, since the usage pattern is conceptually distinct) and instrumented every graph node to publish progress events. Threaded a `job_id` through graph state, sourced from Celery's own `self.request.id` via `bind=True`, guaranteeing the pub/sub channel and the client's existing polling ID always match. Added a WebSocket route that relays live events and closes cleanly on the run's terminal event.

**Verified with a real, separate WebSocket test client** (`curl` can't test WebSockets) connected while a real multi-step run executed inside a different container entirely — watched every event arrive live, in order, with correctly truncated previews. **Known limitation, documented not fixed:** Redis Pub/Sub has no replay — a subscriber connecting after a run completes misses everything, since pub/sub is broadcast-only, not a queue with memory.

### Day 24 — Full Week 4 Cold-Start Verification + Embedding Cache Fix

Ran a genuine `scripts\dev.bat reset` — full volume wipe, rebuild, re-migrate — to prove Days 18–23's work composes correctly together, not just individually. This was the first real test of the Day 18 role-migration fix via an actual reset: `readonly_agent` appeared automatically, with zero manual `psql` intervention, confirming the fix was real rather than theoretical.

**Real, precisely evidenced performance bug found via the fresh environment itself:** the first RAG-triggering agent run in the freshly-reset stack got cut short by the circuit breaker after only 1 of 4 planned steps, having spent nearly the entire 60-second budget on a single iteration. Worker logs pinpointed the exact cause down to the timestamp: cold-loading the `sentence-transformers` embedding model took ~109 seconds by itself, before any real embedding or search work happened — an entirely different container process from the one that had already downloaded the same model earlier that day (the `api` container's seed script), since Docker containers don't share filesystems by default. Fixed with a shared `hf_cache` named volume mounted into both `api` and `worker`. Verified before/after: from a run cut short after one step, to a full 4-step multi-tool run (RAG, web search, reasoning, SQL) completing well within budget, with a genuinely rich, honest synthesized answer spanning all three data sources.

Full test suite (6/6) reconfirmed passing against the freshly recreated database.

---

## Roadmap

- [x] Days 1–10 — Foundation: FastAPI, Docker, Postgres, Alembic, Repository Pattern, auth, Redis, Celery, full Compose integration, CI
- [x] Days 11–17 — Agent core: LangGraph fundamentals, real LLM routing, structured planning, looping per-step router, real web search tool, circuit breaker, Celery-backed HTTP route
- [x] Day 18 — SQL tool with two-layer safety
- [x] Day 19 — RAG tool (Qdrant + embeddings)
- [x] Day 20 — Persist agent runs into the database
- [x] Day 21 — Query endpoints for agent run history
- [x] Day 22 — LangSmith observability
- [x] Day 23 — Live streaming via WebSocket + Redis Pub/Sub
- [x] Day 24 — Full Week 4 cold-start verification + embedding cache fix
- [ ] Day 25 — Production deployment (Railway/Fly.io) — unblocks frontend work by a teammate against a real, live backend instead of requiring full local Docker setup
- [ ] Next.js frontend — in progress by a teammate, consuming `/agent/runs`, `/agent/runs/{run_id}`, and the WebSocket stream
- [ ] Long-term memory architecture (short-term/session/long-term tiers)
- [ ] Additional observability (OpenTelemetry, Prometheus, Grafana, Sentry)
- [ ] Load testing
- [ ] Per-tool timeout, distinct from the whole-run circuit breaker (informed by Day 22's real latency findings and Day 24's cold-start finding)