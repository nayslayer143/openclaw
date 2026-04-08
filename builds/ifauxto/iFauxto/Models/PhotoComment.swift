import SwiftData
import Foundation

/// A single comment on a photo. Multi-user-ready: each comment carries
/// the author's id and display name so a future server-synced version
/// can show full threads with attribution. For now, all comments are
/// authored by the local user.
@Model
final class PhotoComment {
    @Attribute(.unique) var id: String = UUID().uuidString
    var assetIdentifier: String = ""
    var body: String = ""
    var authorId: String = ""
    var authorName: String = ""
    var createdAt: Date = Date()

    init(assetIdentifier: String, body: String, authorId: String, authorName: String) {
        self.id = UUID().uuidString
        self.assetIdentifier = assetIdentifier
        self.body = body
        self.authorId = authorId
        self.authorName = authorName
        self.createdAt = Date()
    }
}
