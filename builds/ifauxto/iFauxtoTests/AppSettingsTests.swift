import Testing
import SwiftData
import Foundation
@testable import iFauxto

@MainActor
@Suite("AppSettings")
struct AppSettingsTests {

    func makeManager() throws -> DataManager {
        return try DataManager(inMemory: true)
    }

    @Test("AppSettings defaults to folder_list home mode")
    func defaultHomeMode() throws {
        let dm = try makeManager()
        let settings = dm.getOrCreateSettings()
        #expect(settings.homeViewMode == "folder_list")
    }

    @Test("AppSettings home mode can be changed")
    func changeHomeMode() throws {
        let dm = try makeManager()
        let settings = dm.getOrCreateSettings()
        settings.homeViewMode = "chronological_feed"
        try dm.modelContext.save()
        let fetched = dm.getOrCreateSettings()
        #expect(fetched.homeViewMode == "chronological_feed")
    }

    @Test("getOrCreateSettings returns same singleton")
    func singleton() throws {
        let dm = try makeManager()
        let s1 = dm.getOrCreateSettings()
        let s2 = dm.getOrCreateSettings()
        #expect(s1.id == s2.id)
    }
}
