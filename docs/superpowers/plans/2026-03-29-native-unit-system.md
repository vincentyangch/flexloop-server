# Native Unit System Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store and display all weight/height values in the user's chosen unit (kg or lbs) with zero conversion anywhere in the system.

**Architecture:** Add `weight_unit` field to User model. All weight values stored in the user's native unit. Server services, AI prompts, and iOS views all operate directly on the stored value. iOS conversion layer (`UnitHelper.swift`) is gutted — values pass through as-is. iOS `WeightUnit` enum changes raw values to `"kg"`/`"lbs"` to match server values directly.

**Tech Stack:** Python/FastAPI/SQLAlchemy (server), Swift/SwiftUI/SwiftData (iOS), Alembic (migrations)

**Unit propagation pattern (iOS):** The user's `weightUnit` string (`"kg"` or `"lbs"`) is stored in `CachedUser.weightUnit`. Views obtain the unit via a helper on `CachedUser`:
```swift
extension CachedUser {
    var unit: WeightUnit { WeightUnit(rawValue: weightUnit) ?? .kg }
}
```
Parent views (HomeView, GuidedWorkoutView) read this once and pass `unitSymbol: String` down to child views. The `WeightUnit` enum uses `"kg"` / `"lbs"` as raw values, matching the server field exactly — no mapping needed.

**SwiftData migration note:** Since we deleted all simulator data, the renamed SwiftData fields (`heightCm` → `height`, `weightKg` → `weight`, new `weightUnit`/`heightUnit`) will just create a fresh schema. No SwiftData versioned migration needed for this change. On any existing dev device, delete the app first.

---

## Chunk 1: Server Schema & Model Changes

### Task 1: Add `weight_unit` to User model and rename `weight_kg`/`height_cm`

**Files:**
- Modify: `flexloop-server/src/flexloop/models/user.py`
- Modify: `flexloop-server/src/flexloop/schemas/user.py`
- Modify: `flexloop-server/tests/test_models_core.py`

- [ ] **Step 1: Update User model**

In `flexloop-server/src/flexloop/models/user.py`, rename `height_cm` → `height`, `weight_kg` → `weight`, add `weight_unit` and `height_unit`:

```python
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    gender: Mapped[str] = mapped_column(String(20), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    weight_unit: Mapped[str] = mapped_column(String(10), nullable=False, default="kg")
    height_unit: Mapped[str] = mapped_column(String(10), nullable=False, default="cm")
    experience_level: Mapped[str] = mapped_column(String(20), nullable=False)
    goals: Mapped[str] = mapped_column(String(500), nullable=False)
    available_equipment: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 2: Update User schemas**

In `flexloop-server/src/flexloop/schemas/user.py`:

```python
from datetime import datetime

from pydantic import BaseModel


class UserCreate(BaseModel):
    name: str
    gender: str
    age: int
    height: float
    weight: float
    weight_unit: str = "kg"
    height_unit: str = "cm"
    experience_level: str
    goals: str
    available_equipment: list[str] = []


class UserUpdate(BaseModel):
    name: str | None = None
    gender: str | None = None
    age: int | None = None
    height: float | None = None
    weight: float | None = None
    experience_level: str | None = None
    goals: str | None = None
    available_equipment: list[str] | None = None


class UserResponse(BaseModel):
    id: int
    name: str
    gender: str
    age: int
    height: float
    weight: float
    weight_unit: str
    height_unit: str
    experience_level: str
    goals: str
    available_equipment: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: Update test_models_core.py**

Update the user test to use new field names and add a test for lbs user:

```python
@pytest.mark.asyncio
async def test_create_user(db_session):
    user = User(
        name="Test User",
        gender="male",
        age=28,
        height=180.0,
        weight=82.0,
        weight_unit="kg",
        height_unit="cm",
        experience_level="intermediate",
        goals="hypertrophy",
        available_equipment=["barbell", "dumbbells", "pull_up_bar"],
    )
    db_session.add(user)
    await db_session.commit()

    result = await db_session.execute(select(User).where(User.name == "Test User"))
    saved = result.scalar_one()
    assert saved.name == "Test User"
    assert saved.weight_unit == "kg"
    assert saved.height_unit == "cm"
    assert saved.weight == 82.0
    assert saved.height == 180.0
    assert "barbell" in saved.available_equipment


@pytest.mark.asyncio
async def test_create_user_imperial(db_session):
    user = User(
        name="US User",
        gender="male",
        age=25,
        height=71.0,
        weight=180.0,
        weight_unit="lbs",
        height_unit="in",
        experience_level="beginner",
        goals="strength",
    )
    db_session.add(user)
    await db_session.commit()

    result = await db_session.execute(select(User).where(User.name == "US User"))
    saved = result.scalar_one()
    assert saved.weight_unit == "lbs"
    assert saved.height_unit == "in"
    assert saved.weight == 180.0
```

- [ ] **Step 4: Run tests**

Run: `cd flexloop-server && python -m pytest tests/test_models_core.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add flexloop-server/src/flexloop/models/user.py flexloop-server/src/flexloop/schemas/user.py flexloop-server/tests/test_models_core.py
git commit -m "feat: add weight_unit/height_unit to User, rename weight_kg/height_cm"
```

---

### Task 2: Rename `value_cm` in Measurement model

**Files:**
- Modify: `flexloop-server/src/flexloop/models/measurement.py`
- Modify: `flexloop-server/src/flexloop/schemas/measurement.py`
- Modify: `flexloop-server/tests/test_models_misc.py` (update Measurement test)

- [ ] **Step 1: Update Measurement model**

In `flexloop-server/src/flexloop/models/measurement.py`, rename `value_cm` → `value`:

```python
from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from flexloop.db.base import Base


class Measurement(Base):
    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 2: Update Measurement schemas**

In `flexloop-server/src/flexloop/schemas/measurement.py`, rename `value_cm` → `value`:

```python
from datetime import date

from pydantic import BaseModel


class MeasurementCreate(BaseModel):
    user_id: int
    date: date
    type: str
    value: float
    notes: str | None = None


class MeasurementResponse(BaseModel):
    id: int
    user_id: int
    date: date
    type: str
    value: float
    notes: str | None = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: Update test_models_misc.py Measurement test**

Find the Measurement test and change `value_cm=` to `value=`:

```python
measurement = Measurement(
    user_id=user.id, date=date.today(), type="waist", value=85.0,
    notes="Morning measurement",
)
```

And assertions:
```python
assert saved.value == 85.0
```

- [ ] **Step 4: Run tests**

Run: `cd flexloop-server && python -m pytest tests/test_models_misc.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add flexloop-server/src/flexloop/models/measurement.py flexloop-server/src/flexloop/schemas/measurement.py flexloop-server/tests/test_models_misc.py
git commit -m "feat: rename value_cm to value in Measurement model"
```

