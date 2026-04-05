# Phase 4: VSCO-Style Photo Editing

> Part of iFauxto v2 plan. Read `2026-04-04-ifauxto-v2-plan.md` first. Phases 1-3 must be complete.

**Goal:** Non-destructive photo editing with slider-based adjustments (exposure, contrast, saturation, temperature, highlights/shadows, grain, vignette). Real-time preview via CIFilter. Edits stored in SwiftData overlay.

---

### Task 1: Create EditState model and EditAdjustments

**Files:**
- Create: `iFauxto/Models/EditState.swift`
- Modify: `iFauxto/Models/DataManager.swift`
- Test: `iFauxtoTests/EditStateTests.swift`

- [ ] **Step 1: Write the failing test**

Create `iFauxtoTests/EditStateTests.swift`:

```swift
import Testing
import SwiftData
import Foundation
@testable import iFauxto

@MainActor
@Suite("EditState")
struct EditStateTests {

    func makeManager() throws -> DataManager {
        return try DataManager(inMemory: true)
    }

    @Test("Save and retrieve edit state")
    func saveAndRetrieve() throws {
        let dm = try makeManager()
        var adj = EditAdjustments()
        adj.exposure = 0.5
        adj.contrast = -0.3
        dm.saveEditState(photoId: "photo-1", adjustments: adj)
        let fetched = dm.fetchEditState(photoId: "photo-1")
        #expect(fetched != nil)
        #expect(fetched?.adjustments.exposure == 0.5)
        #expect(fetched?.adjustments.contrast == -0.3)
    }

    @Test("Default adjustments are all zero")
    func defaults() throws {
        let adj = EditAdjustments()
        #expect(adj.exposure == 0)
        #expect(adj.contrast == 0)
        #expect(adj.saturation == 0)
        #expect(adj.temperature == 0)
        #expect(adj.highlights == 0)
        #expect(adj.shadows == 0)
        #expect(adj.grain == 0)
        #expect(adj.vignette == 0)
    }

    @Test("Delete edit state")
    func deleteEditState() throws {
        let dm = try makeManager()
        dm.saveEditState(photoId: "photo-1", adjustments: EditAdjustments())
        dm.deleteEditState(photoId: "photo-1")
        #expect(dm.fetchEditState(photoId: "photo-1") == nil)
    }

    @Test("hasEdits returns correct state")
    func hasEdits() throws {
        let dm = try makeManager()
        #expect(!dm.hasEdits(photoId: "photo-1"))
        dm.saveEditState(photoId: "photo-1", adjustments: EditAdjustments())
        #expect(dm.hasEdits(photoId: "photo-1"))
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — `EditState`, `EditAdjustments` not found.

- [ ] **Step 3: Create EditState.swift**

Create `iFauxto/Models/EditState.swift`:

```swift
import SwiftData
import Foundation

struct EditAdjustments: Codable, Equatable {
    var exposure: Float = 0       // -1.0 to 1.0
    var contrast: Float = 0       // -1.0 to 1.0
    var saturation: Float = 0     // -1.0 to 1.0
    var temperature: Float = 0    // -1.0 to 1.0
    var highlights: Float = 0     // -1.0 to 1.0
    var shadows: Float = 0        // -1.0 to 1.0
    var grain: Float = 0          // 0.0 to 1.0
    var vignette: Float = 0       // 0.0 to 1.0
}

@Model
final class EditState {
    @Attribute(.unique) var photoId: String = ""
    var adjustmentsData: Data = Data()
    var createdAt: Date = Date()
    var updatedAt: Date = Date()

    var adjustments: EditAdjustments {
        get {
            (try? JSONDecoder().decode(EditAdjustments.self, from: adjustmentsData)) ?? EditAdjustments()
        }
        set {
            adjustmentsData = (try? JSONEncoder().encode(newValue)) ?? Data()
            updatedAt = Date()
        }
    }

