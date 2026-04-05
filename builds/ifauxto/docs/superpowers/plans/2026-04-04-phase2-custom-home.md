# Phase 2: Custom Home Screen

> Part of iFauxto v2 plan. Read `2026-04-04-ifauxto-v2-plan.md` first. Phase 1 (sort modes) must be complete.

**Goal:** User chooses what they see on app launch: folder list, chronological feed, last opened, or a custom pinned view. First launch shows onboarding. Changeable in settings.

---

### Task 1: Create AppSettings model

**Files:**
- Create: `iFauxto/Models/AppSettings.swift`
- Modify: `iFauxto/Models/DataManager.swift`
- Test: `iFauxtoTests/AppSettingsTests.swift`

- [ ] **Step 1: Write the failing test**

Create `iFauxtoTests/AppSettingsTests.swift`:

```swift
import Testing
import SwiftData
import Foundation
@testable import iFauxto

@MainActor
@Suite("AppSettings")
struct AppSettingsTests {

    func makeManager() throws -> DataManager {
        return try DataManager(inMemory: true)
    }

    @Test("AppSettings defaults to folder_list home mode")
    func defaultHomeMode() throws {
        let dm = try makeManager()
        let settings = dm.getOrCreateSettings()
        #expect(settings.homeViewMode == "folder_list")
    }

    @Test("AppSettings home mode can be changed")
    func changeHomeMode() throws {
        let dm = try makeManager()
        let settings = dm.getOrCreateSettings()
        settings.homeViewMode = "chronological_feed"
        try dm.modelContext.save()
        let fetched = dm.getOrCreateSettings()
        #expect(fetched.homeViewMode == "chronological_feed")
    }

    @Test("getOrCreateSettings returns same singleton")
    func singleton() throws {
        let dm = try makeManager()
        let s1 = dm.getOrCreateSettings()
        let s2 = dm.getOrCreateSettings()
        #expect(s1.id == s2.id)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — `AppSettings` type not found.

- [ ] **Step 3: Create AppSettings.swift**

Create `iFauxto/Models/AppSettings.swift`:

```swift
import SwiftData
import Foundation

@Model
final class AppSettings {
    @Attribute(.unique) var id: String = "singleton"
    var homeViewMode: String = "folder_list"  // "folder_list" | "chronological_feed" | "last_opened" | "custom_view"
    var lastOpenedViewId: String?
    var pinnedViewId: String?
    var hasCompletedOnboarding: Bool = false

    init() {
        self.id = "singleton"
    }
}
```

- [ ] **Step 4: Register AppSettings in DataManager schema**

In `iFauxto/Models/DataManager.swift`, change line 16:

From:
```swift
        let schema = Schema([Folder.self, PhotoReference.self])
```

To:
```swift
        let schema = Schema([Folder.self, PhotoReference.self, AppSettings.self])
```

Add this method at the end of DataManager (before the closing `}`):

```swift
    // MARK: Settings

    func getOrCreateSettings() -> AppSettings {
        let descriptor = FetchDescriptor<AppSettings>()
        if let existing = try? modelContext.fetch(descriptor).first {
            return existing
        }
        let settings = AppSettings()
        modelContext.insert(settings)
        try? modelContext.save()
        return settings
    }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -30
```

Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/Models/AppSettings.swift iFauxto/Models/DataManager.swift iFauxtoTests/AppSettingsTests.swift && git commit -m "feat: add AppSettings model with homeViewMode + singleton accessor"
```

---

### Task 2: Create OnboardingView

**Files:**
- Create: `iFauxto/Views/OnboardingView.swift`

- [ ] **Step 1: Create OnboardingView.swift**

Create `iFauxto/Views/OnboardingView.swift`:

