import json
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from flexloop.ai.coach import AICoach
from flexloop.ai.exercise_resolver import resolve_exercise_name
from flexloop.ai.factory import create_adapter
from flexloop.ai.prompts import PromptManager
from flexloop.config import settings
from flexloop.db.engine import get_session
from flexloop.models.ai import AIChatMessage, AIReview, AIUsage
from flexloop.models.cycle_tracker import CycleTracker
from flexloop.models.exercise import Exercise
from flexloop.models.personal_record import PersonalRecord
from flexloop.models.plan import ExerciseGroup, Plan, PlanDay, PlanExercise
from flexloop.models.user import User
from flexloop.models.workout import WorkoutSession, WorkoutSet
from flexloop.ai.refiner import PlanRefiner, REFINER_TOOLS
from flexloop.schemas.ai import (
    AIChatRequest,
    AIChatResponse,
    AIReviewRequest,
    AIUsageResponse,
    SuggestSwapRequest,
    AdjustVolumeRequest,
    ExplainExerciseRequest,
    PlanRefineRequest,
)
from flexloop.schemas.plan import PlanGenerateRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

PROMPTS_DIR = "prompts"


def get_ai_coach() -> AICoach:
    adapter = create_adapter(
        provider=settings.ai_provider,
        model=settings.ai_model,
        api_key=settings.ai_api_key,
        base_url=settings.ai_base_url,
    )
    prompt_manager = PromptManager(PROMPTS_DIR)
    return AICoach(adapter=adapter, prompt_manager=prompt_manager)


async def update_usage(user_id: int, llm_response: "LLMResponse", db: AsyncSession):
    """Track token usage and cache stats."""
    from flexloop.ai.base import LLMResponse as LR  # noqa
    month_key = date.today().strftime("%Y-%m")
    result = await db.execute(
        select(AIUsage).where(AIUsage.user_id == user_id, AIUsage.month == month_key)
    )
    usage = result.scalar_one_or_none()
    if usage:
        usage.total_input_tokens += llm_response.input_tokens
        usage.total_output_tokens += llm_response.output_tokens
        usage.total_cache_read_tokens += llm_response.cache_read_tokens
        usage.total_cache_creation_tokens += llm_response.cache_creation_tokens
        usage.call_count += 1
    else:
        usage = AIUsage(
            user_id=user_id,
            month=month_key,
            total_input_tokens=llm_response.input_tokens,
            total_output_tokens=llm_response.output_tokens,
            total_cache_read_tokens=llm_response.cache_read_tokens,
            total_cache_creation_tokens=llm_response.cache_creation_tokens,
            call_count=1,
        )
        db.add(usage)


def format_user_profile(user: User) -> str:
    return (
        f"Name: {user.name}\n"
        f"Gender: {user.gender}, Age: {user.age}\n"
        f"Height: {user.height}{user.height_unit}, Weight: {user.weight}{user.weight_unit}\n"
        f"Weight unit: {user.weight_unit}\n"
        f"Experience: {user.experience_level}\n"
        f"Goals: {user.goals}\n"
        f"Available equipment: {', '.join(user.available_equipment)}"
    )


def format_plan_profile(user: User) -> str:
    return (
        f"Gender: {user.gender}, Age: {user.age}\n"
        f"Weight: {user.weight}{user.weight_unit}\n"
        f"Weight unit: {user.weight_unit}\n"
        f"Experience: {user.experience_level}\n"
        f"Goals: {user.goals}"
    )


# --- Plan Generation ---

