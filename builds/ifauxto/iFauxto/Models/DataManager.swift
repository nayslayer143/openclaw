import SwiftData
import Foundation

@MainActor
final class DataManager: ObservableObject {
    let modelContainer: ModelContainer
    let modelContext: ModelContext

    // MARK: Init

    // CloudKit sync disabled pending entitlements setup.
    // Model is CloudKit-compatible: all relationships optional ([PhotoReference]?).
    let isCloudKitEnabled: Bool = false

    init(inMemory: Bool = false) throws {
        let schema = Schema([Folder.self, PhotoReference.self, AppSettings.self, EditState.self, PhotoMeta.self])
        // cloudKitDatabase: .none prevents SwiftData from auto-enabling CloudKit via entitlements,
        // which would fail model validation (non-optional to-many relationship).
        let config = ModelConfiguration(
            schema: schema,
            isStoredInMemoryOnly: inMemory,
            cloudKitDatabase: .none
        )
        modelContainer = try ModelContainer(for: schema, configurations: [config])
        modelContext = modelContainer.mainContext
    }

    // MARK: Folder CRUD

    @discardableResult
    func createFolder(name: String, parentId: String? = nil) -> Folder {
        let siblings = fetchFolders(parentId: parentId)
        let order = siblings.count
        let folder = Folder(name: name, parentId: parentId, order: order)
        modelContext.insert(folder)
        try? modelContext.save()
        return folder
    }

    func fetchFolders(parentId: String? = nil) -> [Folder] {
        let descriptor: FetchDescriptor<Folder>
        if let pid = parentId {
            descriptor = FetchDescriptor<Folder>(
                predicate: #Predicate { $0.parentId == pid },
                sortBy: [SortDescriptor(\.order)]
            )
        } else {
            descriptor = FetchDescriptor<Folder>(
                predicate: #Predicate { $0.parentId == nil },
                sortBy: [SortDescriptor(\.order)]
            )
        }
        return (try? modelContext.fetch(descriptor)) ?? []
    }

    func deleteFolder(_ folder: Folder) {
        // Recursively delete subfolders first
        let children = fetchFolders(parentId: folder.id)
        for child in children {
            deleteFolder(child)
        }
        modelContext.delete(folder)
        try? modelContext.save()
    }

    func renameFolder(_ folder: Folder, to name: String) {
        folder.name = name
        try? modelContext.save()
    }

    func updateFolderOrder(_ folders: [Folder]) {
        for (index, folder) in folders.enumerated() {
            folder.order = index
        }
        try? modelContext.save()
    }

    // MARK: Photo CRUD

    @discardableResult
    func addPhoto(assetIdentifier: String, to folder: Folder) -> PhotoReference {
        let order = (folder.photoReferences ?? []).count
        let ref = PhotoReference(assetIdentifier: assetIdentifier, folderId: folder.id, orderIndex: order)
        ref.folder = folder
        modelContext.insert(ref)
        folder.photoReferences = (folder.photoReferences ?? []) + [ref]
        try? modelContext.save()
        return ref
    }

    func addPhotos(assetIdentifiers: [String], to folder: Folder) {
        for identifier in assetIdentifiers {
            // Skip duplicates in this folder
            guard !(folder.photoReferences ?? []).contains(where: { $0.id == identifier }) else { continue }
            _ = addPhoto(assetIdentifier: identifier, to: folder)
        }
    }

    func fetchPhotos(in folder: Folder) -> [PhotoReference] {
        return (folder.photoReferences ?? []).sorted { $0.orderIndex < $1.orderIndex }
    }

    func updatePhotoOrder(_ photos: [PhotoReference]) {
        for (index, photo) in photos.enumerated() {
            photo.orderIndex = index
        }
        try? modelContext.save()
    }

    func removePhoto(_ photo: PhotoReference, from folder: Folder) {
        folder.photoReferences?.removeAll { $0.id == photo.id }
        modelContext.delete(photo)
        try? modelContext.save()
    }

    func removePhotos(_ photos: [PhotoReference], from folder: Folder) {
        for photo in photos {
            removePhoto(photo, from: folder)
        }
        // Re-index remaining
        updatePhotoOrder(fetchPhotos(in: folder))
    }

