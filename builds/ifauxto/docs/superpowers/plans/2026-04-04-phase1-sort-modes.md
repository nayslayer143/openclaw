# Phase 1: Folder Sort Modes

> Part of iFauxto v2 plan. Read `2026-04-04-ifauxto-v2-plan.md` first for context and rules.

**Goal:** Add sortMode property to Folder model and sort-mode picker in HomeView/FolderView. Custom mode preserves manual order. Other modes compute display order without mutating orderIndex.

---

### Task 1: Add sortMode to Folder model

**Files:**
- Modify: `iFauxto/Models/Folder.swift:5-22`
- Test: `iFauxtoTests/FolderTests.swift`

- [ ] **Step 1: Write the failing test**

Add to `iFauxtoTests/FolderTests.swift`:

```swift
import Testing
import SwiftData
import Foundation
@testable import iFauxto

@MainActor
@Suite("Folder Sort Mode")
struct FolderSortModeTests {

    func makeManager() throws -> DataManager {
        return try DataManager(inMemory: true)
    }

    @Test("New folder defaults to custom sort mode")
    func defaultSortMode() throws {
        let dm = try makeManager()
        let folder = dm.createFolder(name: "Test")
        #expect(folder.sortMode == "custom")
    }

    @Test("Sort mode can be changed and persisted")
    func changeSortMode() throws {
        let dm = try makeManager()
        let folder = dm.createFolder(name: "Test")
        folder.sortMode = "alpha"
        try dm.modelContext.save()
        #expect(folder.sortMode == "alpha")
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -30
```

Expected: FAIL — `Folder` has no `sortMode` property.

- [ ] **Step 3: Add sortMode property to Folder.swift**

In `iFauxto/Models/Folder.swift`, add after line 11 (`var order: Int = 0`):

```swift
    var sortMode: String = "custom"  // "custom" | "alpha" | "date" | "recent"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -30
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/Models/Folder.swift iFauxtoTests/FolderTests.swift && git commit -m "feat: add sortMode property to Folder model (default: custom)"
```

---

### Task 2: Add sort mode picker to HomeView

**Files:**
- Modify: `iFauxto/Views/HomeView.swift`

- [ ] **Step 1: Add sorted folders computed property and sort picker**

In `iFauxto/Views/HomeView.swift`, add a new `@State` and a computed property. Replace the existing file with these changes:

After line 10 (`@State private var editMode: EditMode = .inactive`), add:

```swift
    @State private var folderSortMode: String = "custom"
```

Add this computed property after the `@State` declarations (before `var body`):

```swift
    private var displayFolders: [Folder] {
        switch folderSortMode {
        case "alpha":
            return folders.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
        case "date":
            return folders.sorted { $0.createdAt < $1.createdAt }
        case "recent":
            return folders.sorted { $0.createdAt > $1.createdAt }
        default:
            return folders  // "custom" — original order from DataManager (by orderIndex)
        }
    }
```

In the `folderList` computed property, change `ForEach(folders)` to `ForEach(displayFolders)`.

In the `.onMove` modifier, wrap the move logic so it only works in custom mode:

```swift
            .onMove { source, destination in
                guard folderSortMode == "custom" else { return }
                folders.move(fromOffsets: source, toOffset: destination)
                dataManager.updateFolderOrder(folders)
            }
```

In the toolbar Menu (after the "Import Library" button and before the closing `} label:`), add:

```swift
                        Divider()
                        Menu("Sort By") {
                            Button {
                                folderSortMode = "custom"
                            } label: {
                                Label("Manual Order", systemImage: folderSortMode == "custom" ? "checkmark" : "")
                            }
                            Button {
                                folderSortMode = "alpha"
                            } label: {
                                Label("Alphabetical", systemImage: folderSortMode == "alpha" ? "checkmark" : "")
                            }
                            Button {
                                folderSortMode = "date"
                            } label: {
                                Label("Date Created", systemImage: folderSortMode == "date" ? "checkmark" : "")
                            }
                            Button {
                                folderSortMode = "recent"
                            } label: {
                                Label("Most Recent", systemImage: folderSortMode == "recent" ? "checkmark" : "")
                            }
                        }
```

- [ ] **Step 2: Build and verify**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -10
```

Expected: BUILD SUCCEEDED

- [ ] **Step 3: Run all tests**

```bash
cd ~/openclaw/builds/ifauxto && xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -20
```

Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/Views/HomeView.swift && git commit -m "feat: add folder sort mode picker to HomeView (custom/alpha/date/recent)"
```

---

### Task 3: Add sort mode picker to FolderView (photos within a folder)

**Files:**
- Modify: `iFauxto/Views/FolderView.swift`

- [ ] **Step 1: Add photo sort mode state and computed property**

In `iFauxto/Views/FolderView.swift`, after line 16 (`@State private var showingSubfolderCreation = false`), add:

```swift
    @State private var photoSortMode: String = "custom"
```

Add a computed property before `var body`:

```swift
    private var displayPhotos: [PhotoReference] {
        switch photoSortMode {
        case "alpha":
            return photos.sorted { $0.id.localizedCaseInsensitiveCompare($1.id) == .orderedAscending }
        case "date":
            return photos.sorted { $0.orderIndex < $1.orderIndex }  // orderIndex tracks insertion order
        case "recent":
            return photos.sorted { $0.orderIndex > $1.orderIndex }
        default:
            return photos
        }
    }
```

In the body's `LazyVGrid`, change `ForEach(photos)` to `ForEach(displayPhotos)`.

In the drag `.dropDestination` handler, add a guard:

```swift
                            .dropDestination(for: String.self) { items, _ in
                                guard photoSortMode == "custom" else { return false }
                                guard let sourceId = items.first, sourceId != photo.id else { return false }
```

In the toolbar Menu, add a sort submenu after the "Select Photos" button:

```swift
                    Divider()
                    Menu("Sort Photos") {
                        Button {
                            photoSortMode = "custom"
                        } label: {
                            Label("Manual Order", systemImage: photoSortMode == "custom" ? "checkmark" : "")
                        }
                        Button {
                            photoSortMode = "alpha"
                        } label: {
                            Label("By Name", systemImage: photoSortMode == "alpha" ? "checkmark" : "")
                        }
                        Button {
                            photoSortMode = "recent"
                        } label: {
                            Label("Newest First", systemImage: photoSortMode == "recent" ? "checkmark" : "")
                        }
                    }
```

- [ ] **Step 2: Build and verify**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -10
```

Expected: BUILD SUCCEEDED

- [ ] **Step 3: Run all tests**

```bash
cd ~/openclaw/builds/ifauxto && xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -20
```

Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/Views/FolderView.swift && git commit -m "feat: add photo sort mode picker to FolderView"
```

---

## Phase 1 Complete

After all 3 tasks:
- Folder model has `sortMode` property
- HomeView has sort picker for folders
- FolderView has sort picker for photos
- Custom mode preserves manual drag order
- Non-custom modes compute display order without mutating `orderIndex`
- All tests pass
