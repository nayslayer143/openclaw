# iFauxto — Part 2: UI, Drag-and-Drop, and Interactions

> Read before this: `2026-03-27-ifauxto-part1-foundation.md`
> Read after this: nothing (this is last)
>
> Covers: App entry point, all SwiftUI views, drag-and-drop reordering,
> edit mode, multi-select, photo picker integration.

---

## File Map

| File | Responsibility |
|------|---------------|
| `iFauxto/App/iFauxtoApp.swift` | App entry point, ModelContainer injection |
| `iFauxto/App/ContentView.swift` | Root view, permission gate |
| `iFauxto/Views/HomeView.swift` | Root folder list with reorder and create |
| `iFauxto/Views/FolderCreationSheet.swift` | Sheet for naming + creating a new folder |
| `iFauxto/Views/FolderView.swift` | Grid of photos inside a folder |
| `iFauxto/Views/PhotoThumbnailView.swift` | Individual grid cell with selection overlay |
| `iFauxto/Views/PhotoViewer.swift` | Full-screen swipe viewer — no overlays |
| `iFauxto/Views/EditModeToolbar.swift` | Bottom toolbar in edit mode (move, delete) |
| `iFauxto/Utils/DragDropManager.swift` | Stateless helper for reorder index math |

---

## Task 6: App Entry Point

**Files:**
- Create: `iFauxto/App/iFauxtoApp.swift`
- Create: `iFauxto/App/ContentView.swift`

- [ ] **Step 1: Implement iFauxtoApp.swift**

Create `iFauxto/App/iFauxtoApp.swift`:

```swift
import SwiftUI
import SwiftData

@main
struct iFauxtoApp: App {
    @StateObject private var dataManager: DataManager
    @StateObject private var photoKitService = PhotoKitService()
    @StateObject private var syncManager: SyncManager

    init() {
        do {
            let dm = try DataManager()
            _dataManager = StateObject(wrappedValue: dm)
            _syncManager = StateObject(wrappedValue: SyncManager(dataManager: dm))
        } catch {
            fatalError("Failed to initialize DataManager: \(error)")
        }
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(dataManager)
                .environmentObject(photoKitService)
                .environmentObject(syncManager)
        }
    }
}
```

- [ ] **Step 2: Implement ContentView.swift**

Create `iFauxto/App/ContentView.swift`:

```swift
import SwiftUI
import Photos

struct ContentView: View {
    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var hasCheckedAuth = false

    var body: some View {
        Group {
            if !hasCheckedAuth {
                ProgressView("Loading…")
                    .task { await checkAuthorization() }
            } else if photoKitService.isAuthorized {
                HomeView()
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

    private func checkAuthorization() async {
        if photoKitService.authorizationStatus == .notDetermined {
            await photoKitService.requestAuthorization()
        }
        hasCheckedAuth = true
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

- [ ] **Step 3: Build to verify**

```bash
cd ~/openclaw/builds/ifauxto
xcodegen generate
xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0' 2>&1 | tail -10
```

Expected: `BUILD SUCCEEDED`

- [ ] **Step 4: Commit**

```bash
cd ~/openclaw/builds/ifauxto
git add iFauxto/App/iFauxtoApp.swift iFauxto/App/ContentView.swift
git commit -m "feat: add app entry point and permission gate"
```

---

## Task 7: HomeView — Folder List

**Files:**
- Create: `iFauxto/Views/HomeView.swift`

- [ ] **Step 1: Implement HomeView.swift**

Create `iFauxto/Views/HomeView.swift`:

```swift
import SwiftUI

struct HomeView: View {
    @EnvironmentObject var dataManager: DataManager
    @State private var folders: [Folder] = []
    @State private var showingCreateFolder = false
    @State private var editMode: EditMode = .inactive

