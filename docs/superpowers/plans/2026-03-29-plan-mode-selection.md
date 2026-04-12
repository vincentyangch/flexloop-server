# Plan Mode Selection Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users choose from 7 predefined plan modes before AI generates a training plan, and simplify the prompt to focus on exercise selection only.

**Architecture:** Server defines a `PLAN_MODES` lookup dict. New `plan_mode` field added to the generate request. Prompt v2 receives the mode's day structure and a slimmed user profile. Server injects `split_type`/`cycle_length`/`plan_name` from the lookup rather than reading them from AI output. iOS adds a full-screen mode picker before generation and removes the equipment step from onboarding.

**Tech Stack:** Python/FastAPI (server), SwiftUI (iOS), Pydantic, pytest

**Spec:** `docs/superpowers/specs/2026-03-29-plan-mode-selection.md`

---

## Chunk 1: Server — Plan Modes, Schema, Profile, Validator

### Task 1: Add PLAN_MODES lookup dict

**Files:**
- Create: `flexloop-server/src/flexloop/ai/plan_modes.py`

- [ ] **Step 1: Write the test**

In `flexloop-server/tests/test_plan_modes.py`:

```python
from flexloop.ai.plan_modes import PLAN_MODES, VALID_PLAN_MODES


def test_plan_modes_has_all_keys():
    expected = {
        "full_body_3", "upper_lower_4", "ppl_6", "arnold_6",
        "body_part_5", "ppl_3", "phul_4",
    }
    assert set(PLAN_MODES.keys()) == expected


def test_valid_plan_modes_matches_keys():
    assert VALID_PLAN_MODES == set(PLAN_MODES.keys())


def test_each_mode_has_required_fields():
    for key, mode in PLAN_MODES.items():
        assert "plan_name" in mode, f"{key} missing plan_name"
        assert "split_type" in mode, f"{key} missing split_type"
        assert "cycle_length" in mode, f"{key} missing cycle_length"
        assert "description" in mode, f"{key} missing description"
        assert isinstance(mode["cycle_length"], int)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd flexloop-server && python -m pytest tests/test_plan_modes.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write the implementation**

Create `flexloop-server/src/flexloop/ai/plan_modes.py` with the full `PLAN_MODES` dict from the spec (all 7 modes with `plan_name`, `split_type`, `cycle_length`, `description`) and `VALID_PLAN_MODES = set(PLAN_MODES.keys())`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd flexloop-server && python -m pytest tests/test_plan_modes.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add flexloop-server/src/flexloop/ai/plan_modes.py flexloop-server/tests/test_plan_modes.py
git commit -m "feat(server): add PLAN_MODES lookup dict for plan mode selection"
```

---

### Task 2: Update PlanGenerateRequest schema with plan_mode

**Files:**
- Modify: `flexloop-server/src/flexloop/schemas/plan.py:113-114`

- [ ] **Step 1: Write the test**

In `flexloop-server/tests/test_plan_modes.py` (append):

```python
import pytest
from pydantic import ValidationError
from flexloop.schemas.plan import PlanGenerateRequest


def test_plan_generate_request_valid():
    req = PlanGenerateRequest(user_id=1, plan_mode="ppl_6")
    assert req.plan_mode == "ppl_6"


def test_plan_generate_request_invalid_mode():
    with pytest.raises(ValidationError):
        PlanGenerateRequest(user_id=1, plan_mode="invalid_mode")


def test_plan_generate_request_missing_mode():
    with pytest.raises(ValidationError):
        PlanGenerateRequest(user_id=1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd flexloop-server && python -m pytest tests/test_plan_modes.py::test_plan_generate_request_valid -v`
Expected: FAIL — `plan_mode` field not recognized

- [ ] **Step 3: Update the schema**

In `flexloop-server/src/flexloop/schemas/plan.py`, change `PlanGenerateRequest`:

```python
from typing import Literal

class PlanGenerateRequest(BaseModel):
    user_id: int
    plan_mode: Literal[
        "full_body_3", "upper_lower_4", "ppl_6", "arnold_6",
        "body_part_5", "ppl_3", "phul_4"
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd flexloop-server && python -m pytest tests/test_plan_modes.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add flexloop-server/src/flexloop/schemas/plan.py flexloop-server/tests/test_plan_modes.py
git commit -m "feat(server): add plan_mode field to PlanGenerateRequest with Literal validation"
```

