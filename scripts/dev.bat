@echo off
if "%1"=="up" (
    docker compose up
) else if "%1"=="build" (
    docker compose up --build
) else if "%1"=="down" (
    docker compose down
) else if "%1"=="reset" (
    docker compose down -v
    docker compose up --build -d
    timeout /t 8
    uv run alembic upgrade head
    docker compose logs -f
) else if "%1"=="migrate" (
    uv run alembic upgrade head
) else if "%1"=="test" (
    uv run pytest
) else if "%1"=="logs" (
    docker compose logs -f %2
) else (
    echo Usage: scripts\dev.bat [up^|build^|down^|reset^|migrate^|test^|logs SERVICE]
)