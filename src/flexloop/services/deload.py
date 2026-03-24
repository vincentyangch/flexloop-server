from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from flexloop.models.workout import WorkoutSession, WorkoutSet, SessionFeedback


async def detect_fatigue(user_id: int, db: AsyncSession, lookback_days: int = 14) -> dict:
    """Analyze recent training data for fatigue signals.

    Returns a fatigue report with signals and a deload recommendation.
    """
    cutoff = datetime.now() - timedelta(days=lookback_days)

    result = await db.execute(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == user_id,
            WorkoutSession.started_at >= cutoff,
            WorkoutSession.completed_at.isnot(None),
        )
        .options(
            selectinload(WorkoutSession.sets),
            selectinload(WorkoutSession.feedback),
        )
        .order_by(WorkoutSession.started_at)
    )
    sessions = result.scalars().all()

    if len(sessions) < 3:
        return {
            "deload_recommended": False,
            "confidence": "low",
            "reason": "Not enough recent data (need at least 3 sessions in the last 2 weeks).",
            "signals": [],
            "session_count": len(sessions),
        }

    signals = []
    signal_count = 0

    # Signal 1: RPE trending upward while weight is flat
    rpe_trend = _check_rpe_trend(sessions)
    if rpe_trend:
        signals.append(rpe_trend)
        signal_count += 1

    # Signal 2: Rep counts declining at same weight
    rep_decline = _check_rep_decline(sessions)
    if rep_decline:
        signals.append(rep_decline)
        signal_count += 1

    # Signal 3: Session feedback scores dropping
    feedback_decline = _check_feedback_decline(sessions)
    if feedback_decline:
        signals.append(feedback_decline)
        signal_count += 1

    # Signal 4: Missed sessions (gaps > 3 days between expected sessions)
    missed = _check_missed_sessions(sessions)
    if missed:
        signals.append(missed)
        signal_count += 1

    # Determine recommendation
    if signal_count >= 3:
        deload = True
        confidence = "high"
        reason = f"{signal_count} fatigue signals detected. A deload week is strongly recommended."
    elif signal_count == 2:
        deload = True
        confidence = "medium"
        reason = f"{signal_count} fatigue signals detected. Consider a deload this week."
    elif signal_count == 1:
        deload = False
        confidence = "low"
        reason = "Minor fatigue signal detected. Monitor closely but no deload needed yet."
    else:
        deload = False
        confidence = "low"
        reason = "No significant fatigue signals. Training appears sustainable."

    return {
        "deload_recommended": deload,
        "confidence": confidence,
        "reason": reason,
        "signals": signals,
        "session_count": len(sessions),
    }


def generate_deload_week(plan_exercises: list[dict], reduction_pct: float = 0.4) -> list[dict]:
    """Generate a deload version of a training week.

    Reduces volume by removing sets and reducing weight.
    """
    deload_exercises = []
    for ex in plan_exercises:
        deload_ex = dict(ex)
        original_sets = ex.get("sets", 3)
        original_weight = ex.get("weight")

        # Reduce sets (roughly half, minimum 2)
        deload_ex["sets"] = max(2, original_sets // 2)

        # Reduce weight by reduction percentage
        if original_weight and original_weight > 0:
            deload_ex["weight"] = round(original_weight * (1 - reduction_pct), 1)

        # Keep reps the same (practice movement pattern)
        deload_ex["notes"] = f"DELOAD: {deload_ex['sets']}x{ex.get('reps', 8)} at reduced weight. Focus on technique."

        deload_exercises.append(deload_ex)

    return deload_exercises


def _check_rpe_trend(sessions: list) -> dict | None:
    """Check if RPE is trending upward across sessions."""
    session_rpes = []
    for s in sessions:
        working_sets = [st for st in (s.sets or []) if st.set_type == "working" and st.rpe]
        if working_sets:
            avg_rpe = sum(st.rpe for st in working_sets) / len(working_sets)
            session_rpes.append(avg_rpe)

    if len(session_rpes) < 3:
        return None

    # Check if last 3 sessions show rising RPE
    recent = session_rpes[-3:]
    if recent[-1] > recent[0] and recent[-1] >= 8.5:
        return {
            "signal": "rising_rpe",
            "description": f"Average RPE increased from {recent[0]:.1f} to {recent[-1]:.1f} over last 3 sessions.",
            "severity": "high" if recent[-1] >= 9.0 else "medium",
        }
    return None


def _check_rep_decline(sessions: list) -> dict | None:
    """Check if reps at same weight are declining."""
    # Group by exercise, track reps at same weight
    exercise_data: dict[int, list[tuple[float, int]]] = {}
    for s in sessions:
        for st in (s.sets or []):
            if st.set_type == "working" and st.weight and st.reps:
                if st.exercise_id not in exercise_data:
                    exercise_data[st.exercise_id] = []
                exercise_data[st.exercise_id].append((st.weight, st.reps))

    for ex_id, data in exercise_data.items():
        if len(data) < 4:
            continue
        # Check if reps at the same weight are dropping
        recent = data[-4:]
        weights = [d[0] for d in recent]
        reps = [d[1] for d in recent]

        # If weight is stable but reps dropping
        if max(weights) - min(weights) <= 2.5 and reps[-1] < reps[0]:
            return {
                "signal": "rep_decline",
                "description": f"Reps declining at similar weight ({weights[-1]}kg): {reps[0]} → {reps[-1]} reps.",
                "severity": "medium",
            }
    return None


def _check_feedback_decline(sessions: list) -> dict | None:
    """Check if session feedback scores are dropping."""
    feedbacks = []
    for s in sessions:
        if s.feedback:
            scores = []
            if s.feedback.energy_level: scores.append(s.feedback.energy_level)
            if s.feedback.sleep_quality: scores.append(s.feedback.sleep_quality)
            if scores:
                feedbacks.append(sum(scores) / len(scores))

    if len(feedbacks) < 3:
        return None

    recent = feedbacks[-3:]
    if recent[-1] < recent[0] and recent[-1] <= 2.5:
        return {
            "signal": "low_recovery",
            "description": f"Recovery scores dropped from {recent[0]:.1f} to {recent[-1]:.1f}. Sleep and energy are declining.",
            "severity": "high" if recent[-1] <= 2.0 else "medium",
        }
    return None


def _check_missed_sessions(sessions: list) -> dict | None:
    """Check for gaps suggesting missed sessions."""
    if len(sessions) < 2:
        return None

    gaps = []
    for i in range(1, len(sessions)):
        gap_days = (sessions[i].started_at - sessions[i - 1].started_at).days
        if gap_days > 3:
            gaps.append(gap_days)

    if len(gaps) >= 2:
        return {
            "signal": "missed_sessions",
            "description": f"Multiple gaps of {', '.join(str(g) for g in gaps)} days detected. Consistency is dropping.",
            "severity": "low",
        }
    return None
