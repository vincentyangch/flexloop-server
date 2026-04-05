import pytest
from unittest.mock import AsyncMock, MagicMock

from flexloop.ai.base import ToolCall, ToolUseResponse
from flexloop.ai.refiner import PlanRefiner, REFINER_TOOLS, PlanChange


def test_refiner_tools_defined():
    names = {t.name for t in REFINER_TOOLS}
    assert names == {"swap_exercise", "adjust_sets", "add_exercise", "remove_exercise", "explain_choice"}


def test_refiner_tools_have_valid_schemas():
    for tool in REFINER_TOOLS:
        assert tool.input_schema["type"] == "object"
        assert "properties" in tool.input_schema
        assert "required" in tool.input_schema


def _make_plan_data():
    return {
        "days": [
            {
                "day_number": 1,
                "label": "Push A",
                "focus": "chest,shoulders,triceps",
                "exercise_groups": [
                    {
                        "group_type": "straight",
                        "order": 1,
                        "rest_after_group_sec": 90,
                        "exercises": [
                            {"exercise_id": 1, "exercise_name": "Barbell Bench Press", "sets": 4, "reps": 8, "weight": 80.0, "rpe_target": 8.0},
                            {"exercise_id": 2, "exercise_name": "Incline Dumbbell Press", "sets": 3, "reps": 10, "weight": 25.0, "rpe_target": 7.5},
                        ],
                    }
                ],
            }
        ]
    }


def _make_exercise_library():
    lib = {}
    for id, name in [(1, "Barbell Bench Press"), (2, "Incline Dumbbell Press"), (3, "Dumbbell Fly"), (4, "Cable Crossover")]:
        ex = MagicMock()
        ex.id = id
        ex.name = name
        lib[name.lower()] = ex
    return lib


def test_execute_swap_exercise():
    refiner = PlanRefiner.__new__(PlanRefiner)
    plan_data = _make_plan_data()
    lib = _make_exercise_library()

    change = refiner._execute_tool(
        ToolCall(id="t1", name="swap_exercise", input={
            "day_number": 1,
            "exercise_name": "Barbell Bench Press",
            "replacement_name": "Dumbbell Fly",
            "sets": 3, "reps": 12, "rpe_target": 7.0, "weight": 15.0,
            "reason": "More isolation work",
        }),
        plan_data, lib,
    )

    assert change is not None
    assert change.tool_name == "swap_exercise"
    assert change.before["exercise_name"] == "Barbell Bench Press"
    assert change.after["exercise_name"] == "Dumbbell Fly"
    assert change.after["exercise_id"] == 3


def test_execute_swap_unresolvable():
    refiner = PlanRefiner.__new__(PlanRefiner)
    plan_data = _make_plan_data()
    lib = _make_exercise_library()

    change = refiner._execute_tool(
        ToolCall(id="t1", name="swap_exercise", input={
            "day_number": 1,
            "exercise_name": "Barbell Bench Press",
            "replacement_name": "Nonexistent Exercise",
            "reason": "test",
        }),
        plan_data, lib,
    )

    assert change is not None
    assert change.after["exercise_id"] is None
    assert change.warning == "exercise not in library"


def test_execute_adjust_sets():
    refiner = PlanRefiner.__new__(PlanRefiner)
    plan_data = _make_plan_data()
    lib = _make_exercise_library()

    change = refiner._execute_tool(
        ToolCall(id="t2", name="adjust_sets", input={
            "day_number": 1, "exercise_name": "Barbell Bench Press",
            "sets": 5, "reps": 5, "rpe_target": 9.0, "weight": 90.0,
        }),
        plan_data, lib,
    )

    assert change is not None
    assert change.before["sets"] == 4
    assert change.after["sets"] == 5
    assert change.after["weight"] == 90.0


def test_execute_add_exercise():
    refiner = PlanRefiner.__new__(PlanRefiner)
    plan_data = _make_plan_data()
    lib = _make_exercise_library()

    change = refiner._execute_tool(
        ToolCall(id="t3", name="add_exercise", input={
            "day_number": 1, "exercise_name": "Cable Crossover",
            "sets": 3, "reps": 15,
        }),
        plan_data, lib,
    )

    assert change is not None
    assert change.tool_name == "add_exercise"
    assert change.after["exercise_id"] == 4
    assert change.after["exercise_name"] == "Cable Crossover"
    # Verify it was added to the plan
    exercises = plan_data["days"][0]["exercise_groups"][0]["exercises"]
    assert len(exercises) == 3
    assert exercises[-1]["exercise_name"] == "Cable Crossover"


