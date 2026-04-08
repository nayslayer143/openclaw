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
            .environment(\.editMode, $editMode)
            .sheet(isPresented: $showingCreateFolder, onDismiss: loadFolders) {
                FolderCreationSheet(parentId: nil)
            }
            .sheet(isPresented: $showingSettings) {
                SettingsView()
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
            VStack(alignment: .leading, spacing: 6) {
                Text("ALBUMS")
                    .font(.system(size: 12, weight: .regular))
                    .foregroundStyle(Theme.Palette.textMuted)
                    .tracking(0.4)
                    .padding(.horizontal, 32)
                    .padding(.top, 4)

                VStack(spacing: 0) {
                    ForEach(Array(displayFolders.enumerated()), id: \.element.id) { index, folder in
                        NavigationLink(value: folder) {
                            FolderRow(folder: folder)
                        }
                        .buttonStyle(PressableButtonStyle(scale: 0.985))
                        .simultaneousGesture(TapGesture().onEnded { Haptics.tap() })
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
