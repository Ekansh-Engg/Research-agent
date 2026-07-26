from fastapi import FastAPI
import time
import asyncio
from fastapi import Depends
from core.dependencies import get_settings
from core.config import Settings
from sqlalchemy.ext.asyncio import AsyncSession
from core.db import get_db
from repositories.user_repository import create_user, get_user_by_email
from services.user_service import get_or_create_user
from core.security import get_current_user_id
from core.cache import cache_get, cache_set
from celery.result import AsyncResult

from workers.celery_app import celery_app
from workers.tasks import simulate_long_task

from workers.agent_tasks import run_research_agent
from repositories.user_repository import get_user_by_email, create_user
from repositories.user_repository import get_user_by_email, create_user
from core.models import Org
from sqlalchemy import select

app=FastAPI(title="Research agent API")

@app.get("/health")
async def health():
    return {"status":"ok" ,"service": "research-agent"}

@app.get("/slow-sync")
def slow_sync():
    time.sleep(3)
    return {"done": "sync"}


@app.get("/slow-async")
async def slow_async():
    await asyncio.sleep(3)
    return {"done": "async"}

@app.get("/config-check")
async def config_check(settings: Settings = Depends(get_settings)):
    return {"app_name": settings.app_name, "environment": settings.environment}

@app.post("/test-create-user")
async def test_create_user(email: str, db: AsyncSession = Depends(get_db)):
    user, was_created = await get_or_create_user(db, email)
    return {"created": was_created, "id": str(user.id), "email": user.email}




@app.get("/me")
async def me(user_id: str = Depends(get_current_user_id)):
    cache_key = f"user_claims:{user_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return {"user_id": cached["user_id"], "source": "cache"}

    await cache_set(cache_key, {"user_id": user_id}, ttl_seconds=30)
    return {"user_id": user_id, "source": "db"}



@app.post("/trigger-task")
async def trigger_task(duration: int = 5):
    task = simulate_long_task.delay(duration)
    return {"job_id": task.id}


@app.get("/task-status/{job_id}")
async def task_status(job_id: str):
    result = AsyncResult(job_id, app=celery_app)
    return {
        "job_id": job_id,
        "status": result.status,
        "result": result.result if result.ready() else None,
    }





async def _get_or_create_placeholder_org(db: AsyncSession) -> "Org":
    result = await db.execute(select(Org).where(Org.name == "Default Org"))
    org = result.scalar_one_or_none()
    if org:
        return org
    org = Org(name="Default Org")
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org


@app.post("/agent/run")
async def start_agent_run(
    query: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    user = await get_user_by_email(db, f"{user_id}@clerk-placeholder.local")
    if not user:
        user = await create_user(db, f"{user_id}@clerk-placeholder.local")

    if not user.org_id:
        org = await _get_or_create_placeholder_org(db)
        user.org_id = org.id
        await db.commit()
        await db.refresh(user)

    task = run_research_agent.delay(query, str(user.org_id), str(user.id))
    return {"job_id": task.id}

@app.get("/agent/run/{job_id}")
async def get_agent_run_status(job_id: str):
    result = AsyncResult(job_id, app=celery_app)
    return {
        "job_id": job_id,
        "status": result.status,
        "result": result.result if result.ready() else None,
    }

