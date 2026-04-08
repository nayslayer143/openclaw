import SwiftUI

/// Multi-page photobook editor with themes, page templates, drag-to-fill
/// placeholders, and per-page captions. Persists into PhotoProject.bookPages.
struct BookEditorView: View {
    @Bindable var project: PhotoProject
    @EnvironmentObject var dataManager: DataManager
    @Environment(\.dismiss) private var dismiss

    @State private var pages: [BookPage] = []
    @State private var currentIndex: Int = 0
    @State private var theme: BookTheme = .classic
    @State private var showingThemeSheet = false
    @State private var showingTemplateSheet = false
    @State private var pickingSlot: SlotPick?

    struct SlotPick: Identifiable, Hashable {
        let pageIndex: Int
        let slotIndex: Int
        var id: String { "\(pageIndex)-\(slotIndex)" }
    }

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()
            VStack(spacing: 0) {
                topBar

                ScrollView {
                    VStack(spacing: 18) {
                        themeStrip
                        canvas
                            .padding(.horizontal, 16)
                        pageStrip
                        captionField
                        pageActions
                    }
                    .padding(.top, 14)
                    .padding(.bottom, 40)
                }
            }
        }
        .navigationBarHidden(true)
        .onAppear { loadPages() }
        .sheet(isPresented: $showingThemeSheet) {
            ThemePickerSheet(selected: $theme, onPick: { saveTheme() })
                .presentationDetents([.medium])
        }
        .sheet(isPresented: $showingTemplateSheet) {
            TemplatePickerSheet { template in
                pages[currentIndex].template = template
                // Resize slots to match the new template.
                let existing = pages[currentIndex].slots
                var next = Array(repeating: String?.none, count: template.slotCount)
                for i in 0..<min(existing.count, next.count) { next[i] = existing[i] }
                pages[currentIndex].slots = next
                save()
            }
            .presentationDetents([.medium])
        }
        .sheet(item: $pickingSlot) { slot in
            CollagePhotoPickerSheetStub { identifier in
                pages[slot.pageIndex].slots[slot.slotIndex] = identifier
                save()
            }
        }
    }

    // MARK: - Top bar

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
                        Text("Projects")
                    }
                    .font(.system(size: 17))
                    .foregroundStyle(Theme.Palette.accent)
                }
                .buttonStyle(.plain)
                Spacer()
                Menu {
                    Button("Change Theme") { showingThemeSheet = true }
                    Button("Change Layout") { showingTemplateSheet = true }
                    Divider()
                    Button("Export PDF") { exportPDF() }
                } label: {
                    Image(systemName: "ellipsis.circle")
                        .font(.system(size: 19, weight: .semibold))
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

    // MARK: - Theme strip

    private var themeStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(BookTheme.allCases) { t in
                    Button {
                        Haptics.select()
                        theme = t
                        saveTheme()
                    } label: {
                        Text(t.label)
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(theme == t ? .white : Theme.Palette.text)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 8)
                            .background(
                                Capsule().fill(theme == t ? Theme.Palette.accent : Theme.Palette.bgElevated)
                            )
                            .overlay(
                                Capsule().strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
        }
    }

    // MARK: - Canvas

    private var canvas: some View {
        let page = pages.indices.contains(currentIndex) ? pages[currentIndex] : BookPage.blank(template: .fullBleed)
        return VStack(spacing: 0) {
            Text(page.isCover ? "COVER" : "PAGE \(currentIndex)")
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(Theme.Palette.textMuted)
                .tracking(0.6)
                .padding(.bottom, 6)

            BookPageCanvas(page: page, onPickSlot: { slotIdx in
                pickingSlot = SlotPick(pageIndex: currentIndex, slotIndex: slotIdx)
            })
        }
    }

    // MARK: - Page strip

    private var pageStrip: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("PAGES")
                .font(.system(size: 11))
                .foregroundStyle(Theme.Palette.textMuted)
                .tracking(0.4)
                .padding(.horizontal, 20)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(Array(pages.enumerated()), id: \.element.id) { index, page in
                        Button {
                            Haptics.tap()
                            currentIndex = index
                        } label: {
                            VStack(spacing: 4) {
                                BookPageCanvas(page: page, onPickSlot: { _ in })
                                    .frame(width: 58, height: 78)
                                    .allowsHitTesting(false)
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 4)
                                            .strokeBorder(
                                                index == currentIndex ? Theme.Palette.accent : Color.clear,
                                                lineWidth: 2
                                            )
                                    )
                                Text(page.isCover ? "Cover" : "\(index)")
                                    .font(.system(size: 10, weight: .medium))
                                    .foregroundStyle(index == currentIndex ? Theme.Palette.accent : Theme.Palette.textMuted)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                    Button {
                        addPage()
                    } label: {
                        VStack(spacing: 4) {
                            RoundedRectangle(cornerRadius: 4)
                                .strokeBorder(Theme.Palette.accent.opacity(0.5), style: StrokeStyle(lineWidth: 1.5, dash: [4]))
                                .frame(width: 58, height: 78)
                                .overlay(
                                    Image(systemName: "plus")
                                        .font(.system(size: 18, weight: .semibold))
                                        .foregroundStyle(Theme.Palette.accent)
                                )
                            Text("Add")
                                .font(.system(size: 10, weight: .medium))
                                .foregroundStyle(Theme.Palette.accent)
                        }
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 16)
            }
        }
    }

    // MARK: - Caption + actions

    private var captionField: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("CAPTION")
                .font(.system(size: 11))
                .foregroundStyle(Theme.Palette.textMuted)
                .tracking(0.4)
                .padding(.horizontal, 20)
            TextField("Add caption", text: Binding(
                get: { pages.indices.contains(currentIndex) ? pages[currentIndex].caption : "" },
                set: {
                    guard pages.indices.contains(currentIndex) else { return }
                    pages[currentIndex].caption = $0
                    save()
                }
            ), axis: .vertical)
            .lineLimit(1...4)
            .font(.system(size: 14))
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(Theme.Palette.bgElevated)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
            )
            .padding(.horizontal, 16)
        }
    }

    private var pageActions: some View {
        HStack(spacing: 10) {
            Button {
                Haptics.tap()
                showingTemplateSheet = true
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "rectangle.3.offgrid")
                    Text("Layout")
                }
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(Theme.Palette.accent)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(Capsule().fill(Theme.Palette.bgElevated))
                .overlay(Capsule().strokeBorder(Theme.Palette.stroke, lineWidth: 0.5))
            }
            .buttonStyle(.plain)

            if pages.indices.contains(currentIndex), !pages[currentIndex].isCover {
                Button {
                    Haptics.warning()
                    deleteCurrentPage()
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "trash")
                        Text("Delete Page")
                    }
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(.red)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(Capsule().fill(Theme.Palette.bgElevated))
                    .overlay(Capsule().strokeBorder(Color.red.opacity(0.3), lineWidth: 0.5))
                }
                .buttonStyle(.plain)
            }
            Spacer()
        }
        .padding(.horizontal, 16)
    }

    // MARK: - State

    private func loadPages() {
        pages = project.bookPages
        if pages.isEmpty {
            pages = [
                .cover(),
                .blank(template: .fullBleed),
                .blank(template: .twoUp),
                .blank(template: .threeUp),
                .blank(template: .textPage)
            ]
            save()
        }
        if let themeSaved = BookTheme(rawValue: project.theme) {
            theme = themeSaved
        }
    }

    private func save() {
        project.bookPages = pages
        try? dataManager.modelContext.save()
    }

    private func saveTheme() {
        project.theme = theme.rawValue
        try? dataManager.modelContext.save()
    }

    private func addPage() {
        Haptics.tap()
        pages.append(.blank(template: .fullBleed))
        currentIndex = pages.count - 1
        save()
    }

    private func deleteCurrentPage() {
        guard pages.indices.contains(currentIndex), !pages[currentIndex].isCover else { return }
        pages.remove(at: currentIndex)
        currentIndex = min(currentIndex, pages.count - 1)
        save()
    }

    private func exportPDF() {
        Haptics.success()
        // Render each page as a 612x792 (US Letter) UIImage, hand to PDFExportService.
        Task {
            var images: [UIImage] = []
            for page in pages {
                if let img = await BookPageRenderer.render(page: page, size: CGSize(width: 1224, height: 1584)) {
                    images.append(img)
                }
            }
            _ = PDFExportService.renderPDF(images: images, title: project.name)
        }
    }
}

