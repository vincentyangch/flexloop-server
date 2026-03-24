from contextlib import asynccontextmanager

from fastapi import FastAPI

from flexloop.db.engine import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="FlexLoop API",
    description="AI-powered fitness training companion",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
