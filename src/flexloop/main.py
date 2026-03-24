from contextlib import asynccontextmanager

from fastapi import FastAPI

from flexloop.db.engine import init_db
from flexloop.routers.ai import router as ai_router
from flexloop.routers.backup import router as backup_router
from flexloop.routers.data import router as data_router
from flexloop.routers.exercises import router as exercises_router
from flexloop.routers.measurements import router as measurements_router
from flexloop.routers.profiles import router as profiles_router
from flexloop.routers.progress import router as progress_router
from flexloop.routers.prs import router as prs_router
from flexloop.routers.sync import router as sync_router
from flexloop.routers.templates import router as templates_router
from flexloop.routers.workouts import router as workouts_router


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

app.include_router(profiles_router)
app.include_router(exercises_router)
app.include_router(workouts_router)
app.include_router(templates_router)
app.include_router(measurements_router)
app.include_router(ai_router)
app.include_router(data_router)
app.include_router(backup_router)
app.include_router(sync_router)
app.include_router(prs_router)
app.include_router(progress_router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
