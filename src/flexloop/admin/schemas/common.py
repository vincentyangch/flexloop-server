"""Shared schemas for admin CRUD list/detail endpoints."""
from __future__ import annotations

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field

T = TypeVar("T")

MAX_PER_PAGE = 200


class ListQueryParams(BaseModel):
    """Standard list query params injected via ``Depends()`` on every list endpoint.

    Filter params (``filter[key]=value``) are NOT in this model — they're
    parsed directly from ``request.query_params`` by ``parse_filter_params``
    because FastAPI's query-param parser doesn't handle bracket syntax natively.
    """
    page: int = Field(1, ge=1)
    per_page: int = Field(50, ge=1, le=MAX_PER_PAGE)
    search: str | None = None
    sort: str | None = None

    @classmethod
    def as_dependency(
        cls,
        page: int = Query(1, ge=1),
        per_page: int = Query(50, ge=1, le=MAX_PER_PAGE),
        search: str | None = Query(None),
        sort: str | None = Query(None),
    ) -> "ListQueryParams":
        """Call this via ``Depends(ListQueryParams.as_dependency)`` to get one instance."""
        return cls(page=page, per_page=per_page, search=search, sort=sort)


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard list response shape. Matches spec §9.1."""
    items: list[T]
    total: int
    page: int
    per_page: int
    total_pages: int
