import SwiftUI

/// Lightweight grid-based collage editor. The user picks a layout
/// preset, then taps any cell to assign one of their photos. Cells
/// can be drag-swapped. The final composition is saved back onto the
/// PhotoProject.
struct CollageEditorView: View {
    @Bindable var project: PhotoProject
    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var navCoordinator: NavCoordinator
    @Environment(\.dismiss) private var dismiss

    @State private var slots: [String?] = []
    @State private var layout: CollageLayout = .grid3x2
    @State private var pickingSlotIndex: Int?
    @State private var draggingSlotIndex: Int?

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                topBar

                ScrollView {
                    VStack(spacing: 18) {
                        layoutPicker
                        canvas
                            .padding(.horizontal, 16)
                        instructions
                    }
                    .padding(.top, 16)
                    .padding(.bottom, 40)
                }
            }
        }
        .navigationBarHidden(true)
        .onAppear { loadSlots() }
        .sheet(item: Binding<SlotIndex?>(
            get: { pickingSlotIndex.map { SlotIndex(index: $0) } },
            set: { pickingSlotIndex = $0?.index }
        )) { wrapped in
            CollagePhotoPickerSheet { identifier in
                slots[wrapped.index] = identifier
                save()
            }
        }
    }

    private var topBar: some View {
        ZStack {
            Text(project.name)
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
                .lineLimit(1)
            HStack {
                Button { Haptics.tap(); dismiss() } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "chevron.left")
                        Text("Back")
                    }
                    .font(.system(size: 17))
                    .foregroundStyle(Theme.Palette.accent)
                }
                .buttonStyle(.plain)
                Spacer()
                Button {
                    Haptics.success()
                    save()
                    dismiss()
                } label: {
                    Text("Done")
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
    }

    private var layoutPicker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(CollageLayout.allCases) { l in
                    Button {
                        Haptics.select()
                        switchLayout(to: l)
                    } label: {
                        VStack(spacing: 6) {
                            ZStack {
                                RoundedRectangle(cornerRadius: 8, style: .continuous)
                                    .fill(Theme.Palette.bgElevated)
                                LayoutThumbnail(layout: l)
                                    .padding(6)
                            }
                            .frame(width: 56, height: 56)
                            .overlay(
                                RoundedRectangle(cornerRadius: 8, style: .continuous)
                                    .strokeBorder(
                                        layout == l ? Theme.Palette.accent : Theme.Palette.stroke,
                                        lineWidth: layout == l ? 2 : 0.5
                                    )
                            )
                            Text(l.label)
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundStyle(Theme.Palette.text)
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
        }
    }

    private var canvas: some View {
        let cols = layout.columns
        let gridItems = Array(repeating: GridItem(.flexible(), spacing: 4), count: cols)
        return LazyVGrid(columns: gridItems, spacing: 4) {
            ForEach(slots.indices, id: \.self) { index in
                CollageSlot(
                    identifier: slots[index],
                    onTap: {
                        Haptics.tap()
                        pickingSlotIndex = index
                    }
                )
                .draggable("\(index)") {
                    CollageSlot(identifier: slots[index], onTap: {})
                        .frame(width: 80, height: 80)
                        .opacity(0.85)
                }
                .dropDestination(for: String.self) { items, _ in
                    guard let raw = items.first, let from = Int(raw), from != index else {
                        return false
                    }
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                        slots.swapAt(from, index)
                    }
                    save()
                    return true
                }
                .aspectRatio(1, contentMode: .fit)
            }
        }
        .padding(8)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color.white)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
        )
        .shadow(color: .black.opacity(0.06), radius: 8, x: 0, y: 4)
    }

    private var instructions: some View {
        Text("Tap a slot to add a photo · drag photos to swap")
            .font(.system(size: 12))
            .foregroundStyle(Theme.Palette.textMuted)
            .padding(.horizontal, 32)
            .multilineTextAlignment(.center)
    }

    // MARK: - Persistence

    private func loadSlots() {
        let stored = project.photoIds
        let count = layout.cells
        if stored.count == count {
            slots = stored.map { $0 }
        } else {
            slots = Array(repeating: nil, count: count)
            for (i, id) in stored.prefix(count).enumerated() {
                slots[i] = id
            }
        }
    }

    private func switchLayout(to next: CollageLayout) {
        let stored = slots.compactMap { $0 }
        layout = next
        slots = Array(repeating: nil, count: next.cells)
        for (i, id) in stored.prefix(next.cells).enumerated() {
            slots[i] = id
        }
        save()
    }

    private func save() {
        project.photoIds = slots.compactMap { $0 }
        project.updatedAt = Date()
        try? dataManager.modelContext.save()
    }
}

// Hashable wrapper so .sheet(item:) can drive presentation off an Int.
private struct SlotIndex: Identifiable, Hashable { let index: Int; var id: Int { index } }

