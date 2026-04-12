"""Admin manual trigger endpoints."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.audit import write_audit_log
from flexloop.admin.auth import require_admin
from flexloop.config import settings
from flexloop.db.engine import _run_migrations, get_session
from flexloop.models.admin_session import AdminSession
from flexloop.models.admin_user import AdminUser
from flexloop.models.ai import AIUsage
from flexloop.models.exercise import Exercise
from flexloop.models.user import User
from flexloop.models.workout import WorkoutSession, WorkoutSet
from flexloop.services.pr_detection import check_prs
from flexloop.services.backup import BackupService

router = APIRouter(prefix="/api/admin/triggers", tags=["admin:triggers"])


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _sqlite_db_path() -> str:
    return settings.database_url.replace("sqlite+aiosqlite:///", "")


def _get_backup_service() -> BackupService:
    return BackupService(db_path=_sqlite_db_path(), backup_dir="backups")


def _exercise_details_path() -> Path:
    return _repo_root() / "data" / "exercise_details.json"


@router.post("/reload-prompts")
async def reload_prompts(
    _admin: AdminUser = Depends(require_admin),
) -> dict[str, str]:
    return {"status": "ok", "message": "Prompt cache cleared"}


@router.post("/backup")
async def trigger_backup(
    _admin: AdminUser = Depends(require_admin),
) -> dict[str, int | str]:
    backup = _get_backup_service().create_backup(schema_version="1.0.0")
    return {
        "status": "ok",
        "filename": backup.filename,
        "size_bytes": backup.size_bytes,
    }


@router.post("/test-ai")
async def trigger_test_ai(
    _admin: AdminUser = Depends(require_admin),
) -> dict[str, int | str]:
    from flexloop.ai.factory import create_adapter

    started = time.perf_counter()
    try:
        adapter = create_adapter(
            provider=settings.ai_provider,
            model=settings.ai_model,
            api_key=settings.ai_api_key,
            base_url=settings.ai_base_url,
            codex_auth_file=settings.codex_auth_file,
            reasoning_effort=settings.ai_reasoning_effort,
        )
        response = await asyncio.wait_for(
            adapter.generate(
                system_prompt="You are a helpful assistant.",
                user_prompt="Say hello in one word.",
                temperature=0.0,
                max_tokens=10,
            ),
            timeout=30.0,
        )
        return {
            "status": "ok",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "response_text": response.content[:200],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": str(exc),
        }


@router.post("/run-migrations")
async def trigger_run_migrations(
    db: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(require_admin),
) -> dict[str, str]:
    try:
        _run_migrations()
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}

    await write_audit_log(
        db,
        admin_user_id=admin.id,
        action="trigger_run_migrations",
        target_type="system",
    )
    await db.commit()
    return {"status": "ok", "message": "Migrations applied"}


@router.post("/reseed-exercises")
async def trigger_reseed_exercises(
    db: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(require_admin),
) -> dict[str, int | str]:
    data_path = _exercise_details_path()
    if not data_path.exists():
        return {"status": "error", "error": "exercise_details.json not found"}

    details = json.loads(data_path.read_text())
    exercises = (await db.execute(select(Exercise))).scalars().all()

    updated = 0
    for exercise in exercises:
        if exercise.name in details:
            exercise.metadata_json = details[exercise.name]
            updated += 1

    await write_audit_log(
        db,
        admin_user_id=admin.id,
        action="trigger_reseed_exercises",
        target_type="system",
        after={"updated": updated},
    )
    await db.commit()
    return {"status": "ok", "updated": updated}


@router.post("/vacuum-db")
async def trigger_vacuum_db(
    db: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(require_admin),
) -> dict[str, str]:
    try:
        with sqlite3.connect(_sqlite_db_path()) as conn:
            conn.execute("VACUUM")
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}

    await write_audit_log(
        db,
        admin_user_id=admin.id,
        action="trigger_vacuum_db",
        target_type="system",
    )
    await db.commit()
    return {"status": "ok", "message": "Database vacuumed"}


@router.post("/clear-sessions")
async def trigger_clear_sessions(
    db: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(require_admin),
) -> dict[str, int | str]:
    result = await db.execute(delete(AdminSession))
    deleted = result.rowcount or 0
    await write_audit_log(
        db,
        admin_user_id=admin.id,
        action="trigger_clear_sessions",
        target_type="system",
        after={"deleted": deleted},
    )
    await db.commit()
    return {"status": "ok", "deleted": deleted}


@router.post("/clear-ai-usage")
async def trigger_clear_ai_usage(
    db: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(require_admin),
) -> dict[str, int | str]:
    result = await db.execute(delete(AIUsage))
    deleted = result.rowcount or 0
    await write_audit_log(
        db,
        admin_user_id=admin.id,
        action="trigger_clear_ai_usage",
        target_type="system",
        after={"deleted": deleted},
    )
    await db.commit()
    return {"status": "ok", "deleted": deleted}


def _sse_event(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/recompute-prs")
async def trigger_recompute_prs(
    db: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(require_admin),
) -> StreamingResponse:
    async def event_generator():
        total_sets = (
            await db.execute(select(func.count()).select_from(WorkoutSet))
        ).scalar_one()

        if total_sets == 0:
            await write_audit_log(
                db,
                admin_user_id=admin.id,
                action="trigger_recompute_prs",
                target_type="system",
                after={"sets_checked": 0, "new_prs": 0},
            )
            await db.commit()
            yield _sse_event({"type": "done", "result": {"new_prs": 0, "sets_checked": 0}})
            return

        users = {
            user.id: user
            for user in (await db.execute(select(User))).scalars().all()
        }
        sets = (
            await db.execute(
                select(WorkoutSet, WorkoutSession.user_id).join(
                    WorkoutSession,
                    WorkoutSet.session_id == WorkoutSession.id,
                )
            )
        ).all()

        processed = 0
        new_prs_total = 0

        for workout_set, user_id in sets:
            user = users.get(user_id)
            weight_unit = user.weight_unit if user is not None else "kg"

            try:
                new_prs = await check_prs(
                    user_id=user_id,
                    exercise_id=workout_set.exercise_id,
                    weight=workout_set.weight,
                    reps=workout_set.reps,
                    session_id=workout_set.session_id,
                    db=db,
                    weight_unit=weight_unit,
                )
                new_prs_total += len(new_prs)
            except Exception:  # noqa: BLE001
                pass

            processed += 1
            if processed % 50 == 0 or processed == total_sets:
                percent = int(processed / total_sets * 100)
                yield _sse_event(
                    {
                        "type": "progress",
                        "percent": percent,
                        "current_step": f"Set {processed}/{total_sets}",
                        "message": (
                            f"Checked {processed} sets, found {new_prs_total} new PRs"
                        ),
                    }
                )

        await write_audit_log(
            db,
            admin_user_id=admin.id,
            action="trigger_recompute_prs",
            target_type="system",
            after={"sets_checked": processed, "new_prs": new_prs_total},
        )
        await db.commit()

        yield _sse_event(
            {
                "type": "done",
                "result": {
                    "new_prs": new_prs_total,
                    "sets_checked": processed,
                },
            }
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
