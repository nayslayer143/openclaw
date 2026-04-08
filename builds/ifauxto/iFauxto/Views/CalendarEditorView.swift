import SwiftUI

/// 12-month photo calendar editor. Each month has a hero photo (top half)
/// and a day grid with optional per-day photos (bottom half). Persists
/// into PhotoProject.calendarPages.
struct CalendarEditorView: View {
    @Bindable var project: PhotoProject
    @EnvironmentObject var dataManager: DataManager
    @Environment(\.dismiss) private var dismiss

    @State private var pages: [CalendarPage] = []
    @State private var currentIndex: Int = 0
    @State private var pickingTarget: CalendarPickTarget?

    enum CalendarPickTarget: Identifiable, Hashable {
        case hero(pageIndex: Int)
        case day(pageIndex: Int, day: Int)
        var id: String {
            switch self {
            case .hero(let i): return "hero-\(i)"
            case .day(let i, let d): return "day-\(i)-\(d)"
            }
        }
    }

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()
            VStack(spacing: 0) {
                topBar
                monthStrip
                ScrollView {
                    VStack(spacing: 18) {
                        if pages.indices.contains(currentIndex) {
                            monthSpread(page: pages[currentIndex])
                        }
                    }
                    .padding(.top, 16)
                    .padding(.bottom, 40)
                }
            }
        }
        .navigationBarHidden(true)
        .onAppear { loadPages() }
        .sheet(item: $pickingTarget) { target in
            CollagePhotoPickerSheetStub { identifier in
                switch target {
                case .hero(let pi):
                    pages[pi].heroId = identifier
                case .day(let pi, let d):
                    pages[pi].dayPhotos[d] = identifier
                }
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
                    Button("Export PDF") { exportPDF() }
                } label: {
                    Image(systemName: "ellipsis.circle")
                        .font(.system(size: 19, weight: .semibold))
                        .foregroundStyle(Theme.Palette.accent)
                }
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

    // MARK: - Month strip

    private var monthStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(Array(pages.enumerated()), id: \.element.id) { index, page in
                    Button {
                        Haptics.tap()
                        currentIndex = index
                    } label: {
                        Text(page.monthName())
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(currentIndex == index ? .white : Theme.Palette.text)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 8)
                            .background(
                                Capsule().fill(currentIndex == index ? Theme.Palette.accent : Theme.Palette.bgElevated)
                            )
                            .overlay(
                                Capsule().strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
                            )
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

    // MARK: - Month spread

    private func monthSpread(page: CalendarPage) -> some View {
        VStack(spacing: 0) {
            heroSection(page: page)
            dayGrid(page: page)
        }
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
        )
        .shadow(color: .black.opacity(0.06), radius: 8, x: 0, y: 4)
        .padding(.horizontal, 16)
    }

    private func heroSection(page: CalendarPage) -> some View {
        Button {
            Haptics.tap()
            pickingTarget = .hero(pageIndex: currentIndex)
        } label: {
            ZStack {
                CalendarSlotView(identifier: page.heroId)
                    .frame(height: 220)
                LinearGradient(
                    colors: [Color.clear, .black.opacity(0.55)],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .allowsHitTesting(false)
                VStack {
                    Spacer()
                    HStack {
                        VStack(alignment: .leading, spacing: 0) {
                            Text(page.monthName())
                                .font(.system(size: 28, weight: .bold, design: .serif))
                                .foregroundStyle(.white)
                            Text("\(page.year)")
                                .font(.system(size: 14, weight: .medium))
                                .foregroundStyle(.white.opacity(0.85))
                        }
                        Spacer()
                    }
                    .padding(16)
                }
            }
        }
        .buttonStyle(.plain)
    }

    private func dayGrid(page: CalendarPage) -> some View {
        let days = page.daysInMonth()
        let firstWeekday = page.firstWeekday()
        let leadingBlanks = firstWeekday
        let totalCells = leadingBlanks + days
        let rows = Int((Double(totalCells) / 7).rounded(.up))

        return VStack(spacing: 2) {
            HStack {
                ForEach(["S", "M", "T", "W", "T", "F", "S"], id: \.self) { d in
                    Text(d)
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(Theme.Palette.textMuted)
                        .frame(maxWidth: .infinity)
                }
            }
            .padding(.top, 10)

            LazyVGrid(
                columns: Array(repeating: GridItem(.flexible(), spacing: 2), count: 7),
                spacing: 2
            ) {
                ForEach(0..<(rows * 7), id: \.self) { cell in
                    let dayNum = cell - leadingBlanks + 1
                    if dayNum >= 1 && dayNum <= days {
                        dayCell(page: page, day: dayNum)
                    } else {
                        Rectangle()
                            .fill(Color.clear)
                            .aspectRatio(1, contentMode: .fit)
                    }
                }
            }
            .padding(6)
        }
    }

    private func dayCell(page: CalendarPage, day: Int) -> some View {
        Button {
            Haptics.tap()
            pickingTarget = .day(pageIndex: currentIndex, day: day)
        } label: {
            ZStack(alignment: .topLeading) {
                if let id = page.dayPhotos[day] {
                    CalendarSlotView(identifier: id)
                } else {
                    Rectangle()
                        .fill(Color(red: 0.97, green: 0.97, blue: 0.98))
                }
                Text("\(day)")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(page.dayPhotos[day] != nil ? .white : Theme.Palette.text)
                    .padding(4)
                    .shadow(color: page.dayPhotos[day] != nil ? .black.opacity(0.6) : .clear, radius: 2)
            }
            .aspectRatio(1, contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 3))
            .overlay(
                RoundedRectangle(cornerRadius: 3)
                    .strokeBorder(Theme.Palette.divider, lineWidth: 0.5)
            )
        }
        .buttonStyle(.plain)
    }

    // MARK: - State

    private func loadPages() {
        pages = project.calendarPages
        if pages.isEmpty {
            let year = Calendar.current.component(.year, from: Date())
            pages = (1...12).map { month in
                CalendarPage(month: month, year: year)
            }
            save()
        }
    }

    private func save() {
        project.calendarPages = pages
        try? dataManager.modelContext.save()
    }

    private func exportPDF() {
        Haptics.success()
        // Render each month as a UIImage via ImageRenderer.
        Task {
            var images: [UIImage] = []
            for (index, _) in pages.enumerated() {
                if let img = await CalendarPageRenderer.render(
                    page: pages[index],
                    size: CGSize(width: 1224, height: 1584)
                ) {
                    images.append(img)
                }
            }
            _ = PDFExportService.renderPDF(images: images, title: project.name)
        }
    }
}

