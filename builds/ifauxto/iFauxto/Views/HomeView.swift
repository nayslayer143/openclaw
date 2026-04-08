import SwiftUI

struct HomeView: View {
    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var importService: LibraryImportService
    @EnvironmentObject var navCoordinator: NavCoordinator

    @State private var folders: [Folder] = []
    @State private var showingCreateFolder = false
    @State private var showingImport = false
    @State private var showingSettings = false
    @State private var showingSearch = false
    @State private var showingCreateSmartAlbum = false
    @State private var editMode: EditMode = .inactive
    @State private var listAppeared = false
    @Environment(\.searchService) var searchService

    /// Sort mode is stored on AppSettings so it survives launches.
    private var folderSortMode: String {
        dataManager.getOrCreateSettings().rootFolderSortMode
    }

    private func setFolderSortMode(_ mode: String) {
        Haptics.select()
        let s = dataManager.getOrCreateSettings()
        s.rootFolderSortMode = mode
        dataManager.saveSettings()
        loadFolders()
    }

    private var displayFolders: [Folder] {
        switch folderSortMode {
        case "alpha":
            return folders.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
        case "date":
            return folders.sorted { $0.createdAt < $1.createdAt }
        case "recent":
            return folders.sorted { $0.createdAt > $1.createdAt }
        default:
            return folders
        }
    }

