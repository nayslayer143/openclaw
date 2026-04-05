# Phase 3: AI Tagging + Instant Search

> Part of iFauxto v2 plan. Read `2026-04-04-ifauxto-v2-plan.md` first. Phases 1-2 must be complete.

**Goal:** Every photo is analyzed by Apple Vision (on-device, free) and tagged. Tags stored in SQLite FTS5 for instant search. Background indexing, never blocks UI.

---

### Task 1: Create TagStore (SQLite FTS5 wrapper)

**Files:**
- Create: `iFauxto/Services/TagStore.swift`
- Test: `iFauxtoTests/TagStoreTests.swift`

- [ ] **Step 1: Write the failing test**

Create `iFauxtoTests/TagStoreTests.swift`:

```swift
import Testing
import Foundation
@testable import iFauxto

@Suite("TagStore")
struct TagStoreTests {

    func makeStore() throws -> TagStore {
        // In-memory SQLite for testing
        return try TagStore(path: ":memory:")
    }

    @Test("Insert and search tags")
    func insertAndSearch() throws {
        let store = try makeStore()
        try store.insertTags(assetId: "photo-1", tags: [
            TagRecord(tagType: "object", tagValue: "beach", confidence: 0.95),
            TagRecord(tagType: "object", tagValue: "ocean", confidence: 0.88),
            TagRecord(tagType: "scene", tagValue: "sunset", confidence: 0.75),
        ])
        let results = try store.search(query: "beach")
        #expect(results.count == 1)
        #expect(results[0] == "photo-1")
    }

    @Test("Search returns empty for no match")
    func noMatch() throws {
        let store = try makeStore()
        try store.insertTags(assetId: "photo-1", tags: [
            TagRecord(tagType: "object", tagValue: "car", confidence: 0.9),
        ])
        let results = try store.search(query: "beach")
        #expect(results.isEmpty)
    }

    @Test("isIndexed returns correct state")
    func isIndexed() throws {
        let store = try makeStore()
        #expect(try !store.isIndexed(assetId: "photo-1"))
        try store.insertTags(assetId: "photo-1", tags: [
            TagRecord(tagType: "object", tagValue: "tree", confidence: 0.8),
        ])
        #expect(try store.isIndexed(assetId: "photo-1"))
    }

    @Test("deleteTags removes all tags for asset")
    func deleteTags() throws {
        let store = try makeStore()
        try store.insertTags(assetId: "photo-1", tags: [
            TagRecord(tagType: "object", tagValue: "cat", confidence: 0.9),
        ])
        try store.deleteTags(assetId: "photo-1")
        #expect(try !store.isIndexed(assetId: "photo-1"))
    }

    @Test("Suggestions returns unique tag values")
    func suggestions() throws {
        let store = try makeStore()
        try store.insertTags(assetId: "p1", tags: [
            TagRecord(tagType: "object", tagValue: "beach", confidence: 0.9),
        ])
        try store.insertTags(assetId: "p2", tags: [
            TagRecord(tagType: "object", tagValue: "bedroom", confidence: 0.8),
        ])
        let suggestions = try store.suggestions(prefix: "bea")
        #expect(suggestions.contains("beach"))
        #expect(!suggestions.contains("bedroom"))
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — `TagStore` type not found.

- [ ] **Step 3: Create TagStore.swift**

Create `iFauxto/Services/TagStore.swift`:

```swift
import Foundation
import SQLite3

struct TagRecord {
    let tagType: String   // "object", "text", "face", "scene", "location", "time"
    let tagValue: String
    let confidence: Float
}

final class TagStore: Sendable {
    private let db: OpaquePointer

    init(path: String = TagStore.defaultPath()) throws {
        var dbPointer: OpaquePointer?
        let result = sqlite3_open(path, &dbPointer)
        guard result == SQLITE_OK, let db = dbPointer else {
            let msg = dbPointer.flatMap { String(cString: sqlite3_errmsg($0)) } ?? "unknown"
            throw TagStoreError.openFailed(msg)
        }
        self.db = db
        try createTables()
    }

    deinit {
        sqlite3_close(db)
    }

    static func defaultPath() -> String {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("ifauxto_tags.sqlite").path
    }

    private func createTables() throws {
        let sql = """
            CREATE VIRTUAL TABLE IF NOT EXISTS photo_tags USING fts5(
                asset_id,
                tag_type,
                tag_value,
                confidence UNINDEXED
            );
            """
        try execute(sql)
    }

    // MARK: - Write

