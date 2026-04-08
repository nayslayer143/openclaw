import SwiftUI

/// Generic list view for any saved SmartAlbum. Shows the resolved photos
/// in a 3-column grid that opens the PhotoViewer on tap.
struct SmartListView: View {
    let id: String
    let title: String

    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var photoKitService: PhotoKitService
    @EnvironmentObject var navCoordinator: NavCoordinator
    @Environment(\.dismiss) private var dismiss

    @State private var photoIds: [String] = []

    private let columns = [
        GridItem(.flexible(), spacing: 3),
        GridItem(.flexible(), spacing: 3),
        GridItem(.flexible(), spacing: 3)
    ]

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()
            VStack(spacing: 0) {
                BrandTopBar(
                    title: title,
                    subtitle: "\(photoIds.count) \(photoIds.count == 1 ? "photo" : "photos")",
                    onBack: { dismiss() },
                    onHome: { navCoordinator.popToRoot() }
                )

                if photoIds.isEmpty {
                    empty
                } else {
                    grid
                }
            }
        }
        .navigationBarHidden(true)
        .task { resolve() }
    }

    private var grid: some View {
        ScrollView {
            LazyVGrid(columns: columns, spacing: 3) {
                ForEach(Array(photoIds.enumerated()), id: \.element) { index, identifier in
                    NavigationLink(value: PhotoViewerRoute(
                        photoIds: photoIds,
                        startIndex: index
                    )) {
                        SmartListThumbnail(identifier: identifier)
                    }
                    .buttonStyle(PressableButtonStyle(scale: 0.97))
                    .simultaneousGesture(TapGesture().onEnded { Haptics.tap() })
                }
            }
            .padding(.horizontal, 12)
            .padding(.top, 8)
            .padding(.bottom, 40)
        }
    }

    private var empty: some View {
        VStack(spacing: 14) {
            Spacer(minLength: 60)
            Image(systemName: "rectangle.dashed")
                .font(.system(size: 56, weight: .light))
                .foregroundStyle(Theme.Palette.textDim)
            Text("No Matching Photos")
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            Text("Add photos that match the rules of this smart album.")
                .font(.system(size: 14))
                .foregroundStyle(Theme.Palette.textMuted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    private func resolve() {
        let albums = dataManager.fetchSmartAlbums()
        guard let album = albums.first(where: { $0.id == id }) else {
            photoIds = []
            return
        }
        let candidates = DemoLibrary.isEnabled
            ? DemoLibrary.identifiers
            : photoKitService.fetchAllAssetIdentifiers()
        let excluded = dataManager.excludedAssetIdSet()
        photoIds = dataManager.evaluateSmartAlbum(
            album,
            candidates: candidates.filter { !excluded.contains($0) }
        )
    }
}

private struct SmartListThumbnail: View {
    let identifier: String
    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var image: UIImage?

    private var isDemo: Bool { identifier.hasPrefix("demo:") }

    var body: some View {
        GeometryReader { geo in
            Group {
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
                    .frame(width: geo.size.width, height: geo.size.width)
                } else if let img = image {
                    Image(uiImage: img)
                        .resizable()
                        .scaledToFill()
                        .frame(width: geo.size.width, height: geo.size.width)
                        .clipped()
                } else {
                    Color(red: 0.918, green: 0.918, blue: 0.937)
                        .frame(width: geo.size.width, height: geo.size.width)
                }
            }
        }
        .aspectRatio(1, contentMode: .fit)
        .task(id: identifier) {
            guard !isDemo else { return }
            image = await photoKitService.loadThumbnail(
                for: identifier,
                targetSize: CGSize(width: 300, height: 300)
            )
        }
    }
}
