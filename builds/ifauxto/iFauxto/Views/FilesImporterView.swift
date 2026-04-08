import SwiftUI
import UniformTypeIdentifiers

/// SwiftUI wrapper for the system Files importer. Returns the picked
/// URLs back to the caller. Caller is responsible for copying the files
/// into the app's container before the security-scoped URL goes away.
struct FilesImporterView: View {
    let onPick: ([URL]) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var presented = true

    var body: some View {
        Color.clear
            .fileImporter(
                isPresented: $presented,
                allowedContentTypes: [
                    .image, .jpeg, .png, .heic, .gif,
                    .movie, .mpeg4Movie, .quickTimeMovie
                ],
                allowsMultipleSelection: true
            ) { result in
                switch result {
                case .success(let urls):
                    onPick(urls)
                case .failure:
                    onPick([])
                }
                dismiss()
            }
    }
}
