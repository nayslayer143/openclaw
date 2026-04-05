import SwiftUI

struct SearchView: View {
    let searchService: SearchService
    @EnvironmentObject var photoKitService: PhotoKitService
    @EnvironmentObject var indexingManager: IndexingManager

    @State private var query = ""
    @State private var results: [SearchResult] = []
    @State private var suggestions: [String] = []

    private let columns = [GridItem(.adaptive(minimum: 110), spacing: 2)]

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if indexingManager.isIndexing {
                    VStack(spacing: 4) {
                        ProgressView(value: indexingManager.progress)
                        Text("Learning your library... \(Int(indexingManager.progress * 100))% done")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.horizontal, 16)
                    .padding(.top, 8)
                }

                if results.isEmpty && !query.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 36))
                            .foregroundStyle(.secondary)
                        Text("No results for \"\(query)\"")
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if results.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 36))
                            .foregroundStyle(.tertiary)
                        Text("Find anything. Instantly.")
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
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
            .navigationTitle("Search")
            .searchable(text: $query, prompt: "Search photos...")
            .searchSuggestions {
                ForEach(suggestions, id: \.self) { suggestion in
                    Text(suggestion)
                        .searchCompletion(suggestion)
                }
            }
            .onChange(of: query) { _, newValue in
                results = searchService.search(query: newValue)
                suggestions = searchService.suggestions(prefix: newValue)
            }
        }
    }
}

private struct SearchThumbnailView: View {
    let identifier: String
    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var thumbnail: UIImage?
    private let size: CGFloat = 120

    var body: some View {
        Group {
            if let img = thumbnail {
                Image(uiImage: img)
                    .resizable()
                    .scaledToFill()
            } else {
                Rectangle()
                    .fill(Color(.systemGray5))
                    .overlay(ProgressView())
            }
        }
        .frame(width: size, height: size)
        .clipped()
        .task(id: identifier) {
            thumbnail = await photoKitService.loadThumbnail(
                for: identifier,
                targetSize: CGSize(width: size * 2, height: size * 2)
            )
        }
    }
}
