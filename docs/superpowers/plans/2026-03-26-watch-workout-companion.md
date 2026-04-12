# Watch Workout Companion Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bidirectional real-time sync between iPhone and Watch during guided workouts, with the iPhone as source of truth and the Watch as a lightweight input device.

**Architecture:** WCSession `sendMessage` with `replyHandler` for Watch-to-iPhone actions. iPhone sends full `WorkoutSyncState` snapshots; Watch sends individual actions (`completeSet`, `requestState`). `HKWorkoutSession` on Watch keeps app foregrounded. No offline queue or conflict resolution.

**Tech Stack:** Swift, SwiftUI, WatchConnectivity, HealthKit, watchOS

**Spec:** `docs/superpowers/specs/2026-03-26-watch-workout-companion.md`

---

## File Structure

### Create (mirrored in both targets)
- `FlexLoop/FlexLoop/Services/WorkoutSyncModels.swift` — shared Codable models (also copy to Watch target)
- `FlexLoopWatch Watch App/WorkoutSyncModels.swift` — identical copy for Watch target

### Modify — iPhone
- `FlexLoop/FlexLoop/ViewModels/GuidedWorkoutViewModel.swift` — add `name`/`restSeconds` to `GuidedExercise`, add `stateSnapshot()`, add sync callbacks
- `FlexLoop/FlexLoop/ViewModels/HomeViewModel.swift` — remove `syncPlanToWatch()`
- `FlexLoop/FlexLoop/Services/WatchConnectivityManager.swift` — rewrite `PhoneConnectivityManager` for bidirectional messaging
- `FlexLoop/FlexLoop/Views/Workout/GuidedWorkoutView.swift` — pass `exerciseNames` and group rest seconds into ViewModel

### Modify — Watch
- `FlexLoopWatch Watch App/WatchSessionManager.swift` — rewrite for workout state, HKWorkoutSession, bidirectional messaging
- `FlexLoopWatch Watch App/WatchHomeView.swift` — simplify for workout-in-progress state
- `FlexLoopWatch Watch App/WatchWorkoutView.swift` — rewrite: state-driven, +/- buttons for reps/RPE, Digital Crown for weight

### Modify — Localization
- `FlexLoop/FlexLoop/Resources/Localizable.xcstrings` — add Watch-related strings (EN + ZH)

### No Changes
- `FlexLoopWatch Watch App/WatchRestTimerView.swift` — keep as-is
- `FlexLoopWatch Watch App/FlexLoopWatchApp.swift` — keep as-is
- `FlexLoopWatch Watch App/ContentView.swift` — keep as-is

---

## Chunk 1: Shared Models + iPhone ViewModel Changes

### Task 1: Create shared WorkoutSyncModels

**Files:**
- Create: `FlexLoop/FlexLoop/Services/WorkoutSyncModels.swift`
- Create: `FlexLoopWatch Watch App/WorkoutSyncModels.swift` (identical copy)

- [ ] **Step 1: Create WorkoutSyncModels.swift**

```swift
import Foundation

// MARK: - Workout Sync State (iPhone → Watch)

struct WorkoutSyncState: Codable {
    let isActive: Bool
    let currentExerciseIndex: Int
    let exercises: [SyncExercise]
    let restTimerRemaining: Int?
    let startedAt: Date
}

struct SyncExercise: Codable {
    let exerciseId: Int
    let name: String
    let isSkipped: Bool
    let restSeconds: Int
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

// MARK: - Watch → iPhone Actions

struct WatchCompleteSetAction: Codable {
    let exerciseIndex: Int
    let setNumber: Int
    let weightKg: Double?
    let reps: Int?
    let rpe: Double?
}

// MARK: - Message Encoding Helpers

enum SyncMessageType: String {
    case workoutStarted
    case stateUpdate
    case workoutEnded
    case completeSet
    case requestState
    case noActiveWorkout
}

enum SyncMessageCoder {
    private static let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.dateEncodingStrategy = .secondsSince1970
        return e
    }()

    private static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .secondsSince1970
        return d
    }()

    static func encode<T: Encodable>(_ type: SyncMessageType, payload: T) -> [String: Any] {
        let data = (try? encoder.encode(payload)) ?? Data()
        return ["type": type.rawValue, "payload": data]
    }

    static func encode(_ type: SyncMessageType) -> [String: Any] {
        return ["type": type.rawValue]
    }

    static func decodeType(from message: [String: Any]) -> SyncMessageType? {
        guard let raw = message["type"] as? String else { return nil }
        return SyncMessageType(rawValue: raw)
    }

    static func decodePayload<T: Decodable>(_ type: T.Type, from message: [String: Any]) -> T? {
        guard let data = message["payload"] as? Data else { return nil }
        return try? decoder.decode(type, from: data)
    }
}
```

