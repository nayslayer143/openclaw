import UIKit
import UniformTypeIdentifiers
import Social

/// Minimal share extension that accepts images and videos from any host
/// app (Photos.app, Safari, Messages, Files) and drops them into
/// iFauxto's shared App Group container so the main app picks them up
/// on next launch.
///
/// App Group: group.com.ifauxto.shared
/// Inbox path: <group-container>/ShareInbox/
class ShareViewController: SLComposeServiceViewController {

    private let appGroupId = "group.com.ifauxto.shared"
    private let inboxSubpath = "ShareInbox"

    override func isContentValid() -> Bool {
        // Allow sending with or without a caption.
        return true
    }

    override func didSelectPost() {
        guard let items = extensionContext?.inputItems as? [NSExtensionItem] else {
            complete()
            return
        }

        var pending = 0
        let caption = contentText ?? ""

        for item in items {
            guard let providers = item.attachments else { continue }
            for provider in providers {
                if provider.hasItemConformingToTypeIdentifier(UTType.image.identifier) {
                    pending += 1
                    provider.loadFileRepresentation(forTypeIdentifier: UTType.image.identifier) { [weak self] url, _ in
                        defer {
                            DispatchQueue.main.async {
                                pending -= 1
                                if pending == 0 { self?.complete() }
                            }
                        }
                        guard let self, let url else { return }
                        self.copyToInbox(sourceURL: url, caption: caption)
                    }
                } else if provider.hasItemConformingToTypeIdentifier(UTType.movie.identifier) {
                    pending += 1
                    provider.loadFileRepresentation(forTypeIdentifier: UTType.movie.identifier) { [weak self] url, _ in
                        defer {
                            DispatchQueue.main.async {
                                pending -= 1
                                if pending == 0 { self?.complete() }
                            }
                        }
                        guard let self, let url else { return }
                        self.copyToInbox(sourceURL: url, caption: caption)
                    }
                }
            }
        }

        if pending == 0 { complete() }
    }

    override func configurationItems() -> [Any]! {
        return []
    }

    // MARK: - File copy

    private func copyToInbox(sourceURL: URL, caption: String) {
        guard let container = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: appGroupId
        ) else { return }

        let inboxDir = container.appendingPathComponent(inboxSubpath, isDirectory: true)
        if !FileManager.default.fileExists(atPath: inboxDir.path) {
            try? FileManager.default.createDirectory(
                at: inboxDir,
                withIntermediateDirectories: true
            )
        }

        let unique = "\(UUID().uuidString)-\(sourceURL.lastPathComponent)"
        let dest = inboxDir.appendingPathComponent(unique)
        try? FileManager.default.copyItem(at: sourceURL, to: dest)

        // Write caption sidecar.
        if !caption.isEmpty {
            let captionURL = dest.appendingPathExtension("caption.txt")
            try? caption.write(to: captionURL, atomically: true, encoding: .utf8)
        }
    }

    private func complete() {
        extensionContext?.completeRequest(returningItems: nil, completionHandler: nil)
    }
}
