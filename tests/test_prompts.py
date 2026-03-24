import json
from pathlib import Path

import pytest

from flexloop.ai.prompts import PromptManager


@pytest.fixture
def prompt_dir(tmp_path):
    manifest = {
        "plan_generation": {"default": "v1"},
        "block_review": {"default": "v1"},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))

    pg_dir = tmp_path / "plan_generation"
    pg_dir.mkdir()
    (pg_dir / "v1.md").write_text("You are a fitness coach. Generate a plan for: {{user_profile}}")

    br_dir = tmp_path / "block_review"
    br_dir.mkdir()
    (br_dir / "v1.md").write_text("Review this training block: {{block_data}}")

    return tmp_path


def test_load_prompt(prompt_dir):
    manager = PromptManager(prompt_dir)
    prompt = manager.get_prompt("plan_generation")
    assert "fitness coach" in prompt
    assert "{{user_profile}}" in prompt


def test_load_prompt_unknown_type(prompt_dir):
    manager = PromptManager(prompt_dir)
    with pytest.raises(KeyError):
        manager.get_prompt("nonexistent")


def test_render_prompt(prompt_dir):
    manager = PromptManager(prompt_dir)
    rendered = manager.render("plan_generation", user_profile="28M, intermediate, PPL")
    assert "28M, intermediate, PPL" in rendered
    assert "{{user_profile}}" not in rendered


def test_load_real_prompts():
    """Test that the actual prompt files in the repo are loadable."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    if not prompts_dir.exists():
        pytest.skip("prompts directory not found")

    manager = PromptManager(prompts_dir)

    for prompt_type in ["plan_generation", "block_review", "session_review", "chat"]:
        prompt = manager.get_prompt(prompt_type)
        assert len(prompt) > 50, f"{prompt_type} prompt seems too short"
