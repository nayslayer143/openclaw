import Foundation
import UIKit

/// Copies files picked from the Files app into the app's Documents
/// directory and returns the resulting "file:" identifiers so they can
/// be stored as PhotoReference rows. The thumbnail loaders fall back to
/// these identifiers via the `file:` prefix path.
enum FilesImportService {

    /// Copies a list of security-scoped URLs into Documents/Imports/
    /// and returns the new on-disk URLs as identifiers.
    static func importFiles(_ urls: [URL]) -> [String] {
        var imported: [String] = []
        let fm = FileManager.default
        guard let docs = fm.urls(for: .documentDirectory, in: .userDomainMask).first else {
            return []
        }
        let importsDir = docs.appendingPathComponent("Imports", isDirectory: true)
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
                // Use file:// URL string as the identifier so the rest of
                // the app can branch on the prefix.
                imported.append("file://\(dest.path)")
            } catch {
                continue
            }
        }
        return imported
    }
}
