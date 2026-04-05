import SwiftUI
import SwiftData

@main
struct iFauxtoApp: App {
    @StateObject private var dataManager: DataManager
    @StateObject private var photoKitService = PhotoKitService()
    @StateObject private var syncManager: SyncManager
    @StateObject private var importService: LibraryImportService
    @StateObject private var indexingManager: IndexingManager

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
        WindowGroup {
            ContentView()
                .environmentObject(dataManager)
                .environmentObject(photoKitService)
                .environmentObject(syncManager)
                .environmentObject(importService)
                .environmentObject(indexingManager)
                .environment(\.searchService, searchService)
                .onAppear {
                    indexingManager.startBackgroundIndexing()
                }
        }
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