- [ ] **Step 2: Copy to Watch target**

Copy the identical file to `FlexLoopWatch Watch App/WorkoutSyncModels.swift`. Add both files to their respective Xcode targets.

- [ ] **Step 3: Build both targets to verify compilation**

Run: Build FlexLoop scheme + FlexLoopWatch Watch App scheme
Expected: Both compile without errors

- [ ] **Step 4: Commit**

```bash
git add FlexLoop/FlexLoop/Services/WorkoutSyncModels.swift "FlexLoopWatch Watch App/WorkoutSyncModels.swift"
git commit -m "feat(watch): add shared WorkoutSyncModels for bidirectional sync"
```

---

### Task 2: Add name and restSeconds to GuidedExercise, add stateSnapshot()

**Files:**
- Modify: `FlexLoop/FlexLoop/ViewModels/GuidedWorkoutViewModel.swift`

- [ ] **Step 1: Add `name` and `restSeconds` fields to `GuidedExercise`**

```swift
struct GuidedExercise: Identifiable {
    let id = UUID()
    let exerciseId: Int
    let planExerciseId: Int?
    let name: String                    // NEW
    let restSeconds: Int                // NEW
    var targetSets: [GuidedSetTarget]
    var completedSets: [CompletedSet] = []
    var isSkipped = false
    var notes: String?
}
```

- [ ] **Step 2: Update `loadFromPlanDay` to populate name and restSeconds**

In `loadFromPlanDay(_ day: APIPlanDay, exerciseNames: [Int: String])`, update the `GuidedExercise` construction:

```swift
return GuidedExercise(
    exerciseId: ex.exerciseId,
    planExerciseId: ex.id,
    name: exerciseNames[ex.exerciseId] ?? "Exercise #\(ex.exerciseId)",
    restSeconds: group.restAfterGroupSec,
    targetSets: targets,
    notes: ex.notes
)
```

Note: `group` is the enclosing `APIPlanExerciseGroup` from the `flatMap`. The current code uses `group.exercises.map` inside `day.exerciseGroups.flatMap { group in ... }` so `group` is already available.

- [ ] **Step 3: Add `stateSnapshot()` method**

Add to `GuidedWorkoutViewModel`:

```swift
func stateSnapshot() -> WorkoutSyncState {
    WorkoutSyncState(
        isActive: isWorkoutActive,
        currentExerciseIndex: currentExerciseIndex,
        exercises: exercises.map { ex in
            SyncExercise(
                exerciseId: ex.exerciseId,
                name: ex.name,
                isSkipped: ex.isSkipped,
                restSeconds: ex.restSeconds,
                targets: ex.targetSets.map { t in
                    SyncSetTarget(
                        setNumber: t.setNumber,
                        weightKg: t.targetWeightKg,
                        reps: t.targetReps,
                        rpe: t.targetRpe
                    )
                },
                completedSets: ex.completedSets.map { c in
                    SyncCompletedSet(
                        setNumber: c.setNumber,
                        weightKg: c.weightKg,
                        reps: c.reps,
                        rpe: c.rpe
                    )
                }
            )
        },
        restTimerRemaining: isRestTimerActive ? restTimeRemaining : nil,
        startedAt: startedAt ?? Date()
    )
}
```

- [ ] **Step 4: Add sync callback after state mutations**

