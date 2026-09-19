import asyncio
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import os
from datetime import datetime

app = FastAPI(title="Rubux Keep-Alive")
START_TIME = datetime.now()
_last_ping = {"time": None, "source": None}


@app.get("/")
@app.get("/health")
async def health():
    return {
        "status": "alive",
        "uptime_sec": int((datetime.now() - START_TIME).total_seconds()),
        "last_ping": _last_ping["time"],
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/health/deep")
async def health_deep():
    import db
    try:
        await db.q("SELECT 1", (), "one")
        db_ok = True
    except Exception:
        db_ok = False

    try:
        import redis.asyncio as aioredis
        import config
        r = aioredis.from_url(config.REDIS_URL)
        await r.ping()
        await r.close()
        redis_ok = True
    except Exception:
        redis_ok = False

    status = "ok" if (db_ok and redis_ok) else "degraded"
    return JSONResponse(
        {"status": status, "db": db_ok, "redis": redis_ok,
         "timestamp": datetime.now().isoformat()},
        status_code=200 if status == "ok" else 503,
    )


@app.get("/ping")
async def ping(source: str = "unknown", x_ping_secret: str = Header(None)):
    import config
    if x_ping_secret and x_ping_secret != config.PING_SECRET:
        raise HTTPException(403, "Bad secret")
    _last_ping["time"] = datetime.now().isoformat()
    _last_ping["source"] = source
    return {"pong": True, "time": _last_ping["time"]}


async def run_keep_alive(port: int = None):
    port = port or int(os.getenv("PORT", "8080"))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()


async def start_in_background(port: int = None):
    task = asyncio.create_task(run_keep_alive(port))
    return task
