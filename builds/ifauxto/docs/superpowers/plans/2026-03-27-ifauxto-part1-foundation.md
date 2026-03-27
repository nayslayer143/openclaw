# iFauxto — Part 1: Foundation

> Read before this: nothing (this is first)
> Read after this: `2026-03-27-ifauxto-part2-ui.md`
>
> Covers: XcodeGen project setup, SwiftData models (Folder, PhotoReference), DataManager CRUD,
> PhotoKitService (PHAsset access), SyncManager scaffold.

---

## File Map

| File | Responsibility |
|------|---------------|
| `project.yml` | XcodeGen spec — generates the entire Xcode project |
| `iFauxto/iFauxto.entitlements` | iCloud + CloudKit entitlements |
| `iFauxto/Models/Folder.swift` | SwiftData `@Model` for folder hierarchy |
| `iFauxto/Models/PhotoReference.swift` | SwiftData `@Model` for PHAsset references |
| `iFauxto/Models/DataManager.swift` | `@MainActor` class — all CRUD and ordering operations |
| `iFauxto/Services/PhotoKitService.swift` | PHPhotoLibrary auth + image loading |
| `iFauxto/Services/SyncManager.swift` | CloudKit sync coordination scaffold |
| `iFauxto/Services/CloudKitService.swift` | CloudKit conflict resolution placeholder |
| `iFauxto/Utils/Extensions.swift` | PHAsset + Array convenience extensions |
| `iFauxtoTests/FolderTests.swift` | Tests for Folder model |
| `iFauxtoTests/PhotoReferenceTests.swift` | Tests for PhotoReference model |
| `iFauxtoTests/DataManagerTests.swift` | Tests for DataManager CRUD and ordering |

---

## Task 1: XcodeGen Project Bootstrap

**Files:**
- Create: `~/openclaw/builds/ifauxto/project.yml`
- Create: `~/openclaw/builds/ifauxto/iFauxto/iFauxto.entitlements`
- Create: `~/openclaw/builds/ifauxto/iFauxto/Resources/Assets.xcassets/Contents.json`
- Create: `~/openclaw/builds/ifauxto/iFauxtoTests/iFauxtoTests.swift`
- Generate: `iFauxto.xcodeproj` (via xcodegen)

- [ ] **Step 1: Install XcodeGen if not present**

```bash
which xcodegen || brew install xcodegen
```

Expected: path to xcodegen binary or install completes.

- [ ] **Step 2: Create project.yml**

```bash
cat > ~/openclaw/builds/ifauxto/project.yml << 'EOF'
name: iFauxto
options:
  bundleIdPrefix: com.ifauxto
  deploymentTarget:
    iOS: "17.0"
  xcodeVersion: "15.4"
  createIntermediateGroups: true
  generateEmptyDirectories: true

settings:
  SWIFT_VERSION: "5.9"
  IPHONEOS_DEPLOYMENT_TARGET: "17.0"
  MARKETING_VERSION: "1.0.0"
  CURRENT_PROJECT_VERSION: "1"
  DEBUG_INFORMATION_FORMAT: dwarf-with-dsym

targets:
  iFauxto:
    type: application
    platform: iOS
    sources:
      - path: iFauxto
        excludes:
          - "**/.DS_Store"
    settings:
      PRODUCT_BUNDLE_IDENTIFIER: com.ifauxto.app
      DEVELOPMENT_TEAM: ""
      CODE_SIGN_STYLE: Automatic
      INFOPLIST_FILE: iFauxto/Resources/Info.plist
    info:
      path: iFauxto/Resources/Info.plist
      properties:
        CFBundleDisplayName: iFauxto
        CFBundleName: iFauxto
        CFBundleShortVersionString: "$(MARKETING_VERSION)"
        CFBundleVersion: "$(CURRENT_PROJECT_VERSION)"
        NSPhotoLibraryUsageDescription: "iFauxto needs access to your Photos library to organize your photos."
        NSPhotoLibraryAddUsageDescription: "iFauxto needs permission to add photos."
        UIApplicationSceneManifest:
          UIApplicationSupportsMultipleScenes: false
        UISupportedInterfaceOrientations:
          - UIInterfaceOrientationPortrait
          - UIInterfaceOrientationLandscapeLeft
          - UIInterfaceOrientationLandscapeRight
        UISupportedInterfaceOrientations~ipad:
          - UIInterfaceOrientationPortrait
          - UIInterfaceOrientationPortraitUpsideDown
          - UIInterfaceOrientationLandscapeLeft
          - UIInterfaceOrientationLandscapeRight
        UILaunchScreen: {}
    entitlements:
      path: iFauxto/iFauxto.entitlements

  iFauxtoTests:
    type: bundle.unit-test
    platform: iOS
    sources:
      - path: iFauxtoTests
    dependencies:
      - target: iFauxto
    settings:
      PRODUCT_BUNDLE_IDENTIFIER: com.ifauxto.tests
      DEVELOPMENT_TEAM: ""
EOF
```