@router.post("/plan/generate")
async def generate_plan(
    data: PlanGenerateRequest, session: AsyncSession = Depends(get_session)
):
    from flexloop.ai.plan_modes import PLAN_MODES

    # Load user
    result = await session.execute(select(User).where(User.id == data.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Look up plan mode metadata
    mode = PLAN_MODES[data.plan_mode]

    # Load exercise library for name-to-id mapping
    ex_result = await session.execute(select(Exercise))
    exercises = {e.name.lower(): e for e in ex_result.scalars().all()}

    # Generate plan via AI
    coach = get_ai_coach()
    profile_text = format_plan_profile(user)
    plan_data, llm_response = await coach.generate_plan(
        profile_text, mode["description"], user.weight_unit,
    )

    if plan_data is None:
        return {
            "status": "error",
            "message": "AI returned invalid plan format. Raw response included.",
            "raw_response": llm_response.content,
            "input_tokens": llm_response.input_tokens,
            "output_tokens": llm_response.output_tokens,
        }

    # Deactivate existing plans for this user
    await session.execute(
        update(Plan).where(Plan.user_id == user.id).values(status="inactive")
    )

    # Save plan — inject metadata from PLAN_MODES, not from AI output
    plan = Plan(
        user_id=user.id,
        name=mode["plan_name"],
        split_type=mode["split_type"],
        cycle_length=mode["cycle_length"],
        status="active",
        ai_generated=True,
    )
    session.add(plan)
    await session.flush()

    for day_data in plan_data.get("days", []):
        plan_day = PlanDay(
            plan_id=plan.id,
            day_number=day_data.get("day_number", 1),
            label=day_data.get("label", "Workout"),
            focus=day_data.get("focus", ""),
        )
        session.add(plan_day)
        await session.flush()

        for group_data in day_data.get("exercise_groups", []):
            group = ExerciseGroup(
                plan_day_id=plan_day.id,
                group_type=group_data.get("group_type", "straight"),
                order=group_data.get("order", 1),
                rest_after_group_sec=group_data.get("rest_after_group_sec", 90),
            )
            session.add(group)
            await session.flush()

            for i, ex_data in enumerate(group_data.get("exercises", [])):
                # Normalize sets_json field names (AI may output target_weight_kg or target_weight)
                raw_sets = ex_data.get("sets_json", [])
                if raw_sets:
                    normalized = []
                    for s in raw_sets:
                        ns = dict(s)
                        if "target_weight_kg" in ns and "target_weight" not in ns:
                            ns["target_weight"] = ns.pop("target_weight_kg")
                        normalized.append(ns)
                    ex_data["sets_json"] = normalized

                ex_name = ex_data.get("exercise_name", "")
                exercise = resolve_exercise_name(ex_name, exercises)

                if not exercise:
                    logger.warning(f"Exercise not found in library: {ex_name}")
                    continue

                plan_exercise = PlanExercise(
                    plan_day_id=plan_day.id,
                    exercise_group_id=group.id,
                    exercise_id=exercise.id,
                    order=i + 1,
                    sets=ex_data.get("sets", 3),
                    reps=ex_data.get("reps", 10),
                    weight=ex_data.get("weight"),
                    rpe_target=ex_data.get("rpe_target"),
                    sets_json=ex_data.get("sets_json"),
                    notes=ex_data.get("notes"),
                )
                session.add(plan_exercise)

    # Log AI interaction
    review = AIReview(
        user_id=user.id,
        plan_id=plan.id,
        review_type="plan_generation",
        input_summary=profile_text,
        output_json=plan_data,
        suggestions_json=None,
        model_used=settings.ai_model,
        input_tokens=llm_response.input_tokens,
        output_tokens=llm_response.output_tokens,
        estimated_cost=0.0,
    )
    session.add(review)

    await update_usage(user.id, llm_response, session)

    # Create or update cycle tracker
    tracker_result = await session.execute(
        select(CycleTracker).where(CycleTracker.user_id == user.id)
    )
    tracker = tracker_result.scalar_one_or_none()
    if tracker:
        tracker.plan_id = plan.id
        tracker.next_day_number = 1
        tracker.last_completed_at = None
    else:
        tracker = CycleTracker(user_id=user.id, plan_id=plan.id, next_day_number=1)
        session.add(tracker)

    await session.commit()

    # Re-fetch plan with relationships
    result = await session.execute(
        select(Plan)
        .where(Plan.id == plan.id)
        .options(
            selectinload(Plan.days)
            .selectinload(PlanDay.exercise_groups)
            .selectinload(ExerciseGroup.exercises)
        )
    )
    saved_plan = result.scalar_one()

    return {
        "status": "success",
        "plan_id": saved_plan.id,
        "plan_name": saved_plan.name,
        "split_type": saved_plan.split_type,
        "cycle_length": saved_plan.cycle_length,
        "days": [
            {
                "day_number": d.day_number,
                "label": d.label,
                "focus": d.focus,
                "exercise_groups": [
                    {
                        "group_type": g.group_type,
                        "rest_after_group_sec": g.rest_after_group_sec,
                        "exercises": [
                            {
                                "exercise_id": e.exercise_id,
                                "sets": e.sets,
                                "reps": e.reps,
                                "weight": e.weight,
                                "rpe_target": e.rpe_target,
                                "sets_json": e.sets_json,
                                "notes": e.notes,
                            }
                            for e in sorted(g.exercises, key=lambda x: x.order)
                        ],
                    }
                    for g in sorted(d.exercise_groups, key=lambda x: x.order)
                ],
            }
            for d in sorted(saved_plan.days, key=lambda x: x.day_number)
        ],
        "input_tokens": llm_response.input_tokens,
        "output_tokens": llm_response.output_tokens,
    }


# --- AI Chat ---

@router.post("/chat", response_model=AIChatResponse)
async def ai_chat(
    data: AIChatRequest, session: AsyncSession = Depends(get_session)
):
    # Load user
    result = await session.execute(select(User).where(User.id == data.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Load recent chat history
    chat_result = await session.execute(
        select(AIChatMessage)
        .where(AIChatMessage.user_id == data.user_id)
        .order_by(AIChatMessage.created_at.desc())
        .limit(20)
    )
    history = list(reversed(chat_result.scalars().all()))

    # Load recent workouts with sets for context
    workouts_result = await session.execute(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == data.user_id)
        .options(selectinload(WorkoutSession.sets))
        .order_by(WorkoutSession.started_at.desc())
        .limit(10)
    )
    recent_workouts = workouts_result.scalars().all()

    # Load exercise names for readable context
    exercise_ids = {s.exercise_id for w in recent_workouts for s in w.sets}
    exercise_names: dict[int, str] = {}
    if exercise_ids:
        ex_result = await session.execute(
            select(Exercise).where(Exercise.id.in_(exercise_ids))
        )
        exercise_names = {e.id: e.name for e in ex_result.scalars().all()}

    # Load active plan
    plan_result = await session.execute(
        select(Plan)
        .where(Plan.user_id == data.user_id)
        .options(selectinload(Plan.days).selectinload(PlanDay.exercise_groups).selectinload(ExerciseGroup.exercises))
        .order_by(Plan.created_at.desc())
        .limit(1)
    )
    active_plan = plan_result.scalars().first()

    # Load PRs
    pr_result = await session.execute(
        select(PersonalRecord)
        .where(PersonalRecord.user_id == data.user_id, PersonalRecord.pr_type == "estimated_1rm")
    )
    prs = pr_result.scalars().all()

    # Build context
    profile_text = format_user_profile(user)

    # Detailed workout history
    if not recent_workouts:
        history_text = "No recent workouts."
    else:
        workout_lines = []
        for w in recent_workouts:
            sets_by_exercise: dict[int, list] = {}
            for s in w.sets:
                sets_by_exercise.setdefault(s.exercise_id, []).append(s)
            exercise_details = []
            for ex_id, sets in sets_by_exercise.items():
                name = exercise_names.get(ex_id, f"Exercise #{ex_id}")
                set_strs = [
                    f"{s.weight}{user.weight_unit} x {s.reps}" + (f" RPE {s.rpe}" if s.rpe else "")
                    for s in sets if s.weight and s.reps
                ]
                if set_strs:
                    exercise_details.append(f"  {name}: {', '.join(set_strs)}")
            date_str = w.started_at.strftime('%Y-%m-%d')
            workout_lines.append(f"- {date_str} ({w.source}):")
            workout_lines.extend(exercise_details or ["  (no sets logged)"])
        history_text = "\n".join(workout_lines)

    # Plan context
    if active_plan:
        plan_lines = [f"Active plan: {active_plan.name} ({active_plan.split_type})"]
        for day in (active_plan.days or []):
            exercises = []
            for group in (day.exercise_groups or []):
                for ex in (group.exercises or []):
                    name = exercise_names.get(ex.exercise_id, f"Exercise #{ex.exercise_id}")
                    exercises.append(f"{name} {ex.sets}x{ex.reps}")
            plan_lines.append(f"  Day {day.day_number} ({day.label}): {', '.join(exercises)}")
        plan_text = "\n".join(plan_lines)
    else:
        plan_text = "No active plan."

    # PR context
    if prs:
        pr_lines = []
        for pr in prs:
            name = exercise_names.get(pr.exercise_id, f"Exercise #{pr.exercise_id}")
            pr_lines.append(f"- {name}: est. 1RM {pr.value:.1f}{user.weight_unit}")
        history_text += "\n\nPersonal Records:\n" + "\n".join(pr_lines)

    messages = [{"role": m.role, "content": m.content} for m in history]
    messages.append({"role": "user", "content": data.message})

    # Call AI
    coach = get_ai_coach()
    llm_response = await coach.chat(
        messages=messages,
        user_profile=profile_text,
        current_plan=plan_text,
        training_history=history_text,
    )

    # Save messages
    user_msg = AIChatMessage(
        user_id=data.user_id, role="user", content=data.message,
        input_tokens=llm_response.input_tokens, output_tokens=0,
    )
    assistant_msg = AIChatMessage(
        user_id=data.user_id, role="assistant", content=llm_response.content,
        input_tokens=0, output_tokens=llm_response.output_tokens,
    )
    session.add_all([user_msg, assistant_msg])

    await update_usage(data.user_id, llm_response, session)

    await session.commit()

    return AIChatResponse(
        reply=llm_response.content,
        input_tokens=llm_response.input_tokens,
        output_tokens=llm_response.output_tokens,
    )


# --- AI Review ---

@router.post("/review")
async def ai_review(
    data: AIReviewRequest, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(select(User).where(User.id == data.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Load all workouts for the user
    workouts_result = await session.execute(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == data.user_id)
        .options(selectinload(WorkoutSession.sets))
        .order_by(WorkoutSession.started_at)
    )
    workouts = workouts_result.scalars().all()

    if not workouts:
        raise HTTPException(status_code=400, detail="No workout data to review")

    # Build training data summary
    training_lines = []
    for w in workouts:
        sets_summary = []
        for s in w.sets:
            parts = []
            if s.weight: parts.append(f"{s.weight}{user.weight_unit}")
            if s.reps: parts.append(f"{s.reps}reps")
            if s.rpe: parts.append(f"RPE {s.rpe}")
            sets_summary.append(f"  Set {s.set_number} ({s.set_type}): {', '.join(parts)}")
        training_lines.append(
            f"Session {w.started_at.strftime('%Y-%m-%d')} ({w.source}):\n" +
            "\n".join(sets_summary)
        )
    training_data = "\n\n".join(training_lines)

    coach = get_ai_coach()
    review_data, llm_response = await coach.review_block(
        user_profile=format_user_profile(user),
        training_data=training_data,
        volume_landmarks="Using general guidelines for " + user.experience_level + " lifters.",
    )

    if review_data is None:
        return {
            "status": "error",
            "message": "AI returned invalid review format.",
            "raw_response": llm_response.content,
        }

    # Save review
    review = AIReview(
        user_id=user.id,
        plan_id=data.plan_id,
        review_type="block",
        input_summary=f"Review of {len(workouts)} sessions",
        output_json=review_data,
        suggestions_json=review_data.get("suggestions", []),
        model_used=settings.ai_model,
        input_tokens=llm_response.input_tokens,
        output_tokens=llm_response.output_tokens,
    )
    session.add(review)
    await session.commit()

    return {
        "status": "success",
        "review_id": review.id,
        **review_data,
        "input_tokens": llm_response.input_tokens,
        "output_tokens": llm_response.output_tokens,
    }


# --- Plan Refinement ---


def get_plan_refiner() -> PlanRefiner:
    adapter = create_adapter(
        provider=settings.ai_provider, model=settings.ai_model,
        api_key=settings.ai_api_key, base_url=settings.ai_base_url,
    )
    prompt_manager = PromptManager(PROMPTS_DIR)
    return PlanRefiner(adapter=adapter, prompt_manager=prompt_manager)


def _serialize_plan_for_prompt(plan, exercise_names: dict) -> str:
    lines = []
    for day in sorted(plan.days or [], key=lambda d: d.day_number):
        exercises = []
        for group in sorted(day.exercise_groups or [], key=lambda g: g.order):
            for ex in sorted(group.exercises or [], key=lambda e: e.order):
                name = exercise_names.get(ex.exercise_id, f"Exercise #{ex.exercise_id}")
                exercises.append(f"{name} {ex.sets}x{ex.reps}")
        lines.append(f"Day {day.day_number} ({day.label}): {', '.join(exercises)}")
    return "\n".join(lines)


def _plan_to_data(plan, exercise_names: dict) -> dict:
    return {
        "days": [
            {
                "day_number": d.day_number,
                "label": d.label,
                "focus": d.focus,
                "exercise_groups": [
                    {
                        "group_type": g.group_type,
                        "order": g.order,
                        "rest_after_group_sec": g.rest_after_group_sec,
                        "exercises": [
                            {
                                "exercise_id": e.exercise_id,
                                "exercise_name": exercise_names.get(e.exercise_id, ""),
                                "order": e.order,
                                "sets": e.sets,
                                "reps": e.reps,
                                "weight": e.weight,
                                "rpe_target": e.rpe_target,
                                "sets_json": e.sets_json,
                                "notes": e.notes,
                            }
                            for e in sorted(g.exercises or [], key=lambda x: x.order)
                        ],
                    }
                    for g in sorted(d.exercise_groups or [], key=lambda x: x.order)
                ],
            }
            for d in sorted(plan.days or [], key=lambda x: x.day_number)
        ]
    }


async def _load_refinement_context(plan_id: int, user_id: int, session):
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    plan_result = await session.execute(
        select(Plan).where(Plan.id == plan_id)
        .options(
            selectinload(Plan.days)
            .selectinload(PlanDay.exercise_groups)
            .selectinload(ExerciseGroup.exercises)
        )
    )
    plan = plan_result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    ex_result = await session.execute(select(Exercise))
    all_exercises = ex_result.scalars().all()
    exercise_library = {e.name.lower(): e for e in all_exercises}
    exercise_names = {e.id: e.name for e in all_exercises}

    return user, plan, exercise_library, exercise_names


@router.post("/plan/{plan_id}/suggest-swap")
async def suggest_swap(
    plan_id: int, data: SuggestSwapRequest, session: AsyncSession = Depends(get_session)
):
    user, plan, exercise_library, exercise_names = await _load_refinement_context(
        plan_id, data.user_id, session
    )

    plan_data = _plan_to_data(plan, exercise_names)
    plan_text = _serialize_plan_for_prompt(plan, exercise_names)
    ex_list = "\n".join(sorted(exercise_names.values()))

    refiner = get_plan_refiner()
    system_prompt = refiner.prompts.render(
        "plan_refinement",
        user_profile=format_plan_profile(user),
        plan_structure=plan_text,
        exercise_library=ex_list,
        weight_unit=user.weight_unit,
    )

    user_prompt = (
        f"Suggest 3 alternative exercises to replace '{data.exercise_name}' "
        f"on Day {data.day_number}. For each alternative, call swap_exercise with "
        f"full details (sets, reps, rpe_target, weight). Consider the user's profile and goals."
    )

    changes, text, response = await refiner.refine_single_shot(
        system_prompt, user_prompt, plan_data, exercise_library,
        tools=[t for t in REFINER_TOOLS if t.name == "swap_exercise"],
    )

    # Find original exercise info
    found = refiner._find_exercise_in_plan(_plan_to_data(plan, exercise_names), data.day_number, data.exercise_name)
    original = None
    if found:
        _, group, ex, _ = found
        original = {"exercise_id": ex.get("exercise_id"), "exercise_name": ex.get("exercise_name")}

    await update_usage(data.user_id, response.to_llm_response(), session)
    await session.commit()

    alternatives = []
    for c in changes:
        alt = {
            "exercise_name": c.after.get("exercise_name", ""),
            "exercise_id": c.after.get("exercise_id"),
            "sets": c.after.get("sets"),
            "reps": c.after.get("reps"),
            "rpe_target": c.after.get("rpe_target"),
            "weight": c.after.get("weight"),
            "reasoning": c.reasoning,
        }
        if c.warning:
            alt["warning"] = c.warning
        alternatives.append(alt)

    return {
        "status": "success",
        "alternatives": alternatives,
        "original": original,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
    }


@router.post("/plan/{plan_id}/adjust-volume")
async def adjust_volume(
    plan_id: int, data: AdjustVolumeRequest, session: AsyncSession = Depends(get_session)
):
    user, plan, exercise_library, exercise_names = await _load_refinement_context(
        plan_id, data.user_id, session
    )

    plan_data = _plan_to_data(plan, exercise_names)
    plan_text = _serialize_plan_for_prompt(plan, exercise_names)
    ex_list = "\n".join(sorted(exercise_names.values()))

    refiner = get_plan_refiner()
    system_prompt = refiner.prompts.render(
        "plan_refinement",
        user_profile=format_plan_profile(user),
        plan_structure=plan_text,
        exercise_library=ex_list,
        weight_unit=user.weight_unit,
    )

    direction_text = {
        "lighter": "Reduce volume (fewer sets, lower RPE/weight)",
        "heavier": "Increase volume (more sets, higher RPE/weight)",
        "auto": "Adjust volume based on the user's experience level and goals",
    }
    user_prompt = (
        f"Adjust the volume for Day {data.day_number}. Direction: {direction_text[data.direction]}. "
        f"Call adjust_sets for each exercise that needs changing."
    )

    changes, text, response = await refiner.refine_single_shot(
        system_prompt, user_prompt, plan_data, exercise_library,
        tools=[t for t in REFINER_TOOLS if t.name == "adjust_sets"],
    )

    await update_usage(data.user_id, response.to_llm_response(), session)
    await session.commit()

    return {
        "status": "success",
        "changes": [
            {
                "exercise_name": c.exercise_name,
                "exercise_id": c.exercise_id,
                "day_number": c.day_number,
                "before": c.before,
                "after": c.after,
                "reasoning": c.reasoning,
            }
            for c in changes
        ],
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
    }


@router.post("/plan/{plan_id}/explain")
async def explain_exercise(
    plan_id: int, data: ExplainExerciseRequest, session: AsyncSession = Depends(get_session)
):
    user, plan, exercise_library, exercise_names = await _load_refinement_context(
        plan_id, data.user_id, session
    )

    plan_text = _serialize_plan_for_prompt(plan, exercise_names)

    coach = get_ai_coach()
    system_prompt = coach.prompts.render(
        "plan_refinement",
        user_profile=format_plan_profile(user),
        plan_structure=plan_text,
        exercise_library="\n".join(sorted(exercise_names.values())),
        weight_unit=user.weight_unit,
    )

    user_prompt = (
        f"Explain why '{data.exercise_name}' was chosen for Day {data.day_number}. "
        f"Consider its role in the overall plan, the user's experience level, and goals. "
        f"Respond with a clear explanation."
    )

    llm_response = await coach.adapter.generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=settings.ai_temperature,
        max_tokens=500,
    )

    await update_usage(data.user_id, llm_response, session)
    await session.commit()

    return {
        "status": "success",
        "explanation": llm_response.content,
        "input_tokens": llm_response.input_tokens,
        "output_tokens": llm_response.output_tokens,
    }


@router.post("/plan/{plan_id}/refine")
async def refine_plan(
    plan_id: int, data: PlanRefineRequest, session: AsyncSession = Depends(get_session)
):
    user, plan, exercise_library, exercise_names = await _load_refinement_context(
        plan_id, data.user_id, session
    )

    plan_data = _plan_to_data(plan, exercise_names)
    plan_text = _serialize_plan_for_prompt(plan, exercise_names)
    ex_list = "\n".join(sorted(exercise_names.values()))

    refiner = get_plan_refiner()
    system_prompt = refiner.prompts.render(
        "plan_refinement",
        user_profile=format_plan_profile(user),
        plan_structure=plan_text,
        exercise_library=ex_list,
        weight_unit=user.weight_unit,
    )

    changes, reply, responses = await refiner.refine_agentic(
        system_prompt=system_prompt,
        user_message=data.message,
        history=data.history,
        plan_data=plan_data,
        exercise_library=exercise_library,
    )

    for resp in responses:
        await update_usage(data.user_id, resp.to_llm_response(), session)
    await session.commit()

    total_input = sum(r.input_tokens for r in responses)
    total_output = sum(r.output_tokens for r in responses)

    return {
        "status": "success",
        "reply": reply,
        "changes": [
            {
                "tool_name": c.tool_name,
                "day_number": c.day_number,
                "exercise_name": c.exercise_name,
                "exercise_id": c.exercise_id,
                "before": c.before,
                "after": c.after,
                "reasoning": c.reasoning,
                **({"warning": c.warning} if c.warning else {}),
            }
            for c in changes
        ],
        "applied": False,
        "max_iterations_reached": len(responses) >= refiner.MAX_ITERATIONS,
        "input_tokens": total_input,
        "output_tokens": total_output,
    }


# --- Usage ---

@router.get("/usage", response_model=list[AIUsageResponse])
async def get_ai_usage(user_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(AIUsage).where(AIUsage.user_id == user_id).order_by(AIUsage.month.desc())
    )
    return result.scalars().all()
