"""Tests for flexloop.admin.crud helpers."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import DeclarativeBase

from flexloop.admin.crud import parse_sort_spec


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
