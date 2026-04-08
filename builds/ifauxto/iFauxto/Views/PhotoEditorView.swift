import SwiftUI
import CoreImage

struct PhotoEditorView: View {
    let photoIdentifier: String
    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var photoKitService: PhotoKitService
    @Environment(\.dismiss) var dismiss

    @State private var adjustments = EditAdjustments()
    @State private var originalImage: CIImage?
    @State private var previewImage: UIImage?
    @State private var showingOriginal = false
    @State private var isCropping = false
    @State private var cropRect = CGRect(x: 0, y: 0, width: 1, height: 1)

    private let editService = EditService()

    var body: some View {
        VStack(spacing: 0) {
            // Top bar — same iPhoto chrome as the rest of the app.
            ZStack {
                Text("Edit")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(Theme.Palette.text)

                HStack {
                    Button {
                        Haptics.tap()
                        dismiss()
                    } label: {
                        Text("Cancel")
                            .font(.system(size: 17))
                            .foregroundStyle(Theme.Palette.accent)
                    }
                    .buttonStyle(.plain)
                    Spacer()
                    Button {
                        Haptics.success()
                        let dm: DataManager = dataManager
                        dm.saveEditState(photoId: photoIdentifier, adjustments: adjustments)
                        dismiss()
                    } label: {
                        Text("Save")
                            .font(.system(size: 17, weight: .semibold))
                            .foregroundStyle(Theme.Palette.accent)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 16)
            }
            .frame(height: 44)
            .padding(.top, 8)
            .padding(.bottom, 6)
            .background(Theme.Palette.bg)
            .overlay(
                Rectangle().fill(Theme.Palette.divider).frame(height: 0.5),
                alignment: .bottom
            )

            previewSection
            sliderSection
        }
        .background(Theme.Palette.bg)
        .task {
            await loadOriginalImage()
            let dm: DataManager = dataManager
            if let existing = dm.fetchEditState(photoId: photoIdentifier) {
                adjustments = existing.adjustments
            }
            updatePreview()
        }
        .onChange(of: adjustments) { _, _ in
            updatePreview()
        }
    }

    private var previewSection: some View {
        GeometryReader { geo in
            ZStack {
                Color.black
                if showingOriginal, let orig = originalImage {
                    Image(uiImage: UIImage(ciImage: orig))
                        .resizable()
                        .scaledToFit()
                } else if let preview = previewImage {
                    Image(uiImage: preview)
                        .resizable()
                        .scaledToFit()
                } else {
                    ProgressView()
                        .tint(.white)
                }

                if isCropping {
                    CropOverlay(rect: $cropRect, viewport: geo.size)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .onLongPressGesture(minimumDuration: .infinity, pressing: { pressing in
                showingOriginal = pressing
            }, perform: {})
        }
        .frame(maxHeight: .infinity)
    }

    private var sliderSection: some View {
        VStack(spacing: 0) {
            presetStrip

            ScrollView {
                VStack(spacing: 14) {
                    geometrySection
                    sliderRow("Exposure", value: $adjustments.exposure, range: -1...1)
                    sliderRow("Contrast", value: $adjustments.contrast, range: -1...1)
                    sliderRow("Saturation", value: $adjustments.saturation, range: -1...1)
                    sliderRow("Temperature", value: $adjustments.temperature, range: -1...1)
                    sliderRow("Highlights", value: $adjustments.highlights, range: -1...1)
                    sliderRow("Shadows", value: $adjustments.shadows, range: -1...1)
                    sliderRow("Grain", value: $adjustments.grain, range: 0...1)
                    sliderRow("Vignette", value: $adjustments.vignette, range: 0...1)
                }
                .padding(16)
            }
            Divider()
            HStack {
                Spacer()
                Button {
                    Haptics.tap()
                    withAnimation(Theme.Motion.snappy) {
                        adjustments = EditAdjustments()
                    }
                } label: {
                    Text("Reset")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(.red)
                }
                .buttonStyle(.plain)
                Spacer()
            }
            .padding(.vertical, 12)
            .background(Theme.Palette.bgElevated)
        }
        .frame(height: 320)
        .background(Theme.Palette.bgElevated)
    }

    /// Horizontally scrolling preset thumbnails. Tapping a preset
    /// replaces every adjustment except geometry (rotation/crop).
    private var presetStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(EditPresets.all) { preset in
                    Button {
                        Haptics.select()
                        // Preserve geometry while swapping color/tone.
                        let rot = adjustments.rotationQuarterTurns
                        let cx = adjustments.cropOriginX
                        let cy = adjustments.cropOriginY
                        let cw = adjustments.cropWidth
                        let ch = adjustments.cropHeight
                        var next = preset.adjustments
                        next.rotationQuarterTurns = rot
                        next.cropOriginX = cx
                        next.cropOriginY = cy
                        next.cropWidth = cw
                        next.cropHeight = ch
                        withAnimation(Theme.Motion.snappy) {
                            adjustments = next
                        }
                    } label: {
                        VStack(spacing: 6) {
                            ZStack {
                                RoundedRectangle(cornerRadius: 8, style: .continuous)
                                    .fill(presetSwatch(preset))
                                RoundedRectangle(cornerRadius: 8, style: .continuous)
                                    .strokeBorder(
                                        adjustments == preset.adjustments
                                            ? Theme.Palette.accent
                                            : Theme.Palette.stroke,
                                        lineWidth: adjustments == preset.adjustments ? 2 : 0.5
                                    )
                            }
                            .frame(width: 56, height: 56)
                            Text(preset.name)
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(Theme.Palette.text)
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
        }
        .background(Theme.Palette.bg)
        .overlay(
            Rectangle().fill(Theme.Palette.divider).frame(height: 0.5),
            alignment: .bottom
        )
    }

    /// Quick visual approximation of what each preset does — a swatch
    /// drawn from the adjustments themselves rather than a real render.
    private func presetSwatch(_ preset: EditPreset) -> LinearGradient {
        let a = preset.adjustments
        let warm = max(0, CGFloat(a.temperature))
        let cool = max(0, CGFloat(-a.temperature))
        let bright = 0.5 + CGFloat(a.exposure) * 0.5
        let mono = a.saturation < -0.5
        let r = mono ? bright : min(1, bright + warm * 0.4)
        let g = mono ? bright : min(1, bright + 0.05)
        let b = mono ? bright : min(1, bright + cool * 0.4)
        let top = Color(red: r, green: g, blue: b)
        let bot = Color(
            red: max(0, r - 0.18),
            green: max(0, g - 0.18),
            blue: max(0, b - 0.18)
        )
        return LinearGradient(colors: [top, bot], startPoint: .topLeading, endPoint: .bottomTrailing)
    }

    private var geometrySection: some View {
        HStack(spacing: 12) {
            Text("Geometry")
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(Theme.Palette.text)
            Spacer()
            geoButton(systemName: "rotate.left") {
                adjustments.rotationQuarterTurns = ((adjustments.rotationQuarterTurns - 1) % 4 + 4) % 4
            }
            geoButton(systemName: "rotate.right") {
                adjustments.rotationQuarterTurns = (adjustments.rotationQuarterTurns + 1) % 4
            }
            geoButton(systemName: isCropping ? "checkmark" : "crop") {
                if isCropping {
                    // Commit the crop into adjustments.
                    adjustments.cropOriginX = cropRect.origin.x
                    adjustments.cropOriginY = cropRect.origin.y
                    adjustments.cropWidth = cropRect.width
                    adjustments.cropHeight = cropRect.height
                    isCropping = false
                } else {
                    // Enter crop mode with current crop loaded.
                    cropRect = CGRect(
                        x: adjustments.cropOriginX,
                        y: adjustments.cropOriginY,
                        width: adjustments.cropWidth,
                        height: adjustments.cropHeight
                    )
                    isCropping = true
                }
            }
        }
        .padding(.bottom, 4)
    }

    private func geoButton(systemName: String, action: @escaping () -> Void) -> some View {
        Button {
            Haptics.tap()
            action()
        } label: {
            Image(systemName: systemName)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Theme.Palette.accent)
                .frame(width: 38, height: 38)
                .background(Circle().fill(Theme.Palette.bg))
                .overlay(Circle().strokeBorder(Theme.Palette.stroke, lineWidth: 0.5))
        }
        .buttonStyle(.plain)
    }

    private func sliderRow(_ label: String, value: Binding<Float>, range: ClosedRange<Float>) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(label)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(Theme.Palette.text)
                Spacer()
                Text(String(format: "%.2f", value.wrappedValue))
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.Palette.textMuted)
                    .monospacedDigit()
            }
            Slider(value: value, in: range)
                .tint(Theme.Palette.accent)
        }
    }

    private func loadOriginalImage() async {
        guard let uiImage = await photoKitService.loadFullImage(for: photoIdentifier) else { return }
        originalImage = CIImage(image: uiImage)
    }

    private func updatePreview() {
        guard let input = originalImage else { return }
        previewImage = editService.renderPreview(adjustments, inputImage: input, targetSize: CGSize(width: 800, height: 800))
    }
}