Add a sync notification after each state-mutating method. At the end of `completeSet()`, `editCompletedSet()`, `skipExercise()`, `startRestTimer()`, `stopRestTimer()`, add:

```swift
PhoneConnectivityManager.shared.sendStateUpdate(stateSnapshot())
```

Also add to `loadFromPlanDay` (after setup):

```swift
PhoneConnectivityManager.shared.sendWorkoutStarted(stateSnapshot())
```

And in `finishWorkout`:

```swift
PhoneConnectivityManager.shared.sendWorkoutEnded(reason: "finished")
```

For the cancel path in `GuidedWorkoutView` (when user taps Cancel), we'll handle that in Task 5.

- [ ] **Step 5: Build to verify compilation**

Run: Build FlexLoop scheme
Expected: Compile success

- [ ] **Step 6: Commit**

```bash
git add FlexLoop/FlexLoop/ViewModels/GuidedWorkoutViewModel.swift
git commit -m "feat(watch): add exercise name/restSeconds, stateSnapshot, sync callbacks"
```

---

### Task 3: Remove syncPlanToWatch from HomeViewModel

**Files:**
- Modify: `FlexLoop/FlexLoop/ViewModels/HomeViewModel.swift`

- [ ] **Step 1: Remove `syncPlanToWatch()` and its call**

Delete the `syncPlanToWatch()` private method and the `syncPlanToWatch()` call inside `loadNextWorkout()`.

- [ ] **Step 2: Build and commit**

```bash
git add FlexLoop/FlexLoop/ViewModels/HomeViewModel.swift
git commit -m "refactor(watch): remove plan-based Watch sync, replaced by workout sync"
```

---

## Chunk 2: iPhone PhoneConnectivityManager Rewrite

### Task 4: Rewrite PhoneConnectivityManager

**Files:**
- Modify: `FlexLoop/FlexLoop/Services/WatchConnectivityManager.swift`

- [ ] **Step 1: Rewrite the file**

Replace the entire contents with:

```swift
import Foundation
import WatchConnectivity

class PhoneConnectivityManager: NSObject, ObservableObject, WCSessionDelegate {
    static let shared = PhoneConnectivityManager()

    @Published var isWatchReachable = false

    /// Reference to the active workout ViewModel for handling Watch actions.
    /// Set by GuidedWorkoutView on appear, cleared on disappear.
    weak var activeWorkoutViewModel: GuidedWorkoutViewModel?

    override init() {
        super.init()
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
    }

    // MARK: - Send to Watch

    func sendWorkoutStarted(_ state: WorkoutSyncState) {
        let message = SyncMessageCoder.encode(.workoutStarted, payload: state)
        sendAndSetContext(message)
    }

    func sendStateUpdate(_ state: WorkoutSyncState) {
        guard WCSession.default.isReachable else { return }
        let message = SyncMessageCoder.encode(.stateUpdate, payload: state)
        WCSession.default.sendMessage(message, replyHandler: nil)
    }

    func sendWorkoutEnded(reason: String) {
        struct EndPayload: Codable { let reason: String }
        let message = SyncMessageCoder.encode(.workoutEnded, payload: EndPayload(reason: reason))
        sendAndSetContext(message)
    }

    private func sendAndSetContext(_ message: [String: Any]) {
        // Best-effort direct message
        if WCSession.default.isReachable {
            WCSession.default.sendMessage(message, replyHandler: nil)
        }
        // Also set application context as fallback
        try? WCSession.default.updateApplicationContext(message)
    }

    // MARK: - Handle Watch Messages

    func session(_ session: WCSession, didReceiveMessage message: [String: Any],
                 replyHandler: @escaping ([String: Any]) -> Void) {
        guard let type = SyncMessageCoder.decodeType(from: message) else {
            replyHandler(SyncMessageCoder.encode(.noActiveWorkout))
            return
        }

        switch type {
        case .completeSet:
            handleCompleteSet(message: message, replyHandler: replyHandler)
        case .requestState:
            handleRequestState(replyHandler: replyHandler)
        default:
            replyHandler(SyncMessageCoder.encode(.noActiveWorkout))
        }
    }

    private func handleCompleteSet(message: [String: Any],
                                   replyHandler: @escaping ([String: Any]) -> Void) {
        guard let action = SyncMessageCoder.decodePayload(WatchCompleteSetAction.self, from: message),
              let vm = activeWorkoutViewModel else {
            handleRequestState(replyHandler: replyHandler)
            return
        }

        DispatchQueue.main.async {
            vm.completeSet(
                exerciseIndex: action.exerciseIndex,
                setNumber: action.setNumber,
                weightKg: action.weightKg,
                reps: action.reps != nil ? action.reps! : nil,
                rpe: action.rpe
            )
            let state = vm.stateSnapshot()
            replyHandler(SyncMessageCoder.encode(.stateUpdate, payload: state))
        }
    }

    private func handleRequestState(replyHandler: @escaping ([String: Any]) -> Void) {
        DispatchQueue.main.async {
            if let vm = self.activeWorkoutViewModel, vm.isWorkoutActive {
                let state = vm.stateSnapshot()
                replyHandler(SyncMessageCoder.encode(.stateUpdate, payload: state))
            } else {
                replyHandler(SyncMessageCoder.encode(.noActiveWorkout))
            }
        }
    }

    // MARK: - WCSessionDelegate

    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        DispatchQueue.main.async {
            self.isWatchReachable = session.isReachable
        }
    }

    func sessionDidBecomeInactive(_ session: WCSession) {}

    func sessionDidDeactivate(_ session: WCSession) {
        WCSession.default.activate()
    }

    func sessionReachabilityDidChange(_ session: WCSession) {
        DispatchQueue.main.async {
            self.isWatchReachable = session.isReachable
        }
    }
}
```