// MARK: - Page canvas

struct BookPageCanvas: View {
    let page: BookPage
    let onPickSlot: (Int) -> Void

    var body: some View {
        GeometryReader { geo in
            ZStack {
                Color.white
                content(in: geo.size)
            }
            .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
            )
            .shadow(color: .black.opacity(0.08), radius: 4, x: 0, y: 2)
        }
        .aspectRatio(0.77, contentMode: .fit)
    }

    @ViewBuilder
    private func content(in size: CGSize) -> some View {
        switch page.template {
        case .cover:
            coverLayout(in: size)
        case .fullBleed:
            slot(at: 0, frame: CGRect(origin: .zero, size: size))
        case .twoUp:
            VStack(spacing: 4) {
                slot(at: 0, frame: CGRect(x: 0, y: 0, width: size.width, height: size.height / 2 - 2))
                slot(at: 1, frame: CGRect(x: 0, y: size.height / 2 + 2, width: size.width, height: size.height / 2 - 2))
            }
        case .threeUp:
            VStack(spacing: 4) {
                slot(at: 0, frame: CGRect(x: 0, y: 0, width: size.width, height: size.height * 0.55 - 2))
                HStack(spacing: 4) {
                    slot(at: 1, frame: CGRect(x: 0, y: 0, width: size.width / 2 - 2, height: size.height * 0.45 - 2))
                    slot(at: 2, frame: CGRect(x: size.width / 2 + 2, y: 0, width: size.width / 2 - 2, height: size.height * 0.45 - 2))
                }
                .frame(height: size.height * 0.45 - 2)
            }
        case .mixed4:
            VStack(spacing: 4) {
                HStack(spacing: 4) {
                    slot(at: 0, frame: .zero)
                    slot(at: 1, frame: .zero)
                }
                HStack(spacing: 4) {
                    slot(at: 2, frame: .zero)
                    slot(at: 3, frame: .zero)
                }
            }
        case .textPage:
            VStack {
                Spacer()
                Text(page.caption.isEmpty ? "Your dedication here." : page.caption)
                    .font(.system(size: 14, design: .serif))
                    .foregroundStyle(.black.opacity(0.75))
                    .multilineTextAlignment(.center)
                    .padding(24)
                Spacer()
            }
        }
    }

    private func coverLayout(in size: CGSize) -> some View {
        ZStack {
            slot(at: 0, frame: CGRect(origin: .zero, size: size))
            LinearGradient(
                colors: [Color.clear, .black.opacity(0.55)],
                startPoint: .top,
                endPoint: .bottom
            )
            .allowsHitTesting(false)
            VStack {
                Spacer()
                Text(page.caption.isEmpty ? "Title" : page.caption)
                    .font(.system(size: 14, weight: .bold, design: .serif))
                    .foregroundStyle(.white)
                    .padding(.bottom, 10)
            }
        }
    }

    @ViewBuilder
    private func slot(at index: Int, frame: CGRect) -> some View {
        BookSlotView(
            identifier: page.slots.indices.contains(index) ? page.slots[index] : nil,
            onTap: { onPickSlot(index) }
        )
    }
}

