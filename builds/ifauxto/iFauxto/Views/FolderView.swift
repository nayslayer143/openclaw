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
    @State private var photoSortMode: String = "custom"

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

    private let columns = [GridItem(.adaptive(minimum: 110), spacing: 2)]

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
                                guard photoSortMode == "custom" else { return false }
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
                .padding(.bottom, 60)
            }
            .scrollIndicators(.hidden)

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
                Button { showingSubfolderCreation = true } label: {
                    Label("New Subfolder", systemImage: "folder.badge.plus")
                }
                Divider()
                Button {
                    isEditMode = true
                } label: {
                    Label("Select Photos", systemImage: "checkmark.circle")
                }
                Divider()
                Menu("Sort Photos") {
                    Button { photoSortMode = "custom" } label: {
                        Label("Manual Order", systemImage: photoSortMode == "custom" ? "checkmark" : "hand.point.up.left")
                    }
                    Button { photoSortMode = "alpha" } label: {
                        Label("By Name", systemImage: photoSortMode == "alpha" ? "checkmark" : "textformat")
                    }
                    Button { photoSortMode = "recent" } label: {
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
