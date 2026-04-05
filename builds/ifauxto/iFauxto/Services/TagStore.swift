import Foundation
import SQLite3

struct TagRecord {
    let tagType: String   // "object", "text", "face", "scene", "location", "time"
    let tagValue: String
    let confidence: Float
}

final class TagStore: Sendable {
    private let db: OpaquePointer

    init(path: String = TagStore.defaultPath()) throws {
        var dbPointer: OpaquePointer?
        let result = sqlite3_open(path, &dbPointer)
        guard result == SQLITE_OK, let db = dbPointer else {
            let msg = dbPointer.flatMap { String(cString: sqlite3_errmsg($0)) } ?? "unknown"
            throw TagStoreError.openFailed(msg)
        }
        self.db = db
        try createTables()
    }

    deinit {
        sqlite3_close(db)
    }

    static func defaultPath() -> String {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("ifauxto_tags.sqlite").path
    }

    private func createTables() throws {
        let sql = """
            CREATE VIRTUAL TABLE IF NOT EXISTS photo_tags USING fts5(
                asset_id,
                tag_type,
                tag_value,
                confidence UNINDEXED
            );
            """
        try execute(sql)
    }

    // MARK: - Write

    func insertTags(assetId: String, tags: [TagRecord]) throws {
        for tag in tags {
            let sql = "INSERT INTO photo_tags (asset_id, tag_type, tag_value, confidence) VALUES (?, ?, ?, ?)"
            try execute(sql, bindings: [assetId, tag.tagType, tag.tagValue, "\(tag.confidence)"])
        }
    }

    func deleteTags(assetId: String) throws {
        try execute("DELETE FROM photo_tags WHERE asset_id = ?", bindings: [assetId])
    }

    // MARK: - Read

    func search(query: String) throws -> [String] {
        let ftsQuery = query.split(separator: " ").map { "\($0)*" }.joined(separator: " ")
        let sql = "SELECT DISTINCT asset_id FROM photo_tags WHERE tag_value MATCH ? ORDER BY rank"
        return try queryStrings(sql, bindings: [ftsQuery])
    }

    func suggestions(prefix: String) throws -> [String] {
        let sql = "SELECT DISTINCT tag_value FROM photo_tags WHERE tag_value MATCH ? LIMIT 10"
        return try queryStrings(sql, bindings: ["\(prefix)*"])
    }

    func isIndexed(assetId: String) throws -> Bool {
        let sql = "SELECT COUNT(*) FROM photo_tags WHERE asset_id = ?"
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else {
            throw TagStoreError.queryFailed(String(cString: sqlite3_errmsg(db)))
        }
        sqlite3_bind_text(stmt, 1, (assetId as NSString).utf8String, -1, nil)
        guard sqlite3_step(stmt) == SQLITE_ROW else { return false }
        return sqlite3_column_int(stmt, 0) > 0
    }

    func indexedCount() throws -> Int {
        let sql = "SELECT COUNT(DISTINCT asset_id) FROM photo_tags"
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return 0 }
        guard sqlite3_step(stmt) == SQLITE_ROW else { return 0 }
        return Int(sqlite3_column_int(stmt, 0))
    }

    // MARK: - Helpers

    private func execute(_ sql: String, bindings: [String] = []) throws {
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else {
            throw TagStoreError.queryFailed(String(cString: sqlite3_errmsg(db)))
        }
        for (i, value) in bindings.enumerated() {
            sqlite3_bind_text(stmt, Int32(i + 1), (value as NSString).utf8String, -1, nil)
        }
        let result = sqlite3_step(stmt)
        guard result == SQLITE_DONE || result == SQLITE_ROW else {
            throw TagStoreError.queryFailed(String(cString: sqlite3_errmsg(db)))
        }
    }

    private func queryStrings(_ sql: String, bindings: [String] = []) throws -> [String] {
        var stmt: OpaquePointer?
        defer { sqlite3_finalize(stmt) }
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else {
            throw TagStoreError.queryFailed(String(cString: sqlite3_errmsg(db)))
        }
        for (i, value) in bindings.enumerated() {
            sqlite3_bind_text(stmt, Int32(i + 1), (value as NSString).utf8String, -1, nil)
        }
        var results: [String] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            if let cStr = sqlite3_column_text(stmt, 0) {
                results.append(String(cString: cStr))
            }
        }
        return results
    }
}

enum TagStoreError: Error {
    case openFailed(String)
    case queryFailed(String)
}
