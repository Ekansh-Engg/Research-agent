from fastapi import FastAPI,Depends, HTTPException, WebSocket, WebSocketDisconnect
import time
import json
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
from core.models import Org
from sqlalchemy import select
from uuid import UUID
from schemas.agent_run import AgentRunDetail, AgentRunSummary
from services.agent_run_service import get_run_detail, get_run_history
from core.pubsub import subscribe_to_progress
from fastapi.middleware.cors import CORSMiddleware 
from core.pubsub import get_buffered_events, subscribe_to_progress

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




@app.get("/agent/runs", response_model=list[AgentRunSummary])
async def list_runs(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
    limit: int = 20,
    offset: int = 0,
):
    user = await get_user_by_email(db, f"{user_id}@clerk-placeholder.local")
    if not user or not user.org_id:
        return []
    runs = await get_run_history(db, user.org_id, limit, offset)
    return runs


@app.get("/agent/runs/{run_id}", response_model=AgentRunDetail)
async def get_run(run_id: UUID, db: AsyncSession = Depends(get_db)):
    run = await get_run_detail(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return AgentRunDetail(
        id=run.id,
        query=run.query,
        status=run.status.value,
        cost_usd=run.cost_usd,
        iteration_count=run.iteration_count,
        created_at=run.created_at,
        steps=run.steps,
        report_content=run.report.content if run.report else None,
    )






@app.websocket("/ws/agent/run/{job_id}")
async def agent_run_progress_ws(websocket: WebSocket, job_id: str):
    await websocket.accept()

    # Replay anything that already happened before this client connected --
    # Redis Pub/Sub itself has no memory, so we buffer separately for this.
    buffered = await get_buffered_events(job_id)
    already_finished = False
    for payload in buffered:
        await websocket.send_text(payload)
        data = json.loads(payload)
        if data.get("event") in ("run_completed", "stopped_early"):
            already_finished = True

    if already_finished:
        await websocket.close()
        return

    pubsub = await subscribe_to_progress(job_id)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            await websocket.send_text(message["data"])
            data = json.loads(message["data"])
            if data.get("event") in ("run_completed", "stopped_early"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe()
        await pubsub.close()
        await websocket.close()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # their actual Next.js dev origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)