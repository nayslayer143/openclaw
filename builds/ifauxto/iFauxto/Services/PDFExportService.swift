import UIKit
import PDFKit

/// Renders one or more UIImages to a multi-page PDF in the temp directory
/// and returns the URL so the share sheet can hand it off.
enum PDFExportService {

    /// US Letter at 72dpi (612 × 792 pts).
    static let pageSize = CGSize(width: 612, height: 792)
    static let margin: CGFloat = 36

    static func renderPDF(images: [UIImage], title: String = "iFauxto Photos") -> URL? {
        guard !images.isEmpty else { return nil }

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("iFauxto-\(UUID().uuidString.prefix(8)).pdf")

        let renderer = UIGraphicsPDFRenderer(
            bounds: CGRect(origin: .zero, size: pageSize),
            format: pdfFormat(title: title)
        )

        do {
            try renderer.writePDF(to: url) { context in
                for image in images {
                    context.beginPage()
                    drawCenteredImage(image, in: pageSize, context: context.cgContext)
                }
            }
            return url
        } catch {
            return nil
        }
    }

    private static func pdfFormat(title: String) -> UIGraphicsPDFRendererFormat {
        let format = UIGraphicsPDFRendererFormat()
        format.documentInfo = [
            kCGPDFContextCreator as String: "iFauxto",
            kCGPDFContextTitle as String: title
        ]
        return format
    }

    private static func drawCenteredImage(_ image: UIImage, in pageSize: CGSize, context: CGContext) {
        let inner = CGRect(
            x: margin,
            y: margin,
            width: pageSize.width - margin * 2,
            height: pageSize.height - margin * 2
        )
        let imgSize = image.size
        let scale = min(inner.width / imgSize.width, inner.height / imgSize.height)
        let drawn = CGSize(width: imgSize.width * scale, height: imgSize.height * scale)
        let origin = CGPoint(
            x: inner.midX - drawn.width / 2,
            y: inner.midY - drawn.height / 2
        )
        image.draw(in: CGRect(origin: origin, size: drawn))
    }
}
