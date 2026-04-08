import SwiftData
import Foundation

/// User-created creative project (collage, photobook, card, calendar).
/// Holds a name, type, optional theme, ordered list of photo identifiers,
/// and a dateCreated.
@Model
final class PhotoProject {
    @Attribute(.unique) var id: String = UUID().uuidString
    var name: String = ""
    /// Stored as raw string so the enum can evolve without migration pain.
    var typeRaw: String = "collage"
    var theme: String = "Default"
    var photoIdsCSV: String = ""
    var createdAt: Date = Date()
    var updatedAt: Date = Date()

    var type: ProjectType {
        get { ProjectType(rawValue: typeRaw) ?? .collage }
        set { typeRaw = newValue.rawValue }
    }

    var photoIds: [String] {
        get {
            photoIdsCSV.isEmpty ? [] : photoIdsCSV.components(separatedBy: "\u{1F}")
        }
        set {
            photoIdsCSV = newValue.joined(separator: "\u{1F}")
        }
    }

    init(name: String, type: ProjectType, theme: String = "Default", photoIds: [String] = []) {
        self.id = UUID().uuidString
        self.name = name
        self.typeRaw = type.rawValue
        self.theme = theme
        self.createdAt = Date()
        self.updatedAt = Date()
        self.photoIdsCSV = photoIds.joined(separator: "\u{1F}")
    }
}

enum ProjectType: String, CaseIterable, Identifiable {
    case collage
    case book
    case card
    case calendar

    var id: String { rawValue }

    var label: String {
        switch self {
        case .collage:  return "Collage"
        case .book:     return "Photo Book"
        case .card:     return "Card"
        case .calendar: return "Calendar"
        }
    }

    var icon: String {
        switch self {
        case .collage:  return "square.grid.3x3.square"
        case .book:     return "book.closed.fill"
        case .card:     return "rectangle.portrait.fill"
        case .calendar: return "calendar"
        }
    }
}
