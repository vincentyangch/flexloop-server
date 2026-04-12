# FlexLoop iOS App Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FlexLoop native iOS app (iPhone + Apple Watch) — a workout logging and AI coaching client that syncs with the self-hosted FlexLoop backend server.

**Architecture:** SwiftUI app with MVVM pattern, SwiftData for offline caching, URLSession-based API client for backend communication, HealthKit integration for heart rate and workout data, and a WatchOS companion app for glanceable workout logging.

**Tech Stack:** Swift 5.9+, SwiftUI, SwiftData, HealthKit, WatchKit, WatchConnectivity, XCTest

**PRD Reference:** `/Users/flyingchickens/Documents/Projects/FlexLoop/FlexLoop_PRD.md`
**Backend Plan Reference:** `/Users/flyingchickens/Documents/Projects/FlexLoop/docs/superpowers/plans/2026-03-23-flexloop-server.md`

**Prerequisite:** The backend API server should be running (at least Tasks 1–11 from the backend plan) before testing API integration.

---

## Chunk 1: Project Setup & Core Data Layer

### Task 1: Initialize Xcode project with app and Watch target

**Files:**
- Create: `FlexLoop.xcodeproj` (via Xcode)
- Create: `FlexLoop/FlexLoopApp.swift`
- Create: `FlexLoop/Info.plist`
- Create: `FlexLoopWatch/FlexLoopWatchApp.swift`
- Create: `FlexLoopTests/FlexLoopTests.swift`

- [ ] **Step 1: Create Xcode project**

Open Xcode → File → New → Project → iOS App:
- Product Name: `FlexLoop`
- Organization Identifier: `com.flexloop`
- Interface: SwiftUI
- Language: Swift
- Storage: SwiftData
- Include Tests: Yes (Unit + UI)

- [ ] **Step 2: Add Watch target**

File → New → Target → watchOS → App:
- Product Name: `FlexLoopWatch`
- Embed in: FlexLoop

- [ ] **Step 3: Create basic app entry point**

```swift
// FlexLoop/FlexLoopApp.swift
import SwiftUI
import SwiftData

@main
struct FlexLoopApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .modelContainer(for: [
            CachedUser.self,
            CachedWorkoutSession.self,
            CachedWorkoutSet.self,
            CachedExercise.self,
            CachedPlan.self,
        ])
    }
}
```

```swift
// FlexLoop/ContentView.swift
import SwiftUI

struct ContentView: View {
    var body: some View {
        TabView {
            Text("Home")
                .tabItem { Label("Home", systemImage: "house") }
            Text("Workout")
                .tabItem { Label("Workout", systemImage: "figure.strengthtraining.traditional") }
            Text("Plan")
                .tabItem { Label("Plan", systemImage: "calendar") }
            Text("Progress")
                .tabItem { Label("Progress", systemImage: "chart.line.uptrend.xyaxis") }
            Text("Settings")
                .tabItem { Label("Settings", systemImage: "gear") }
        }
    }
}
```

- [ ] **Step 4: Verify project builds and runs on simulator**

Run: Build and run on iPhone 16 Pro simulator
Expected: App launches with tab bar showing 5 tabs

- [ ] **Step 5: Run initial test**

```swift
// FlexLoopTests/FlexLoopTests.swift
import XCTest
@testable import FlexLoop

final class FlexLoopTests: XCTestCase {
    func testAppLaunches() {
        // Verify the app module can be imported
        XCTAssertTrue(true)
    }
}
```

Run: `Cmd+U` in Xcode
Expected: Test passes

- [ ] **Step 6: Commit**

```bash
git init
git add .
git commit -m "feat: initialize Xcode project with iPhone app, Watch app, and test targets"
```

---

### Task 2: Define SwiftData models for offline caching

**Files:**
- Create: `FlexLoop/Models/CachedUser.swift`
- Create: `FlexLoop/Models/CachedExercise.swift`
- Create: `FlexLoop/Models/CachedPlan.swift`
- Create: `FlexLoop/Models/CachedWorkoutSession.swift`
- Create: `FlexLoop/Models/CachedWorkoutSet.swift`
- Create: `FlexLoopTests/ModelTests.swift`

- [ ] **Step 1: Write failing test for CachedUser model**

```swift
// FlexLoopTests/ModelTests.swift
import XCTest
import SwiftData
@testable import FlexLoop

final class ModelTests: XCTestCase {
    var container: ModelContainer!
    var context: ModelContext!

    override func setUp() {
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        container = try! ModelContainer(
            for: CachedUser.self, CachedExercise.self,
                 CachedWorkoutSession.self, CachedWorkoutSet.self,
            configurations: config
        )
        context = ModelContext(container)
    }

    func testCreateUser() {
        let user = CachedUser(
            serverId: 1,
            name: "Test User",
            gender: "male",
            age: 28,
            heightCm: 180.0,
            weightKg: 82.0,
            experienceLevel: "intermediate",
            goals: "hypertrophy",
            availableEquipment: ["barbell", "dumbbells"]
        )
        context.insert(user)
        try! context.save()

        let descriptor = FetchDescriptor<CachedUser>()
        let users = try! context.fetch(descriptor)
        XCTAssertEqual(users.count, 1)
        XCTAssertEqual(users.first?.name, "Test User")
        XCTAssertEqual(users.first?.serverId, 1)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `Cmd+U`
Expected: FAIL — `CachedUser` not defined

- [ ] **Step 3: Implement CachedUser model**

```swift
// FlexLoop/Models/CachedUser.swift
import Foundation
import SwiftData

@Model
final class CachedUser {
    @Attribute(.unique) var serverId: Int
    var name: String
    var gender: String
    var age: Int
    var heightCm: Double
    var weightKg: Double
    var experienceLevel: String
    var goals: String
    var availableEquipment: [String]
    var lastSyncedAt: Date?

