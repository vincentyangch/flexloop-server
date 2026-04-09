"""Admin endpoints for the AI playground.

Three endpoints:
- POST /api/admin/playground/run         SSE streaming run
- GET  /api/admin/playground/templates   list registered prompts + variables
- POST /api/admin/playground/render      render a template with variables

The ``/run`` endpoint always returns ``text/event-stream``. Each event is
a single ``data: <json>\\n\\n`` line. Event types: ``content``, ``usage``,
``error``, ``done``. The stream is terminated by an explicit ``done``
event so frontends can render the complete state before the connection
closes.

Spec: §10.3
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from flexloop.admin.auth import require_admin
from flexloop.admin.prompt_service import (
    extract_variables,
    read_version,
)
from flexloop.admin.routers.prompts import get_prompts_dir
from flexloop.ai.factory import create_adapter
from flexloop.ai.prompts import PromptManager
from flexloop.config import settings
from flexloop.models.admin_user import AdminUser

router = APIRouter(prefix="/api/admin/playground", tags=["admin:playground"])


# --- Schemas --------------------------------------------------------------


class PlaygroundRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_prompt: str
    user_prompt: str
    temperature: float | None = None
    max_tokens: int | None = None
    provider_override: str | None = None
    model_override: str | None = None
    api_key_override: str | None = None
    base_url_override: str | None = None


# --- Helpers --------------------------------------------------------------


def _event_to_data_line(event_dict: dict) -> str:
    """Format an event dict as a single ``data: <json>\\n\\n`` SSE line."""
    payload = {k: v for k, v in event_dict.items() if v is not None}
    return f"data: {json.dumps(payload)}\n\n"


# --- POST /run ------------------------------------------------------------


@router.post("/run")
async def run_playground(
    payload: PlaygroundRunRequest,
    _admin: AdminUser = Depends(require_admin),
) -> StreamingResponse:
    # Resolve provider/model/key/base_url: override values take precedence,
    # omitted fields fall back to saved settings.
    provider = payload.provider_override or settings.ai_provider
    model = payload.model_override or settings.ai_model
    api_key = (
        payload.api_key_override
        if payload.api_key_override is not None
        else settings.ai_api_key
    )
    base_url = (
        payload.base_url_override
        if payload.base_url_override is not None
        else settings.ai_base_url
    )
    temperature = (
        payload.temperature if payload.temperature is not None else settings.ai_temperature
    )
    max_tokens = (
        payload.max_tokens if payload.max_tokens is not None else settings.ai_max_tokens
    )

    adapter = create_adapter(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )

    async def event_generator():
        try:
            async for event in adapter.stream_generate(
                system_prompt=payload.system_prompt,
                user_prompt=payload.user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                yield _event_to_data_line(asdict(event))
        except Exception as exc:  # noqa: BLE001
            # Catch any exception raised OUTSIDE the adapter's own
            # error-handling path (e.g. create_adapter failure reaching
            # here would normally surface as an HTTPException, but an
            # error inside the async-for loop would propagate).
            yield _event_to_data_line({"type": "error", "error": str(exc)})
            yield _event_to_data_line({"type": "done"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- GET /templates -------------------------------------------------------


class PlaygroundTemplate(BaseModel):
    name: str
    active_version: str
    variables: list[str]


class PlaygroundTemplatesResponse(BaseModel):
    templates: list[PlaygroundTemplate]


@router.get("/templates", response_model=PlaygroundTemplatesResponse)
async def list_templates(
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> PlaygroundTemplatesResponse:
    from flexloop.admin import prompt_service

    infos = prompt_service.list_prompts(prompts_dir)
    templates: list[PlaygroundTemplate] = []
    for info in infos:
        active = info.active_by_provider.get("default")
        if not active:
            # Skip prompts with no default provider; the playground's
            # template picker only exposes default-active versions.
            continue
        try:
            content = read_version(prompts_dir, info.name, active)
        except Exception:  # noqa: BLE001
            # If the active version file is missing, skip rather than 500
            continue
        templates.append(
            PlaygroundTemplate(
                name=info.name,
                active_version=active,
                variables=extract_variables(content),
            )
        )
    return PlaygroundTemplatesResponse(templates=templates)


# --- POST /render ---------------------------------------------------------


class PlaygroundRenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_name: str
    variables: dict[str, str]


class PlaygroundRenderResponse(BaseModel):
    template_name: str
    version: str
    rendered: str


@router.post("/render", response_model=PlaygroundRenderResponse)
async def render_template(
    payload: PlaygroundRenderRequest,
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> PlaygroundRenderResponse:
    from flexloop.admin.prompt_service import (
        InvalidNameError,
        NotFoundError,
        _read_manifest,
    )

    # Validate the template name early — reuses the service layer's validator
    # by calling read_version on the active version. But first we need to
    # find the active version.
    try:
        manifest = _read_manifest(prompts_dir)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    if payload.template_name not in manifest:
        # Pass through the service's validation for invalid names (400) vs
        # genuinely missing templates (404). read_version validates the name
        # before it checks the file, so call it with a dummy version to get
        # the right error — except for valid-but-missing names which should
        # 404 cleanly.
        try:
            read_version(prompts_dir, payload.template_name, "v1")
        except InvalidNameError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc
        except NotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
            ) from exc
        # Fallback: if somehow the template name validates and the file
        # reads without error, return 404.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"template {payload.template_name!r} not found",
        )

    active_version = manifest[payload.template_name].get("default")
    if not active_version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"template {payload.template_name!r} has no default active version",
        )

    # Use PromptManager.render for consistency with the existing codebase.
    manager = PromptManager(prompts_dir)
    try:
        rendered = manager.render(payload.template_name, **payload.variables)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    return PlaygroundRenderResponse(
        template_name=payload.template_name,
        version=active_version,
        rendered=rendered,
    )