def test_execute_remove_exercise():
    refiner = PlanRefiner.__new__(PlanRefiner)
    plan_data = _make_plan_data()
    lib = _make_exercise_library()

    change = refiner._execute_tool(
        ToolCall(id="t4", name="remove_exercise", input={
            "day_number": 1, "exercise_name": "Incline Dumbbell Press",
        }),
        plan_data, lib,
    )

    assert change is not None
    assert change.tool_name == "remove_exercise"
    assert change.before["exercise_id"] == 2
    exercises = plan_data["days"][0]["exercise_groups"][0]["exercises"]
    assert len(exercises) == 1


def test_execute_tool_unknown_exercise():
    refiner = PlanRefiner.__new__(PlanRefiner)
    plan_data = _make_plan_data()
    lib = _make_exercise_library()

    change = refiner._execute_tool(
        ToolCall(id="t5", name="adjust_sets", input={
            "day_number": 1, "exercise_name": "Nonexistent Exercise",
            "sets": 3, "reps": 10,
        }),
        plan_data, lib,
    )

    assert change is None


def test_execute_explain_returns_none():
    """explain_choice is read-only and returns None (no plan change)."""
    refiner = PlanRefiner.__new__(PlanRefiner)
    plan_data = _make_plan_data()
    lib = _make_exercise_library()

    change = refiner._execute_tool(
        ToolCall(id="t6", name="explain_choice", input={
            "day_number": 1, "exercise_name": "Barbell Bench Press",
        }),
        plan_data, lib,
    )

    assert change is None


@pytest.mark.asyncio
async def test_refine_agentic_executes_multiple_tools():
    adapter = MagicMock()
    prompt_manager = MagicMock()
    refiner = PlanRefiner(adapter=adapter, prompt_manager=prompt_manager)

    plan_data = _make_plan_data()
    lib = _make_exercise_library()

    # First call: model calls adjust_sets, stop_reason=tool_use
    resp1 = ToolUseResponse(
        content=[{"type": "text", "text": "I'll adjust that."}],
        tool_calls=[ToolCall(id="t1", name="adjust_sets", input={
            "day_number": 1, "exercise_name": "Barbell Bench Press",
            "sets": 5, "reps": 5,
        })],
        text="I'll adjust that.",
        stop_reason="tool_use",
        input_tokens=100, output_tokens=50,
    )
    # Second call: model is done
    resp2 = ToolUseResponse(
        content=[{"type": "text", "text": "Done! I increased sets to 5x5."}],
        tool_calls=[],
        text="Done! I increased sets to 5x5.",
        stop_reason="end_turn",
        input_tokens=120, output_tokens=60,
    )
    adapter.tool_use = AsyncMock(side_effect=[resp1, resp2])

    changes, reply, responses = await refiner.refine_agentic(
        system_prompt="You are a coach.",
        user_message="Make bench press heavier",
        history=[],
        plan_data=plan_data,
        exercise_library=lib,
    )

    assert len(changes) == 1
    assert changes[0].after["sets"] == 5
    assert reply == "Done! I increased sets to 5x5."
    assert len(responses) == 2
    assert adapter.tool_use.call_count == 2


@pytest.mark.asyncio
async def test_refine_agentic_max_iterations():
    adapter = MagicMock()
    prompt_manager = MagicMock()
    refiner = PlanRefiner(adapter=adapter, prompt_manager=prompt_manager)

    plan_data = _make_plan_data()
    lib = _make_exercise_library()

    # Every call returns tool_use — should stop at MAX_ITERATIONS
    def make_response():
        return ToolUseResponse(
            content=[],
            tool_calls=[ToolCall(id="t1", name="adjust_sets", input={
                "day_number": 1, "exercise_name": "Barbell Bench Press", "sets": 5,
            })],
            text="Adjusting...",
            stop_reason="tool_use",
            input_tokens=100, output_tokens=50,
        )

    adapter.tool_use = AsyncMock(side_effect=[make_response() for _ in range(10)])

    changes, reply, responses = await refiner.refine_agentic(
        system_prompt="Coach",
        user_message="Keep adjusting",
        history=[],
        plan_data=plan_data,
        exercise_library=lib,
    )

    assert len(responses) == PlanRefiner.MAX_ITERATIONS
    assert adapter.tool_use.call_count == PlanRefiner.MAX_ITERATIONS