    var body: some View {
        NavigationStack {
            Group {
                if folders.isEmpty {
                    emptyState
                } else {
                    folderList
                }
            }
            .navigationTitle("iFauxto")
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    EditButton()
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        showingCreateFolder = true
                    } label: {
                        Image(systemName: "folder.badge.plus")
                    }
                }
            }
            .environment(\.editMode, $editMode)
            .sheet(isPresented: $showingCreateFolder, onDismiss: loadFolders) {
                FolderCreationSheet(parentId: nil)
            }
            .onAppear(perform: loadFolders)
        }
    }

    private var folderList: some View {
        List {
            ForEach(folders) { folder in
                NavigationLink {
                    FolderView(folder: folder)
                } label: {
                    FolderRowView(folder: folder)
                }
            }
            .onMove { source, destination in
                folders.move(fromOffsets: source, toOffset: destination)
                dataManager.updateFolderOrder(folders)
            }
            .onDelete { indexSet in
                indexSet.forEach { dataManager.deleteFolder(folders[$0]) }
                folders.remove(atOffsets: indexSet)
            }
        }
        .listStyle(.plain)
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "folder")
                .font(.system(size: 56))
                .foregroundStyle(.secondary)
            Text("No Folders Yet")
                .font(.title2.weight(.semibold))
            Text("Tap + to create your first folder.")
                .foregroundStyle(.secondary)
            Button("Create Folder") {
                showingCreateFolder = true
            }
            .buttonStyle(.borderedProminent)
        }
    }

    private func loadFolders() {
        folders = dataManager.fetchFolders(parentId: nil)
    }
}

struct FolderRowView: View {
    let folder: Folder

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: "folder.fill")
                .font(.title2)
                .foregroundStyle(.yellow)
            VStack(alignment: .leading, spacing: 2) {
                Text(folder.name)
                    .font(.body.weight(.medium))
                Text("\(folder.photoReferences.count) photos")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}
```

- [ ] **Step 2: Build to verify**

```bash
cd ~/openclaw/builds/ifauxto
xcodegen generate
xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0' 2>&1 | tail -10
```

Expected: `BUILD SUCCEEDED`

- [ ] **Step 3: Commit**

```bash
cd ~/openclaw/builds/ifauxto
git add iFauxto/Views/HomeView.swift
git commit -m "feat: add HomeView with folder list, reorder, and empty state"
```

---

## Task 8: FolderCreationSheet

**Files:**
- Create: `iFauxto/Views/FolderCreationSheet.swift`

- [ ] **Step 1: Implement FolderCreationSheet.swift**

Create `iFauxto/Views/FolderCreationSheet.swift`:

```swift
import SwiftUI

struct FolderCreationSheet: View {
    let parentId: String?
    @EnvironmentObject var dataManager: DataManager
    @Environment(\.dismiss) var dismiss

    @State private var folderName = ""
    @FocusState private var nameFieldFocused: Bool