---

### Task 3: Add format_plan_profile() and v2 validator

**Files:**
- Modify: `flexloop-server/src/flexloop/routers/ai.py:75-84` (add new function, keep old one)
- Modify: `flexloop-server/src/flexloop/ai/validators.py` (add `validate_plan_v2_output`)

- [ ] **Step 1: Write the tests**

In `flexloop-server/tests/test_plan_modes.py` (append):

```python
from flexloop.ai.validators import validate_plan_v2_output


def test_format_plan_profile_excludes_name_height_equipment():
    from flexloop.routers.ai import format_plan_profile
    from unittest.mock import MagicMock

    user = MagicMock()
    user.gender = "male"
    user.age = 28
    user.weight = 82.0
    user.weight_unit = "kg"
    user.experience_level = "intermediate"
    user.goals = "hypertrophy"
    user.name = "Test"
    user.height = 180.0
    user.available_equipment = ["barbell"]

    profile = format_plan_profile(user)
    assert "male" in profile
    assert "28" in profile
    assert "82.0" in profile
    assert "intermediate" in profile
    assert "hypertrophy" in profile
    assert "Test" not in profile
    assert "180" not in profile
    assert "barbell" not in profile


def test_validate_plan_v2_valid():
    data = {
        "days": [
            {
                "day_number": 1,
                "label": "Push A",
                "focus": "chest,shoulders,triceps",
                "exercise_groups": [
                    {
                        "group_type": "straight",
                        "order": 1,
                        "exercises": [{"exercise_name": "Bench Press", "sets": 4, "reps": 8}],
                    }
                ],
            }
        ]
    }
    result = validate_plan_v2_output(data)
    assert result.is_valid


def test_validate_plan_v2_missing_days():
    result = validate_plan_v2_output({})
    assert not result.is_valid


def test_validate_plan_v2_empty_days():
    result = validate_plan_v2_output({"days": []})
    assert not result.is_valid


def test_validate_plan_v2_missing_exercise_groups():
    data = {"days": [{"day_number": 1, "label": "Push"}]}
    result = validate_plan_v2_output(data)
    assert not result.is_valid
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd flexloop-server && python -m pytest tests/test_plan_modes.py::test_format_plan_profile_excludes_name_height_equipment -v`
Expected: FAIL — `format_plan_profile` not found

- [ ] **Step 3: Add format_plan_profile() to ai.py**

In `flexloop-server/src/flexloop/routers/ai.py`, add after `format_user_profile()` (after line 84):

```python
def format_plan_profile(user: User) -> str:
    return (
        f"Gender: {user.gender}, Age: {user.age}\n"
        f"Weight: {user.weight}{user.weight_unit}\n"
        f"Weight unit: {user.weight_unit}\n"
        f"Experience: {user.experience_level}\n"
        f"Goals: {user.goals}"
    )
```

- [ ] **Step 4: Add validate_plan_v2_output() to validators.py**

In `flexloop-server/src/flexloop/ai/validators.py`, add after `validate_plan_output()`:

```python
def validate_plan_v2_output(data: dict) -> ValidationResult:
    errors = []
    if "days" not in data:
        errors.append("Missing required field: days")
    elif not isinstance(data["days"], list) or len(data["days"]) == 0:
        errors.append("'days' must be a non-empty list")
    else:
        for i, day in enumerate(data["days"]):
            if "exercise_groups" not in day:
                errors.append(f"Day {i + 1} missing 'exercise_groups'")
            elif not isinstance(day["exercise_groups"], list):
                errors.append(f"Day {i + 1} 'exercise_groups' must be a list")
    return ValidationResult(is_valid=len(errors) == 0, errors=errors)
```

- [ ] **Step 5: Run all tests**

Run: `cd flexloop-server && python -m pytest tests/test_plan_modes.py -v`
Expected: PASS (11 tests)

- [ ] **Step 6: Commit**

```bash
git add flexloop-server/src/flexloop/routers/ai.py flexloop-server/src/flexloop/ai/validators.py flexloop-server/tests/test_plan_modes.py
git commit -m "feat(server): add format_plan_profile and validate_plan_v2_output"
```

