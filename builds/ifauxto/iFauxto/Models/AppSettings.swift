import SwiftData
import Foundation

@Model
final class AppSettings {
    @Attribute(.unique) var id: String = "singleton"
    var homeViewMode: String = "folder_list"  // "folder_list" | "chronological_feed" | "last_opened" | "custom_view"
    var lastOpenedViewId: String?
    var pinnedViewId: String?
    var hasCompletedOnboarding: Bool = false
    /// Sort mode for the root folder list. "custom" | "alpha" | "date" | "recent"
    var rootFolderSortMode: String = "custom"

    init() {
        self.id = "singleton"
    }
}