Note: `GuidedWorkoutViewModel` needs to be `class` (not struct) for the `weak` reference. It already is (`final class`).

- [ ] **Step 2: Build to verify compilation**

Run: Build FlexLoop scheme
Expected: Compile success

- [ ] **Step 3: Commit**

```bash
git add FlexLoop/FlexLoop/Services/WatchConnectivityManager.swift
git commit -m "feat(watch): rewrite PhoneConnectivityManager for bidirectional workout sync"
```

---

### Task 5: Wire up ViewModel reference in GuidedWorkoutView

**Files:**
- Modify: `FlexLoop/FlexLoop/Views/Workout/GuidedWorkoutView.swift`

- [ ] **Step 1: Set activeWorkoutViewModel on appear, clear on disappear**

In `.onAppear`, add:

```swift
PhoneConnectivityManager.shared.activeWorkoutViewModel = viewModel
```

Add `.onDisappear`:

```swift
.onDisappear {
    PhoneConnectivityManager.shared.activeWorkoutViewModel = nil
}
```

- [ ] **Step 2: Send workoutEnded on cancel**

Find the Cancel button action. After dismissing, add:

```swift
PhoneConnectivityManager.shared.sendWorkoutEnded(reason: "cancelled")
```

- [ ] **Step 3: Build and commit**

```bash
git add FlexLoop/FlexLoop/Views/Workout/GuidedWorkoutView.swift
git commit -m "feat(watch): wire up ViewModel reference and cancel sync in GuidedWorkoutView"
```

---

## Chunk 3: Watch WatchSessionManager Rewrite + HKWorkoutSession

### Task 6: Rewrite WatchSessionManager

**Files:**
- Modify: `FlexLoopWatch Watch App/WatchSessionManager.swift`

- [ ] **Step 1: Rewrite the file**

Replace the entire contents with:

