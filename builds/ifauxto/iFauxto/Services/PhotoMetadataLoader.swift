import Photos
import ImageIO
import CoreLocation
import UIKit

struct PhotoMetadata {
    let assetId: String
    let dimensions: String?
    let fileSize: String?
    let mediaType: String?
    let captureDate: String?
    let modifiedDate: String?
    let camera: String?
    let lens: String?
    let aperture: String?
    let shutterSpeed: String?
    let iso: String?
    let focalLength: String?
    let coordinates: String?
    let altitude: String?

    var hasCamera: Bool {
        camera != nil || lens != nil || aperture != nil || shutterSpeed != nil || iso != nil
    }
    var hasLocation: Bool {
        coordinates != nil
    }
}

enum PhotoMetadataLoader {

    /// Loads metadata for a PHAsset identifier. For "demo:" identifiers
    /// returns a deterministic synthesized record so the info sheet can
    /// be exercised without real PhotoKit data.
    static func load(identifier: String) async -> PhotoMetadata? {
        if identifier.hasPrefix("demo:") {
            return synthesizedDemo(for: identifier)
        }
        return await loadReal(identifier: identifier)
    }

    // MARK: - Real PHAsset path

    private static func loadReal(identifier: String) async -> PhotoMetadata? {
        let result = PHAsset.fetchAssets(withLocalIdentifiers: [identifier], options: nil)
        guard let asset = result.firstObject else { return nil }

        // Basic asset-level info
        let dimensions = "\(asset.pixelWidth) × \(asset.pixelHeight)"
        let captureDate = asset.creationDate.map { fullDateString(from: $0) }
        let modifiedDate = asset.modificationDate.map { fullDateString(from: $0) }
        let mediaType: String = {
            switch asset.mediaType {
            case .image: return "Image"
            case .video: return "Video"
            case .audio: return "Audio"
            default: return "Unknown"
            }
        }()

        // Location
        var coordinates: String?
        var altitude: String?
        if let loc = asset.location {
            coordinates = String(format: "%.5f, %.5f", loc.coordinate.latitude, loc.coordinate.longitude)
            altitude = String(format: "%.0f m", loc.altitude)
        }

        // EXIF and file size require fetching the image data
        let exif = await fetchExif(for: asset)
        let fileSize = await fetchFileSize(for: asset)

        return PhotoMetadata(
            assetId: identifier,
            dimensions: dimensions,
            fileSize: fileSize,
            mediaType: mediaType,
            captureDate: captureDate,
            modifiedDate: modifiedDate,
            camera: exif.camera,
            lens: exif.lens,
            aperture: exif.aperture,
            shutterSpeed: exif.shutterSpeed,
            iso: exif.iso,
            focalLength: exif.focalLength,
            coordinates: coordinates,
            altitude: altitude
        )
    }

    private struct ExifInfo {
        var camera: String?
        var lens: String?
        var aperture: String?
        var shutterSpeed: String?
        var iso: String?
        var focalLength: String?
    }

    private static func fetchExif(for asset: PHAsset) async -> ExifInfo {
        await withCheckedContinuation { (continuation: CheckedContinuation<ExifInfo, Never>) in
            let options = PHContentEditingInputRequestOptions()
            options.isNetworkAccessAllowed = false
            asset.requestContentEditingInput(with: options) { input, _ in
                guard let url = input?.fullSizeImageURL,
                      let source = CGImageSourceCreateWithURL(url as CFURL, nil),
                      let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [String: Any]
                else {
                    continuation.resume(returning: ExifInfo())
                    return
                }
                var info = ExifInfo()
                if let tiff = props[kCGImagePropertyTIFFDictionary as String] as? [String: Any] {
                    let make = tiff[kCGImagePropertyTIFFMake as String] as? String
                    let model = tiff[kCGImagePropertyTIFFModel as String] as? String
                    info.camera = [make, model].compactMap { $0 }.joined(separator: " ")
                    if info.camera?.isEmpty == true { info.camera = nil }
                }
                if let exif = props[kCGImagePropertyExifDictionary as String] as? [String: Any] {
                    if let f = exif[kCGImagePropertyExifFNumber as String] as? Double {
                        info.aperture = String(format: "ƒ/%.1f", f)
                    }
                    if let s = exif[kCGImagePropertyExifExposureTime as String] as? Double {
                        if s >= 1 {
                            info.shutterSpeed = String(format: "%.1fs", s)
                        } else {
                            info.shutterSpeed = "1/\(Int(round(1.0 / s)))s"
                        }
                    }
                    if let isoArray = exif[kCGImagePropertyExifISOSpeedRatings as String] as? [Int],
                       let iso = isoArray.first {
                        info.iso = "ISO \(iso)"
                    }
                    if let fl = exif[kCGImagePropertyExifFocalLength as String] as? Double {
                        info.focalLength = String(format: "%.0f mm", fl)
                    }
                    if let lens = exif[kCGImagePropertyExifLensModel as String] as? String {
                        info.lens = lens
                    }
                }
                continuation.resume(returning: info)
            }
        }
    }

