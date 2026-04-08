import SwiftUI
import Photos

struct ChronologicalFeedView: View {
    @EnvironmentObject var photoKitService: PhotoKitService
    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var navCoordinator: NavCoordinator
    @Environment(\.searchService) var searchService

    @State private var assetIdentifiers: [String] = []
    @State private var allIdentifiers: [String] = []
    @State private var isLoading = true
    @State private var loadedCount = 0
    @State private var showingSettings = false
    @State private var showingSearch = false

    // Selection mode — pick photos from the feed and add them to an album.
    @State private var isSelectMode = false
    @State private var selectedIds: Set<String> = []
    @State private var showingAlbumPicker = false

    private let pageSize = 100
    private let columns = [
        GridItem(.flexible(), spacing: 3),
        GridItem(.flexible(), spacing: 3),
        GridItem(.flexible(), spacing: 3)
    ]

    var body: some View {
        NavigationStack(path: $navCoordinator.path) {
            ZStack(alignment: .top) {
                Theme.Palette.bg.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 0) {
                        BrandHeader(
                            title: "iFauxto",
                            subtitle: chronoSubtitle
                        ) {
                            HStack(spacing: 2) {
                                if isSelectMode {
                                    Button {
                                        Haptics.tap()
                                        isSelectMode = false
                                        selectedIds.removeAll()
                                    } label: {
                                        Text("Done")
                                            .font(.system(size: 17, weight: .semibold))
                                            .foregroundStyle(Theme.Palette.accent)
                                            .padding(.horizontal, 8)
                                    }
                                    .buttonStyle(.plain)
                                } else {
                                    GlassIconButton(systemName: "gearshape") {
                                        showingSettings = true
                                    }
                                    GlassIconButton(systemName: "checkmark.circle") {
                                        Haptics.tap()
                                        isSelectMode = true
                                    }
                                    GlassIconButton(systemName: "rectangle.stack.fill") {
                                        switchMode(to: "folder_list")
                                    }
                                }
                            }
                        }

                        if !isSelectMode {
                            HeroSearchField(placeholder: "Find anything. Instantly.") {
                                showingSearch = true
                            }
                            .padding(.bottom, 16)
                        } else {
                            Spacer().frame(height: 12)
                        }

                        if isLoading {
                            loadingState
                        } else if assetIdentifiers.isEmpty {
                            emptyState
                        } else {
                            grid
                        }
                    }
                    .padding(.bottom, isSelectMode ? 96 : 40)
                }
                .scrollIndicators(.hidden)

                // Bottom action bar in select mode
                if isSelectMode {
                    selectActionBar
                        .frame(maxHeight: .infinity, alignment: .bottom)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
            .animation(Theme.Motion.snappy, value: isSelectMode)
            .navigationBarHidden(true)
            .navigationDestination(for: PhotoViewerRoute.self) { route in
                PhotoViewer(photoIds: route.photoIds, startIndex: route.startIndex)
            }
            .navigationDestination(for: Folder.self) { folder in
                FolderView(folder: folder)
            }
            .sheet(isPresented: $showingSettings) {
                SettingsView()
            }
            .sheet(isPresented: $showingSearch) {
                if let service = searchService {
                    SearchView(searchService: service)
                }
            }
            .sheet(isPresented: $showingAlbumPicker) {
                AlbumPickerSheet { folder in
                    addSelectedToFolder(folder)
                }
            }
            .task {
                if DemoLibrary.isEnabled {
                    allIdentifiers = DemoLibrary.identifiers
                } else if ProcessInfo.processInfo.arguments.contains("-demoPhotos") {
                    allIdentifiers = (0..<48).map { "demo:\($0)" }
                } else {
                    allIdentifiers = photoKitService.fetchAllAssetIdentifiers()
                }
                loadNextPage()
                withAnimation(Theme.Motion.soft) {
                    isLoading = false
                }
                #if DEBUG
                if ProcessInfo.processInfo.arguments.contains("-autoOpenPhoto") {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                        navCoordinator.path.append(
                            PhotoViewerRoute(photoIds: assetIdentifiers, startIndex: 3)
                        )
                    }
                }
                #endif
            }
        }
    }

    private var chronoSubtitle: String {
        if isSelectMode {
            let n = selectedIds.count
            return n == 0 ? "Select photos to add to an album" : "\(n) selected"
        }
        if isLoading { return "Loading your library…" }
        if assetIdentifiers.isEmpty { return "No photos yet" }
        return "\(allIdentifiers.count) photos · newest first"
    }

    // MARK: - Grid

    private var grid: some View {
        LazyVGrid(columns: columns, spacing: 3) {
            ForEach(Array(assetIdentifiers.enumerated()), id: \.element) { index, identifier in
                Group {
                    if isSelectMode {
                        FeedThumbnailView(
                            identifier: identifier,
                            isSelected: selectedIds.contains(identifier),
                            isSelectMode: true
                        )
                        .onTapGesture {
                            Haptics.select()
                            if selectedIds.contains(identifier) {
                                selectedIds.remove(identifier)
                            } else {
                                selectedIds.insert(identifier)
                            }
                        }
                    } else {
                        NavigationLink(value: PhotoViewerRoute(
                            photoIds: assetIdentifiers,
                            startIndex: index
                        )) {
                            FeedThumbnailView(
                                identifier: identifier,
                                isSelected: false,
                                isSelectMode: false
                            )
                        }
                        .buttonStyle(PressableButtonStyle(scale: 0.97))
                        .simultaneousGesture(TapGesture().onEnded { Haptics.tap() })
                    }
                }
            }
            if loadedCount < allIdentifiers.count {
                Color.clear
                    .frame(height: 1)
                    .onAppear { loadNextPage() }
            }
        }
        .padding(.horizontal, 12)
        .padding(.top, 4)
    }

    // MARK: - Select action bar

    private var selectActionBar: some View {
        VStack(spacing: 0) {
            Rectangle().fill(Theme.Palette.divider).frame(height: 0.5)

            HStack(spacing: 12) {
                Button {
                    Haptics.tap()
                    if selectedIds.count == assetIdentifiers.count {
                        selectedIds.removeAll()
                    } else {
                        selectedIds = Set(assetIdentifiers)
                    }
                } label: {
                    Text(selectedIds.count == assetIdentifiers.count ? "Deselect All" : "Select All")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(Theme.Palette.accent)
                }
                .buttonStyle(.plain)

                Spacer()

                Button {
                    Haptics.medium()
                    showingAlbumPicker = true
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "folder.badge.plus")
                        Text("Add to Album")
                    }
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(
                        Capsule().fill(
                            selectedIds.isEmpty ? Theme.Palette.textDim : Theme.Palette.accent
                        )
                    )
                }
                .buttonStyle(.plain)
                .disabled(selectedIds.isEmpty)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(.ultraThinMaterial)
        }
    }

    // MARK: - Loading + empty states

    private var loadingState: some View {
        VStack(spacing: 18) {
            Spacer(minLength: 80)
            ProgressView()
                .controlSize(.large)
                .tint(Theme.Palette.accent)
            Text("Warming up your library")
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(Theme.Palette.textMuted)
            Spacer()
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 40)
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Spacer(minLength: 60)
            Image(systemName: "photo.stack")
                .font(.system(size: 56, weight: .light))
                .foregroundStyle(Theme.Palette.accent)
                .symbolRenderingMode(.hierarchical)
            Text("Your library is empty")
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            Text("Add photos in the Photos app and they'll appear here.")
                .font(.system(size: 14))
                .foregroundStyle(Theme.Palette.textMuted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Helpers

    private func switchMode(to mode: String) {
        Haptics.select()
        let settings = dataManager.getOrCreateSettings()
        settings.homeViewMode = mode
        dataManager.saveSettings()
    }

    private func loadNextPage() {
        let nextBatch = Array(allIdentifiers.dropFirst(loadedCount).prefix(pageSize))
        assetIdentifiers.append(contentsOf: nextBatch)
        loadedCount = assetIdentifiers.count
    }

    private func addSelectedToFolder(_ folder: Folder) {
        let ids = Array(selectedIds)
        dataManager.addPhotos(assetIdentifiers: ids, to: folder)
        Haptics.success()
        selectedIds.removeAll()
        isSelectMode = false
        showingAlbumPicker = false
    }
}

// MARK: - FeedThumbnailView

private struct FeedThumbnailView: View {
    let identifier: String
    let isSelected: Bool
    let isSelectMode: Bool
    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var thumbnail: UIImage?

    private var isDemo: Bool { identifier.hasPrefix("demo:") }

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .topTrailing) {
                Group {
                    if isDemo {
                        ZStack {
                            LinearGradient(
                                colors: [
                                    DemoPalette.color(for: identifier),
                                    DemoPalette.color(for: identifier).opacity(0.65)
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                            Image(systemName: DemoPalette.icon(for: identifier))
                                .font(.system(size: 22, weight: .light))
                                .foregroundStyle(.white.opacity(0.85))
                            Text(DemoPalette.label(for: identifier))
                                .font(.system(size: 9, weight: .semibold))
                                .foregroundStyle(.white.opacity(0.95))
                                .padding(.horizontal, 5)
                                .padding(.vertical, 2)
                                .background(Capsule().fill(.black.opacity(0.25)))
                                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
                                .padding(4)
                        }
                        .frame(width: geo.size.width, height: geo.size.width)
                    } else if let img = thumbnail {
                        Image(uiImage: img)
                            .resizable()
                            .scaledToFill()
                            .frame(width: geo.size.width, height: geo.size.width)
                            .clipped()
                    } else {
                        Rectangle()
                            .fill(Color(red: 0.918, green: 0.918, blue: 0.937))
                            .overlay(
                                ProgressView()
                                    .controlSize(.small)
                                    .tint(Theme.Palette.textDim)
                            )
                            .frame(width: geo.size.width, height: geo.size.width)
                    }
                }
                .overlay(isSelected ? Color.black.opacity(0.28) : Color.clear)
                .overlay(
                    Rectangle()
                        .strokeBorder(
                            isSelected ? Theme.Palette.accent : Color.clear,
                            lineWidth: 3
                        )
                )

                if isSelectMode {
                    ZStack {
                        Circle()
                            .fill(isSelected ? Theme.Palette.accent : Color.black.opacity(0.35))
                            .frame(width: 22, height: 22)
                        Circle()
                            .strokeBorder(Color.white, lineWidth: 1.5)
                            .frame(width: 22, height: 22)
                        if isSelected {
                            Image(systemName: "checkmark")
                                .font(.system(size: 11, weight: .bold))
                                .foregroundStyle(.white)
                        }
                    }
                    .padding(6)
                }
            }
        }
        .aspectRatio(1, contentMode: .fit)
        .task(id: identifier) {
            guard !isDemo else { return }
            thumbnail = await photoKitService.loadThumbnail(
                for: identifier,
                targetSize: CGSize(width: 300, height: 300)
            )
        }
    }
}