    func insertTags(assetId: String, tags: [TagRecord]) throws {
        for tag in tags {
            let sql = "INSERT INTO photo_tags (asset_id, tag_type, tag_value, confidence) VALUES (?, ?, ?, ?)"
            try execute(sql, bindings: [assetId, tag.tagType, tag.tagValue, "\(tag.confidence)"])
        }
    }

    func deleteTags(assetId: String) throws {
        try execute("DELETE FROM photo_tags WHERE asset_id = ?", bindings: [assetId])
    }

    // MARK: - Read

    func search(query: String) throws -> [String] {
        let ftsQuery = query.split(separator: " ").map { "\($0)*" }.joined(separator: " ")
        let sql = "SELECT DISTINCT asset_id FROM photo_tags WHERE tag_value MATCH ? ORDER BY rank"
        return try queryStrings(sql, bindings: [ftsQuery])
    }

    func suggestions(prefix: String) throws -> [String] {
        let sql = "SELECT DISTINCT tag_value FROM photo_tags WHERE tag_value MATCH ? LIMIT 10"
        return try queryStrings(sql, bindings: ["\(prefix)*"])
    }

    func isIndexed(assetId: String) throws -> Bool {
        let sql = "SELECT COUNT(*) FROM photo_tags WHERE asset_id = ?"
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else {
            throw TagStoreError.queryFailed(String(cString: sqlite3_errmsg(db)))
        }
        sqlite3_bind_text(stmt, 1, (assetId as NSString).utf8String, -1, nil)
        guard sqlite3_step(stmt) == SQLITE_ROW else { return false }
        return sqlite3_column_int(stmt, 0) > 0
    }

    func indexedCount() throws -> Int {
        let sql = "SELECT COUNT(DISTINCT asset_id) FROM photo_tags"
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return 0 }
        guard sqlite3_step(stmt) == SQLITE_ROW else { return 0 }
        return Int(sqlite3_column_int(stmt, 0))
    }

    // MARK: - Helpers

    private func execute(_ sql: String, bindings: [String] = []) throws {
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else {
            throw TagStoreError.queryFailed(String(cString: sqlite3_errmsg(db)))
        }
        for (i, value) in bindings.enumerated() {
            sqlite3_bind_text(stmt, Int32(i + 1), (value as NSString).utf8String, -1, nil)
        }
        let result = sqlite3_step(stmt)
        guard result == SQLITE_DONE || result == SQLITE_ROW else {
            throw TagStoreError.queryFailed(String(cString: sqlite3_errmsg(db)))
        }
    }

    private func queryStrings(_ sql: String, bindings: [String] = []) throws -> [String] {
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else {
            throw TagStoreError.queryFailed(String(cString: sqlite3_errmsg(db)))
        }
        for (i, value) in bindings.enumerated() {
            sqlite3_bind_text(stmt, Int32(i + 1), (value as NSString).utf8String, -1, nil)
        }
        var results: [String] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            if let cStr = sqlite3_column_text(stmt, 0) {
                results.append(String(cString: cStr))
            }
        }
        return results
    }
}

enum TagStoreError: Error {
    case openFailed(String)
    case queryFailed(String)
}
```

- [ ] **Step 4: Add libsqlite3 to project.yml**

In `project.yml`, under the `iFauxto` target, add after the `entitlements` section:

```yaml
    dependencies:
      - sdk: libsqlite3.tbd
```

Also add under `iFauxtoTests` target:

```yaml
    dependencies:
      - target: iFauxto
      - sdk: libsqlite3.tbd
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -30
```

Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/Services/TagStore.swift iFauxtoTests/TagStoreTests.swift project.yml && git commit -m "feat: add TagStore with SQLite FTS5 for photo tag storage and search"
```

---

### Task 2: Create VisionTaggingService

**Files:**
- Create: `iFauxto/Services/VisionTaggingService.swift`

- [ ] **Step 1: Create VisionTaggingService.swift**

Create `iFauxto/Services/VisionTaggingService.swift`:

```swift
import Vision
import UIKit

struct PhotoTags {
    let assetId: String
    let tags: [TagRecord]
}

final class VisionTaggingService {

    func tagPhoto(image: CGImage, assetId: String) async -> PhotoTags {
        async let objectTags = classifyImage(image)
        async let textTags = recognizeText(image)
        async let faceCount = detectFaces(image)

        let objects = await objectTags
        let texts = await textTags
        let faces = await faceCount

        var tags: [TagRecord] = []

        // Object/scene classifications (top 10 above 0.1 confidence)
        for item in objects {
            tags.append(TagRecord(tagType: "object", tagValue: item.label, confidence: item.confidence))
        }

        // OCR text
        for text in texts {
            tags.append(TagRecord(tagType: "text", tagValue: text, confidence: 1.0))
        }

        // Face count
        if faces > 0 {
            tags.append(TagRecord(tagType: "face", tagValue: "\(faces) face\(faces == 1 ? "" : "s")", confidence: 1.0))
        }

        return PhotoTags(assetId: assetId, tags: tags)
    }

    // MARK: - Vision Requests

    private func classifyImage(_ image: CGImage) async -> [(label: String, confidence: Float)] {
        await withCheckedContinuation { continuation in
            let request = VNClassifyImageRequest { request, error in
                guard let results = request.results as? [VNClassificationObservation] else {
                    continuation.resume(returning: [])
                    return
                }
                let filtered = results
                    .filter { $0.confidence > 0.1 }
                    .prefix(10)
                    .map { (label: $0.identifier.replacingOccurrences(of: "_", with: " "), confidence: $0.confidence) }
                continuation.resume(returning: Array(filtered))
            }
            let handler = VNImageRequestHandler(cgImage: image, options: [:])
            try? handler.perform([request])
        }
    }

    private func recognizeText(_ image: CGImage) async -> [String] {
        await withCheckedContinuation { continuation in
            let request = VNRecognizeTextRequest { request, error in
                guard let results = request.results as? [VNRecognizedTextObservation] else {
                    continuation.resume(returning: [])
                    return
                }
                let texts = results.compactMap { $0.topCandidates(1).first?.string }
                continuation.resume(returning: texts)
            }
            request.recognitionLevel = .fast
            let handler = VNImageRequestHandler(cgImage: image, options: [:])
            try? handler.perform([request])
        }
    }

    private func detectFaces(_ image: CGImage) async -> Int {
        await withCheckedContinuation { continuation in
            let request = VNDetectFaceRectanglesRequest { request, error in
                let count = (request.results as? [VNFaceObservation])?.count ?? 0
                continuation.resume(returning: count)
            }
            let handler = VNImageRequestHandler(cgImage: image, options: [:])
            try? handler.perform([request])
        }
    }
}
```

- [ ] **Step 2: Build and verify**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -10
```

Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/Services/VisionTaggingService.swift && git commit -m "feat: add VisionTaggingService using Apple Vision for object/text/face detection"
```

---

### Task 3: Create IndexingManager

**Files:**
- Create: `iFauxto/Services/IndexingManager.swift`

- [ ] **Step 1: Create IndexingManager.swift**

Create `iFauxto/Services/IndexingManager.swift`:

```swift
import Photos
import UIKit

@MainActor
final class IndexingManager: ObservableObject {
    @Published var isIndexing = false
    @Published var indexedCount = 0
    @Published var totalCount = 0

    private let tagStore: TagStore
    private let taggingService = VisionTaggingService()
    private var indexingTask: Task<Void, Never>?

    init(tagStore: TagStore) {
        self.tagStore = tagStore
    }

    var progress: Double {
        guard totalCount > 0 else { return 0 }
        return Double(indexedCount) / Double(totalCount)
    }

    func startBackgroundIndexing() {
        guard indexingTask == nil else { return }
        indexingTask = Task.detached(priority: .utility) { [weak self] in
            await self?.runIndexing()
        }
    }

    func stopIndexing() {
        indexingTask?.cancel()
        indexingTask = nil
    }

    private func runIndexing() async {
        await MainActor.run { isIndexing = true }

        // Fetch all photo asset identifiers
        let fetchOptions = PHFetchOptions()
        fetchOptions.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        let assets = PHAsset.fetchAssets(with: .image, options: fetchOptions)

        await MainActor.run { totalCount = assets.count }

        let batchSize = 10
        var processed = 0

        for i in 0..<assets.count {
            guard !Task.isCancelled else { break }

            let asset = assets.object(at: i)
            let assetId = asset.localIdentifier

            // Skip already indexed
            if (try? tagStore.isIndexed(assetId: assetId)) == true {
                processed += 1
                await MainActor.run { indexedCount = processed }
                continue
            }

            // Load thumbnail for Vision analysis
            guard let image = await loadImageForAnalysis(asset: asset) else {
                processed += 1
                await MainActor.run { indexedCount = processed }
                continue
            }

            // Run Vision tagging
            let photoTags = await taggingService.tagPhoto(image: image, assetId: assetId)

            // Add metadata tags
            var allTags = photoTags.tags
            allTags.append(contentsOf: metadataTags(for: asset))

            // Store tags
            try? tagStore.insertTags(assetId: assetId, tags: allTags)

            processed += 1
            await MainActor.run { indexedCount = processed }

            // Yield between batches to avoid hogging CPU
            if processed % batchSize == 0 {
                try? await Task.sleep(nanoseconds: 100_000_000) // 100ms
            }
        }

        await MainActor.run {
            isIndexing = false
            indexingTask = nil
        }
    }

    private func loadImageForAnalysis(asset: PHAsset) async -> CGImage? {
        await withCheckedContinuation { continuation in
            let options = PHImageRequestOptions()
            options.deliveryMode = .fastFormat
            options.resizeMode = .fast
            options.isSynchronous = false
            options.isNetworkAccessAllowed = false
            PHImageManager.default().requestImage(
                for: asset,
                targetSize: CGSize(width: 640, height: 640),
                contentMode: .aspectFit,
                options: options
            ) { image, _ in
                continuation.resume(returning: image?.cgImage)
            }
        }
    }

    private func metadataTags(for asset: PHAsset) -> [TagRecord] {
        var tags: [TagRecord] = []

        // Time of day
        if let date = asset.creationDate {
            let hour = Calendar.current.component(.hour, from: date)
            let timeOfDay: String
            switch hour {
            case 5..<12: timeOfDay = "morning"
            case 12..<17: timeOfDay = "afternoon"
            case 17..<21: timeOfDay = "evening"
            default: timeOfDay = "night"
            }
            tags.append(TagRecord(tagType: "time", tagValue: timeOfDay, confidence: 1.0))
        }

        // Location (if available)
        if let location = asset.location {
            tags.append(TagRecord(
                tagType: "location",
                tagValue: "lat:\(location.coordinate.latitude) lon:\(location.coordinate.longitude)",
                confidence: 1.0
            ))
        }

        // Media subtype
        if asset.mediaSubtypes.contains(.photoScreenshot) {
            tags.append(TagRecord(tagType: "object", tagValue: "screenshot", confidence: 1.0))
        }

        return tags
    }
}
```

- [ ] **Step 2: Build and verify**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -10
```

Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/Services/IndexingManager.swift && git commit -m "feat: add IndexingManager for background Vision tagging pipeline"
```

---

### Task 4: Create SearchService and SearchView

**Files:**
- Create: `iFauxto/Services/SearchService.swift`
- Create: `iFauxto/Views/SearchView.swift`

- [ ] **Step 1: Create SearchService.swift**

Create `iFauxto/Services/SearchService.swift`:

```swift
import Foundation

struct SearchResult: Identifiable {
    let id: String  // asset identifier
    let matchedTags: [String]
}

final class SearchService {
    private let tagStore: TagStore

    init(tagStore: TagStore) {
        self.tagStore = tagStore
    }

    func search(query: String) -> [SearchResult] {
        guard !query.trimmingCharacters(in: .whitespaces).isEmpty else { return [] }
        let assetIds = (try? tagStore.search(query: query)) ?? []
        return assetIds.map { SearchResult(id: $0, matchedTags: [query]) }
    }

    func suggestions(prefix: String) -> [String] {
        guard prefix.count >= 2 else { return [] }
        return (try? tagStore.suggestions(prefix: prefix)) ?? []
    }
}
```

- [ ] **Step 2: Create SearchView.swift**

Create `iFauxto/Views/SearchView.swift`:

```swift
import SwiftUI

struct SearchView: View {
    let searchService: SearchService
    @EnvironmentObject var photoKitService: PhotoKitService
    @EnvironmentObject var indexingManager: IndexingManager

    @State private var query = ""
    @State private var results: [SearchResult] = []
    @State private var suggestions: [String] = []

    private let columns = [GridItem(.adaptive(minimum: 110), spacing: 2)]

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Indexing progress bar
                if indexingManager.isIndexing {
                    VStack(spacing: 4) {
                        ProgressView(value: indexingManager.progress)
                        Text("Learning your library... \(Int(indexingManager.progress * 100))% done")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.horizontal, 16)
                    .padding(.top, 8)
                }

                // Results
                if results.isEmpty && !query.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 36))
                            .foregroundStyle(.secondary)
                        Text("No results for \"\(query)\"")
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if results.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 36))
                            .foregroundStyle(.tertiary)
                        Text("Find anything. Instantly.")
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ScrollView {
                        LazyVGrid(columns: columns, spacing: 2) {
                            ForEach(results) { result in
                                SearchThumbnailView(identifier: result.id)
                            }
                        }
                        .padding(2)
                    }
                }
            }
            .navigationTitle("Search")
            .searchable(text: $query, prompt: "Search photos...")
            .searchSuggestions {
                ForEach(suggestions, id: \.self) { suggestion in
                    Text(suggestion)
                        .searchCompletion(suggestion)
                }
            }
            .onChange(of: query) { _, newValue in
                results = searchService.search(query: newValue)
                suggestions = searchService.suggestions(prefix: newValue)
            }
        }
    }
}

private struct SearchThumbnailView: View {
    let identifier: String
    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var thumbnail: UIImage?
    private let size: CGFloat = 120

    var body: some View {
        Group {
            if let img = thumbnail {
                Image(uiImage: img)
                    .resizable()
                    .scaledToFill()
            } else {
                Rectangle()
                    .fill(Color(.systemGray5))
                    .overlay(ProgressView())
            }
        }
        .frame(width: size, height: size)
        .clipped()
        .task(id: identifier) {
            thumbnail = await photoKitService.loadThumbnail(
                for: identifier,
                targetSize: CGSize(width: size * 2, height: size * 2)
            )
        }
    }
}
```