    var body: some View {
        NavigationStack(path: $navCoordinator.path) {
            ZStack {
                Theme.Palette.bg.ignoresSafeArea()

                VStack(spacing: 0) {
                    BrandHeader(
                        title: "iFauxto",
                        subtitle: "Your photos. Your order."
                    ) {
                        HStack(spacing: 2) {
                            GlassIconButton(systemName: "gearshape") {
                                showingSettings = true
                            }
                            GlassIconButton(systemName: "square.grid.2x2") {
                                switchToFeed()
                            }
                            sortMenu
                            GlassIconButton(systemName: "plus") {
                                showingCreateFolder = true
                            }
                        }
                    }

                    HeroSearchField(placeholder: "Search photos") {
                        showingSearch = true
                    }

                    if folders.isEmpty {
                        emptyState
                    } else {
                        folderList
                    }
                }
            }
            .navigationBarHidden(true)
            .navigationDestination(for: Folder.self) { folder in
                FolderView(folder: folder)
            }
            .navigationDestination(for: PhotoViewerRoute.self) { route in
                PhotoViewer(photoIds: route.photoIds, startIndex: route.startIndex)
            }
            .navigationDestination(for: SmartAlbumRoute.self) { route in
                switch route {
                case .events:   EventsView()
                case .places:   PlacesView()
                case .faces:    FacesView()
                case .projects: ProjectsView()
                case .smartList(let id, let title):
                    SmartListView(id: id, title: title)
                }
            }
            .environment(\.editMode, $editMode)
            .sheet(isPresented: $showingCreateFolder, onDismiss: loadFolders) {
                FolderCreationSheet(parentId: nil)
            }
            .sheet(isPresented: $showingSettings) {
                SettingsView()
            }
            .sheet(isPresented: $showingCreateSmartAlbum, onDismiss: { loadFolders() }) {
                CreateSmartAlbumSheet()
            }
            .sheet(isPresented: $showingSearch) {
                if let service = searchService {
                    SearchView(searchService: service)
                }
            }
            .sheet(isPresented: $showingImport, onDismiss: loadFolders) {
                ImportProgressView(importService: importService) {
                    showingImport = false
                    loadFolders()
                }
            }
            .onAppear {
                #if DEBUG
                seedDemoFoldersIfEmpty()
                #endif
                loadFolders()
                listAppeared = false
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                    listAppeared = true
                }
                #if DEBUG
                autoNavigateForScreenshot()
                #endif
            }
        }
    }

    // MARK: - Sort menu

    private var sortMenu: some View {
        Menu {
            Button { setFolderSortMode("custom") } label: {
                Label("Manual Order", systemImage: folderSortMode == "custom" ? "checkmark" : "hand.point.up.left")
            }
            Button { setFolderSortMode("alpha") } label: {
                Label("Alphabetical", systemImage: folderSortMode == "alpha" ? "checkmark" : "textformat")
            }
            Button { setFolderSortMode("date") } label: {
                Label("Date Created", systemImage: folderSortMode == "date" ? "checkmark" : "calendar")
            }
            Button { setFolderSortMode("recent") } label: {
                Label("Most Recent", systemImage: folderSortMode == "recent" ? "checkmark" : "clock")
            }
            Divider()
            Button {
                withAnimation(Theme.Motion.snappy) {
                    editMode = editMode == .active ? .inactive : .active
                }
            } label: {
                Label(editMode == .active ? "Done Editing" : "Reorder", systemImage: "arrow.up.arrow.down")
            }
            Divider()
            Button {
                showingImport = true
            } label: {
                Label(importService.hasImportedLibrary ? "Re-import Library" : "Import Library",
                      systemImage: "square.and.arrow.down.on.square")
            }
        } label: {
            Image(systemName: "arrow.up.arrow.down")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Theme.Palette.accent)
                .frame(width: 34, height: 34)
                .contentShape(Rectangle())
        }
        .simultaneousGesture(TapGesture().onEnded { Haptics.tap() })
    }

    // MARK: - Folder list

    private var folderList: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                smartAlbums

                Text("ALBUMS")
                    .font(.system(size: 12, weight: .regular))
                    .foregroundStyle(Theme.Palette.textMuted)
                    .tracking(0.4)
                    .padding(.horizontal, 32)

                VStack(spacing: 0) {
                    ForEach(Array(displayFolders.enumerated()), id: \.element.id) { index, folder in
                        NavigationLink(value: folder) {
                            FolderRow(folder: folder)
                        }
                        .buttonStyle(PressableButtonStyle(scale: 0.985))
                        .simultaneousGesture(TapGesture().onEnded { Haptics.tap() })
                        .dropDestination(for: URL.self) { urls, _ in
                            let ids = FilesImportService.importFiles(urls)
                            guard !ids.isEmpty else { return false }
                            dataManager.addPhotos(assetIdentifiers: ids, to: folder)
                            Haptics.success()
                            loadFolders()
                            return true
                        }
                        .opacity(listAppeared ? 1 : 0)
                        .offset(y: listAppeared ? 0 : 12)
                        .animation(
                            .spring(response: 0.45, dampingFraction: 0.85)
                                .delay(0.04 * Double(index)),
                            value: listAppeared
                        )
                        if index < displayFolders.count - 1 {
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
            .animation(Theme.Motion.soft, value: folders.count)
        }
    }

    // MARK: - Empty state

    private var emptyState: some View {
        VStack(spacing: 18) {
            Spacer(minLength: 40)

            Image(systemName: "folder.badge.plus")
                .font(.system(size: 64, weight: .light))
                .foregroundStyle(Theme.Palette.folder)
                .symbolRenderingMode(.hierarchical)

            VStack(spacing: 6) {
                Text("No Albums Yet")
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundStyle(Theme.Palette.text)
                Text("Import your photo library or create an album to get started.")
                    .font(.system(size: 15))
                    .foregroundStyle(Theme.Palette.textMuted)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
            }

            VStack(spacing: 12) {
                Button {
                    Haptics.medium()
                    showingImport = true
                } label: {
                    Text("Import from Photos")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(.white)
                        .frame(maxWidth: 260)
                        .padding(.vertical, 13)
                        .background(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .fill(Theme.Palette.accent)
                        )
                }
                .buttonStyle(.plain)

                Button {
                    Haptics.tap()
                    showingCreateFolder = true
                } label: {
                    Text("Create Album")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(Theme.Palette.accent)
                }
                .buttonStyle(.plain)
            }
            .padding(.top, 6)

            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Helpers

    private func loadFolders() {
        withAnimation(Theme.Motion.soft) {
            folders = dataManager.fetchFolders(parentId: nil)
        }
    }

    // MARK: - Smart albums

    private var smartAlbums: some View {
        let favorites = dataManager.favoriteAssetIds()
        let hidden = dataManager.hiddenAssetIds()
        let trashed = dataManager.trashedAssetIds()
        return VStack(alignment: .leading, spacing: 6) {
            Text("SMART ALBUMS")
                .font(.system(size: 12))
                .foregroundStyle(Theme.Palette.textMuted)
                .tracking(0.4)
                .padding(.horizontal, 32)
                .padding(.top, 4)

            VStack(spacing: 0) {
                smartAlbumNavRow(
                    title: "Events",
                    icon: "calendar",
                    tint: Color(red: 0.95, green: 0.55, blue: 0.10),
                    route: .events
                )
                divider
                smartAlbumNavRow(
                    title: "Places",
                    icon: "mappin.and.ellipse",
                    tint: Color(red: 0.20, green: 0.55, blue: 0.95),
                    route: .places
                )
                divider
                smartAlbumNavRow(
                    title: "Faces",
                    icon: "person.crop.square",
                    tint: Color(red: 0.55, green: 0.40, blue: 0.95),
                    route: .faces
                )
                divider
                smartAlbumNavRow(
                    title: "Projects",
                    icon: "square.grid.3x3.square",
                    tint: Color(red: 0.30, green: 0.70, blue: 0.55),
                    route: .projects
                )
                divider
                smartAlbumRow(
                    title: "Favorites",
                    icon: "heart.fill",
                    tint: Color(red: 1.0, green: 0.30, blue: 0.30),
                    ids: favorites
                )
                divider
                smartAlbumRow(
                    title: "Hidden",
                    icon: "eye.slash.fill",
                    tint: Color(red: 0.5, green: 0.5, blue: 0.55),
                    ids: hidden
                )
                divider
                smartAlbumRow(
                    title: "Recently Deleted",
                    icon: "trash.fill",
                    tint: Color(red: 0.95, green: 0.55, blue: 0.10),
                    ids: trashed,
                    subtitle: trashed.isEmpty ? nil : "Auto-purged after 30 days"
                )

                let savedSmartAlbums = dataManager.fetchSmartAlbums()
                if !savedSmartAlbums.isEmpty {
                    divider
                    ForEach(savedSmartAlbums) { album in
                        smartAlbumNavRow(
                            title: album.name,
                            icon: "rectangle.dashed",
                            tint: Color(red: 0.40, green: 0.65, blue: 0.40),
                            route: .smartList(id: album.id, title: album.name)
                        )
                        if album.id != savedSmartAlbums.last?.id {
                            divider
                        }
                    }
                }

                divider
                Button {
                    Haptics.tap()
                    showingCreateSmartAlbum = true
                } label: {
                    HStack(spacing: 14) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 9, style: .continuous)
                                .fill(Theme.Palette.accent.opacity(0.15))
                                .frame(width: 38, height: 38)
                            Image(systemName: "plus")
                                .font(.system(size: 18, weight: .semibold))
                                .foregroundStyle(Theme.Palette.accent)
                        }
                        Text("New Smart Album")
                            .font(.system(size: 17))
                            .foregroundStyle(Theme.Palette.accent)
                        Spacer()
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
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
    }

    private var divider: some View {
        Rectangle()
            .fill(Theme.Palette.divider)
            .frame(height: 0.5)
            .padding(.leading, 64)
    }

    /// Row that pushes a SmartAlbumRoute (Events, Places, Faces, etc).
    private func smartAlbumNavRow(
        title: String,
        icon: String,
        tint: Color,
        route: SmartAlbumRoute
    ) -> some View {
        NavigationLink(value: route) {
            HStack(spacing: 14) {
                ZStack {
                    RoundedRectangle(cornerRadius: 9, style: .continuous)
                        .fill(tint.opacity(0.15))
                        .frame(width: 38, height: 38)
                    Image(systemName: icon)
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(tint)
                }
                Text(title)
                    .font(.system(size: 17))
                    .foregroundStyle(Theme.Palette.text)
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
        .simultaneousGesture(TapGesture().onEnded { Haptics.tap() })
    }

    private func smartAlbumRow(
        title: String,
        icon: String,
        tint: Color,
        ids: [String],
        subtitle: String? = nil
    ) -> some View {
        let isEmpty = ids.isEmpty
        return NavigationLink(value: PhotoViewerRoute(photoIds: ids, startIndex: 0)) {
            HStack(spacing: 14) {
                ZStack {
                    RoundedRectangle(cornerRadius: 9, style: .continuous)
                        .fill(tint.opacity(0.15))
                        .frame(width: 38, height: 38)
                    Image(systemName: icon)
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(tint)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text(title)
                        .font(.system(size: 17))
                        .foregroundStyle(Theme.Palette.text)
                    Text(subtitle ?? "\(ids.count) \(ids.count == 1 ? "photo" : "photos")")
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
        .simultaneousGesture(TapGesture().onEnded { Haptics.tap() })
        .disabled(isEmpty)
        .opacity(isEmpty ? 0.55 : 1)
    }

    private func switchToFeed() {
        Haptics.select()
        let s = dataManager.getOrCreateSettings()
        s.homeViewMode = "chronological_feed"
        dataManager.saveSettings()
    }

    #if DEBUG
    private func seedDemoFoldersIfEmpty() {
        let existing = dataManager.fetchFolders(parentId: nil)
        guard existing.isEmpty else { return }
        let names = ["Travel", "Family", "Screenshots", "Food", "Everything Else"]
        for name in names {
            dataManager.createFolder(name: name)
        }
    }

    /// Allows screenshots of nested screens by passing launch args.
    /// Examples:
    ///   `... -autoPushFolder Travel`
    ///   `... -autoShowSettings`
    private func autoNavigateForScreenshot() {
        let args = ProcessInfo.processInfo.arguments
        if let idx = args.firstIndex(of: "-autoPushFolder"), idx + 1 < args.count {
            let target = args[idx + 1]
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                if let folder = folders.first(where: { $0.name == target }) {
                    navCoordinator.path.append(folder)
                }
            }
        }
        if args.contains("-autoShowSettings") {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                showingSettings = true
            }
        }
        if args.contains("-autoShowSearch") {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                showingSearch = true
            }
        }
        if args.contains("-autoShowCreate") {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                showingCreateFolder = true
            }
        }
        if args.contains("-autoShowImport") {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                showingImport = true
            }
        }
        if let idx = args.firstIndex(of: "-openSmart"), idx + 1 < args.count {
            let target = args[idx + 1]
            let route: SmartAlbumRoute? = {
                switch target {
                case "events":   return .events
                case "places":   return .places
                case "faces":    return .faces
                case "projects": return .projects
                default: return nil
                }
            }()
            if let route {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                    navCoordinator.path.append(route)
                }
            }
        }
    }
    #endif
}

// MARK: - FolderRow

/// Single grouped-list row. Yellow Apple folder icon, name, count, chevron.
private struct FolderRow: View {
    let folder: Folder

    private var photoCount: Int {
        (folder.photoReferences ?? []).count
    }

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: "folder.fill")
                .font(.system(size: 30, weight: .regular))
                .foregroundStyle(Theme.Palette.folder)
                .shadow(color: Theme.Palette.folderEdge.opacity(0.5), radius: 0.5, x: 0, y: 0.5)
                .frame(width: 38, height: 38)

            VStack(alignment: .leading, spacing: 1) {
                Text(folder.name)
                    .font(.system(size: 17))
                    .foregroundStyle(Theme.Palette.text)
                    .lineLimit(1)
                Text("\(photoCount) \(photoCount == 1 ? "photo" : "photos")")
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
        .pressScale(0.985)
    }
}
