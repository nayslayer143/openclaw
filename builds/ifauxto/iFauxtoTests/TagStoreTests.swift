import Testing
import Foundation
@testable import iFauxto

@Suite("TagStore")
struct TagStoreTests {

    func makeStore() throws -> TagStore {
        return try TagStore(path: ":memory:")
    }

    @Test("Insert and search tags")
    func insertAndSearch() throws {
        let store = try makeStore()
        try store.insertTags(assetId: "photo-1", tags: [
            TagRecord(tagType: "object", tagValue: "beach", confidence: 0.95),
            TagRecord(tagType: "object", tagValue: "ocean", confidence: 0.88),
            TagRecord(tagType: "scene", tagValue: "sunset", confidence: 0.75),
        ])
        let results = try store.search(query: "beach")
        #expect(results.count == 1)
        #expect(results[0] == "photo-1")
    }

    @Test("Search returns empty for no match")
    func noMatch() throws {
        let store = try makeStore()
        try store.insertTags(assetId: "photo-1", tags: [
            TagRecord(tagType: "object", tagValue: "car", confidence: 0.9),
        ])
        let results = try store.search(query: "beach")
        #expect(results.isEmpty)
    }

    @Test("isIndexed returns correct state")
    func isIndexed() throws {
        let store = try makeStore()
        #expect(try !store.isIndexed(assetId: "photo-1"))
        try store.insertTags(assetId: "photo-1", tags: [
            TagRecord(tagType: "object", tagValue: "tree", confidence: 0.8),
        ])
        #expect(try store.isIndexed(assetId: "photo-1"))
    }

    @Test("deleteTags removes all tags for asset")
    func deleteTags() throws {
        let store = try makeStore()
        try store.insertTags(assetId: "photo-1", tags: [
            TagRecord(tagType: "object", tagValue: "cat", confidence: 0.9),
        ])
        try store.deleteTags(assetId: "photo-1")
        #expect(try !store.isIndexed(assetId: "photo-1"))
    }

    @Test("Suggestions returns matching tag values")
    func suggestions() throws {
        let store = try makeStore()
        try store.insertTags(assetId: "p1", tags: [
            TagRecord(tagType: "object", tagValue: "beach", confidence: 0.9),
        ])
        try store.insertTags(assetId: "p2", tags: [
            TagRecord(tagType: "object", tagValue: "bedroom", confidence: 0.8),
        ])
        let suggestions = try store.suggestions(prefix: "bea")
        #expect(suggestions.contains("beach"))
        #expect(!suggestions.contains("bedroom"))
    }
}
