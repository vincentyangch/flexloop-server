from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from flexloop.db.engine import get_session
from flexloop.models.cycle_tracker import CycleTracker
from flexloop.models.plan import ExerciseGroup, Plan, PlanDay, PlanExercise
from flexloop.schemas.plan import (
    PlanCreate,
    PlanListResponse,
    PlanResponse,
    PlanUpdate,
)

router = APIRouter(prefix="/api/plans", tags=["plans"])


def _plan_query(plan_id: int | None = None, user_id: int | None = None):
    q = select(Plan).options(
        selectinload(Plan.days)
        .selectinload(PlanDay.exercise_groups)
        .selectinload(ExerciseGroup.exercises)
    )
    if plan_id is not None:
        q = q.where(Plan.id == plan_id)
    if user_id is not None:
        q = q.where(Plan.user_id == user_id)
    return q


@router.post("", status_code=201, response_model=PlanResponse)
async def create_plan(data: PlanCreate, session: AsyncSession = Depends(get_session)):
    # Deactivate other plans for this user
    await session.execute(
        update(Plan).where(Plan.user_id == data.user_id).values(status="inactive")
    )

    plan = Plan(
        user_id=data.user_id,
        name=data.name,
        split_type=data.split_type,
        cycle_length=data.cycle_length,
        status="active",
        ai_generated=False,
    )
    session.add(plan)
    await session.flush()

    for day_data in data.days:
        plan_day = PlanDay(
            plan_id=plan.id,
            day_number=day_data.day_number,
            label=day_data.label,
            focus=day_data.focus,
        )
        session.add(plan_day)
        await session.flush()

        for group_data in day_data.exercise_groups:
            group = ExerciseGroup(
                plan_day_id=plan_day.id,
                group_type=group_data.group_type,
                order=group_data.order,
                rest_after_group_sec=group_data.rest_after_group_sec,
            )
            session.add(group)
            await session.flush()

            for ex_data in group_data.exercises:
                plan_ex = PlanExercise(
                    plan_day_id=plan_day.id,
                    exercise_group_id=group.id,
                    exercise_id=ex_data.exercise_id,
                    order=ex_data.order,
                    sets=ex_data.sets,
                    reps=ex_data.reps,
                    weight=ex_data.weight,
                    rpe_target=ex_data.rpe_target,
                    sets_json=[s.model_dump() for s in ex_data.sets_json] if ex_data.sets_json else None,
                    notes=ex_data.notes,
                )
                session.add(plan_ex)

    await session.commit()

    result = await session.execute(_plan_query(plan_id=plan.id))
    return result.scalar_one()


@router.get("", response_model=PlanListResponse)
async def list_plans(
    user_id: int,
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    q = _plan_query(user_id=user_id)
    if status:
        q = q.where(Plan.status == status)
    q = q.order_by(Plan.created_at.desc())
    result = await session.execute(q)
    plans = list(result.scalars().all())
    return PlanListResponse(plans=plans, total=len(plans))


@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(plan_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(_plan_query(plan_id=plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.put("/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: int, data: PlanUpdate, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    if data.name is not None:
        plan.name = data.name
    if data.split_type is not None:
        plan.split_type = data.split_type
    if data.cycle_length is not None:
        plan.cycle_length = data.cycle_length

    if data.days is not None:
        # Full replacement: delete old days, create new
        old_days = await session.execute(
            select(PlanDay).where(PlanDay.plan_id == plan_id)
        )
        for old_day in old_days.scalars().all():
            await session.delete(old_day)
        await session.flush()

        for day_data in data.days:
            plan_day = PlanDay(
                plan_id=plan.id,
                day_number=day_data.day_number,
                label=day_data.label,
                focus=day_data.focus,
            )
            session.add(plan_day)
            await session.flush()

            for group_data in day_data.exercise_groups:
                group = ExerciseGroup(
                    plan_day_id=plan_day.id,
                    group_type=group_data.group_type,
                    order=group_data.order,
                    rest_after_group_sec=group_data.rest_after_group_sec,
                )
                session.add(group)
                await session.flush()

                for ex_data in group_data.exercises:
                    plan_ex = PlanExercise(
                        plan_day_id=plan_day.id,
                        exercise_group_id=group.id,
                        exercise_id=ex_data.exercise_id,
                        order=ex_data.order,
                        sets=ex_data.sets,
                        reps=ex_data.reps,
                        weight=ex_data.weight,
                        rpe_target=ex_data.rpe_target,
                        sets_json=[s.model_dump() for s in ex_data.sets_json] if ex_data.sets_json else None,
                        notes=ex_data.notes,
                    )
                    session.add(plan_ex)

    await session.commit()

    result = await session.execute(_plan_query(plan_id=plan.id))
    return result.scalar_one()


@router.put("/{plan_id}/activate", response_model=PlanResponse)
async def activate_plan(plan_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Deactivate all other plans for this user
    await session.execute(
        update(Plan)
        .where(Plan.user_id == plan.user_id, Plan.id != plan_id)
        .values(status="inactive")
    )
    plan.status = "active"

    # Create or update cycle tracker
    tracker_result = await session.execute(
        select(CycleTracker).where(CycleTracker.user_id == plan.user_id)
    )
    tracker = tracker_result.scalar_one_or_none()
    if tracker:
        tracker.plan_id = plan.id
        tracker.next_day_number = 1
        tracker.last_completed_at = None
    else:
        tracker = CycleTracker(user_id=plan.user_id, plan_id=plan.id, next_day_number=1)
        session.add(tracker)

    await session.commit()

    result = await session.execute(_plan_query(plan_id=plan.id))
    return result.scalar_one()


@router.put("/{plan_id}/archive", response_model=PlanResponse)
async def archive_plan(plan_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    plan.status = "inactive"
    await session.commit()

    result = await session.execute(_plan_query(plan_id=plan.id))
    return result.scalar_one()


@router.delete("/{plan_id}", status_code=204)
async def delete_plan(plan_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    await session.delete(plan)
    await session.commit()
