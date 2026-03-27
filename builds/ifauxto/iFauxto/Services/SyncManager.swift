import Foundation
import SwiftData
import CoreData
import Combine

/// Coordinates CloudKit sync state and notifies the UI of sync events.
/// SwiftData handles the actual sync via ModelConfiguration(cloudKitDatabase:).
/// This class surfaces status and triggers manual refresh when needed.
@MainActor
final class SyncManager: ObservableObject {
    @Published var isSyncing: Bool = false
    @Published var lastSyncDate: Date?
    @Published var syncError: Error?

    private let dataManager: DataManager
    private var cancellables = Set<AnyCancellable>()

    init(dataManager: DataManager) {
        self.dataManager = dataManager
        observeRemoteChanges()
    }

    /// SwiftData + CloudKit fires NSPersistentStoreRemoteChange notifications.
    private func observeRemoteChanges() {
        NotificationCenter.default
            .publisher(for: NSPersistentCloudKitContainer.eventChangedNotification)
            .receive(on: DispatchQueue.main)
            .sink { [weak self] notification in
                self?.handleCloudKitEvent(notification)
            }
            .store(in: &cancellables)
    }

    private func handleCloudKitEvent(_ notification: Notification) {
        guard let event = notification.userInfo?[NSPersistentCloudKitContainer.eventNotificationUserInfoKey]
            as? NSPersistentCloudKitContainer.Event else { return }

        switch event.type {
        case .setup:
            break
        case .import:
            isSyncing = event.endDate == nil
            if event.endDate != nil { lastSyncDate = event.endDate }
        case .export:
            isSyncing = event.endDate == nil
        @unknown default:
            break
        }

        if let error = event.error {
            syncError = error
        }
    }
}