- [ ] **Step 3: Create entitlements file**

```bash
mkdir -p ~/openclaw/builds/ifauxto/iFauxto
cat > ~/openclaw/builds/ifauxto/iFauxto/iFauxto.entitlements << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.developer.icloud-container-identifiers</key>
    <array>
        <string>iCloud.com.ifauxto.app</string>
    </array>
    <key>com.apple.developer.ubiquity-kvstore-identifier</key>
    <string>$(TeamIdentifierPrefix)com.ifauxto.app</string>
    <key>com.apple.developer.icloud-container-development-container-identifiers</key>
    <array>
        <string>iCloud.com.ifauxto.app</string>
    </array>
</dict>
</plist>
EOF
```

- [ ] **Step 4: Create required empty directories and stub files**

```bash
mkdir -p ~/openclaw/builds/ifauxto/iFauxto/{App,Models,Views,Services,Utils,Resources}
mkdir -p ~/openclaw/builds/ifauxto/iFauxto/Resources/Assets.xcassets/AppIcon.appiconset
mkdir -p ~/openclaw/builds/ifauxto/iFauxtoTests

# Assets catalog root
cat > ~/openclaw/builds/ifauxto/iFauxto/Resources/Assets.xcassets/Contents.json << 'EOF'
{ "info": { "author": "xcode", "version": 1 } }
EOF

cat > ~/openclaw/builds/ifauxto/iFauxto/Resources/Assets.xcassets/AppIcon.appiconset/Contents.json << 'EOF'
{ "images": [{ "idiom": "universal", "platform": "ios", "size": "1024x1024" }], "info": { "author": "xcode", "version": 1 } }
EOF

# Stub test file (XcodeGen requires at least one source file per target)
cat > ~/openclaw/builds/ifauxto/iFauxtoTests/iFauxtoTests.swift << 'EOF'
import XCTest
@testable import iFauxto

// Tests are in FolderTests.swift, PhotoReferenceTests.swift, DataManagerTests.swift
EOF
```

- [ ] **Step 5: Generate the Xcode project**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate
```

Expected: `Generating project iFauxto` and `iFauxto.xcodeproj` created with no errors.

- [ ] **Step 6: Commit bootstrap**

```bash
cd ~/openclaw/builds/ifauxto
git init
echo "*.xcuserstate\n.DS_Store\n/build/\nDerivedData/" > .gitignore
git add project.yml iFauxto/iFauxto.entitlements iFauxto/Resources/Assets.xcassets iFauxtoTests/iFauxtoTests.swift .gitignore
git commit -m "chore: bootstrap iFauxto Xcode project via XcodeGen"
```

---

## Task 2: SwiftData Models

**Files:**
- Create: `iFauxto/Models/Folder.swift`
- Create: `iFauxto/Models/PhotoReference.swift`
- Create: `iFauxtoTests/FolderTests.swift`
- Create: `iFauxtoTests/PhotoReferenceTests.swift`

- [ ] **Step 1: Write failing tests for Folder model**

Create `iFauxtoTests/FolderTests.swift`:

```swift
import Testing
import Foundation
@testable import iFauxto