---

### Task 4: Create prompt v2 and update manifest

**Files:**
- Create: `flexloop-server/prompts/plan_generation/v2.md`
- Modify: `flexloop-server/prompts/manifest.json`

- [ ] **Step 1: Write the test**

In `flexloop-server/tests/test_plan_modes.py` (append):

```python
from pathlib import Path
from flexloop.ai.prompts import PromptManager


def test_prompt_v2_renders_with_plan_mode():
    prompts_dir = Path(__file__).parent.parent / "prompts"
    if not prompts_dir.exists():
        pytest.skip("prompts directory not found")
    manager = PromptManager(prompts_dir)
    rendered = manager.render(
        "plan_generation",
        user_profile="Gender: male, Age: 28\nWeight: 82.0kg\nExperience: intermediate\nGoals: hypertrophy",
        plan_mode_description="Cycle length: 6 days\n- Day 1 (Push A): chest, shoulders, triceps",
        weight_unit="kg",
    )
    assert "82.0kg" in rendered
    assert "Push A" in rendered
    assert "{{user_profile}}" not in rendered
    assert "{{plan_mode_description}}" not in rendered
    assert "{{weight_unit}}" not in rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd flexloop-server && python -m pytest tests/test_plan_modes.py::test_prompt_v2_renders_with_plan_mode -v`
Expected: FAIL — template still v1, missing placeholders

- [ ] **Step 3: Create prompt v2**

Create `flexloop-server/prompts/plan_generation/v2.md`:

```markdown
You are an expert fitness coach selecting exercises for a training program.

## User Profile
{{user_profile}}

## Plan Structure
{{plan_mode_description}}

## Instructions
The plan structure above is fixed. Your job is to select appropriate exercises and set targets for each day. Consider:
- Experience level and appropriate volume (sets per muscle group)
- Goal-appropriate rep ranges and intensity
- Per-set targets with weight, reps, and RPE
- Exercise variety between A/B days (if applicable)
- Use compound movements first, then isolation exercises

## Unit System
ALL weights MUST use {{weight_unit}}. Use round numbers (5lb increments for lbs, 2.5kg increments for kg).

## Output Format
Respond with a JSON object:
{
  "days": [
    {
      "day_number": 1,
      "label": "Push A",
      "focus": "chest,shoulders,triceps",
      "exercise_groups": [
        {
          "group_type": "straight",
          "rest_after_group_sec": 90,
          "order": 1,
          "exercises": [
            {
              "exercise_name": "Barbell Bench Press",
              "sets": 4,
              "reps": 8,
              "rpe_target": 8.0,
              "sets_json": [
                {"set_number": 1, "target_weight": 60, "target_reps": 8, "target_rpe": 7},
                {"set_number": 2, "target_weight": 60, "target_reps": 8, "target_rpe": 7.5},
                {"set_number": 3, "target_weight": 60, "target_reps": 8, "target_rpe": 8},
                {"set_number": 4, "target_weight": 60, "target_reps": 8, "target_rpe": 8.5}
              ],
              "notes": "optional coaching note"
            }
          ]
        }
      ]
    }
  ]
}

- Each day MUST match the plan structure above (same day count and muscle focus)
- Each exercise MUST include `sets_json` with per-set targets using the user's weight unit
- Be conservative with starting weights and volume for beginners
- Include `order` field in each exercise_group starting from 1
```

- [ ] **Step 4: Update manifest.json**

Change `flexloop-server/prompts/manifest.json`:

```json
{
  "plan_generation": { "default": "v2" },
  "block_review": { "default": "v1" },
  "session_review": { "default": "v1" },
  "chat": { "default": "v1" }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd flexloop-server && python -m pytest tests/test_plan_modes.py::test_prompt_v2_renders_with_plan_mode -v`
Expected: PASS

- [ ] **Step 6: Run all prompt tests to check nothing broke**

Run: `cd flexloop-server && python -m pytest tests/test_prompts.py tests/test_plan_modes.py -v`
Expected: PASS (all tests)

- [ ] **Step 7: Commit**

```bash
git add flexloop-server/prompts/plan_generation/v2.md flexloop-server/prompts/manifest.json flexloop-server/tests/test_plan_modes.py
git commit -m "feat(server): add prompt v2 for plan mode selection, update manifest"
```