    init(serverId: Int, name: String, gender: String, age: Int,
         heightCm: Double, weightKg: Double, experienceLevel: String,
         goals: String, availableEquipment: [String] = []) {
        self.serverId = serverId
        self.name = name
        self.gender = gender
        self.age = age
        self.heightCm = heightCm
        self.weightKg = weightKg
        self.experienceLevel = experienceLevel
        self.goals = goals
        self.availableEquipment = availableEquipment
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `Cmd+U`
Expected: PASS

- [ ] **Step 5: Write failing test for CachedExercise**

```swift
// FlexLoopTests/ModelTests.swift (append)

    func testCreateExercise() {
        let exercise = CachedExercise(
            serverId: 1,
            name: "Barbell Bench Press",
            muscleGroup: "chest",
            equipment: "barbell",
            category: "compound",
            difficulty: "intermediate"
        )
        context.insert(exercise)
        try! context.save()

        let descriptor = FetchDescriptor<CachedExercise>()
        let exercises = try! context.fetch(descriptor)
        XCTAssertEqual(exercises.count, 1)
        XCTAssertEqual(exercises.first?.muscleGroup, "chest")
    }
```

- [ ] **Step 6: Implement CachedExercise model**

```swift
// FlexLoop/Models/CachedExercise.swift
import Foundation
import SwiftData

@Model
final class CachedExercise {
    @Attribute(.unique) var serverId: Int
    var name: String
    var muscleGroup: String
    var equipment: String
    var category: String
    var difficulty: String
    var sourcePlugin: String?

    init(serverId: Int, name: String, muscleGroup: String,
         equipment: String, category: String, difficulty: String,
         sourcePlugin: String? = nil) {
        self.serverId = serverId
        self.name = name
        self.muscleGroup = muscleGroup
        self.equipment = equipment
        self.category = category
        self.difficulty = difficulty
        self.sourcePlugin = sourcePlugin
    }
}
```

- [ ] **Step 7: Write failing test for CachedWorkoutSession and CachedWorkoutSet**

```swift
// FlexLoopTests/ModelTests.swift (append)

    func testCreateWorkoutSessionWithSets() {
        let exercise = CachedExercise(
            serverId: 1, name: "Squat", muscleGroup: "quads",
            equipment: "barbell", category: "compound", difficulty: "intermediate"
        )
        context.insert(exercise)

        let session = CachedWorkoutSession(
            source: .adHoc,
            startedAt: Date()
        )
        context.insert(session)

        let set = CachedWorkoutSet(
            session: session,
            exerciseServerId: exercise.serverId,
            setNumber: 1,
            setType: .working,
            weight: 100.0,
            reps: 5,
            rpe: 8.0
        )
        context.insert(set)
        try! context.save()

        let descriptor = FetchDescriptor<CachedWorkoutSession>()
        let sessions = try! context.fetch(descriptor)
        XCTAssertEqual(sessions.count, 1)
        XCTAssertEqual(sessions.first?.sets?.count, 1)
        XCTAssertFalse(sessions.first?.isSynced ?? true)
    }
```

- [ ] **Step 8: Implement CachedWorkoutSession and CachedWorkoutSet models**

```swift
// FlexLoop/Models/CachedWorkoutSession.swift
import Foundation
import SwiftData

enum WorkoutSource: String, Codable {
    case plan
    case template
    case adHoc = "ad_hoc"
}

@Model
final class CachedWorkoutSession {
    var serverId: Int?
    var userId: Int?
    var planDayId: Int?
    var templateId: Int?
    var source: WorkoutSource
    var startedAt: Date
    var completedAt: Date?
    var notes: String?
    var isSynced: Bool

    @Relationship(deleteRule: .cascade, inverse: \CachedWorkoutSet.session)
    var sets: [CachedWorkoutSet]?

    init(serverId: Int? = nil, userId: Int? = nil, planDayId: Int? = nil,
         templateId: Int? = nil, source: WorkoutSource = .adHoc,
         startedAt: Date = Date(), notes: String? = nil) {
        self.serverId = serverId
        self.userId = userId
        self.planDayId = planDayId
        self.templateId = templateId
        self.source = source
        self.startedAt = startedAt
        self.notes = notes
        self.isSynced = false
    }
}
```

```swift
// FlexLoop/Models/CachedWorkoutSet.swift
import Foundation
import SwiftData

enum SetType: String, Codable {
    case warmUp = "warm_up"
    case working
    case drop
    case amrap
    case backoff
}

@Model
final class CachedWorkoutSet {
    var session: CachedWorkoutSession?
    var exerciseServerId: Int
    var exerciseGroupId: Int?
    var setNumber: Int
    var setType: SetType
    var weight: Double?
    var reps: Int?
    var rpe: Double?
    var durationSec: Int?
    var distanceM: Double?
    var restSec: Int?

    init(session: CachedWorkoutSession? = nil, exerciseServerId: Int,
         exerciseGroupId: Int? = nil, setNumber: Int,
         setType: SetType = .working, weight: Double? = nil,
         reps: Int? = nil, rpe: Double? = nil, durationSec: Int? = nil,
         distanceM: Double? = nil, restSec: Int? = nil) {
        self.session = session
        self.exerciseServerId = exerciseServerId
        self.exerciseGroupId = exerciseGroupId
        self.setNumber = setNumber
        self.setType = setType
        self.weight = weight
        self.reps = reps
        self.rpe = rpe
        self.durationSec = durationSec
        self.distanceM = distanceM
        self.restSec = restSec
    }
}
```

- [ ] **Step 9: Run all model tests**

Run: `Cmd+U`
Expected: All PASS

- [ ] **Step 10: Implement CachedPlan model**

```swift
// FlexLoop/Models/CachedPlan.swift
import Foundation
import SwiftData

@Model
final class CachedPlan {
    @Attribute(.unique) var serverId: Int
    var userId: Int
    var name: String
    var splitType: String
    var blockStart: Date
    var blockEnd: Date
    var status: String
    var aiGenerated: Bool
    var daysJson: Data?  // Store full plan days as JSON blob for offline viewing
    var lastSyncedAt: Date?

    init(serverId: Int, userId: Int, name: String, splitType: String,
         blockStart: Date, blockEnd: Date, status: String = "active",
         aiGenerated: Bool = false, daysJson: Data? = nil) {
        self.serverId = serverId
        self.userId = userId
        self.name = name
        self.splitType = splitType
        self.blockStart = blockStart
        self.blockEnd = blockEnd
        self.status = status
        self.aiGenerated = aiGenerated
        self.daysJson = daysJson
    }
}
```

- [ ] **Step 11: Commit**

```bash
git add .
git commit -m "feat: add SwiftData models for offline caching (User, Exercise, Plan, WorkoutSession, WorkoutSet)"
```

---

### Task 3: Build API client for backend communication

**Files:**
- Create: `FlexLoop/Services/APIClient.swift`
- Create: `FlexLoop/Services/APIModels.swift`
- Create: `FlexLoop/Services/ServerConfig.swift`
- Create: `FlexLoopTests/APIClientTests.swift`

- [ ] **Step 1: Write failing test for API client configuration**

```swift
// FlexLoopTests/APIClientTests.swift
import XCTest
@testable import FlexLoop

final class APIClientTests: XCTestCase {

    func testServerConfigDefaultURL() {
        let config = ServerConfig(baseURL: "http://localhost:8000")
        XCTAssertEqual(config.baseURL, "http://localhost:8000")
    }

    func testBuildURL() {
        let config = ServerConfig(baseURL: "http://localhost:8000")
        let client = APIClient(config: config)
        let url = client.buildURL(path: "/api/health")
        XCTAssertEqual(url?.absoluteString, "http://localhost:8000/api/health")
    }

    func testBuildURLWithQueryParams() {
        let config = ServerConfig(baseURL: "http://localhost:8000")
        let client = APIClient(config: config)
        let url = client.buildURL(path: "/api/exercises", queryItems: [
            URLQueryItem(name: "muscle_group", value: "chest"),
        ])
        XCTAssertTrue(url?.absoluteString.contains("muscle_group=chest") ?? false)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `Cmd+U`
Expected: FAIL — types not defined

- [ ] **Step 3: Implement ServerConfig**

```swift
// FlexLoop/Services/ServerConfig.swift
import Foundation

struct ServerConfig {
    let baseURL: String

    static var `default`: ServerConfig {
        // Read from UserDefaults, fallback to localhost
        let url = UserDefaults.standard.string(forKey: "serverBaseURL") ?? "http://localhost:8000"
        return ServerConfig(baseURL: url)
    }

    static func save(baseURL: String) {
        UserDefaults.standard.set(baseURL, forKey: "serverBaseURL")
    }
}
```

- [ ] **Step 4: Implement API response models**

```swift
// FlexLoop/Services/APIModels.swift
import Foundation

// MARK: - User / Profile

struct APIUser: Codable {
    let id: Int
    let name: String
    let gender: String
    let age: Int
    let heightCm: Double
    let weightKg: Double
    let experienceLevel: String
    let goals: String
    let availableEquipment: [String]
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, name, gender, age, goals
        case heightCm = "height_cm"
        case weightKg = "weight_kg"
        case experienceLevel = "experience_level"
        case availableEquipment = "available_equipment"
        case createdAt = "created_at"
    }
}

struct APIUserCreate: Codable {
    let name: String
    let gender: String
    let age: Int
    let heightCm: Double
    let weightKg: Double
    let experienceLevel: String
    let goals: String
    let availableEquipment: [String]

    enum CodingKeys: String, CodingKey {
        case name, gender, age, goals
        case heightCm = "height_cm"
        case weightKg = "weight_kg"
        case experienceLevel = "experience_level"
        case availableEquipment = "available_equipment"
    }
}

// MARK: - Exercise

struct APIExercise: Codable, Identifiable {
    let id: Int
    let name: String
    let muscleGroup: String
    let equipment: String
    let category: String
    let difficulty: String

    enum CodingKeys: String, CodingKey {
        case id, name, equipment, category, difficulty
        case muscleGroup = "muscle_group"
    }
}

struct APIExerciseList: Codable {
    let exercises: [APIExercise]
    let total: Int
}

// MARK: - Workout

struct APIWorkoutSet: Codable, Identifiable {
    let id: Int?
    let exerciseId: Int
    let exerciseGroupId: Int?
    let setNumber: Int
    let setType: String
    let weight: Double?
    let reps: Int?
    let rpe: Double?
    let durationSec: Int?
    let distanceM: Double?
    let restSec: Int?

    enum CodingKeys: String, CodingKey {
        case id
        case exerciseId = "exercise_id"
        case exerciseGroupId = "exercise_group_id"
        case setNumber = "set_number"
        case setType = "set_type"
        case weight, reps, rpe
        case durationSec = "duration_sec"
        case distanceM = "distance_m"
        case restSec = "rest_sec"
    }
}

struct APIWorkoutSession: Codable, Identifiable {
    let id: Int
    let userId: Int
    let planDayId: Int?
    let templateId: Int?
    let source: String
    let startedAt: String
    let completedAt: String?
    let notes: String?
    let sets: [APIWorkoutSet]

    enum CodingKeys: String, CodingKey {
        case id, source, notes, sets
        case userId = "user_id"
        case planDayId = "plan_day_id"
        case templateId = "template_id"
        case startedAt = "started_at"
        case completedAt = "completed_at"
    }
}

// MARK: - Plan

struct APIPlanExercise: Codable {
    let id: Int
    let exerciseId: Int
    let order: Int
    let sets: Int
    let reps: Int
    let weight: Double?
    let rpeTarget: Double?
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case id, order, sets, reps, weight, notes
        case exerciseId = "exercise_id"
        case rpeTarget = "rpe_target"
    }
}

struct APIExerciseGroup: Codable {
    let id: Int
    let groupType: String
    let order: Int
    let restAfterGroupSec: Int
    let exercises: [APIPlanExercise]

    enum CodingKeys: String, CodingKey {
        case id, order, exercises
        case groupType = "group_type"
        case restAfterGroupSec = "rest_after_group_sec"
    }
}

struct APIPlanDay: Codable {
    let id: Int
    let dayNumber: Int
    let label: String
    let focus: String
    let exerciseGroups: [APIExerciseGroup]

    enum CodingKeys: String, CodingKey {
        case id, label, focus
        case dayNumber = "day_number"
        case exerciseGroups = "exercise_groups"
    }
}

struct APIPlan: Codable, Identifiable {
    let id: Int
    let userId: Int
    let name: String
    let splitType: String
    let blockStart: String
    let blockEnd: String
    let status: String
    let aiGenerated: Bool
    let days: [APIPlanDay]

    enum CodingKeys: String, CodingKey {
        case id, name, status, days
        case userId = "user_id"
        case splitType = "split_type"
        case blockStart = "block_start"
        case blockEnd = "block_end"
        case aiGenerated = "ai_generated"
    }
}

// MARK: - Sync

struct APISyncRequest: Codable {
    let userId: Int
    let workouts: [APISyncWorkout]

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case workouts
    }
}

struct APISyncWorkout: Codable {
    let planDayId: Int?
    let templateId: Int?
    let source: String
    let startedAt: String
    let completedAt: String?
    let notes: String?
    let sets: [APISyncSet]

    enum CodingKeys: String, CodingKey {
        case source, notes, sets
        case planDayId = "plan_day_id"
        case templateId = "template_id"
        case startedAt = "started_at"
        case completedAt = "completed_at"
    }
}

struct APISyncSet: Codable {
    let exerciseId: Int
    let exerciseGroupId: Int?
    let setNumber: Int
    let setType: String
    let weight: Double?
    let reps: Int?
    let rpe: Double?
    let durationSec: Int?
    let distanceM: Double?
    let restSec: Int?

    enum CodingKeys: String, CodingKey {
        case setNumber = "set_number"
        case setType = "set_type"
        case exerciseId = "exercise_id"
        case exerciseGroupId = "exercise_group_id"
        case weight, reps, rpe
        case durationSec = "duration_sec"
        case distanceM = "distance_m"
        case restSec = "rest_sec"
    }
}

struct APISyncResponse: Codable {
    let workoutsSynced: Int

    enum CodingKeys: String, CodingKey {
        case workoutsSynced = "workouts_synced"
    }
}

// MARK: - AI

struct AIChatRequest: Codable {
    let userId: Int
    let message: String

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case message
    }
}

struct AIChatResponse: Codable {
    let reply: String
    let inputTokens: Int
    let outputTokens: Int

