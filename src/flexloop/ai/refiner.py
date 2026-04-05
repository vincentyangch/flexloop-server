"""PlanRefiner engine — AI-assisted plan modifications via tool use."""

import copy
import json
import logging
from dataclasses import dataclass

from flexloop.ai.base import LLMAdapter, ToolCall, ToolDef, ToolUseResponse
from flexloop.ai.exercise_resolver import resolve_exercise_name
from flexloop.ai.prompts import PromptManager
from flexloop.config import settings

logger = logging.getLogger(__name__)


@dataclass
class PlanChange:
    """A single proposed change to a plan."""
    tool_name: str
    day_number: int
    exercise_name: str
    exercise_id: int | None
    before: dict
    after: dict
    reasoning: str
    warning: str | None = None


REFINER_TOOLS = [
    ToolDef(
        name="swap_exercise",
        description="Replace one exercise with another on a specific day. Use when the user wants an alternative exercise.",
        input_schema={
            "type": "object",
            "properties": {
                "day_number": {"type": "integer", "description": "The day number in the plan"},
                "exercise_name": {"type": "string", "description": "Current exercise to replace"},
                "replacement_name": {"type": "string", "description": "New exercise name"},
                "sets": {"type": "integer", "description": "Number of sets for the new exercise"},
                "reps": {"type": "integer", "description": "Reps per set"},
                "rpe_target": {"type": "number", "description": "Target RPE (1-10)"},
                "weight": {"type": "number", "description": "Target weight"},
                "reason": {"type": "string", "description": "Why this swap is recommended"},
            },
            "required": ["day_number", "exercise_name", "replacement_name", "reason"],
        },
    ),
    ToolDef(
        name="adjust_sets",
        description="Change sets, reps, weight, or RPE for an existing exercise.",
        input_schema={
            "type": "object",
            "properties": {
                "day_number": {"type": "integer"},
                "exercise_name": {"type": "string", "description": "Exercise to adjust"},
                "sets": {"type": "integer"},
                "reps": {"type": "integer"},
                "rpe_target": {"type": "number"},
                "weight": {"type": "number"},
            },
            "required": ["day_number", "exercise_name"],
        },
    ),
    ToolDef(
        name="add_exercise",
        description="Add a new exercise to a specific day.",
        input_schema={
            "type": "object",
            "properties": {
                "day_number": {"type": "integer"},
                "exercise_name": {"type": "string"},
                "sets": {"type": "integer"},
                "reps": {"type": "integer"},
                "rpe_target": {"type": "number"},
                "weight": {"type": "number"},
                "group_type": {"type": "string"},
                "order_after": {"type": "string", "description": "Insert after this exercise, or null for end"},
            },
            "required": ["day_number", "exercise_name"],
        },
    ),
    ToolDef(
        name="remove_exercise",
        description="Remove an exercise from a specific day.",
        input_schema={
            "type": "object",
            "properties": {
                "day_number": {"type": "integer"},
                "exercise_name": {"type": "string"},
            },
            "required": ["day_number", "exercise_name"],
        },
    ),
    ToolDef(
        name="explain_choice",
        description="Explain why a specific exercise was chosen for its slot in the plan. Read-only, does not modify the plan.",
        input_schema={
            "type": "object",
            "properties": {
                "day_number": {"type": "integer"},
                "exercise_name": {"type": "string"},
            },
            "required": ["day_number", "exercise_name"],
        },
    ),
]