---

### Task 5: Update generate_plan endpoint to use plan_mode

**Files:**
- Modify: `flexloop-server/src/flexloop/routers/ai.py:89-134` (replace lines 89-134 of the generate_plan endpoint; keep lines 136-275 unchanged — the day/exercise saving loop)
- Modify: `flexloop-server/src/flexloop/ai/coach.py:17-42` (generate_plan method)

- [ ] **Step 1: Update AICoach.generate_plan() signature**

In `flexloop-server/src/flexloop/ai/coach.py`, update:

```python
async def generate_plan(
    self, user_profile: str, plan_mode_description: str, weight_unit: str,
) -> tuple[dict | None, LLMResponse]:
    prompt = self.prompts.render(
        "plan_generation",
        provider=settings.ai_provider,
        user_profile=user_profile,
        plan_mode_description=plan_mode_description,
        weight_unit=weight_unit,
    )

    response = await self.adapter.generate(
        system_prompt="You are a fitness plan generator. Respond only with valid JSON.",
        user_prompt=prompt,
        temperature=settings.ai_temperature,
        max_tokens=settings.ai_max_tokens,
    )

    try:
        data = json.loads(response.content)
    except json.JSONDecodeError:
        logger.warning("AI returned non-JSON response for plan generation")
        return None, response

    validation = validate_plan_v2_output(data)
    if not validation.is_valid:
        logger.warning(f"AI plan output validation failed: {validation.errors}")
        return None, response

    return data, response
```

Update the import at top of coach.py:

```python
from flexloop.ai.validators import validate_plan_v2_output, validate_review_output
```

- [ ] **Step 2: Update generate_plan endpoint in ai.py**

In `flexloop-server/src/flexloop/routers/ai.py`, update the endpoint (lines 89-132) to:

```python
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
    # ... rest of day/exercise saving logic stays the same
```

- [ ] **Step 3: Run full test suite**

Run: `cd flexloop-server && python -m pytest -v`
Expected: PASS (existing tests may need minor updates — see Step 4)

- [ ] **Step 4: Fix any broken tests**