    var body: some View {
        NavigationStack {
            Form {
                Section("Folder Name") {
                    TextField("e.g. Japan 2025", text: $folderName)
                        .focused($nameFieldFocused)
                        .submitLabel(.done)
                        .onSubmit(createAndDismiss)
                }
                if let parentId {
                    Section("Location") {
                        Text("Inside: \(parentFolderName(for: parentId))")
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("New Folder")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Create") { createAndDismiss() }
                        .fontWeight(.semibold)
                        .disabled(folderName.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
            .onAppear { nameFieldFocused = true }
        }
    }

    private func createAndDismiss() {
        let trimmed = folderName.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        dataManager.createFolder(name: trimmed, parentId: parentId)
        dismiss()
    }

    private func parentFolderName(for id: String) -> String {
        let folders = dataManager.fetchFolders(parentId: nil)
        return folders.first(where: { $0.id == id })?.name ?? "Folder"
    }
}
```

- [ ] **Step 2: Build and commit**

```bash
cd ~/openclaw/builds/ifauxto
xcodegen generate
xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0' 2>&1 | tail -5
git add iFauxto/Views/FolderCreationSheet.swift
git commit -m "feat: add FolderCreationSheet for naming and creating folders"
```

---

## Task 9: DragDropManager Helper

**Files:**
- Create: `iFauxto/Utils/DragDropManager.swift`

- [ ] **Step 1: Implement DragDropManager.swift**

Create `iFauxto/Utils/DragDropManager.swift`:

```swift
import Foundation

/// Stateless helpers for drag-and-drop index math.
/// All mutations are returned as new arrays — callers persist the result.
enum DragDropManager {

    /// Swaps the item with `draggedId` into the position of `targetId` and vice versa.
    /// Swap semantics: drop source takes target's slot, target fills the gap.
    /// - Returns: reordered array, or original array if either id is not found.
    static func reorder<T: Identifiable>(
        _ items: [T],
        draggedId: T.ID,
        targetId: T.ID
    ) -> [T] where T.ID: Equatable {
        guard draggedId != targetId,
              let sourceIndex = items.firstIndex(where: { $0.id == draggedId }),
              let destinationIndex = items.firstIndex(where: { $0.id == targetId })
        else { return items }

        var result = items
        result.swapAt(sourceIndex, destinationIndex)
        return result
    }
}
```

- [ ] **Step 2: Build and commit**

```bash
cd ~/openclaw/builds/ifauxto
xcodegen generate
xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0' 2>&1 | tail -5
git add iFauxto/Utils/DragDropManager.swift
git commit -m "feat: add DragDropManager stateless reorder helper"
```

---

## Task 10: PhotoThumbnailView

**Files:**
- Create: `iFauxto/Views/PhotoThumbnailView.swift`

- [ ] **Step 1: Implement PhotoThumbnailView.swift**

Create `iFauxto/Views/PhotoThumbnailView.swift`:

```swift
import SwiftUI

struct PhotoThumbnailView: View {
    let photo: PhotoReference
    let isSelected: Bool
    let isEditMode: Bool

    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var thumbnail: UIImage?

    private let size: CGFloat = 120

    var body: some View {
        ZStack(alignment: .topTrailing) {
            thumbnailImage
                .frame(width: size, height: size)
                .clipped()
                .contentShape(Rectangle())

            if isEditMode {
                selectionIndicator
                    .padding(4)
            }
        }
        .animation(.easeInOut(duration: 0.15), value: isSelected)
        .task(id: photo.id) {
            thumbnail = await photoKitService.loadThumbnail(
                for: photo.id,
                targetSize: CGSize(width: size * 2, height: size * 2)
            )
        }
    }

    @ViewBuilder
    private var thumbnailImage: some View {
        if let img = thumbnail {
            Image(uiImage: img)
                .resizable()
                .scaledToFill()
                .overlay(
                    isSelected
                        ? Color.black.opacity(0.3)
                        : Color.clear
                )
        } else {
            Rectangle()
                .fill(Color.secondarySystemBackground)
                .overlay(ProgressView())
        }
    }

    private var selectionIndicator: some View {
        ZStack {
            Circle()
                .fill(isSelected ? Color.accentColor : Color.white.opacity(0.7))
                .frame(width: 22, height: 22)
            if isSelected {
                Image(systemName: "checkmark")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.white)
            }
        }
    }
}
```

- [ ] **Step 2: Build and commit**

```bash
cd ~/openclaw/builds/ifauxto
xcodegen generate
xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0' 2>&1 | tail -5
git add iFauxto/Views/PhotoThumbnailView.swift
git commit -m "feat: add PhotoThumbnailView with async image loading and selection overlay"
```

---

## Task 11: FolderView — Photo Grid with Drag-and-Drop

**Files:**
- Create: `iFauxto/Views/FolderView.swift`

- [ ] **Step 1: Implement FolderView.swift**

Create `iFauxto/Views/FolderView.swift`:

```swift
import SwiftUI
import PhotosUI

struct FolderView: View {
    let folder: Folder

    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var photoKitService: PhotoKitService

    @State private var subfolders: [Folder] = []
    @State private var photos: [PhotoReference] = []
    @State private var isEditMode = false
    @State private var selectedPhotoIds: Set<String> = []
    @State private var showingPhotoPicker = false
    @State private var showingMoveSheet = false
    @State private var showingSubfolderCreation = false

    private let columns = [GridItem(.adaptive(minimum: 110), spacing: 2)]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                // Subfolders section — shown when this folder has children
                if !subfolders.isEmpty {
                    subfolderSection
                }
                // Photos grid
                if !photos.isEmpty {
                    LazyVGrid(columns: columns, spacing: 2) {
                        ForEach(photos) { photo in
                            PhotoThumbnailView(
                                photo: photo,
                                isSelected: selectedPhotoIds.contains(photo.id),
                                isEditMode: isEditMode
                            )
                            .draggable(photo.id) {
                                PhotoThumbnailView(
                                    photo: photo,
                                    isSelected: false,
                                    isEditMode: false
                                )
                                .frame(width: 80, height: 80)
                                .opacity(0.9)
                            }
                            .dropDestination(for: String.self) { items, _ in
                                guard let sourceId = items.first, sourceId != photo.id else { return false }
                                withAnimation(.easeInOut(duration: 0.2)) {
                                    photos = DragDropManager.reorder(photos, draggedId: sourceId, targetId: photo.id)
                                }
                                dataManager.updatePhotoOrder(photos)
                                return true
                            }
                            .onTapGesture {
                                if isEditMode { toggleSelection(photo.id) }
                            }
                            .overlay {
                                if !isEditMode {
                                    NavigationLink {
                                        PhotoViewer(
                                            photos: photos,
                                            startIndex: photos.firstIndex(where: { $0.id == photo.id }) ?? 0
                                        )
                                    } label: {
                                        Color.clear
                                    }
                                }
                            }
                        }
                    }
                    .padding(2)
                }
                if subfolders.isEmpty && photos.isEmpty {
                    emptyState
                }
            }
        }
        .navigationTitle(folder.name)
        .navigationBarTitleDisplayMode(.large)
        .toolbar { toolbarItems }
        .safeAreaInset(edge: .bottom) {
            if isEditMode && !selectedPhotoIds.isEmpty {
                EditModeToolbar(
                    selectedCount: selectedPhotoIds.count,
                    onMove: { showingMoveSheet = true },
                    onDelete: deleteSelectedPhotos
                )
            }
        }
        .sheet(isPresented: $showingPhotoPicker, onDismiss: loadContent) {
            PhotoPickerView { identifiers in
                dataManager.addPhotos(assetIdentifiers: identifiers, to: folder)
            }
        }
        .sheet(isPresented: $showingMoveSheet, onDismiss: loadContent) {
            FolderPickerSheet(
                excludingFolderId: folder.id,
                onSelect: { destination in
                    let toMove = photos.filter { selectedPhotoIds.contains($0.id) }
                    dataManager.movePhotos(toMove, to: destination)
                    selectedPhotoIds.removeAll()
                    isEditMode = false
                    showingMoveSheet = false
                }
            )
        }
        .sheet(isPresented: $showingSubfolderCreation, onDismiss: loadContent) {
            FolderCreationSheet(parentId: folder.id)
        }
        .onAppear(perform: loadContent)
    }