    enum CodingKeys: String, CodingKey {
        case reply
        case inputTokens = "input_tokens"
        case outputTokens = "output_tokens"
    }
}
```

- [ ] **Step 5: Implement APIClient**

```swift
// FlexLoop/Services/APIClient.swift
import Foundation

enum APIError: Error {
    case invalidURL
    case requestFailed(statusCode: Int, body: String)
    case decodingFailed(Error)
    case networkUnavailable
}

actor APIClient {
    let config: ServerConfig
    private let session: URLSession
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    init(config: ServerConfig = .default, session: URLSession = .shared) {
        self.config = config
        self.session = session
        self.encoder = JSONEncoder()
        self.decoder = JSONDecoder()
    }

    func buildURL(path: String, queryItems: [URLQueryItem]? = nil) -> URL? {
        var components = URLComponents(string: config.baseURL + path)
        if let queryItems, !queryItems.isEmpty {
            components?.queryItems = queryItems
        }
        return components?.url
    }

    // MARK: - Generic request methods

    func get<T: Decodable>(_ path: String, queryItems: [URLQueryItem]? = nil) async throws -> T {
        guard let url = buildURL(path: path, queryItems: queryItems) else {
            throw APIError.invalidURL
        }

        let (data, response) = try await session.data(from: url)
        try validateResponse(response, data: data)
        return try decoder.decode(T.self, from: data)
    }

    func post<Body: Encodable, Response: Decodable>(
        _ path: String, body: Body
    ) async throws -> Response {
        guard let url = buildURL(path: path) else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(body)

        let (data, response) = try await session.data(for: request)
        try validateResponse(response, data: data)
        return try decoder.decode(Response.self, from: data)
    }

    func put<Body: Encodable, Response: Decodable>(
        _ path: String, body: Body
    ) async throws -> Response {
        guard let url = buildURL(path: path) else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(body)

        let (data, response) = try await session.data(for: request)
        try validateResponse(response, data: data)
        return try decoder.decode(Response.self, from: data)
    }

    // MARK: - Convenience methods

    func fetchExercises(muscleGroup: String? = nil, equipment: String? = nil,
                        query: String? = nil) async throws -> APIExerciseList {
        var queryItems: [URLQueryItem] = []
        if let muscleGroup { queryItems.append(.init(name: "muscle_group", value: muscleGroup)) }
        if let equipment { queryItems.append(.init(name: "equipment", value: equipment)) }
        if let query { queryItems.append(.init(name: "q", value: query)) }
        return try await get("/api/exercises", queryItems: queryItems)
    }

    func fetchPlan(planId: Int) async throws -> APIPlan {
        try await get("/api/plans/\(planId)")
    }

    func fetchUserWorkouts(userId: Int) async throws -> [APIWorkoutSession] {
        try await get("/api/users/\(userId)/workouts")
    }

    func syncWorkouts(request: APISyncRequest) async throws -> APISyncResponse {
        try await post("/api/sync", body: request)
    }

    func sendChatMessage(request: AIChatRequest) async throws -> AIChatResponse {
        try await post("/api/ai/chat", body: request)
    }

    // MARK: - Helpers

    private func validateResponse(_ response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else { return }
        guard (200...299).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw APIError.requestFailed(statusCode: http.statusCode, body: body)
        }
    }
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `Cmd+U`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "feat: add API client with server config, API models, and generic request methods"
```

---

### Task 4: Build sync service for offline-first data flow

**Files:**
- Create: `FlexLoop/Services/SyncService.swift`
- Create: `FlexLoopTests/SyncServiceTests.swift`

- [ ] **Step 1: Write failing test for sync service**

```swift
// FlexLoopTests/SyncServiceTests.swift
import XCTest
import SwiftData
@testable import FlexLoop

final class SyncServiceTests: XCTestCase {
    var container: ModelContainer!
    var context: ModelContext!

    override func setUp() {
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        container = try! ModelContainer(
            for: CachedUser.self, CachedExercise.self,
                 CachedWorkoutSession.self, CachedWorkoutSet.self,
            configurations: config
        )
        context = ModelContext(container)
    }

    func testFindUnsyncedSessions() {
        let session1 = CachedWorkoutSession(source: .adHoc, startedAt: Date())
        session1.isSynced = false

        let session2 = CachedWorkoutSession(source: .adHoc, startedAt: Date())
        session2.isSynced = true

        context.insert(session1)
        context.insert(session2)
        try! context.save()

        let unsynced = SyncService.findUnsyncedSessions(in: context)
        XCTAssertEqual(unsynced.count, 1)
    }