@Suite("Folder Model")
struct FolderTests {

    @Test("Folder initializes with generated UUID id")
    func folderHasUUID() {
        let folder = Folder(name: "Vacation", parentId: nil, order: 0)
        #expect(!folder.id.isEmpty)
        #expect(UUID(uuidString: folder.id) != nil)
    }

    @Test("Folder stores name and parentId correctly")
    func folderStoresFields() {
        let parent = Folder(name: "Travel", parentId: nil, order: 0)
        let child = Folder(name: "Japan", parentId: parent.id, order: 1)
        #expect(child.name == "Japan")
        #expect(child.parentId == parent.id)
        #expect(child.order == 1)
    }

    @Test("Root folder has nil parentId")
    func rootFolderHasNilParent() {
        let folder = Folder(name: "Root", parentId: nil, order: 0)
        #expect(folder.parentId == nil)
    }

    @Test("Folder createdAt is set on init")
    func folderHasCreatedAt() {
        let before = Date()
        let folder = Folder(name: "Test", parentId: nil, order: 0)
        let after = Date()
        #expect(folder.createdAt >= before)
        #expect(folder.createdAt <= after)
    }
}
```

- [ ] **Step 2: Run to verify failure**

```bash
cd ~/openclaw/builds/ifauxto
xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0' \
  -only-testing:iFauxtoTests/FolderTests 2>&1 | tail -20
```

Expected: compile error — `Folder` type not found.

- [ ] **Step 3: Implement Folder.swift**

Create `iFauxto/Models/Folder.swift`:

```swift
import SwiftData
import Foundation

@Model
final class Folder {
    @Attribute(.unique) var id: String
    var name: String
    var parentId: String?
    var createdAt: Date
    var order: Int

    @Relationship(deleteRule: .cascade, inverse: \PhotoReference.folder)
    var photoReferences: [PhotoReference] = []

    init(name: String, parentId: String? = nil, order: Int = 0) {
        self.id = UUID().uuidString
        self.name = name
        self.parentId = parentId
        self.createdAt = Date()
        self.order = order
    }
}
```

- [ ] **Step 4: Write failing tests for PhotoReference**

Create `iFauxtoTests/PhotoReferenceTests.swift`:

```swift
import Testing
@testable import iFauxto

@Suite("PhotoReference Model")
struct PhotoReferenceTests {

    @Test("PhotoReference stores PHAsset localIdentifier as id")
    func storesAssetIdentifier() {
        let assetId = "ABCD-1234-PHAsset-LocalIdentifier"
        let ref = PhotoReference(assetIdentifier: assetId, folderId: "folder-1", orderIndex: 0)
        #expect(ref.id == assetId)
        #expect(ref.folderId == "folder-1")
        #expect(ref.orderIndex == 0)
    }

    @Test("Two refs with different identifiers are distinct")
    func distinctIdentifiers() {
        let ref1 = PhotoReference(assetIdentifier: "id-1", folderId: "f", orderIndex: 0)
        let ref2 = PhotoReference(assetIdentifier: "id-2", folderId: "f", orderIndex: 1)
        #expect(ref1.id != ref2.id)
    }
}
```

- [ ] **Step 5: Implement PhotoReference.swift**

Create `iFauxto/Models/PhotoReference.swift`:

```swift
import SwiftData
import Foundation

@Model
final class PhotoReference {
    @Attribute(.unique) var id: String  // PHAsset.localIdentifier — never duplicated
    var folderId: String
    var orderIndex: Int

    var folder: Folder?