```swift
import Combine
import Foundation
import HealthKit
import WatchConnectivity

class WatchSessionManager: NSObject, ObservableObject, WCSessionDelegate {
    static let shared = WatchSessionManager()

    @Published var workoutState: WorkoutSyncState?
    @Published var isConnected = false

    private var healthStore = HKHealthStore()
    private var workoutSession: HKWorkoutSession?
    private var workoutBuilder: HKLiveWorkoutBuilder?

    override init() {
        super.init()
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
    }

    // MARK: - Send to iPhone

    func sendCompleteSet(exerciseIndex: Int, setNumber: Int,
                         weightKg: Double?, reps: Int?, rpe: Double?) {
        let action = WatchCompleteSetAction(
            exerciseIndex: exerciseIndex,
            setNumber: setNumber,
            weightKg: weightKg,
            reps: reps,
            rpe: rpe
        )
        let message = SyncMessageCoder.encode(.completeSet, payload: action)

        WCSession.default.sendMessage(message, replyHandler: { [weak self] reply in
            if let state = SyncMessageCoder.decodePayload(WorkoutSyncState.self, from: reply) {
                DispatchQueue.main.async {
                    self?.workoutState = state
                }
            }
        }, errorHandler: { error in
            print("sendCompleteSet error: \(error)")
        })
    }

    func requestState() {
        guard WCSession.default.isReachable else { return }
        let message = SyncMessageCoder.encode(.requestState)

        WCSession.default.sendMessage(message, replyHandler: { [weak self] reply in
            guard let type = SyncMessageCoder.decodeType(from: reply) else { return }
            if type == .stateUpdate,
               let state = SyncMessageCoder.decodePayload(WorkoutSyncState.self, from: reply) {
                DispatchQueue.main.async {
                    self?.workoutState = state
                }
            } else if type == .noActiveWorkout {
                DispatchQueue.main.async {
                    self?.workoutState = nil
                }
            }
        }, errorHandler: { error in
            print("requestState error: \(error)")
        })
    }

    // MARK: - HKWorkoutSession

    private func startWorkoutSession() {
        guard HKHealthStore.isHealthDataAvailable() else { return }

        let config = HKWorkoutConfiguration()
        config.activityType = .traditionalStrengthTraining
        config.locationType = .indoor

        do {
            workoutSession = try HKWorkoutSession(healthStore: healthStore, configuration: config)
            workoutBuilder = workoutSession?.associatedWorkoutBuilder()
            workoutBuilder?.dataSource = HKLiveWorkoutDataSource(healthStore: healthStore, workoutConfiguration: config)

            workoutSession?.startActivity(with: Date())
            try workoutBuilder?.beginCollection(withStart: Date()) { _, _ in }
        } catch {
            print("Failed to start workout session: \(error)")
        }
    }

    private func endWorkoutSession() {
        workoutSession?.end()
        workoutBuilder?.endCollection(withEnd: Date()) { [weak self] _, _ in
            self?.workoutBuilder?.finishWorkout { _, _ in }
        }
        workoutSession = nil
        workoutBuilder = nil
    }

    // MARK: - WCSessionDelegate

    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        DispatchQueue.main.async {
            self.isConnected = activationState == .activated
        }
        // Check for queued application context
        if !session.receivedApplicationContext.isEmpty {
            handleIncomingMessage(session.receivedApplicationContext)
        }
    }

    func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        handleIncomingMessage(message)
    }

    func session(_ session: WCSession, didReceiveApplicationContext applicationContext: [String: Any]) {
        handleIncomingMessage(applicationContext)
    }

    private func handleIncomingMessage(_ message: [String: Any]) {
        guard let type = SyncMessageCoder.decodeType(from: message) else { return }

        switch type {
        case .workoutStarted, .stateUpdate:
            if let state = SyncMessageCoder.decodePayload(WorkoutSyncState.self, from: message) {
                DispatchQueue.main.async {
                    let wasInactive = self.workoutState == nil
                    self.workoutState = state
                    if wasInactive && state.isActive {
                        self.startWorkoutSession()
                    }
                }
            }
        case .workoutEnded:
            DispatchQueue.main.async {
                self.workoutState = nil
                self.endWorkoutSession()
            }
        default:
            break
        }
    }
}
```

- [ ] **Step 2: Build Watch target to verify compilation**

Run: Build FlexLoopWatch Watch App scheme
Expected: Compile success

- [ ] **Step 3: Commit**

```bash
git add "FlexLoopWatch Watch App/WatchSessionManager.swift"
git commit -m "feat(watch): rewrite WatchSessionManager for bidirectional sync + HKWorkoutSession"
```

