import SwiftData
import Foundation

@MainActor
final class DataManager: ObservableObject {
    let modelContainer: ModelContainer
    let modelContext: ModelContext

    // MARK: Init

    /// CloudKit sync is enabled when the build has the
    /// `com.apple.developer.icloud-services` entitlement and a valid
    /// container identifier. The Info.plist key `iFauxtoCloudKitEnabled`
    /// flips it on. Defaults off so unsigned dev builds don't crash.
    let isCloudKitEnabled: Bool

    init(inMemory: Bool = false) throws {
        let cloudEnabled = (Bundle.main.object(forInfoDictionaryKey: "iFauxtoCloudKitEnabled") as? Bool) ?? false
        self.isCloudKitEnabled = cloudEnabled

        let schema = Schema([Folder.self, PhotoReference.self, AppSettings.self, EditState.self, PhotoMeta.self, SmartAlbum.self, PhotoProject.self])
        let config = ModelConfiguration(
            schema: schema,
            isStoredInMemoryOnly: inMemory,
            cloudKitDatabase: cloudEnabled ? .automatic : .none
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

    func setTitle(_ title: String, for assetId: String) {
        let meta = getOrCreateMeta(for: assetId)
        meta.title = title
        meta.updatedAt = Date()
        try? modelContext.save()
    }

    func setCaption(_ caption: String, for assetId: String) {
        let meta = getOrCreateMeta(for: assetId)
        meta.caption = caption
        meta.updatedAt = Date()
        try? modelContext.save()
    }

    func favoriteAssetIds() -> [String] {
        let descriptor = FetchDescriptor<PhotoMeta>(
            predicate: #Predicate { $0.isFavorite == true && $0.trashedAt == nil }
        )
        return ((try? modelContext.fetch(descriptor)) ?? []).map(\.assetIdentifier)
    }

    func hiddenAssetIds() -> [String] {
        let descriptor = FetchDescriptor<PhotoMeta>(
            predicate: #Predicate { $0.isHidden == true && $0.trashedAt == nil }
        )
        return ((try? modelContext.fetch(descriptor)) ?? []).map(\.assetIdentifier)
    }

    func trashedAssetIds() -> [String] {
        let descriptor = FetchDescriptor<PhotoMeta>(
            predicate: #Predicate { $0.trashedAt != nil }
        )
        return ((try? modelContext.fetch(descriptor)) ?? []).map(\.assetIdentifier)
    }

    /// Returns the union of asset IDs that should be filtered out of the
    /// chronological feed and album grids (hidden + trashed).
    func excludedAssetIdSet() -> Set<String> {
        let descriptor = FetchDescriptor<PhotoMeta>(
            predicate: #Predicate { $0.isHidden == true || $0.trashedAt != nil }
        )
        let metas = (try? modelContext.fetch(descriptor)) ?? []
        return Set(metas.map(\.assetIdentifier))
    }

    func toggleHidden(for assetId: String) -> Bool {
        let meta = getOrCreateMeta(for: assetId)
        meta.isHidden.toggle()
        meta.updatedAt = Date()
        try? modelContext.save()
        return meta.isHidden
    }

    func moveToTrash(_ assetId: String) {
        let meta = getOrCreateMeta(for: assetId)
        meta.trashedAt = Date()
        meta.updatedAt = Date()
        try? modelContext.save()
    }

    func restoreFromTrash(_ assetId: String) {
        let meta = getOrCreateMeta(for: assetId)
        meta.trashedAt = nil
        meta.updatedAt = Date()
        try? modelContext.save()
    }

    // MARK: - Smart Albums

    func fetchSmartAlbums() -> [SmartAlbum] {
        let descriptor = FetchDescriptor<SmartAlbum>(
            sortBy: [SortDescriptor(\.createdAt, order: .reverse)]
        )
        return (try? modelContext.fetch(descriptor)) ?? []
    }

    @discardableResult
    func createSmartAlbum(name: String, rules: [SmartRule]) -> SmartAlbum {
        let album = SmartAlbum(name: name, rules: rules)
        modelContext.insert(album)
        try? modelContext.save()
        return album
    }

    func deleteSmartAlbum(_ album: SmartAlbum) {
        modelContext.delete(album)
        try? modelContext.save()
    }

    /// Evaluates a smart album's rules against all PhotoMeta + the
    /// candidate identifier list, returning matching identifiers.
    func evaluateSmartAlbum(_ album: SmartAlbum, candidates: [String]) -> [String] {
        guard !album.rules.isEmpty else { return candidates }
        let metas = Dictionary(
            uniqueKeysWithValues: candidates.map { ($0, metaIfExists(for: $0)) }
        )
        return candidates.filter { id in
            let meta = metas[id] ?? nil
            return album.rules.allSatisfy { evaluate(rule: $0, identifier: id, meta: meta) }
        }
    }

    private func evaluate(rule: SmartRule, identifier: String, meta: PhotoMeta?) -> Bool {
        switch rule.field {
        case .favorite:
            let v = meta?.isFavorite ?? false
            return rule.op == .isTrue ? v : !v
        case .hidden:
            let v = meta?.isHidden ?? false
            return rule.op == .isTrue ? v : !v
        case .rating:
            let r = meta?.rating ?? 0
            let target = Int(rule.value) ?? 0
            switch rule.op {
            case .equals:  return r == target
            case .atLeast: return r >= target
            default:       return false
            }
        case .eventBucket:
            // Match against the synthesized bucket title for the photo.
            let title = PhotoDateGrouper.group([identifier]).first?.title ?? ""
            return title.localizedCaseInsensitiveContains(rule.value)
        }
    }

    // MARK: - Projects (collage / book / card / calendar)

    func fetchProjects() -> [PhotoProject] {
        let descriptor = FetchDescriptor<PhotoProject>(
            sortBy: [SortDescriptor(\.updatedAt, order: .reverse)]
        )
        return (try? modelContext.fetch(descriptor)) ?? []
    }

    @discardableResult
    func createProject(name: String, type: ProjectType, photoIds: [String] = []) -> PhotoProject {
        let project = PhotoProject(name: name, type: type, photoIds: photoIds)
        modelContext.insert(project)
        try? modelContext.save()
        return project
    }

    func deleteProject(_ project: PhotoProject) {
        modelContext.delete(project)
        try? modelContext.save()
    }

    /// Hard-deletes any PhotoMeta whose trashedAt is older than 30 days.
    func purgeExpiredTrash() {
        let cutoff = Date().addingTimeInterval(-30 * 24 * 3600)
        let descriptor = FetchDescriptor<PhotoMeta>(
            predicate: #Predicate { $0.trashedAt != nil }
        )
        let trashed = (try? modelContext.fetch(descriptor)) ?? []
        for meta in trashed where (meta.trashedAt ?? Date()) < cutoff {
            modelContext.delete(meta)
        }
        try? modelContext.save()
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