---

### Task 3: Rename `target_weight_kg` in plan schema

**Files:**
- Modify: `flexloop-server/src/flexloop/schemas/plan.py:66-70`

- [ ] **Step 1: Update SetTarget schema**

In `flexloop-server/src/flexloop/schemas/plan.py`, rename `target_weight_kg` → `target_weight`:

```python
class SetTarget(BaseModel):
    set_number: int
    target_weight: float | None = None
    target_reps: int = 10
    target_rpe: float | None = None
```

- [ ] **Step 2: Run plan tests**

Run: `cd flexloop-server && python -m pytest tests/test_plans.py -v`
Expected: PASS (check if `target_weight_kg` is referenced in test payloads — if so, update them too)

- [ ] **Step 3: Commit**

```bash
git add flexloop-server/src/flexloop/schemas/plan.py
git commit -m "feat: rename target_weight_kg to target_weight in SetTarget schema"
```

---

## Chunk 2: Server Services — Unit-Aware Logic

### Task 4: Add unit config and make warmup service unit-aware

**Files:**
- Create: `flexloop-server/src/flexloop/services/unit_config.py`
- Modify: `flexloop-server/src/flexloop/services/warmup.py`
- Modify: `flexloop-server/tests/test_warmup.py`

- [ ] **Step 1: Create unit config lookup**

Create `flexloop-server/src/flexloop/services/unit_config.py`:

```python
UNIT_CONFIG = {
    "kg": {
        "bar_weight": 20.0,
        "barbell_increment": 5.0,
        "dumbbell_increment": 2.5,
        "default_increment": 2.5,
        "min_meaningful_weight": 20.0,
        "same_weight_tolerance": 2.5,
        "label": "kg",
    },
    "lbs": {
        "bar_weight": 45.0,
        "barbell_increment": 10.0,
        "dumbbell_increment": 5.0,
        "default_increment": 5.0,
        "min_meaningful_weight": 45.0,
        "same_weight_tolerance": 5.0,
        "label": "lbs",
    },
}


def get_unit_config(weight_unit: str) -> dict:
    return UNIT_CONFIG.get(weight_unit, UNIT_CONFIG["kg"])
```

- [ ] **Step 2: Update warmup service**

Replace `flexloop-server/src/flexloop/services/warmup.py`:

```python
from flexloop.services.unit_config import get_unit_config


def generate_warmup_sets(
    working_weight: float,
    exercise_category: str = "compound",
    equipment: str = "barbell",
    weight_unit: str = "kg",
) -> list[dict]:
    """Generate warm-up sets ramping up to the working weight.

    Only generates warm-ups for compound exercises with meaningful weight.
    All weights are in the user's preferred unit (kg or lbs).
    Returns warm-up weights rounded to equipment-appropriate increments.
    """
    config = get_unit_config(weight_unit)

    if exercise_category != "compound" or working_weight <= config["min_meaningful_weight"]:
        return []

    bar_weight, increment = _equipment_config(equipment, weight_unit)
    sets = []

    steps = [
        (0.0, 10),   # Bar only
        (0.4, 8),    # 40%
        (0.6, 5),    # 60%
        (0.8, 3),    # 80%
    ]

    for pct, reps in steps:
        if pct > 0:
            weight = round_to_nearest(working_weight * pct, increment)
            weight = max(weight, bar_weight if bar_weight > 0 else increment)
        else:
            if bar_weight <= 0:
                continue
            weight = bar_weight

        if pct > 0 and bar_weight > 0 and weight <= bar_weight:
            continue

        if sets and weight <= sets[-1]["weight"]:
            continue

        if working_weight - weight < increment and pct < 0.9:
            continue

        sets.append({
            "weight": weight,
            "reps": reps,
            "percentage": int(pct * 100) if pct > 0 else 0,
            "rest_sec": 30 if pct < 0.6 else 45,
        })

    return sets


def _equipment_config(equipment: str, weight_unit: str = "kg") -> tuple[float, float]:
    """Return (bar_weight, plate_increment) for equipment type in user's unit."""
    config = get_unit_config(weight_unit)
    equip = equipment.lower()
    if equip == "barbell":
        return config["bar_weight"], config["barbell_increment"]
    elif equip in ("dumbbell", "dumbbells"):
        return 0.0, config["dumbbell_increment"]
    else:
        return 0.0, config["default_increment"]


def round_to_nearest(value: float, increment: float) -> float:
    """Round to nearest weight increment."""
    return round(value / increment) * increment
```

- [ ] **Step 3: Update warmup tests — add lbs tests**

Add to `flexloop-server/tests/test_warmup.py`:

```python
def test_warmup_for_225lbs_compound():
    sets = generate_warmup_sets(225.0, "compound", weight_unit="lbs")
    assert len(sets) >= 2
    assert sets[0]["weight"] == 45.0  # bar weight in lbs
    assert sets[-1]["weight"] <= 180.0
    for i in range(1, len(sets)):
        assert sets[i]["weight"] > sets[i - 1]["weight"]


def test_warmup_lbs_weights_rounded_to_10():
    sets = generate_warmup_sets(225.0, "compound", weight_unit="lbs")
    for s in sets:
        assert s["weight"] % 10 == 0 or s["weight"] == 45.0


def test_no_warmup_for_light_weight_lbs():
    sets = generate_warmup_sets(35.0, "compound", weight_unit="lbs")
    assert sets == []
```

Also update existing tests to explicitly pass `weight_unit="kg"` (they'll still work without it due to the default, but it's good to be explicit).

- [ ] **Step 4: Run warmup tests**

Run: `cd flexloop-server && python -m pytest tests/test_warmup.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add flexloop-server/src/flexloop/services/unit_config.py flexloop-server/src/flexloop/services/warmup.py flexloop-server/tests/test_warmup.py
git commit -m "feat: make warmup service unit-aware with config lookup"
```

---

### Task 5: Make PR detection service unit-aware

**Files:**
- Modify: `flexloop-server/src/flexloop/services/pr_detection.py`
- Modify: `flexloop-server/tests/test_pr_detection.py`

- [ ] **Step 1: Update pr_detection.py**

Add `weight_unit` parameter to `check_prs` and use it in detail strings. Change lines 66, 92, 128 from hardcoded "kg" to `{weight_unit}`:

```python
async def check_prs(
    user_id: int,
    exercise_id: int,
    weight: float | None,
    reps: int | None,
    session_id: int | None,
    db: AsyncSession,
    weight_unit: str = "kg",
) -> list[dict]:
```

Update detail strings:
- Line 66: `f"{round(weight, 1)}{weight_unit} x {reps} reps"`
- Line 92: `f"{reps} reps at {round(weight, 1)}{weight_unit}"`
- Line 128: `f"{round(weight, 1)}{weight_unit} x {reps} = {round(volume, 1)}{weight_unit} volume"`

