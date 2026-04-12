"""Admin config editor endpoints.

Three endpoints:
- GET  /api/admin/config                  masked read
- PUT  /api/admin/config                  validated update + audit log
- POST /api/admin/config/test-connection  tiny round-trip via the AI factory

The GET response always masks ``ai_api_key`` — the cleartext is never
echoed back. PUT accepts plaintext; if the incoming ``ai_api_key`` value
matches the masked form exactly, the server treats it as "no change" and
keeps the existing key.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.audit import write_audit_log
from flexloop.admin.auth import require_admin
from flexloop.ai.codex_auth import CodexAuthReader
from flexloop.ai.factory import create_adapter
from flexloop.config import refresh_settings_from_db, settings
from flexloop.db.engine import get_session
from flexloop.models.admin_user import AdminUser
from flexloop.models.app_settings import AppSettings

router = APIRouter(prefix="/api/admin/config", tags=["admin:config"])


# --- Schemas ---------------------------------------------------------------


class AppSettingsResponse(BaseModel):
    """GET /api/admin/config response shape.

    ``ai_api_key`` is always masked — the cleartext value stays on the
    server. A client that wants to "see" the key has to type it in again.
    """
    model_config = ConfigDict(from_attributes=False)

    ai_provider: str
    ai_model: str
    ai_api_key: str  # always masked
    ai_base_url: str
    codex_auth_file: str
    ai_reasoning_effort: str
    ai_temperature: float
    ai_max_tokens: int
    ai_review_frequency: str
    ai_review_block_weeks: int
    admin_allowed_origins: list[str]


class AppSettingsUpdate(BaseModel):
    """PUT /api/admin/config payload.

    All fields optional — partial update. ``ai_api_key`` accepts either
    a new plaintext value or the masked form returned by GET (treated as
    "leave unchanged"). Omitted fields are not touched.
    """
    model_config = ConfigDict(extra="forbid")

    ai_provider: str | None = None
    ai_model: str | None = None
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    codex_auth_file: str | None = None
    ai_reasoning_effort: str | None = None
    ai_temperature: float | None = None
    ai_max_tokens: int | None = None
    ai_review_frequency: str | None = None
    ai_review_block_weeks: int | None = None
    admin_allowed_origins: list[str] | None = None


class TestConnectionRequest(BaseModel):
    """POST /api/admin/config/test-connection payload.

    All fields optional — omitted fields fall back to the currently saved
    DB value, EXCEPT ``max_tokens`` which defaults to 10 (test calls should
    be cheap; override explicitly if you need a longer response).
    """
    model_config = ConfigDict(extra="forbid")

    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    codex_auth_file: str | None = None
    reasoning_effort: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class TestConnectionResponse(BaseModel):
    status: str  # "ok" | "error"
    latency_ms: int
    response_text: str | None
    error: str | None


class CodexStatusResponse(BaseModel):
    status: str
    file_exists: bool
    file_path: str
    auth_mode: str | None = None
    last_refresh: datetime | None = None
    days_since_refresh: float | None = None
    account_email: str | None = None
    error: str | None = None
    error_code: str | None = None


# --- Helpers ---------------------------------------------------------------


def _mask_key(key: str) -> str:
    """Return a masked form of an API key: bullets + last 3 chars.

    Empty string stays empty. Keys shorter than 3 chars are fully bulleted.
    """
    if not key:
        return ""
    if len(key) <= 3:
        return "\u2022" * len(key)  # • bullet
    return "\u2022" * (len(key) - 3) + key[-3:]


def _masked_dict(row: AppSettings) -> dict:
    """Snapshot the app_settings row as a dict suitable for audit logging.

    API key is masked so the audit log never stores plaintext keys.
    """
    return {
        "ai_provider": row.ai_provider,
        "ai_model": row.ai_model,
        "ai_api_key": _mask_key(row.ai_api_key),
        "ai_base_url": row.ai_base_url,
        "codex_auth_file": row.codex_auth_file,
        "ai_reasoning_effort": row.ai_reasoning_effort,
        "ai_temperature": row.ai_temperature,
        "ai_max_tokens": row.ai_max_tokens,
        "ai_review_frequency": row.ai_review_frequency,
        "ai_review_block_weeks": row.ai_review_block_weeks,
        "admin_allowed_origins": list(row.admin_allowed_origins or []),
    }


async def _load_row(db: AsyncSession) -> AppSettings:
    result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="app_settings row not found — run the seed migration",
        )
    return row


# --- GET -------------------------------------------------------------------


@router.get("/codex-status", response_model=CodexStatusResponse)
async def get_codex_status(
    _admin: AdminUser = Depends(require_admin),
) -> CodexStatusResponse:
    snapshot = CodexAuthReader(settings.codex_auth_file).snapshot()
    return CodexStatusResponse.model_validate(snapshot.__dict__)


@router.get("", response_model=AppSettingsResponse)
async def get_config(
    db: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(require_admin),
) -> dict:
    row = await _load_row(db)
    return AppSettingsResponse(
        ai_provider=row.ai_provider,
        ai_model=row.ai_model,
        ai_api_key=_mask_key(row.ai_api_key),
        ai_base_url=row.ai_base_url,
        codex_auth_file=row.codex_auth_file,
        ai_reasoning_effort=row.ai_reasoning_effort,
        ai_temperature=row.ai_temperature,
        ai_max_tokens=row.ai_max_tokens,
        ai_review_frequency=row.ai_review_frequency,
        ai_review_block_weeks=row.ai_review_block_weeks,
        admin_allowed_origins=list(row.admin_allowed_origins or []),
    )


# --- PUT -------------------------------------------------------------------


@router.put("", response_model=AppSettingsResponse)
async def update_config(
    payload: AppSettingsUpdate,
    db: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(require_admin),
) -> dict:
    row = await _load_row(db)

    before_snapshot = _masked_dict(row)

    updates = payload.model_dump(exclude_unset=True)

    # Special handling for ai_api_key: if the incoming value matches the
    # masked form of the current key, treat it as "no change" — the UI
    # round-tripped the mask back to us. Any OTHER value (including empty
    # string) overwrites.
    if "ai_api_key" in updates:
        incoming = updates["ai_api_key"]
        if incoming == _mask_key(row.ai_api_key):
            del updates["ai_api_key"]

    for field, value in updates.items():
        setattr(row, field, value)

    after_snapshot = _masked_dict(row)

    # Only write an audit entry if SOMETHING actually changed.
    changed_fields = {
        k: after_snapshot[k]
        for k in after_snapshot
        if after_snapshot[k] != before_snapshot[k]
    }
    if changed_fields:
        await write_audit_log(
            db,
            admin_user_id=admin.id,
            action="config_update",
            target_type="app_settings",
            target_id="1",
            before=before_snapshot,
            after=after_snapshot,
        )

    await db.commit()
    # Mutate the in-memory singleton so subsequent requests (and the CSRF
    # middleware) see the new values without a server restart.
    await refresh_settings_from_db(db)

    return AppSettingsResponse(
        ai_provider=row.ai_provider,
        ai_model=row.ai_model,
        ai_api_key=_mask_key(row.ai_api_key),
        ai_base_url=row.ai_base_url,
        codex_auth_file=row.codex_auth_file,
        ai_reasoning_effort=row.ai_reasoning_effort,
        ai_temperature=row.ai_temperature,
        ai_max_tokens=row.ai_max_tokens,
        ai_review_frequency=row.ai_review_frequency,
        ai_review_block_weeks=row.ai_review_block_weeks,
        admin_allowed_origins=list(row.admin_allowed_origins or []),
    )


# --- POST /test-connection -------------------------------------------------


_TEST_CONNECTION_SYSTEM = "You are a helpful assistant."
_TEST_CONNECTION_USER = "Say hello in one word."
_TEST_CONNECTION_TIMEOUT_SEC = 30.0


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(
    payload: TestConnectionRequest,
    db: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(require_admin),
) -> TestConnectionResponse:
    """Fire a tiny round-trip to the AI provider and return the result.

    Override fields in the payload are used when present, else the saved
    config is used. The endpoint always returns 200 — failures are
    returned in the ``status`` field so the UI can render them inline.
    """
    row = await _load_row(db)

    provider = payload.provider or row.ai_provider
    model = payload.model or row.ai_model
    api_key = payload.api_key if payload.api_key is not None else row.ai_api_key
    base_url = payload.base_url if payload.base_url is not None else row.ai_base_url
    temperature = (
        payload.temperature if payload.temperature is not None else row.ai_temperature
    )
    # Cap to 10 for cheap test calls unless explicitly overridden.
    # (Not row.ai_max_tokens — test-connection is a ping, not a full generation.)
    max_tokens = payload.max_tokens if payload.max_tokens is not None else 10

    start = time.perf_counter()
    try:
        adapter = create_adapter(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
        llm_response = await asyncio.wait_for(
            adapter.generate(
                system_prompt=_TEST_CONNECTION_SYSTEM,
                user_prompt=_TEST_CONNECTION_USER,
                temperature=temperature,
                max_tokens=max_tokens,
            ),
            timeout=_TEST_CONNECTION_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        return TestConnectionResponse(
            status="error",
            latency_ms=int(_TEST_CONNECTION_TIMEOUT_SEC * 1000),
            response_text=None,
            error=f"timeout after {int(_TEST_CONNECTION_TIMEOUT_SEC)}s",
        )
    except Exception as e:  # noqa: BLE001 — we want to surface any adapter failure
        latency_ms = int((time.perf_counter() - start) * 1000)
        return TestConnectionResponse(
            status="error",
            latency_ms=latency_ms,
            response_text=None,
            error=str(e),
        )

    latency_ms = int((time.perf_counter() - start) * 1000)
    return TestConnectionResponse(
        status="ok",
        latency_ms=latency_ms,
        response_text=llm_response.content[:200],
        error=None,
    )
