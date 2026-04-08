import SwiftData
import Foundation

/// User-defined smart album. Stores a list of rules that filter the
/// photo library at query time. Each rule has a field, an operator, and
/// a value. AND-combined.
@Model
final class SmartAlbum {
    @Attribute(.unique) var id: String = UUID().uuidString
    var name: String = ""
    var rulesData: Data = Data()
    var createdAt: Date = Date()

    var rules: [SmartRule] {
        get {
            (try? JSONDecoder().decode([SmartRule].self, from: rulesData)) ?? []
        }
        set {
            rulesData = (try? JSONEncoder().encode(newValue)) ?? Data()
        }
    }

    init(name: String, rules: [SmartRule]) {
        self.id = UUID().uuidString
        self.name = name
        self.createdAt = Date()
        self.rules = rules
    }
}

/// One predicate inside a SmartAlbum.
struct SmartRule: Codable, Identifiable, Equatable {
    var id: String = UUID().uuidString
    var field: Field
    var op: Op
    var value: String

    enum Field: String, Codable, CaseIterable, Identifiable {
        case favorite, rating, hidden, eventBucket
        var id: String { rawValue }
        var label: String {
            switch self {
            case .favorite:    return "Favorite"
            case .rating:      return "Rating"
            case .hidden:      return "Hidden"
            case .eventBucket: return "Event"
            }
        }
    }

    enum Op: String, Codable, CaseIterable, Identifiable {
        case isTrue, isFalse, equals, atLeast, contains
        var id: String { rawValue }
        var label: String {
            switch self {
            case .isTrue:  return "is true"
            case .isFalse: return "is false"
            case .equals:  return "equals"
            case .atLeast: return "is at least"
            case .contains: return "contains"
            }
        }
    }
}