// MARK: - AlbumPickerSheet

/// Reusable picker that lists every root album so the user can drop
/// selected photos into one. Same look as FolderPickerSheet but doesn't
/// exclude any folder (since it's not a "move").
private struct AlbumPickerSheet: View {
    let onPick: (Folder) -> Void

    @EnvironmentObject var dataManager: DataManager
    @Environment(\.dismiss) private var dismiss
    @State private var folders: [Folder] = []
    @State private var showingCreate = false

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                topBar
                if folders.isEmpty {
                    empty
                } else {
                    list
                }
            }
        }
        .sheet(isPresented: $showingCreate, onDismiss: { folders = dataManager.fetchFolders(parentId: nil) }) {
            FolderCreationSheet(parentId: nil)
        }
        .onAppear { folders = dataManager.fetchFolders(parentId: nil) }
    }

    private var topBar: some View {
        ZStack {
            Text("Add to Album")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            HStack {
                Button {
                    Haptics.tap()
                    dismiss()
                } label: {
                    Text("Cancel")
                        .font(.system(size: 17))
                        .foregroundStyle(Theme.Palette.accent)
                }
                .buttonStyle(.plain)
                Spacer()
                Button {
                    Haptics.tap()
                    showingCreate = true
                } label: {
                    Image(systemName: "plus")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(Theme.Palette.accent)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
        }
        .frame(height: 44)
        .padding(.top, 8)
        .padding(.bottom, 6)
        .background(Theme.Palette.bg)
        .overlay(
            Rectangle().fill(Theme.Palette.divider).frame(height: 0.5),
            alignment: .bottom
        )
    }

    private var list: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                Text("YOUR ALBUMS")
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.Palette.textMuted)
                    .tracking(0.4)
                    .padding(.horizontal, 32)
                    .padding(.top, 12)

                VStack(spacing: 0) {
                    ForEach(Array(folders.enumerated()), id: \.element.id) { index, folder in
                        Button {
                            Haptics.success()
                            onPick(folder)
                            dismiss()
                        } label: {
                            HStack(spacing: 14) {
                                Image(systemName: "folder.fill")
                                    .font(.system(size: 28))
                                    .foregroundStyle(Theme.Palette.folder)
                                    .frame(width: 38, height: 38)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(folder.name)
                                        .font(.system(size: 17))
                                        .foregroundStyle(Theme.Palette.text)
                                    Text("\((folder.photoReferences ?? []).count) photos")
                                        .font(.system(size: 13))
                                        .foregroundStyle(Theme.Palette.textMuted)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.system(size: 13, weight: .semibold))
                                    .foregroundStyle(Theme.Palette.textDim)
                            }
                            .padding(.horizontal, 16)
                            .padding(.vertical, 10)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(PressableButtonStyle(scale: 0.985))
                        if index < folders.count - 1 {
                            Rectangle()
                                .fill(Theme.Palette.divider)
                                .frame(height: 0.5)
                                .padding(.leading, 64)
                        }
                    }
                }
                .background(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(Theme.Palette.bgElevated)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
                )
                .padding(.horizontal, 16)
            }
            .padding(.bottom, 40)
        }
    }

    private var empty: some View {
        VStack(spacing: 14) {
            Spacer(minLength: 60)
            Image(systemName: "folder.badge.plus")
                .font(.system(size: 56, weight: .light))
                .foregroundStyle(Theme.Palette.folder)
                .symbolRenderingMode(.hierarchical)
            Text("No Albums Yet")
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            Text("Tap + to create one.")
                .font(.system(size: 14))
                .foregroundStyle(Theme.Palette.textMuted)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }
}
