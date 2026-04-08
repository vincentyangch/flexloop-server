"""Unit tests for flexloop.admin.prompt_service."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from flexloop.admin.prompt_service import (
    ConflictError,
    InvalidNameError,
    NotFoundError,
    PromptInfo,
    create_version,
    delete_version,
    diff_versions,
    extract_variables,
    list_prompts,
    read_version,
    set_active,
    write_version,
)


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    """Build a small prompts directory with two prompts and multiple versions."""
    (tmp_path / "plan_generation").mkdir()
    (tmp_path / "plan_generation" / "v1.md").write_text("v1 content for plan_generation")
    (tmp_path / "plan_generation" / "v2.md").write_text("v2 content {{user_name}}")
    (tmp_path / "chat").mkdir()
    (tmp_path / "chat" / "v1.md").write_text("chat v1 {{message}}")
    manifest = {
        "plan_generation": {"default": "v2"},
        "chat": {"default": "v1"},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path


class TestListPrompts:
    def test_returns_all_prompts_with_versions(self, prompts_dir: Path) -> None:
        result = list_prompts(prompts_dir)
        assert len(result) == 2
        by_name = {p.name: p for p in result}

        pg = by_name["plan_generation"]
        assert pg.versions == ["v1", "v2"]
        assert pg.active_by_provider == {"default": "v2"}

        chat = by_name["chat"]
        assert chat.versions == ["v1"]
        assert chat.active_by_provider == {"default": "v1"}

    def test_versions_sorted_by_numeric_order(self, tmp_path: Path) -> None:
        """v10 must come after v9, not between v1 and v2 (natural sort)."""
        (tmp_path / "foo").mkdir()
        for i in [1, 2, 10, 3, 9]:
            (tmp_path / "foo" / f"v{i}.md").write_text(f"content {i}")
        (tmp_path / "manifest.json").write_text(json.dumps({"foo": {"default": "v1"}}))
        result = list_prompts(tmp_path)
        assert result[0].versions == ["v1", "v2", "v3", "v9", "v10"]

    def test_empty_dir_returns_empty_list(self, tmp_path: Path) -> None:
        (tmp_path / "manifest.json").write_text("{}")
        assert list_prompts(tmp_path) == []

    def test_ignores_non_prompt_files(self, tmp_path: Path) -> None:
        (tmp_path / "manifest.json").write_text("{}")
        (tmp_path / "README.md").write_text("not a prompt")
        (tmp_path / ".DS_Store").write_text("trash")
        result = list_prompts(tmp_path)
        assert result == []

    def test_ignores_non_version_files_inside_prompt_dir(self, tmp_path: Path) -> None:
        (tmp_path / "foo").mkdir()
        (tmp_path / "foo" / "v1.md").write_text("x")
        (tmp_path / "foo" / "notes.txt").write_text("y")
        (tmp_path / "foo" / "v2a.md").write_text("z")
        (tmp_path / "manifest.json").write_text(json.dumps({"foo": {"default": "v1"}}))
        result = list_prompts(tmp_path)
        assert result[0].versions == ["v1"]


class TestReadVersion:
    def test_returns_file_contents(self, prompts_dir: Path) -> None:
        content = read_version(prompts_dir, "plan_generation", "v1")
        assert content == "v1 content for plan_generation"

    def test_missing_prompt_raises(self, prompts_dir: Path) -> None:
        with pytest.raises(NotFoundError):
            read_version(prompts_dir, "nonexistent", "v1")

    def test_missing_version_raises(self, prompts_dir: Path) -> None:
        with pytest.raises(NotFoundError):
            read_version(prompts_dir, "plan_generation", "v99")

    def test_rejects_path_traversal_in_name(self, prompts_dir: Path) -> None:
        from flexloop.admin.prompt_service import InvalidNameError
        with pytest.raises(InvalidNameError):
            read_version(prompts_dir, "../etc/passwd", "v1")

    def test_rejects_path_traversal_in_version(self, prompts_dir: Path) -> None:
        from flexloop.admin.prompt_service import InvalidNameError
        with pytest.raises(InvalidNameError):
            read_version(prompts_dir, "plan_generation", "../foo")


class TestWriteVersion:
    def test_overwrites_existing_version(self, prompts_dir: Path) -> None:
        write_version(prompts_dir, "plan_generation", "v1", "new content")
        assert read_version(prompts_dir, "plan_generation", "v1") == "new content"

    def test_missing_version_raises(self, prompts_dir: Path) -> None:
        with pytest.raises(NotFoundError):
            write_version(prompts_dir, "plan_generation", "v99", "x")

    def test_missing_prompt_raises(self, prompts_dir: Path) -> None:
        with pytest.raises(NotFoundError):
            write_version(prompts_dir, "nonexistent", "v1", "x")

    def test_rejects_invalid_name(self, prompts_dir: Path) -> None:
        from flexloop.admin.prompt_service import InvalidNameError
        with pytest.raises(InvalidNameError):
            write_version(prompts_dir, "Plan-Generation!", "v1", "x")


class TestCreateVersion:
    def test_clones_active_version(self, prompts_dir: Path) -> None:
        new_version, content = create_version(prompts_dir, "plan_generation")
        assert new_version == "v3"
        assert content == "v2 content {{user_name}}"
        # Read it back
        assert read_version(prompts_dir, "plan_generation", "v3") == (
            "v2 content {{user_name}}"
        )

    def test_version_number_continues_from_max(self, tmp_path: Path) -> None:
        (tmp_path / "foo").mkdir()
        (tmp_path / "foo" / "v1.md").write_text("one")
        (tmp_path / "foo" / "v5.md").write_text("five")
        (tmp_path / "manifest.json").write_text(
            json.dumps({"foo": {"default": "v1"}})
        )
        new_version, _ = create_version(tmp_path, "foo")
        assert new_version == "v6"

    def test_prompt_with_no_active_raises_conflict(self, tmp_path: Path) -> None:
        from flexloop.admin.prompt_service import ConflictError
        (tmp_path / "foo").mkdir()
        (tmp_path / "foo" / "v1.md").write_text("x")
        (tmp_path / "manifest.json").write_text(json.dumps({"foo": {}}))
        with pytest.raises(ConflictError):
            create_version(tmp_path, "foo")

    def test_missing_prompt_raises(self, prompts_dir: Path) -> None:
        with pytest.raises(NotFoundError):
            create_version(prompts_dir, "nonexistent")
