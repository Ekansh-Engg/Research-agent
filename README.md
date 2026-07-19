\# Research Agent — Autonomous Research/Data Analyst Agent



An enterprise-grade AI agent platform that plans, executes, and self-corrects multi-step research tasks using tool calling, RAG, and long-term memory — built to demonstrate production AI engineering practices, not just a demo chatbot.



\## Tech Stack



\- \*\*Backend:\*\* FastAPI (async), Python 3.12

\- \*\*Agent orchestration:\*\* LangGraph \*(coming Week 3)\*

\- \*\*Database:\*\* PostgreSQL + async SQLAlchemy + Alembic \*(coming Day 3)\*

\- \*\*Cache / Queue broker:\*\* Redis + Celery \*(coming Day 7–8)\*

\- \*\*Vector DB:\*\* Qdrant \*(coming later)\*

\- \*\*Package management:\*\* uv

\- \*\*Containerization:\*\* Docker + Docker Compose



\## Project Structure



```

research-agent/

├── api/              # Route handlers only — no business logic

├── services/         # Business logic layer

├── repositories/      # Database access layer

├── core/             # Config, DI providers, security

├── schemas/          # Pydantic request/response models

├── workers/           # Celery background tasks

├── tests/

├── Dockerfile

└── docker-compose.yml

```



This follows Clean Architecture / Repository Pattern conventions: routes call services, services call repositories, nothing talks directly to the database except the repository layer. Details on why in the build log below.



\## Getting Started



\*\*Prerequisites:\*\* Docker Desktop, `uv`



```bash

git clone <your-repo-url>

cd research-agent

docker compose up --build

```



Once running:

\- API: http://localhost:8000

\- Interactive docs (Swagger UI): http://localhost:8000/docs

\- Health check: http://localhost:8000/health



\*\*Running tests:\*\*

```bash

uv run pytest

```



\*\*Local dev without Docker\*\* (for quick iteration):

```bash

uv sync

uv run uvicorn api.main:app --reload --reload-dir api --port 8000

```



\## Build Log



Documenting real decisions and real bugs as I go — including the ones that didn't work on the first try. Treating this as a learning artifact, not a highlight reel.



\### Day 1 — FastAPI Skeleton + Docker



Built a minimal FastAPI app (`/health` endpoint), proven first on bare Windows, then containerized with a multi-stage Dockerfile.



\*\*Why multi-stage Docker:\*\* the `builder` stage installs dependencies via `uv sync`; the final runtime image only copies the resulting `.venv` and application code — no build tooling ships in production, keeping the image smaller and reducing attack surface.



\*\*Bug — `--reload` watching the entire project by default.\*\* Uvicorn's `--reload` flag watches the whole working directory unless scoped, which meant it was picking up file-timestamp changes inside `.venv/` (thousands of installed package files) and triggering endless, pointless server restarts. Fixed by scoping the watcher: `--reload-dir api`.