The `test_api_ai.py` user fixture still works (it doesn't test plan generation directly). If any existing plan generation integration tests fail due to the new required `plan_mode` field, update them to include `plan_mode`.

- [ ] **Step 5: Commit**

```bash
git add flexloop-server/src/flexloop/ai/coach.py flexloop-server/src/flexloop/routers/ai.py
git commit -m "feat(server): wire plan_mode through generate_plan endpoint and AICoach"
```

---

## Chunk 2: iOS — Plan Mode Picker and API Changes

### Task 6: Update APIPlanGenerateRequest with planMode

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Services/APIModels.swift:203-209`
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Services/APIClient.swift:165-167`

- [ ] **Step 1: Update APIPlanGenerateRequest**

In `APIModels.swift`, change:

```swift
struct APIPlanGenerateRequest: Codable, Sendable {
    let userId: Int
    let planMode: String

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case planMode = "plan_mode"
    }
}
```

- [ ] **Step 2: Update APIClient.generatePlan()**

In `APIClient.swift`, change:

```swift
func generatePlan(userId: Int, planMode: String) async throws -> APIPlanGenerateResponse {
    try await post("/api/ai/plan/generate", body: APIPlanGenerateRequest(userId: userId, planMode: planMode), timeout: 120)
}
```

- [ ] **Step 3: Update PlanListViewModel.generatePlan()**

In `PlanListViewModel.swift`, change the method signature:

```swift
func generatePlan(apiClient: APIClient, userId: Int, planMode: String) async {
    isGenerating = true
    errorMessage = nil

    do {
        let response = try await apiClient.generatePlan(userId: userId, planMode: planMode)
        if response.status == "success" {
            await loadPlans(apiClient: apiClient, userId: userId)
        } else {
            errorMessage = response.message ?? String(localized: "error.invalidPlan")
        }
    } catch {
        errorMessage = String(localized: "error.generatePlan")
    }

    isGenerating = false
}
```

- [ ] **Step 4: Build to verify compilation**

Run: Build the iOS project to verify no compile errors from the signature changes. Callers will break — that's expected, fixed in Task 7.

- [ ] **Step 5: Commit**

```bash
git add flexloop-ios/
git commit -m "feat(ios): add planMode to API request and viewmodel"
```

---

### Task 7: Create PlanModePickerView

**Files:**
- Create: `flexloop-ios/FlexLoop/FlexLoop/Views/Plan/PlanModePickerView.swift`
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Views/Plan/PlanListView.swift`

- [ ] **Step 1: Define PlanMode model**

Create `flexloop-ios/FlexLoop/FlexLoop/Views/Plan/PlanModePickerView.swift`:

```swift
import SwiftUI

enum PlanMode: String, CaseIterable, Identifiable {
    case fullBody3 = "full_body_3"
    case upperLower4 = "upper_lower_4"
    case ppl6 = "ppl_6"
    case arnold6 = "arnold_6"
    case bodyPart5 = "body_part_5"
    case ppl3 = "ppl_3"
    case phul4 = "phul_4"

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .fullBody3: String(localized: "planMode.fullBody3.name")
        case .upperLower4: String(localized: "planMode.upperLower4.name")
        case .ppl6: String(localized: "planMode.ppl6.name")
        case .arnold6: String(localized: "planMode.arnold6.name")
        case .bodyPart5: String(localized: "planMode.bodyPart5.name")
        case .ppl3: String(localized: "planMode.ppl3.name")
        case .phul4: String(localized: "planMode.phul4.name")
        }
    }

    var subtitle: String {
        switch self {
        case .fullBody3: String(localized: "planMode.fullBody3.subtitle")
        case .upperLower4: String(localized: "planMode.upperLower4.subtitle")
        case .ppl6: String(localized: "planMode.ppl6.subtitle")
        case .arnold6: String(localized: "planMode.arnold6.subtitle")
        case .bodyPart5: String(localized: "planMode.bodyPart5.subtitle")
        case .ppl3: String(localized: "planMode.ppl3.subtitle")
        case .phul4: String(localized: "planMode.phul4.subtitle")
        }
    }

    var daysPerCycle: Int {
        switch self {
        case .fullBody3, .ppl3: 3
        case .upperLower4, .phul4: 4
        case .bodyPart5: 5
        case .ppl6, .arnold6: 6
        }
    }

    var suitedFor: String {
        switch self {
        case .fullBody3: String(localized: "planMode.suited.beginner")
        case .upperLower4, .ppl3, .phul4: String(localized: "planMode.suited.intermediate")
        case .ppl6, .arnold6, .bodyPart5: String(localized: "planMode.suited.intAdvanced")
        }
    }
}
```

- [ ] **Step 2: Create PlanModePickerView**

Append to the same file:

```swift
struct PlanModePickerView: View {
    @State private var selectedMode: PlanMode?
    @Binding var isGenerating: Bool
    @Binding var errorMessage: String?
    let hasActivePlan: Bool
    let onGenerate: (PlanMode) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var showReplaceConfirmation = false

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(spacing: 12) {
                    ForEach(PlanMode.allCases) { mode in
                        PlanModeCard(
                            mode: mode,
                            isSelected: selectedMode == mode
                        )
                        .onTapGesture {
                            withAnimation(.easeInOut(duration: 0.2)) {
                                selectedMode = selectedMode == mode ? nil : mode
                            }
                        }
                    }
                }
                .padding()
            }
            .navigationTitle(String(localized: "planMode.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(String(localized: "common.cancel")) { dismiss() }
                }
            }
            .safeAreaInset(edge: .bottom) {
                Button {
                    if hasActivePlan {
                        showReplaceConfirmation = true
                    } else {
                        generate()
                    }
                } label: {
                    Text(String(localized: "plan.generatePlan"))
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                }
                .buttonStyle(.borderedProminent)
                .disabled(selectedMode == nil || isGenerating)
                .padding()
                .background(.ultraThinMaterial)
            }
            .overlay {
                if isGenerating {
                    VStack(spacing: 12) {
                        ProgressView()
                        Text(String(localized: "plan.generating"))
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(.ultraThinMaterial)
                }
            }
            .alert(String(localized: "planMode.replaceAlert.title"), isPresented: $showReplaceConfirmation) {
                Button(String(localized: "common.cancel"), role: .cancel) {}
                Button(String(localized: "planMode.replaceAlert.confirm"), role: .destructive) {
                    generate()
                }
            } message: {
                Text(String(localized: "planMode.replaceAlert.message"))
            }
            .alert(String(localized: "common.error"), isPresented: Binding(
                get: { errorMessage != nil },
                set: { if !$0 { errorMessage = nil } }
            )) {
                Button(String(localized: "common.ok")) { errorMessage = nil }
            } message: {
                if let msg = errorMessage {
                    Text(msg)
                }
            }
        }
    }

    private func generate() {
        guard let mode = selectedMode else { return }
        onGenerate(mode)
    }
}

