import SwiftUI
import Photos

struct ChronologicalFeedView: View {
    @EnvironmentObject var photoKitService: PhotoKitService

    @State private var assetIdentifiers: [String] = []
    @State private var allIdentifiers: [String] = []
    @State private var isLoading = true
    @State private var loadedCount = 0
    private let pageSize = 100

    private let columns = [GridItem(.adaptive(minimum: 110), spacing: 2)]

    var body: some View {
        NavigationStack {
            ScrollView {
                if isLoading {
                    ProgressView("Loading photos...")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .padding(.top, 100)
                } else if assetIdentifiers.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "photo.on.rectangle")
                            .font(.system(size: 48))
                            .foregroundStyle(.secondary)
                        Text("No Photos")
                            .font(.title3.weight(.medium))
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.top, 80)
                } else {
                    LazyVGrid(columns: columns, spacing: 2) {
                        ForEach(assetIdentifiers, id: \.self) { identifier in
                            FeedThumbnailView(identifier: identifier)
                        }

                        if loadedCount < allIdentifiers.count {
                            Color.clear
                                .frame(height: 1)
                                .onAppear { loadNextPage() }
                        }
                    }
                    .padding(2)
                }
            }
            .navigationTitle("All Photos")
            .task {
                allIdentifiers = photoKitService.fetchAllAssetIdentifiers()
                loadNextPage()
                isLoading = false
            }
        }
    }

    private func loadNextPage() {
        let nextBatch = Array(allIdentifiers.dropFirst(loadedCount).prefix(pageSize))
        assetIdentifiers.append(contentsOf: nextBatch)
        loadedCount = assetIdentifiers.count
    }
}

private struct FeedThumbnailView: View {
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
