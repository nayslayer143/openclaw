import Foundation

/// Hashable nav payload for opening one of the built-in smart albums.
enum SmartAlbumRoute: Hashable {
    case events
    case places
    case faces
    case projects
    case smartList(id: String, title: String)
}
