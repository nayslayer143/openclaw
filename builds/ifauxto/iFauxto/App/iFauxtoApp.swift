import SwiftUI
import SwiftData

@main
struct iFauxtoApp: App {
    @StateObject private var dataManager: DataManager
    @StateObject private var photoKitService = PhotoKitService()
    @StateObject private var syncManager: SyncManager
    @StateObject private var importService: LibraryImportService
    @StateObject private var indexingManager: IndexingManager
    @StateObject private var navCoordinator = NavCoordinator()
    @StateObject private var userSession = UserSession.shared

    private let tagStore: TagStore
    private let searchService: SearchService

    init() {
        do {
            let dm = try DataManager()
            let ts = try TagStore()
            _dataManager = StateObject(wrappedValue: dm)
            _syncManager = StateObject(wrappedValue: SyncManager(dataManager: dm))
            _importService = StateObject(wrappedValue: LibraryImportService(dataManager: dm))
            _indexingManager = StateObject(wrappedValue: IndexingManager(tagStore: ts))
            tagStore = ts
            searchService = SearchService(tagStore: ts)
        } catch {
            fatalError("Failed to initialize: \(error)")
        }
    }

    var body: some Scene {
        mainScene
    }

    private var mainScene: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(dataManager)
                .environmentObject(photoKitService)
                .environmentObject(syncManager)
                .environmentObject(importService)
                .environmentObject(indexingManager)
                .environmentObject(navCoordinator)
                .environmentObject(userSession)
                .environment(\.searchService, searchService)
                .modelContainer(dataManager.modelContainer)
                .preferredColorScheme(.light)
                .onAppear {
                    userSession.bootstrap(dataManager: dataManager)
                    indexingManager.startBackgroundIndexing()
                    drainShareInboxIfNeeded()
                }
        }
        .commands { AppCommands() }
    }

    /// Looks at the shared App Group inbox where the Share Extension drops
    /// incoming photos, moves them into Documents/Imports/, and stashes the
    /// resulting identifiers into a "Recents → Shared" folder so the user
    /// sees them on next launch.
    private func drainShareInboxIfNeeded() {
        let incoming = ShareInboxService.drainInbox()
        guard !incoming.isEmpty else { return }
        let name = "Shared with iFauxto"
        let siblings = dataManager.fetchFolders(parentId: nil)
        let target = siblings.first(where: { $0.name == name })
            ?? dataManager.createFolder(name: name)
        dataManager.addPhotos(assetIdentifiers: incoming, to: target)
    }
}

private struct SearchServiceKey: EnvironmentKey {
    static let defaultValue: SearchService? = nil
}

extension EnvironmentValues {
    var searchService: SearchService? {
        get { self[SearchServiceKey.self] }
        set { self[SearchServiceKey.self] = newValue }
    }
}
