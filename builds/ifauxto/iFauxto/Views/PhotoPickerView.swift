import SwiftUI
import PhotosUI

/// Wraps PHPickerViewController to let users pick photos from their library.
/// Returns PHAsset localIdentifiers — never UIImages (no duplication).
struct PhotoPickerView: UIViewControllerRepresentable {
    let onComplete: ([String]) -> Void

    func makeUIViewController(context: Context) -> PHPickerViewController {
        var config = PHPickerConfiguration(photoLibrary: .shared())
        config.selectionLimit = 0       // unlimited selection
        config.filter = .images
        config.preferredAssetRepresentationMode = .current

        let picker = PHPickerViewController(configuration: config)
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: PHPickerViewController, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(onComplete: onComplete)
    }

    final class Coordinator: NSObject, PHPickerViewControllerDelegate {
        let onComplete: ([String]) -> Void
        init(onComplete: @escaping ([String]) -> Void) { self.onComplete = onComplete }

        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            picker.dismiss(animated: true)
            // Extract localIdentifiers — only available when using PHPickerConfiguration(photoLibrary:)
            let identifiers = results.compactMap { $0.assetIdentifier }
            onComplete(identifiers)
        }
    }
}
