import UIKit
import ImageIO
import UniformTypeIdentifiers

/// Loads and downsamples local image files efficiently. Uses ImageIO
/// `CGImageSourceCreateThumbnailAtIndex` which decodes only what's
/// needed for the requested pixel size — crucial for large HEIC/JPEG
/// originals that would otherwise blow up memory when used as grid
/// thumbnails.
enum FileImageLoader {

    /// In-memory cache keyed by "path|maxPixel". Small because we also
    /// rely on the underlying OS file cache.
    private static let cache = NSCache<NSString, UIImage>()

    /// Resolves a stored identifier to an on-disk URL.
    /// - `local:Imports/foo.jpg` → `<activeUserDir>/Imports/foo.jpg`
    /// - `file:///absolute/path/foo.jpg` → direct URL
    /// - anything else → nil
    @MainActor
    static func resolveURL(for identifier: String) -> URL? {
        if identifier.hasPrefix("local:") {
            let relative = String(identifier.dropFirst("local:".count))
            return UserSession.shared.activeUserDirectory
                .appendingPathComponent(relative)
        }
        if identifier.hasPrefix("file://") {
            return URL(string: identifier)
        }
        return nil
    }

    static func isLocalIdentifier(_ identifier: String) -> Bool {
        identifier.hasPrefix("local:") || identifier.hasPrefix("file://")
    }

    static func loadThumbnail(url: URL, maxPixelSize: CGFloat) async -> UIImage? {
        let key = "\(url.path)|\(Int(maxPixelSize))" as NSString
        if let cached = cache.object(forKey: key) {
            return cached
        }

        // Downsample off the main actor.
        let img = await Task.detached(priority: .userInitiated) { () -> UIImage? in
            guard let src = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
            let opts: [CFString: Any] = [
                kCGImageSourceCreateThumbnailFromImageAlways: true,
                kCGImageSourceCreateThumbnailWithTransform: true,
                kCGImageSourceShouldCacheImmediately: true,
                kCGImageSourceThumbnailMaxPixelSize: maxPixelSize
            ]
            guard let cg = CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary) else { return nil }
            return UIImage(cgImage: cg)
        }.value

        if let img {
            cache.setObject(img, forKey: key)
        }
        return img
    }

    /// Full-resolution load for the photo viewer.
    static func loadFull(url: URL) async -> UIImage? {
        await Task.detached(priority: .userInitiated) { () -> UIImage? in
            guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
                  let cg = CGImageSourceCreateImageAtIndex(src, 0, [
                      kCGImageSourceShouldCacheImmediately: true,
                      kCGImageSourceCreateThumbnailWithTransform: true
                  ] as CFDictionary)
            else { return nil }
            return UIImage(cgImage: cg)
        }.value
    }
}