- [ ] **Step 2: Update PR detection tests**

Add a test with lbs:

```python
@pytest.mark.asyncio
async def test_pr_detail_uses_weight_unit(db_session):
    user = User(name="US User", gender="male", age=25, height=71.0, weight=180.0,
                weight_unit="lbs", height_unit="in", experience_level="beginner", goals="strength")
    exercise = Exercise(name="Bench Press", muscle_group="chest", equipment="barbell",
                        category="compound", difficulty="intermediate")
    db_session.add_all([user, exercise])
    await db_session.commit()

    new_prs = await check_prs(user.id, exercise.id, 200.0, 5, None, db_session, weight_unit="lbs")
    assert any("lbs" in pr["detail"] for pr in new_prs)
    assert not any("kg" in pr["detail"] for pr in new_prs)
```

- [ ] **Step 3: Run PR tests**

Run: `cd flexloop-server && python -m pytest tests/test_pr_detection.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add flexloop-server/src/flexloop/services/pr_detection.py flexloop-server/tests/test_pr_detection.py
git commit -m "feat: make PR detection service unit-aware"
```

---

### Task 6: Make deload service unit-aware

**Files:**
- Modify: `flexloop-server/src/flexloop/services/deload.py:164,167`

- [ ] **Step 1: Update `_check_rep_decline`**

The function needs access to `weight_unit`. Change the signature of `detect_fatigue` and internal helpers to pass `weight_unit` through:

In `detect_fatigue`, add `weight_unit: str = "kg"` parameter.
Pass it to `_check_rep_decline(sessions, weight_unit)`.

In `_check_rep_decline`, add `weight_unit: str = "kg"` parameter:

```python
def _check_rep_decline(sessions: list, weight_unit: str = "kg") -> dict | None:
```

Update line 164:
```python
from flexloop.services.unit_config import get_unit_config
# inside _check_rep_decline:
config = get_unit_config(weight_unit)
if max(weights) - min(weights) <= config["same_weight_tolerance"] and reps[-1] < reps[0]:
```

Update line 167:
```python
"description": f"Reps declining at similar weight ({weights[-1]}{weight_unit}): {reps[0]} → {reps[-1]} reps.",
```

- [ ] **Step 2: Run full test suite to check nothing broke**

Run: `cd flexloop-server && python -m pytest -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add flexloop-server/src/flexloop/services/deload.py
git commit -m "feat: make deload service unit-aware"
```

---

### Task 7: Update export service

**Files:**
- Modify: `flexloop-server/src/flexloop/services/export.py`
- Modify: `flexloop-server/tests/test_api_export.py`

- [ ] **Step 1: Update export.py**

Change the user export dict (line 33) from `height_cm`/`weight_kg` to `height`/`weight`, and add `weight_unit`/`height_unit`:

```python
"user": {
    "name": user.name, "gender": user.gender, "age": user.age,
    "height": user.height, "weight": user.weight,
    "weight_unit": user.weight_unit, "height_unit": user.height_unit,
    "experience_level": user.experience_level, "goals": user.goals,
    "available_equipment": user.available_equipment,
},
```

Change measurement export (line 58) from `value_cm` to `value`:

```python
"measurements": [
    {
        "date": m.date.isoformat(), "type": m.type,
        "value": m.value, "notes": m.notes,
    }
    for m in measurements
],
```

- [ ] **Step 2: Update export tests**

In `test_api_export.py`, update the seed_data fixture's User creation to use new field names, and update assertions to check for `weight` and `weight_unit` instead of `weight_kg`.

- [ ] **Step 3: Run export tests**

Run: `cd flexloop-server && python -m pytest tests/test_api_export.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add flexloop-server/src/flexloop/services/export.py flexloop-server/tests/test_api_export.py
git commit -m "feat: update export service for native units"
```

---

## Chunk 3: Server AI Router & Prompts

### Task 8: Update AI router — unit-aware formatting

**Files:**
- Modify: `flexloop-server/src/flexloop/routers/ai.py`

- [ ] **Step 1: Update `format_user_profile`**

```python
def format_user_profile(user: User) -> str:
    return (
        f"Name: {user.name}\n"
        f"Gender: {user.gender}, Age: {user.age}\n"
        f"Height: {user.height}{user.height_unit}, Weight: {user.weight}{user.weight_unit}\n"
        f"Experience: {user.experience_level}\n"
        f"Goals: {user.goals}\n"
        f"Available equipment: {', '.join(user.available_equipment)}\n"
        f"Weight unit: {user.weight_unit}"
    )
```

- [ ] **Step 2: Update chat context formatting (line 339)**

Change:
```python
f"{s.weight}kg x {s.reps}" + (f" RPE {s.rpe}" if s.rpe else "")
```
To:
```python
f"{s.weight}{user.weight_unit} x {s.reps}" + (f" RPE {s.rpe}" if s.rpe else "")
```

- [ ] **Step 3: Update PR context formatting (line 368)**

Change:
```python
pr_lines.append(f"- {name}: est. 1RM {pr.value:.1f}kg")
```
To:
```python
pr_lines.append(f"- {name}: est. 1RM {pr.value:.1f}{user.weight_unit}")
```

- [ ] **Step 4: Update review context formatting (line 434)**

Change:
```python
if s.weight: parts.append(f"{s.weight}kg")
```
To:
```python
if s.weight: parts.append(f"{s.weight}{user.weight_unit}")
```

- [ ] **Step 5: Run AI tests**

Run: `cd flexloop-server && python -m pytest tests/test_api_ai.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add flexloop-server/src/flexloop/routers/ai.py
git commit -m "feat: use user's weight_unit in AI context formatting"
```

---

### Task 9: Update AI prompts for unit awareness

**Files:**
- Modify: `flexloop-server/prompts/plan_generation/v1.md`
- Modify: `flexloop-server/prompts/chat/v1.md`
- Modify: `flexloop-server/prompts/block_review/v1.md`
- Modify: `flexloop-server/prompts/session_review/v1.md`

- [ ] **Step 1: Update plan_generation/v1.md**

Add unit instruction after the `## Instructions` section:

```
## Unit System
The user's weight unit is included in their profile. ALL weights in the output MUST use the same unit as the user (kg or lbs). Use round numbers that are practical for the user's unit system (e.g., 5lb increments for barbells, 2.5kg increments for kg users).
```

Change the JSON example `target_weight_kg` → `target_weight`:

```json
"sets_json": [
    {"set_number": 1, "target_weight": 60, "target_reps": 8, "target_rpe": 7},
    {"set_number": 2, "target_weight": 60, "target_reps": 8, "target_rpe": 7.5},
    {"set_number": 3, "target_weight": 60, "target_reps": 8, "target_rpe": 8},
    {"set_number": 4, "target_weight": 60, "target_reps": 8, "target_rpe": 8.5}
]
```