    init(photoId: String, adjustments: EditAdjustments) {
        self.photoId = photoId
        self.adjustmentsData = (try? JSONEncoder().encode(adjustments)) ?? Data()
        self.createdAt = Date()
        self.updatedAt = Date()
    }
}
```

- [ ] **Step 4: Register EditState in DataManager and add CRUD**

In `iFauxto/Models/DataManager.swift`, update the schema line:

From:
```swift
        let schema = Schema([Folder.self, PhotoReference.self, AppSettings.self])
```
To:
```swift
        let schema = Schema([Folder.self, PhotoReference.self, AppSettings.self, EditState.self])
```

Add these methods at the end of DataManager (before the closing `}`):

```swift
    // MARK: Edit State

    func saveEditState(photoId: String, adjustments: EditAdjustments) {
        if let existing = fetchEditState(photoId: photoId) {
            existing.adjustments = adjustments
        } else {
            let state = EditState(photoId: photoId, adjustments: adjustments)
            modelContext.insert(state)
        }
        try? modelContext.save()
    }

    func fetchEditState(photoId: String) -> EditState? {
        let descriptor = FetchDescriptor<EditState>(
            predicate: #Predicate { $0.photoId == photoId }
        )
        return try? modelContext.fetch(descriptor).first
    }

    func deleteEditState(photoId: String) {
        if let state = fetchEditState(photoId: photoId) {
            modelContext.delete(state)
            try? modelContext.save()
        }
    }

    func hasEdits(photoId: String) -> Bool {
        fetchEditState(photoId: photoId) != nil
    }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -30
```

Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/Models/EditState.swift iFauxto/Models/DataManager.swift iFauxtoTests/EditStateTests.swift && git commit -m "feat: add EditState model with JSON-encoded adjustments + DataManager CRUD"
```

---

### Task 2: Create EditService (CIFilter pipeline)

**Files:**
- Create: `iFauxto/Services/EditService.swift`

- [ ] **Step 1: Create EditService.swift**

Create `iFauxto/Services/EditService.swift`:

```swift
import CoreImage
import CoreImage.CIFilterBuiltins
import UIKit

final class EditService {
    private let context = CIContext(options: [.useSoftwareRenderer: false])

    func applyAdjustments(_ adj: EditAdjustments, to inputImage: CIImage) -> CIImage {
        var image = inputImage

        // Exposure
        if adj.exposure != 0 {
            let filter = CIFilter.exposureAdjust()
            filter.inputImage = image
            filter.ev = adj.exposure * 3.0  // scale to useful range
            image = filter.outputImage ?? image
        }

        // Contrast + Saturation
        if adj.contrast != 0 || adj.saturation != 0 {
            let filter = CIFilter.colorControls()
            filter.inputImage = image
            filter.contrast = 1.0 + adj.contrast  // 0.0 to 2.0
            filter.saturation = 1.0 + adj.saturation  // 0.0 to 2.0
            image = filter.outputImage ?? image
        }

        // Temperature
        if adj.temperature != 0 {
            let filter = CIFilter.temperatureAndTint()
            filter.inputImage = image
            // Neutral is (6500, 0). Shift ±3000K based on slider.
            filter.neutral = CIVector(x: 6500, y: 0)
            filter.targetNeutral = CIVector(x: CGFloat(6500 + adj.temperature * 3000), y: 0)
            image = filter.outputImage ?? image
        }

        // Highlights / Shadows
        if adj.highlights != 0 || adj.shadows != 0 {
            let filter = CIFilter.highlightShadowAdjust()
            filter.inputImage = image
            filter.highlightAmount = 1.0 + adj.highlights  // 0.0 to 2.0
            filter.shadowAmount = adj.shadows * -1.0  // inverted for intuitive slider
            image = filter.outputImage ?? image
        }

        // Vignette
        if adj.vignette > 0 {
            let filter = CIFilter.vignette()
            filter.inputImage = image
            filter.intensity = adj.vignette * 2.0
            filter.radius = 2.0
            image = filter.outputImage ?? image
        }

        // Grain
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
```