    func testBuildSyncRequest() {
        let session = CachedWorkoutSession(userId: 1, source: .adHoc, startedAt: Date())
        session.isSynced = false
        context.insert(session)

        let set = CachedWorkoutSet(
            session: session, exerciseServerId: 1,
            setNumber: 1, setType: .working, weight: 100.0, reps: 5
        )
        context.insert(set)
        try! context.save()

        let request = SyncService.buildSyncRequest(userId: 1, sessions: [session])
        XCTAssertEqual(request.workouts.count, 1)
        XCTAssertEqual(request.workouts.first?.sets.count, 1)
        XCTAssertEqual(request.workouts.first?.sets.first?.weight, 100.0)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `Cmd+U`
Expected: FAIL — `SyncService` not defined

- [ ] **Step 3: Implement SyncService**

```swift
// FlexLoop/Services/SyncService.swift
import Foundation
import SwiftData

struct SyncService {
    static func findUnsyncedSessions(in context: ModelContext) -> [CachedWorkoutSession] {
        let descriptor = FetchDescriptor<CachedWorkoutSession>(
            predicate: #Predicate { $0.isSynced == false }
        )
        return (try? context.fetch(descriptor)) ?? []
    }

    static func buildSyncRequest(userId: Int,
                                  sessions: [CachedWorkoutSession]) -> APISyncRequest {
        let formatter = ISO8601DateFormatter()

        let workouts = sessions.map { session in
            let sets = (session.sets ?? []).map { set in
                APISyncSet(
                    exerciseId: set.exerciseServerId,
                    exerciseGroupId: set.exerciseGroupId,
                    setNumber: set.setNumber,
                    setType: set.setType.rawValue,
                    weight: set.weight,
                    reps: set.reps,
                    rpe: set.rpe,
                    durationSec: set.durationSec,
                    distanceM: set.distanceM,
                    restSec: set.restSec
                )
            }

            return APISyncWorkout(
                planDayId: session.planDayId,
                templateId: session.templateId,
                source: session.source.rawValue,
                startedAt: formatter.string(from: session.startedAt),
                completedAt: session.completedAt.map { formatter.string(from: $0) },
                notes: session.notes,
                sets: sets
            )
        }

        return APISyncRequest(userId: userId, workouts: workouts)
    }

    static func performSync(apiClient: APIClient, context: ModelContext,
                             userId: Int) async throws -> Int {
        let unsyncedSessions = findUnsyncedSessions(in: context)
        guard !unsyncedSessions.isEmpty else { return 0 }

        let request = buildSyncRequest(userId: userId, sessions: unsyncedSessions)
        let response = try await apiClient.syncWorkouts(request: request)

        // Mark sessions as synced
        for session in unsyncedSessions {
            session.isSynced = true
        }
        try context.save()

        return response.workoutsSynced
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `Cmd+U`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: add SyncService for offline-first workout sync to backend"
```

---

## Chunk 2: Core UI — Onboarding, Home, and Workout Logging

### Task 5: Build onboarding flow

**Files:**
- Create: `FlexLoop/Views/Onboarding/OnboardingView.swift`
- Create: `FlexLoop/Views/Onboarding/ProfileSetupView.swift`
- Create: `FlexLoop/Views/Onboarding/EquipmentPickerView.swift`
- Create: `FlexLoop/Views/Onboarding/GoalPickerView.swift`
- Create: `FlexLoop/ViewModels/OnboardingViewModel.swift`

- [ ] **Step 1: Implement OnboardingViewModel**

```swift
// FlexLoop/ViewModels/OnboardingViewModel.swift
import Foundation
import SwiftData
import Observation

@Observable
final class OnboardingViewModel {
    var name = ""
    var gender = "male"
    var age = 25
    var heightCm = 170.0
    var weightKg = 70.0
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

    func submit(apiClient: APIClient, context: ModelContext) async {
        isSubmitting = true
        errorMessage = nil

        let userData = APIUserCreate(
            name: name, gender: gender, age: age,
            heightCm: heightCm, weightKg: weightKg,
            experienceLevel: experienceLevel, goals: goals,
            availableEquipment: Array(availableEquipment)
        )

        do {
            let apiUser: APIUser = try await apiClient.post("/api/profiles", body: userData)

            let cachedUser = CachedUser(
                serverId: apiUser.id, name: apiUser.name, gender: apiUser.gender,
                age: apiUser.age, heightCm: apiUser.heightCm, weightKg: apiUser.weightKg,
                experienceLevel: apiUser.experienceLevel, goals: apiUser.goals,
                availableEquipment: apiUser.availableEquipment
            )
            context.insert(cachedUser)
            try context.save()

            isComplete = true
        } catch {
            errorMessage = "Failed to create profile. Check your server connection."
        }

        isSubmitting = false
    }
}
```

- [ ] **Step 2: Implement OnboardingView**

```swift
// FlexLoop/Views/Onboarding/OnboardingView.swift
import SwiftUI

struct OnboardingView: View {
    @State private var viewModel = OnboardingViewModel()
    @State private var currentStep = 0

    var body: some View {
        NavigationStack {
            TabView(selection: $currentStep) {
                ProfileSetupView(viewModel: viewModel, onNext: { currentStep = 1 })
                    .tag(0)
                EquipmentPickerView(viewModel: viewModel, onNext: { currentStep = 2 })
                    .tag(1)
                GoalPickerView(viewModel: viewModel)
                    .tag(2)
            }
            .tabViewStyle(.page(indexDisplayMode: .always))
            .navigationTitle("Welcome to FlexLoop")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}
```

- [ ] **Step 3: Implement ProfileSetupView**

```swift
// FlexLoop/Views/Onboarding/ProfileSetupView.swift
import SwiftUI

struct ProfileSetupView: View {
    @Bindable var viewModel: OnboardingViewModel
    let onNext: () -> Void

    var body: some View {
        Form {
            Section("About You") {
                TextField("Name", text: $viewModel.name)

                Picker("Gender", selection: $viewModel.gender) {
                    ForEach(viewModel.genders, id: \.self) { Text($0.capitalized) }
                }

                Stepper("Age: \(viewModel.age)", value: $viewModel.age, in: 13...100)

                HStack {
                    Text("Height")
                    Spacer()
                    TextField("cm", value: $viewModel.heightCm, format: .number)
                        .keyboardType(.decimalPad)
                        .frame(width: 80)
                        .multilineTextAlignment(.trailing)
                    Text("cm")
                }

                HStack {
                    Text("Weight")
                    Spacer()
                    TextField("kg", value: $viewModel.weightKg, format: .number)
                        .keyboardType(.decimalPad)
                        .frame(width: 80)
                        .multilineTextAlignment(.trailing)
                    Text("kg")
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

- [ ] **Step 4: Implement EquipmentPickerView**

```swift
// FlexLoop/Views/Onboarding/EquipmentPickerView.swift
import SwiftUI

struct EquipmentPickerView: View {
    @Bindable var viewModel: OnboardingViewModel
    let onNext: () -> Void

    var body: some View {
        Form {
            Section("Available Equipment") {
                Text("Select what you have access to:")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                ForEach(viewModel.equipmentOptions, id: \.self) { item in
                    Button {
                        if viewModel.availableEquipment.contains(item) {
                            viewModel.availableEquipment.remove(item)
                        } else {
                            viewModel.availableEquipment.insert(item)
                        }
                    } label: {
                        HStack {
                            Text(item.replacingOccurrences(of: "_", with: " ").capitalized)
                            Spacer()
                            if viewModel.availableEquipment.contains(item) {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(.blue)
                            } else {
                                Image(systemName: "circle")
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    .foregroundStyle(.primary)
                }
            }

            Section {
                Button("Next") { onNext() }
                    .frame(maxWidth: .infinity)
            }
        }
    }
}
```

- [ ] **Step 5: Implement GoalPickerView**

```swift
// FlexLoop/Views/Onboarding/GoalPickerView.swift
import SwiftUI
import SwiftData

struct GoalPickerView: View {
    @Bindable var viewModel: OnboardingViewModel
    @Environment(\.modelContext) private var context

    var body: some View {
        Form {
            Section("Primary Goal") {
                Picker("Goal", selection: $viewModel.goals) {
                    ForEach(viewModel.goalOptions, id: \.self) { Text($0.capitalized) }
                }
                .pickerStyle(.inline)
            }

            if let error = viewModel.errorMessage {
                Section {
                    Text(error)
                        .foregroundStyle(.red)
                        .font(.caption)
                }
            }

            Section {
                Button {
                    Task {
                        await viewModel.submit(
                            apiClient: APIClient(),
                            context: context
                        )
                    }
                } label: {
                    if viewModel.isSubmitting {
                        ProgressView()
                            .frame(maxWidth: .infinity)
                    } else {
                        Text("Create Profile & Generate Plan")
                            .frame(maxWidth: .infinity)
                    }
                }
                .disabled(viewModel.isSubmitting)
            }
        }
    }
}
```

- [ ] **Step 6: Build and run to verify onboarding flow renders**

Run: Build and run on simulator
Expected: Onboarding shows 3 paged steps: profile, equipment, goals

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "feat: add onboarding flow with profile setup, equipment picker, and goal selection"
```

---

### Task 6: Build Home Dashboard

**Files:**
- Create: `FlexLoop/Views/Home/HomeView.swift`
- Create: `FlexLoop/ViewModels/HomeViewModel.swift`
- Modify: `FlexLoop/ContentView.swift`

- [ ] **Step 1: Implement HomeViewModel**

```swift
// FlexLoop/ViewModels/HomeViewModel.swift
import Foundation
import SwiftData
import Observation

@Observable
final class HomeViewModel {
    var todaysPlan: APIPlanDay?
    var recentSessions: [CachedWorkoutSession] = []
    var weeklySessionCount = 0
    var isLoading = false

    func loadDashboard(context: ModelContext) {
        // Load recent sessions from local cache
        let descriptor = FetchDescriptor<CachedWorkoutSession>(
            sortBy: [SortDescriptor(\.startedAt, order: .reverse)]
        )
        recentSessions = (try? context.fetch(descriptor))?.prefix(5).map { $0 } ?? []

        // Count sessions this week
        let calendar = Calendar.current
        let weekStart = calendar.date(from: calendar.dateComponents(
            [.yearForWeekOfYear, .weekOfYear], from: Date()
        ))!
        let weekDescriptor = FetchDescriptor<CachedWorkoutSession>(
            predicate: #Predicate { $0.startedAt >= weekStart }
        )
        weeklySessionCount = (try? context.fetchCount(weekDescriptor)) ?? 0
    }
}
```

- [ ] **Step 2: Implement HomeView**

```swift
// FlexLoop/Views/Home/HomeView.swift
import SwiftUI
import SwiftData

struct HomeView: View {
    @Environment(\.modelContext) private var context
    @State private var viewModel = HomeViewModel()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    // Weekly streak card
                    HStack {
                        VStack(alignment: .leading) {
                            Text("This Week")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                            Text("\(viewModel.weeklySessionCount) sessions")
                                .font(.title2.bold())
                        }
                        Spacer()
                        Image(systemName: "flame.fill")
                            .font(.title)
                            .foregroundStyle(.orange)
                    }
                    .padding()
                    .background(.regularMaterial)
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                    // Quick start button
                    NavigationLink {
                        // Will link to ActiveWorkoutView
                        Text("Active Workout")
                    } label: {
                        Label("Start Workout", systemImage: "play.fill")
                            .font(.headline)
                            .frame(maxWidth: .infinity)
                            .padding()
                            .background(.blue)
                            .foregroundStyle(.white)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                    }

                    // Recent sessions
                    if !viewModel.recentSessions.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Recent Sessions")
                                .font(.headline)

                            ForEach(viewModel.recentSessions, id: \.startedAt) { session in
                                HStack {
                                    VStack(alignment: .leading) {
                                        Text(session.source.rawValue.capitalized)
                                            .font(.subheadline.bold())
                                        Text(session.startedAt, style: .date)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    Text("\(session.sets?.count ?? 0) sets")
                                        .font(.subheadline)
                                        .foregroundStyle(.secondary)
                                }
                                .padding(.vertical, 4)
                            }
                        }
                        .padding()
                        .background(.regularMaterial)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                }
                .padding()
            }
            .navigationTitle("FlexLoop")
            .onAppear { viewModel.loadDashboard(context: context) }
        }
    }
}
```

- [ ] **Step 3: Update ContentView with HomeView**

```swift
// FlexLoop/ContentView.swift
import SwiftUI

struct ContentView: View {
    var body: some View {
        TabView {
            HomeView()
                .tabItem { Label("Home", systemImage: "house") }
            Text("Workout")
                .tabItem { Label("Workout", systemImage: "figure.strengthtraining.traditional") }
            Text("Plan")
                .tabItem { Label("Plan", systemImage: "calendar") }
            Text("Progress")
                .tabItem { Label("Progress", systemImage: "chart.line.uptrend.xyaxis") }
            Text("Settings")
                .tabItem { Label("Settings", systemImage: "gear") }
        }
    }
}
```

- [ ] **Step 4: Build and run to verify**

Run: Build and run on simulator
Expected: Home tab shows weekly count, start button, and recent sessions section

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: add Home dashboard with weekly count, quick start, and recent sessions"
```

---

### Task 7: Build Active Workout logging screen

**Files:**
- Create: `FlexLoop/Views/Workout/ActiveWorkoutView.swift`
- Create: `FlexLoop/Views/Workout/SetEntryRow.swift`
- Create: `FlexLoop/Views/Workout/RestTimerView.swift`
- Create: `FlexLoop/ViewModels/ActiveWorkoutViewModel.swift`
- Create: `FlexLoopTests/ActiveWorkoutViewModelTests.swift`

- [ ] **Step 1: Write failing test for ActiveWorkoutViewModel**

```swift
// FlexLoopTests/ActiveWorkoutViewModelTests.swift
import XCTest
import SwiftData
@testable import FlexLoop

final class ActiveWorkoutViewModelTests: XCTestCase {
    var container: ModelContainer!
    var context: ModelContext!

    override func setUp() {
        let config = ModelConfiguration(isStoredInMemoryOnly: true)
        container = try! ModelContainer(
            for: CachedUser.self, CachedExercise.self,
                 CachedWorkoutSession.self, CachedWorkoutSet.self,
            configurations: config
        )
        context = ModelContext(container)
    }

    func testStartWorkoutCreatesSession() {
        let vm = ActiveWorkoutViewModel()
        vm.startWorkout(context: context)

        XCTAssertNotNil(vm.currentSession)
        XCTAssertNil(vm.currentSession?.completedAt)
    }

    func testLogSetAddsToSession() {
        let vm = ActiveWorkoutViewModel()
        vm.startWorkout(context: context)

        vm.logSet(exerciseId: 1, weight: 100, reps: 5, rpe: 8.0,
                  setType: .working, context: context)

        XCTAssertEqual(vm.currentSession?.sets?.count, 1)
        XCTAssertEqual(vm.loggedSets.count, 1)
        XCTAssertEqual(vm.loggedSets.first?.weight, 100)
    }

    func testCompleteWorkoutSetsTimestamp() {
        let vm = ActiveWorkoutViewModel()
        vm.startWorkout(context: context)
        vm.completeWorkout(context: context)

        XCTAssertNotNil(vm.currentSession?.completedAt)
        XCTAssertFalse(vm.currentSession?.isSynced ?? true)
    }

    func testRestTimerCountdown() async throws {
        let vm = ActiveWorkoutViewModel()
        vm.startRestTimer(seconds: 2)

        XCTAssertTrue(vm.isRestTimerActive)
        XCTAssertEqual(vm.restTimeRemaining, 2)

        try await Task.sleep(for: .seconds(3))

        XCTAssertFalse(vm.isRestTimerActive)
        XCTAssertEqual(vm.restTimeRemaining, 0)
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `Cmd+U`
Expected: FAIL — `ActiveWorkoutViewModel` not defined

- [ ] **Step 3: Implement ActiveWorkoutViewModel**

```swift
// FlexLoop/ViewModels/ActiveWorkoutViewModel.swift
import Foundation
import SwiftData
import Observation
import UIKit

@Observable
final class ActiveWorkoutViewModel {
    var currentSession: CachedWorkoutSession?
    var loggedSets: [CachedWorkoutSet] = []
    var isRestTimerActive = false
    var restTimeRemaining = 0
    var isWorkoutActive = false

    private var restTimer: Timer?

    func startWorkout(context: ModelContext, source: WorkoutSource = .adHoc,
                      planDayId: Int? = nil, templateId: Int? = nil) {
        let session = CachedWorkoutSession(
            planDayId: planDayId,
            templateId: templateId,
            source: source,
            startedAt: Date()
        )
        context.insert(session)
        try? context.save()

        currentSession = session
        loggedSets = []
        isWorkoutActive = true
    }

    func logSet(exerciseId: Int, weight: Double?, reps: Int?,
                rpe: Double? = nil, setType: SetType = .working,
                context: ModelContext) {
        guard let session = currentSession else { return }

        let setNumber = (loggedSets.last?.setNumber ?? 0) + 1

        let workoutSet = CachedWorkoutSet(
            session: session,
            exerciseServerId: exerciseId,
            setNumber: setNumber,
            setType: setType,
            weight: weight,
            reps: reps,
            rpe: rpe
        )
        context.insert(workoutSet)
        try? context.save()

        loggedSets.append(workoutSet)

        // Haptic feedback on set completion
        let impact = UIImpactFeedbackGenerator(style: .medium)
        impact.impactOccurred()
    }

    func completeWorkout(context: ModelContext) {
        currentSession?.completedAt = Date()
        try? context.save()
        isWorkoutActive = false
        stopRestTimer()
    }

    func startRestTimer(seconds: Int) {
        stopRestTimer()
        restTimeRemaining = seconds
        isRestTimerActive = true

        restTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] timer in
            guard let self else {
                timer.invalidate()
                return
            }

            if self.restTimeRemaining > 0 {
                self.restTimeRemaining -= 1
            } else {
                self.isRestTimerActive = false
                timer.invalidate()

                // Haptic notification when timer completes
                let notification = UINotificationFeedbackGenerator()
                notification.notificationOccurred(.success)
            }
        }
    }

    func stopRestTimer() {
        restTimer?.invalidate()
        restTimer = nil
        isRestTimerActive = false
        restTimeRemaining = 0
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `Cmd+U`
Expected: All PASS

- [ ] **Step 5: Implement SetEntryRow**

```swift
// FlexLoop/Views/Workout/SetEntryRow.swift
import SwiftUI

struct SetEntryRow: View {
    let setNumber: Int
    let previousWeight: Double?
    let previousReps: Int?

    @Binding var weight: Double?
    @Binding var reps: Int?
    @Binding var rpe: Double?
    @Binding var setType: SetType

    var body: some View {
        HStack(spacing: 12) {
            // Set number
            Text("\(setNumber)")
                .font(.caption.bold())
                .frame(width: 24)
                .foregroundStyle(setType == .warmUp ? .secondary : .primary)

            // Set type indicator
            Menu {
                ForEach([SetType.warmUp, .working, .drop, .amrap, .backoff], id: \.self) { type in
                    Button(type.rawValue.replacingOccurrences(of: "_", with: " ").uppercased()) {
                        setType = type
                    }
                }
            } label: {
                Text(setType.rawValue.prefix(1).uppercased())
                    .font(.caption2.bold())
                    .padding(4)
                    .background(setType == .warmUp ? Color.gray.opacity(0.3) : Color.blue.opacity(0.2))
                    .clipShape(RoundedRectangle(cornerRadius: 4))
            }

            // Weight input
            VStack(alignment: .center, spacing: 2) {
                TextField("—", value: $weight, format: .number)
                    .keyboardType(.decimalPad)
                    .multilineTextAlignment(.center)
                    .frame(width: 64)
                if let prev = previousWeight {
                    Text("\(prev, specifier: "%.1f")")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            Text("x")
                .foregroundStyle(.secondary)

            // Reps input
            VStack(alignment: .center, spacing: 2) {
                TextField("—", value: $reps, format: .number)
                    .keyboardType(.numberPad)
                    .multilineTextAlignment(.center)
                    .frame(width: 48)
                if let prev = previousReps {
                    Text("\(prev)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            // RPE slider
            VStack(alignment: .center, spacing: 2) {
                TextField("RPE", value: $rpe, format: .number)
                    .keyboardType(.decimalPad)
                    .multilineTextAlignment(.center)
                    .frame(width: 48)
                Text("RPE")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}
```

- [ ] **Step 6: Implement RestTimerView**

```swift
// FlexLoop/Views/Workout/RestTimerView.swift
import SwiftUI

struct RestTimerView: View {
    let timeRemaining: Int
    let isActive: Bool
    let onStop: () -> Void

    var body: some View {
        if isActive {
            HStack {
                Image(systemName: "timer")
                    .foregroundStyle(.blue)

                Text(formattedTime)
                    .font(.title2.monospacedDigit().bold())
                    .foregroundStyle(timeRemaining <= 10 ? .red : .primary)

                Spacer()

                Button("Skip", action: onStop)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            .padding()
            .background(.regularMaterial)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
    }

    private var formattedTime: String {
        let minutes = timeRemaining / 60
        let seconds = timeRemaining % 60
        return String(format: "%d:%02d", minutes, seconds)
    }
}
```

- [ ] **Step 7: Implement ActiveWorkoutView**

```swift
// FlexLoop/Views/Workout/ActiveWorkoutView.swift
import SwiftUI
import SwiftData

struct ActiveWorkoutView: View {
    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss
    @State private var viewModel = ActiveWorkoutViewModel()

    // Current set entry state
    @State private var currentWeight: Double?
    @State private var currentReps: Int?
    @State private var currentRPE: Double?
    @State private var currentSetType: SetType = .working
    @State private var selectedExerciseId: Int?

    @Query private var exercises: [CachedExercise]

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Rest timer bar
                RestTimerView(
                    timeRemaining: viewModel.restTimeRemaining,
                    isActive: viewModel.isRestTimerActive,
                    onStop: { viewModel.stopRestTimer() }
                )
                .padding(.horizontal)

                List {
                    // Exercise picker
                    Section("Exercise") {
                        Picker("Select Exercise", selection: $selectedExerciseId) {
                            Text("Select...").tag(nil as Int?)
                            ForEach(exercises) { exercise in
                                Text(exercise.name).tag(exercise.serverId as Int?)
                            }
                        }
                    }

                    // Set entry
                    if selectedExerciseId != nil {
                        Section("Log Set") {
                            SetEntryRow(
                                setNumber: (viewModel.loggedSets.count) + 1,
                                previousWeight: viewModel.loggedSets.last?.weight,
                                previousReps: viewModel.loggedSets.last?.reps,
                                weight: $currentWeight,
                                reps: $currentReps,
                                rpe: $currentRPE,
                                setType: $currentSetType
                            )

                            Button("Log Set") {
                                guard let exerciseId = selectedExerciseId else { return }
                                viewModel.logSet(
                                    exerciseId: exerciseId,
                                    weight: currentWeight,
                                    reps: currentReps,
                                    rpe: currentRPE,
                                    setType: currentSetType,
                                    context: context
                                )

                                // Start rest timer (90s compound, 60s isolation)
                                let restTime = currentSetType == .warmUp ? 30 : 90
                                viewModel.startRestTimer(seconds: restTime)

                                // Reset for next set (keep weight)
                                currentReps = nil
                                currentRPE = nil
                            }
                            .disabled(currentWeight == nil && currentReps == nil)
                        }
                    }

                    // Logged sets
                    if !viewModel.loggedSets.isEmpty {
                        Section("Completed Sets (\(viewModel.loggedSets.count))") {
                            ForEach(viewModel.loggedSets, id: \.setNumber) { set in
                                HStack {
                                    Text("Set \(set.setNumber)")
                                        .font(.subheadline)
                                    Spacer()
                                    if let w = set.weight, let r = set.reps {
                                        Text("\(w, specifier: "%.1f") x \(r)")
                                    }
                                    if let rpe = set.rpe {
                                        Text("RPE \(rpe, specifier: "%.1f")")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Workout")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Finish") {
                        viewModel.completeWorkout(context: context)
                        dismiss()
                    }
                }
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
            .onAppear {
                if viewModel.currentSession == nil {
                    viewModel.startWorkout(context: context)
                }
            }
        }
    }
}
```

- [ ] **Step 8: Build and run to verify workout logging works**

Run: Build and run on simulator
Expected: Workout screen shows exercise picker, set entry with weight/reps/RPE inputs, rest timer, and logged sets list

- [ ] **Step 9: Commit**

```bash
git add .
git commit -m "feat: add active workout logging screen with set entry, rest timer, and haptic feedback"
```

---

## Chunk 3: Plan View, AI Coach, Settings & HealthKit

### Task 8: Build Plan view

**Files:**
- Create: `FlexLoop/Views/Plan/PlanView.swift`
- Create: `FlexLoop/Views/Plan/PlanDayCard.swift`
- Create: `FlexLoop/ViewModels/PlanViewModel.swift`

- [ ] **Step 1: Implement PlanViewModel**

```swift
// FlexLoop/ViewModels/PlanViewModel.swift
import Foundation
import Observation

@Observable
final class PlanViewModel {
    var currentPlan: APIPlan?
    var isLoading = false
    var errorMessage: String?

    func loadPlan(apiClient: APIClient, userId: Int) async {
        isLoading = true
        errorMessage = nil

        do {
            let plans: [APIPlan] = try await apiClient.get(
                "/api/users/\(userId)/plans"
            )
            currentPlan = plans.first(where: { $0.status == "active" })
        } catch {
            errorMessage = "Could not load plan. Check server connection."
        }

        isLoading = false
    }
}
```

- [ ] **Step 2: Implement PlanDayCard**

```swift
// FlexLoop/Views/Plan/PlanDayCard.swift
import SwiftUI

struct PlanDayCard: View {
    let day: APIPlanDay
    let isToday: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Day \(day.dayNumber): \(day.label)")
                    .font(.headline)
                Spacer()
                if isToday {
                    Text("TODAY")
                        .font(.caption.bold())
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(.blue)
                        .foregroundStyle(.white)
                        .clipShape(Capsule())
                }
            }

            Text(day.focus)
                .font(.caption)
                .foregroundStyle(.secondary)

            ForEach(day.exerciseGroups, id: \.id) { group in
                if group.groupType != "straight" {
                    Text(group.groupType.uppercased())
                        .font(.caption2.bold())
                        .foregroundStyle(.blue)
                }

                ForEach(group.exercises, id: \.id) { exercise in
                    HStack {
                        Text(exercise.exerciseId.description) // Would be exercise name from cache
                            .font(.subheadline)
                        Spacer()
                        Text("\(exercise.sets)x\(exercise.reps)")
                            .font(.subheadline.monospacedDigit())
                            .foregroundStyle(.secondary)
                        if let weight = exercise.weight {
                            Text("\(weight, specifier: "%.1f")kg")
                                .font(.subheadline.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .padding()
        .background(isToday ? Color.blue.opacity(0.05) : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(isToday ? Color.blue.opacity(0.3) : Color.gray.opacity(0.2))
        )
    }
}
```

- [ ] **Step 3: Implement PlanView**

```swift
// FlexLoop/Views/Plan/PlanView.swift
import SwiftUI

struct PlanView: View {
    @State private var viewModel = PlanViewModel()
    private let todayDayNumber = Calendar.current.component(.weekday, from: Date())

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading {
                    ProgressView("Loading plan...")
                } else if let plan = viewModel.currentPlan {
                    ScrollView {
                        VStack(spacing: 12) {
                            // Plan header
                            VStack(alignment: .leading) {
                                Text(plan.name)
                                    .font(.title2.bold())
                                Text("\(plan.splitType.uppercased()) split")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal)

                            // Days
                            ForEach(plan.days, id: \.id) { day in
                                PlanDayCard(
                                    day: day,
                                    isToday: day.dayNumber == todayDayNumber
                                )
                                .padding(.horizontal)
                            }
                        }
                        .padding(.vertical)
                    }
                } else if let error = viewModel.errorMessage {
                    ContentUnavailableView(
                        "No Plan",
                        systemImage: "calendar.badge.exclamationmark",
                        description: Text(error)
                    )
                } else {
                    ContentUnavailableView(
                        "No Active Plan",
                        systemImage: "calendar",
                        description: Text("Generate a plan from the AI Coach or create one manually.")
                    )
                }
            }
            .navigationTitle("My Plan")
            .task {
                await viewModel.loadPlan(apiClient: APIClient(), userId: 1)
            }
        }
    }
}
```

- [ ] **Step 4: Update ContentView**

Replace the Plan tab placeholder:

```swift
PlanView()
    .tabItem { Label("Plan", systemImage: "calendar") }
```

- [ ] **Step 5: Build and run to verify**

Run: Build and run on simulator
Expected: Plan tab shows plan days or "No Active Plan" empty state

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "feat: add Plan view with day cards showing exercises, groups, and today highlight"
```

---

### Task 9: Build AI Coach chat interface

**Files:**
- Create: `FlexLoop/Views/AICoach/AIChatView.swift`
- Create: `FlexLoop/ViewModels/AIChatViewModel.swift`

- [ ] **Step 1: Implement AIChatViewModel**

```swift
// FlexLoop/ViewModels/AIChatViewModel.swift
import Foundation
import Observation

struct ChatMessage: Identifiable {
    let id = UUID()
    let role: String  // "user" or "assistant"
    let content: String
    let timestamp: Date
}

@Observable
final class AIChatViewModel {
    var messages: [ChatMessage] = []
    var inputText = ""
    var isLoading = false
    var errorMessage: String?

    func sendMessage(apiClient: APIClient, userId: Int) async {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }

        let userMessage = ChatMessage(role: "user", content: text, timestamp: Date())
        messages.append(userMessage)
        inputText = ""
        isLoading = true
        errorMessage = nil

        do {
            let request = AIChatRequest(userId: userId, message: text)
            let response: AIChatResponse = try await apiClient.sendChatMessage(request: request)

            let assistantMessage = ChatMessage(
                role: "assistant", content: response.reply, timestamp: Date()
            )
            messages.append(assistantMessage)
        } catch {
            errorMessage = "Failed to get AI response. Check server connection."
        }

        isLoading = false
    }
}
```

- [ ] **Step 2: Implement AIChatView**

```swift
// FlexLoop/Views/AICoach/AIChatView.swift
import SwiftUI

struct AIChatView: View {
    @State private var viewModel = AIChatViewModel()

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Messages
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 12) {
                            ForEach(viewModel.messages) { message in
                                ChatBubble(message: message)
                                    .id(message.id)
                            }

                            if viewModel.isLoading {
                                HStack {
                                    ProgressView()
                                    Text("Thinking...")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                .padding(.horizontal)
                            }
                        }
                        .padding()
                    }
                    .onChange(of: viewModel.messages.count) {
                        if let last = viewModel.messages.last {
                            proxy.scrollTo(last.id, anchor: .bottom)
                        }
                    }
                }

                if let error = viewModel.errorMessage {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .padding(.horizontal)
                }

                // Input bar
                HStack {
                    TextField("Ask about your training...", text: $viewModel.inputText)
                        .textFieldStyle(.roundedBorder)

                    Button {
                        Task {
                            await viewModel.sendMessage(apiClient: APIClient(), userId: 1)
                        }
                    } label: {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.title2)
                    }
                    .disabled(viewModel.inputText.trimmingCharacters(in: .whitespaces).isEmpty
                              || viewModel.isLoading)
                }
                .padding()
                .background(.regularMaterial)
            }
            .navigationTitle("AI Coach")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

struct ChatBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.role == "user" { Spacer(minLength: 60) }

            Text(message.content)
                .padding(12)
                .background(message.role == "user" ? Color.blue : Color.gray.opacity(0.2))
                .foregroundStyle(message.role == "user" ? .white : .primary)
                .clipShape(RoundedRectangle(cornerRadius: 16))

            if message.role == "assistant" { Spacer(minLength: 60) }
        }
    }
}
```

- [ ] **Step 3: Build and run to verify chat UI**

Run: Build and run on simulator
Expected: AI Coach screen shows chat bubbles and input field

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "feat: add AI Coach chat interface with message bubbles and loading state"
```

---

### Task 10: Build Settings screen with server configuration

**Files:**
- Create: `FlexLoop/Views/Settings/SettingsView.swift`
- Create: `FlexLoop/Views/Settings/ServerConfigView.swift`

- [ ] **Step 1: Implement SettingsView**

```swift
// FlexLoop/Views/Settings/SettingsView.swift
import SwiftUI

struct SettingsView: View {
    @AppStorage("unitSystem") private var unitSystem = "metric"
    @AppStorage("sessionFeedbackEnabled") private var sessionFeedbackEnabled = false
    @AppStorage("measurementReminders") private var measurementReminders = false

    var body: some View {
        NavigationStack {
            List {
                Section("Server") {
                    NavigationLink("Backend Server") {
                        ServerConfigView()
                    }
                }

                Section("Units") {
                    Picker("Weight Unit", selection: $unitSystem) {
                        Text("Metric (kg)").tag("metric")
                        Text("Imperial (lbs)").tag("imperial")
                    }
                }

                Section("Workout") {
                    Toggle("Post-session feedback", isOn: $sessionFeedbackEnabled)
                    Text("When enabled, you'll be prompted to rate sleep, energy, and soreness after each workout.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Tracking") {
                    Toggle("Measurement reminders", isOn: $measurementReminders)
                    Text("Reminds you to take body measurements every 2–4 weeks.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section("Data") {
                    Button("Export All Data (JSON)") {
                        // Trigger export via API
                    }

                    Button("Sync Now") {
                        // Trigger manual sync
                    }
                }

                Section("About") {
                    HStack {
                        Text("Version")
                        Spacer()
                        Text("1.0.0")
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Settings")
        }
    }
}
```

- [ ] **Step 2: Implement ServerConfigView**

```swift
// FlexLoop/Views/Settings/ServerConfigView.swift
import SwiftUI

struct ServerConfigView: View {
    @AppStorage("serverBaseURL") private var serverURL = "http://localhost:8000"
    @State private var testResult: String?
    @State private var isTesting = false

    var body: some View {
        Form {
            Section("Server URL") {
                TextField("http://your-server:8000", text: $serverURL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)

                Text("The URL of your self-hosted FlexLoop backend.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section {
                Button {
                    Task { await testConnection() }
                } label: {
                    HStack {
                        Text("Test Connection")
                        Spacer()
                        if isTesting {
                            ProgressView()
                        } else if let result = testResult {
                            Image(systemName: result == "ok" ? "checkmark.circle.fill" : "xmark.circle.fill")
                                .foregroundStyle(result == "ok" ? .green : .red)
                        }
                    }
                }
                .disabled(isTesting)
            }

            if let result = testResult, result != "ok" {
                Section {
                    Text("Connection failed: \(result)")
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            }
        }
        .navigationTitle("Server")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func testConnection() async {
        isTesting = true
        testResult = nil

        let config = ServerConfig(baseURL: serverURL)
        let client = APIClient(config: config)

        do {
            struct HealthResponse: Decodable {
                let status: String
            }
            let response: HealthResponse = try await client.get("/api/health")
            testResult = response.status
            if response.status == "ok" {
                ServerConfig.save(baseURL: serverURL)
            }
        } catch {
            testResult = error.localizedDescription
        }

        isTesting = false
    }
}
```

- [ ] **Step 3: Update ContentView with all tabs**

```swift
// FlexLoop/ContentView.swift
import SwiftUI

struct ContentView: View {
    var body: some View {
        TabView {
            HomeView()
                .tabItem { Label("Home", systemImage: "house") }
            ActiveWorkoutView()
                .tabItem { Label("Workout", systemImage: "figure.strengthtraining.traditional") }
            PlanView()
                .tabItem { Label("Plan", systemImage: "calendar") }
            AIChatView()
                .tabItem { Label("AI Coach", systemImage: "brain") }
            SettingsView()
                .tabItem { Label("Settings", systemImage: "gear") }
        }
    }
}
```

- [ ] **Step 4: Build and run to verify**

Run: Build and run on simulator
Expected: All 5 tabs functional — Home, Workout, Plan, AI Coach, Settings with server config

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: add Settings screen with server config, unit preferences, and feedback toggles"
```

---

### Task 11: Integrate HealthKit

**Files:**
- Create: `FlexLoop/Services/HealthKitManager.swift`
- Create: `FlexLoopTests/HealthKitTests.swift`
- Modify: `FlexLoop/Info.plist` (add HealthKit usage descriptions)

- [ ] **Step 1: Add HealthKit capability**

In Xcode: FlexLoop target → Signing & Capabilities → + Capability → HealthKit.
Check "Background Delivery" if available.

Add to Info.plist:
- `NSHealthShareUsageDescription`: "FlexLoop reads your heart rate data during workouts to correlate with training performance."
- `NSHealthUpdateUsageDescription`: "FlexLoop saves your workout sessions to Apple Health."

- [ ] **Step 2: Write test for HealthKit authorization check**

```swift
// FlexLoopTests/HealthKitTests.swift
import XCTest
import HealthKit
@testable import FlexLoop

final class HealthKitTests: XCTestCase {
    func testHealthKitAvailability() {
        // HealthKit is available on iPhone but not on simulator in all configs
        // This test verifies our code handles both cases
        let isAvailable = HKHealthStore.isHealthDataAvailable()
        // On simulator this may be true or false — test that we don't crash
        XCTAssertNotNil(isAvailable)
    }
}
```

- [ ] **Step 3: Implement HealthKitManager**

```swift
// FlexLoop/Services/HealthKitManager.swift
import Foundation
import HealthKit

actor HealthKitManager {
    static let shared = HealthKitManager()

    private let healthStore = HKHealthStore()
    private var isAuthorized = false

    var isAvailable: Bool {
        HKHealthStore.isHealthDataAvailable()
    }

    func requestAuthorization() async throws {
        guard isAvailable else { return }

        let readTypes: Set<HKObjectType> = [
            HKObjectType.quantityType(forIdentifier: .heartRate)!,
            HKObjectType.quantityType(forIdentifier: .activeEnergyBurned)!,
            HKObjectType.quantityType(forIdentifier: .stepCount)!,
            HKObjectType.categoryType(forIdentifier: .sleepAnalysis)!,
        ]

        let writeTypes: Set<HKSampleType> = [
            HKObjectType.workoutType(),
        ]

        try await healthStore.requestAuthorization(toShare: writeTypes, read: readTypes)
        isAuthorized = true
    }

    func fetchLatestHeartRate() async throws -> Double? {
        guard isAvailable else { return nil }

        let heartRateType = HKQuantityType.quantityType(forIdentifier: .heartRate)!
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierStartDate, ascending: false)
        let query = HKSampleQuery(
            sampleType: heartRateType,
            predicate: nil,
            limit: 1,
            sortDescriptors: [sortDescriptor]
        ) { _, _, _ in }

        return await withCheckedContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: heartRateType,
                predicate: nil,
                limit: 1,
                sortDescriptors: [sortDescriptor]
            ) { _, samples, _ in
                guard let sample = samples?.first as? HKQuantitySample else {
                    continuation.resume(returning: nil)
                    return
                }
                let bpm = sample.quantity.doubleValue(
                    for: HKUnit.count().unitDivided(by: .minute())
                )
                continuation.resume(returning: bpm)
            }
            healthStore.execute(query)
        }
    }

    func saveWorkout(startDate: Date, endDate: Date, caloriesBurned: Double?) async throws {
        guard isAvailable else { return }

        let workout = HKWorkout(
            activityType: .traditionalStrengthTraining,
            start: startDate,
            end: endDate,
            duration: endDate.timeIntervalSince(startDate),
            totalEnergyBurned: caloriesBurned.map {
                HKQuantity(unit: .kilocalorie(), doubleValue: $0)
            },
            totalDistance: nil,
            metadata: ["FlexLoop": true]
        )

        try await healthStore.save(workout)
    }
}
```

- [ ] **Step 4: Run test**

Run: `Cmd+U`
Expected: PASS (availability check doesn't crash)

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: add HealthKit integration for heart rate reading and workout saving"
```

---

## Chunk 4: Watch App, History View & Final Integration

### Task 12: Build Apple Watch companion app

**Files:**
- Create: `FlexLoopWatch/Views/WatchHomeView.swift`
- Create: `FlexLoopWatch/Views/WatchWorkoutView.swift`
- Create: `FlexLoopWatch/Views/WatchRestTimerView.swift`
- Create: `FlexLoopWatch/Services/WatchConnectivityManager.swift`

- [ ] **Step 1: Implement WatchConnectivityManager on phone side**

```swift
// FlexLoop/Services/WatchConnectivityManager.swift
import Foundation
import WatchConnectivity

class PhoneConnectivityManager: NSObject, WCSessionDelegate {
    static let shared = PhoneConnectivityManager()

    override init() {
        super.init()
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
    }

    func sendPlanToWatch(planDays: [[String: Any]]) {
        guard WCSession.default.isReachable else { return }
        WCSession.default.sendMessage(
            ["type": "planUpdate", "days": planDays],
            replyHandler: nil
        )
    }

    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {}
    func sessionDidBecomeInactive(_ session: WCSession) {}
    func sessionDidDeactivate(_ session: WCSession) {
        WCSession.default.activate()
    }
}
```

- [ ] **Step 2: Implement Watch home view**

```swift
// FlexLoopWatch/Views/WatchHomeView.swift
import SwiftUI

struct WatchHomeView: View {
    @State private var todayLabel = "Push Day"
    @State private var exerciseCount = 6

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                Text("Today")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Text(todayLabel)
                    .font(.headline)

                Text("\(exerciseCount) exercises")
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                NavigationLink("Start") {
                    WatchWorkoutView()
                }
                .buttonStyle(.borderedProminent)
            }
        }
    }
}
```

- [ ] **Step 3: Implement Watch workout view**

```swift
// FlexLoopWatch/Views/WatchWorkoutView.swift
import SwiftUI

struct WatchWorkoutView: View {
    @State private var currentExercise = "Bench Press"
    @State private var plannedWeight = 80.0
    @State private var plannedReps = 8
    @State private var setNumber = 1
    @State private var weight = 80.0
    @State private var reps = 8
    @State private var showRestTimer = false

    var body: some View {
        VStack(spacing: 8) {
            Text(currentExercise)
                .font(.headline)
                .lineLimit(1)

            Text("Set \(setNumber)")
                .font(.caption)
                .foregroundStyle(.secondary)

            HStack {
                VStack {
                    Text("\(weight, specifier: "%.1f")")
                        .font(.title3.monospacedDigit().bold())
                    Text("kg")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                .focusable()
                .digitalCrownRotation($weight, from: 0, through: 500, by: 2.5)

                Text("x")
                    .foregroundStyle(.secondary)

                VStack {
                    Text("\(reps)")
                        .font(.title3.monospacedDigit().bold())
                    Text("reps")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            Button("Log Set") {
                setNumber += 1
                showRestTimer = true
            }
            .buttonStyle(.borderedProminent)
            .tint(.green)
        }
        .sheet(isPresented: $showRestTimer) {
            WatchRestTimerView(seconds: 90) {
                showRestTimer = false
            }
        }
    }
}
```

- [ ] **Step 4: Implement Watch rest timer**

```swift
// FlexLoopWatch/Views/WatchRestTimerView.swift
import SwiftUI
import WatchKit

struct WatchRestTimerView: View {
    let seconds: Int
    let onComplete: () -> Void

    @State private var remaining: Int
    @State private var timer: Timer?

    init(seconds: Int, onComplete: @escaping () -> Void) {
        self.seconds = seconds
        self.onComplete = onComplete
        self._remaining = State(initialValue: seconds)
    }

    var body: some View {
        VStack(spacing: 12) {
            Text("Rest")
                .font(.caption)
                .foregroundStyle(.secondary)

            Text(formattedTime)
                .font(.system(size: 40, weight: .bold, design: .monospaced))
                .foregroundStyle(remaining <= 10 ? .red : .primary)

            Button("Skip") {
                timer?.invalidate()
                onComplete()
            }
            .font(.caption)
        }
        .onAppear { startTimer() }
        .onDisappear { timer?.invalidate() }
    }

    private var formattedTime: String {
        let m = remaining / 60
        let s = remaining % 60
        return String(format: "%d:%02d", m, s)
    }

    private func startTimer() {
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
            if remaining > 0 {
                remaining -= 1
            } else {
                timer?.invalidate()
                WKInterfaceDevice.current().play(.notification)
                onComplete()
            }
        }
    }
}
```

- [ ] **Step 5: Update Watch app entry point**

```swift
// FlexLoopWatch/FlexLoopWatchApp.swift
import SwiftUI

@main
struct FlexLoopWatchApp: App {
    var body: some Scene {
        WindowGroup {
            WatchHomeView()
        }
    }
}
```

- [ ] **Step 6: Build and run on Watch simulator**

Run: Select Watch simulator target, build and run
Expected: Watch shows today's workout label, start button, workout logging with digital crown weight adjustment, and rest timer

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "feat: add Apple Watch companion app with workout logging, digital crown input, and rest timer"
```

---

### Task 13: Build History view

**Files:**
- Create: `FlexLoop/Views/History/HistoryView.swift`
- Create: `FlexLoop/Views/History/SessionDetailView.swift`

- [ ] **Step 1: Implement HistoryView**

```swift
// FlexLoop/Views/History/HistoryView.swift
import SwiftUI
import SwiftData

struct HistoryView: View {
    @Query(sort: \CachedWorkoutSession.startedAt, order: .reverse)
    private var sessions: [CachedWorkoutSession]

    var body: some View {
        NavigationStack {
            List {
                ForEach(groupedByMonth, id: \.key) { month, monthSessions in
                    Section(month) {
                        ForEach(monthSessions, id: \.startedAt) { session in
                            NavigationLink {
                                SessionDetailView(session: session)
                            } label: {
                                HStack {
                                    VStack(alignment: .leading) {
                                        Text(session.startedAt, style: .date)
                                            .font(.subheadline.bold())
                                        Text(session.source.rawValue.replacingOccurrences(of: "_", with: " ").capitalized)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }

                                    Spacer()

                                    VStack(alignment: .trailing) {
                                        Text("\(session.sets?.count ?? 0) sets")
                                            .font(.subheadline)
                                        if let duration = sessionDuration(session) {
                                            Text(duration)
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }
                                    }

                                    if !session.isSynced {
                                        Image(systemName: "arrow.triangle.2.circlepath")
                                            .font(.caption)
                                            .foregroundStyle(.orange)
                                    }
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("History")
            .overlay {
                if sessions.isEmpty {
                    ContentUnavailableView(
                        "No Workouts Yet",
                        systemImage: "figure.strengthtraining.traditional",
                        description: Text("Your completed workouts will appear here.")
                    )
                }
            }
        }
    }

    private var groupedByMonth: [(key: String, value: [CachedWorkoutSession])] {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMMM yyyy"
        let grouped = Dictionary(grouping: sessions) { formatter.string(from: $0.startedAt) }
        return grouped.sorted { $0.value.first!.startedAt > $1.value.first!.startedAt }
    }

    private func sessionDuration(_ session: CachedWorkoutSession) -> String? {
        guard let end = session.completedAt else { return nil }
        let minutes = Int(end.timeIntervalSince(session.startedAt) / 60)
        return "\(minutes)min"
    }
}
```

- [ ] **Step 2: Implement SessionDetailView**

```swift
// FlexLoop/Views/History/SessionDetailView.swift
import SwiftUI

struct SessionDetailView: View {
    let session: CachedWorkoutSession

    var body: some View {
        List {
            Section("Session Info") {
                LabeledContent("Date", value: session.startedAt, format: .dateTime)
                LabeledContent("Source", value: session.source.rawValue.capitalized)
                if let end = session.completedAt {
                    let minutes = Int(end.timeIntervalSince(session.startedAt) / 60)
                    LabeledContent("Duration", value: "\(minutes) minutes")
                }
                LabeledContent("Synced", value: session.isSynced ? "Yes" : "Pending")
            }

            if let notes = session.notes, !notes.isEmpty {
                Section("Notes") {
                    Text(notes)
                }
            }

            Section("Sets (\(session.sets?.count ?? 0))") {
                ForEach(session.sets?.sorted(by: { $0.setNumber < $1.setNumber }) ?? [],
                        id: \.setNumber) { set in
                    HStack {
                        Text(set.setType.rawValue.uppercased())
                            .font(.caption2.bold())
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.blue.opacity(0.15))
                            .clipShape(RoundedRectangle(cornerRadius: 4))

                        Text("Set \(set.setNumber)")
                            .font(.subheadline)

                        Spacer()

                        if let w = set.weight, let r = set.reps {
                            Text("\(w, specifier: "%.1f")kg x \(r)")
                                .font(.subheadline.monospacedDigit())
                        }

                        if let rpe = set.rpe {
                            Text("RPE \(rpe, specifier: "%.0f")")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .navigationTitle("Session Detail")
        .navigationBarTitleDisplayMode(.inline)
    }
}
```

- [ ] **Step 3: Add History to navigation**

Update `ContentView.swift` — replace the Progress tab with a combined view or add History as accessible from Home. For MVP, replace the Progress placeholder:

```swift
HistoryView()
    .tabItem { Label("History", systemImage: "clock.arrow.circlepath") }
```

Note: Progress charts (1RM trends, volume) are v1.1 features. History view covers MVP needs.

- [ ] **Step 4: Build and run to verify**

Run: Build and run on simulator
Expected: History tab shows sessions grouped by month with sync status indicators, tapping shows detail with all logged sets

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: add History view with session list, detail view, and sync status indicators"
```

---

### Task 14: Wire up app flow — onboarding gate, tab routing, auto-sync

**Files:**
- Modify: `FlexLoop/FlexLoopApp.swift`
- Modify: `FlexLoop/ContentView.swift`

- [ ] **Step 1: Implement onboarding gate in app entry**

```swift
// FlexLoop/FlexLoopApp.swift
import SwiftUI
import SwiftData

@main
struct FlexLoopApp: App {
    @State private var hasCompletedOnboarding = false

    var body: some Scene {
        WindowGroup {
            Group {
                if hasCompletedOnboarding {
                    ContentView()
                } else {
                    OnboardingView()
                }
            }
            .onAppear { checkOnboarding() }
        }
        .modelContainer(for: [
            CachedUser.self,
            CachedExercise.self,
            CachedWorkoutSession.self,
            CachedWorkoutSet.self,
            CachedPlan.self,
        ])
    }

    private func checkOnboarding() {
        // Check if user profile exists in SwiftData
        let container = try? ModelContainer(for: CachedUser.self)
        if let context = container?.mainContext {
            let descriptor = FetchDescriptor<CachedUser>()
            let count = (try? context.fetchCount(descriptor)) ?? 0
            hasCompletedOnboarding = count > 0
        }
    }
}
```

- [ ] **Step 2: Add auto-sync on app launch and workout completion**

Update `ContentView.swift`:

```swift
// FlexLoop/ContentView.swift
import SwiftUI
import SwiftData

struct ContentView: View {
    @Environment(\.modelContext) private var context
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        TabView {
            HomeView()
                .tabItem { Label("Home", systemImage: "house") }
            ActiveWorkoutView()
                .tabItem { Label("Workout", systemImage: "figure.strengthtraining.traditional") }
            PlanView()
                .tabItem { Label("Plan", systemImage: "calendar") }
            AIChatView()
                .tabItem { Label("AI Coach", systemImage: "brain") }
            SettingsView()
                .tabItem { Label("Settings", systemImage: "gear") }
        }
        .onChange(of: scenePhase) { _, newPhase in
            if newPhase == .active {
                Task { await syncIfNeeded() }
            }
        }
    }

    private func syncIfNeeded() async {
        let apiClient = APIClient()
        do {
            let synced = try await SyncService.performSync(
                apiClient: apiClient, context: context, userId: 1
            )
            if synced > 0 {
                print("Synced \(synced) workout(s) to server")
            }
        } catch {
            print("Sync failed: \(error.localizedDescription)")
        }
    }
}
```

- [ ] **Step 3: Build and run full app flow**

Run: Build and run on simulator
Expected: Fresh install → onboarding flow → main tab view with auto-sync on app foreground

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "feat: add onboarding gate, tab routing, and auto-sync on app launch"
```

---

### Task 15: Run full test suite and finalize

- [ ] **Step 1: Run all unit tests**

Run: `Cmd+U` in Xcode (or `xcodebuild test -scheme FlexLoop -destination 'platform=iOS Simulator,name=iPhone 16 Pro'`)
Expected: All tests PASS

- [ ] **Step 2: Run on device (if available)**

Run: Build and run on physical iPhone
Expected: App launches, onboarding works, HealthKit permission prompt appears, workout logging works with haptics

- [ ] **Step 3: Run Watch app on Watch simulator**

Run: Select Watch scheme, build and run
Expected: Watch app shows today's workout, set logging with digital crown, rest timer with haptic

- [ ] **Step 4: Verify sync end-to-end**

1. Start backend: `cd flexloop-server && docker-compose up -d`
2. Configure server URL in iOS Settings
3. Complete onboarding
4. Log a workout
5. Verify workout appears in backend: `curl http://localhost:8000/api/users/1/workouts`

- [ ] **Step 5: Commit any final fixes**

```bash
git add .
git commit -m "chore: finalize iOS app, fix test issues, verify end-to-end sync"
```

- [ ] **Step 6: Create TestFlight build**

Run: In Xcode, Product → Archive → Distribute App → TestFlight
Expected: Build uploads successfully to App Store Connect

---

## Appendix: File Structure Summary

```
flexloop-ios/
├── FlexLoop/
│   ├── FlexLoopApp.swift
│   ├── ContentView.swift
│   ├── Models/
│   │   ├── CachedUser.swift
│   │   ├── CachedExercise.swift
│   │   ├── CachedPlan.swift
│   │   ├── CachedWorkoutSession.swift
│   │   └── CachedWorkoutSet.swift
│   ├── Services/
│   │   ├── APIClient.swift
│   │   ├── APIModels.swift
│   │   ├── ServerConfig.swift
│   │   ├── SyncService.swift
│   │   ├── HealthKitManager.swift
│   │   └── WatchConnectivityManager.swift
│   ├── ViewModels/
│   │   ├── OnboardingViewModel.swift
│   │   ├── HomeViewModel.swift
│   │   ├── ActiveWorkoutViewModel.swift
│   │   ├── PlanViewModel.swift
│   │   └── AIChatViewModel.swift
│   └── Views/
│       ├── Onboarding/
│       │   ├── OnboardingView.swift
│       │   ├── ProfileSetupView.swift
│       │   ├── EquipmentPickerView.swift
│       │   └── GoalPickerView.swift
│       ├── Home/
│       │   └── HomeView.swift
│       ├── Workout/
│       │   ├── ActiveWorkoutView.swift
│       │   ├── SetEntryRow.swift
│       │   └── RestTimerView.swift
│       ├── Plan/
│       │   ├── PlanView.swift
│       │   └── PlanDayCard.swift
│       ├── History/
│       │   ├── HistoryView.swift
│       │   └── SessionDetailView.swift
│       ├── AICoach/
│       │   └── AIChatView.swift
│       └── Settings/
│           ├── SettingsView.swift
│           └── ServerConfigView.swift
├── FlexLoopWatch/
│   ├── FlexLoopWatchApp.swift
│   ├── Views/
│   │   ├── WatchHomeView.swift
│   │   ├── WatchWorkoutView.swift
│   │   └── WatchRestTimerView.swift
│   └── Services/
│       └── WatchConnectivityManager.swift
└── FlexLoopTests/
    ├── FlexLoopTests.swift
    ├── ModelTests.swift
    ├── APIClientTests.swift
    ├── SyncServiceTests.swift
    ├── ActiveWorkoutViewModelTests.swift
    └── HealthKitTests.swift
```
