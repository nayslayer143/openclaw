import SwiftData
import Foundation

@Model
final class PhotoReference {
    @Attribute(.unique) var id: String
    var folderId: String
    var orderIndex: Int

    var folder: Folder?

    init(assetIdentifier: String, folderId: String, orderIndex: Int) {
        self.id = assetIdentifier
        self.folderId = folderId
        self.orderIndex = orderIndex
    }
}