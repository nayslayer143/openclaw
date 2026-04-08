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
    @State private var folderSortMode: String = "custom"
    @State private var editMode: EditMode = .inactive
    @Environment(\.searchService) var searchService

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
                ambientGlow

                VStack(spacing: 0) {
                    BrandHeader(
                        title: "iFauxto",
                        subtitle: "Your photos. Your order."
                    ) {
                        HStack(spacing: 10) {
                            GlassIconButton(systemName: "gearshape.fill") {
                                showingSettings = true
                            }
                            sortMenu
                            GlassIconButton(systemName: "plus") {
                                showingCreateFolder = true
                            }
                        }
                    }

                    HeroSearchField(placeholder: "Find anything. Instantly.") {
                        showingSearch = true
                    }
                    .padding(.top, 4)
                    .padding(.bottom, 18)

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
            }
        }
    }

    // MARK: - Ambient glow

    private var ambientGlow: some View {
        GeometryReader { geo in
            Circle()
                .fill(
                    RadialGradient(
                        colors: [Theme.Palette.accent.opacity(0.22), .clear],
                        center: .center,
                        startRadius: 0,
                        endRadius: 280
                    )
                )
                .frame(width: 520, height: 520)
                .position(x: geo.size.width * 0.85, y: 80)
                .blur(radius: 40)
                .allowsHitTesting(false)
        }
    }

    // MARK: - Sort menu

    private var sortMenu: some View {
        Menu {
            Button { folderSortMode = "custom" } label: {
                Label("Manual Order", systemImage: folderSortMode == "custom" ? "checkmark" : "hand.point.up.left")
            }
            Button { folderSortMode = "alpha" } label: {
                Label("Alphabetical", systemImage: folderSortMode == "alpha" ? "checkmark" : "textformat")
            }
            Button { folderSortMode = "date" } label: {
                Label("Date Created", systemImage: folderSortMode == "date" ? "checkmark" : "calendar")
            }
            Button { folderSortMode = "recent" } label: {
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
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
                .frame(width: 38, height: 38)
                .background(Circle().fill(.ultraThinMaterial))
                .overlay(Circle().strokeBorder(Theme.Palette.stroke, lineWidth: 1))
        }
    }

    // MARK: - Folder list

    private var folderList: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                ForEach(Array(displayFolders.enumerated()), id: \.element.id) { index, folder in
                    NavigationLink(value: folder) {
                        FolderCard(folder: folder, accentIndex: index)
                    }
                    .buttonStyle(.plain)
                    .simultaneousGesture(TapGesture().onEnded { Haptics.tap() })
                    .transition(.asymmetric(
                        insertion: .scale(scale: 0.9).combined(with: .opacity),
                        removal: .opacity
                    ))
                }
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 40)
            .animation(Theme.Motion.soft, value: folders.count)
        }
    }

    // MARK: - Empty state

    private var emptyState: some View {
        VStack(spacing: 22) {
            Spacer(minLength: 40)

            ZStack {
                Circle()
                    .fill(Theme.Palette.accent.opacity(0.12))
                    .frame(width: 140, height: 140)
                    .blur(radius: 20)
                Image(systemName: "folder.badge.plus")
                    .font(.system(size: 54, weight: .light))
                    .foregroundStyle(Theme.Palette.accent)
                    .symbolRenderingMode(.hierarchical)
            }

            VStack(spacing: 8) {
                Text("A clean slate")
                    .font(Theme.Font.display(28))
                    .foregroundStyle(Theme.Palette.text)
                Text("Import your albums, or start a folder.\nNothing auto-shuffles. Ever.")
                    .font(Theme.Font.body(15))
                    .foregroundStyle(Theme.Palette.textMuted)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            }

            VStack(spacing: 10) {
                Button {
                    Haptics.medium()
                    showingImport = true
                } label: {
                    HStack {
                        Image(systemName: "square.and.arrow.down.on.square.fill")
                        Text("Import from Photos")
                    }
                    .font(Theme.Font.body(16, weight: .bold))
                    .foregroundStyle(Color.black)
                    .frame(maxWidth: 280)
                    .padding(.vertical, 14)
                    .background(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .fill(Theme.Palette.accent)
                    )
                    .shadow(color: Theme.Palette.accentGlow, radius: 18, x: 0, y: 8)
                }

                Button {
                    Haptics.tap()
                    showingCreateFolder = true
                } label: {
                    HStack {
                        Image(systemName: "folder.badge.plus")
                        Text("Create Folder")
                    }
                    .font(Theme.Font.body(16, weight: .semibold))
                    .foregroundStyle(Theme.Palette.text)
                    .frame(maxWidth: 280)
                    .padding(.vertical, 14)
                    .background(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .fill(.ultraThinMaterial)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .strokeBorder(Theme.Palette.stroke, lineWidth: 1)
                    )
                }
            }
            .padding(.top, 4)

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

    #if DEBUG
    private func seedDemoFoldersIfEmpty() {
        let existing = dataManager.fetchFolders(parentId: nil)
        guard existing.isEmpty else { return }
        let names = ["Travel", "Family", "Screenshots", "Food", "Everything Else"]
        for name in names {
            dataManager.createFolder(name: name)
        }
    }
    #endif
}

// MARK: - FolderCard

private struct FolderCard: View {
    let folder: Folder
    let accentIndex: Int
    @State private var isPressed = false

    private var photoCount: Int {
        (folder.photoReferences ?? []).count
    }

    private var accent: Color {
        let colors: [Color] = [
            Theme.Palette.accent,
            Color(red: 0.43, green: 0.78, blue: 0.98),
            Color(red: 0.62, green: 0.42, blue: 0.94),
            Color(red: 0.98, green: 0.75, blue: 0.31),
            Color(red: 0.40, green: 0.84, blue: 0.55)
        ]
        return colors[accentIndex % colors.count]
    }

    var body: some View {
        HStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(accent.opacity(0.18))
                    .frame(width: 56, height: 56)
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(accent.opacity(0.45), lineWidth: 1)
                    .frame(width: 56, height: 56)
                Image(systemName: "folder.fill")
                    .font(.system(size: 22, weight: .regular))
                    .foregroundStyle(accent)
            }

            VStack(alignment: .leading, spacing: 3) {
                Text(folder.name)
                    .font(Theme.Font.title(17, weight: .semibold))
                    .foregroundStyle(Theme.Palette.text)
                    .lineLimit(1)
                Text("\(photoCount) \(photoCount == 1 ? "photo" : "photos")")
                    .font(Theme.Font.body(12, weight: .medium))
                    .foregroundStyle(Theme.Palette.textMuted)
            }

            Spacer()

            Image(systemName: "chevron.right")
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(Theme.Palette.textDim)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(
            RoundedRectangle(cornerRadius: Theme.Radius.l, style: .continuous)
                .fill(.ultraThinMaterial)
        )
        .overlay(
            RoundedRectangle(cornerRadius: Theme.Radius.l, style: .continuous)
                .strokeBorder(Theme.Palette.stroke, lineWidth: 1)
        )
        .scaleEffect(isPressed ? 0.97 : 1)
        .animation(Theme.Motion.instant, value: isPressed)
        .onLongPressGesture(minimumDuration: 0, maximumDistance: .infinity,
                            pressing: { pressing in isPressed = pressing },
                            perform: {})
    }
}
