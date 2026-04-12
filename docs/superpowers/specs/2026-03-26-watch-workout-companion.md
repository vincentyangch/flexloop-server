# Watch Workout Companion — Design Spec

## Overview

Transform the Watch app from a static plan viewer into a live workout companion with bidirectional real-time sync. The iPhone is the source of truth. The Watch acts as a lightweight input device for logging sets during a workout.

## Requirements

1. When a workout starts on iPhone, the Watch app receives the workout state (best-effort wake via `sendMessage` + `applicationContext` fallback)
2. Watch displays a simplified guided workout: current exercise, weight/reps/RPE, set completion
3. Changes on either device sync to the other instantly via WCSession messages
4. Watch can edit weight (Digital Crown), reps (+/- buttons), RPE (+/- buttons)
5. No need to edit already-completed sets on Watch (use iPhone for that)
6. iPhone continues to work independently if Watch is unavailable

## Architecture

### Approach: WCSession Messages (request/response)

Both apps are active during a workout. The iPhone sends full state snapshots; the Watch sends individual actions. No offline queue, no conflict resolution, no event sourcing.

If a message is lost, the next `stateUpdate` or `requestState` corrects everything.

### iPhone is Source of Truth

`GuidedWorkoutViewModel` remains the single authoritative state. `PhoneConnectivityManager` is a transport layer that serializes/deserializes state and routes Watch actions to the ViewModel.

## Message Protocol

Each message is a `[String: Any]` dictionary: `["type": String, "payload": Data]`. The `payload` is a `Codable` struct encoded via `JSONEncoder` with `.secondsSince1970` date encoding strategy, placed into the dictionary as `Data`.

### iPhone to Watch

| Type | Payload | When |
|------|---------|------|
| `workoutStarted` | `WorkoutSyncState` | "Start Workout" tapped |
| `stateUpdate` | `WorkoutSyncState` | After any state change (set completed, edited, skipped, rest timer) |
| `workoutEnded` | `{reason: "finished" \| "cancelled"}` | Workout finishes or is cancelled |

### Watch to iPhone

Watch-to-iPhone messages use `sendMessage(_:replyHandler:errorHandler:)`. The iPhone implements `session(_:didReceiveMessage:replyHandler:)` and returns the `stateUpdate` payload in the reply. This ensures the Watch gets confirmation in a single round-trip.

| Type | Payload | Reply |
|------|---------|-------|
| `completeSet` | `{exerciseIndex, setNumber, weightKg, reps, rpe}` | `stateUpdate` |
| `requestState` | (empty) | `stateUpdate` (or `{type: "noActiveWorkout"}`) |

`completeSet` always uses `.working` set type. Warmup/other set types are not supported on Watch.

## Shared Data Models

Defined in a shared Swift file added to both iPhone and Watch targets. All structs are immutable value types — a new instance is created for each state update (never mutated in place).

```swift
struct WorkoutSyncState: Codable {
    let isActive: Bool
    let currentExerciseIndex: Int
    let exercises: [SyncExercise]
    let restTimerRemaining: Int?  // nil = not active
    let startedAt: Date
}

struct SyncExercise: Codable {
    let exerciseId: Int
    let name: String
    let isSkipped: Bool
    let restSeconds: Int          // rest duration after each set
    let targets: [SyncSetTarget]
    let completedSets: [SyncCompletedSet]
}

struct SyncSetTarget: Codable {
    let setNumber: Int
    let weightKg: Double?
    let reps: Int
    let rpe: Double?
}

struct SyncCompletedSet: Codable {
    let setNumber: Int
    let weightKg: Double?
    let reps: Int?
    let rpe: Double?
}
```

These replace the existing `WatchPlanData`, `WatchDayData`, and `WatchExerciseData` models.

## iPhone Side Changes

### PhoneConnectivityManager (rewrite)

- `sendWorkoutStarted(state: WorkoutSyncState)` — serialize and send via `sendMessage`; also set `updateApplicationContext` as fallback for when Watch is not immediately reachable
- `sendStateUpdate(state: WorkoutSyncState)` — send current state snapshot via `sendMessage`
- `sendWorkoutEnded(reason: String)` — notify Watch workout is over
- Implement `session(_:didReceiveMessage:replyHandler:)`:
  - `completeSet`: call into `GuidedWorkoutViewModel.completeSet()`, then reply with `stateUpdate`
  - `requestState`: reply with current state if workout is active, or `{type: "noActiveWorkout"}`

### GuidedWorkoutViewModel

- Add `name: String` field to `GuidedExercise` struct. Populate it in `loadFromPlanDay` using the `exerciseNames` dictionary already passed as a parameter.
- Add `restSeconds: Int` field to `GuidedExercise` struct. Populate from exercise group's `restAfterGroupSec`.
- Add `stateSnapshot() -> WorkoutSyncState` method that serializes current ViewModel state including exercise names and rest seconds.
- After any state mutation (completeSet, editCompletedSet, skipExercise, rest timer start/stop), call `PhoneConnectivityManager.shared.sendStateUpdate()`.

### GuidedWorkoutView

