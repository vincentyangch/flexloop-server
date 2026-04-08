"""Admin endpoints for prompt file management.

All endpoints are thin wrappers over ``flexloop.admin.prompt_service``.
The prompts directory path is provided via the ``get_prompts_dir``
dependency, which tests override to a temp path.

Spec: §10.2
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from flexloop.admin import prompt_service
from flexloop.admin.auth import require_admin
from flexloop.admin.prompt_service import (
    ConflictError,
    InvalidNameError,
    NotFoundError,
)
from flexloop.models.admin_user import AdminUser

router = APIRouter(prefix="/api/admin/prompts", tags=["admin:prompts"])


# --- Dependency ------------------------------------------------------------


# Default prompts directory — matches flexloop.routers.ai PROMPTS_DIR.
# Resolved to an absolute path so worktrees/tests can't accidentally
# read from the wrong directory when the CWD changes.
# Honors ``PROMPTS_DIR`` env var for smoke-test overrides.
_DEFAULT_PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", "prompts")).resolve()


def get_prompts_dir() -> Path:
    """FastAPI dependency returning the active prompts directory.

    Tests override this via ``app.dependency_overrides`` to point at a
    ``tmp_path`` fixture.
    """
    return _DEFAULT_PROMPTS_DIR


# --- Schemas --------------------------------------------------------------


class PromptInfoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    versions: list[str]
    active_by_provider: dict[str, str]


class ListPromptsResponse(BaseModel):
    prompts: list[PromptInfoResponse]


# --- Error translation ----------------------------------------------------


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, InvalidNameError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# --- List -----------------------------------------------------------------


@router.get("", response_model=ListPromptsResponse)
async def list_prompts(
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> ListPromptsResponse:
    infos = prompt_service.list_prompts(prompts_dir)
    return ListPromptsResponse(
        prompts=[
            PromptInfoResponse(
                name=p.name,
                versions=p.versions,
                active_by_provider=p.active_by_provider,
            )
            for p in infos
        ]
    )


# --- Get version ----------------------------------------------------------


class PromptVersionResponse(BaseModel):
    name: str
    version: str
    content: str
    variables: list[str]


@router.get(
    "/{name}/versions/{version}",
    response_model=PromptVersionResponse,
)
async def get_version(
    name: str,
    version: str,
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> PromptVersionResponse:
    try:
        content = prompt_service.read_version(prompts_dir, name, version)
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc
    return PromptVersionResponse(
        name=name,
        version=version,
        content=content,
        variables=prompt_service.extract_variables(content),
    )


# --- Update version -------------------------------------------------------


class PromptVersionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str


@router.put(
    "/{name}/versions/{version}",
    response_model=PromptVersionResponse,
)
async def update_version(
    name: str,
    version: str,
    payload: PromptVersionUpdate,
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> PromptVersionResponse:
    try:
        prompt_service.write_version(prompts_dir, name, version, payload.content)
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc
    return PromptVersionResponse(
        name=name,
        version=version,
        content=payload.content,
        variables=prompt_service.extract_variables(payload.content),
    )


# --- Create version (clone active) ----------------------------------------


@router.post(
    "/{name}/versions",
    response_model=PromptVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    name: str,
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> PromptVersionResponse:
    try:
        new_version, content = prompt_service.create_version(prompts_dir, name)
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc
    return PromptVersionResponse(
        name=name,
        version=new_version,
        content=content,
        variables=prompt_service.extract_variables(content),
    )


# --- Set active version ---------------------------------------------------


class SetActiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    provider: str = "default"


class SetActiveResponse(BaseModel):
    name: str
    version: str
    provider: str


@router.put(
    "/{name}/active",
    response_model=SetActiveResponse,
)
async def set_active_version(
    name: str,
    payload: SetActiveRequest,
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> SetActiveResponse:
    try:
        prompt_service.set_active(
            prompts_dir, name, payload.version, provider=payload.provider
        )
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc
    return SetActiveResponse(
        name=name, version=payload.version, provider=payload.provider
    )


# --- Diff -----------------------------------------------------------------


class DiffResponse(BaseModel):
    name: str
    from_version: str
    to_version: str
    diff: str


@router.get(
    "/{name}/diff",
    response_model=DiffResponse,
)
async def get_diff(
    name: str,
    from_version: str = Query(..., alias="from"),
    to_version: str = Query(..., alias="to"),
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> DiffResponse:
    try:
        diff = prompt_service.diff_versions(
            prompts_dir, name, from_version, to_version
        )
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc
    return DiffResponse(
        name=name,
        from_version=from_version,
        to_version=to_version,
        diff=diff,
    )


# --- Delete version -------------------------------------------------------


@router.delete(
    "/{name}/versions/{version}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_version_endpoint(
    name: str,
    version: str,
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> None:
    try:
        prompt_service.delete_version(prompts_dir, name, version)
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc
