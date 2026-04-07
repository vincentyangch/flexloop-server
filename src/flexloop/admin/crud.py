"""Reusable CRUD helpers for admin resource routers.

Every admin resource router follows the same pattern:
- GET /api/admin/{resource}           → list with pagination/sort/filter/search
- GET /api/admin/{resource}/{id}       → detail
- POST /api/admin/{resource}           → create
- PUT /api/admin/{resource}/{id}       → update
- DELETE /api/admin/{resource}/{id}    → delete

This module provides the shared building blocks so each router only has to
supply the model class, the schemas, and its whitelists.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement
from sqlalchemy.orm import InstrumentedAttribute
from starlette.datastructures import QueryParams


def parse_sort_spec(
    spec: str | None,
    *,
    model: Any,
    allowed: set[str],
) -> list[ColumnElement[Any]]:
    """Parse a sort spec like 'created_at:desc,name:asc' into ORDER BY clauses.

    Args:
        spec: The raw ?sort=... query string value. None or "" returns [].
        model: The SQLAlchemy model class whose columns are being sorted on.
        allowed: Whitelist of column names the caller permits sorting on.

    Returns:
        A list of SQLAlchemy ColumnElement order-by clauses, in the order
        they appeared in the spec.

    Raises:
        HTTPException(400) if a requested column is not in `allowed`.
    """
    if not spec:
        return []

    clauses: list[ColumnElement[Any]] = []
    for raw in spec.split(","):
        raw = raw.strip()
        if not raw:
            continue
        if ":" in raw:
            col_name, _, direction = raw.partition(":")
            col_name = col_name.strip()
            direction = direction.strip().lower()
        else:
            col_name = raw
            direction = "asc"

        if col_name not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Sort column '{col_name}' is not allowed. Allowed: {sorted(allowed)}",
            )

        column: InstrumentedAttribute[Any] = getattr(model, col_name)
        if direction == "desc":
            clauses.append(column.desc())
        else:
            clauses.append(column.asc())

    return clauses


def parse_filter_params(
    query_params: QueryParams,
    *,
    allowed: set[str],
) -> dict[str, str]:
    """Extract ``filter[key]=value`` query params into a whitelisted dict.

    Only keys of the form ``filter[name]`` are considered. Keys whose ``name``
    is not in ``allowed`` cause a 400. Values are returned as raw strings;
    callers coerce to the appropriate SQLAlchemy column type.

    Args:
        query_params: Starlette ``QueryParams`` from ``request.query_params``.
        allowed: Whitelist of filter names the caller permits.

    Returns:
        A dict mapping filter name -> string value.

    Raises:
        HTTPException(400) if an unknown filter key is present.
    """
    result: dict[str, str] = {}
    for key, value in query_params.items():
        if not (key.startswith("filter[") and key.endswith("]")):
            continue
        name = key[len("filter[") : -1]
        if name not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Filter '{name}' is not allowed. Allowed: {sorted(allowed)}",
            )
        result[name] = value
    return result