---

## Chunk 4: Watch UI Rewrite

### Task 7: Rewrite WatchHomeView

**Files:**
- Modify: `FlexLoopWatch Watch App/WatchHomeView.swift`

- [ ] **Step 1: Rewrite the file**

```swift
import SwiftUI

struct WatchHomeView: View {
    @EnvironmentObject var sessionManager: WatchSessionManager

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                if let state = sessionManager.workoutState, state.isActive {
                    activeWorkoutView(state)
                } else {
                    inactiveView
                }
            }
            .navigationTitle("FlexLoop")
            .navigationBarTitleDisplayMode(.inline)
            .onAppear {
                sessionManager.requestState()
            }
        }
    }

    private func activeWorkoutView(_ state: WorkoutSyncState) -> some View {
        let exercise = state.exercises.indices.contains(state.currentExerciseIndex)
            ? state.exercises[state.currentExerciseIndex] : nil

        return VStack(spacing: 8) {
            Text("Workout Active")
                .font(.caption)
                .foregroundStyle(.green)

            if let exercise {
                Text(exercise.name)
                    .font(.headline)
                    .multilineTextAlignment(.center)
                    .lineLimit(2)
                    .minimumScaleFactor(0.6)

                let completed = exercise.completedSets.count
                let total = exercise.targets.count
                Text("Set \(completed + 1) of \(total)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            NavigationLink("Continue") {
                WatchWorkoutView()
                    .environmentObject(sessionManager)
            }
            .buttonStyle(.borderedProminent)
            .tint(.green)
        }
    }

    private var inactiveView: some View {
        VStack(spacing: 8) {
            Text("No Active Workout")
                .font(.headline)

            Text("Start a workout\nfrom iPhone")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
    }
}
```

- [ ] **Step 2: Build Watch target**

Expected: Compile success (WatchWorkoutView will be updated in next task)

- [ ] **Step 3: Commit**

```bash
git add "FlexLoopWatch Watch App/WatchHomeView.swift"
git commit -m "feat(watch): rewrite WatchHomeView for active workout state"
```

---

### Task 8: Rewrite WatchWorkoutView

**Files:**
- Modify: `FlexLoopWatch Watch App/WatchWorkoutView.swift`

- [ ] **Step 1: Rewrite the file**

