import SwiftData
import Foundation

@Model
final class Folder {
    // CloudKit requires all non-optional properties to have default values
    @Attribute(.unique) var id: String = UUID().uuidString
    var name: String = ""
    var parentId: String?
    var createdAt: Date = Date()
    var order: Int = 0

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