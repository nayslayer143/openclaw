import SwiftData
import Foundation

@Model
final class Folder {
    @Attribute(.unique) var id: String
    var name: String
    var parentId: String?
    var createdAt: Date
    var order: Int

    @Relationship(deleteRule: .cascade, inverse: \PhotoReference.folder)
    var photoReferences: [PhotoReference] = []

    init(name: String, parentId: String? = nil, order: Int = 0) {
        self.id = UUID().uuidString
        self.name = name
        self.parentId = parentId
        self.createdAt = Date()
        self.order = order
    }
}