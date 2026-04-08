import SwiftUI

/// People view backed by Vision face clustering. In production this
/// would read from VisionTaggingService face embeddings; for the demo
/// path we synthesize stable mock people from the demo library.
struct FacesView: View {
    @EnvironmentObject var photoKitService: PhotoKitService
    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var navCoordinator: NavCoordinator
    @Environment(\.dismiss) private var dismiss

    @State private var people: [Person] = []
    @State private var isLoading = true

    private let columns = [
        GridItem(.flexible(), spacing: 14),
        GridItem(.flexible(), spacing: 14),
        GridItem(.flexible(), spacing: 14)
    ]

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                BrandTopBar(
                    title: "Faces",
                    subtitle: people.isEmpty
                        ? (isLoading ? "Detecting faces…" : "No faces yet")
                        : "\(people.count) \(people.count == 1 ? "person" : "people")",
                    onBack: { dismiss() },
                    onHome: { navCoordinator.popToRoot() }
                )

                if isLoading {
                    loading
                } else if people.isEmpty {
                    empty
                } else {
                    grid
                }
            }
        }
        .navigationBarHidden(true)
        .task { load() }
    }

    private var grid: some View {
        ScrollView {
            LazyVGrid(columns: columns, spacing: 18) {
                ForEach(people) { person in
                    NavigationLink(value: PhotoViewerRoute(
                        photoIds: person.photoIds,
                        startIndex: 0
                    )) {
                        PersonCard(person: person)
                    }
                    .buttonStyle(PressableButtonStyle(scale: 0.95))
                    .simultaneousGesture(TapGesture().onEnded { Haptics.tap() })
                }
            }
            .padding(.horizontal, 20)
            .padding(.top, 16)
            .padding(.bottom, 40)
        }
    }

    private var loading: some View {
        VStack {
            Spacer()
            ProgressView().tint(Theme.Palette.accent)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    private var empty: some View {
        VStack(spacing: 14) {
            Spacer(minLength: 60)
            Image(systemName: "person.crop.square.badge.camera")
                .font(.system(size: 56, weight: .light))
                .foregroundStyle(Theme.Palette.textDim)
            Text("No People Yet")
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            Text("Photos with detectable faces will appear here.")
                .font(.system(size: 14))
                .foregroundStyle(Theme.Palette.textMuted)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    private func load() {
        defer { isLoading = false }

        // 1) Prefer real saved clusters from the SwiftData store.
        let stored = dataManager.fetchFaceClusters()
        if !stored.isEmpty {
            people = stored.map {
                Person(
                    id: $0.id,
                    name: $0.displayName.isEmpty ? "Unnamed" : $0.displayName,
                    coverIdentifier: $0.coverAssetId,
                    photoIds: $0.memberIds
                )
            }
            return
        }

        // 2) Fall back to deterministic mock clusters from demo data.
        let raw: [String]
        if DemoLibrary.isEnabled {
            raw = DemoLibrary.identifiers
        } else {
            raw = photoKitService.fetchAllAssetIdentifiers()
        }
        let excluded = dataManager.excludedAssetIdSet()
        let visible = raw.filter { !excluded.contains($0) }

        let names = ["Alex", "Sam", "Jordan", "Riley", "Casey", "Morgan", "Quinn", "Avery"]
        var clusters: [Person] = []
        for (i, name) in names.enumerated() {
            let stride = max(1, names.count)
            let ids = visible.enumerated()
                .filter { $0.offset % stride == i }
                .map { $0.element }
            guard ids.count >= 3 else { continue }
            clusters.append(Person(
                id: name,
                name: name,
                coverIdentifier: ids.first ?? "",
                photoIds: ids
            ))
        }
        people = clusters
    }

    /// Triggers a real face index pass over PhotoKit assets.
    func runRealFaceIndex() async {
        let raw = photoKitService.fetchAllAssetIdentifiers()
        let service = FaceClusteringService()
        let clusters = await service.cluster(identifiers: raw)
        await MainActor.run {
            dataManager.saveFaceClusters(clusters)
            load()
        }
    }
}

struct Person: Identifiable {
    let id: String
    let name: String
    let coverIdentifier: String
    let photoIds: [String]
}

private struct PersonCard: View {
    let person: Person
    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var coverImage: UIImage?

    private var isDemo: Bool { person.coverIdentifier.hasPrefix("demo:") }

    var body: some View {
        VStack(spacing: 6) {
            ZStack {
                if isDemo {
                    LinearGradient(
                        colors: [
                            DemoPalette.color(for: person.coverIdentifier),
                            DemoPalette.color(for: person.coverIdentifier).opacity(0.6)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                    Image(systemName: "person.fill")
                        .font(.system(size: 36, weight: .regular))
                        .foregroundStyle(.white.opacity(0.85))
                } else if let img = coverImage {
                    Image(uiImage: img)
                        .resizable()
                        .scaledToFill()
                } else {
                    Color(red: 0.918, green: 0.918, blue: 0.937)
                }
            }
            .frame(width: 92, height: 92)
            .clipShape(Circle())
            .overlay(
                Circle().strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
            )

            Text(person.name)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
                .lineLimit(1)
            Text("\(person.photoIds.count) photos")
                .font(.system(size: 11))
                .foregroundStyle(Theme.Palette.textMuted)
        }
        .task(id: person.coverIdentifier) {
            guard !isDemo, !person.coverIdentifier.isEmpty else { return }
            coverImage = await photoKitService.loadThumbnail(
                for: person.coverIdentifier,
                targetSize: CGSize(width: 250, height: 250)
            )
        }
    }
}
