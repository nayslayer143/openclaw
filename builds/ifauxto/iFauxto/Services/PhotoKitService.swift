import Photos
import UIKit
import SwiftUI

@MainActor
final class PhotoKitService: ObservableObject {
    @Published var authorizationStatus: PHAuthorizationStatus = PHPhotoLibrary.authorizationStatus(for: .readWrite)

    // MARK: Authorization

    func requestAuthorization() async {
        let status = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
        authorizationStatus = status
    }

    var isAuthorized: Bool {
        authorizationStatus == .authorized || authorizationStatus == .limited
    }

    // MARK: Asset Fetching

    func fetchAsset(withIdentifier identifier: String) -> PHAsset? {
        let result = PHAsset.fetchAssets(withLocalIdentifiers: [identifier], options: nil)
        return result.firstObject
    }

    /// Returns a UIImage thumbnail for a given PHAsset identifier, with caching.
    func loadThumbnail(for identifier: String, targetSize: CGSize = CGSize(width: 200, height: 200)) async -> UIImage? {
        let cacheKey = "\(identifier)_\(Int(targetSize.width))x\(Int(targetSize.height))"

        if let cached = ThumbnailCache.shared.get(key: cacheKey) {
            return cached
        }

        guard let asset = fetchAsset(withIdentifier: identifier) else { return nil }
        let image = await withCheckedContinuation { continuation in
            let options = PHImageRequestOptions()
            options.deliveryMode = .highQualityFormat
            options.resizeMode = .fast
            options.isNetworkAccessAllowed = true
            options.isSynchronous = false
            PHImageManager.default().requestImage(
                for: asset,
                targetSize: targetSize,
                contentMode: .aspectFill,
                options: options
            ) { image, _ in
                continuation.resume(returning: image)
            }
        }

        if let image {
            ThumbnailCache.shared.set(key: cacheKey, image: image)
        }

        return image
    }

    /// Returns a full-resolution UIImage for a given PHAsset identifier.
    func loadFullImage(for identifier: String) async -> UIImage? {
        guard let asset = fetchAsset(withIdentifier: identifier) else { return nil }
        return await withCheckedContinuation { continuation in
            let options = PHImageRequestOptions()
            options.deliveryMode = .highQualityFormat
            options.isNetworkAccessAllowed = true
            options.isSynchronous = false
            PHImageManager.default().requestImage(
                for: asset,
                targetSize: PHImageManagerMaximumSize,
                contentMode: .aspectFit,
                options: options
            ) { image, _ in
                continuation.resume(returning: image)
            }
        }
    }

    /// Returns true if the asset is a video.
    func isVideo(identifier: String) -> Bool {
        guard let asset = fetchAsset(withIdentifier: identifier) else { return false }
        return asset.mediaType == .video
    }

    /// Loads an AVPlayerItem for a video asset, async/await wrapped.
    func loadPlayerItem(for identifier: String) async -> AVPlayerItem? {
        guard let asset = fetchAsset(withIdentifier: identifier),
              asset.mediaType == .video else { return nil }
        return await withCheckedContinuation { continuation in
            let options = PHVideoRequestOptions()
            options.deliveryMode = .automatic
            options.isNetworkAccessAllowed = true
            PHImageManager.default().requestPlayerItem(
                forVideo: asset,
                options: options
            ) { item, _ in
                continuation.resume(returning: item)
            }
        }
    }

    /// Fetches all PHAsset identifiers from the user's library (for the photo picker flow).
    /// Includes both images and videos.
    func fetchAllAssetIdentifiers() -> [String] {
        let fetchOptions = PHFetchOptions()
        fetchOptions.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        // .image OR .video — leave mediaType filter off to include both.
        let result = PHAsset.fetchAssets(with: fetchOptions)
        var identifiers: [String] = []
        result.enumerateObjects { asset, _, _ in
            if asset.mediaType == .image || asset.mediaType == .video {
                identifiers.append(asset.localIdentifier)
            }
        }
        return identifiers
    }
}