```swift
import SwiftUI

struct WatchWorkoutView: View {
    @EnvironmentObject var sessionManager: WatchSessionManager
    @Environment(\.dismiss) private var dismiss

    @State private var weight: Double = 0
    @State private var reps: Int = 8
    @State private var rpe: Double = 7.0
    @State private var showRestTimer = false
    @State private var restSeconds = 120

    private let unit = WeightUnit.current

    private var state: WorkoutSyncState? { sessionManager.workoutState }

    private var currentExercise: SyncExercise? {
        guard let state, state.exercises.indices.contains(state.currentExerciseIndex) else { return nil }
        return state.exercises[state.currentExerciseIndex]
    }

    private var currentSetNumber: Int {
        guard let exercise = currentExercise else { return 1 }
        return exercise.completedSets.count + 1
    }

    private var totalSetsCompleted: Int {
        state?.exercises.flatMap(\.completedSets).count ?? 0
    }

    var body: some View {
        Group {
            if let exercise = currentExercise {
                exerciseView(exercise)
            } else if let state, !state.isActive {
                workoutEndedView
            } else {
                ProgressView()
            }
        }
        .navigationBarBackButtonHidden(true)
        .sheet(isPresented: $showRestTimer) {
            WatchRestTimerView(seconds: restSeconds) {
                showRestTimer = false
            }
        }
        .onChange(of: sessionManager.workoutState) { _, newState in
            if let newState, !newState.isActive {
                dismiss()
            } else {
                loadCurrentExerciseDefaults()
            }
        }
        .onAppear {
            loadCurrentExerciseDefaults()
        }
    }

    private func exerciseView(_ exercise: SyncExercise) -> some View {
        ScrollView {
            VStack(spacing: 6) {
                // Exercise name
                Text(exercise.name)
                    .font(.headline)
                    .lineLimit(2)
                    .minimumScaleFactor(0.6)
                    .multilineTextAlignment(.center)

                Text("Set \(currentSetNumber) of \(exercise.targets.count)")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                // Weight — Digital Crown
                VStack(spacing: 2) {
                    Text("\(unit.fromKgRounded(weight), specifier: "%.1f") \(unit.label)")
                        .font(.title3.monospacedDigit().bold())
                }
                .focusable()
                .digitalCrownRotation($weight, from: 0, through: 250,
                                      by: unit == .metric ? 2.5 : 2.26796)

                // Reps — +/- buttons
                HStack {
                    Button { if reps > 1 { reps -= 1 } } label: {
                        Image(systemName: "minus")
                            .font(.caption2)
                    }
                    .buttonStyle(.bordered)
                    .frame(width: 36)

                    Text("\(reps) reps")
                        .font(.subheadline.monospacedDigit())
                        .frame(width: 60)

                    Button { if reps < 99 { reps += 1 } } label: {
                        Image(systemName: "plus")
                            .font(.caption2)
                    }
                    .buttonStyle(.bordered)
                    .frame(width: 36)
                }

                // RPE — +/- buttons
                HStack {
                    Button { if rpe > 1 { rpe -= 0.5 } } label: {
                        Image(systemName: "minus")
                            .font(.caption2)
                    }
                    .buttonStyle(.bordered)
                    .frame(width: 36)

                    Text("RPE \(rpe, specifier: "%.1f")")
                        .font(.subheadline.monospacedDigit())
                        .frame(width: 70)

                    Button { if rpe < 10 { rpe += 0.5 } } label: {
                        Image(systemName: "plus")
                            .font(.caption2)
                    }
                    .buttonStyle(.bordered)
                    .frame(width: 36)
                }

                // Action buttons
                HStack(spacing: 12) {
                    Button {
                        completeSet(exercise)
                    } label: {
                        Image(systemName: "checkmark")
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.green)

                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark")
                    }
                    .buttonStyle(.bordered)
                    .tint(.red)
                }

                Text("\(totalSetsCompleted) sets done")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .padding(.vertical, 4)
        }
    }

    private var workoutEndedView: some View {
        VStack(spacing: 12) {
            Image(systemName: "checkmark.circle.fill")
                .font(.largeTitle)
                .foregroundStyle(.green)
            Text("Workout Complete!")
                .font(.headline)
            Text("\(totalSetsCompleted) total sets")
                .font(.caption)
                .foregroundStyle(.secondary)
            Button("Done") { dismiss() }
                .buttonStyle(.borderedProminent)
        }
    }

    private func loadCurrentExerciseDefaults() {
        guard let exercise = currentExercise else { return }
        let setIndex = exercise.completedSets.count
        let target = exercise.targets.indices.contains(setIndex)
            ? exercise.targets[setIndex] : exercise.targets.first

        weight = target?.weightKg ?? 0
        reps = target?.reps ?? 8
        rpe = target?.rpe ?? 7.0
        restSeconds = exercise.restSeconds
    }

    private func completeSet(_ exercise: SyncExercise) {
        guard let state else { return }

        sessionManager.sendCompleteSet(
            exerciseIndex: state.currentExerciseIndex,
            setNumber: currentSetNumber,
            weightKg: weight,
            reps: reps,
            rpe: rpe
        )

        showRestTimer = true
    }
}
```

- [ ] **Step 2: Add `WeightUnit` to Watch target**

The Watch needs access to `WeightUnit` from `UnitHelper.swift`. Since targets can't share files directly, copy the relevant parts. Create `FlexLoopWatch Watch App/WeightUnit.swift`:

