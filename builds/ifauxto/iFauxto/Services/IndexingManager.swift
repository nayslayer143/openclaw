import Photos
import UIKit
import Combine

// Assume TagStore, TagRecord, and VisionTaggingService are defined and accessible in scope.

@MainActor
final class IndexingManager: ObservableObject {
    
    // MARK: - Published Properties
    @Published private(set) var isIndexing: Bool = false
    @Published private(set) var indexedCount: Int = 0
    @Published private(set) var totalCount: Int = 0
    
    // MARK: - Private State
    private let tagStore: TagStore
    private let taggingService: VisionTaggingService
    private var indexingTask: Task<Void, Never>?
    
    /// Computed property for tracking progress.
    var progress: Double {
        guard totalCount > 0 else { return 0.0 }
        return Double(indexedCount) / Double(totalCount)
    }
    
    // MARK: - Initialization
    init(tagStore: TagStore) {
        self.tagStore = tagStore
        // Initialize VisionTaggingService as per requirements
        self.taggingService = VisionTaggingService()
    }
    
    // MARK: - Public API
    
    /// Starts the background photo indexing process if not already running.
    func startBackgroundIndexing() {
        guard indexingTask == nil else {
            print("Indexing is already running.")
            return
        }
        
        print("Starting background photo indexing...")
        // Use Task.detached to run in the background with utility priority
        indexingTask = Task.detached(priority: .utility) { [weak self] in
            await self?.runIndexing()
        }
    }
    
    /// Cancels the ongoing indexing task.
    func stopIndexing() {
        indexingTask?.cancel()
        indexingTask = nil
        print("Indexing process cancelled.")
    }
    
    // MARK: - Core Logic
    
    private func runIndexing() async {
        // 1. Set isIndexing = true on MainActor
        await MainActor.run {
            self.isIndexing = true
            self.indexedCount = 0
            self.totalCount = 0
        }
        
        // 2. Fetch all PHAssets
        let fetchOptions = PHFetchOptions()
        // Sort by creationDate descending
        fetchOptions.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        
        let assets = PHAsset.fetchAssets(with: .image, options: fetchOptions)
        guard let firstAsset = assets.allObjects.first else {
            print("No assets found to index.")
            await MainActor.run {
                self.isIndexing = false
            }
            return
        }
        
        let allAssets = assets.allObjects
        
        // 3. Set totalCount on MainActor
        await MainActor.run {
            self.totalCount = allAssets.count
        }
        
        // 4. Loop through assets
        for (index, asset) in allAssets.enumerated() {
            // Check for cancellation before processing
            guard !Task.isCancelled else {
                print("Indexing task was cancelled.")
                break
            }
            
            // Skip if already tagged
            guard !tagStore.isIndexed(asset: asset) else {
                continue
            }
            
            do {
                // Load image and tag
                guard let cgImage = await loadImageForAnalysis(asset: asset) else {
                    print("Skipping asset \(index) due to image loading failure.")
                    continue
                }
                
                // Tag photo
                let tags = await taggingService.tagPhoto(cgImage: cgImage)
                
                // Metadata tags
                var metadata: [TagRecord] = [
                    .location(string: ""),
                    .timeOfDay(string: "")
                ]
                
                // Add metadata tags
                metadata.append(contentsOf: metadataTags(for: asset))
                
                // Store tags
                try tagStore.insertTags(asset: asset, tags: metadata)
                
                // Update count on MainActor
                await MainActor.run {
                    self.indexedCount += 1
                }
            } catch {
                print("Error processing asset \(index): \(error.localizedDescription)")
            }
            
            // 5. Every 20 photos: sleep
            if (index + 1) % 20 == 0 {
                do {
                    try await Task.sleep(nanoseconds: 50_000_000)
                } catch {
                    // Task cancelled during sleep
                    break
                }
            }
        }
        
        // 7. Set isIndexing = false on MainActor when done
        await MainActor.run {
            self.isIndexing = false
            print("Background photo indexing finished.")
        }
    }
    
    // MARK: - Helpers
    
    /// Loads a CGImage representation of the asset thumbnail.
    private func loadImageForAnalysis(asset: PHAsset) async -> CGImage? {
        return await withCheckedContinuation { continuation in
            PHImageManager.default().requestImage(
                for: asset,
                targetSize: CGSize(width: 640, height: 640),
                contentMode: .aspectFill,
                options: [PHImageOptionsKey.deliveryMode: .fastFormat,
                          PHImageOptionsKey.isNetworkAccessAllowed: false]
            ) { (image, _, error) in
                if let image = image {
                    let cgImage = image.cgImage
                    continuation.resume(returning: cgImage)
                } else {
                    continuation.resume(returning: nil)
                }
            }
        }
    }
    
    /// Generates tags based on time, location, and screenshot detection.
    private func metadataTags(for asset: PHAsset) -> [TagRecord] {
        let creationDate = asset.creationDate?
        var records: [TagRecord] = []
        
        // 1. Time of day detection
        var timeOfDayString = "Night"
        if let date = creationDate {
            let calendar = Calendar.current
            let hour = calendar.component(.hour, from: date)
            
            if (5...11).contains(hour) { // 5 AM to 11:59 AM
                timeOfDayString = "Morning"
            } else if (12...16).contains(hour) { // 12 PM to 4:59 PM
                timeOfDayString = "Afternoon"
            } else if (17...20).contains(hour) { // 5 PM to 8:59 PM
                timeOfDayString = "Evening"
            }
        }
        records.append(.timeOfDay(string: timeOfDayString))
        
        // 2. Location
        let location = asset.location
        if let lat = location.latitude, let lon = location.longitude {
            records.append(.location(string: "\(lat), \(lon)"))
        }
        
        // 3. Screenshot detection
        if asset.mediaSubtypes.contains(.photoScreenshot) {
            records.append(.screenshot(string: "Detected"))
        }
        
        return records
    }
}