Update the note at the bottom:
```
- Each exercise MUST include `sets_json` with per-set targets using the user's weight unit
```

- [ ] **Step 2: Update chat/v1.md**

Add after the `## Instructions` line:

```
The user's weight unit is specified in their profile. Always use that unit (kg or lbs) when discussing weights. Use practical, round numbers for that unit system.
```

- [ ] **Step 3: Update block_review/v1.md**

Add after `## Instructions`:

```
Use the same weight unit as the user's profile (kg or lbs) in all recommendations.
```

- [ ] **Step 4: Update session_review/v1.md**

Add after `## Instructions`:

```
Use the same weight unit as shown in the session data.
```

- [ ] **Step 5: Run prompt tests**

Run: `cd flexloop-server && python -m pytest tests/test_prompts.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add flexloop-server/prompts/
git commit -m "feat: add unit awareness instructions to all AI prompts"
```

---

### Task 10: Handle AI plan output field name for `target_weight`

**Files:**
- Modify: `flexloop-server/src/flexloop/routers/ai.py` (plan generation section around line 170-180)

Note: `ai/validators.py` does not reference `target_weight_kg` — no changes needed there.

- [ ] **Step 1: Update plan generation parser for backwards compatibility**

In `ai.py`, the plan generation handler stores `sets_json` as raw JSON from AI output. The AI prompt (updated in Task 9) now uses `target_weight`, but older cached responses might use `target_weight_kg`. Add a normalizer when reading AI output:

In the plan generation handler, after parsing `ex_data`, normalize `sets_json` entries:

```python
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
```

- [ ] **Step 2: Run full server test suite**

Run: `cd flexloop-server && python -m pytest -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add flexloop-server/src/flexloop/routers/ai.py
git commit -m "feat: normalize AI plan output to use target_weight field"
```

---

## Chunk 4: Server Routers & Remaining Backend

### Task 11: Update remaining routers that reference old field names

**Files:**
- Modify: `flexloop-server/src/flexloop/routers/measurements.py` (if references `value_cm`)
- Modify: `flexloop-server/src/flexloop/routers/progress.py` (line 121: `m.value_cm`)
- Modify: `flexloop-server/src/flexloop/routers/prs.py` (if references kg)
- Modify: `flexloop-server/src/flexloop/routers/warmup.py` (pass weight_unit to service)
- Modify: `flexloop-server/src/flexloop/routers/deload.py` (pass weight_unit to service)

- [ ] **Step 1: Update progress router**

In `routers/progress.py`, change `m.value_cm` → `m.value`.

- [ ] **Step 2: Update warmup router**

The warmup endpoint needs to look up the user's `weight_unit` and pass it to `generate_warmup_sets`. Add `user_id` parameter to the endpoint and query for user's weight_unit, then pass `weight_unit=user.weight_unit` to the service call.

- [ ] **Step 3: Update deload router**

Pass `weight_unit` from user to `detect_fatigue()`.

- [ ] **Step 4: Update PR check router**

In `routers/prs.py` or wherever `check_prs` is called from an endpoint, pass `weight_unit` from the user.

- [ ] **Step 5: Update measurements router**

Check `routers/measurements.py` for any reference to `value_cm` and update to `value`.

- [ ] **Step 6: Run full test suite**

Run: `cd flexloop-server && python -m pytest -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add flexloop-server/src/flexloop/routers/
git commit -m "feat: update all routers for native unit system"
```

---

### Task 12: Update remaining test files for field renames

**Files:**
- Modify: `flexloop-server/tests/test_api_ai.py` (user fixture uses `height_cm`, `weight_kg`)
- Modify: `flexloop-server/tests/test_plans.py` (`target_weight_kg` in payloads)
- Modify: `flexloop-server/tests/test_models_plan.py` (user fixture)
- Modify: `flexloop-server/tests/test_api_workouts.py` (user fixture)
- Modify: `flexloop-server/tests/test_api_measurements.py` (`value_cm` in payloads)
- Modify: `flexloop-server/tests/test_cycle.py` (user fixture)
- Modify: `flexloop-server/tests/test_api_sync.py` (user fixture uses `height_cm`, `weight_kg`)
- Modify: `flexloop-server/tests/test_api_export.py` (if not already fixed in Task 7)
- Modify: `flexloop-server/tests/test_pr_detection.py` (if not already fixed in Task 5)
- Modify: `flexloop-server/tests/test_eval_scoring.py` (if references old field names)

Note: `test_backup.py` does NOT reference old field names — skip it.

- [ ] **Step 1: Find and fix all test files**

Search all test files for `weight_kg`, `height_cm`, `value_cm`, `target_weight_kg` and replace:
- `weight_kg=` → `weight=` (in User creation)
- `height_cm=` → `height=` (in User creation)
- `value_cm=` → `value=` (in Measurement creation)
- `target_weight_kg` → `target_weight` (in plan payloads)
- Add `weight_unit="kg", height_unit="cm"` to User creation where needed

- [ ] **Step 2: Run full test suite**

Run: `cd flexloop-server && python -m pytest -v`
Expected: ALL PASS — this is the server-side milestone

- [ ] **Step 3: Commit**

```bash
git add flexloop-server/tests/
git commit -m "fix: update all test files for native unit field names"
```

---

## Chunk 5: iOS API Models & Data Layer

### Task 13: Update iOS API models

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Services/APIModels.swift`

- [ ] **Step 1: Update APIUser**

```swift
struct APIUser: Codable, Sendable {
    let id: Int
    let name: String
    let gender: String
    let age: Int
    let height: Double
    let weight: Double
    let weightUnit: String
    let heightUnit: String
    let experienceLevel: String
    let goals: String
    let availableEquipment: [String]
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, name, gender, age, goals, height, weight
        case weightUnit = "weight_unit"
        case heightUnit = "height_unit"
        case experienceLevel = "experience_level"
        case availableEquipment = "available_equipment"
        case createdAt = "created_at"
    }
}
```

- [ ] **Step 2: Update APIUserCreate**

```swift
struct APIUserCreate: Codable, Sendable {
    let name: String
    let gender: String
    let age: Int
    let height: Double
    let weight: Double
    let weightUnit: String
    let heightUnit: String
    let experienceLevel: String
    let goals: String
    let availableEquipment: [String]

    enum CodingKeys: String, CodingKey {
        case name, gender, age, goals, height, weight
        case weightUnit = "weight_unit"
        case heightUnit = "height_unit"
        case experienceLevel = "experience_level"
        case availableEquipment = "available_equipment"
    }
}
```

- [ ] **Step 3: Update APISetTarget**

Rename `targetWeightKg` → `targetWeight`:

```swift
struct APISetTarget: Codable, Sendable {
    var setNumber: Int
    var targetWeight: Double?
    var targetReps: Int
    var targetRpe: Double?