private struct BookSlotView: View {
    let identifier: String?
    let onTap: () -> Void

    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var thumbnail: UIImage?

    private var isDemo: Bool { identifier?.hasPrefix("demo:") ?? false }

    var body: some View {
        Button(action: { Haptics.tap(); onTap() }) {
            ZStack {
                if let identifier {
                    if isDemo {
                        LinearGradient(
                            colors: [
                                DemoPalette.color(for: identifier),
                                DemoPalette.color(for: identifier).opacity(0.65)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                        Image(systemName: DemoPalette.icon(for: identifier))
                            .font(.system(size: 16, weight: .light))
                            .foregroundStyle(.white.opacity(0.85))
                    } else if let img = thumbnail {
                        Image(uiImage: img).resizable().scaledToFill()
                    } else {
                        Color(red: 0.92, green: 0.92, blue: 0.94)
                    }
                } else {
                    ZStack {
                        Color(red: 0.96, green: 0.96, blue: 0.97)
                        Image(systemName: "plus")
                            .font(.system(size: 14, weight: .regular))
                            .foregroundStyle(Theme.Palette.textDim)
                    }
                }
            }
            .clipped()
            .clipShape(RoundedRectangle(cornerRadius: 2))
        }
        .buttonStyle(.plain)
        .task(id: identifier ?? "") {
            guard let identifier, !isDemo else { return }
            thumbnail = await photoKitService.loadThumbnail(
                for: identifier,
                targetSize: CGSize(width: 300, height: 300)
            )
        }
    }
}

// MARK: - Theme sheet

private struct ThemePickerSheet: View {
    @Binding var selected: BookTheme
    let onPick: () -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()
            VStack(spacing: 0) {
                HStack {
                    Text("Theme")
                        .font(.system(size: 17, weight: .semibold))
                    Spacer()
                    Button("Done") { dismiss() }
                        .foregroundStyle(Theme.Palette.accent)
                }
                .padding(16)
                .overlay(
                    Rectangle().fill(Theme.Palette.divider).frame(height: 0.5),
                    alignment: .bottom
                )

                ScrollView {
                    VStack(spacing: 8) {
                        ForEach(BookTheme.allCases) { t in
                            Button {
                                Haptics.select()
                                selected = t
                                onPick()
                            } label: {
                                HStack {
                                    Text(t.label)
                                        .font(.system(size: 16, weight: .medium))
                                        .foregroundStyle(Theme.Palette.text)
                                    Spacer()
                                    if selected == t {
                                        Image(systemName: "checkmark")
                                            .foregroundStyle(Theme.Palette.accent)
                                    }
                                }
                                .padding(.horizontal, 16)
                                .padding(.vertical, 14)
                                .background(
                                    RoundedRectangle(cornerRadius: 10)
                                        .fill(Theme.Palette.bgElevated)
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(16)
                }
            }
        }
    }
}

// MARK: - Template sheet

private struct TemplatePickerSheet: View {
    let onPick: (BookTemplate) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()
            VStack(spacing: 0) {
                HStack {
                    Text("Layout")
                        .font(.system(size: 17, weight: .semibold))
                    Spacer()
                    Button("Cancel") { dismiss() }
                        .foregroundStyle(Theme.Palette.accent)
                }
                .padding(16)
                .overlay(
                    Rectangle().fill(Theme.Palette.divider).frame(height: 0.5),
                    alignment: .bottom
                )

                ScrollView {
                    LazyVGrid(columns: [
                        GridItem(.flexible(), spacing: 10),
                        GridItem(.flexible(), spacing: 10),
                        GridItem(.flexible(), spacing: 10)
                    ], spacing: 10) {
                        ForEach(BookTemplate.allCases.filter { $0 != .cover }) { t in
                            Button {
                                Haptics.select()
                                onPick(t)
                                dismiss()
                            } label: {
                                VStack(spacing: 6) {
                                    Image(systemName: t.icon)
                                        .font(.system(size: 28, weight: .light))
                                        .foregroundStyle(Theme.Palette.accent)
                                        .frame(height: 40)
                                    Text(t.label)
                                        .font(.system(size: 11, weight: .semibold))
                                        .foregroundStyle(Theme.Palette.text)
                                }
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 14)
                                .background(
                                    RoundedRectangle(cornerRadius: 10)
                                        .fill(Theme.Palette.bgElevated)
                                )
                                .overlay(
                                    RoundedRectangle(cornerRadius: 10)
                                        .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(16)
                }
            }
        }
    }
}

// MARK: - Photo picker stub (wraps the generic library picker)

struct CollagePhotoPickerSheetStub: View {
    let onPick: (String) -> Void
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var photoKitService: PhotoKitService
    @EnvironmentObject var dataManager: DataManager

    @State private var ids: [String] = []
    private let columns = Array(repeating: GridItem(.flexible(), spacing: 3), count: 4)

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()
            VStack(spacing: 0) {
                HStack {
                    Text("Pick a Photo")
                        .font(.system(size: 17, weight: .semibold))
                    Spacer()
                    Button("Cancel") { dismiss() }
                        .foregroundStyle(Theme.Palette.accent)
                }
                .padding(16)
                .overlay(
                    Rectangle().fill(Theme.Palette.divider).frame(height: 0.5),
                    alignment: .bottom
                )

                ScrollView {
                    LazyVGrid(columns: columns, spacing: 3) {
                        ForEach(ids, id: \.self) { identifier in
                            Button {
                                Haptics.success()
                                onPick(identifier)
                                dismiss()
                            } label: {
                                BookSlotView(identifier: identifier, onTap: {})
                                    .aspectRatio(1, contentMode: .fit)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(3)
                }
            }
        }
        .onAppear {
            let raw = DemoLibrary.isEnabled
                ? DemoLibrary.identifiers
                : photoKitService.fetchAllAssetIdentifiers()
            ids = raw.filter { !dataManager.excludedAssetIdSet().contains($0) }
        }
    }
}

// MARK: - Renderer

enum BookPageRenderer {
    @MainActor
    static func render(page: BookPage, size: CGSize) async -> UIImage? {
        let hostingView = BookPageCanvas(page: page, onPickSlot: { _ in })
            .frame(width: size.width, height: size.height)
        let renderer = ImageRenderer(content: hostingView)
        renderer.scale = 2
        return renderer.uiImage
    }
}
