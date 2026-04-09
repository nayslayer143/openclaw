import Foundation
import UIKit

/// Copies files picked from the Files app into the app's Documents
/// directory and returns the resulting "file:" identifiers so they can
/// be stored as PhotoReference rows. The thumbnail loaders fall back to
/// these identifiers via the `file:` prefix path.
enum FilesImportService {

    /// Copies a list of security-scoped URLs into the current user's
    /// Imports directory and returns stable `local:` identifiers.
    /// Relative paths survive reinstalls — iOS rolls the app container
    /// UUID on every install, so absolute file:// paths would orphan.
    @MainActor
    static func importFiles(_ urls: [URL]) -> [String] {
        var imported: [String] = []
        let fm = FileManager.default
        let importsDir = UserSession.shared.activeUserDirectory
            .appendingPathComponent("Imports", isDirectory: true)
        if !fm.fileExists(atPath: importsDir.path) {
            try? fm.createDirectory(at: importsDir, withIntermediateDirectories: true)
        }

        for src in urls {
            let needsScope = src.startAccessingSecurityScopedResource()
            defer { if needsScope { src.stopAccessingSecurityScopedResource() } }

            let unique = "\(UUID().uuidString)-\(src.lastPathComponent)"
            let dest = importsDir.appendingPathComponent(unique)
            do {
                try fm.copyItem(at: src, to: dest)
                imported.append("local:Imports/\(unique)")
            } catch {
                continue
            }
        }
        return imported
    }
}
