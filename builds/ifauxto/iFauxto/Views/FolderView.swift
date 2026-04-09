import SwiftUI
import PhotosUI

struct FolderView: View {
    let folder: Folder

    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var photoKitService: PhotoKitService
    @EnvironmentObject var navCoordinator: NavCoordinator
    @Environment(\.dismiss) private var dismiss

    @State private var subfolders: [Folder] = []
    @State private var photos: [PhotoReference] = []
    @State private var isEditMode = false
    @State private var selectedPhotoIds: Set<String> = []
    @State private var showingPhotoPicker = false
    @State private var showingMoveSheet = false
    @State private var showingSubfolderCreation = false
    @State private var showingSlideshow = false
    @State private var showingFilesImport = false

    /// Bound to the Folder model so the sort survives launches.
    private var photoSortMode: String { folder.sortMode }
    private func setPhotoSortMode(_ mode: String) {
        Haptics.select()
        folder.sortMode = mode
        try? dataManager.modelContext.save()
    }

    private var displayPhotos: [PhotoReference] {
        switch photoSortMode {
        case "alpha":
            return photos.sorted { $0.id.localizedCaseInsensitiveCompare($1.id) == .orderedAscending }
        case "recent":
            return photos.sorted { $0.orderIndex > $1.orderIndex }
        default:
            return photos
        }
    }

    @AppStorage("iFauxto.folderColumns") private var columnCount: Int = 3
    @State private var pinchBase: CGFloat = 0

    private var columns: [GridItem] {
        Array(repeating: GridItem(.flexible(), spacing: 2), count: max(2, min(8, columnCount)))
    }

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()

            ScrollView {
                Spacer().frame(height: 72) // room for sticky top bar

                VStack(alignment: .leading, spacing: 0) {
                    // Subfolders section
                    if !subfolders.isEmpty {
                        subfolderSection
                    }
                    // Photos grid
                    if !photos.isEmpty {
                        LazyVGrid(columns: columns, spacing: 2) {
                            ForEach(displayPhotos) { photo in
                                photoCell(photo)
                            }
                        }
                        .padding(2)
                    }
                if subfolders.isEmpty && photos.isEmpty {
                    emptyState
                }
                }
                .padding(.bottom, 60)
            }
            .scrollIndicators(.hidden)
            .simultaneousGesture(pinchGesture)