    init(assetIdentifier: String, folderId: String, orderIndex: Int) {
        self.id = assetIdentifier
        self.folderId = folderId
        self.orderIndex = orderIndex
    }
}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd ~/openclaw/builds/ifauxto
xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0' \
  -only-testing:iFauxtoTests/FolderTests \
  -only-testing:iFauxtoTests/PhotoReferenceTests 2>&1 | tail -20
```

Expected: `Test Suite ... passed` for both suites.

- [ ] **Step 7: Commit models**

```bash
cd ~/openclaw/builds/ifauxto
git add iFauxto/Models/Folder.swift iFauxto/Models/PhotoReference.swift \
        iFauxtoTests/FolderTests.swift iFauxtoTests/PhotoReferenceTests.swift
git commit -m "feat: add SwiftData models Folder and PhotoReference"
```

---

## Task 3: DataManager — CRUD and Ordering

**Files:**
- Create: `iFauxto/Models/DataManager.swift`
- Create: `iFauxtoTests/DataManagerTests.swift`

- [ ] **Step 1: Write failing DataManager tests**

Create `iFauxtoTests/DataManagerTests.swift`:

```swift
import Testing
import SwiftData
import Foundation
@testable import iFauxto

// DataManager tests use an in-memory ModelContainer to avoid disk I/O
@MainActor
@Suite("DataManager")
struct DataManagerTests {

    func makeManager() throws -> DataManager {
        return try DataManager(inMemory: true)
    }

    @Test("Creates root folder with correct defaults")
    func createRootFolder() throws {
        let dm = try makeManager()
        let folder = dm.createFolder(name: "Travel", parentId: nil)
        #expect(folder.name == "Travel")
        #expect(folder.parentId == nil)
        #expect(folder.order == 0)
    }

    @Test("Creates nested folder under parent")
    func createNestedFolder() throws {
        let dm = try makeManager()
        let parent = dm.createFolder(name: "Travel", parentId: nil)
        let child = dm.createFolder(name: "Japan", parentId: parent.id)
        #expect(child.parentId == parent.id)
        let children = dm.fetchFolders(parentId: parent.id)
        #expect(children.count == 1)
        #expect(children[0].id == child.id)
    }

    @Test("Fetch root folders returns only top-level folders")
    func fetchRootFolders() throws {
        let dm = try makeManager()
        let root1 = dm.createFolder(name: "A", parentId: nil)
        let root2 = dm.createFolder(name: "B", parentId: nil)
        let _ = dm.createFolder(name: "C", parentId: root1.id)
        let roots = dm.fetchFolders(parentId: nil)
        #expect(roots.count == 2)
        #expect(roots.map(\.id).contains(root1.id))
        #expect(roots.map(\.id).contains(root2.id))
    }

    @Test("Folder order auto-increments within same parent")
    func folderOrderIncrements() throws {
        let dm = try makeManager()
        let f1 = dm.createFolder(name: "First", parentId: nil)
        let f2 = dm.createFolder(name: "Second", parentId: nil)
        let f3 = dm.createFolder(name: "Third", parentId: nil)
        #expect(f1.order == 0)
        #expect(f2.order == 1)
        #expect(f3.order == 2)
    }

    @Test("updateFolderOrder persists new sequence")
    func updateFolderOrder() throws {
        let dm = try makeManager()
        let f1 = dm.createFolder(name: "A", parentId: nil)
        let f2 = dm.createFolder(name: "B", parentId: nil)
        let f3 = dm.createFolder(name: "C", parentId: nil)
        dm.updateFolderOrder([f3, f1, f2])
        #expect(f3.order == 0)
        #expect(f1.order == 1)
        #expect(f2.order == 2)
    }

    @Test("Add photo to folder assigns correct orderIndex")
    func addPhoto() throws {
        let dm = try makeManager()
        let folder = dm.createFolder(name: "Shots", parentId: nil)
        let p1 = dm.addPhoto(assetIdentifier: "asset-1", to: folder)
        let p2 = dm.addPhoto(assetIdentifier: "asset-2", to: folder)
        #expect(p1.orderIndex == 0)
        #expect(p2.orderIndex == 1)
    }