- [ ] **Step 2: Build and verify**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -10
```

Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/Services/EditService.swift && git commit -m "feat: add EditService with CIFilter pipeline for all adjustment types"
```

---

### Task 3: Create PhotoEditorView

**Files:**
- Create: `iFauxto/Views/PhotoEditorView.swift`

- [ ] **Step 1: Create PhotoEditorView.swift**

Create `iFauxto/Views/PhotoEditorView.swift`:

```swift
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
                // Preview
                ZStack {
                    Color.black
                    if showingOriginal, let orig = originalImage {
                        let uiImg = UIImage(ciImage: orig)
                        Image(uiImage: uiImg)
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

                // Sliders
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
            .navigationTitle("Edit")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        dataManager.saveEditState(photoId: photoIdentifier, adjustments: adjustments)
                        dismiss()
                    }
                    .fontWeight(.semibold)
                }
                ToolbarItem(placement: .bottomBar) {
                    Button("Reset") {
                        adjustments = EditAdjustments()
                    }
                    .foregroundStyle(.red)
                }
            }
            .task {
                await loadOriginalImage()
                if let existing = dataManager.fetchEditState(photoId: photoIdentifier) {
                    adjustments = existing.adjustments
                }
                updatePreview()
            }
            .onChange(of: adjustments) { _, _ in
                updatePreview()
            }
        }
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
```

- [ ] **Step 2: Build and verify**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -10
```

Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/Views/PhotoEditorView.swift && git commit -m "feat: add PhotoEditorView with VSCO-style slider editing and real-time preview"
```

---

### Task 4: Wire editor into PhotoViewer + add edit badge

**Files:**
- Modify: `iFauxto/Views/PhotoViewer.swift`
- Modify: `iFauxto/Views/PhotoThumbnailView.swift`

- [ ] **Step 1: Add Edit button to PhotoViewer**

In `iFauxto/Views/PhotoViewer.swift`, add `@EnvironmentObject var dataManager: DataManager` and `@State private var showingEditor = false` to PhotoViewer.

Add an Edit button in the overlay area (after the xmark close button overlay, before the counter overlay):

```swift
        .overlay(alignment: .topTrailing) {
            Button {
                showingEditor = true
            } label: {
                Image(systemName: "slider.horizontal.3")
                    .font(.title2)
                    .foregroundStyle(.white, .black.opacity(0.5))
                    .padding(16)
            }
        }
        .sheet(isPresented: $showingEditor) {
            PhotoEditorView(photoIdentifier: photos[currentIndex].id)
        }
```

- [ ] **Step 2: Add edit badge to PhotoThumbnailView**

In `iFauxto/Views/PhotoThumbnailView.swift`, add `@EnvironmentObject var dataManager: DataManager` to the struct.

In the `ZStack`, after the edit mode selection indicator, add:

```swift
            if !isEditMode && dataManager.hasEdits(photoId: photo.id) {
                Image(systemName: "slider.horizontal.3")
                    .font(.caption2)
                    .padding(4)
                    .background(.ultraThinMaterial, in: Circle())
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
                    .padding(4)
            }
```

- [ ] **Step 3: Build and run all tests**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -30
```

Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/Views/PhotoViewer.swift iFauxto/Views/PhotoThumbnailView.swift && git commit -m "feat: wire PhotoEditorView into viewer + add edit badge on thumbnails"
```

---

## Phase 4 Complete

After all 4 tasks:
- EditState model stores non-destructive adjustments as JSON
- EditService applies CIFilter chain with Metal GPU acceleration
- PhotoEditorView provides VSCO-style slider UI with real-time preview
- Long press shows original (before/after)
- Edit button in PhotoViewer, edit badge on thumbnails
- Original PHAsset never modified