            BrandTopBar(
                title: folder.name,
                subtitle: "\(photos.count) \(photos.count == 1 ? "photo" : "photos")",
                onBack: { dismiss() },
                onHome: { navCoordinator.popToRoot() }
            ) {
                folderMenuButton
            }
        }
        .navigationBarHidden(true)
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
        .fullScreenCover(isPresented: $showingSlideshow) {
            SlideshowView(photoIds: photos.map(\.id))
        }
        #if targetEnvironment(macCatalyst)
        .dropDestination(for: URL.self) { urls, _ in
            let ids = FilesImportService.importFiles(urls)
            guard !ids.isEmpty else { return false }
            dataManager.addPhotos(assetIdentifiers: ids, to: folder)
            Haptics.success()
            loadContent()
            return true
        }
        #endif
        .sheet(isPresented: $showingFilesImport) {
            FilesImporterView { urls in
                let identifiers = FilesImportService.importFiles(urls)
                if !identifiers.isEmpty {
                    dataManager.addPhotos(assetIdentifiers: identifiers, to: folder)
                    Haptics.success()
                    loadContent()
                }
            }
            .presentationDetents([.height(120)])
        }
        .onAppear {
            loadContent()
            // Track this folder as the most recently opened — the
            // "Last Opened" home mode reads this on next launch.
            let s = dataManager.getOrCreateSettings()
            s.lastOpenedViewId = folder.id
            dataManager.saveSettings()
        }
    }

    // MARK: Photo cell

    @ViewBuilder
    private func photoCell(_ photo: PhotoReference) -> some View {
        // Minimal gesture stack: a single Button handles tap + nav in
        // non-edit mode, a tap gesture handles selection in edit mode.
        // `.draggable` / `.dropDestination` were removed from individual
        // cells because the gesture arbitration cost on 100+ cells was
        // eating scroll and pinch events. Reordering lives in a future
        // dedicated Reorder mode instead.
        let thumb = PhotoThumbnailView(
            photo: photo,
            isSelected: selectedPhotoIds.contains(photo.id),
            isEditMode: isEditMode
        )

        if isEditMode {
            thumb
                .contentShape(Rectangle())
                .onTapGesture { toggleSelection(photo.id) }
        } else {
            Button {
                Haptics.tap()
                let route = PhotoViewerRoute(
                    photoIds: photos.map(\.id),
                    startIndex: photos.firstIndex(where: { $0.id == photo.id }) ?? 0
                )
                navCoordinator.path.append(route)
            } label: {
                thumb
            }
            .buttonStyle(PressableButtonStyle(scale: 0.97))
        }
    }

    // MARK: Subfolders section

    private var subfolderSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("ALBUMS")
                .font(.system(size: 12))
                .foregroundStyle(Theme.Palette.textMuted)
                .tracking(0.4)
                .padding(.horizontal, 24)
                .padding(.top, 8)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 14) {
                    ForEach(subfolders) { sub in
                        NavigationLink(value: sub) {
                            VStack(spacing: 8) {
                                Image(systemName: "folder.fill")
                                    .font(.system(size: 44, weight: .regular))
                                    .foregroundStyle(Theme.Palette.folder)
                                    .shadow(color: Theme.Palette.folderEdge.opacity(0.5), radius: 0.5, x: 0, y: 0.5)
                                Text(sub.name)
                                    .font(.system(size: 12))
                                    .foregroundStyle(Theme.Palette.text)
                                    .lineLimit(2)
                                    .multilineTextAlignment(.center)
                                    .frame(width: 78)
                            }
                            .padding(8)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(PressableButtonStyle())
                        .simultaneousGesture(TapGesture().onEnded { Haptics.tap() })
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 14)
            }

            Rectangle()
                .fill(Theme.Palette.divider)
                .frame(height: 0.5)
        }
    }

    // MARK: Empty state

    private var emptyState: some View {
        VStack(spacing: 16) {
            Spacer(minLength: 80)
            Image(systemName: "photo.on.rectangle.angled")
                .font(.system(size: 56, weight: .light))
                .foregroundStyle(Theme.Palette.textDim)
                .symbolRenderingMode(.hierarchical)
            Text("Empty Album")
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            Text("Tap ··· to add photos or create a subfolder.")
                .font(.system(size: 14))
                .foregroundStyle(Theme.Palette.textMuted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
            Spacer()
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 20)
    }

    // MARK: Brand menu

    @ViewBuilder
    private var folderMenuButton: some View {
        if isEditMode {
            Button {
                Haptics.tap()
                isEditMode = false
                selectedPhotoIds.removeAll()
            } label: {
                Text("Done")
                    .font(Theme.Font.body(14, weight: .bold))
                    .foregroundStyle(Theme.Palette.accent)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 9)
                    .background(
                        Capsule().fill(.ultraThinMaterial)
                    )
                    .overlay(
                        Capsule().strokeBorder(Theme.Palette.accent.opacity(0.5), lineWidth: 1)
                    )
            }
            .buttonStyle(.plain)
        } else {
            Menu {
                Button { showingPhotoPicker = true } label: {
                    Label("Add Photos", systemImage: "photo.badge.plus")
                }
                Button { showingFilesImport = true } label: {
                    Label("Import from Files", systemImage: "doc.badge.plus")
                }
                Button { showingSubfolderCreation = true } label: {
                    Label("New Subfolder", systemImage: "folder.badge.plus")
                }
                Divider()
                Button {
                    isEditMode = true
                } label: {
                    Label("Select Photos", systemImage: "checkmark.circle")
                }
                Button {
                    togglePinAsHome()
                } label: {
                    Label(isPinnedAsHome ? "Unpin as Home" : "Pin as Home",
                          systemImage: isPinnedAsHome ? "pin.slash.fill" : "pin.fill")
                }
                Button {
                    showingSlideshow = true
                } label: {
                    Label("Play Slideshow", systemImage: "play.rectangle.fill")
                }
                .disabled(photos.isEmpty)
                Divider()
                Menu("Sort Photos") {
                    Button { setPhotoSortMode("custom") } label: {
                        Label("Manual Order", systemImage: photoSortMode == "custom" ? "checkmark" : "hand.point.up.left")
                    }
                    Button { setPhotoSortMode("alpha") } label: {
                        Label("By Name", systemImage: photoSortMode == "alpha" ? "checkmark" : "textformat")
                    }
                    Button { setPhotoSortMode("recent") } label: {
                        Label("Newest First", systemImage: photoSortMode == "recent" ? "checkmark" : "clock")
                    }
                }
            } label: {
                Image(systemName: "ellipsis")
                    .font(.system(size: 15, weight: .bold))
                    .foregroundStyle(Theme.Palette.text)
                    .frame(width: 38, height: 38)
                    .background(Circle().fill(.ultraThinMaterial))
                    .overlay(Circle().strokeBorder(Theme.Palette.stroke, lineWidth: 1))
            }
            .simultaneousGesture(TapGesture().onEnded { Haptics.tap() })
        }
    }

    // MARK: Pinch gesture

    private var pinchGesture: some Gesture {
        MagnificationGesture()
            .onChanged { value in
                if pinchBase == 0 { pinchBase = value }
                let delta = value / max(pinchBase, 0.01)
                if delta > 1.25, columnCount < 8 {
                    columnCount += 1
                    Haptics.tap()
                    pinchBase = value
                } else if delta < 0.8, columnCount > 2 {
                    columnCount -= 1
                    Haptics.tap()
                    pinchBase = value
                }
            }
            .onEnded { _ in pinchBase = 0 }
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

    // MARK: Pinning

    private var isPinnedAsHome: Bool {
        let s = dataManager.getOrCreateSettings()
        return s.pinnedViewId == folder.id && s.homeViewMode == "custom_view"
    }

    private func togglePinAsHome() {
        Haptics.success()
        let s = dataManager.getOrCreateSettings()
        if isPinnedAsHome {
            s.pinnedViewId = nil
            s.homeViewMode = "folder_list"
        } else {
            s.pinnedViewId = folder.id
            s.homeViewMode = "custom_view"
        }
        dataManager.saveSettings()
    }
}