    // MARK: Subfolders section

    private var subfolderSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Folders")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 16)
                .padding(.top, 12)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(subfolders) { sub in
                        NavigationLink {
                            FolderView(folder: sub)
                        } label: {
                            VStack(spacing: 6) {
                                Image(systemName: "folder.fill")
                                    .font(.system(size: 36))
                                    .foregroundStyle(.yellow)
                                Text(sub.name)
                                    .font(.caption)
                                    .lineLimit(2)
                                    .multilineTextAlignment(.center)
                                    .frame(width: 72)
                            }
                        }
                        .foregroundStyle(.primary)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 12)
            }
            Divider()
        }
    }

    // MARK: Empty state

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "photo.on.rectangle")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            Text("Empty Folder")
                .font(.title3.weight(.medium))
            Text("Tap ··· to add photos or create a subfolder.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 80)
    }

    // MARK: Toolbar

    @ToolbarContentBuilder
    private var toolbarItems: some ToolbarContent {
        ToolbarItem(placement: .navigationBarTrailing) {
            if isEditMode {
                Button("Done") {
                    isEditMode = false
                    selectedPhotoIds.removeAll()
                }
                .fontWeight(.semibold)
            } else {
                Menu {
                    Button {
                        showingPhotoPicker = true
                    } label: {
                        Label("Add Photos", systemImage: "photo.badge.plus")
                    }
                    Button {
                        showingSubfolderCreation = true
                    } label: {
                        Label("New Subfolder", systemImage: "folder.badge.plus")
                    }
                    Divider()
                    Button {
                        isEditMode = true
                    } label: {
                        Label("Select Photos", systemImage: "checkmark.circle")
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
            }
        }
    }

    // MARK: Actions

    private func loadContent() {
        subfolders = dataManager.fetchFolders(parentId: folder.id)
        photos = dataManager.fetchPhotos(in: folder)
    }

    private func toggleSelection(_ id: String) {
        if selectedPhotoIds.contains(id) {
            selectedPhotoIds.remove(id)
        } else {
            selectedPhotoIds.insert(id)
        }
    }

    private func deleteSelectedPhotos() {
        let toDelete = photos.filter { selectedPhotoIds.contains($0.id) }
        dataManager.removePhotos(toDelete, from: folder)
        selectedPhotoIds.removeAll()
        isEditMode = false
        loadContent()
    }
}
```

- [ ] **Step 2: Build to verify**

```bash
cd ~/openclaw/builds/ifauxto
xcodegen generate
xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0' 2>&1 | tail -10
```

Expected: `BUILD SUCCEEDED`

- [ ] **Step 3: Commit**

```bash
cd ~/openclaw/builds/ifauxto
git add iFauxto/Views/FolderView.swift
git commit -m "feat: add FolderView with drag-and-drop reordering and edit mode"
```

---

## Task 12: PhotoViewer

**Files:**
- Create: `iFauxto/Views/PhotoViewer.swift`

- [ ] **Step 1: Implement PhotoViewer.swift**

Create `iFauxto/Views/PhotoViewer.swift`:

```swift
import SwiftUI

struct PhotoViewer: View {
    let photos: [PhotoReference]
    let startIndex: Int

    @EnvironmentObject var photoKitService: PhotoKitService
    @Environment(\.dismiss) var dismiss
    @State private var currentIndex: Int

    init(photos: [PhotoReference], startIndex: Int) {
        self.photos = photos
        self.startIndex = startIndex
        _currentIndex = State(initialValue: startIndex)
    }

    var body: some View {
        TabView(selection: $currentIndex) {
            ForEach(Array(photos.enumerated()), id: \.offset) { index, photo in
                FullPhotoView(identifier: photo.id)
                    .tag(index)
            }
        }
        .tabViewStyle(.page(indexDisplayMode: .never))
        .background(Color.black)
        .ignoresSafeArea()
        .overlay(alignment: .topLeading) {
            Button {
                dismiss()
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.title)
                    .foregroundStyle(.white, .black.opacity(0.5))
                    .padding(16)
            }
        }
        .overlay(alignment: .bottom) {
            Text("\(currentIndex + 1) / \(photos.count)")
                .font(.caption)
                .foregroundStyle(.white.opacity(0.7))
                .padding(.bottom, 20)
        }
        .onAppear { currentIndex = startIndex }
    }
}

