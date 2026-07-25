FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency files first (layer caching — only reinstalls if these change)
COPY pyproject.toml uv.lock ./

# Install dependencies into a project-local venv
RUN uv sync --frozen --no-dev

# ---- Runtime stage ----
FROM python:3.12-slim

WORKDIR /app

# Copy the installed venv from the builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY api ./api
COPY core ./core
COPY services ./services
COPY repositories ./repositories
COPY schemas ./schemas
COPY workers ./workers
COPY agent ./agent

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]