class PlanRefiner:
    """AI-assisted plan refinement engine."""

    MAX_ITERATIONS = 5

    def __init__(self, adapter: LLMAdapter, prompt_manager: PromptManager):
        self.adapter = adapter
        self.prompts = prompt_manager

    def _find_exercise_in_plan(self, plan_data: dict, day_number: int, exercise_name: str):
        """Find an exercise in plan data by day number and name.

        Returns (day, group, exercise, index) or None.
        """
        normalized = exercise_name.strip().lower()
        for day in plan_data.get("days", []):
            if day.get("day_number") != day_number:
                continue
            for group in day.get("exercise_groups", []):
                for i, ex in enumerate(group.get("exercises", [])):
                    if ex.get("exercise_name", "").strip().lower() == normalized:
                        return day, group, ex, i
        return None

    def _execute_tool(
        self, tool_call: ToolCall, plan_data: dict, exercise_library: dict,
    ) -> PlanChange | None:
        """Execute a tool call against plan data in-memory. Returns PlanChange or None."""
        inp = tool_call.input
        day_number = inp.get("day_number", 0)
        exercise_name = inp.get("exercise_name", "")

        if tool_call.name == "swap_exercise":
            found = self._find_exercise_in_plan(plan_data, day_number, exercise_name)
            if not found:
                return None
            day, group, ex, idx = found
            before = dict(ex)
            replacement_name = inp.get("replacement_name", "")
            resolved = resolve_exercise_name(replacement_name, exercise_library)
            after = dict(ex)
            after["exercise_name"] = replacement_name
            after["exercise_id"] = resolved.id if resolved else None
            for key in ("sets", "reps", "rpe_target", "weight"):
                if key in inp:
                    after[key] = inp[key]
            group["exercises"][idx] = after
            warning = None if resolved else "exercise not in library"
            return PlanChange(
                tool_name="swap_exercise", day_number=day_number,
                exercise_name=exercise_name, exercise_id=before.get("exercise_id"),
                before=before, after=after,
                reasoning=inp.get("reason", ""), warning=warning,
            )

        elif tool_call.name == "adjust_sets":
            found = self._find_exercise_in_plan(plan_data, day_number, exercise_name)
            if not found:
                return None
            day, group, ex, idx = found
            before = dict(ex)
            after = dict(ex)
            for key in ("sets", "reps", "rpe_target", "weight"):
                if key in inp:
                    after[key] = inp[key]
            group["exercises"][idx] = after
            return PlanChange(
                tool_name="adjust_sets", day_number=day_number,
                exercise_name=exercise_name, exercise_id=ex.get("exercise_id"),
                before=before, after=after, reasoning="",
            )

        elif tool_call.name == "add_exercise":
            for day in plan_data.get("days", []):
                if day.get("day_number") != day_number:
                    continue
                resolved = resolve_exercise_name(exercise_name, exercise_library)
                new_ex = {
                    "exercise_name": exercise_name,
                    "exercise_id": resolved.id if resolved else None,
                    "sets": inp.get("sets", 3),
                    "reps": inp.get("reps", 10),
                    "rpe_target": inp.get("rpe_target"),
                    "weight": inp.get("weight"),
                }
                groups = day.get("exercise_groups", [])
                if groups:
                    groups[-1]["exercises"].append(new_ex)
                else:
                    day["exercise_groups"] = [{
                        "group_type": inp.get("group_type", "straight"),
                        "order": 1, "rest_after_group_sec": 90,
                        "exercises": [new_ex],
                    }]
                warning = None if resolved else "exercise not in library"
                return PlanChange(
                    tool_name="add_exercise", day_number=day_number,
                    exercise_name=exercise_name, exercise_id=resolved.id if resolved else None,
                    before={}, after=new_ex,
                    reasoning="", warning=warning,
                )
            return None

        elif tool_call.name == "remove_exercise":
            found = self._find_exercise_in_plan(plan_data, day_number, exercise_name)
            if not found:
                return None
            day, group, ex, idx = found
            before = dict(ex)
            group["exercises"].pop(idx)
            return PlanChange(
                tool_name="remove_exercise", day_number=day_number,
                exercise_name=exercise_name, exercise_id=ex.get("exercise_id"),
                before=before, after={}, reasoning="",
            )

        elif tool_call.name == "explain_choice":
            return None

        return None

    async def refine_single_shot(
        self, system_prompt: str, user_prompt: str,
        plan_data: dict, exercise_library: dict,
        tools: list[ToolDef] | None = None,
    ) -> tuple[list[PlanChange], str, ToolUseResponse]:
        """Single-shot refinement: one LLM call, execute tool calls, return changes."""
        plan_copy = copy.deepcopy(plan_data)
        active_tools = tools or REFINER_TOOLS

        response = await self.adapter.tool_use(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=active_tools,
            tool_choice="any",
            temperature=settings.ai_temperature,
            max_tokens=settings.ai_max_tokens,
        )

        changes = []
        for tc in response.tool_calls:
            change = self._execute_tool(tc, plan_copy, exercise_library)
            if change:
                changes.append(change)

        return changes, response.text, response

    async def refine_agentic(
        self, system_prompt: str, user_message: str,
        history: list[dict],
        plan_data: dict, exercise_library: dict,
    ) -> tuple[list[PlanChange], str, list[ToolUseResponse]]:
        """Agentic refinement: loop until model stops calling tools or max iterations."""
        plan_copy = copy.deepcopy(plan_data)
        changes: list[PlanChange] = []
        all_responses: list[ToolUseResponse] = []

        messages = list(history) + [{"role": "user", "content": user_message}]

        for iteration in range(self.MAX_ITERATIONS):
            response = await self.adapter.tool_use(
                system_prompt=system_prompt,
                messages=messages,
                tools=REFINER_TOOLS,
                tool_choice="auto",
                temperature=settings.ai_temperature,
                max_tokens=settings.ai_max_tokens,
            )
            all_responses.append(response)

            # No tool calls → model is done
            if not response.tool_calls:
                break

            # Execute all tool calls (always, regardless of stop_reason)
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for tc in response.tool_calls:
                change = self._execute_tool(tc, plan_copy, exercise_library)
                if change:
                    changes.append(change)
                    result_text = json.dumps({"status": "ok", "change": change.after})
                else:
                    if tc.name == "explain_choice":
                        result_text = json.dumps({"status": "ok", "note": "Explanation included in text response."})
                    else:
                        result_text = json.dumps({"status": "error", "message": f"Exercise not found: {tc.input.get('exercise_name', '')}"})
                tool_results.append({
                    "tool_use_id": tc.id,
                    "content": result_text,
                    "is_error": change is None and tc.name != "explain_choice",
                })
            messages.append({"role": "tool_results", "results": tool_results})

            # Check stop reason — provider-agnostic: Anthropic="tool_use", OpenAI/Ollama="tool_calls"
            if response.stop_reason not in ("tool_use", "tool_calls"):
                break

        final_text = all_responses[-1].text if all_responses else ""
        return changes, final_text, all_responses
