import Foundation

/// Reads files dropped into the shared App Group inbox by the Share
/// Extension and imports them into the main app's Documents/Imports
/// directory, returning the resulting identifiers for PhotoReference
/// creation. Should be called at app launch and when returning to the
/// foreground.
enum ShareInboxService {

    static let appGroupId = "group.com.ifauxto.shared"
    static let inboxSubpath = "ShareInbox"

    /// Drains the inbox. Returns `file://` identifiers for any files
    /// that were successfully imported. Caller is responsible for
    /// deciding which album they land in — for now we pass them back
    /// and the app surfaces a "Imported N photos" toast or adds them
    /// to a default "Inbox" album.
    static func drainInbox() -> [String] {
        guard let container = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: appGroupId
        ) else { return [] }

        let inboxDir = container.appendingPathComponent(inboxSubpath, isDirectory: true)
        guard FileManager.default.fileExists(atPath: inboxDir.path) else { return [] }

        let contents = (try? FileManager.default.contentsOfDirectory(
            at: inboxDir,
            includingPropertiesForKeys: nil
        )) ?? []

        var identifiers: [String] = []

        // Target directory in main app's Documents.
        guard let docs = FileManager.default.urls(
            for: .documentDirectory,
            in: .userDomainMask
        ).first else { return [] }
        let importsDir = docs.appendingPathComponent("Imports", isDirectory: true)
        if !FileManager.default.fileExists(atPath: importsDir.path) {
            try? FileManager.default.createDirectory(
                at: importsDir,
                withIntermediateDirectories: true
            )
        }

        for src in contents {
            // Skip caption sidecars — they get picked up alongside
            // their media file by filename match.
            if src.lastPathComponent.hasSuffix(".caption.txt") { continue }

            let dest = importsDir.appendingPathComponent(src.lastPathComponent)
            do {
                if FileManager.default.fileExists(atPath: dest.path) {
                    try FileManager.default.removeItem(at: dest)
                }
                try FileManager.default.moveItem(at: src, to: dest)
                identifiers.append("file://\(dest.path)")
            } catch {
                continue
            }
        }

        return identifiers
    }

    /// How many files are sitting in the inbox right now, for a badge.
    static func pendingCount() -> Int {
        guard let container = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: appGroupId
        ) else { return 0 }

        let inboxDir = container.appendingPathComponent(inboxSubpath, isDirectory: true)
        guard FileManager.default.fileExists(atPath: inboxDir.path) else { return 0 }

        let contents = (try? FileManager.default.contentsOfDirectory(
            at: inboxDir,
            includingPropertiesForKeys: nil
        )) ?? []
        return contents.filter { !$0.lastPathComponent.hasSuffix(".caption.txt") }.count
    }
}
