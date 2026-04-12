# FlexLoop — Product Requirements Document

**AI-Powered Fitness Training Companion**
**Version 1.0 | March 2026 | Open-Source Community Project**

---

## 1. Product Overview

### 1.1 Vision

FlexLoop is an open-source, self-hosted AI fitness app that acts as your personal training coach. It builds customized workout plans, tracks training sessions in real time, and uses AI to periodically review progress and suggest plan adjustments — creating a continuous feedback loop of **train → review → adjust → repeat**.

### 1.2 Problem Statement

Most fitness apps are either simple loggers with no intelligence, or rigid subscription services with pre-built programs that don't adapt. Serious self-trainers — whether they're into heavy lifting, light-weight/bodyweight training, or cardio — are left guessing when to change exercises, how to fix imbalances, and whether their programming is actually working.

Commercial solutions lock useful AI features behind expensive subscriptions and offer no transparency into how recommendations are generated.

### 1.3 Solution

FlexLoop is a free, open-source alternative that combines real-time workout logging with a **configurable AI engine** that understands periodization, progressive overload, muscle group balance, and fatigue management. Users bring their own LLM (OpenAI, Anthropic, local models via Ollama, etc.) and retain full control over their data.

The app runs natively on iOS (iPhone + Apple Watch) with a self-hosted backend API server. Users log workouts on their phone at the gym, and the app syncs to their personal backend server for AI-powered analysis and plan adjustments.

### 1.4 Key Differentiators

- **Native iOS experience** — built with SwiftUI for iPhone and Apple Watch, with full HealthKit integration
- **Open-source and self-hostable** — no vendor lock-in, no subscription fees, full data ownership
- **Pluggable LLM backend** — configure any model provider (OpenAI, Anthropic, Google, local Ollama/llama.cpp)
- **Extensible architecture** — plugin system for community contributions (new exercise libraries, AI prompts, cardio integrations, wearable connectors)
- **Inclusive design** — supports strength training, bodyweight/light-weight training, and cardio
- **Small-scale by design** — optimized for personal use, not enterprise SaaS

### 1.5 Project Philosophy

- **Convention over configuration** — sensible defaults that work out of the box, with deep customization available
- **Offline-first** — core logging works without internet on-device; data syncs to the backend when connectivity is available; AI features require backend connectivity
- **Privacy-first** — all data stored locally on-device and on user-controlled backend infrastructure; no telemetry, no analytics
- **Contributor-friendly** — clear module boundaries, comprehensive docs, and a plugin API so the community can extend without forking
- **Platform-agnostic backend** — all business logic lives on the server, enabling future Android or web clients without duplicating core functionality

---

## 2. Target Users & Personas

### 2.1 Persona A — The Self-Coached Lifter

| Attribute | Detail |
|-----------|--------|
| Profile | Male or female, trains 4–6 days/week, intermediate experience (1–4 years) |
| Goals | Hypertrophy, strength gains, progressive overload |
| Pain Points | Doesn't know when to rotate exercises, unsure about volume balance, hits plateaus without knowing why |
| Needs | AI plan adjustments every 4–8 weeks, workout logging during sessions, plateau detection |

### 2.2 Persona B — The Light-Weight / Bodyweight Trainee

| Attribute | Detail |
|-----------|--------|
| Profile | Often female, trains 3–5 days/week, beginner to intermediate, may prefer home workouts |
| Goals | Toning, functional strength, flexibility, general fitness |
| Pain Points | Intimidated by complex programs, wants guided routines, needs progression without heavy weights |
| Needs | Bodyweight/dumbbell/band plans, exercise progression levels (e.g., knee push-up → push-up → diamond push-up), home-friendly routines |

### 2.3 Persona C — The Hybrid Athlete

| Attribute | Detail |
|-----------|--------|
| Profile | Any gender, mixes strength and cardio, varied experience across modalities |
| Goals | Overall fitness, body recomposition, endurance + strength balance |
| Pain Points | Balancing cardio and lifting without overtraining, no unified plan, uses multiple apps |
| Needs | Integrated cardio + strength programming, fatigue management across modalities |

---

## 3. User Stories & Use Cases

### 3.1 Onboarding & Plan Generation

1. As a new user, I want to input my stats (height, weight, gender, age), training experience, available equipment, and goals so the AI generates a personalized starting plan.
2. As a bodyweight-only user, I want to specify my available equipment (e.g., "dumbbells + pull-up bar") so my plan excludes exercises I can't do.
3. As a hybrid athlete, I want to set dual goals (e.g., "5K improvement + muscle gain") so the AI balances both modalities.

### 3.2 Workout Logging (During Session)

4. As a user mid-workout, I want to quickly log each set (weight, reps, RPE) with minimal taps so tracking doesn't interrupt my session.
5. As a user, I want to see my previous session's numbers for each exercise while logging so I know what to beat.
6. As a cardio user, I want to log duration, distance, pace, and heart rate (via HealthKit or manual entry).
7. As a user, I want a built-in rest timer that auto-starts between sets with haptic feedback on completion.
8. As a user performing supersets, I want to log grouped exercises together with rest only after the full superset round.
9. As a user, I want to see warm-up sets auto-suggested before my working sets on compound lifts.
10. As a user, I want to be notified in real time when I hit a personal record during logging.