// MARK: - Collage layouts

enum CollageLayout: String, CaseIterable, Identifiable {
    case grid2x2, grid3x2, grid3x3, grid4x3
    var id: String { rawValue }
    var columns: Int {
        switch self {
        case .grid2x2: return 2
        case .grid3x2, .grid3x3: return 3
        case .grid4x3: return 4
        }
    }
    var rows: Int {
        switch self {
        case .grid2x2: return 2
        case .grid3x2: return 2
        case .grid3x3: return 3
        case .grid4x3: return 3
        }
    }
    var cells: Int { columns * rows }
    var label: String {
        switch self {
        case .grid2x2: return "2×2"
        case .grid3x2: return "3×2"
        case .grid3x3: return "3×3"
        case .grid4x3: return "4×3"
        }
    }
}

// MARK: - Slot

private struct CollageSlot: View {
    let identifier: String?
    let onTap: () -> Void

    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var thumbnail: UIImage?

    private var isDemo: Bool { identifier?.hasPrefix("demo:") ?? false }

    var body: some View {
        Button(action: onTap) {
            ZStack {
                if let identifier {
                    if isDemo {
                        ZStack {
                            LinearGradient(
                                colors: [
                                    DemoPalette.color(for: identifier),
                                    DemoPalette.color(for: identifier).opacity(0.65)
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                            Image(systemName: DemoPalette.icon(for: identifier))
                                .font(.system(size: 22, weight: .light))
                                .foregroundStyle(.white.opacity(0.85))
                        }
                    } else if let img = thumbnail {
                        Image(uiImage: img)
                            .resizable()
                            .scaledToFill()
                    } else {
                        Color(red: 0.918, green: 0.918, blue: 0.937)
                    }
                } else {
                    ZStack {
                        Rectangle()
                            .fill(Color(red: 0.95, green: 0.95, blue: 0.96))
                        Image(systemName: "plus")
                            .font(.system(size: 22, weight: .regular))
                            .foregroundStyle(Theme.Palette.textDim)
                    }
                }
            }
            .clipped()
            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
            )
        }
        .buttonStyle(.plain)
        .task(id: identifier ?? "") {
            guard let identifier, !isDemo else { return }
            thumbnail = await photoKitService.loadThumbnail(
                for: identifier,
                targetSize: CGSize(width: 400, height: 400)
            )
        }
    }
}

// MARK: - Layout thumbnail

private struct LayoutThumbnail: View {
    let layout: CollageLayout

    var body: some View {
        let gridItems = Array(repeating: GridItem(.flexible(), spacing: 2), count: layout.columns)
        LazyVGrid(columns: gridItems, spacing: 2) {
            ForEach(0..<layout.cells, id: \.self) { _ in
                Rectangle()
                    .fill(Theme.Palette.accent.opacity(0.3))
                    .aspectRatio(1, contentMode: .fit)
                    .clipShape(RoundedRectangle(cornerRadius: 1.5))
            }
        }
    }
}

// MARK: - Photo picker sheet

private struct CollagePhotoPickerSheet: View {
    let onPick: (String) -> Void
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var photoKitService: PhotoKitService
    @EnvironmentObject var dataManager: DataManager

    @State private var ids: [String] = []
    private let columns = [
        GridItem(.flexible(), spacing: 3),
        GridItem(.flexible(), spacing: 3),
        GridItem(.flexible(), spacing: 3),
        GridItem(.flexible(), spacing: 3)
    ]

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()
            VStack(spacing: 0) {
                topBar
                ScrollView {
                    LazyVGrid(columns: columns, spacing: 3) {
                        ForEach(ids, id: \.self) { identifier in
                            Button {
                                Haptics.success()
                                onPick(identifier)
                                dismiss()
                            } label: {
                                CollageSlot(identifier: identifier, onTap: {})
                                    .aspectRatio(1, contentMode: .fit)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(3)
                }
            }
        }
        .onAppear { loadIds() }
    }

    private var topBar: some View {
        ZStack {
            Text("Pick a Photo")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            HStack {
                Button("Cancel") { dismiss() }
                    .font(.system(size: 17))
                    .foregroundStyle(Theme.Palette.accent)
                Spacer()
            }
            .padding(.horizontal, 16)
            .buttonStyle(.plain)
        }
        .frame(height: 44)
        .padding(.top, 8)
        .padding(.bottom, 6)
        .background(Theme.Palette.bg)
        .overlay(
            Rectangle().fill(Theme.Palette.divider).frame(height: 0.5),
            alignment: .bottom
        )
    }

    private func loadIds() {
        let raw = DemoLibrary.isEnabled
            ? DemoLibrary.identifiers
            : photoKitService.fetchAllAssetIdentifiers()
        let excluded = dataManager.excludedAssetIdSet()
        ids = raw.filter { !excluded.contains($0) }
    }
}
