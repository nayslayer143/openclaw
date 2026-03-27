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
        let schema = Schema([Folder.self, PhotoReference.self])
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
}
