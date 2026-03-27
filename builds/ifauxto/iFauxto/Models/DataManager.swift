import SwiftData
import Foundation

@MainActor
final class DataManager: ObservableObject {
    let modelContainer: ModelContainer
    let modelContext: ModelContext

    // MARK: Init

    init(inMemory: Bool = false) throws {
        let schema = Schema([Folder.self, PhotoReference.self])
        let config: ModelConfiguration
        if inMemory {
            config = ModelConfiguration(schema: schema, isStoredInMemoryOnly: true)
        } else {
            config = ModelConfiguration(
                schema: schema,
                isStoredInMemoryOnly: false,
                cloudKitDatabase: .private("iCloud.com.ifauxto.app")
            )
        }
        modelContainer = try ModelContainer(for: schema, configurations: [config])
        modelContext = modelContainer.mainContext
    }

    // MARK: Folder CRUD

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

    func addPhoto(assetIdentifier: String, to folder: Folder) -> PhotoReference {
        let order = folder.photoReferences.count
        let ref = PhotoReference(assetIdentifier: assetIdentifier, folderId: folder.id, orderIndex: order)
        ref.folder = folder
        modelContext.insert(ref)
        folder.photoReferences.append(ref)
        try? modelContext.save()
        return ref
    }

    func addPhotos(assetIdentifiers: [String], to folder: Folder) {
        for identifier in assetIdentifiers {
            // Skip duplicates in this folder
            guard !folder.photoReferences.contains(where: { $0.id == identifier }) else { continue }
            _ = addPhoto(assetIdentifier: identifier, to: folder)
        }
    }

    func fetchPhotos(in folder: Folder) -> [PhotoReference] {
        return folder.photoReferences.sorted { $0.orderIndex < $1.orderIndex }
    }

    func updatePhotoOrder(_ photos: [PhotoReference]) {
        for (index, photo) in photos.enumerated() {
            photo.orderIndex = index
        }
        try? modelContext.save()
    }

    func removePhoto(_ photo: PhotoReference, from folder: Folder) {
        folder.photoReferences.removeAll { $0.id == photo.id }
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
            photo.folderId = destination.id
            photo.folder = destination
            photo.orderIndex = destination.photoReferences.count
            destination.photoReferences.append(photo)
        }
        try? modelContext.save()
    }
}
