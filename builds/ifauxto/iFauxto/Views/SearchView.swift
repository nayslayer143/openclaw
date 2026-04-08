import SwiftUI

struct SearchView: View {
    let searchService: SearchService
    @EnvironmentObject var photoKitService: PhotoKitService
    @EnvironmentObject var indexingManager: IndexingManager
    @Environment(\.dismiss) private var dismiss

    @State private var query = ""
    @State private var results: [SearchResult] = []
    @State private var suggestions: [String] = []
    @FocusState private var searchFocused: Bool

    private let columns = [
        GridItem(.flexible(), spacing: 2),
        GridItem(.flexible(), spacing: 2),
        GridItem(.flexible(), spacing: 2)
    ]

    private let popularTags = ["beach", "people", "food", "screenshots", "night", "dog"]

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                topBar
                searchBar

                if indexingManager.isIndexing {
                    indexingBanner
                }

                contentSection
            }
        }
        .onAppear {
            searchFocused = true
        }
    }

    // MARK: - Top bar

    private var topBar: some View {
        ZStack {
            Text("Search")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            HStack {
                Spacer()
                Button {
                    Haptics.tap()
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

    // MARK: - Search bar

    private var searchBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(Theme.Palette.textMuted)
            TextField("Search photos", text: $query)
                .font(.system(size: 15))
                .foregroundStyle(Theme.Palette.text)
                .focused($searchFocused)
                .submitLabel(.search)
            if !query.isEmpty {
                Button {
                    query = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 16))
                        .foregroundStyle(Theme.Palette.textDim)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Color(red: 0.918, green: 0.918, blue: 0.937))
        )
        .padding(.horizontal, 16)
        .padding(.top, 10)
        .padding(.bottom, 12)
        .onChange(of: query) { _, newValue in
            results = searchService.search(query: newValue)
            suggestions = searchService.suggestions(prefix: newValue)
        }
    }

    // MARK: - Indexing banner

    private var indexingBanner: some View {
        HStack(spacing: 10) {
            ProgressView()
                .controlSize(.small)
                .tint(Theme.Palette.accent)
            Text("Learning your library… \(Int(indexingManager.progress * 100))%")
                .font(.system(size: 12))
                .foregroundStyle(Theme.Palette.textMuted)
            Spacer()
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 8)
        .background(Theme.Palette.bgElevated)
        .overlay(
            Rectangle().fill(Theme.Palette.divider).frame(height: 0.5),
            alignment: .bottom
        )
    }

    // MARK: - Content

    @ViewBuilder
    private var contentSection: some View {
        if query.isEmpty {
            suggestionsView
        } else if results.isEmpty {
            noResultsView
        } else {
            resultsGrid
        }
    }

    private var suggestionsView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("SUGGESTIONS")
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.Palette.textMuted)
                    .tracking(0.4)
                    .padding(.horizontal, 32)
                    .padding(.top, 4)

                FlowLayout(spacing: 8) {
                    ForEach(popularTags, id: \.self) { tag in
                        Button {
                            Haptics.select()
                            query = tag
                        } label: {
                            Text(tag)
                                .font(.system(size: 14, weight: .medium))
                                .foregroundStyle(Theme.Palette.accent)
                                .padding(.horizontal, 14)
                                .padding(.vertical, 8)
                                .background(
                                    Capsule()
                                        .fill(Theme.Palette.bgElevated)
                                )
                                .overlay(
                                    Capsule()
                                        .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
                                )
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 24)

                Spacer(minLength: 40)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.bottom, 40)
        }
    }

    private var noResultsView: some View {
        VStack(spacing: 12) {
            Spacer(minLength: 60)
            Image(systemName: "magnifyingglass")
                .font(.system(size: 48, weight: .light))
                .foregroundStyle(Theme.Palette.textDim)
            Text("No Results")
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            Text("Nothing matched \"\(query)\"")
                .font(.system(size: 14))
                .foregroundStyle(Theme.Palette.textMuted)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    private var resultsGrid: some View {
        ScrollView {
            LazyVGrid(columns: columns, spacing: 2) {
                ForEach(results) { result in
                    SearchThumbnailView(identifier: result.id)
                }
            }
            .padding(2)
        }
    }
}

// MARK: - Simple flow layout (for tag chips)

private struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxWidth {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: maxWidth, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x: CGFloat = bounds.minX
        var y: CGFloat = bounds.minY
        var rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            subview.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}

private struct SearchThumbnailView: View {
    let identifier: String
    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var thumbnail: UIImage?

    var body: some View {
        GeometryReader { geo in
            Group {
                if let img = thumbnail {
                    Image(uiImage: img)
                        .resizable()
                        .scaledToFill()
                        .frame(width: geo.size.width, height: geo.size.width)
                        .clipped()
                } else {
                    Rectangle()
                        .fill(Color(red: 0.918, green: 0.918, blue: 0.937))
                        .overlay(
                            ProgressView()
                                .controlSize(.small)
                                .tint(Theme.Palette.textDim)
                        )
                }
            }
        }
        .aspectRatio(1, contentMode: .fit)
        .task(id: identifier) {
            thumbnail = await photoKitService.loadThumbnail(
                for: identifier,
                targetSize: CGSize(width: 300, height: 300)
            )
        }
    }
}
