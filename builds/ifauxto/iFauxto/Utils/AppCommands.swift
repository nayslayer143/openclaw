import SwiftUI

/// macOS / Catalyst menu bar commands. On iPhone/iPad these become
/// keyboard shortcuts available via the hardware keyboard; on Mac they
/// populate the top-of-screen menu bar.
struct AppCommands: Commands {
    var body: some Commands {
        // Replace default New Item with "New Album" so Cmd+N makes sense here.
        CommandGroup(replacing: .newItem) {
            Button("New Album") {
                NotificationCenter.default.post(name: .iFauxtoNewAlbum, object: nil)
            }
            .keyboardShortcut("n", modifiers: .command)

            Button("New Smart Album") {
                NotificationCenter.default.post(name: .iFauxtoNewSmartAlbum, object: nil)
            }
            .keyboardShortcut("n", modifiers: [.command, .shift])

            Button("Import from Files…") {
                NotificationCenter.default.post(name: .iFauxtoImportFiles, object: nil)
            }
            .keyboardShortcut("i", modifiers: [.command, .shift])
        }

        // Photo menu — unique to iFauxto.
        CommandMenu("Photo") {
            Button("Favorite") {
                NotificationCenter.default.post(name: .iFauxtoToggleFavorite, object: nil)
            }
            .keyboardShortcut(".", modifiers: .command)

            Button("Rotate Left") {
                NotificationCenter.default.post(name: .iFauxtoRotateLeft, object: nil)
            }
            .keyboardShortcut("l", modifiers: [.command, .option])

            Button("Rotate Right") {
                NotificationCenter.default.post(name: .iFauxtoRotateRight, object: nil)
            }
            .keyboardShortcut("r", modifiers: [.command, .option])

            Divider()

            Button("Get Info") {
                NotificationCenter.default.post(name: .iFauxtoShowInfo, object: nil)
            }
            .keyboardShortcut("i", modifiers: .command)

            Button("Edit…") {
                NotificationCenter.default.post(name: .iFauxtoOpenEditor, object: nil)
            }
            .keyboardShortcut("e", modifiers: .command)

            Divider()

            Button("Move to Trash") {
                NotificationCenter.default.post(name: .iFauxtoTrash, object: nil)
            }
            .keyboardShortcut(.delete, modifiers: .command)
        }

        // View menu additions.
        CommandGroup(before: .toolbar) {
            Button("Show Folders") {
                NotificationCenter.default.post(name: .iFauxtoShowFolders, object: nil)
            }
            .keyboardShortcut("1", modifiers: .command)

            Button("Show Photo Feed") {
                NotificationCenter.default.post(name: .iFauxtoShowFeed, object: nil)
            }
            .keyboardShortcut("2", modifiers: .command)

            Button("Show Events") {
                NotificationCenter.default.post(name: .iFauxtoShowEvents, object: nil)
            }
            .keyboardShortcut("3", modifiers: .command)

            Button("Show Places") {
                NotificationCenter.default.post(name: .iFauxtoShowPlaces, object: nil)
            }
            .keyboardShortcut("4", modifiers: .command)

            Divider()

            Button("Start Slideshow") {
                NotificationCenter.default.post(name: .iFauxtoStartSlideshow, object: nil)
            }
            .keyboardShortcut("s", modifiers: [.command, .shift])
        }
    }
}

extension Notification.Name {
    static let iFauxtoNewAlbum        = Notification.Name("iFauxto.newAlbum")
    static let iFauxtoNewSmartAlbum   = Notification.Name("iFauxto.newSmartAlbum")
    static let iFauxtoImportFiles     = Notification.Name("iFauxto.importFiles")
    static let iFauxtoToggleFavorite  = Notification.Name("iFauxto.toggleFavorite")
    static let iFauxtoRotateLeft      = Notification.Name("iFauxto.rotateLeft")
    static let iFauxtoRotateRight     = Notification.Name("iFauxto.rotateRight")
    static let iFauxtoShowInfo        = Notification.Name("iFauxto.showInfo")
    static let iFauxtoOpenEditor      = Notification.Name("iFauxto.openEditor")
    static let iFauxtoTrash           = Notification.Name("iFauxto.trash")
    static let iFauxtoShowFolders     = Notification.Name("iFauxto.showFolders")
    static let iFauxtoShowFeed        = Notification.Name("iFauxto.showFeed")
    static let iFauxtoShowEvents      = Notification.Name("iFauxto.showEvents")
    static let iFauxtoShowPlaces      = Notification.Name("iFauxto.showPlaces")
    static let iFauxtoStartSlideshow  = Notification.Name("iFauxto.startSlideshow")
}
