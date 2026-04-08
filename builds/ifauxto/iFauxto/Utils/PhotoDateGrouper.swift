import Foundation
import Photos

/// Buckets a flat list of asset identifiers into date-keyed groups so the
/// chronological feed can show sticky headers ("Today", "Yesterday",
/// "This Week", "March 2026", etc.) — iPhoto's "Events" primitive.
struct PhotoDateGroup: Identifiable {
    let id: String           // header text used as id
    let title: String
    let identifiers: [String]
}

enum PhotoDateGrouper {

    /// Returns groups newest-first. For demo identifiers we synthesize a
    /// stable date from the identifier hash. For real PHAsset identifiers
    /// we read `asset.creationDate`.
    static func group(_ identifiers: [String]) -> [PhotoDateGroup] {
        // Build (date, id) pairs.
        let now = Date()
        let cal = Calendar.current
        let todayStart = cal.startOfDay(for: now)
        let yesterdayStart = cal.date(byAdding: .day, value: -1, to: todayStart) ?? todayStart
        let weekStart = cal.date(byAdding: .day, value: -7, to: todayStart) ?? todayStart
        let monthStart = cal.date(byAdding: .day, value: -30, to: todayStart) ?? todayStart

        // Header formatter for older dates.
        let monthYear: DateFormatter = {
            let f = DateFormatter()
            f.dateFormat = "MMMM yyyy"
            return f
        }()

        // Resolve dates (real assets in batch where possible).
        let realIds = identifiers.filter { !$0.hasPrefix("demo:") }
        let realDates: [String: Date] = {
            guard !realIds.isEmpty else { return [:] }
            let result = PHAsset.fetchAssets(withLocalIdentifiers: realIds, options: nil)
            var map: [String: Date] = [:]
            result.enumerateObjects { asset, _, _ in
                if let d = asset.creationDate {
                    map[asset.localIdentifier] = d
                }
            }
            return map
        }()

        var dated: [(String, Date)] = identifiers.map { id in
            if id.hasPrefix("demo:") {
                return (id, syntheticDate(for: id, anchor: now))
            } else {
                return (id, realDates[id] ?? now)
            }
        }
        // Newest first.
        dated.sort { $0.1 > $1.1 }

        // Bucket.
        struct Bucket {
            var title: String
            var ids: [String] = []
        }
        var ordered: [Bucket] = []
        var indexByTitle: [String: Int] = [:]

        func bucketTitle(for date: Date) -> String {
            if date >= todayStart { return "Today" }
            if date >= yesterdayStart { return "Yesterday" }
            if date >= weekStart { return "This Week" }
            if date >= monthStart { return "Earlier This Month" }
            return monthYear.string(from: date)
        }

        for (id, date) in dated {
            let title = bucketTitle(for: date)
            if let idx = indexByTitle[title] {
                ordered[idx].ids.append(id)
            } else {
                indexByTitle[title] = ordered.count
                ordered.append(Bucket(title: title, ids: [id]))
            }
        }

        return ordered.map { PhotoDateGroup(id: $0.title, title: $0.title, identifiers: $0.ids) }
    }

    /// Stable synthetic date for "demo:" identifiers — same hash math as
    /// PhotoMetadataLoader so the info sheet and the bucket header agree.
    private static func syntheticDate(for identifier: String, anchor: Date) -> Date {
        var h: UInt64 = 1469598103934665603
        for byte in identifier.utf8 {
            h ^= UInt64(byte)
            h &*= 1099511628211
        }
        let daysAgo = Int(h % 720)
        return Calendar.current.date(byAdding: .day, value: -daysAgo, to: anchor) ?? anchor
    }
}