```swift
import Foundation

enum WeightUnit: String {
    case metric
    case imperial

    static var current: WeightUnit {
        let stored = UserDefaults.standard.string(forKey: "unitSystem") ?? "metric"
        return WeightUnit(rawValue: stored) ?? .metric
    }

    var label: String {
        switch self {
        case .metric: return "kg"
        case .imperial: return "lbs"
        }
    }

    func fromKg(_ kg: Double) -> Double {
        switch self {
        case .metric: return kg
        case .imperial: return kg * 2.20462
        }
    }

    func toKg(_ value: Double) -> Double {
        switch self {
        case .metric: return value
        case .imperial: return value / 2.20462
        }
    }

    func fromKgRounded(_ kg: Double) -> Double {
        let converted = fromKg(kg)
        let increment: Double = self == .metric ? 2.5 : 5.0
        return (converted / increment).rounded() * increment
    }
}
```

- [ ] **Step 3: Build Watch target to verify compilation**

Run: Build FlexLoopWatch Watch App scheme
Expected: Compile success

- [ ] **Step 4: Commit**

```bash
git add "FlexLoopWatch Watch App/WatchWorkoutView.swift" "FlexLoopWatch Watch App/WeightUnit.swift"
git commit -m "feat(watch): rewrite WatchWorkoutView with weight/reps/RPE editing and sync"
```

---

## Chunk 5: Cleanup + Localization

### Task 9: Remove old Watch data models

**Files:**
- Modify: `FlexLoop/FlexLoop/Services/WatchConnectivityManager.swift` — old models already removed in Task 4
- Verify: no other references to `WatchPlanData`, `WatchDayData`, `WatchExerciseData`

- [ ] **Step 1: Search for remaining references**

```bash
grep -rn "WatchPlanData\|WatchDayData\|WatchExerciseData" FlexLoop/ "FlexLoopWatch Watch App/"
```

Expected: No matches (all references removed in Tasks 4, 6, 7, 8)

- [ ] **Step 2: Delete ContentView.swift if unused**

`FlexLoopWatch Watch App/ContentView.swift` is a placeholder. Verify it's not referenced anywhere except `FlexLoopWatchApp.swift`. If `FlexLoopWatchApp.swift` uses `WatchHomeView` directly (it does), `ContentView.swift` can be deleted.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore(watch): remove old Watch data models and unused files"
```

---

### Task 10: Add localization strings

**Files:**
- Modify: `FlexLoop/FlexLoop/Resources/Localizable.xcstrings`

- [ ] **Step 1: Add Watch-related strings**

Note: The Watch workout view currently uses hardcoded English strings. Add localization keys for the Watch UI strings that need translation. Since the Watch app uses a separate target, it may need its own localization file. Check if the Watch target has access to the main app's `Localizable.xcstrings`.

If the Watch target has its own localization, create strings there. Otherwise, keep Watch strings hardcoded for now (the Watch Digital Crown/button UI is mostly numbers and symbols) and add a follow-up task to set up Watch localization properly.

Key strings to localize:
- "Workout Active"
- "No Active Workout"
- "Start a workout\nfrom iPhone"
- "Continue"
- "Workout Complete!"
- "sets done" / "total sets"
- "Set %d of %d"
- "reps"
- "RPE"
- "Done"

- [ ] **Step 2: Commit**

```bash
git add FlexLoop/FlexLoop/Resources/Localizable.xcstrings
git commit -m "feat(watch): add Watch UI localization strings"
```

---

### Task 11: Manual verification on simulator

**Files:** None (testing only)

- [ ] **Step 1: Build and run iPhone app on iPhone 17 Pro simulator**

Verify: App launches, Start Workout works, guided workout functions normally without Watch.

- [ ] **Step 2: Build and run Watch app on Apple Watch simulator**

Verify: Watch app launches, shows "No Active Workout — Start from iPhone".

- [ ] **Step 3: Verify no regressions**

Start a workout on iPhone, complete sets, finish workout. Verify all existing functionality works (set completion, rest timer, PR detection, exercise navigation, workout summary).

Note: Bidirectional sync CANNOT be tested on simulators — WatchConnectivity requires real paired devices. The simulator test verifies no regressions and that both apps build/run independently.

- [ ] **Step 4: Final commit with any fixes**

```bash
git commit -m "fix(watch): address issues found during manual verification"
```
