import Foundation
import Photos
import UIKit
import Vision

/// Runs Vision face detection over the user's library and groups
/// photos into clusters using a coarse spatial signature. Production
/// would swap the signature for a real face embedding (FaceNet etc.) —
/// the cluster API stays the same.
@MainActor
final class FaceClusteringService {
    private let tagger = VisionTaggingService()

    /// Scans every authorized photo, detects faces, and returns clusters.
    /// Each cluster groups photo identifiers that share at least one
    /// face signature.
    func cluster(identifiers: [String]) async -> [(displayName: String, cover: String, members: [String])] {
        var sigToMembers: [String: Set<String>] = [:]
        var photoToSigs: [String: [String]] = [:]

        for id in identifiers {
            guard !id.hasPrefix("demo:"), !id.hasPrefix("file://") else { continue }
            guard let cgImage = await loadCGImage(for: id) else { continue }
            let sigs = await tagger.faceSignatures(image: cgImage)
            guard !sigs.isEmpty else { continue }
            photoToSigs[id] = sigs
            for sig in sigs {
                sigToMembers[sig, default: []].insert(id)
            }
        }

        // Coalesce: any signature with at least 2 members becomes a cluster.
        var clusters: [(displayName: String, cover: String, members: [String])] = []
        var seen = Set<String>()
        var personIndex = 1
        for (sig, members) in sigToMembers where members.count >= 2 {
            let unseen = members.filter { !seen.contains($0) }
            guard !unseen.isEmpty else { continue }
            let sorted = unseen.sorted()
            let cover = sorted.first ?? ""
            clusters.append((
                displayName: "Person \(personIndex)",
                cover: cover,
                members: sorted
            ))
            seen.formUnion(sorted)
            personIndex += 1
            _ = sig
        }

        return clusters
    }

    private func loadCGImage(for identifier: String) async -> CGImage? {
        let result = PHAsset.fetchAssets(withLocalIdentifiers: [identifier], options: nil)
        guard let asset = result.firstObject else { return nil }
        return await withCheckedContinuation { (continuation: CheckedContinuation<CGImage?, Never>) in
            let options = PHImageRequestOptions()
            options.deliveryMode = .highQualityFormat
            options.isNetworkAccessAllowed = false
            options.isSynchronous = false
            PHImageManager.default().requestImage(
                for: asset,
                targetSize: CGSize(width: 512, height: 512),
                contentMode: .aspectFit,
                options: options
            ) { image, _ in
                continuation.resume(returning: image?.cgImage)
            }
        }
    }
}
