import Testing
import SwiftData
import Foundation
@testable import iFauxto

@MainActor
@Suite("EditState")
struct EditStateTests {

    func makeManager() throws -> DataManager {
        return try DataManager(inMemory: true)
    }

    @Test("Save and retrieve edit state")
    func saveAndRetrieve() throws {
        let dm = try makeManager()
        var adj = EditAdjustments()
        adj.exposure = 0.5
        adj.contrast = -0.3
        dm.saveEditState(photoId: "photo-1", adjustments: adj)
        let fetched = dm.fetchEditState(photoId: "photo-1")
        #expect(fetched != nil)
        #expect(fetched?.adjustments.exposure == 0.5)
        #expect(fetched?.adjustments.contrast == -0.3)
    }

    @Test("Default adjustments are all zero")
    func defaults() throws {
        let adj = EditAdjustments()
        #expect(adj.exposure == 0)
        #expect(adj.contrast == 0)
        #expect(adj.saturation == 0)
        #expect(adj.temperature == 0)
        #expect(adj.highlights == 0)
        #expect(adj.shadows == 0)
        #expect(adj.grain == 0)
        #expect(adj.vignette == 0)
    }

    @Test("Delete edit state")
    func deleteEditState() throws {
        let dm = try makeManager()
        dm.saveEditState(photoId: "photo-1", adjustments: EditAdjustments())
        dm.deleteEditState(photoId: "photo-1")
        #expect(dm.fetchEditState(photoId: "photo-1") == nil)
    }

    @Test("hasEdits returns correct state")
    func hasEdits() throws {
        let dm = try makeManager()
        #expect(!dm.hasEdits(photoId: "photo-1"))
        dm.saveEditState(photoId: "photo-1", adjustments: EditAdjustments())
        #expect(dm.hasEdits(photoId: "photo-1"))
    }
}
