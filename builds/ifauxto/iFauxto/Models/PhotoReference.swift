import SwiftData
import Foundation

@Model
final class PhotoReference {
    // CloudKit requires all non-optional properties to have default values
    @Attribute(.unique) var id: String = ""
    var folderId: String = ""
    var orderIndex: Int = 0

    var folder: Folder?

    init(assetIdentifier: String, folderId: String, orderIndex: Int) {
        self.id = assetIdentifier
        self.folderId = folderId
        self.orderIndex = orderIndex
    }
}