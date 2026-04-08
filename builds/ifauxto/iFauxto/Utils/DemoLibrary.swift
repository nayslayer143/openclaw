import Foundation

/// Synthetic photo library for development. Returns 100 stable identifiers
/// that the chronological feed and folder grids can render via the demo
/// placeholder path in PhotoThumbnailView / FeedThumbnailView.
///
/// In a real build, photos come from PhotoKit. The demo library is a
/// deterministic stand-in so the UI can be exercised without needing
/// system photo permission or a populated camera roll.
enum DemoLibrary {

    /// Whether the synthetic library should be active. Driven by the
    /// `-seedDemoPhotos` launch argument so production builds and
    /// real-PhotoKit testing remain unaffected.
    static var isEnabled: Bool {
        ProcessInfo.processInfo.arguments.contains("-seedDemoPhotos")
    }

    /// 100 deterministic identifiers, mixed buckets so colors/icons vary
    /// but stay reproducible across launches.
    static let identifiers: [String] = {
        var out: [String] = []
        let buckets = ["travel", "family", "screens", "food", "misc"]
        for i in 0..<100 {
            let bucket = buckets[i % buckets.count]
            out.append("demo:\(bucket):\(i)")
        }
        return out
    }()
}