    enum CodingKeys: String, CodingKey {
        case setNumber = "set_number"
        case targetWeight = "target_weight"
        case targetReps = "target_reps"
        case targetRpe = "target_rpe"
    }
}
```

- [ ] **Step 4: Commit**

```bash
git add flexloop-ios/
git commit -m "feat: update iOS API models for native unit system"
```

---

### Task 14: Update CachedUser SwiftData model

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Models/CachedUser.swift`

- [ ] **Step 1: Rename fields and add unit fields**

```swift
import Foundation
import SwiftData

@Model
final class CachedUser {
    @Attribute(.unique) var serverId: Int
    var name: String
    var gender: String
    var age: Int
    var height: Double
    var weight: Double
    var weightUnit: String
    var heightUnit: String
    var experienceLevel: String
    var goals: String
    var availableEquipment: [String]
    var lastSyncedAt: Date?

    init(serverId: Int, name: String, gender: String, age: Int,
         height: Double, weight: Double, weightUnit: String, heightUnit: String,
         experienceLevel: String, goals: String, availableEquipment: [String] = []) {
        self.serverId = serverId
        self.name = name
        self.gender = gender
        self.age = age
        self.height = height
        self.weight = weight
        self.weightUnit = weightUnit
        self.heightUnit = heightUnit
        self.experienceLevel = experienceLevel
        self.goals = goals
        self.availableEquipment = availableEquipment
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add flexloop-ios/FlexLoop/FlexLoop/Models/CachedUser.swift
git commit -m "feat: update CachedUser for native units"
```

---

### Task 15: Update WorkoutSyncModels — rename `weightKg` fields

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Services/WorkoutSyncModels.swift`
- Modify: `flexloop-ios/FlexLoop/FlexLoopWatch Watch App/WorkoutSyncModels.swift`

- [ ] **Step 1: Update iPhone WorkoutSyncModels.swift**

Rename all `weightKg` → `weight` in the structs:

- `SyncSetTarget.weightKg` → `SyncSetTarget.weight`
- `SyncCompletedSet.weightKg` → `SyncCompletedSet.weight`
- `WatchCompleteSetAction.weightKg` → `WatchCompleteSetAction.weight`

- [ ] **Step 2: Update Watch WorkoutSyncModels.swift**

Same renames — the Watch copy should be identical to the iPhone copy.

- [ ] **Step 3: Commit**

```bash
git add flexloop-ios/FlexLoop/FlexLoop/Services/WorkoutSyncModels.swift flexloop-ios/FlexLoop/FlexLoopWatch\ Watch\ App/WorkoutSyncModels.swift
git commit -m "feat: rename weightKg to weight in sync models"
```

---

## Chunk 6: iOS ViewModel & Conversion Layer Changes

### Task 16: Gut UnitHelper.swift — remove conversion functions

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Services/UnitHelper.swift`

- [ ] **Step 1: Simplify UnitHelper**

Remove `fromKg`, `toKg`, `fromCm`, `toCm`, `fromKgRounded`, `formatWeight`, `formatWeightRounded`. Keep only: `symbol`, `heightSymbol`, `increment`, equipment increments, and `roundToNearest` (for rounding to practical plate increments — still useful).

Remove `WeightUnit.current` since the unit is now stored on the user profile, not in UserDefaults.

```swift
import Foundation

/// WeightUnit raw values match the server's weight_unit field exactly ("kg" or "lbs").
/// This eliminates any mapping between iOS enum values and server strings.
enum WeightUnit: String, Codable {
    case kg
    case lbs

    var symbol: String { rawValue }

    var heightSymbol: String {
        switch self {
        case .kg: return "cm"
        case .lbs: return "in"
        }
    }

    /// Weight increment for digital crown / steppers
    var increment: Double {
        switch self {
        case .kg: return 2.5
        case .lbs: return 5.0
        }
    }

    var barbellIncrement: Double {
        switch self {
        case .kg: return 5.0
        case .lbs: return 10.0
        }
    }

    var barbellMinimum: Double {
        switch self {
        case .kg: return 20.0
        case .lbs: return 45.0
        }
    }

    var dumbbellIncrement: Double {
        switch self {
        case .kg: return 2.5
        case .lbs: return 5.0
        }
    }

    /// Round a value to the nearest valid weight for the given equipment
    func roundToNearest(_ value: Double, equipment: String) -> Double {
        let inc: Double
        let minimum: Double
        switch equipment.lowercased() {
        case "barbell":
            inc = barbellIncrement
            minimum = barbellMinimum
        case "dumbbell", "dumbbells":
            inc = dumbbellIncrement
            minimum = inc
        default:
            inc = increment
            minimum = inc
        }
        let rounded = (value / inc).rounded() * inc
        return max(rounded, minimum)
    }

    /// Format a weight value for display
    func format(_ value: Double) -> String {
        "\(String(format: "%.1f", value)) \(symbol)"
    }
}
```

Also add a convenience on `CachedUser`:

```swift
extension CachedUser {
    var unit: WeightUnit { WeightUnit(rawValue: weightUnit) ?? .kg }
}
```

- [ ] **Step 2: Commit**

```bash
git add flexloop-ios/FlexLoop/FlexLoop/Services/UnitHelper.swift
git commit -m "feat: gut UnitHelper — remove all conversion functions"
```

---

### Task 17: Update Watch WeightUnit.swift

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoopWatch Watch App/WeightUnit.swift`

- [ ] **Step 1: Simplify Watch WeightUnit**

Replace with a minimal version matching the iPhone UnitHelper (the Watch needs `symbol`, `increment`, `roundToNearest`):

```swift
import Foundation

/// Matches server weight_unit values exactly.
enum WeightUnit: String, Codable, Equatable {
    case kg
    case lbs

    var label: String { rawValue }

    var increment: Double {
        switch self {
        case .kg: return 2.5
        case .lbs: return 5.0
        }
    }

