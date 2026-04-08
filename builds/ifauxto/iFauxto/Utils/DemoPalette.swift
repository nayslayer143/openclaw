import SwiftUI

/// Deterministic placeholder rendering for synthetic "demo:" identifiers.
/// Each id maps to a stable color, icon, and short label so the test
/// dataset feels visually varied while staying reproducible.
enum DemoPalette {

    static let colors: [Color] = [
        Color(red: 0.84, green: 0.86, blue: 0.91),  // periwinkle
        Color(red: 0.95, green: 0.85, blue: 0.71),  // peach
        Color(red: 0.74, green: 0.86, blue: 0.78),  // sage
        Color(red: 0.92, green: 0.79, blue: 0.84),  // rose
        Color(red: 0.78, green: 0.83, blue: 0.92),  // sky
        Color(red: 0.89, green: 0.91, blue: 0.74),  // butter
        Color(red: 0.95, green: 0.81, blue: 0.67),  // apricot
        Color(red: 0.81, green: 0.78, blue: 0.92),  // lavender
        Color(red: 0.72, green: 0.84, blue: 0.85),  // seafoam
        Color(red: 0.93, green: 0.75, blue: 0.78),  // coral
        Color(red: 0.85, green: 0.91, blue: 0.84),  // mint
        Color(red: 0.87, green: 0.83, blue: 0.78)   // sand
    ]

    static let icons: [String] = [
        "photo", "camera", "mountain.2", "sun.max", "moon.stars",
        "leaf", "fork.knife", "person.2", "house", "car",
        "airplane", "pawprint"
    ]

    private static func bucket(_ id: String, mod: Int) -> Int {
        // FNV-1a-ish stable hash on the suffix so the same id always maps
        // to the same color/icon. Avoid Swift's randomized hashValue.
        var h: UInt64 = 1469598103934665603
        for byte in id.utf8 {
            h ^= UInt64(byte)
            h &*= 1099511628211
        }
        return Int(h % UInt64(mod))
    }

    static func color(for id: String) -> Color {
        colors[bucket(id, mod: colors.count)]
    }

    static func icon(for id: String) -> String {
        icons[bucket(id, mod: icons.count)]
    }

    /// "T-12", "F-3", etc. Useful for the user to visually distinguish
    /// individual photos when reordering or moving across albums.
    static func label(for id: String) -> String {
        // id format: "demo:<bucket>:<index>" or "demo:sub:<name>:<index>"
        let parts = id.split(separator: ":", omittingEmptySubsequences: true).map(String.init)
        guard parts.count >= 2 else { return "—" }
        let bucket = parts[1]
        let index = parts.last ?? "0"
        let prefix: String = {
            switch bucket {
            case "travel":  return "T"
            case "family":  return "F"
            case "screens": return "S"
            case "food":    return "B" // bites
            case "misc":    return "M"
            case "sub":     return parts.count >= 4 ? String(parts[2].prefix(1)).uppercased() : "•"
            default:        return "•"
            }
        }()
        return "\(prefix)\(index)"
    }
}
