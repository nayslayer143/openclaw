import SwiftUI

/// First-class view of date-bucketed photo events. Each event is a card
/// with a cover thumbnail, the bucket name (Today / Yesterday / month),
/// and the photo count. Tap → opens the photo viewer at the first photo.
struct EventsView: View {
    @EnvironmentObject var photoKitService: PhotoKitService
    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var navCoordinator: NavCoordinator
    @Environment(\.dismiss) private var dismiss

    @State private var groups: [PhotoDateGroup] = []

    private let columns = [
        GridItem(.flexible(), spacing: 12),
        GridItem(.flexible(), spacing: 12)
    ]

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                topBar
                if groups.isEmpty {
                    empty
                } else {
                    list
                }
            }
        }
        .navigationBarHidden(true)
        .task { loadGroups() }
    }

    private var topBar: some View {
        BrandTopBar(
            title: "Events",
            subtitle: groups.isEmpty ? nil : "\(groups.count) event\(groups.count == 1 ? "" : "s")",
            onBack: { dismiss() },
            onHome: { navCoordinator.popToRoot() }
        )
    }

    private var list: some View {
        ScrollView {
            LazyVGrid(columns: columns, spacing: 12) {
                ForEach(groups) { group in
                    NavigationLink(value: PhotoViewerRoute(
                        photoIds: group.identifiers,
                        startIndex: 0
                    )) {
                        EventCard(group: group)
                    }
                    .buttonStyle(PressableButtonStyle(scale: 0.97))
                    .simultaneousGesture(TapGesture().onEnded { Haptics.tap() })
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 40)
        }
    }

    private var empty: some View {
        VStack(spacing: 14) {
            Spacer(minLength: 60)
            Image(systemName: "calendar")
                .font(.system(size: 56, weight: .light))
                .foregroundStyle(Theme.Palette.textDim)
            Text("No Events")
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            Text("Add photos and they'll be grouped by date.")
                .font(.system(size: 14))
                .foregroundStyle(Theme.Palette.textMuted)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    private func loadGroups() {
        let raw: [String]
        if DemoLibrary.isEnabled {
            raw = DemoLibrary.identifiers
        } else {
            raw = photoKitService.fetchAllAssetIdentifiers()
        }
        let excluded = dataManager.excludedAssetIdSet()
        groups = PhotoDateGrouper.group(raw.filter { !excluded.contains($0) })
    }
}

private struct EventCard: View {
    let group: PhotoDateGroup
    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var coverImage: UIImage?

    private var coverIdentifier: String { group.identifiers.first ?? "" }
    private var isDemo: Bool { coverIdentifier.hasPrefix("demo:") }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ZStack {
                if isDemo {
                    LinearGradient(
                        colors: [
                            DemoPalette.color(for: coverIdentifier),
                            DemoPalette.color(for: coverIdentifier).opacity(0.65)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                    Image(systemName: DemoPalette.icon(for: coverIdentifier))
                        .font(.system(size: 36, weight: .light))
                        .foregroundStyle(.white.opacity(0.85))
                } else if let img = coverImage {
                    Image(uiImage: img)
                        .resizable()
                        .scaledToFill()
                } else {
                    Rectangle().fill(Color(red: 0.918, green: 0.918, blue: 0.937))
                        .overlay(ProgressView().controlSize(.small).tint(Theme.Palette.textDim))
                }
            }
            .aspectRatio(1, contentMode: .fill)
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
            )
            .overlay(
                Text("\(group.identifiers.count)")
                    .font(.system(size: 11, weight: .semibold).monospacedDigit())
                    .foregroundStyle(.white)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(Capsule().fill(.black.opacity(0.55)))
                    .padding(8),
                alignment: .topTrailing
            )

            VStack(alignment: .leading, spacing: 1) {
                Text(group.title)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(Theme.Palette.text)
                    .lineLimit(1)
                Text("\(group.identifiers.count) \(group.identifiers.count == 1 ? "photo" : "photos")")
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.Palette.textMuted)
            }
        }
        .task(id: coverIdentifier) {
            guard !isDemo, !coverIdentifier.isEmpty else { return }
            coverImage = await photoKitService.loadThumbnail(
                for: coverIdentifier,
                targetSize: CGSize(width: 600, height: 600)
            )
        }
    }
}