### 3.3 AI Review & Adjustment

11. As a user completing a training block, I want the AI to review my logged data and tell me what's progressing, what's stalling, and what to change — with clear reasoning.
12. As a user, I want to accept, modify, or reject each AI suggestion individually so I stay in control.
13. As a user who missed sessions, I want the AI to recognize the gap and adjust intensity accordingly.
14. As a user, I want to ask the AI free-form questions about my training ("Why did you change my squat day?") and get contextual answers.
15. As a user, I want to configure how often the AI reviews my training — after every session, weekly, end of block, or manual only.
16. As a user, I want each AI suggestion to include a confidence level so I can prioritize which ones to act on.
17. As a user showing signs of accumulated fatigue, I want the AI to proactively suggest a deload week with modified weights and volume.

### 3.4 Progress & Insights

18. As a user, I want charts showing strength progression (estimated 1RM), volume per muscle group, and cardio trends.
19. As a user, I want weekly/monthly AI-generated summaries highlighting achievements and focus areas.
20. As a user, I want a personal records board showing all-time and recent PRs across exercises.
21. As a user, I want to optionally track body measurements (waist, arms, chest, etc.) to monitor changes beyond bodyweight.
22. As a user, I want to see my current weekly volume per muscle group compared against recommended volume landmarks.

### 3.5 Templates & Flexibility

23. As a user, I want to save any workout as a reusable template so I can repeat it without AI involvement.
24. As a user, I want to start a workout from a saved template, from today's planned session, or as a blank ad-hoc session.
25. As a user, I want to optionally provide post-session feedback (sleep quality, energy, soreness) to give the AI richer context for reviews.

### 3.6 Configuration & Data

26. As a self-hoster, I want to configure my LLM provider (API key + model name) in a simple config file or settings UI.
27. As a developer, I want a plugin API so I can add new exercise types, AI prompt templates, or data import/export formats without modifying core code.
28. As a user, I want to export all my data as JSON or CSV at any time for backup or migration purposes.
29. As a user, I want the app to automatically back up my data and let me restore from a backup if needed.
30. As a user, I want to see my AI token usage and estimated cost so I understand what the AI features are costing me.

---

## 4. Architecture & Extensibility

### 4.1 High-Level Architecture

```
┌──────────────────────┐     ┌──────────────────┐
│   iOS App (SwiftUI)  │     │  Future Android   │
│   + Watch App        │     │  (Kotlin)         │
│   + HealthKit        │     │  + Health Connect  │
└──────────┬───────────┘     └────────┬──────────┘
           │         REST API         │
┌──────────▼──────────────────────────▼──────────┐
│              Backend API Server                 │
│              (Python / FastAPI)                  │
│                                                 │
│  ┌─────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ Workout │  │ AI Coach │  │ Plugin Engine  │  │
│  │ Logger  │  │ Service  │  │ (exercise libs,│  │
│  │         │  │          │  │  prompts,      │  │
│  │         │  │          │  │  import/export) │  │
│  └────┬────┘  └────┬─────┘  └───────────────┘  │
│       │            │                             │
│  ┌────▼────────────▼────────────────────────┐   │
│  │           LLM Adapter Layer              │   │
│  │  ┌─────────┐ ┌─────────┐ ┌───────────┐  │   │
│  │  │ OpenAI  │ │Anthropic│ │Ollama/Local│  │   │
│  │  └─────────┘ └─────────┘ └───────────┘  │   │
│  └──────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│              SQLite / PostgreSQL                  │
│   (user profiles, workout logs, plans, AI history)│
└─────────────────────────────────────────────────┘
```

**Design principle:** All business logic, AI integration, plan generation rules, volume calculations, and data validation live on the backend. The iOS app is a client — it handles UI, on-device logging/caching, HealthKit, and Watch integration. This ensures a future Android or web client can reuse the entire backend without duplicating logic.

### 4.2 Client-Server Sync Model

- The iOS app stores workout data locally (CoreData/SwiftData) as an offline cache
- When the device has network connectivity to the backend, data syncs automatically
- The user logs workouts at the gym on their phone (offline-capable), and data syncs to their self-hosted backend (e.g., Mac Mini at home) when they return to their network
- AI features require backend connectivity — requests are queued when offline and processed on sync
- Sync is conflict-free by design: workout sessions are append-only, plans are server-authoritative

### 4.3 LLM Adapter Layer

The AI engine communicates with LLMs through a unified adapter interface. Adding a new provider means implementing a single adapter class.

```
interface LLMAdapter {
  generatePlan(userProfile, trainingHistory, config) → Plan
  reviewBlock(blockData, config) → ReviewReport
  chat(messages, context, config) → Response
}
```

**Supported providers (MVP):**

| Provider | Model Examples | Notes |
|----------|---------------|-------|
| OpenAI | gpt-4o, gpt-4o-mini | API key required |
| Anthropic | claude-sonnet-4-20250514, claude-haiku-4-5-20251001 | API key required, prompt caching supported |
| Ollama (local) | llama3, mistral, gemma | No API key, runs on user hardware |
| OpenAI-compatible | Any endpoint matching the OpenAI API spec | Covers LM Studio, vLLM, Together, Groq, etc. |

