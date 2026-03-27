import Testing
import SwiftData
import Foundation
@testable import iFauxto

// DataManager tests use an in-memory ModelContainer to avoid disk I/O
@MainActor
@Suite("DataManager")
struct DataManagerTests {

    func makeManager() throws -> DataManager {
        return try DataManager(inMemory: true)
    }

    @Test("Creates root folder with correct defaults")
    func createRootFolder() throws {
        let dm = try makeManager()
        let folder = dm.createFolder(name: "Travel", parentId: nil)
        #expect(folder.name == "Travel")
        #expect(folder.parentId == nil)
        #expect(folder.order == 0)
    }

    @Test("Creates nested folder under parent")
    func createNestedFolder() throws {
        let dm = try makeManager()
        let parent = dm.createFolder(name: "Travel", parentId: nil)
        let child = dm.createFolder(name: "Japan", parentId: parent.id)
        #expect(child.parentId == parent.id)
        let children = dm.fetchFolders(parentId: parent.id)
        #expect(children.count == 1)
        #expect(children[0].id == child.id)
    }

    @Test("Fetch root folders returns only top-level folders")
    func fetchRootFolders() throws {
        let dm = try makeManager()
        let root1 = dm.createFolder(name: "A", parentId: nil)
        let root2 = dm.createFolder(name: "B", parentId: nil)
        let _ = dm.createFolder(name: "C", parentId: root1.id)
        let roots = dm.fetchFolders(parentId: nil)
        #expect(roots.count == 2)
        #expect(roots.map(\.id).contains(root1.id))
        #expect(roots.map(\.id).contains(root2.id))
    }

    @Test("Folder order auto-increments within same parent")
    func folderOrderIncrements() throws {
        let dm = try makeManager()
        let f1 = dm.createFolder(name: "First", parentId: nil)
        let f2 = dm.createFolder(name: "Second", parentId: nil)
        let f3 = dm.createFolder(name: "Third", parentId: nil)
        #expect(f1.order == 0)
        #expect(f2.order == 1)
        #expect(f3.order == 2)
    }

    @Test("updateFolderOrder persists new sequence")
    func updateFolderOrder() throws {
        let dm = try makeManager()
        let f1 = dm.createFolder(name: "A", parentId: nil)
        let f2 = dm.createFolder(name: "B", parentId: nil)
        let f3 = dm.createFolder(name: "C", parentId: nil)
        dm.updateFolderOrder([f3, f1, f2])
        #expect(f3.order == 0)
        #expect(f1.order == 1)
        #expect(f2.order == 2)
    }

    @Test("Add photo to folder assigns correct orderIndex")
    func addPhoto() throws {
        let dm = try makeManager()
        let folder = dm.createFolder(name: "Shots", parentId: nil)
        let p1 = dm.addPhoto(assetIdentifier: "asset-1", to: folder)
        let p2 = dm.addPhoto(assetIdentifier: "asset-2", to: folder)
        #expect(p1.orderIndex == 0)
        #expect(p2.orderIndex == 1)
    }

    @Test("fetchPhotos returns photos sorted by orderIndex")
    func fetchPhotosSorted() throws {
        let dm = try makeManager()
        let folder = dm.createFolder(name: "Events", parentId: nil)
        dm.addPhoto(assetIdentifier: "z", to: folder)
        dm.addPhoto(assetIdentifier: "a", to: folder)
        dm.addPhoto(assetIdentifier: "m", to: folder)
        let photos = dm.fetchPhotos(in: folder)
        #expect(photos[0].id == "z")
        #expect(photos[1].id == "a")
        #expect(photos[2].id == "m")
    }

    @Test("updatePhotoOrder persists new sequence")
    func updatePhotoOrder() throws {
        let dm = try makeManager()
        let folder = dm.createFolder(name: "Reorder", parentId: nil)
        let p1 = dm.addPhoto(assetIdentifier: "first", to: folder)
        let p2 = dm.addPhoto(assetIdentifier: "second", to: folder)
        let p3 = dm.addPhoto(assetIdentifier: "third", to: folder)
        dm.updatePhotoOrder([p3, p1, p2])
        #expect(p3.orderIndex == 0)
        #expect(p1.orderIndex == 1)
        #expect(p2.orderIndex == 2)
    }

    @Test("Delete folder removes it from fetch results")
    func deleteFolder() throws {
        let dm = try makeManager()
        let folder = dm.createFolder(name: "ToDelete", parentId: nil)
        dm.deleteFolder(folder)
        let folders = dm.fetchFolders(parentId: nil)
        #expect(!folders.map(\.id).contains(folder.id))
    }

    @Test("Delete folder also deletes its photos (cascade)")
    func deleteFolderCascadesPhotos() throws {
        let dm = try makeManager()
        let folder = dm.createFolder(name: "Cascade", parentId: nil)
        dm.addPhoto(assetIdentifier: "orphan-1", to: folder)
        dm.addPhoto(assetIdentifier: "orphan-2", to: folder)
        dm.deleteFolder(folder)
        // After cascade delete, photos should be gone
        let descriptor = FetchDescriptor<PhotoReference>()
        let remaining = (try? dm.modelContext.fetch(descriptor)) ?? []
        #expect(remaining.filter { $0.folderId == folder.id }.isEmpty)
    }
}
