import SwiftData
import Foundation

/// User-controlled metadata for a single photo asset.
/// Separate from `PhotoReference` (which is the album/order join) so a
/// favorite or rating sticks to the photo regardless of how many albums
/// it lives in. Keyed uniquely by the PHAsset localIdentifier.
@Model
final class PhotoMeta {
    @Attribute(.unique) var assetIdentifier: String = ""
    var isFavorite: Bool = false
    var rating: Int = 0          // 0..5
    var isHidden: Bool = false
    /// Soft-delete timestamp. Photos are auto-purged 30 days after this.
    var trashedAt: Date?
    var title: String = ""
    var caption: String = ""
    var createdAt: Date = Date()
    var updatedAt: Date = Date()

    var isTrashed: Bool { trashedAt != nil }

    init(assetIdentifier: String) {
        self.assetIdentifier = assetIdentifier
        self.createdAt = Date()
        self.updatedAt = Date()
    }
}