\*\*Cross-platform dependency resolution surprised me.\*\* `uv add fastapi uvicorn\[standard]` installed 19 packages on bare Windows — no `uvloop` (it doesn't support Windows). The exact same `uv.lock` file, built inside the Linux-based Docker image, resolved 20 packages, correctly adding `uvloop` since the container runs Linux. Same lockfile, different resolved packages, per-platform — this is `uv` working as intended, not a bug, but worth understanding rather than being confused by if the package counts don't match across environments.



\### Day 2 — Async Patterns, Pydantic Settings, Dependency Injection



\*\*Load-tested sync vs. async routes empirically instead of just trusting the theory.\*\* Added two throwaway routes (`/slow-sync` using `time.sleep`, `/slow-async` using `asyncio.sleep`) and fired concurrent requests at both using PowerShell's `ForEach-Object -Parallel`.



At 15 concurrent requests, both performed identically (\~3.0–3.5s each) — which initially contradicted my assumption that sync would visibly block. The correction: FastAPI runs sync `def` routes in a threadpool (via Starlette/AnyIO), not on a single blocking thread, so low concurrency doesn't reveal any difference.



Pushed to 60 concurrent requests and found the real boundary: sync routes split cleanly into two batches — the first \~40 finished around 3.0s, the remaining \~20 queued and finished at 5.0–5.2s, once the threadpool was exhausted. Async routes stayed flat at \~3.0s across all 60 requests, since they don't depend on a fixed thread pool at all.



\*\*Takeaway for this project specifically:\*\* every I/O-bound operation (LLM calls, tool calls, DB queries) in the agent service needs to be genuinely `async def` with real `await`, not a sync function relying on the threadpool to paper over scale. The threadpool has a hard ceiling; the event loop doesn't.



\*\*Bug — dependency changes don't hot-reload through Docker volume mounts.\*\* Ran `uv add pydantic-settings` on the host, which updated `pyproject.toml`/`uv.lock` locally — but the running container's `.venv` was baked in at image-build time and had no idea a new package existed. Got `ModuleNotFoundError: No module named 'pydantic\_settings'` despite the package clearly being installed on the host. The distinction that matters: \*\*code changes\*\* (inside the volume-mounted folders) hot-reload live; \*\*dependency changes\*\* require a full `docker compose up --build` to re-run `uv sync` inside the image. Volume mounts don't touch `.venv` at all.



\*\*Bug — pytest couldn't resolve `api.main` imports.\*\* `from api.main import app` failed with `ModuleNotFoundError: No module named 'api'` because pytest doesn't automatically add the project root to `sys.path` when packages lack `\_\_init\_\_.py` files. Fixed with `pythonpath = \["."]` under `\[tool.pytest.ini\_options]` in `pyproject.toml`.



\*\*Why dependency injection over direct imports:\*\* proved this concretely with a test, not just by asserting it. A route depending on `Depends(get\_settings)` can have that dependency swapped for a fake `Settings` object in a test (`app.dependency\_overrides\[get\_settings] = fake\_settings`) without touching any route code. A route that directly imported `settings` from `core.config` would have no clean way to substitute it in a test.

### Day 3 — PostgreSQL + Async SQLAlchemy + Alembic Migrations

Added Postgres to the stack, wired up async SQLAlchemy 2.0, and got Alembic generating real migrations against live models — no manual schema hand-writing.

**Docker Compose healthcheck prevents a real race condition.** Used `depends_on: condition: service_healthy` (not plain `depends_on`) so the `api` container waits for Postgres to actually pass `pg_isready`, not just for the container to start. Confirmed this works — the logs show `api-1` only begins startup after `Container research-agent-db-1 Healthy` appears.

**Named volume (`pgdata`) proven to persist data across restarts.** After a `docker compose down` and `up`, Postgres logged `PostgreSQL Database directory appears to contain a database; Skipping initialization` — confirming the `users` table and its data survived the restart, as intended.

**Used SQLAlchemy 2.0's typed declarative style** (`Mapped[...]`, `mapped_column(...)`) instead of the older `Column()` syntax — gives real type-checking on model attributes instead of `Any`.

**Alembic configured to use the app's actual settings, not a separate hardcoded URL.** Overrode `config.set_main_option("sqlalchemy.url", settings.database_url)` in `migrations/env.py` right after `config = context.config`, so `.env` stays the single source of truth for the connection string instead of duplicating it inside `alembic.ini`.

**Bug — reload scope didn't cover new folders as the project grew.** Day 1's `--reload-dir api` scoping only watched the `api/` folder. Adding `repositories/user_repository.py` didn't trigger a reload, and worse, the container's next restart threw `ModuleNotFoundError: No module named 'repositories.user_repository'` — looked like a missing-file bug at first, but the file was there; uvicorn just hadn't been told to watch that directory. Fixed by adding a `--reload-dir` flag per source folder (`api`, `core`, `repositories`, `services`, `schemas`, `workers`) in the Compose `command`.

**Proved the full stack round-trip, not just that it "should" work.** Built a throwaway `/test-create-user` route and called it twice with the same email — first call returned `"created": true` with a fresh UUID, second call returned `"created": false` with the *same* UUID, confirming `get_user_by_email` correctly deduplicated instead of inserting a second row. Verified independently via `docker exec ... psql -c "\dt"` that the `users` table (and Alembic's own `alembic_version` bookkeeping table) genuinely exist in Postgres, rather than just trusting Alembic's own success message.


\## Roadmap



\- \[x] Day 1 — FastAPI + Docker skeleton

\- \[x] Day 2 — Async patterns, Pydantic Settings, dependency injection

\- \[x] Day 3 — PostgreSQL + async SQLAlchemy + Alembic

\- \[ ] Day 4 — Full schema design

\- \[ ] Day 5 — Repository Pattern + Clean Architecture

\- \[ ] Day 6 — Clerk authentication + JWT middleware

\- \[ ] Day 7 — Redis + Week 1 revision

\- \[ ] Day 8 — Celery background jobs

\- \[ ] Day 9 — Full Docker Compose integration

\- \[ ] Day 10 — Testing + CI pipeline



