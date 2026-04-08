import CoreImage
import CoreImage.CIFilterBuiltins
import UIKit

final class EditService {
    private let context = CIContext(options: [.useSoftwareRenderer: false])

    func applyAdjustments(_ adj: EditAdjustments, to inputImage: CIImage) -> CIImage {
        var image = inputImage

        // Geometry first so subsequent filters operate on the rotated image.
        let turns = ((adj.rotationQuarterTurns % 4) + 4) % 4
        if turns > 0 {
            // Each clockwise turn is -π/2 radians.
            let radians = -CGFloat(turns) * .pi / 2
            let transform = CGAffineTransform(rotationAngle: radians)
            image = image.transformed(by: transform)
            // Re-anchor to origin so downstream extents are positive.
            let translate = CGAffineTransform(translationX: -image.extent.origin.x, y: -image.extent.origin.y)
            image = image.transformed(by: translate)
        }

        // Crop after rotation so the normalized rect maps onto the
        // rotated image extents.
        if adj.hasCustomCrop {
            let extent = image.extent
            let cropRect = CGRect(
                x: extent.origin.x + extent.width * adj.cropOriginX,
                y: extent.origin.y + extent.height * (1 - adj.cropOriginY - adj.cropHeight),
                width: extent.width * adj.cropWidth,
                height: extent.height * adj.cropHeight
            )
            image = image.cropped(to: cropRect)
            let reset = CGAffineTransform(translationX: -image.extent.origin.x, y: -image.extent.origin.y)
            image = image.transformed(by: reset)
        }

        if adj.exposure != 0 {
            let filter = CIFilter.exposureAdjust()
            filter.inputImage = image
            filter.ev = adj.exposure * 3.0
            image = filter.outputImage ?? image
        }

        if adj.contrast != 0 || adj.saturation != 0 {
            let filter = CIFilter.colorControls()
            filter.inputImage = image
            filter.contrast = 1.0 + adj.contrast
            filter.saturation = 1.0 + adj.saturation
            image = filter.outputImage ?? image
        }

        if adj.temperature != 0 {
            let filter = CIFilter.temperatureAndTint()
            filter.inputImage = image
            filter.neutral = CIVector(x: 6500, y: 0)
            filter.targetNeutral = CIVector(x: CGFloat(6500 + adj.temperature * 3000), y: 0)
            image = filter.outputImage ?? image
        }

        if adj.highlights != 0 || adj.shadows != 0 {
            let filter = CIFilter.highlightShadowAdjust()
            filter.inputImage = image
            filter.highlightAmount = 1.0 + adj.highlights
            filter.shadowAmount = adj.shadows * -1.0
            image = filter.outputImage ?? image
        }

        if adj.vignette > 0 {
            let filter = CIFilter.vignette()
            filter.inputImage = image
            filter.intensity = adj.vignette * 2.0
            filter.radius = 2.0
            image = filter.outputImage ?? image
        }

        if adj.grain > 0 {
            image = applyGrain(to: image, amount: adj.grain)
        }

        return image
    }

    func renderPreview(_ adj: EditAdjustments, inputImage: CIImage, targetSize: CGSize) -> UIImage? {
        let output = applyAdjustments(adj, to: inputImage)
        guard let cgImage = context.createCGImage(output, from: output.extent) else { return nil }
        return UIImage(cgImage: cgImage)
    }

    private func applyGrain(to image: CIImage, amount: Float) -> CIImage {
        let noise = CIFilter.randomGenerator()
        guard let noiseImage = noise.outputImage else { return image }

        let croppedNoise = noiseImage.cropped(to: image.extent)

        let whitening = CIFilter.colorMatrix()
        whitening.inputImage = croppedNoise
        whitening.rVector = CIVector(x: 0, y: 1, z: 0, w: 0)
        whitening.gVector = CIVector(x: 0, y: 1, z: 0, w: 0)
        whitening.bVector = CIVector(x: 0, y: 1, z: 0, w: 0)
        whitening.aVector = CIVector(x: 0, y: 0, z: 0, w: CGFloat(amount * 0.3))

        guard let whiteNoise = whitening.outputImage else { return image }

        let composite = CIFilter.sourceOverCompositing()
        composite.inputImage = whiteNoise
        composite.backgroundImage = image
        return composite.outputImage ?? image
    }
}