struct PlanModeCard: View {
    let mode: PlanMode
    let isSelected: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(mode.displayName)
                    .font(.headline)
                Spacer()
                Text(String(localized: "planMode.daysPerCycle.\(mode.daysPerCycle)"))
                    .font(.caption)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(.fill.tertiary)
                    .clipShape(Capsule())
            }
            Text(mode.subtitle)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text(mode.suitedFor)
                .font(.caption)
                .foregroundStyle(.tertiary)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(isSelected ? Color.accentColor.opacity(0.1) : Color(.secondarySystemGroupedBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(isSelected ? Color.accentColor : .clear, lineWidth: 2)
        )
    }
}
```

- [ ] **Step 3: Update PlanListView to present PlanModePickerView**

In `PlanListView.swift`:

Add a `@State private var showModePicker = false` property.

Replace the toolbar button action (line 23) from `Task { await generatePlan() }` to `showModePicker = true`.

Replace the empty state button action (line 108) from `Task { await generatePlan() }` to `showModePicker = true`.

Add a `.sheet` modifier to present the picker:

```swift
.sheet(isPresented: $showModePicker) {
    PlanModePickerView(
        isGenerating: $viewModel.isGenerating,
        errorMessage: $viewModel.errorMessage,
        hasActivePlan: viewModel.activePlan != nil,
        onGenerate: { mode in
            Task { await generatePlan(planMode: mode.rawValue) }
        }
    )
}
```

Update the `generatePlan()` method:

```swift
private func generatePlan(planMode: String) async {
    guard let user = users.first else { return }
    let apiClient = APIClient(config: .current)
    await viewModel.generatePlan(apiClient: apiClient, userId: user.serverId, planMode: planMode)
    if viewModel.errorMessage == nil {
        // Success: dismiss picker, list reloads with new active plan visible
        showModePicker = false
    }
    // On error: stay on picker, error alert is shown inside PlanModePickerView
}
```

Remove the generating overlay from PlanListView (lines 30-41) since it's now in PlanModePickerView.
Remove the error alert from PlanListView (lines 43-52) since errors during generation are now shown in PlanModePickerView. Keep the alert only if other operations (activate, archive, delete) can set `errorMessage` — in that case, keep it but it won't conflict since the picker sheet handles its own errors via the binding.

- [ ] **Step 4: Build and verify**

Run: Build iOS project. Verify no compile errors.

- [ ] **Step 5: Commit**

```bash
git add flexloop-ios/
git commit -m "feat(ios): add PlanModePickerView with 7 plan mode cards"
```

---

### Task 8: Add localization strings for plan modes

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Resources/Localizable.xcstrings`

- [ ] **Step 1: Add English and Simplified Chinese strings**

Add the following localization keys:

| Key | English | Chinese |
|-----|---------|---------|
| `planMode.title` | Choose Plan Mode | 选择计划模式 |
| `planMode.fullBody3.name` | Full Body | 全身训练 |
| `planMode.fullBody3.subtitle` | All muscle groups each session | 每次训练覆盖所有肌群 |
| `planMode.upperLower4.name` | Upper / Lower | 上下肢分化 |
| `planMode.upperLower4.subtitle` | Upper A / Lower A / Upper B / Lower B | 上肢A / 下肢A / 上肢B / 下肢B |
| `planMode.ppl6.name` | Push / Pull / Legs | 推拉腿 |
| `planMode.ppl6.subtitle` | 3-way split, repeated twice | 三分化，重复两次 |
| `planMode.arnold6.name` | Arnold Split | 阿诺德分化 |
| `planMode.arnold6.subtitle` | Chest+Back / Shoulders+Arms / Legs, 2x | 胸背 / 肩臂 / 腿，重复两次 |
| `planMode.bodyPart5.name` | Body Part Split | 部位分化 |
| `planMode.bodyPart5.subtitle` | Chest / Back / Shoulders / Legs / Arms | 胸 / 背 / 肩 / 腿 / 臂 |
| `planMode.ppl3.name` | PPL (3-Day) | 推拉腿（3天） |
| `planMode.ppl3.subtitle` | Push / Pull / Legs, once through | 推 / 拉 / 腿，单次循环 |
| `planMode.phul4.name` | PHUL | PHUL |
| `planMode.phul4.subtitle` | Power + Hypertrophy, Upper/Lower | 力量 + 增肌，上下肢分化 |
| `planMode.suited.beginner` | Best for beginners | 适合初学者 |
| `planMode.suited.intermediate` | Best for intermediates | 适合中级训练者 |
| `planMode.suited.intAdvanced` | Intermediate to advanced | 中级至高级 |
| `planMode.daysPerCycle.%lld` | %lld days/cycle | %lld天/循环 |
| `planMode.replaceAlert.title` | Replace Current Plan? | 替换当前计划？ |
| `planMode.replaceAlert.message` | Generating a new plan will deactivate your current active plan. | 生成新计划将停用当前活跃的计划。 |
| `planMode.replaceAlert.confirm` | Replace | 替换 |

- [ ] **Step 2: Build and verify strings load**

Run: Build iOS project.

- [ ] **Step 3: Commit**

```bash
git add flexloop-ios/FlexLoop/FlexLoop/Resources/Localizable.xcstrings
git commit -m "feat(ios): add localization strings for plan mode picker (en + zh-Hans)"
```

---

## Chunk 3: iOS — Remove Equipment from Onboarding

### Task 9: Remove equipment step from onboarding

**Files:**
- Modify: `flexloop-ios/FlexLoop/FlexLoop/Views/Onboarding/OnboardingView.swift`
- Modify: `flexloop-ios/FlexLoop/FlexLoop/ViewModels/OnboardingViewModel.swift`

- [ ] **Step 1: Update OnboardingView**

Replace the TabView contents:

```swift
struct OnboardingView: View {
    @State private var viewModel = OnboardingViewModel()
    @State private var currentStep = 0

    var body: some View {
        NavigationStack {
            TabView(selection: $currentStep) {
                ProfileSetupView(viewModel: viewModel, onNext: { currentStep = 1 })
                    .tag(0)
                GoalPickerView(viewModel: viewModel)
                    .tag(1)
            }
            .tabViewStyle(.page(indexDisplayMode: .always))
            .navigationTitle("Welcome to FlexLoop")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}
```

- [ ] **Step 2: Clean up OnboardingViewModel**

In `OnboardingViewModel.swift`, remove:
- The `availableEquipment` property (line 15)
- The `equipmentOptions` array (lines 27-30)
- The `availableEquipment` usage in `submit()` (line 41) — pass an empty array instead: `availableEquipment: []`

- [ ] **Step 3: Build and verify**

Run: Build iOS project. Verify onboarding compiles and EquipmentPickerView is no longer referenced.

Note: Do NOT delete `EquipmentPickerView.swift` yet — it may be referenced elsewhere. If the build succeeds without it being imported anywhere, it can be deleted in a follow-up cleanup.

- [ ] **Step 4: Commit**

```bash
git add flexloop-ios/
git commit -m "feat(ios): remove equipment selection from onboarding flow"
```

---

## Chunk 4: Integration Test and Cleanup

### Task 10: Run full test suite and verify end-to-end

- [ ] **Step 1: Run server tests**

Run: `cd flexloop-server && python -m pytest -v`
Expected: All pass

- [ ] **Step 2: Build iOS project**

Run: Build via Xcode. Verify no warnings related to changes.

- [ ] **Step 3: Manual smoke test**

1. Launch app fresh (or clear data)
2. Go through onboarding — verify no equipment step
3. Go to Plans tab, tap Generate
4. Verify PlanModePickerView appears with 7 modes
5. Select a mode, tap Generate Plan
6. Verify plan is generated with correct split type and cycle length

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git commit -m "fix: address integration issues from plan mode selection"
```