**Configuration (config.yaml or .env):**

```yaml
ai:
  provider: "openai"           # openai | anthropic | ollama | openai-compatible
  model: "gpt-4o-mini"         # model name
  api_key: "${OPENAI_API_KEY}" # env var reference
  base_url: ""                 # override for openai-compatible endpoints
  temperature: 0.7
  max_tokens: 2000

  # Review frequency
  review_frequency: "block"    # session | weekly | block | manual
  review_block_weeks: 6        # block length in weeks (used when review_frequency is "block")

  # Cost management
  prompt_caching: true         # enable prompt caching where supported (e.g., Anthropic)

  # Prompt customization
  system_prompt_override: ""   # path to custom system prompt file (optional)
  review_prompt_override: ""   # path to custom review prompt file (optional)
```

### 4.4 AI Fallback Behavior

The app must handle AI failures gracefully without degrading the core logging experience:

| Failure Mode | Behavior |
|-------------|----------|
| **Malformed AI output** | Validate AI response against expected JSON schema. If validation fails, display the raw response in the chat view for the user to read, but do not auto-apply changes to the plan. Log the failure for debugging. |
| **API timeout or error** | Queue the request for retry. Show the user: "AI review queued — will process when connection is restored." For chat messages, show a retry button. |
| **No LLM configured** | All AI-specific UI elements (coach button, review cards, chat) are hidden entirely. The app functions as a full-featured manual logger with plan creation, templates, history, PRs, and progress charts. |
| **Dangerous suggestion detected** | Rule-based guardrails reject suggestions exceeding safe thresholds (e.g., >10% weekly volume jump, weights beyond reasonable multipliers for experience level). Rejected suggestions are logged with the reason and shown to the user with an explanation of why they were blocked. |

### 4.5 AI Prompt Versioning

Prompt templates are versioned independently from the application, allowing fast iteration on AI quality without code changes or releases.

```
prompts/
├── manifest.json              # maps prompt types to active versions
├── plan_generation/
│   ├── v1.md                  # initial plan generation prompt
│   ├── v2.md                  # improved version
│   └── v2_llama.md            # variant tuned for local Llama models
├── block_review/
│   ├── v1.md
│   └── v2.md
├── session_review/
│   └── v1.md
└── chat/
    └── v1.md
```

**manifest.json example:**

```json
{
  "plan_generation": { "default": "v2", "ollama": "v2_llama" },
  "block_review": { "default": "v2" },
  "session_review": { "default": "v1" },
  "chat": { "default": "v1" }
}
```

Users can pin a specific version in their config or use `"latest"`. Custom prompt overrides (§4.3 config) take precedence over versioned prompts.

### 4.6 Plugin System

Plugins are self-contained modules that register with the core via a manifest file.

```
plugins/
├── exercise-yoga/
│   ├── manifest.json          # name, version, type, hooks
│   ├── exercises.json         # exercise definitions
│   └── prompts/               # AI prompt templates for this modality
├── import-strong-app/
│   ├── manifest.json
│   └── importer.js            # converts Strong app CSV to FlexLoop format
└── wearable-garmin/
    ├── manifest.json
    └── sync.js                # Garmin Connect data sync
```

**Plugin types:**

| Type | Purpose | Example |
|------|---------|---------|
| `exercise-library` | Add new exercises, modalities, or progression schemes | Yoga poses, calisthenics progressions, powerlifting peaking programs |
| `import-export` | Data migration from/to other apps | Import from Strong, Hevy, Fitbod; export to CSV/JSON |
| `ai-prompt` | Custom AI prompt templates for specialized use cases | Powerlifting peaking review, marathon training periodization |
| `integration` | Connect external services or devices | Wearable sync, nutrition API |

### 4.7 Database Schema (Core Tables)