    func movePhotos(_ photos: [PhotoReference], to destination: Folder) {
        for photo in photos {
            // Remove from source folder's relationship array
            photo.folder?.photoReferences?.removeAll { $0.id == photo.id }
            // Assign to destination
            photo.folderId = destination.id
            photo.folder = destination
            photo.orderIndex = (destination.photoReferences ?? []).count
            destination.photoReferences = (destination.photoReferences ?? []) + [photo]
        }
        try? modelContext.save()
    }

    // MARK: Settings

    func getOrCreateSettings() -> AppSettings {
        let descriptor = FetchDescriptor<AppSettings>()
        if let existing = try? modelContext.fetch(descriptor).first {
            return existing
        }
        let settings = AppSettings()
        modelContext.insert(settings)
        try? modelContext.save()
        return settings
    }

    /// Persist any in-place mutations to AppSettings.
    func saveSettings() {
        try? modelContext.save()
    }

    // MARK: - PhotoMeta (favorites, ratings, hidden, title, caption)

    func getOrCreateMeta(for assetId: String) -> PhotoMeta {
        let descriptor = FetchDescriptor<PhotoMeta>(
            predicate: #Predicate { $0.assetIdentifier == assetId }
        )
        if let existing = try? modelContext.fetch(descriptor).first {
            return existing
        }
        let meta = PhotoMeta(assetIdentifier: assetId)
        modelContext.insert(meta)
        try? modelContext.save()
        return meta
    }

    func metaIfExists(for assetId: String) -> PhotoMeta? {
        let descriptor = FetchDescriptor<PhotoMeta>(
            predicate: #Predicate { $0.assetIdentifier == assetId }
        )
        return try? modelContext.fetch(descriptor).first
    }

    func toggleFavorite(for assetId: String) -> Bool {
        let meta = getOrCreateMeta(for: assetId)
        meta.isFavorite.toggle()
        meta.updatedAt = Date()
        try? modelContext.save()
        return meta.isFavorite
    }

    func setRating(_ rating: Int, for assetId: String) {
        let meta = getOrCreateMeta(for: assetId)
        meta.rating = max(0, min(5, rating))
        meta.updatedAt = Date()
        try? modelContext.save()
    }

    func favoriteAssetIds() -> [String] {
        let descriptor = FetchDescriptor<PhotoMeta>(
            predicate: #Predicate { $0.isFavorite == true }
        )
        return ((try? modelContext.fetch(descriptor)) ?? []).map(\.assetIdentifier)
    }

    // MARK: Edit State CRUD

    /// Checks if any edit state exists for a given photo ID.
    func hasEdits(photoId: String) -> Bool {
        let descriptor = FetchDescriptor<EditState>(
            predicate: #Predicate { $0.photoId == photoId }
        )
        return (try? modelContext.fetch(descriptor))?.isEmpty == false
    }

    /// Fetches the current edit state for a photo ID.
    func fetchEditState(photoId: String) -> EditState? {
        let descriptor = FetchDescriptor<EditState>(
            predicate: #Predicate { $0.photoId == photoId }
        )
        return try? modelContext.fetch(descriptor).first
    }

    /// Saves or updates the edit state for a photo.
    func saveEditState(photoId: String, adjustments: EditAdjustments) {
        if let existingState = fetchEditState(photoId: photoId) {
            // Update existing record
            existingState.adjustments = adjustments
        } else {
            // Create new record
            let newState = EditState(photoId: photoId, adjustments: adjustments)
            modelContext.insert(newState)
        }
        do {
            try modelContext.save()
        } catch {
            print("Failed to save edit state: \(error)")
        }
    }

    /// Deletes the edit state for a photo ID.
    func deleteEditState(photoId: String) {
        let descriptor = FetchDescriptor<EditState>(
            predicate: #Predicate { $0.photoId == photoId }
        )
        if let stateToDelete = try? modelContext.fetch(descriptor).first {
            modelContext.delete(stateToDelete)
            try? modelContext.save()
        }
    }
}