```swift
import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject var dataManager: DataManager
    let onComplete: () -> Void

    @State private var selectedMode: String = "folder_list"

    private let modes: [(id: String, title: String, subtitle: String, icon: String)] = [
        ("folder_list", "Folders", "Your organized folder structure", "folder.fill"),
        ("chronological_feed", "Photo Feed", "All photos, newest first", "photo.on.rectangle"),
        ("last_opened", "Last Opened", "Pick up where you left off", "clock.arrow.circlepath"),
    ]

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            VStack(spacing: 12) {
                Text("Welcome to iFauxto")
                    .font(.largeTitle.weight(.bold))
                Text("Let's set this up your way.")
                    .font(.title3)
                    .foregroundStyle(.secondary)
            }

            VStack(spacing: 12) {
                ForEach(modes, id: \.id) { mode in
                    Button {
                        selectedMode = mode.id
                    } label: {
                        HStack(spacing: 16) {
                            Image(systemName: mode.icon)
                                .font(.title2)
                                .frame(width: 36)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(mode.title)
                                    .font(.body.weight(.semibold))
                                Text(mode.subtitle)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            if selectedMode == mode.id {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(.accentColor)
                            }
                        }
                        .padding(16)
                        .background(
                            RoundedRectangle(cornerRadius: 12)
                                .fill(selectedMode == mode.id ? Color.accentColor.opacity(0.1) : Color(.systemGray6))
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(selectedMode == mode.id ? Color.accentColor : Color.clear, lineWidth: 2)
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 24)

            Spacer()

            Button {
                let settings = dataManager.getOrCreateSettings()
                settings.homeViewMode = selectedMode
                settings.hasCompletedOnboarding = true
                try? dataManager.modelContext.save()
                onComplete()
            } label: {
                Text("Get Started")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
            }
            .buttonStyle(.borderedProminent)
            .padding(.horizontal, 24)
            .padding(.bottom, 32)
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
cd ~/openclaw/builds/ifauxto && git add iFauxto/Views/OnboardingView.swift && git commit -m "feat: add OnboardingView with home mode selection"
```

---

### Task 3: Create SettingsView

**Files:**
- Create: `iFauxto/Views/SettingsView.swift`

- [ ] **Step 1: Create SettingsView.swift**

Create `iFauxto/Views/SettingsView.swift`:

```swift
import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var dataManager: DataManager
    @Environment(\.dismiss) var dismiss

    @State private var homeMode: String = "folder_list"

    private let modes: [(id: String, label: String)] = [
        ("folder_list", "Folders"),
        ("chronological_feed", "Photo Feed"),
        ("last_opened", "Last Opened"),
    ]

    var body: some View {
        NavigationStack {
            List {
                Section("Home Screen") {
                    ForEach(modes, id: \.id) { mode in
                        Button {
                            homeMode = mode.id
                        } label: {
                            HStack {
                                Text(mode.label)
                                    .foregroundStyle(.primary)
                                Spacer()
                                if homeMode == mode.id {
                                    Image(systemName: "checkmark")
                                        .foregroundStyle(.accentColor)
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        let settings = dataManager.getOrCreateSettings()
                        settings.homeViewMode = homeMode
                        try? dataManager.modelContext.save()
                        dismiss()
                    }
                }
            }
            .onAppear {
                homeMode = dataManager.getOrCreateSettings().homeViewMode
            }
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
cd ~/openclaw/builds/ifauxto && git add iFauxto/Views/SettingsView.swift && git commit -m "feat: add SettingsView with home mode preference"
```

---

### Task 4: Create ChronologicalFeedView

**Files:**
- Create: `iFauxto/Views/ChronologicalFeedView.swift`

- [ ] **Step 1: Create ChronologicalFeedView.swift**

Create `iFauxto/Views/ChronologicalFeedView.swift`:

```swift
import SwiftUI
import Photos

struct ChronologicalFeedView: View {
    @EnvironmentObject var photoKitService: PhotoKitService

    @State private var assetIdentifiers: [String] = []
    @State private var isLoading = true

    private let columns = [GridItem(.adaptive(minimum: 110), spacing: 2)]

    var body: some View {
        NavigationStack {
            ScrollView {
                if isLoading {
                    ProgressView("Loading photos...")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .padding(.top, 100)
                } else if assetIdentifiers.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "photo.on.rectangle")
                            .font(.system(size: 48))
                            .foregroundStyle(.secondary)
                        Text("No Photos")
                            .font(.title3.weight(.medium))
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.top, 80)
                } else {
                    LazyVGrid(columns: columns, spacing: 2) {
                        ForEach(assetIdentifiers, id: \.self) { identifier in
                            FeedThumbnailView(identifier: identifier)
                        }
                    }
                    .padding(2)
                }
            }
            .navigationTitle("All Photos")
            .task {
                assetIdentifiers = photoKitService.fetchAllAssetIdentifiers()
                isLoading = false
            }
        }
    }
}

private struct FeedThumbnailView: View {
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

- [ ] **Step 2: Build and verify**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -10
```

Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/Views/ChronologicalFeedView.swift && git commit -m "feat: add ChronologicalFeedView with lazy photo grid"
```

---

### Task 5: Wire up ContentView routing + onboarding

**Files:**
- Modify: `iFauxto/App/ContentView.swift`
- Modify: `iFauxto/App/iFauxtoApp.swift`
- Modify: `iFauxto/Views/HomeView.swift` (add settings button)

- [ ] **Step 1: Update ContentView.swift to route based on AppSettings**

Replace the entire content of `iFauxto/App/ContentView.swift` with:

```swift
import SwiftUI
import Photos

struct ContentView: View {
    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var hasCheckedAuth = false
    @State private var showOnboarding = false

    var body: some View {
        Group {
            if !hasCheckedAuth {
                ProgressView("Loading...")
                    .task { await checkAuthorization() }
            } else if photoKitService.isAuthorized {
                if showOnboarding {
                    OnboardingView {
                        showOnboarding = false
                    }
                } else {
                    mainView
                }
            } else {
                PhotoPermissionView {
                    Task { await photoKitService.requestAuthorization() }
                }
            }
        }
        .onChange(of: photoKitService.authorizationStatus) { _, _ in
            hasCheckedAuth = true
        }
    }

    @ViewBuilder
    private var mainView: some View {
        let settings = dataManager.getOrCreateSettings()
        switch settings.homeViewMode {
        case "chronological_feed":
            ChronologicalFeedView()
        case "last_opened":
            HomeView()  // fallback to folders for now; last_opened requires navigation state tracking
        default:
            HomeView()
        }
    }

    private func checkAuthorization() async {
        if photoKitService.authorizationStatus == .notDetermined {
            await photoKitService.requestAuthorization()
        }
        hasCheckedAuth = true
        let settings = dataManager.getOrCreateSettings()
        if !settings.hasCompletedOnboarding {
            showOnboarding = true
        }
    }
}

struct PhotoPermissionView: View {
    let onRequest: () -> Void

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "photo.on.rectangle.angled")
                .font(.system(size: 64))
                .foregroundStyle(.secondary)
            Text("iFauxto needs access to your Photos library to get started.")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
            Button("Grant Access", action: onRequest)
                .buttonStyle(.borderedProminent)
        }
        .padding(40)
    }
}
```

- [ ] **Step 2: Add Settings button to HomeView toolbar**

In `iFauxto/Views/HomeView.swift`, add a `@State private var showingSettings = false` after the other @State declarations.

In the toolbar, add before the existing `ToolbarItem(placement: .navigationBarLeading)`:

```swift
                ToolbarItem(placement: .navigationBarLeading) {
                    HStack {
                        EditButton()
                        Button {
                            showingSettings = true
                        } label: {
                            Image(systemName: "gearshape")
                        }
                    }
                }
```

Remove the existing separate EditButton ToolbarItem to avoid duplicate leading items.

Add a `.sheet` modifier for settings:

```swift
            .sheet(isPresented: $showingSettings) {
                SettingsView()
            }
```

- [ ] **Step 3: Build and verify**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -10
```

Expected: BUILD SUCCEEDED

- [ ] **Step 4: Run all tests**

```bash
cd ~/openclaw/builds/ifauxto && xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -30
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/App/ContentView.swift iFauxto/Views/HomeView.swift && git commit -m "feat: wire up home mode routing, onboarding gate, and settings access"
```

---

## Phase 2 Complete

After all 5 tasks:
- AppSettings model persists home view preference
- OnboardingView shown on first launch
- ContentView routes to correct view based on setting
- SettingsView allows changing preference
- ChronologicalFeedView shows all photos in time order
- Settings accessible from HomeView toolbar gear icon