- [ ] **Step 3: Build and verify**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -10
```

Expected: BUILD SUCCEEDED

- [ ] **Step 4: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/Services/SearchService.swift iFauxto/Views/SearchView.swift && git commit -m "feat: add SearchService and SearchView with FTS-powered instant search"
```

---

### Task 5: Wire indexing + search into app lifecycle

**Files:**
- Modify: `iFauxto/App/iFauxtoApp.swift`
- Modify: `iFauxto/Views/HomeView.swift`

- [ ] **Step 1: Update iFauxtoApp.swift to create TagStore, IndexingManager, SearchService**

Replace `iFauxto/App/iFauxtoApp.swift` with:

```swift
import SwiftUI
import SwiftData

@main
struct iFauxtoApp: App {
    @StateObject private var dataManager: DataManager
    @StateObject private var photoKitService = PhotoKitService()
    @StateObject private var syncManager: SyncManager
    @StateObject private var importService: LibraryImportService
    @StateObject private var indexingManager: IndexingManager

    private let tagStore: TagStore
    private let searchService: SearchService

    init() {
        do {
            let dm = try DataManager()
            let ts = try TagStore()
            _dataManager = StateObject(wrappedValue: dm)
            _syncManager = StateObject(wrappedValue: SyncManager(dataManager: dm))
            _importService = StateObject(wrappedValue: LibraryImportService(dataManager: dm))
            _indexingManager = StateObject(wrappedValue: IndexingManager(tagStore: ts))
            tagStore = ts
            searchService = SearchService(tagStore: ts)
        } catch {
            fatalError("Failed to initialize: \(error)")
        }
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(dataManager)
                .environmentObject(photoKitService)
                .environmentObject(syncManager)
                .environmentObject(importService)
                .environmentObject(indexingManager)
                .environment(\.searchService, searchService)
                .onAppear {
                    indexingManager.startBackgroundIndexing()
                }
        }
    }
}

// Environment key for SearchService (non-ObservableObject)
private struct SearchServiceKey: EnvironmentKey {
    static let defaultValue: SearchService? = nil
}

extension EnvironmentValues {
    var searchService: SearchService? {
        get { self[SearchServiceKey.self] }
        set { self[SearchServiceKey.self] = newValue }
    }
}
```

- [ ] **Step 2: Add Search tab to HomeView**

In `iFauxto/Views/HomeView.swift`, add `@Environment(\.searchService) var searchService` and `@EnvironmentObject var indexingManager: IndexingManager` to the state declarations.

Add `@State private var showingSearch = false` to the state declarations.

In the toolbar Menu, add a Search button:

```swift
                        Button {
                            showingSearch = true
                        } label: {
                            Label("Search", systemImage: "magnifyingglass")
                        }
```

Add a sheet for search:

```swift
            .sheet(isPresented: $showingSearch) {
                if let service = searchService {
                    SearchView(searchService: service)
                }
            }
```

- [ ] **Step 3: Build and run all tests**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -30
```

Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/App/iFauxtoApp.swift iFauxto/Views/HomeView.swift && git commit -m "feat: wire up background indexing and search into app lifecycle"
```

---

## Phase 3 Complete

After all 5 tasks:
- TagStore provides SQLite FTS5 storage for photo tags
- VisionTaggingService analyzes photos via Apple Vision (on-device, free)
- IndexingManager coordinates background indexing (newest first, progressive)
- SearchService + SearchView provide instant search with suggestions
- Background indexing starts on app launch, never blocks UI
- All tests pass
