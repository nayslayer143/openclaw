import Photos
import UIKit

@MainActor
final class IndexingManager: ObservableObject {
    @Published var isIndexing = false
    @Published var indexedCount = 0
    @Published var totalCount = 0

    private let tagStore: TagStore
    private let taggingService = VisionTaggingService()
    private var indexingTask: Task<Void, Never>?

    init(tagStore: TagStore) {
        self.tagStore = tagStore
    }

    var progress: Double {
        guard totalCount > 0 else { return 0 }
        return Double(indexedCount) / Double(totalCount)
    }

    func startBackgroundIndexing() {
        guard indexingTask == nil else { return }
        indexingTask = Task.detached(priority: .utility) { [weak self] in
            await self?.runIndexing()
        }
    }

    func stopIndexing() {
        indexingTask?.cancel()
        indexingTask = nil
    }

    private func runIndexing() async {
        await MainActor.run { isIndexing = true }

        let fetchOptions = PHFetchOptions()
        fetchOptions.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        let assets = PHAsset.fetchAssets(with: .image, options: fetchOptions)

        await MainActor.run { totalCount = assets.count }

        let batchSize = 20
        var processed = 0

        for i in 0..<assets.count {
            guard !Task.isCancelled else { break }

            let asset = assets.object(at: i)
            let assetId = asset.localIdentifier

            if (try? tagStore.isIndexed(assetId: assetId)) == true {
                processed += 1
                await MainActor.run { indexedCount = processed }
                continue
            }

            guard let image = await loadImageForAnalysis(asset: asset) else {
                processed += 1
                await MainActor.run { indexedCount = processed }
                continue
            }

            let photoTags = await taggingService.tagPhoto(image: image, assetId: assetId)

            var allTags = photoTags.tags
            allTags.append(contentsOf: metadataTags(for: asset))

            try? tagStore.insertTags(assetId: assetId, tags: allTags)

            processed += 1
            await MainActor.run { indexedCount = processed }

            if processed % batchSize == 0 {
                if ProcessInfo.processInfo.isLowPowerModeEnabled {
                    try? await Task.sleep(nanoseconds: 500_000_000)
                } else {
                    try? await Task.sleep(nanoseconds: 50_000_000)
                }
            }
        }

        await MainActor.run {
            isIndexing = false
            indexingTask = nil
        }
    }

    private func loadImageForAnalysis(asset: PHAsset) async -> CGImage? {
        await withCheckedContinuation { continuation in
            let options = PHImageRequestOptions()
            options.deliveryMode = .fastFormat
            options.resizeMode = .fast
            options.isSynchronous = false
            options.isNetworkAccessAllowed = false
            PHImageManager.default().requestImage(
                for: asset,
                targetSize: CGSize(width: 640, height: 640),
                contentMode: .aspectFit,
                options: options
            ) { image, _ in
                continuation.resume(returning: image?.cgImage)
            }
        }
    }

    private func metadataTags(for asset: PHAsset) -> [TagRecord] {
        var tags: [TagRecord] = []

        if let date = asset.creationDate {
            let hour = Calendar.current.component(.hour, from: date)
            let timeOfDay: String
            switch hour {
            case 5..<12: timeOfDay = "morning"
            case 12..<17: timeOfDay = "afternoon"
            case 17..<21: timeOfDay = "evening"
            default: timeOfDay = "night"
            }
            tags.append(TagRecord(tagType: "time", tagValue: timeOfDay, confidence: 1.0))
        }

        if let location = asset.location {
            tags.append(TagRecord(
                tagType: "location",
                tagValue: "lat:\(location.coordinate.latitude) lon:\(location.coordinate.longitude)",
                confidence: 1.0
            ))
        }

        if asset.mediaSubtypes.contains(.photoScreenshot) {
            tags.append(TagRecord(tagType: "object", tagValue: "screenshot", confidence: 1.0))
        }

        return tags
    }
}