struct CalendarSlotView: View {
    let identifier: String?
    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var image: UIImage?

    private var isDemo: Bool { identifier?.hasPrefix("demo:") ?? false }

    var body: some View {
        Group {
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
                } else if let img = image {
                    Image(uiImage: img).resizable().scaledToFill()
                } else {
                    Color(red: 0.92, green: 0.92, blue: 0.94)
                }
            } else {
                Color(red: 0.96, green: 0.96, blue: 0.97)
            }
        }
        .clipped()
        .task(id: identifier ?? "") {
            guard let identifier, !isDemo else { return }
            image = await photoKitService.loadThumbnail(
                for: identifier,
                targetSize: CGSize(width: 400, height: 400)
            )
        }
    }
}

enum CalendarPageRenderer {
    @MainActor
    static func render(page: CalendarPage, size: CGSize) async -> UIImage? {
        // Simple placeholder: render a branded page header.
        let renderer = ImageRenderer(
            content:
                VStack(spacing: 16) {
                    ZStack {
                        LinearGradient(
                            colors: [Theme.Palette.accent.opacity(0.2), Theme.Palette.accent.opacity(0.05)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                        Text("\(page.monthName()) \(page.year)")
                            .font(.system(size: 36, weight: .bold, design: .serif))
                            .foregroundStyle(.black)
                    }
                    .frame(width: size.width - 80, height: 200)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                }
                .frame(width: size.width, height: size.height)
                .background(Color.white)
        )
        renderer.scale = 2
        return renderer.uiImage
    }
}