    @Test("fetchPhotos returns photos sorted by orderIndex")
    func fetchPhotosSorted() throws {
        let dm = try makeManager()
        let folder = dm.createFolder(name: "Events", parentId: nil)
        dm.addPhoto(assetIdentifier: "z", to: folder)
        dm.addPhoto(assetIdentifier: "a", to: folder)
        dm.addPhoto(assetIdentifier: "m", to: folder)
        let photos = dm.fetchPhotos(in: folder)
        #expect(photos[0].id == "z")
        #expect(photos[1].id == "a")
        #expect(photos[2].id == "m")
    }

    @Test("updatePhotoOrder persists new sequence")
    func updatePhotoOrder() throws {
        let dm = try makeManager()
        let folder = dm.createFolder(name: "Reorder", parentId: nil)
        let p1 = dm.addPhoto(assetIdentifier: "first", to: folder)
        let p2 = dm.addPhoto(assetIdentifier: "second", to: folder)
        let p3 = dm.addPhoto(assetIdentifier: "third", to: folder)
        dm.updatePhotoOrder([p3, p1, p2])
        #expect(p3.orderIndex == 0)
        #expect(p1.orderIndex == 1)
        #expect(p2.orderIndex == 2)
    }

    @Test("Delete folder removes it from fetch results")
    func deleteFolder() throws {
        let dm = try makeManager()
        let folder = dm.createFolder(name: "ToDelete", parentId: nil)
        dm.deleteFolder(folder)
        let folders = dm.fetchFolders(parentId: nil)
        #expect(!folders.map(\.id).contains(folder.id))
    }

    @Test("Delete folder also deletes its photos (cascade)")
    func deleteFolderCascadesPhotos() throws {
        let dm = try makeManager()
        let folder = dm.createFolder(name: "Cascade", parentId: nil)
        dm.addPhoto(assetIdentifier: "orphan-1", to: folder)
        dm.addPhoto(assetIdentifier: "orphan-2", to: folder)
        dm.deleteFolder(folder)
        // After cascade delete, photos should be gone
        let descriptor = FetchDescriptor<PhotoReference>()
        let remaining = (try? dm.modelContext.fetch(descriptor)) ?? []
        #expect(remaining.filter { $0.folderId == folder.id }.isEmpty)
    }
}
```

- [ ] **Step 2: Run to verify failure**

```bash
cd ~/openclaw/builds/ifauxto
xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0' \
  -only-testing:iFauxtoTests/DataManagerTests 2>&1 | tail -20
```

Expected: compile error — `DataManager` not found.

- [ ] **Step 3: Implement DataManager.swift**

Create `iFauxto/Models/DataManager.swift`:

```swift
import SwiftData
import Foundation

@MainActor
final class DataManager: ObservableObject {
    let modelContainer: ModelContainer
    let modelContext: ModelContext

    // MARK: Init

    init(inMemory: Bool = false) throws {
        let schema = Schema([Folder.self, PhotoReference.self])
        let config: ModelConfiguration
        if inMemory {
            config = ModelConfiguration(schema: schema, isStoredInMemoryOnly: true)
        } else {
            config = ModelConfiguration(
                schema: schema,
                isStoredInMemoryOnly: false,
                cloudKitDatabase: .private("iCloud.com.ifauxto.app")
            )
        }
        modelContainer = try ModelContainer(for: schema, configurations: [config])
        modelContext = modelContainer.mainContext
    }

    // MARK: Folder CRUD

    func createFolder(name: String, parentId: String? = nil) -> Folder {
        let siblings = fetchFolders(parentId: parentId)
        let order = siblings.count
        let folder = Folder(name: name, parentId: parentId, order: order)
        modelContext.insert(folder)
        try? modelContext.save()
        return folder
    }

