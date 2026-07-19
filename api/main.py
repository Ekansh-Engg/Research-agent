from fastapi import FastAPI
import time
import asyncio
from fastapi import Depends
from core.dependencies import get_settings
from core.config import Settings


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

from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from repositories.user_repository import create_user, get_user_by_email


@app.post("/test-create-user")
async def test_create_user(email: str, db: AsyncSession = Depends(get_db)):
    existing = await get_user_by_email(db, email)
    if existing:
        return {"created": False, "id": str(existing.id), "email": existing.email}

    user = await create_user(db, email)
    return {"created": True, "id": str(user.id), "email": user.email}