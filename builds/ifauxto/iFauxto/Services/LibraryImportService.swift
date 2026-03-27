import Photos
import SwiftData
import Foundation

// Mirrors the user's Photos app album/folder hierarchy into iFauxto's SwiftData store.
// Uses PHCollectionList for folders and PHAssetCollection for albums.
// Stores only PHAsset.localIdentifier — no pixel data is copied.
@MainActor
final class LibraryImportService: ObservableObject {

    // MARK: - Published state

    @Published var isImporting = false
    @Published var progress: Double = 0          // 0.0 → 1.0
    @Published var statusMessage = ""
    @Published var importedFolderCount = 0
    @Published var importedPhotoCount = 0
    @Published var authorizationDenied = false

    // MARK: - Persistence

    private static let importedKey = "iFauxto.hasImportedLibrary"

    var hasImportedLibrary: Bool {
        UserDefaults.standard.bool(forKey: Self.importedKey)
    }

    func resetImportFlag() {
        UserDefaults.standard.removeObject(forKey: Self.importedKey)
    }

    // MARK: - Init

    private let dataManager: DataManager

    init(dataManager: DataManager) {
        self.dataManager = dataManager
    }

    // MARK: - Public import entry point

    /// Walk the user's Photos library and mirror the folder/album structure.
    /// Skips smart albums. Runs entirely on MainActor since DataManager is @MainActor.
    func importLibrary() async {
        guard !isImporting else { return }

        isImporting = true
        authorizationDenied = false
        progress = 0
        importedFolderCount = 0
        importedPhotoCount = 0
        statusMessage = "Requesting Photos access…"

        // Request authorization
        let status = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
        guard status == .authorized || status == .limited else {
            statusMessage = status == .denied || status == .restricted
                ? "Photos access denied. Enable in Settings → Privacy → Photos."
                : "Photos access not granted."
            authorizationDenied = true
            isImporting = false
            return
        }

        statusMessage = "Reading library structure…"

        // Top-level collections: returns both PHCollectionList (folders) and PHAssetCollection (albums)
        let topLevel = PHCollectionList.fetchTopLevelUserCollections(with: nil)
        let totalTopLevel = max(topLevel.count, 1)

        for i in 0 ..< topLevel.count {
            let collection = topLevel.object(at: i)
            await importCollection(collection, parentId: nil)
            // 95% of progress covers the traversal; last 5% is the final save
            progress = Double(i + 1) / Double(totalTopLevel) * 0.95
        }

        // Final batch save
        try? dataManager.modelContext.save()
        progress = 1.0

        let summary = importedPhotoCount == 0
            ? "No photos imported — library may be empty on this device."
            : "Imported \(importedFolderCount) folders · \(importedPhotoCount) photos"
        statusMessage = summary

        UserDefaults.standard.set(true, forKey: Self.importedKey)
        isImporting = false
    }

    // MARK: - Private recursive import

    private func importCollection(_ collection: PHCollection, parentId: String?) async {
        if let album = collection as? PHAssetCollection {
            guard shouldImport(album) else { return }
            await importAlbum(album, parentId: parentId)

        } else if let folderList = collection as? PHCollectionList {
            guard shouldImport(folderList) else { return }
            await importFolder(folderList, parentId: parentId)
        }
    }

    private func importAlbum(_ album: PHAssetCollection, parentId: String?) async {
        let title = album.localizedTitle?.trimmingCharacters(in: .whitespaces).nonEmpty ?? "Album"
        statusMessage = "Importing \"\(title)\"…"

        // Skip albums that have no assets
        let fetchOpts = PHFetchOptions()
        fetchOpts.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: true)]
        let assets = PHAsset.fetchAssets(in: album, options: fetchOpts)
        guard assets.count > 0 else { return }

        let folder = dataManager.createFolder(name: title, parentId: parentId)
        importedFolderCount += 1

        // Batch-insert PhotoReferences without per-photo saves
        var batch: [PhotoReference] = []
        let existingIds = Set((folder.photoReferences ?? []).map(\.id))

        for j in 0 ..< assets.count {
            let identifier = assets.object(at: j).localIdentifier
            guard !existingIds.contains(identifier) else { continue }

            let orderIndex = (folder.photoReferences ?? []).count + batch.count
            let ref = PhotoReference(assetIdentifier: identifier,
                                     folderId: folder.id,
                                     orderIndex: orderIndex)
            ref.folder = folder
            dataManager.modelContext.insert(ref)
            batch.append(ref)
            importedPhotoCount += 1

            // Flush every 500 to avoid unbounded memory growth
            if batch.count >= 500 {
                folder.photoReferences = (folder.photoReferences ?? []) + batch
                try? dataManager.modelContext.save()
                batch = []
            }
        }

        if !batch.isEmpty {
            folder.photoReferences = (folder.photoReferences ?? []) + batch
            // Don't save here — caller does the final save after all albums
        }
    }

    private func importFolder(_ folderList: PHCollectionList, parentId: String?) async {
        let title = folderList.localizedTitle?.trimmingCharacters(in: .whitespaces).nonEmpty ?? "Folder"
        statusMessage = "Processing \"\(title)\"…"

        let folder = dataManager.createFolder(name: title, parentId: parentId)
        importedFolderCount += 1

        let subCollections = PHCollection.fetchCollections(in: folderList, options: nil)
        for j in 0 ..< subCollections.count {
            await importCollection(subCollections.object(at: j), parentId: folder.id)
        }

        // Remove empty parent folders
        if (folder.photoReferences ?? []).isEmpty && dataManager.fetchFolders(parentId: folder.id).isEmpty {
            dataManager.modelContext.delete(folder)
            importedFolderCount -= 1
        }
    }

    // MARK: - Filtering

    private func shouldImport(_ album: PHAssetCollection) -> Bool {
        switch album.assetCollectionType {
        case .album:
            // Import all user albums: regular, imported, synced, shared
            return true
        case .smartAlbum:
            // Only import "All Photos" / Recents as a convenience root album
            return album.assetCollectionSubtype == .smartAlbumUserLibrary
        case .moment:
            return false
        @unknown default:
            return false
        }
    }

    private func shouldImport(_ folderList: PHCollectionList) -> Bool {
        // PHCollectionListType: .folder = user-created, .momentList/.smartFolder = system-generated
        return folderList.collectionListType == .folder
    }
}

// MARK: - String helper

private extension String {
    /// Returns nil if the string is empty after trimming, otherwise self.
    var nonEmpty: String? { isEmpty ? nil : self }
}
