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
        NavigationStack {
            VStack(spacing: 0) {
                previewSection
                sliderSection
            }
            .navigationTitle("Edit")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        let dm: DataManager = dataManager
                        dm.saveEditState(photoId: photoIdentifier, adjustments: adjustments)
                        dismiss()
                    }
                    .fontWeight(.semibold)
                }
                ToolbarItem(placement: .bottomBar) {
                    Button("Reset") {
                        adjustments = EditAdjustments()
                    }
                    .foregroundColor(.red)
                }
            }
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
        ScrollView {
            VStack(spacing: 16) {
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
        .frame(height: 280)
        .background(Color(.systemBackground))
    }

    private func sliderRow(_ label: String, value: Binding<Float>, range: ClosedRange<Float>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(label)
                    .font(.caption.weight(.medium))
                Spacer()
                Text(String(format: "%.2f", value.wrappedValue))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }
            Slider(value: value, in: range)
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
