import SwiftData
import Foundation

/// A cluster of detected faces — typically one cluster per person.
/// In demo mode this is generated synthetically. In production it's
/// populated by VisionTaggingService running over the user's library.
@Model
final class FaceCluster {
    @Attribute(.unique) var id: String = UUID().uuidString
    /// User-assigned name. Empty until the user labels the cluster.
    var displayName: String = ""
    /// Asset identifier of the cover photo for this cluster.
    var coverAssetId: String = ""
    /// Asset identifiers of all photos containing this person.
    var memberIdsCSV: String = ""
    var createdAt: Date = Date()
    var updatedAt: Date = Date()

    var memberIds: [String] {
        get {
            memberIdsCSV.isEmpty ? [] : memberIdsCSV.components(separatedBy: "\u{1F}")
        }
        set {
            memberIdsCSV = newValue.joined(separator: "\u{1F}")
        }
    }

    init(displayName: String, coverAssetId: String, memberIds: [String]) {
        self.id = UUID().uuidString
        self.displayName = displayName
        self.coverAssetId = coverAssetId
        self.memberIdsCSV = memberIds.joined(separator: "\u{1F}")
    }
}
