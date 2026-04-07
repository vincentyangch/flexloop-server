"""Tests for flexloop.admin.crud helpers."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import DeclarativeBase
from starlette.datastructures import QueryParams

from flexloop.admin.crud import parse_filter_params, parse_sort_spec


class _FakeBase(DeclarativeBase):
    pass


class _FakeModel(_FakeBase):
    """Stand-in for a SQLAlchemy model, just enough to exercise parse_sort_spec."""
    __tablename__ = "_fake_model"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    created_at = Column(String)  # type doesn't matter for sort tests


class TestParseSortSpec:
    def test_single_column_asc(self) -> None:
        clauses = parse_sort_spec("name:asc", model=_FakeModel, allowed={"name"})
        assert len(clauses) == 1
        # The ORDER BY rendering contains "name ASC"
        assert "name" in str(clauses[0]).lower()
        assert "asc" in str(clauses[0]).lower()

    def test_single_column_desc(self) -> None:
        clauses = parse_sort_spec("created_at:desc", model=_FakeModel, allowed={"created_at"})
        assert "desc" in str(clauses[0]).lower()

    def test_multiple_columns_preserve_order(self) -> None:
        clauses = parse_sort_spec(
            "created_at:desc,name:asc",
            model=_FakeModel,
            allowed={"created_at", "name"},
        )
        assert len(clauses) == 2
        assert "created_at" in str(clauses[0]).lower()
        assert "name" in str(clauses[1]).lower()

    def test_missing_direction_defaults_to_asc(self) -> None:
        clauses = parse_sort_spec("name", model=_FakeModel, allowed={"name"})
        assert "asc" in str(clauses[0]).lower()

    def test_unknown_column_raises_400(self) -> None:
        with pytest.raises(HTTPException) as exc:
            parse_sort_spec("bogus:desc", model=_FakeModel, allowed={"name"})
        assert exc.value.status_code == 400
        assert "bogus" in exc.value.detail.lower()

    def test_empty_string_returns_empty_list(self) -> None:
        clauses = parse_sort_spec("", model=_FakeModel, allowed={"name"})
        assert clauses == []

    def test_none_returns_empty_list(self) -> None:
        clauses = parse_sort_spec(None, model=_FakeModel, allowed={"name"})
        assert clauses == []

    def test_whitespace_tolerated(self) -> None:
        clauses = parse_sort_spec(" name : asc , created_at : desc ", model=_FakeModel, allowed={"name", "created_at"})
        assert len(clauses) == 2

    def test_direction_case_insensitive(self) -> None:
        clauses = parse_sort_spec("name:DESC", model=_FakeModel, allowed={"name"})
        assert "desc" in str(clauses[0]).lower()


class TestParseFilterParams:
    def test_extracts_filter_brackets(self) -> None:
        qp = QueryParams("filter[user_id]=4&filter[type]=weight&page=1")
        result = parse_filter_params(qp, allowed={"user_id", "type"})
        assert result == {"user_id": "4", "type": "weight"}

    def test_ignores_non_filter_params(self) -> None:
        qp = QueryParams("page=1&per_page=50&sort=name:asc")
        result = parse_filter_params(qp, allowed={"user_id"})
        assert result == {}

    def test_unknown_filter_key_raises_400(self) -> None:
        qp = QueryParams("filter[secret]=1")
        with pytest.raises(HTTPException) as exc:
            parse_filter_params(qp, allowed={"user_id"})
        assert exc.value.status_code == 400
        assert "secret" in exc.value.detail.lower()

    def test_empty_allowed_rejects_all(self) -> None:
        qp = QueryParams("filter[anything]=x")
        with pytest.raises(HTTPException):
            parse_filter_params(qp, allowed=set())

    def test_empty_query_returns_empty_dict(self) -> None:
        qp = QueryParams("")
        assert parse_filter_params(qp, allowed={"user_id"}) == {}

    def test_malformed_key_ignored(self) -> None:
        """filter_without_brackets=1 is not a 'filter[...]' param."""
        qp = QueryParams("filter_user_id=4")
        assert parse_filter_params(qp, allowed={"user_id"}) == {}


from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.crud import paginated_response
from flexloop.models.user import User


# Inline test schema — keeps this task independent of any resource-level
# schemas defined in later tasks. We only validate the couple of fields
# we assert on.
class _RowSchemaForTests(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class TestPaginatedResponse:
    async def test_empty_table(self, db_session: AsyncSession) -> None:
        query = select(User)
        result = await paginated_response(
            db_session,
            query=query,
            item_schema=_RowSchemaForTests,
            page=1,
            per_page=50,
        )
        assert result == {
            "items": [],
            "total": 0,
            "page": 1,
            "per_page": 50,
            "total_pages": 0,
        }

    async def test_first_page_partial(self, db_session: AsyncSession) -> None:
        for i in range(3):
            db_session.add(User(
                name=f"U{i}", gender="other", age=30, height=180, weight=80,
                weight_unit="kg", height_unit="cm", experience_level="intermediate",
                goals="stay fit", available_equipment=[],
            ))
        await db_session.commit()

        query = select(User).order_by(User.id)
        result = await paginated_response(
            db_session, query=query, item_schema=_RowSchemaForTests, page=1, per_page=50,
        )
        assert result["total"] == 3
        assert result["page"] == 1
        assert result["per_page"] == 50
        assert result["total_pages"] == 1
        assert len(result["items"]) == 3
        assert result["items"][0].name == "U0"

    async def test_second_page(self, db_session: AsyncSession) -> None:
        for i in range(5):
            db_session.add(User(
                name=f"U{i}", gender="other", age=30, height=180, weight=80,
                weight_unit="kg", height_unit="cm", experience_level="intermediate",
                goals="stay fit", available_equipment=[],
            ))
        await db_session.commit()

        query = select(User).order_by(User.id)
        result = await paginated_response(
            db_session, query=query, item_schema=_RowSchemaForTests, page=2, per_page=2,
        )
        assert result["total"] == 5
        assert result["page"] == 2
        assert result["per_page"] == 2
        assert result["total_pages"] == 3
        assert len(result["items"]) == 2
        assert result["items"][0].name == "U2"
        assert result["items"][1].name == "U3"

    async def test_page_out_of_range_returns_empty_items(self, db_session: AsyncSession) -> None:
        db_session.add(User(
            name="only", gender="other", age=30, height=180, weight=80,
            weight_unit="kg", height_unit="cm", experience_level="intermediate",
            goals="stay fit", available_equipment=[],
        ))
        await db_session.commit()

        query = select(User)
        result = await paginated_response(
            db_session, query=query, item_schema=_RowSchemaForTests, page=99, per_page=10,
        )
        assert result["total"] == 1
        assert result["items"] == []
