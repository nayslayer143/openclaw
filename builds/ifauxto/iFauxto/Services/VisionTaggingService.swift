import Vision
import UIKit

struct PhotoTags {
    let assetId: String
    let tags: [TagRecord]
}

final class VisionTaggingService {

    func tagPhoto(image: CGImage, assetId: String) async -> PhotoTags {
        async let objectTags = classifyImage(image)
        async let textTags = recognizeText(image)
        async let faceCount = detectFaces(image)

        let objects = await objectTags
        let texts = await textTags
        let faces = await faceCount

        var tags: [TagRecord] = []

        for item in objects {
            tags.append(TagRecord(tagType: "object", tagValue: item.label, confidence: item.confidence))
        }

        for text in texts {
            tags.append(TagRecord(tagType: "text", tagValue: text, confidence: 1.0))
        }

        if faces > 0 {
            tags.append(TagRecord(tagType: "face", tagValue: "\(faces) face\(faces == 1 ? "" : "s")", confidence: 1.0))
        }

        return PhotoTags(assetId: assetId, tags: tags)
    }

    // MARK: - Vision Requests

    private func classifyImage(_ image: CGImage) async -> [(label: String, confidence: Float)] {
        await withCheckedContinuation { continuation in
            let request = VNClassifyImageRequest { request, error in
                guard let results = request.results as? [VNClassificationObservation] else {
                    continuation.resume(returning: [])
                    return
                }
                let filtered = results
                    .filter { $0.confidence > 0.1 }
                    .prefix(10)
                    .map { (label: $0.identifier.replacingOccurrences(of: "_", with: " "), confidence: $0.confidence) }
                continuation.resume(returning: Array(filtered))
            }
            let handler = VNImageRequestHandler(cgImage: image, options: [:])
            try? handler.perform([request])
        }
    }

    private func recognizeText(_ image: CGImage) async -> [String] {
        await withCheckedContinuation { continuation in
            let request = VNRecognizeTextRequest { request, error in
                guard let results = request.results as? [VNRecognizedTextObservation] else {
                    continuation.resume(returning: [])
                    return
                }
                let texts = results.compactMap { $0.topCandidates(1).first?.string }
                continuation.resume(returning: texts)
            }
            request.recognitionLevel = .fast
            let handler = VNImageRequestHandler(cgImage: image, options: [:])
            try? handler.perform([request])
        }
    }

    private func detectFaces(_ image: CGImage) async -> Int {
        await withCheckedContinuation { continuation in
            let request = VNDetectFaceRectanglesRequest { request, error in
                let count = (request.results as? [VNFaceObservation])?.count ?? 0
                continuation.resume(returning: count)
            }
            let handler = VNImageRequestHandler(cgImage: image, options: [:])
            try? handler.perform([request])
        }
    }
}
