import SwiftUI
import SwiftData

@main
struct iFauxtoApp: App {
    @StateObject private var dataManager: DataManager
    @StateObject private var photoKitService = PhotoKitService()
    @StateObject private var syncManager: SyncManager
    @StateObject private var importService: LibraryImportService

    init() {
        do {
            let dm = try DataManager()
            _dataManager = StateObject(wrappedValue: dm)
            _syncManager = StateObject(wrappedValue: SyncManager(dataManager: dm))
            _importService = StateObject(wrappedValue: LibraryImportService(dataManager: dm))
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
                .environmentObject(importService)
        }
    }
}