- No changes needed. Sync is handled transparently by the ViewModel.

### HomeViewModel

- Remove `syncPlanToWatch()` added during smoke testing. Watch now gets data when workout starts, not on home load.

## Watch Side Changes

### WatchSessionManager (rewrite)

- `@Published var workoutState: WorkoutSyncState?` — replaces `todayPlan`/`planName`
- Handle `workoutStarted`/`stateUpdate`: decode `WorkoutSyncState`, update published property
- Handle `workoutEnded`: set `workoutState = nil`
- `sendCompleteSet(exerciseIndex:, setNumber:, weightKg:, reps:, rpe:, replyHandler:)` — send action to iPhone via `sendMessage` with `replyHandler`, update `workoutState` from reply
- `requestState()` — ask iPhone for current state (called on app appear)
- Start `HKWorkoutSession` on Watch when `workoutStarted` is received (keeps app in foreground, shows green workout indicator on watch face)
- End `HKWorkoutSession` when `workoutEnded` is received

### WatchHomeView (simplify)

- If `workoutState != nil` and `isActive`: show exercise name, progress, and "Continue" button navigating to `WatchWorkoutView`
- If no active workout: show "No active workout — Start from iPhone"
- On appear: call `requestState()` to check if iPhone has an active workout

### WatchWorkoutView (rewrite)

State-driven from `workoutState`, not local arrays. The Watch always follows the iPhone's `currentExerciseIndex` — it does not maintain its own navigation position.

**Layout:**
```
    Barbell Back Squat
      Set 1 of 3

   [ 25.0 kg ]      ← Digital Crown, 2.5 kg / 5 lbs steps

   [-]  8 reps  [+]  ← tap buttons, integer
   [-] 7.0 RPE  [+]  ← tap buttons, 0.5 steps

      [checkmark]  [X]
    2 sets done
```

**Behavior:**
- Weight: Digital Crown rotation, 2.5 kg or 5 lbs increments (based on unit preference), range 0-500
- Reps: +/- buttons, integer, range 1-99
- RPE: +/- buttons, 0.5 steps, range 1-10. Pre-filled from `SyncSetTarget.rpe`. If target RPE is nil, default to 7.0.
- Checkmark: sends `completeSet` to iPhone via `replyHandler`, updates state from reply
- X button: dismisses workout on Watch only (iPhone continues)
- Rest timer: starts locally after set completion using `SyncExercise.restSeconds`
- Auto-advances to next exercise when state update arrives with updated `currentExerciseIndex`

### WatchRestTimerView

Keep as-is. Works well.

### Remove Old Models

Delete `WatchExerciseData`, `WatchDayData`, `WatchPlanData` from both `WatchSessionManager.swift` and `WatchConnectivityManager.swift`.

## HKWorkoutSession (Watch Side)

`HKWorkoutSession` runs on **watchOS only** (there is no iPhone-side HKWorkoutSession API). It cannot be used to wake the Watch app from iPhone.

**Watch wake strategy:**
1. iPhone sends `workoutStarted` via `sendMessage` (best-effort — works if Watch app is reachable)
2. iPhone also sets `updateApplicationContext` with the workout state (guaranteed delivery when Watch app next opens)
3. When Watch app opens (whether from message wake or user manually opening), it sends `requestState` to get current data

**Watch side HKWorkoutSession:**
- Start an `HKWorkoutSession` when `workoutStarted` is received. This keeps the Watch app in the foreground and shows the green workout indicator on the watch face.
- End the session when `workoutEnded` is received. This also saves the workout to HealthKit on the Watch side.
- The existing `HealthKitManager.shared.saveWorkout()` call on iPhone at workout finish is kept — both devices record the workout independently.

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Watch app opened mid-workout | Sends `requestState`, iPhone replies with current state |
| Watch not reachable when workout starts | `sendMessage` fails silently; `applicationContext` queues state for next open |
| Watch unreachable mid-workout | iPhone continues normally, messages fail silently |
| Watch reconnects mid-workout | On appear, sends `requestState`, re-syncs |
| Workout ends while Watch showing it | iPhone sends `workoutEnded`, Watch dismisses to home, ends HK session |
| No Watch paired / forgot Watch | All sync calls check reachability/activation, no-op if unavailable |
| Rapid set logging on Watch | Watch sends `completeSet` with replyHandler, doesn't block UI; reply confirms and updates state |
| iPhone navigates to different exercise | State update moves `currentExerciseIndex`, Watch follows |

## Unit Handling

The sync state always uses kg internally. The Watch reads `WeightUnit.current` to display in the user's preferred unit and converts back to kg before sending `completeSet`. Digital Crown increments adjust based on unit (2.5 kg or 5 lbs).

## Localization

Watch UI strings must support English and Simplified Chinese, consistent with the iPhone app. Reuse existing localization keys where possible (e.g., `common.done`, `common.cancel`).

## What This Does NOT Include

- Starting a workout from the Watch (always starts from iPhone)
- Editing completed sets on the Watch (use iPhone)
- Watch complications or widgets
- Standalone Watch operation without iPhone
- Warmup/non-working set types from Watch (always `.working`)