    func roundToNearest(_ value: Double) -> Double {
        let inc = increment
        return (value / inc).rounded() * inc
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add flexloop-ios/FlexLoop/FlexLoopWatch\ Watch\ App/WeightUnit.swift
git commit -m "feat: simplify Watch WeightUnit — remove conversions"
```

---

### Task 18: Update OnboardingViewModel and ProfileSetupView

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/ViewModels/OnboardingViewModel.swift`
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Views/Onboarding/ProfileSetupView.swift`

- [ ] **Step 1: Update OnboardingViewModel**

Add unit properties and rename fields:

```swift
import Foundation
import SwiftData
import Observation

@Observable
final class OnboardingViewModel {
    var name = ""
    var gender = "male"
    var age = 25
    var height = 170.0
    var weight = 70.0
    var weightUnit: WeightUnit = .kg
    var experienceLevel = "beginner"
    var goals = "general fitness"
    var availableEquipment: Set<String> = []
    var daysPerWeek = 3

    var isComplete = false
    var isSubmitting = false
    var errorMessage: String?

    let genders = ["male", "female", "other"]
    let experienceLevels = ["beginner", "intermediate", "advanced"]
    let goalOptions = ["hypertrophy", "strength", "general fitness", "weight loss", "endurance"]
    let equipmentOptions = [
        "barbell", "dumbbells", "kettlebells", "pull_up_bar",
        "cables", "machines", "bands", "bodyweight_only",
    ]

    var heightUnit: String {
        weightUnit == .kg ? "cm" : "in"
    }

    func submit(apiClient: APIClient, context: ModelContext) async {
        isSubmitting = true
        errorMessage = nil

        let userData = APIUserCreate(
            name: name, gender: gender, age: age,
            height: height, weight: weight,
            weightUnit: weightUnit.rawValue,
            heightUnit: heightUnit,
            experienceLevel: experienceLevel, goals: goals,
            availableEquipment: Array(availableEquipment)
        )

        do {
            let apiUser: APIUser = try await apiClient.post("/api/profiles", body: userData)

            let cachedUser = CachedUser(
                serverId: apiUser.id, name: apiUser.name, gender: apiUser.gender,
                age: apiUser.age, height: apiUser.height, weight: apiUser.weight,
                weightUnit: apiUser.weightUnit, heightUnit: apiUser.heightUnit,
                experienceLevel: apiUser.experienceLevel, goals: apiUser.goals,
                availableEquipment: apiUser.availableEquipment
            )
            context.insert(cachedUser)
            try context.save()

            try? await HealthKitManager.shared.requestAuthorization()

            isComplete = true
        } catch {
            errorMessage = "Failed to create profile. Check your server connection."
        }

        isSubmitting = false
    }
}
```

- [ ] **Step 2: Update ProfileSetupView — add unit picker first**

```swift
import SwiftUI

struct ProfileSetupView: View {
    @Bindable var viewModel: OnboardingViewModel
    let onNext: () -> Void

    var body: some View {
        Form {
            Section(String(localized: "onboarding.unitSystem")) {
                Picker(String(localized: "settings.weightUnit"), selection: $viewModel.weightUnit) {
                    Text(String(localized: "settings.metric")).tag(WeightUnit.kg)
                    Text(String(localized: "settings.imperial")).tag(WeightUnit.lbs)
                }
                .pickerStyle(.segmented)
            }

            Section("About You") {
                TextField("Name", text: $viewModel.name)

                Picker("Gender", selection: $viewModel.gender) {
                    ForEach(viewModel.genders, id: \.self) { Text($0.capitalized) }
                }

                Stepper("Age: \(viewModel.age)", value: $viewModel.age, in: 13...100)

                HStack {
                    Text("Height")
                    Spacer()
                    TextField(viewModel.weightUnit.heightSymbol,
                              value: $viewModel.height, format: .number)
                        .keyboardType(.decimalPad)
                        .frame(width: 80)
                        .multilineTextAlignment(.trailing)
                    Text(viewModel.weightUnit.heightSymbol)
                }

                HStack {
                    Text("Weight")
                    Spacer()
                    TextField(viewModel.weightUnit.symbol,
                              value: $viewModel.weight, format: .number)
                        .keyboardType(.decimalPad)
                        .frame(width: 80)
                        .multilineTextAlignment(.trailing)
                    Text(viewModel.weightUnit.symbol)
                }
            }

            Section("Experience") {
                Picker("Level", selection: $viewModel.experienceLevel) {
                    ForEach(viewModel.experienceLevels, id: \.self) { Text($0.capitalized) }
                }

                Stepper("Days per week: \(viewModel.daysPerWeek)",
                        value: $viewModel.daysPerWeek, in: 1...7)
            }

            Section {
                Button("Next") { onNext() }
                    .frame(maxWidth: .infinity)
                    .disabled(viewModel.name.isEmpty)
            }
        }
    }
}
```

- [ ] **Step 3: Commit**

```bash
git add flexloop-ios/FlexLoop/FlexLoop/ViewModels/OnboardingViewModel.swift flexloop-ios/FlexLoop/FlexLoop/Views/Onboarding/ProfileSetupView.swift
git commit -m "feat: add unit picker to onboarding, remove kg/cm hardcoding"
```

---

### Task 19: Update GuidedWorkoutViewModel — rename weightKg fields

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/ViewModels/GuidedWorkoutViewModel.swift`

- [ ] **Step 1: Rename internal structs**

- `GuidedSetTarget.targetWeightKg` → `GuidedSetTarget.targetWeight`
- `CompletedSet.weightKg` → `CompletedSet.weight`
- All references: `completed.weightKg` → `completed.weight`, `t.targetWeightKg` → `t.targetWeight`

- [ ] **Step 2: Update `completeSet` signature**

Change `weightKg:` parameter name to `weight:` throughout.

- [ ] **Step 3: Update `editCompletedSet`**

Change `weightKg:` parameter to `weight:`.

- [ ] **Step 4: Update `stateSnapshot`**

Change `weightKg: t.targetWeightKg` → `weight: t.targetWeight` and `weightKg: c.weightKg` → `weight: c.weight`.

- [ ] **Step 5: Update `loadFromPlanDay`**

Change `targetWeightKg: target.targetWeightKg` → `targetWeight: target.targetWeight` and `targetWeightKg: ex.weight` → `targetWeight: ex.weight`.

- [ ] **Step 6: Commit**

```bash
git add flexloop-ios/FlexLoop/FlexLoop/ViewModels/GuidedWorkoutViewModel.swift
git commit -m "feat: rename weightKg to weight throughout GuidedWorkoutViewModel"
```

---

## Chunk 7: iOS Views — Remove Conversions

### Task 20: Update SetEntryRow — remove conversion binding

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Views/Workout/SetEntryRow.swift`

- [ ] **Step 1: Remove conversion layer**

Remove the `displayWeight` binding wrapper and `unit.fromKg`/`unit.toKg` calls. Weight is now stored in the user's unit — bind directly:

Remove `private let unit = WeightUnit.current` and the `displayWeight` computed binding.

The `weight` binding already holds the value in the user's unit. Pass the unit symbol from outside or read from the user profile. Simplest: accept `unitSymbol: String` as a parameter.

```swift
struct SetEntryRow: View {
    let setNumber: Int
    let previousWeight: Double?
    let previousReps: Int?
    let unitSymbol: String

    @Binding var weight: Double?
    @Binding var reps: Int?
    @Binding var rpe: Double?
    @Binding var setType: SetType

    var body: some View {
        HStack(spacing: 12) {
            // ... set number and type menu unchanged ...

            VStack(alignment: .center, spacing: 2) {
                HStack(spacing: 2) {
                    TextField("--", value: $weight, format: .number)
                        .keyboardType(.decimalPad)
                        .multilineTextAlignment(.center)
                        .frame(width: 56)
                    Text(unitSymbol)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if let prev = previousWeight {
                    Text("\(prev, specifier: "%.1f")")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            // ... rest unchanged ...
        }
        .padding(.vertical, 4)
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add flexloop-ios/FlexLoop/FlexLoop/Views/Workout/SetEntryRow.swift
git commit -m "feat: remove unit conversion from SetEntryRow — use native values"
```

---

### Task 21: Update GuidedWorkoutView — remove conversions from GuidedSetRow

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Views/Workout/GuidedWorkoutView.swift`

- [ ] **Step 1: Update GuidedSetRow**

Remove `private let unit = WeightUnit.current`. Add `let unitSymbol: String` parameter.

Remove all `unit.fromKgRounded()` and `unit.toKg()` calls:
- `_editWeightDisplay = State(initialValue: weightKg.map { u.fromKgRounded($0) })` → `_editWeightDisplay = State(initialValue: completedSet?.weight ?? targetWeight)`
- `editWeightKg` computed property (line 357-358) is no longer needed — `editWeightDisplay` IS the stored value
- In `onComplete`/`onEdit` calls, pass `editWeightDisplay` directly instead of `editWeightKg`
- In `.onChange` handlers, remove `unit.fromKgRounded()` — assign directly

Rename `targetWeightKg` → `targetWeight` and `completedSet?.weightKg` → `completedSet?.weight`.

- [ ] **Step 2: Update setsSection**

Pass `unitSymbol` to `GuidedSetRow`. Change `targetWeightKg:` → `targetWeight:` in the call site.

Update the column header: `WeightUnit.current.symbol` → get symbol from the view model or pass it through.

- [ ] **Step 3: Commit**

```bash
git add flexloop-ios/FlexLoop/FlexLoop/Views/Workout/GuidedWorkoutView.swift
git commit -m "feat: remove all unit conversions from GuidedWorkoutView"
```

---

### Task 22: Update SessionDetailView — remove conversion

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Views/History/SessionDetailView.swift`

- [ ] **Step 1: Remove conversion**

Remove `let unit = WeightUnit.current` and `unit.fromKgRounded(w)` calls. Display `set.weight` directly. Accept `unitSymbol: String` as a parameter or read from context:

```swift
if let w = set.weight, let r = set.reps {
    Text("\(w, specifier: "%.1f") \(unitSymbol) x \(r)")
        .font(.subheadline.monospacedDigit())
}
```

- [ ] **Step 2: Commit**

```bash
git add flexloop-ios/FlexLoop/FlexLoop/Views/History/SessionDetailView.swift
git commit -m "feat: remove unit conversion from SessionDetailView"
```

---

### Task 23: Update E1RMChartCard — remove conversion

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Views/Progress/E1RMChartCard.swift`

- [ ] **Step 1: Remove all `unit.fromKgRounded` calls**

Replace every `unit.fromKgRounded(x)` with just `x`. Accept `unitSymbol: String` parameter:

- Line 15: `unit.fromKgRounded(latest.value)` → `latest.value`
- Line 30, 37: same in chart marks
- Line 62: trend diff calculation — remove conversion

- [ ] **Step 2: Commit**

```bash
git add flexloop-ios/FlexLoop/FlexLoop/Views/Progress/E1RMChartCard.swift
git commit -m "feat: remove unit conversion from E1RMChartCard"
```

---

### Task 24: Update PlanExerciseEditView — remove conversion

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Views/Plan/PlanExerciseEditView.swift`

- [ ] **Step 1: Remove init-time conversion and onDisappear conversion**

The init currently converts `target.targetWeightKg` via `u.fromKgRounded()`. Now `targetWeight` is already in the user's unit — use directly:

```swift
_setTargets = State(initialValue: setsJson.map { target in
    EditableSetTarget(
        setNumber: target.setNumber,
        targetWeightDisplay: target.targetWeight,
        targetReps: target.targetReps,
        targetRpe: target.targetRpe
    )
})
```

In `onDisappear`, remove `unit.toKg()` — write value directly:

```swift
exercise.setsJson = setTargets.map { target in
    APISetTarget(
        setNumber: target.setNumber,
        targetWeight: target.targetWeightDisplay,
        targetReps: target.targetReps,
        targetRpe: target.targetRpe
    )
}
if let first = setTargets.first {
    exercise.weight = first.targetWeightDisplay
    exercise.rpeTarget = first.targetRpe
}
```

- [ ] **Step 2: Commit**

```bash
git add flexloop-ios/FlexLoop/FlexLoop/Views/Plan/PlanExerciseEditView.swift
git commit -m "feat: remove unit conversion from PlanExerciseEditView"
```

---

### Task 25: Update WatchWorkoutView — fix digital crown and remove conversion

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoopWatch Watch App/WatchWorkoutView.swift`

- [ ] **Step 1: Fix digital crown increment**

Change line 103 from the weird `2.26796` to native unit increments:

```swift
.digitalCrownRotation($weight, from: 0, through: 500,
                      by: unit.increment)
```

- [ ] **Step 2: Remove `unit.fromKgRounded(weight)` conversion**

Line 98: `let displayWeight = unit.fromKgRounded(weight)` → just use `weight` directly:

```swift
Text("\(weight, specifier: "%.1f") \(unit.label)")
```

- [ ] **Step 3: Update `completeSet` — rename `weightKg:` parameter**

```swift
sessionManager.sendCompleteSet(
    exerciseIndex: state.currentExerciseIndex,
    setNumber: currentSetNumber,
    weight: weight,
    reps: reps,
    rpe: rpe
)
```

- [ ] **Step 4: Update `loadCurrentExerciseDefaults`**

Line 192: `weight = target?.weightKg ?? 0` → `weight = target?.weight ?? 0`

- [ ] **Step 5: Commit**

```bash
git add flexloop-ios/FlexLoop/FlexLoopWatch\ Watch\ App/WatchWorkoutView.swift
git commit -m "feat: fix Watch digital crown increments, remove conversions"
```

---

## Chunk 8: iOS Connectivity, Settings & Tests

### Task 26: Update WatchConnectivityManager and WatchSessionManager

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Services/WatchConnectivityManager.swift`
- Modify: `flexloop-ios/FlexLoop/FlexLoopWatch Watch App/WatchSessionManager.swift`

- [ ] **Step 1: Update WatchConnectivityManager**

Rename any `weightKg` parameter references to `weight` in the message handling. Since sync models were renamed in Task 15, update the field access accordingly (e.g., `action.weightKg` → `action.weight`).

- [ ] **Step 2: Update WatchSessionManager**

Same — rename `weightKg` → `weight` in the `sendCompleteSet` method signature and message construction.

- [ ] **Step 3: Commit**

```bash
git add flexloop-ios/FlexLoop/FlexLoop/Services/WatchConnectivityManager.swift flexloop-ios/FlexLoop/FlexLoopWatch\ Watch\ App/WatchSessionManager.swift
git commit -m "feat: update Watch connectivity for native weight values"
```

---

### Task 27: Update SettingsView — make unit read-only

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Views/Settings/SettingsView.swift`

- [ ] **Step 1: Replace toggle with read-only display**

Remove the `@AppStorage("unitSystem")` picker. Query `CachedUser` from SwiftData and show the unit as read-only:

```swift
@Query private var users: [CachedUser]
private var currentUser: CachedUser? { users.first }

// In body, replace the unit picker section:
Section(String(localized: "settings.weightUnit")) {
    HStack {
        Text(String(localized: "settings.weightUnit"))
        Spacer()
        Text(currentUser?.weightUnit == "lbs" ?
             String(localized: "settings.imperial") :
             String(localized: "settings.metric"))
            .foregroundStyle(.secondary)
    }
    Text(String(localized: "settings.unitChangeHint"))
        .font(.caption)
        .foregroundStyle(.secondary)
}
```

- [ ] **Step 2: Commit**

```bash
git add flexloop-ios/FlexLoop/FlexLoop/Views/Settings/SettingsView.swift
git commit -m "feat: make unit preference read-only in settings"
```

---

### Task 28: Update iOS test file for CachedUser rename

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoopTests/FlexLoopTests.swift`

- [ ] **Step 1: Update CachedUser test**

Line 24-27 uses old init parameters. Update:

```swift
let user = CachedUser(
    serverId: 1, name: "Test User", gender: "male", age: 28,
    height: 180.0, weight: 82.0, weightUnit: "kg", heightUnit: "cm",
    experienceLevel: "intermediate",
    goals: "hypertrophy", availableEquipment: ["barbell"]
)
```

- [ ] **Step 2: Commit**

```bash
git add flexloop-ios/FlexLoop/FlexLoopTests/FlexLoopTests.swift
git commit -m "fix: update iOS tests for CachedUser field renames"
```

---

### Task 29: Update evals test profiles and runner

**Files:**
- Modify: `flexloop-server/evals/test_profiles.json`
- Modify: `flexloop-server/evals/runner.py`

- [ ] **Step 1: Update test_profiles.json**

Rename `height_cm` → `height`, `weight_kg` → `weight` in all 5 profiles. Add `weight_unit` and `height_unit` to each:

```json
{
    "id": "beginner_female_bodyweight",
    "name": "Sarah",
    "gender": "female",
    "age": 24,
    "height": 163,
    "weight": 58,
    "weight_unit": "kg",
    "height_unit": "cm",
    ...
}
```

Do this for all 5 profiles (Sarah, Mike, Tom, Lisa, Alex).

- [ ] **Step 2: Update runner.py format_profile function**

Line 43-52, change:

```python
def format_profile(profile: dict) -> str:
    unit = profile.get("weight_unit", "kg")
    h_unit = profile.get("height_unit", "cm")
    return (
        f"Name: {profile['name']}\n"
        f"Gender: {profile['gender']}, Age: {profile['age']}\n"
        f"Height: {profile['height']}{h_unit}, Weight: {profile['weight']}{unit}\n"
        f"Experience: {profile['experience_level']}\n"
        f"Goals: {profile['goals']}\n"
        f"Available equipment: {', '.join(profile['available_equipment'])}\n"
        f"Days per week: {profile['days_per_week']}"
    )
```

- [ ] **Step 3: Commit**

```bash
git add flexloop-server/evals/
git commit -m "feat: update evals for native unit system"
```

---

### Task 30: Add localization keys for new UI strings

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Resources/Localizable.xcstrings`

- [ ] **Step 1: Add missing keys**

Add `onboarding.unitSystem` and `settings.unitChangeHint` with English and Simplified Chinese translations:

- `onboarding.unitSystem`: EN "Unit System", ZH "单位系统"
- `settings.unitChangeHint`: EN "Unit is set during profile creation. To change, create a new profile.", ZH "单位在创建个人资料时设置。如需更改，请创建新的个人资料。"

- [ ] **Step 2: Commit**

```bash
git add flexloop-ios/FlexLoop/FlexLoop/Resources/Localizable.xcstrings
git commit -m "feat: add localization keys for unit system UI"
```

---

## Chunk 9: Database Migration & Final Verification

### Task 31: Create Alembic migration

**Files:**
- Create: `flexloop-server/alembic/versions/xxxx_native_unit_system.py`

- [ ] **Step 1: Generate migration**

Since we deleted the database (no existing data to migrate), this migration is for schema documentation. The models will auto-create tables on fresh start. But we still need a migration for production-readiness:

```bash
cd flexloop-server && python -m alembic revision --autogenerate -m "native unit system"
```

Review the generated migration — it should show:
- `users` table: `height_cm` → `height`, `weight_kg` → `weight`, new columns `weight_unit`, `height_unit`
- `measurements` table: `value_cm` → `value`

- [ ] **Step 2: Commit**

```bash
git add flexloop-server/alembic/
git commit -m "feat: add migration for native unit system schema changes"
```

---

### Task 32: Run full server test suite

- [ ] **Step 1: Run all server tests**

```bash
cd flexloop-server && python -m pytest -v --tb=short
```

Expected: ALL PASS

- [ ] **Step 2: Fix any failures**

Address any remaining `weight_kg`, `height_cm`, `value_cm`, `target_weight_kg` references.

---

### Task 33: Build and verify iOS app

- [ ] **Step 1: Build iOS app**

Use XcodeBuildMCP `build_sim` or:
```bash
cd flexloop-ios/FlexLoop && xcodebuild build -scheme FlexLoop -destination 'platform=iOS Simulator,name=iPhone 16' 2>&1 | tail -5
```

Expected: BUILD SUCCEEDED with zero errors

- [ ] **Step 2: Build Watch app**

```bash
cd flexloop-ios/FlexLoop && xcodebuild build -scheme FlexLoopWatch\ Watch\ App -destination 'platform=watchOS Simulator,name=Apple Watch Series 10 (46mm)' 2>&1 | tail -5
```

Expected: BUILD SUCCEEDED

- [ ] **Step 3: Fix any compile errors**

Address remaining references to old field names (`weightKg`, `fromKg`, `toKg`, `fromKgRounded`, `heightCm`, `targetWeightKg`).

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "fix: resolve remaining compile errors from native unit migration"
```
