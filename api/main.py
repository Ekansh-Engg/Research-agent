from fastapi import FastAPI

app=FastAPI(title="Research agent API")

@app.get("/health")
async def health():
    return {"status":"ok" ,"service": "research-agent"}