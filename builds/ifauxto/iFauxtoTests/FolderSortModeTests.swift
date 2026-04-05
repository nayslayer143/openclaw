import Testing
import SwiftData
import Foundation
@testable import iFauxto

@MainActor
@Suite("Folder Sort Mode")
struct FolderSortModeTests {

    func makeManager() throws -> DataManager {
        return try DataManager(inMemory: true)
    }

    @Test("New folder defaults to custom sort mode")
    func defaultSortMode() throws {
        let dm = try makeManager()
        let folder = dm.createFolder(name: "Test")
        #expect(folder.sortMode == "custom")
    }

    @Test("Sort mode can be changed and persisted")
    func changeSortMode() throws {
        let dm = try makeManager()
        let folder = dm.createFolder(name: "Test")
        folder.sortMode = "alpha"
        try dm.modelContext.save()
        #expect(folder.sortMode == "alpha")
    }
}