private struct FullPhotoView: View {
    let identifier: String
    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var image: UIImage?

    var body: some View {
        Group {
            if let img = image {
                Image(uiImage: img)
                    .resizable()
                    .scaledToFit()
            } else {
                ProgressView()
                    .tint(.white)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task(id: identifier) {
            image = await photoKitService.loadFullImage(for: identifier)
        }
    }
}
```

- [ ] **Step 2: Build and commit**

```bash
cd ~/openclaw/builds/ifauxto
xcodegen generate
xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0' 2>&1 | tail -5
git add iFauxto/Views/PhotoViewer.swift
git commit -m "feat: add PhotoViewer with full-screen swipe navigation, no overlays"
```

---

## Task 13: EditModeToolbar and FolderPickerSheet

**Files:**
- Create: `iFauxto/Views/EditModeToolbar.swift`

- [ ] **Step 1: Implement EditModeToolbar.swift**

Create `iFauxto/Views/EditModeToolbar.swift`:

```swift
import SwiftUI

struct EditModeToolbar: View {
    let selectedCount: Int
    let onMove: () -> Void
    let onDelete: () -> Void

    var body: some View {
        HStack(spacing: 0) {
            Button(action: onMove) {
                VStack(spacing: 4) {
                    Image(systemName: "folder.badge.plus")
                    Text("Move")
                        .font(.caption)
                }
                .frame(maxWidth: .infinity)
            }

            Divider().frame(height: 36)

            Button(role: .destructive, action: onDelete) {
                VStack(spacing: 4) {
                    Image(systemName: "trash")
                    Text("Remove")
                        .font(.caption)
                }
                .frame(maxWidth: .infinity)
            }
        }
        .padding(.vertical, 8)
        .background(.regularMaterial)
        .overlay(alignment: .top) {
            Divider()
        }
    }
}

struct FolderPickerSheet: View {
    let excludingFolderId: String
    let onSelect: (Folder) -> Void

    @EnvironmentObject var dataManager: DataManager
    @Environment(\.dismiss) var dismiss
    @State private var rootFolders: [Folder] = []

    var body: some View {
        NavigationStack {
            List(rootFolders.filter { $0.id != excludingFolderId }) { folder in
                Button {
                    onSelect(folder)
                } label: {
                    HStack {
                        Image(systemName: "folder.fill")
                            .foregroundStyle(.yellow)
                        Text(folder.name)
                        Spacer()
                        Image(systemName: "chevron.right")
                            .foregroundStyle(.secondary)
                    }
                }
                .foregroundStyle(.primary)
            }
            .navigationTitle("Move To")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                }
            }
            .onAppear {
                rootFolders = dataManager.fetchFolders(parentId: nil)
            }
        }
    }
}
```

- [ ] **Step 2: Build and commit**

```bash
cd ~/openclaw/builds/ifauxto
xcodegen generate
xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0' 2>&1 | tail -5
git add iFauxto/Views/EditModeToolbar.swift
git commit -m "feat: add EditModeToolbar and FolderPickerSheet for batch operations"
```

---

## Task 14: Photo Picker Integration

**Files:**
- Create (inline in FolderView.swift context): `iFauxto/Views/PhotoPickerView.swift`

PhotosUI's `PHPickerViewController` is the correct API for adding photos without requesting full library write access.

- [ ] **Step 1: Implement PhotoPickerView.swift**

Create `iFauxto/Views/PhotoPickerView.swift`:

```swift
import SwiftUI
import PhotosUI