```sql
-- User profile (single user for MVP, multi-profile in future versions)
users (id, name, gender, age, height_cm, weight_kg, experience_level,
       goals, available_equipment[], created_at)

-- Training plans generated by AI or manually created
plans (id, user_id, name, split_type, block_start, block_end,
       status, ai_generated, created_at)

plan_days (id, plan_id, day_number, label, focus)

-- Exercise groups support supersets, circuits, tri-sets, etc.
exercise_groups (id, plan_day_id, group_type, order, rest_after_group_sec)
-- group_type: straight | superset | triset | circuit | drop_set

plan_exercises (id, plan_day_id, exercise_group_id, exercise_id, order,
                sets, reps, weight, rpe_target, notes)

-- Exercise library (core + plugins)
exercises (id, name, muscle_group, equipment, category,
           difficulty, source_plugin, metadata_json)

-- Volume landmarks reference data
volume_landmarks (id, muscle_group, experience_level,
                  mv_sets, mev_sets, mav_sets, mrv_sets)

-- Workout logs (the core data asset)
workout_sessions (id, user_id, plan_day_id, template_id, source,
                  started_at, completed_at, notes)
-- source: plan | template | ad_hoc

workout_sets (id, session_id, exercise_id, exercise_group_id,
              set_number, set_type, weight, reps, rpe,
              duration_sec, distance_m, rest_sec)
-- set_type: warm_up | working | drop | amrap | backoff

-- Optional post-session feedback (disabled by default)
session_feedback (id, session_id, sleep_quality, energy_level,
                  muscle_soreness_json, session_difficulty,
                  stress_level, created_at)

-- Personal records (precomputed for fast lookups during logging)
personal_records (id, user_id, exercise_id, pr_type, value,
                  session_id, achieved_at)
-- pr_type: estimated_1rm | volume | rep_at_weight | duration | distance

-- Workout templates (saved routines)
templates (id, user_id, name, exercises_json, created_at)

-- Body measurements (optional tracking)
measurements (id, user_id, date, type, value_cm, notes)
-- type: waist | hips | chest | shoulders | bicep_l | bicep_r | thigh_l | thigh_r | calves_l | calves_r | body_fat_pct

-- AI interaction history
ai_reviews (id, user_id, plan_id, review_type, input_summary,
            output_json, suggestions_json, accepted_json,
            model_used, input_tokens, output_tokens, estimated_cost,
            created_at)

ai_chat_messages (id, user_id, role, content, context_json,
                  input_tokens, output_tokens, created_at)

-- AI token usage tracking
ai_usage (id, user_id, month, total_input_tokens, total_output_tokens,
          estimated_cost, call_count)

-- Notifications
notifications (id, user_id, type, title, body, read,
               action_url, created_at)

-- Backup metadata
backups (id, filename, size_bytes, created_at, schema_version)
```

### 4.8 REST API (Core Endpoints)

```
Profiles
  POST   /api/profiles              — create user profile
  GET    /api/profiles/:id          — get profile
  PUT    /api/profiles/:id          — update profile

Plans
  POST   /api/plans/generate        — trigger AI plan generation
  GET    /api/plans/:id             — get plan with days and exercises
  PUT    /api/plans/:id             — manually edit plan
  GET    /api/users/:id/plans       — list user's plans

Workouts
  POST   /api/workouts              — start a new session
  PUT    /api/workouts/:id          — update session (add sets, complete)
  GET    /api/workouts/:id          — get session detail
  GET    /api/users/:id/workouts    — list sessions (with date filters)
  POST   /api/workouts/:id/feedback — submit optional post-session feedback

Templates
  POST   /api/templates             — save a workout as template
  GET    /api/templates             — list user's templates
  GET    /api/templates/:id         — get template detail
  PUT    /api/templates/:id         — edit template
  DELETE /api/templates/:id         — delete template

Exercises
  GET    /api/exercises             — list/search exercise library
  GET    /api/exercises/:id         — exercise detail

Personal Records
  GET    /api/users/:id/prs         — get all PRs (filterable by exercise, type, time range)
  GET    /api/exercises/:id/prs     — get PRs for a specific exercise

Measurements
  POST   /api/measurements          — log a measurement
  GET    /api/users/:id/measurements — get measurement history (filterable by type, date range)

AI
  POST   /api/ai/review             — trigger a block review
  POST   /api/ai/chat               — send a chat message
  GET    /api/ai/reviews/:id        — get a review with suggestions
  PUT    /api/ai/suggestions/:id    — accept/reject a suggestion
  GET    /api/ai/usage              — get token usage and cost summary

Data
  GET    /api/export                — full data export (JSON or CSV)
  GET    /api/export/session/:id    — single session export
  POST   /api/backup                — trigger manual backup
  GET    /api/backups               — list available backups
  POST   /api/restore/:backup_id   — restore from backup

Sync
  POST   /api/sync                  — client pushes offline data, receives updates
```

---

## 5. Feature Requirements

### 5.1 Priority Matrix

| Priority | Feature | Persona | Phase |
|----------|---------|---------|-------|
| **P0** | Workout logging (sets, reps, weight, RPE) | A, B, C | MVP |
| **P0** | Superset / circuit / drop set support in logging | A, B, C | MVP |
| **P0** | AI plan generation from onboarding profile | A, B, C | MVP |
| **P0** | Rest timer between sets (with haptic feedback) | A, B, C | MVP |
| **P0** | Training history & session log | A, B, C | MVP |
| **P0** | AI periodic review & plan adjustment | A, B, C | MVP |
| **P0** | Configurable AI review frequency (per-session, weekly, block, manual) | All | MVP |
| **P0** | Configurable LLM backend | All | MVP |
| **P0** | Data export (JSON/CSV) | All | MVP |
| **P0** | AI fallback behavior (graceful degradation) | All | MVP |
| **P0** | Automated daily backups with restore flow | All | MVP |
| **P0** | HealthKit integration (heart rate, workouts) | A, B, C | MVP |
| **P0** | Apple Watch companion app | A, B, C | MVP |
| **P1** | Personal records board with real-time detection | A, B, C | v1.1 |
| **P1** | Workout templates / favorites | A, B, C | v1.1 |
| **P1** | Warm-up set generator for compound lifts | A, C | v1.1 |
| **P1** | Deload week automation (scheduled + reactive) | A, C | v1.1 |
| **P1** | Volume landmarks per muscle group (guardrails) | A, C | v1.1 |
| **P1** | AI confidence scoring on suggestions | All | v1.1 |
| **P1** | AI cost tracking dashboard (tokens, estimated spend) | All | v1.1 |
| **P1** | Cardio session logging (duration, distance, pace, HR) | C | v1.1 |
| **P1** | Bodyweight / light-weight exercise library + progressions | B | v1.1 |
| **P1** | Progress charts (1RM trends, volume, cardio) | A, B, C | v1.1 |
| **P1** | Plugin system (exercise libraries, import/export) | Devs | v1.1 |
| **P1** | Optional post-session feedback (sleep, energy, soreness) | All | v1.1 |
| **P1** | Optional body measurements tracking | B, C | v1.1 |
| **P2** | Exercise demonstration animations | B | v1.2 |
| **P2** | Prompt caching optimization (Anthropic, OpenAI) | All | v1.2 |
| **P2** | AI prompt evaluation framework | Devs | v1.2 |
| **P2** | Localization framework (i18n) | All | v1.2 |
| **P3** | AI form check via phone camera | A, B | Future |
| **P3** | Multi-profile support with authentication | All | Future |
| **P3** | Rate limiting / budget caps for AI usage | All | Future |

