import SwiftUI

/// Drag-handle crop overlay used inside the photo editor preview.
/// Operates on a normalized 0..1 rectangle so it survives device rotations
/// and works at any preview size. Four corner handles + center pan.
struct CropOverlay: View {
    @Binding var rect: CGRect      // normalized 0..1
    let viewport: CGSize

    private let handleSize: CGFloat = 28
    private let minNormalized: CGFloat = 0.1

    var body: some View {
        let frame = pixelFrame(in: viewport)

        ZStack {
            // Dim outside the crop area.
            Color.black.opacity(0.55)
                .mask(
                    Rectangle()
                        .overlay(
                            Rectangle()
                                .frame(width: frame.width, height: frame.height)
                                .position(x: frame.midX, y: frame.midY)
                                .blendMode(.destinationOut)
                        )
                        .compositingGroup()
                )
                .allowsHitTesting(false)

            // Crop frame
            Rectangle()
                .strokeBorder(Color.white, lineWidth: 1.5)
                .frame(width: frame.width, height: frame.height)
                .position(x: frame.midX, y: frame.midY)

            // Rule-of-thirds guides
            Path { p in
                p.move(to: CGPoint(x: frame.minX + frame.width / 3, y: frame.minY))
                p.addLine(to: CGPoint(x: frame.minX + frame.width / 3, y: frame.maxY))
                p.move(to: CGPoint(x: frame.minX + 2 * frame.width / 3, y: frame.minY))
                p.addLine(to: CGPoint(x: frame.minX + 2 * frame.width / 3, y: frame.maxY))
                p.move(to: CGPoint(x: frame.minX, y: frame.minY + frame.height / 3))
                p.addLine(to: CGPoint(x: frame.maxX, y: frame.minY + frame.height / 3))
                p.move(to: CGPoint(x: frame.minX, y: frame.minY + 2 * frame.height / 3))
                p.addLine(to: CGPoint(x: frame.maxX, y: frame.minY + 2 * frame.height / 3))
            }
            .stroke(Color.white.opacity(0.4), lineWidth: 0.5)

            // Center pan target
            Rectangle()
                .fill(Color.clear)
                .contentShape(Rectangle())
                .frame(width: frame.width, height: frame.height)
                .position(x: frame.midX, y: frame.midY)
                .gesture(panGesture)

            // Corner handles
            handle(.topLeading,    at: CGPoint(x: frame.minX, y: frame.minY))
            handle(.topTrailing,   at: CGPoint(x: frame.maxX, y: frame.minY))
            handle(.bottomLeading, at: CGPoint(x: frame.minX, y: frame.maxY))
            handle(.bottomTrailing, at: CGPoint(x: frame.maxX, y: frame.maxY))
        }
    }

    // MARK: - Geometry helpers

    private func pixelFrame(in size: CGSize) -> CGRect {
        CGRect(
            x: rect.origin.x * size.width,
            y: rect.origin.y * size.height,
            width: rect.width * size.width,
            height: rect.height * size.height
        )
    }

    private func clampedRect(_ r: CGRect) -> CGRect {
        var out = r
        if out.width < minNormalized { out.size.width = minNormalized }
        if out.height < minNormalized { out.size.height = minNormalized }
        if out.origin.x < 0 { out.origin.x = 0 }
        if out.origin.y < 0 { out.origin.y = 0 }
        if out.origin.x + out.width > 1 { out.origin.x = 1 - out.width }
        if out.origin.y + out.height > 1 { out.origin.y = 1 - out.height }
        return out
    }

    // MARK: - Gestures

    private var panGesture: some Gesture {
        DragGesture()
            .onChanged { value in
                let dx = value.translation.width / viewport.width
                let dy = value.translation.height / viewport.height
                var next = rect
                next.origin.x = max(0, min(1 - rect.width, rect.origin.x + dx))
                next.origin.y = max(0, min(1 - rect.height, rect.origin.y + dy))
                rect = clampedRect(next)
            }
    }

    private enum Corner { case topLeading, topTrailing, bottomLeading, bottomTrailing }

    private func handle(_ corner: Corner, at point: CGPoint) -> some View {
        Circle()
            .fill(Color.white)
            .overlay(Circle().strokeBorder(Color.black.opacity(0.6), lineWidth: 1))
            .frame(width: 16, height: 16)
            .shadow(color: .black.opacity(0.4), radius: 2)
            .frame(width: handleSize, height: handleSize)
            .contentShape(Rectangle())
            .position(point)
            .gesture(
                DragGesture()
                    .onChanged { value in
                        let dx = value.translation.width / viewport.width
                        let dy = value.translation.height / viewport.height
                        var next = rect
                        switch corner {
                        case .topLeading:
                            next.origin.x += dx
                            next.origin.y += dy
                            next.size.width -= dx
                            next.size.height -= dy
                        case .topTrailing:
                            next.size.width += dx
                            next.origin.y += dy
                            next.size.height -= dy
                        case .bottomLeading:
                            next.origin.x += dx
                            next.size.width -= dx
                            next.size.height += dy
                        case .bottomTrailing:
                            next.size.width += dx
                            next.size.height += dy
                        }
                        rect = clampedRect(next)
                    }
            )
    }
}
