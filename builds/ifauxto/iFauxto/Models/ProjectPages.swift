import Foundation

// MARK: - Photobook

struct BookPage: Codable, Identifiable, Equatable {
    var id: String = UUID().uuidString
    var template: BookTemplate = .fullBleed
    /// One asset identifier per slot. Count matches `template.slotCount`.
    var slots: [String?] = []
    var caption: String = ""
    var isCover: Bool = false

    static func cover() -> BookPage {
        BookPage(template: .cover, slots: [nil], isCover: true)
    }

    static func blank(template: BookTemplate) -> BookPage {
        BookPage(template: template, slots: Array(repeating: nil, count: template.slotCount))
    }
}

enum BookTemplate: String, Codable, CaseIterable, Identifiable {
    case cover          // Single large photo + title overlay
    case fullBleed      // Single edge-to-edge photo
    case twoUp          // Two stacked photos + caption
    case threeUp        // Three-photo mosaic
    case textPage       // Pure caption / dedication, no photos
    case mixed4         // 4-photo grid

    var id: String { rawValue }
    var label: String {
        switch self {
        case .cover:     return "Cover"
        case .fullBleed: return "Full Bleed"
        case .twoUp:     return "Two-Up"
        case .threeUp:   return "Three-Up"
        case .textPage:  return "Text"
        case .mixed4:    return "Grid"
        }
    }
    var slotCount: Int {
        switch self {
        case .cover, .fullBleed: return 1
        case .twoUp:             return 2
        case .threeUp:           return 3
        case .textPage:          return 0
        case .mixed4:            return 4
        }
    }
    var icon: String {
        switch self {
        case .cover:     return "book.closed.fill"
        case .fullBleed: return "rectangle.fill"
        case .twoUp:     return "rectangle.split.1x2"
        case .threeUp:   return "rectangle.split.3x1"
        case .textPage:  return "text.alignleft"
        case .mixed4:    return "square.grid.2x2"
        }
    }
}

enum BookTheme: String, Codable, CaseIterable, Identifiable {
    case classic, travel, wedding, baby, yearInReview, modern
    var id: String { rawValue }
    var label: String {
        switch self {
        case .classic:      return "Classic"
        case .travel:       return "Travel"
        case .wedding:      return "Wedding"
        case .baby:         return "Baby"
        case .yearInReview: return "Year in Review"
        case .modern:       return "Modern"
        }
    }
}

// MARK: - Calendar

struct CalendarPage: Codable, Identifiable, Equatable {
    var id: String = UUID().uuidString
    var month: Int = 1       // 1..12
    var year: Int = Calendar.current.component(.year, from: Date())
    /// Hero photo for the top half of the page.
    var heroId: String?
    /// Day number (1..31) → asset identifier for optional per-day photos.
    var dayPhotos: [Int: String] = [:]

    func monthName() -> String {
        let fmt = DateFormatter()
        fmt.dateFormat = "MMMM"
        var comps = DateComponents()
        comps.month = month
        comps.year = year
        if let date = Calendar.current.date(from: comps) {
            return fmt.string(from: date)
        }
        return "Month \(month)"
    }

    func daysInMonth() -> Int {
        var comps = DateComponents()
        comps.year = year
        comps.month = month
        if let date = Calendar.current.date(from: comps),
           let range = Calendar.current.range(of: .day, in: .month, for: date) {
            return range.count
        }
        return 30
    }

    /// Weekday index (0 = Sun) for the 1st of the month.
    func firstWeekday() -> Int {
        var comps = DateComponents()
        comps.year = year
        comps.month = month
        comps.day = 1
        if let date = Calendar.current.date(from: comps) {
            return Calendar.current.component(.weekday, from: date) - 1
        }
        return 0
    }
}

// MARK: - Card

struct CardContent: Codable, Equatable {
    var heroId: String?
    var headline: String = ""
    var insideBody: String = ""
    var recipientName: String = ""
    var recipientAddress: String = ""
    var cardStyleRaw: String = "folded5x7"

    var cardStyle: CardStyle {
        get { CardStyle(rawValue: cardStyleRaw) ?? .folded5x7 }
        set { cardStyleRaw = newValue.rawValue }
    }
}

enum CardStyle: String, Codable, CaseIterable, Identifiable {
    case folded5x7
    case flat4x6
    case postcard

    var id: String { rawValue }
    var label: String {
        switch self {
        case .folded5x7: return "Folded 5×7"
        case .flat4x6:   return "Flat 4×6"
        case .postcard:  return "Postcard"
        }
    }
    var aspect: CGSize {
        switch self {
        case .folded5x7: return CGSize(width: 5, height: 7)
        case .flat4x6:   return CGSize(width: 4, height: 6)
        case .postcard:  return CGSize(width: 6, height: 4)
        }
    }
    var hasInside: Bool {
        self == .folded5x7
    }
}