### 5.2 Workout Logging (Must-Have)

- Quick-entry UI: pre-filled with planned exercise, weight, and reps from the current plan. User taps to confirm or edits inline.
- RPE (Rate of Perceived Exertion) slider (1–10) per set, optional but encouraged.
- Previous session overlay: last session's numbers displayed next to input fields.
- Swipe to add/remove sets. Long-press to substitute an exercise (with AI-suggested alternatives if LLM is configured).
- Auto-rest timer starts on set completion with haptic feedback when rest period ends. Configurable per exercise type (default: 90s compound, 60s isolation). In supersets, rest timer starts after the full group, not individual exercises.
- Supports kg/lbs toggle globally and per-exercise override.
- **Superset / circuit support**: exercises can be grouped as supersets (2 exercises), tri-sets (3), giant sets (4+), or circuits (5+). The logging UI guides the user through the rotation and adjusts rest timer behavior accordingly.
- **Set types**: each logged set has a type — warm-up, working, drop, AMRAP, backoff. Warm-up sets are visually distinct and optional to log.
- **Real-time PR detection**: when a set is logged that beats the user's previous best (estimated 1RM, rep PR at weight, volume PR), the app immediately displays a PR notification with haptic celebration.
- **Offline-capable**: all logging works without network. Data syncs to the backend when connectivity is available.

### 5.3 AI Plan Generation

- Onboarding collects: gender, age, height, weight, experience level, goals, days per week, available equipment, injuries/limitations.
- AI generates a full weekly plan with exercises, sets, reps, and suggested starting weights (based on bodyweight heuristics and experience).
- Plan variants: PPL, Upper/Lower, Full Body, Bro Split, Custom. AI recommends a split based on available days.
- Plans can include supersets and circuits where appropriate (e.g., superset accessory work for time efficiency).
- For bodyweight users: plans use progression levels rather than weight increments.
- AI uses volume landmarks as constraints — generated plans should keep volume within MEV–MRV range per muscle group for the user's experience level.
- **Deload scheduling**: AI-generated plans include a scheduled deload week (default: every 4th–7th week depending on experience level and training intensity).
- **Prompt templates are version-controlled and editable** — advanced users can customize how the AI generates plans.

### 5.4 AI Periodic Review & Adjustment

- **Configurable review frequency**: users choose when the AI reviews their training:
  - **After every session** — brief feedback on the session, one actionable insight. Best for beginners.
  - **Weekly** — summary of the past week's sessions with volume and progression analysis.
  - **End of block** (default) — full analysis at the end of each training block (configurable, default 6–8 weeks).
  - **Manual only** — AI never reviews automatically; user triggers on demand.
- AI analyzes: progression rate per exercise, volume per muscle group vs. volume landmarks, RPE trends, missed sessions, session duration trends, and session feedback data (if provided by user).
- Output: a structured review card showing what's working, what's stalling, and specific recommendations.
- **Each recommendation includes a confidence level** (high / medium / low) based on how much logged data supports it, with a brief explanation of the confidence rating.
- Each recommendation is explainable (e.g., "Your bench press hasn't increased in 3 weeks despite RPE consistently at 9+. Suggestion: deload to 80% for one week, then resume. Confidence: High — 4 weeks of consistent data.").
- User can accept, modify, or reject each suggestion independently.
- **Reactive deload detection**: independent of scheduled deloads, the AI monitors for fatigue signals (RPE trending up with flat/declining performance, declining session feedback scores) and proactively suggests a deload when multiple signals converge.
- **All AI inputs and outputs are logged** for transparency and debugging, including token counts and estimated cost per call.

### 5.5 Warm-Up Set Generator (v1.1)

- For compound lifts, auto-suggest ramping warm-up sets based on the planned working weight (e.g., 40%, 60%, 80% of working weight with decreasing reps).
- Warm-up sets appear above working sets in the logging UI, visually distinct (grayed out). Loggable but skippable with one tap.
- Warm-up rest timer uses shorter durations than working set rest.
- Configurable: users can adjust the number of warm-up steps or disable per exercise.
- For bodyweight exercises: suggest movement-prep alternatives (e.g., wall push-ups before push-ups).
- Rule-based, no LLM required — works offline with zero API cost.

