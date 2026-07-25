import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from core.config import settings

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


def is_safe_select(sql: str) -> bool:
    stripped = sql.strip().rstrip(";")
    if not stripped.upper().startswith("SELECT"):
        return False
    if _FORBIDDEN_KEYWORDS.search(stripped):
        return False
    if ";" in stripped:
        return False
    return True


async def sql_query(sql: str) -> str:
    if not is_safe_select(sql):
        return f"[query rejected -- only single SELECT statements are permitted: {sql}]"

    # Engine created fresh per call, not as a module-level singleton --
    # asyncpg connections bind to the event loop active when they're created,
    # and Celery's asyncio.run() creates a new loop per task. A shared engine
    # would break on the second task run in the same worker process.
    engine = create_async_engine(settings.readonly_database_url, pool_pre_ping=True)

    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(sql))
            rows = result.fetchall()
            columns = result.keys()
    except Exception as e:
        print(f"SQL query failed: {e}")
        return f"[query failed: {e}]"
    finally:
        await engine.dispose()

    if not rows:
        return "[query returned no rows]"

    formatted_rows = [dict(zip(columns, row)) for row in rows[:20]]
    return str(formatted_rows)