import SwiftUI
import Photos

struct ChronologicalFeedView: View {
    @EnvironmentObject var photoKitService: PhotoKitService
    @EnvironmentObject var dataManager: DataManager
    @Environment(\.searchService) var searchService

    @State private var assetIdentifiers: [String] = []
    @State private var allIdentifiers: [String] = []
    @State private var isLoading = true
    @State private var loadedCount = 0
    @State private var showingSettings = false
    @State private var showingSearch = false
    @State private var showingViewModeSwitcher = false
    @State private var showingModeChangeNotice = false

    private let pageSize = 100
    private let columns = [
        GridItem(.flexible(), spacing: 3),
        GridItem(.flexible(), spacing: 3),
        GridItem(.flexible(), spacing: 3)
    ]

    var body: some View {
        NavigationStack {
            ZStack(alignment: .top) {
                Theme.Palette.bg.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 0) {
                        BrandHeader(
                            title: "iFauxto",
                            subtitle: chronoSubtitle
                        ) {
                            HStack(spacing: 10) {
                                GlassIconButton(systemName: "gearshape.fill") {
                                    showingSettings = true
                                }
                                GlassIconButton(systemName: "square.grid.2x2.fill") {
                                    showingViewModeSwitcher = true
                                }
                            }
                        }

                        HeroSearchField(placeholder: "Find anything. Instantly.") {
                            showingSearch = true
                        }
                        .padding(.bottom, 16)

                        if isLoading {
                            loadingState
                        } else if assetIdentifiers.isEmpty {
                            emptyState
                        } else {
                            grid
                        }
                    }
                    .padding(.bottom, 40)
                }
                .scrollIndicators(.hidden)

                if showingModeChangeNotice {
                    toastBanner
                        .transition(.move(edge: .top).combined(with: .opacity))
                }
            }
            .navigationBarHidden(true)
            .confirmationDialog("Home View", isPresented: $showingViewModeSwitcher, titleVisibility: .visible) {
                Button("Folders") { switchMode(to: "folder_list") }
                Button("Chronological Feed") { switchMode(to: "chronological_feed") }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("Choose what you see when you open iFauxto.")
            }
            .sheet(isPresented: $showingSettings) {
                SettingsView()
            }
            .sheet(isPresented: $showingSearch) {
                if let service = searchService {
                    SearchView(searchService: service)
                }
            }
            .task {
                allIdentifiers = photoKitService.fetchAllAssetIdentifiers()
                loadNextPage()
                withAnimation(Theme.Motion.soft) {
                    isLoading = false
                }
            }
        }
    }

    private var chronoSubtitle: String {
        if isLoading { return "Loading your library…" }
        if assetIdentifiers.isEmpty { return "No photos yet" }
        return "\(allIdentifiers.count) photos, newest first"
    }

    // MARK: - Grid

    private var grid: some View {
        LazyVGrid(columns: columns, spacing: 3) {
            ForEach(assetIdentifiers, id: \.self) { identifier in
                FeedThumbnailView(identifier: identifier)
            }
            if loadedCount < allIdentifiers.count {
                Color.clear
                    .frame(height: 1)
                    .onAppear { loadNextPage() }
            }
        }
        .padding(.horizontal, 12)
        .padding(.top, 4)
    }

    // MARK: - Loading state

    private var loadingState: some View {
        VStack(spacing: 18) {
            Spacer(minLength: 80)
            ProgressView()
                .controlSize(.large)
                .tint(Theme.Palette.accent)
            Text("Warming up your library")
                .font(Theme.Font.body(14, weight: .medium))
                .foregroundStyle(Theme.Palette.textMuted)
            Spacer()
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 40)
    }

    // MARK: - Empty state

    private var emptyState: some View {
        VStack(spacing: 16) {
            Spacer(minLength: 60)
            Image(systemName: "photo.stack")
                .font(.system(size: 56, weight: .light))
                .foregroundStyle(Theme.Palette.accent)
                .symbolRenderingMode(.hierarchical)
            Text("Your library is empty")
                .font(Theme.Font.display(24))
                .foregroundStyle(Theme.Palette.text)
            Text("Add photos in the Photos app and they'll appear here.")
                .font(Theme.Font.body(14))
                .foregroundStyle(Theme.Palette.textMuted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Toast

    private var toastBanner: some View {
        HStack(spacing: 10) {
            Image(systemName: "checkmark.circle.fill")
                .foregroundStyle(Theme.Palette.accent)
            Text("Switched. Relaunch to see folders.")
                .font(Theme.Font.body(13, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(.ultraThinMaterial)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(Theme.Palette.accent.opacity(0.4), lineWidth: 1)
        )
        .padding(.top, 60)
        .padding(.horizontal, 20)
    }

    // MARK: - Helpers

    private func switchMode(to mode: String) {
        let settings = dataManager.getOrCreateSettings()
        settings.homeViewMode = mode
        dataManager.saveSettings()
        Haptics.success()
        withAnimation(Theme.Motion.snappy) {
            showingModeChangeNotice = true
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.4) {
            withAnimation(Theme.Motion.soft) {
                showingModeChangeNotice = false
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
                        .frame(width: geo.size.width, height: geo.size.width)
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 2, style: .continuous))
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
