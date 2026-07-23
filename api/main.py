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