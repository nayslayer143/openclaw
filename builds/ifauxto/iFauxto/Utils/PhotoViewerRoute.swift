import Foundation

/// Hashable nav payload for pushing the full-screen photo viewer.
/// Carries the ordered list of photo identifiers + the index to start on.
struct PhotoViewerRoute: Hashable {
    let photoIds: [String]
    let startIndex: Int
}
