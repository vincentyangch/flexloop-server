# Install the admin ring-buffer log handler BEFORE any flexloop imports so
# that early-startup log records (model registration, DB init, router import
# side effects) flow into the buffer. Only stdlib imports may appear above.
import logging

from flexloop.admin.log_handler import admin_ring_buffer

logging.getLogger().addHandler(admin_ring_buffer)
logging.getLogger().setLevel(logging.INFO)

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from flexloop.admin.csrf import OriginCheckMiddleware
from flexloop.admin.routers.auth import router as admin_auth_router
from flexloop.admin.routers.health import router as admin_health_router
from flexloop.admin.routers.users import router as admin_users_router
from flexloop.db.engine import init_db
from flexloop.routers.ai import router as ai_router
from flexloop.routers.backup import router as backup_router
from flexloop.routers.cycle import router as cycle_router
from flexloop.routers.data import router as data_router
from flexloop.routers.deload import router as deload_router
from flexloop.routers.exercises import router as exercises_router
from flexloop.routers.measurements import router as measurements_router
from flexloop.routers.plans import router as plans_router
from flexloop.routers.profiles import router as profiles_router
from flexloop.routers.progress import router as progress_router
from flexloop.routers.prs import router as prs_router
from flexloop.routers.sync import router as sync_router
from flexloop.routers.warmup import router as warmup_router
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

# Add CSRF middleware BEFORE routers so it runs on every /api/admin/* request.
# For Phase 1: fixed allowed-origins list. Phase 4 will replace this callable
# with one that reads from app_settings.admin_allowed_origins.
_PHASE1_ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:8000"]
app.add_middleware(
    OriginCheckMiddleware,
    allowed_origins_getter=lambda: _PHASE1_ALLOWED_ORIGINS,
)

app.include_router(profiles_router)
app.include_router(exercises_router)
app.include_router(workouts_router)
app.include_router(measurements_router)
app.include_router(plans_router)
app.include_router(cycle_router)
app.include_router(ai_router)
app.include_router(data_router)
app.include_router(backup_router)
app.include_router(sync_router)
app.include_router(prs_router)
app.include_router(progress_router)
app.include_router(warmup_router)
app.include_router(deload_router)
app.include_router(admin_auth_router)
app.include_router(admin_health_router)
app.include_router(admin_users_router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}


# Mount the built admin SPA bundle at /admin/*.
# In dev, you'd run `npm run dev` separately and the Vite dev server proxies
# to this FastAPI process. In prod, the bundle is prebuilt into static/admin.
_STATIC_ADMIN = Path(__file__).parent / "static" / "admin"
_ADMIN_INDEX = _STATIC_ADMIN / "index.html"

if _STATIC_ADMIN.exists():
    # Serve built assets (JS, CSS, images, fonts) at /admin/assets/...
    app.mount(
        "/admin/assets",
        StaticFiles(directory=_STATIC_ADMIN / "assets"),
        name="admin_assets",
    )

    @app.get("/admin")
    async def admin_root():
        if not _ADMIN_INDEX.exists():
            raise HTTPException(status_code=404, detail="admin UI not built")
        return FileResponse(_ADMIN_INDEX)

    @app.get("/admin/{path:path}")
    async def admin_spa_fallback(path: str):
        """Serve index.html for any /admin/* path (SPA client-side routing)."""
        if not _ADMIN_INDEX.exists():
            raise HTTPException(status_code=404, detail="admin UI not built")
        return FileResponse(_ADMIN_INDEX)
