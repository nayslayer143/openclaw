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
        }
        .frame(maxHeight: .infinity)
        .onLongPressGesture(minimumDuration: .infinity, pressing: { pressing in
            showingOriginal = pressing
        }, perform: {})
    }

    private var sliderSection: some View {
        VStack(spacing: 0) {
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

    private var geometrySection: some View {
        HStack(spacing: 16) {
            Text("Geometry")
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(Theme.Palette.text)
            Spacer()
            Button {
                Haptics.tap()
                adjustments.rotationQuarterTurns = ((adjustments.rotationQuarterTurns - 1) % 4 + 4) % 4
            } label: {
                Image(systemName: "rotate.left")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(Theme.Palette.accent)
                    .frame(width: 38, height: 38)
                    .background(Circle().fill(Theme.Palette.bg))
                    .overlay(Circle().strokeBorder(Theme.Palette.stroke, lineWidth: 0.5))
            }
            .buttonStyle(.plain)
            Button {
                Haptics.tap()
                adjustments.rotationQuarterTurns = (adjustments.rotationQuarterTurns + 1) % 4
            } label: {
                Image(systemName: "rotate.right")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(Theme.Palette.accent)
                    .frame(width: 38, height: 38)
                    .background(Circle().fill(Theme.Palette.bg))
                    .overlay(Circle().strokeBorder(Theme.Palette.stroke, lineWidth: 0.5))
            }
            .buttonStyle(.plain)
        }
        .padding(.bottom, 4)
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