### 5.6 Cardio Support (v1.1)

- Supported types: running, cycling, swimming, rowing, elliptical, HIIT, walking.
- Logging fields: duration, distance, average pace/speed, heart rate (via HealthKit or manual entry), perceived effort.
- AI integrates cardio load into overall fatigue model when reviewing training blocks.
- Cardio plan generation: zone-based training plans (Zone 2 base, intervals, tempo) aligned with user goals.

### 5.7 Post-Session Feedback (v1.1, Optional)

- **Disabled by default.** Users opt in via Settings > Workout > "Ask for session feedback."
- When enabled, a dismissable card appears after completing a session with quick-tap inputs:
  - Sleep quality (1–5)
  - Energy level (1–5)
  - Muscle soreness (body region selector)
  - Session difficulty (1–5)
  - Stress level (1–5)
- All fields are optional. A single "Skip" button dismisses the entire card. Defaults to middle values for one-tap submission.
- When feedback data exists, the AI factors it into reviews. When it doesn't, the AI works with set/rep/RPE data only — no degraded experience.
- The AI can correlate performance dips with poor sleep/energy patterns and distinguish programming issues from recovery issues.

### 5.8 Body Measurements (v1.1, Optional)

- Optionally track: waist, hips, chest, shoulders, biceps (L/R), thighs (L/R), calves (L/R), body fat percentage.
- Reminder every 2–4 weeks (configurable, dismissable, non-blocking).
- Line charts per measurement over time in the Progress screen.
- AI correlates body changes with training data in reviews (e.g., "weight stable but waist decreased — likely recomposition").
- Progress photos: optional, stored locally on-device only, grid view with side-by-side comparison. Never synced to the backend (privacy).

---

## 6. Information Architecture

### 6.1 Core Screens

| Screen | Purpose & Key Elements |
|--------|----------------------|
| **Home / Dashboard** | Today's workout, quick-start button (plan / template / ad-hoc), weekly streak, AI insight card (if LLM configured), upcoming sessions, recent PR highlights |
| **Active Workout** | Exercise list with group indicators (superset/circuit), set logging interface with set type tags, rest timer with haptics, RPE input, previous session overlay, warm-up sets (v1.1), real-time PR detection, swap exercise |
| **My Plan** | Full weekly view, tap to edit, drag to reorder, manual add/remove exercises, deload weeks marked visually, volume per muscle group summary |
| **AI Coach** | Chat interface for questions, review cards with confidence levels and accept/reject, block summary reports, review frequency setting. Entirely hidden if no LLM configured. |
| **Progress** | Charts: estimated 1RM, volume per muscle group vs. landmarks, bodyweight trend, cardio trends. PR board (all-time + recent). Body measurements charts (if opted in). |
| **History** | Calendar view of sessions. Tap any date for full log. Filter by exercise or muscle group. Session source indicator (plan / template / ad-hoc). |
| **Exercise Library** | Searchable database with muscle targets, equipment, difficulty. Extensible via plugins. |
| **Templates** | Saved workout routines. Create from completed session or manually. Start workout from template. |
| **Settings** | Profile management, LLM configuration (provider, model, review frequency), notification preferences, unit preferences, data export, backup/restore, plugin management, session feedback toggle, measurement reminders |

### 6.2 Navigation

```
Tab Bar:
  [Home]  [Workout]  [Plan]  [Progress]  [Settings]

AI Coach accessible via:
  - Floating action button on Home
  - Dedicated section in Settings > AI Configuration
  - Context menu during workout ("Ask AI about this exercise")

Templates accessible via:
  - Workout tab > "Start from Template"
  - History > any session > "Save as Template"
```

### 6.3 Apple Watch App

| Screen | Purpose |
|--------|---------|
| **Today's Workout** | Glanceable view of planned exercises and sets |
| **Active Logging** | Quick set confirmation (weight/reps pre-filled from plan), digital crown for weight adjustment |
| **Rest Timer** | Countdown with haptic tap on completion |
| **Heart Rate** | Live heart rate from Watch sensors, synced to session via HealthKit |
| **Complications** | Next workout, weekly streak, rest timer countdown |

### 6.4 Notifications

Notifications are delivered via iOS local notifications and Apple Watch mirroring:

| Notification | Default |
|-------------|---------|
| AI review ready | On |
| PR achieved | On |
| Deload suggestion | On |
| Workout reminder (scheduled sessions) | Off |
| Missed session nudge | Off |
| Measurement reminder | Off (only if measurements opted in) |

All notifications are individually toggleable in Settings. The app should never feel like it's guilt-tripping the user — default to quiet, celebrate achievements, inform about AI results.

---

