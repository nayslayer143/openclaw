import SwiftUI

/// Greeting / postcard editor. Front = hero photo + headline.
/// Inside (for folded cards) = longer message. Recipient captured for
/// future print-and-mail integration. Persists into PhotoProject.cardContent.
struct CardEditorView: View {
    @Bindable var project: PhotoProject
    @EnvironmentObject var dataManager: DataManager
    @Environment(\.dismiss) private var dismiss

    @State private var content = CardContent()
    @State private var side: Side = .front
    @State private var showingPhotoPicker = false

    enum Side: String, CaseIterable, Identifiable {
        case front, inside, address
        var id: String { rawValue }
        var label: String {
            switch self {
            case .front:   return "Front"
            case .inside:  return "Inside"
            case .address: return "Recipient"
            }
        }
    }

    private var availableSides: [Side] {
        content.cardStyle.hasInside ? Side.allCases : [.front, .address]
    }

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()
            VStack(spacing: 0) {
                topBar
                stylePicker
                sideToggle

                ScrollView {
                    VStack(spacing: 18) {
                        cardPreview
                            .padding(.horizontal, 20)
                            .padding(.top, 16)
                        fields
                    }
                    .padding(.bottom, 40)
                }
            }
        }
        .navigationBarHidden(true)
        .onAppear { loadContent() }
        .sheet(isPresented: $showingPhotoPicker) {
            CollagePhotoPickerSheetStub { identifier in
                content.heroId = identifier
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

    // MARK: - Style picker

    private var stylePicker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(CardStyle.allCases) { style in
                    Button {
                        Haptics.select()
                        content.cardStyle = style
                        if !style.hasInside { side = side == .inside ? .front : side }
                        save()
                    } label: {
                        Text(style.label)
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(content.cardStyle == style ? .white : Theme.Palette.text)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 8)
                            .background(
                                Capsule().fill(content.cardStyle == style ? Theme.Palette.accent : Theme.Palette.bgElevated)
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
    }

    private var sideToggle: some View {
        HStack(spacing: 0) {
            ForEach(availableSides) { s in
                Button {
                    Haptics.tap()
                    side = s
                } label: {
                    Text(s.label)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(side == s ? Theme.Palette.accent : Theme.Palette.textMuted)
                        .padding(.vertical, 10)
                        .frame(maxWidth: .infinity)
                        .background(
                            Rectangle()
                                .fill(side == s ? Theme.Palette.accent.opacity(0.1) : Color.clear)
                        )
                }
                .buttonStyle(.plain)
            }
        }
        .background(Theme.Palette.bgElevated)
        .overlay(
            Rectangle().fill(Theme.Palette.divider).frame(height: 0.5),
            alignment: .bottom
        )
    }

    // MARK: - Card preview

    private var cardPreview: some View {
        GeometryReader { geo in
            let aspect = content.cardStyle.aspect
            let maxWidth = geo.size.width
            let maxHeight = maxWidth * (aspect.height / aspect.width)

            Group {
                switch side {
                case .front:    frontPreview
                case .inside:   insidePreview
                case .address:  addressPreview
                }
            }
            .frame(width: maxWidth, height: maxHeight)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
            )
            .shadow(color: .black.opacity(0.10), radius: 10, x: 0, y: 6)
        }
        .aspectRatio(content.cardStyle.aspect.width / content.cardStyle.aspect.height, contentMode: .fit)
    }

    private var frontPreview: some View {
        Button {
            Haptics.tap()
            showingPhotoPicker = true
        } label: {
            ZStack {
                CalendarSlotView(identifier: content.heroId)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                if !content.headline.isEmpty {
                    LinearGradient(
                        colors: [Color.clear, .black.opacity(0.55)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                    VStack {
                        Spacer()
                        Text(content.headline)
                            .font(.system(size: 22, weight: .bold, design: .serif))
                            .foregroundStyle(.white)
                            .multilineTextAlignment(.center)
                            .padding(20)
                    }
                }
                if content.heroId == nil {
                    VStack(spacing: 10) {
                        Image(systemName: "photo.badge.plus")
                            .font(.system(size: 40, weight: .light))
                            .foregroundStyle(Theme.Palette.textDim)
                        Text("Tap to choose photo")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundStyle(Theme.Palette.textMuted)
                    }
                }
            }
        }
        .buttonStyle(.plain)
    }

    private var insidePreview: some View {
        ZStack {
            Color.white
            VStack {
                Spacer()
                Text(content.insideBody.isEmpty ? "Your message here." : content.insideBody)
                    .font(.system(size: 15, design: .serif))
                    .foregroundStyle(.black.opacity(0.8))
                    .multilineTextAlignment(.center)
                    .padding(30)
                Spacer()
            }
        }
    }

    private var addressPreview: some View {
        ZStack(alignment: .topLeading) {
            Color.white
            VStack(alignment: .leading, spacing: 6) {
                if !content.recipientName.isEmpty {
                    Text(content.recipientName)
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(.black)
                }
                if !content.recipientAddress.isEmpty {
                    Text(content.recipientAddress)
                        .font(.system(size: 13))
                        .foregroundStyle(.black.opacity(0.8))
                } else {
                    Text("Add recipient address")
                        .font(.system(size: 13))
                        .foregroundStyle(Theme.Palette.textMuted)
                }
                Spacer()
            }
            .padding(24)
        }
    }

    // MARK: - Fields

    private var fields: some View {
        VStack(alignment: .leading, spacing: 14) {
            switch side {
            case .front:
                labeledField("Headline", text: Binding(
                    get: { content.headline },
                    set: { content.headline = $0; save() }
                ))
                Button {
                    Haptics.tap()
                    showingPhotoPicker = true
                } label: {
                    HStack {
                        Image(systemName: "photo.badge.plus")
                        Text(content.heroId == nil ? "Choose front photo" : "Replace front photo")
                    }
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(Theme.Palette.accent)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 11)
                    .background(Capsule().fill(Theme.Palette.bgElevated))
                    .overlay(Capsule().strokeBorder(Theme.Palette.stroke, lineWidth: 0.5))
                }
                .buttonStyle(.plain)

            case .inside:
                labeledField("Inside Message", text: Binding(
                    get: { content.insideBody },
                    set: { content.insideBody = $0; save() }
                ), multiline: true)

            case .address:
                labeledField("Recipient Name", text: Binding(
                    get: { content.recipientName },
                    set: { content.recipientName = $0; save() }
                ))
                labeledField("Address", text: Binding(
                    get: { content.recipientAddress },
                    set: { content.recipientAddress = $0; save() }
                ), multiline: true)
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 18)
    }

    private func labeledField(_ label: String, text: Binding<String>, multiline: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label.uppercased())
                .font(.system(size: 11))
                .foregroundStyle(Theme.Palette.textMuted)
                .tracking(0.4)
            if multiline {
                TextField(label, text: text, axis: .vertical)
                    .lineLimit(2...6)
                    .font(.system(size: 15))
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
            } else {
                TextField(label, text: text)
                    .font(.system(size: 15))
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
            }
        }
    }

    // MARK: - State

    private func loadContent() {
        content = project.cardContent
    }

    private func save() {
        project.cardContent = content
        try? dataManager.modelContext.save()
    }

    private func exportPDF() {
        Haptics.success()
        Task {
            let renderer = ImageRenderer(
                content:
                    frontPreview
                        .frame(width: 1050, height: 1500)
            )
            renderer.scale = 2
            if let img = renderer.uiImage {
                _ = PDFExportService.renderPDF(images: [img], title: project.name)
            }
        }
    }
}