    func fetchFolders(parentId: String? = nil) -> [Folder] {
        let descriptor: FetchDescriptor<Folder>
        if let pid = parentId {
            descriptor = FetchDescriptor<Folder>(
                predicate: #Predicate { $0.parentId == pid },
                sortBy: [SortDescriptor(\.order)]
            )
        } else {
            descriptor = FetchDescriptor<Folder>(
                predicate: #Predicate { $0.parentId == nil },
                sortBy: [SortDescriptor(\.order)]
            )
        }
        return (try? modelContext.fetch(descriptor)) ?? []
    }

    func deleteFolder(_ folder: Folder) {
        modelContext.delete(folder)
        try? modelContext.save()
    }

    func renameFolder(_ folder: Folder, to name: String) {
        folder.name = name
        try? modelContext.save()
    }

    func updateFolderOrder(_ folders: [Folder]) {
        for (index, folder) in folders.enumerated() {
            folder.order = index
        }
        try? modelContext.save()
    }

    // MARK: Photo CRUD

    func addPhoto(assetIdentifier: String, to folder: Folder) -> PhotoReference {
        let order = folder.photoReferences.count
        let ref = PhotoReference(assetIdentifier: assetIdentifier, folderId: folder.id, orderIndex: order)
        ref.folder = folder
        modelContext.insert(ref)
        folder.photoReferences.append(ref)
        try? modelContext.save()
        return ref
    }

    func addPhotos(assetIdentifiers: [String], to folder: Folder) {
        for identifier in assetIdentifiers {
            // Skip duplicates in this folder
            guard !folder.photoReferences.contains(where: { $0.id == identifier }) else { continue }
            _ = addPhoto(assetIdentifier: identifier, to: folder)
        }
    }

    func fetchPhotos(in folder: Folder) -> [PhotoReference] {
        return folder.photoReferences.sorted { $0.orderIndex < $1.orderIndex }
    }

    func updatePhotoOrder(_ photos: [PhotoReference]) {
        for (index, photo) in photos.enumerated() {
            photo.orderIndex = index
        }
        try? modelContext.save()
    }

    func removePhoto(_ photo: PhotoReference, from folder: Folder) {
        folder.photoReferences.removeAll { $0.id == photo.id }
        modelContext.delete(photo)
        try? modelContext.save()
    }

    func removePhotos(_ photos: [PhotoReference], from folder: Folder) {
        for photo in photos {
            removePhoto(photo, from: folder)
        }
        // Re-index remaining
        updatePhotoOrder(fetchPhotos(in: folder))
    }