    private static func fetchFileSize(for asset: PHAsset) async -> String? {
        await withCheckedContinuation { (continuation: CheckedContinuation<String?, Never>) in
            let resources = PHAssetResource.assetResources(for: asset)
            guard let resource = resources.first else {
                continuation.resume(returning: nil)
                return
            }
            // PHAssetResource has an undocumented "fileSize" key.
            if let bytes = resource.value(forKey: "fileSize") as? Int64 {
                continuation.resume(returning: humanBytes(bytes))
                return
            }
            continuation.resume(returning: nil)
        }
    }

    // MARK: - Demo synthesizer

    private static func synthesizedDemo(for identifier: String) -> PhotoMetadata {
        // Stable values from the identifier so each photo "feels real" but
        // doesn't change between launches.
        let h = abs(identifier.hashValue)
        let widths = [3024, 4032, 4000, 3840, 5712, 1920, 2048, 2560]
        let heights = [4032, 3024, 3000, 2160, 4284, 1080, 1536, 1440]
        let cameras = [
            "Apple iPhone 16 Pro",
            "Apple iPhone 15 Pro Max",
            "Sony α7 IV",
            "FUJIFILM X-T5",
            "Canon EOS R6",
            "Apple iPhone 14"
        ]
        let lenses = [
            "iPhone 16 Pro back camera 6.86mm ƒ/1.78",
            "FE 24-70mm F2.8 GM II",
            "XF 23mm F1.4 R LM WR",
            "RF 50mm F1.2 L USM",
            "iPhone 15 Pro Max back triple camera"
        ]
        let apertures = ["ƒ/1.4", "ƒ/1.8", "ƒ/2.0", "ƒ/2.8", "ƒ/4.0", "ƒ/5.6"]
        let shutters = ["1/2000s", "1/1000s", "1/500s", "1/250s", "1/125s", "1/60s", "1/30s"]
        let isos = ["ISO 50", "ISO 100", "ISO 200", "ISO 400", "ISO 800", "ISO 1600"]
        let focals = ["24 mm", "35 mm", "50 mm", "85 mm", "135 mm", "6.86 mm"]
        let sizes: [Int64] = [1_240_000, 2_780_000, 3_410_000, 4_900_000, 6_120_000, 8_540_000]

        let w = widths[h % widths.count]
        let ht = heights[(h / 7) % heights.count]
        let cam = cameras[(h / 13) % cameras.count]
        let lens = lenses[(h / 17) % lenses.count]
        let ap = apertures[(h / 19) % apertures.count]
        let sh = shutters[(h / 23) % shutters.count]
        let iso = isos[(h / 29) % isos.count]
        let focal = focals[(h / 31) % focals.count]
        let size = sizes[(h / 37) % sizes.count]

        // Stable date in 2025/2026 driven by the hash
        let daysAgo = (h % 720)  // up to ~2 years
        let date = Calendar.current.date(byAdding: .day, value: -daysAgo, to: Date()) ?? Date()

        // Random-ish coordinates clustered around a few familiar cities
        let cities: [(String, Double, Double)] = [
            ("San Francisco", 37.7749, -122.4194),
            ("Tokyo", 35.6762, 139.6503),
            ("Reykjavík", 64.1466, -21.9426),
            ("Lisbon", 38.7223, -9.1393),
            ("Mexico City", 19.4326, -99.1332)
        ]
        let city = cities[(h / 41) % cities.count]
        let jitterLat = Double((h % 200) - 100) / 1000.0
        let jitterLon = Double(((h / 3) % 200) - 100) / 1000.0
        let coords = String(format: "%.5f, %.5f", city.1 + jitterLat, city.2 + jitterLon)
        let altitude = "\((h / 53) % 1200) m"

        return PhotoMetadata(
            assetId: identifier,
            dimensions: "\(w) × \(ht)",
            fileSize: humanBytes(size),
            mediaType: "Image",
            captureDate: fullDateString(from: date),
            modifiedDate: fullDateString(from: date),
            camera: cam,
            lens: lens,
            aperture: ap,
            shutterSpeed: sh,
            iso: iso,
            focalLength: focal,
            coordinates: coords + "  · " + city.0,
            altitude: altitude
        )
    }

    // MARK: - Formatting

    private static let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .medium
        f.timeStyle = .short
        return f
    }()

    private static func fullDateString(from date: Date) -> String {
        dateFormatter.string(from: date)
    }

    private static func humanBytes(_ bytes: Int64) -> String {
        let formatter = ByteCountFormatter()
        formatter.allowedUnits = [.useKB, .useMB, .useGB]
        formatter.countStyle = .file
        return formatter.string(fromByteCount: bytes)
    }
}
