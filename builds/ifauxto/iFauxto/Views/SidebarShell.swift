import SwiftUI

/// Three-column iPad / Mac layout: sidebar (smart albums + folders),
/// content (selected source), detail (push-stack inside the content).
/// On compact width (iPhone) this collapses to the existing HomeView.
struct SidebarShell: View {
    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var navCoordinator: NavCoordinator
    @Environment(\.horizontalSizeClass) private var sizeClass

    @AppStorage("iFauxto.sidebarSelection") private var persistedSelection: String = "folders"
    @State private var selection: SidebarItem? = .folders
    @State private var folders: [Folder] = []
    @State private var smartAlbums: [SmartAlbum] = []

    enum SidebarItem: Hashable {
        case folders
        case feed
        case events
        case places
        case faces
        case favorites
        case hidden
        case trash
        case folder(String)
        case smartAlbum(String)
    }

    var body: some View {
        if sizeClass == .compact {
            // iPhone: existing single-stack layout.
            HomeView()
        } else {
            // iPad / Mac: three-column split.
            NavigationSplitView {
                sidebar
            } detail: {
                NavigationStack(path: $navCoordinator.path) {
                    detailContent
                        .navigationDestination(for: Folder.self) { f in FolderView(folder: f) }
                        .navigationDestination(for: PhotoViewerRoute.self) { r in
                            PhotoViewer(photoIds: r.photoIds, startIndex: r.startIndex)
                        }
                        .navigationDestination(for: SmartAlbumRoute.self) { r in
                            switch r {
                            case .events:   EventsView()
                            case .places:   PlacesView()
                            case .faces:    FacesView()
                            case .projects: ProjectsView()
                            case .smartList(let id, let title):
                                SmartListView(id: id, title: title)
                            }
                        }
                }
            }
            .onAppear {
                reload()
                selection = decodeSelection(persistedSelection)
            }
            .onChange(of: selection) { _, newValue in
                if let newValue {
                    persistedSelection = encodeSelection(newValue)
                }
            }
        }
    }

    private func encodeSelection(_ item: SidebarItem) -> String {
        switch item {
        case .folders:   return "folders"
        case .feed:      return "feed"
        case .events:    return "events"
        case .places:    return "places"
        case .faces:     return "faces"
        case .favorites: return "favorites"
        case .hidden:    return "hidden"
        case .trash:     return "trash"
        case .folder(let id):      return "folder:\(id)"
        case .smartAlbum(let id):  return "smart:\(id)"
        }
    }

    private func decodeSelection(_ raw: String) -> SidebarItem {
        switch raw {
        case "folders":   return .folders
        case "feed":      return .feed
        case "events":    return .events
        case "places":    return .places
        case "faces":     return .faces
        case "favorites": return .favorites
        case "hidden":    return .hidden
        case "trash":     return .trash
        default:
            if raw.hasPrefix("folder:") {
                return .folder(String(raw.dropFirst("folder:".count)))
            }
            if raw.hasPrefix("smart:") {
                return .smartAlbum(String(raw.dropFirst("smart:".count)))
            }
            return .folders
        }
    }

    @ViewBuilder
    private var detailContent: some View {
        switch selection ?? .folders {
        case .folders:  HomeView()
        case .feed:     ChronologicalFeedView()
        case .events:   EventsView()
        case .places:   PlacesView()
        case .faces:    FacesView()
        case .favorites:
            SmartListView(id: "__favorites", title: "Favorites")
        case .hidden:
            SmartListView(id: "__hidden", title: "Hidden")
        case .trash:
            SmartListView(id: "__trash", title: "Recently Deleted")
        case .folder(let id):
            if let folder = folders.first(where: { $0.id == id }) {
                FolderView(folder: folder)
            } else {
                Text("Album not found").foregroundStyle(.secondary)
            }
        case .smartAlbum(let id):
            if let album = smartAlbums.first(where: { $0.id == id }) {
                SmartListView(id: album.id, title: album.name)
            } else {
                Text("Smart album not found").foregroundStyle(.secondary)
            }
        }
    }

    private var sidebar: some View {
        List(selection: $selection) {
            Section("Library") {
                Label("Folders", systemImage: "folder.fill")
                    .tag(SidebarItem.folders)
                Label("Photos", systemImage: "photo.on.rectangle")
                    .tag(SidebarItem.feed)
                Label("Events", systemImage: "calendar")
                    .tag(SidebarItem.events)
                Label("Places", systemImage: "mappin.and.ellipse")
                    .tag(SidebarItem.places)
                Label("Faces", systemImage: "person.crop.square")
                    .tag(SidebarItem.faces)
            }

            Section("Smart Albums") {
                Label("Favorites", systemImage: "heart.fill")
                    .tag(SidebarItem.favorites)
                Label("Hidden", systemImage: "eye.slash.fill")
                    .tag(SidebarItem.hidden)
                Label("Recently Deleted", systemImage: "trash.fill")
                    .tag(SidebarItem.trash)
                ForEach(smartAlbums) { album in
                    Label(album.name, systemImage: "rectangle.dashed")
                        .tag(SidebarItem.smartAlbum(album.id))
                }
            }

            Section("Albums") {
                ForEach(folders) { folder in
                    Label(folder.name, systemImage: "folder.fill")
                        .tag(SidebarItem.folder(folder.id))
                }
            }
        }
        .navigationTitle("iFauxto")
    }

    private func reload() {
        folders = dataManager.fetchFolders(parentId: nil)
        smartAlbums = dataManager.fetchSmartAlbums()
    }
}