    func movePhotos(_ photos: [PhotoReference], to destination: Folder) {
        for photo in photos {
            photo.folderId = destination.id
            photo.folder = destination
            photo.orderIndex = destination.photoReferences.count
            destination.photoReferences.append(photo)
        }
        try? modelContext.save()
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/openclaw/builds/ifauxto
xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0' \
  -only-testing:iFauxtoTests/DataManagerTests 2>&1 | tail -30
```

Expected: all DataManager tests pass.

- [ ] **Step 5: Regenerate xcodeproj (new source files added)**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate
```

- [ ] **Step 6: Commit DataManager**

```bash
cd ~/openclaw/builds/ifauxto
git add iFauxto/Models/DataManager.swift iFauxtoTests/DataManagerTests.swift
git commit -m "feat: add DataManager with folder/photo CRUD and ordering"
```

---

## Task 4: PhotoKitService

**Files:**
- Create: `iFauxto/Services/PhotoKitService.swift`
- Create: `iFauxto/Utils/Extensions.swift`

Note: PHAsset cannot be instantiated in unit tests without a real device/simulator photo library. Test the service's interface and error paths only.

- [ ] **Step 1: Implement PhotoKitService.swift**

Create `iFauxto/Services/PhotoKitService.swift`:

```swift
import Photos
import UIKit
import SwiftUI

@MainActor
final class PhotoKitService: ObservableObject {
    @Published var authorizationStatus: PHAuthorizationStatus = PHPhotoLibrary.authorizationStatus(for: .readWrite)

    // MARK: Authorization

    func requestAuthorization() async {
        let status = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
        authorizationStatus = status
    }

    var isAuthorized: Bool {
        authorizationStatus == .authorized || authorizationStatus == .limited
    }

    // MARK: Asset Fetching

    func fetchAsset(withIdentifier identifier: String) -> PHAsset? {
        let result = PHAsset.fetchAssets(withLocalIdentifiers: [identifier], options: nil)
        return result.firstObject
    }

    /// Returns a UIImage thumbnail for a given PHAsset identifier.
    func loadThumbnail(for identifier: String, targetSize: CGSize = CGSize(width: 200, height: 200)) async -> UIImage? {
        guard let asset = fetchAsset(withIdentifier: identifier) else { return nil }
        return await withCheckedContinuation { continuation in
            let options = PHImageRequestOptions()
            options.deliveryMode = .opportunistic
            options.resizeMode = .fast
            options.isNetworkAccessAllowed = true
            options.isSynchronous = false
            var didResume = false
            PHImageManager.default().requestImage(
                for: asset,
                targetSize: targetSize,
                contentMode: .aspectFill,
                options: options
            ) { image, info in
                // opportunistic mode can call back twice; only resume once
                guard !didResume else { return }
                if let isDegraded = info?[PHImageResultIsDegradedKey] as? Bool, isDegraded { return }
                didResume = true
                continuation.resume(returning: image)
            }
        }
    }

    /// Returns a full-resolution UIImage for a given PHAsset identifier.
    func loadFullImage(for identifier: String) async -> UIImage? {
        guard let asset = fetchAsset(withIdentifier: identifier) else { return nil }
        return await withCheckedContinuation { continuation in
            let options = PHImageRequestOptions()
            options.deliveryMode = .highQualityFormat
            options.isNetworkAccessAllowed = true
            options.isSynchronous = false
            PHImageManager.default().requestImage(
                for: asset,
                targetSize: PHImageManagerMaximumSize,
                contentMode: .aspectFit,
                options: options
            ) { image, _ in
                continuation.resume(returning: image)
            }
        }
    }

    /// Fetches all PHAsset identifiers from the user's library (for the photo picker flow).
    func fetchAllAssetIdentifiers() -> [String] {
        let fetchOptions = PHFetchOptions()
        fetchOptions.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        let result = PHAsset.fetchAssets(with: .image, options: fetchOptions)
        var identifiers: [String] = []
        result.enumerateObjects { asset, _, _ in
            identifiers.append(asset.localIdentifier)
        }
        return identifiers
    }
}
```

- [ ] **Step 2: Create Extensions.swift**

Create `iFauxto/Utils/Extensions.swift`:

```swift
import SwiftUI
import Photos

extension Array {
    /// Moves elements at the given offsets to the destination index, returning the reordered array.
    mutating func move(fromOffsets source: IndexSet, toOffset destination: Int) {
        var result = self
        let elements = source.map { result[$0] }
        result.remove(atOffsets: source)
        let adjusted = destination - source.filter { $0 < destination }.count
        result.insert(contentsOf: elements, at: adjusted)
        self = result
    }
}

extension Color {
    static let systemBackground = Color(UIColor.systemBackground)
    static let secondarySystemBackground = Color(UIColor.secondarySystemBackground)
}

extension View {
    /// Applies a modifier only on iOS 17+.
    @ViewBuilder
    func ifAvailable<Content: View>(@ViewBuilder transform: (Self) -> Content) -> some View {
        transform(self)
    }
}
```

- [ ] **Step 3: Build to verify compilation**

```bash
cd ~/openclaw/builds/ifauxto
xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0' 2>&1 | tail -10
```

Expected: `BUILD SUCCEEDED`

- [ ] **Step 4: Regenerate xcodeproj and commit**

```bash
cd ~/openclaw/builds/ifauxto
xcodegen generate
git add iFauxto/Services/PhotoKitService.swift iFauxto/Utils/Extensions.swift
git commit -m "feat: add PhotoKitService for PHAsset access and Extensions"
```

---

## Task 5: SyncManager and CloudKit Scaffold

**Files:**
- Create: `iFauxto/Services/SyncManager.swift`
- Create: `iFauxto/Services/CloudKitService.swift`

The CloudKit sync is handled automatically by SwiftData's `ModelConfiguration(cloudKitDatabase:)`. These files provide a coordination layer and a hook for future conflict resolution.

- [ ] **Step 1: Implement SyncManager.swift**

Create `iFauxto/Services/SyncManager.swift`:

```swift
import Foundation
import SwiftData
import Combine

/// Coordinates CloudKit sync state and notifies the UI of sync events.
/// SwiftData handles the actual sync via ModelConfiguration(cloudKitDatabase:).
/// This class surfaces status and triggers manual refresh when needed.
@MainActor
final class SyncManager: ObservableObject {
    @Published var isSyncing: Bool = false
    @Published var lastSyncDate: Date?
    @Published var syncError: Error?

    private let dataManager: DataManager
    private var cancellables = Set<AnyCancellable>()

    init(dataManager: DataManager) {
        self.dataManager = dataManager
        observeRemoteChanges()
    }

    /// SwiftData + CloudKit fires NSPersistentStoreRemoteChange notifications.
    private func observeRemoteChanges() {
        NotificationCenter.default
            .publisher(for: NSPersistentCloudKitContainer.eventChangedNotification)
            .receive(on: DispatchQueue.main)
            .sink { [weak self] notification in
                self?.handleCloudKitEvent(notification)
            }
            .store(in: &cancellables)
    }

    private func handleCloudKitEvent(_ notification: Notification) {
        guard let event = notification.userInfo?[NSPersistentCloudKitContainer.eventNotificationUserInfoKey]
            as? NSPersistentCloudKitContainer.Event else { return }

        switch event.type {
        case .setup:
            break
        case .import:
            isSyncing = event.endDate == nil
            if event.endDate != nil { lastSyncDate = event.endDate }
        case .export:
            isSyncing = event.endDate == nil
        @unknown default:
            break
        }

        if let error = event.error {
            syncError = error
        }
    }
}
```

- [ ] **Step 2: Implement CloudKitService.swift**

Create `iFauxto/Services/CloudKitService.swift`:

```swift
import CloudKit
import Foundation

/// Placeholder for CloudKit-specific operations (conflict resolution, sharing, etc.).
/// Core sync is handled by SwiftData's ModelConfiguration. This class extends as needed.
final class CloudKitService {
    static let containerIdentifier = "iCloud.com.ifauxto.app"
    private let container: CKContainer

    init() {
        container = CKContainer(identifier: Self.containerIdentifier)
    }

    /// Checks whether the user is signed into iCloud.
    func checkAccountStatus() async throws -> CKAccountStatus {
        return try await container.accountStatus()
    }
}
```

- [ ] **Step 3: Build to verify compilation**

```bash
cd ~/openclaw/builds/ifauxto
xcodegen generate
xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0' 2>&1 | tail -10
```

Expected: `BUILD SUCCEEDED`

- [ ] **Step 4: Run all Part 1 tests**

```bash
cd ~/openclaw/builds/ifauxto
xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0' \
  -only-testing:iFauxtoTests 2>&1 | grep -E "(Test Suite|PASS|FAIL|error:)"
```

Expected: all test suites pass, no errors.

- [ ] **Step 5: Commit Part 1 complete**

```bash
cd ~/openclaw/builds/ifauxto
git add iFauxto/Services/SyncManager.swift iFauxto/Services/CloudKitService.swift
git commit -m "feat: add SyncManager and CloudKitService scaffold"
```

---

**End of Part 1.** Continue with `2026-03-27-ifauxto-part2-ui.md`.