/// Wraps PHPickerViewController to let users pick photos from their library.
/// Returns PHAsset localIdentifiers — never UIImages (no duplication).
struct PhotoPickerView: UIViewControllerRepresentable {
    let onComplete: ([String]) -> Void

    func makeUIViewController(context: Context) -> PHPickerViewController {
        var config = PHPickerConfiguration(photoLibrary: .shared())
        config.selectionLimit = 0       // unlimited selection
        config.filter = .images
        config.preferredAssetRepresentationMode = .current

        let picker = PHPickerViewController(configuration: config)
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: PHPickerViewController, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(onComplete: onComplete)
    }

    final class Coordinator: NSObject, PHPickerViewControllerDelegate {
        let onComplete: ([String]) -> Void
        init(onComplete: @escaping ([String]) -> Void) { self.onComplete = onComplete }

        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            picker.dismiss(animated: true)
            // Extract localIdentifiers — only available when using PHPickerConfiguration(photoLibrary:)
            let identifiers = results.compactMap { $0.assetIdentifier }
            onComplete(identifiers)
        }
    }
}
```

- [ ] **Step 2: Build and commit**

```bash
cd ~/openclaw/builds/ifauxto
xcodegen generate
xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0' 2>&1 | tail -5
git add iFauxto/Views/PhotoPickerView.swift
git commit -m "feat: add PhotoPickerView using PHPickerViewController (no duplication)"
```

---

## Task 15: Full Test Suite Run and README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Run full test suite**

```bash
cd ~/openclaw/builds/ifauxto
xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0' 2>&1 \
  | grep -E "(Test Suite|Test Case|PASS|FAIL|BUILD|error:)"
```

Expected: `BUILD SUCCEEDED` and all test cases pass. Fix any failures before continuing.

- [ ] **Step 2: Create README**

Create `README.md`:

```markdown
# iFauxto

**Your photos. Your order.**

Manual-first iOS photo organization. Layers on top of Apple Photos — no duplication, no AI, no auto-sorting.

## Requirements

- Xcode 15.4+
- iOS 17.0+ target
- XcodeGen (`brew install xcodegen`)
- Apple Developer account (for iCloud/CloudKit entitlements)

## Setup

```bash
cd ~/openclaw/builds/ifauxto
xcodegen generate
open iFauxto.xcodeproj
```

Set your Development Team in Xcode (Signing & Capabilities tab) before building to device.

## Architecture

- **Overlay model:** References PHAsset via localIdentifier only. Zero photo duplication.
- **SwiftData + CloudKit:** Folder structure and ordering syncs via iCloud automatically.
- **No auto-reorder:** orderIndex is explicit and never overwritten by the system.

## Key Files

| File | Purpose |
|------|---------|
| `Models/Folder.swift` | SwiftData folder hierarchy |
| `Models/PhotoReference.swift` | PHAsset reference with orderIndex |
| `Models/DataManager.swift` | All CRUD and ordering operations |
| `Services/PhotoKitService.swift` | PHAsset access and image loading |
| `Views/FolderView.swift` | Photo grid with drag-and-drop |
| `Views/PhotoViewer.swift` | Full-screen viewer, swipe only |

## Testing

```bash
xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0'
```
```

- [ ] **Step 3: Final commit**

```bash
cd ~/openclaw/builds/ifauxto
git add README.md
git commit -m "docs: add README with setup and architecture overview"
```

- [ ] **Step 4: Tag MVP complete**

```bash
cd ~/openclaw/builds/ifauxto
git tag v0.1.0-mvp
```

---

**Part 2 complete. iFauxto MVP is buildable, testable, and ready for device testing.**

To run on a physical device: open `iFauxto.xcodeproj` in Xcode, set your Development Team under Signing & Capabilities, and build to your device. CloudKit sync requires a real device with an iCloud account.