## 7. Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| **Performance** | Workout logging screen loads < 300ms. Set input responds < 100ms. PR detection < 50ms. AI generation < 15s (varies by provider). |
| **Offline** | Full workout logging offline on-device. Plan and templates viewable offline. AI features require backend connectivity. Queue AI requests when offline, process on sync. |
| **Platforms** | MVP: Native iOS app (SwiftUI, iOS 17+) with Apple Watch companion (watchOS 10+). Backend API server deployable via Docker. |
| **Deployment** | Single `docker-compose up` for backend. iOS app distributed via TestFlight (beta) and App Store (release). |
| **Data Privacy** | All data stored on-device and user-controlled backend. No telemetry. No external calls except user-configured LLM API. Progress photos stored on-device only, never synced. Data exportable as JSON/CSV at any time. |
| **Accessibility** | iOS Dynamic Type support. VoiceOver compatible. Minimum 44pt touch targets. High contrast support. |
| **Extensibility** | Plugin API documented. Core module boundaries enforced. Contribution guide with PR templates and coding standards. |
| **Testing** | Unit tests for core logic (plan generation rules, 1RM calculations, set validation, PR detection, volume landmark checks). Integration tests for LLM adapters. UI tests for critical logging flows. |
| **Backup** | Automated daily backup of database. Retain last 7 daily + 4 weekly backups. Auto-backup before schema migrations. Restore via Settings UI or CLI. |
| **Migration** | Schema changes ship as numbered migration files via ORM. Auto-migrate on backend startup. Backup created before each migration. Down migrations supported for rollback. App refuses to start if database is from a newer version. |

---

## 8. Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| iOS App | Swift / SwiftUI (iOS 17+) | Native performance, full HealthKit/Watch access, best in-session UX |
| Watch App | SwiftUI + WatchKit (watchOS 10+) | Native Watch experience, complications, haptics |
| Health Data | HealthKit | Heart rate, workout sessions, step data, sleep (for session feedback correlation) |
| Backend | Python (FastAPI) | Rich AI/LLM ecosystem, Pydantic for AI output validation, auto-generated OpenAPI docs, large contributor pool for AI features |
| Database | SQLite (default) / PostgreSQL (optional) | SQLite = zero-config for personal use. Postgres for future multi-user. |
| ORM | SQLAlchemy + Alembic | Mature, battle-tested, migration-friendly with Alembic, excellent Python ecosystem support |
| Validation | Pydantic | Type-safe request/response models, AI output schema validation, built into FastAPI |
| AI Layer | Custom adapter pattern (see §4.3) | Provider-agnostic, testable, swappable |
| Containerization | Docker + docker-compose | One-command backend deployment |
| CI/CD | GitHub Actions + Xcode Cloud | GitHub Actions for backend. Xcode Cloud for iOS builds and TestFlight distribution. |
| Documentation | Markdown in-repo + Docusaurus or VitePress | Low friction for contributors |

---

## 9. MVP Scope & Roadmap

### 9.1 MVP (v1.0) — Target: 12–14 weeks

Core experience for the self-coached lifter — native iOS app with self-hosted backend:

1. Native iOS app (SwiftUI) with Apple Watch companion
2. Onboarding questionnaire and AI plan generation (strength training focus)
3. Workout logging with set/rep/weight/RPE tracking, set types, and superset/circuit support
4. Rest timer with haptic feedback (iPhone + Watch)
5. HealthKit integration (heart rate, workout sessions)
6. Training history (session log, calendar view)
7. AI periodic review at end of block with adjustment suggestions and confidence scoring
8. Configurable AI review frequency (per-session, weekly, block, manual)
9. AI chat for training questions
10. Basic exercise library (~80 exercises, community-expandable)
11. LLM adapter layer with OpenAI, Anthropic, and Ollama support
12. AI fallback behavior (graceful degradation for all failure modes)
13. Data export (JSON/CSV)
14. Automated daily backups with restore flow
15. Docker-based backend deployment (`docker-compose up`)
16. TestFlight distribution for iOS app

### 9.2 v1.1 — Target: +6 weeks

- Personal records board with real-time detection during logging
- Workout templates / favorites (save, browse, start from template)
- Warm-up set generator for compound lifts
- Deload week automation (scheduled in plan generation + reactive fatigue detection)
- Volume landmarks per muscle group (AI guardrails + visual display in Progress)
- AI cost tracking dashboard (token usage, estimated spend per month)
- Optional post-session feedback (sleep, energy, soreness — disabled by default)
- Optional body measurements tracking
- Bodyweight/light-weight exercise library with progression levels
- Cardio session logging and AI-integrated cardio plans
- Progress charts (1RM trends, volume per muscle group vs. landmarks, cardio trends)
- Plugin system v1 (exercise libraries, import/export)
- Data import from Strong, Hevy (community-contributed plugins)

### 9.3 v1.2 — Target: +6 weeks

- Exercise demonstration animations (open-licensed or community-contributed)
- Prompt caching optimization for Anthropic and OpenAI (reduce API costs)
- AI prompt evaluation framework (test profiles, expected output criteria, automated scoring)
- Improved AI prompt templates based on community feedback and eval results
- Localization framework (i18n) with community translations

### 9.4 Future Ideas (Community-Driven)

- Android app (Kotlin) consuming the same backend API
- Web dashboard for reviewing progress on desktop
- Multi-profile support with proper JWT authentication
- AI form check via phone camera (on-device model)
- Nutrition tracking integration
- Training plan sharing (export/import plan templates)
- Community exercise library with upvoting
- Rate limiting / budget caps for AI usage
- Garmin Connect sync plugin

---

## 10. Success Metrics

Since this is an open-source personal project, success is measured differently than a commercial product:

| Metric | Target (6 months post-launch) |
|--------|-------------------------------|
| GitHub stars | 500+ |
| Active contributors | 10+ |
| Community plugins published | 5+ |
| TestFlight beta testers | 200+ |
| Personal usage — sessions logged per week | 4+ (dogfooding) |
| AI review acceptance rate | > 60% suggestions accepted |
| Open issues resolution time (median) | < 2 weeks |
| Documentation coverage | All public APIs documented |
| AI prompt eval pass rate | > 80% of test profiles produce valid output |

---

## 11. Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| AI gives bad training advice → injury | High | Conservative defaults in prompt templates. Mandatory disclaimers in UI. Rule-based guardrails: never exceed volume landmarks (MRV), never recommend >10% weekly volume jumps, validate against exercise database. All suggestions require user approval. |
| AI hallucination / nonsensical exercises | High | Validate AI output against exercise database and expected JSON schema. Reject malformed responses and suggestions referencing unknown exercises. Display raw response in chat view when validation fails. Log all AI outputs for debugging. |
| Unexpected AI API costs | Medium | Token usage tracking on every call. Pre-call warning for unusually large requests. Cost dashboard showing monthly spend. Configurable review frequency to control call volume. Prompt caching to reduce costs (v1.2). |
| LLM provider API changes break adapters | Medium | Abstract via adapter interface. Pin API versions. Community can submit fixes quickly in OSS model. |
| Low contributor engagement | Medium | Clear CONTRIBUTING.md, good-first-issue labels, plugin system lowers barrier to entry, responsive maintainership. AI prompt eval framework (v1.2) gives contributors clear quality targets. |
| Scope creep in MVP | Medium | Strict P0-only for v1.0. Feature requests go to GitHub Discussions, not issue tracker. |
| Local Ollama models produce lower-quality plans | Low | Document recommended models and minimum specs. Provide quality benchmarks for different models. Default prompts tuned for smaller models. AI confidence scoring helps users assess output quality. |
| Data loss from SQLite corruption | Low | Automated daily backups with retention policy. Backup before schema migrations. JSON export as manual backup. Restore flow in Settings UI and CLI. Clear recovery docs. |
| iOS-only limits initial audience | Low | Backend API is platform-agnostic — designed for future Android/web clients. All business logic on the server. Schema includes user_id on all tables for future multi-profile support. |
| Offline sync conflicts | Low | Workout sessions are append-only (no conflict). Plans are server-authoritative — client fetches latest on sync. Conflict-free by design. |

---

## 12. Resolved Questions

All major architectural decisions have been made:

| Question | Decision | Rationale |
|----------|----------|-----------|
| **Frontend framework** | Native iOS with SwiftUI | HealthKit and Apple Watch support are must-haves; native provides the best in-session logging experience |
| **Mobile strategy** | iOS-first (Swift/SwiftUI) | Android (Kotlin) is a future community goal, consuming the same backend API |
| **Backend language** | Python (FastAPI) | Richest LLM/AI ecosystem, Pydantic for AI output validation, auto-generated OpenAPI docs for contributors |
| **Repo structure** | Two repos: `flexloop-server` (Python) + `flexloop-ios` (Swift) | Different languages/toolchains warrant separation; API contract via auto-generated OpenAPI spec bridges them |
| **Sync protocol** | REST polling for MVP | Simple, reliable, no WebSocket infrastructure needed. App syncs on launch, workout completion, and pull-to-refresh. WebSocket can be added later if UX demands it. |
| **AI prompt versioning** | Independent from app releases | Prompts live in `prompts/` directory with versioned files and a `manifest.json`. Contributors can iterate on prompt quality without code changes. Users can pin versions or use latest. |
| **Exercise library source** | Curate from wger.de (open-licensed) + manual review | Use wger data for names, muscle groups, and equipment tags. Write original descriptions. Community expands via plugin system. |
| **Multi-user auth** | Single user for MVP, no auth | Multi-profile with JWT authentication is a future feature. Schema uses `user_id` throughout to enable this without migration pain. |

---

## 13. Contributing

FlexLoop welcomes contributions of all kinds. See `CONTRIBUTING.md` for full guidelines.

**Quick start for contributors:**

```bash
# Backend (flexloop-server)
git clone https://github.com/flexloop/flexloop-server.git
cd flexloop-server
cp .env.example .env          # configure your LLM provider
docker-compose up -d           # start the backend (FastAPI + SQLite)
# API docs available at http://localhost:8000/docs (auto-generated by FastAPI)

# iOS App (flexloop-ios)
git clone https://github.com/flexloop/flexloop-ios.git
open FlexLoop.xcodeproj        # open in Xcode
# Set your backend URL in the app's configuration
# Build and run on simulator or device
```

**Areas where help is needed:**

- Exercise library expansion (especially bodyweight, yoga, and sport-specific exercises)
- AI prompt tuning and evaluation for different LLM providers
- Import plugins for popular fitness apps (Strong, Hevy, Fitbod, Garmin)
- Watch app complications and workout UI
- Backend API development and testing
- Android client development (Kotlin)
- Translations and localization
- Documentation and tutorials

---

*This is a living document. For the latest version, see the repo wiki or `docs/PRD.md`.*
