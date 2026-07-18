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