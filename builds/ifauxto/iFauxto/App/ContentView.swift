import SwiftUI
import SwiftData
import Photos

struct ContentView: View {
    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var photoKitService: PhotoKitService
    @Query private var allSettings: [AppSettings]
    @State private var hasCheckedAuth = false
    @State private var showOnboarding = false

    private var settings: AppSettings {
        allSettings.first ?? dataManager.getOrCreateSettings()
    }

    var body: some View {
        Group {
            if showOnboarding {
                OnboardingView {
                    withAnimation(Theme.Motion.soft) {
                        showOnboarding = false
                    }
                }
                .transition(.opacity)
            } else {
                mainView
                    .transition(.opacity.combined(with: .scale(scale: 0.98)))
            }
        }
        .animation(Theme.Motion.soft, value: showOnboarding)
        .animation(Theme.Motion.soft, value: settings.homeViewMode)
        .task {
            // Photo permission is requested lazily from views that actually
            // need it (chronological feed, import, photo picker) — not here.
            let dm: DataManager = dataManager
            #if DEBUG
            seedDebugDataIfNeeded(dm)
            #endif
            if !dm.getOrCreateSettings().hasCompletedOnboarding {
                withAnimation(Theme.Motion.soft) {
                    showOnboarding = true
                }
            }
            hasCheckedAuth = true
        }
    }

    #if DEBUG
    @MainActor
    private func seedDebugDataIfNeeded(_ dm: DataManager) {
        let args = ProcessInfo.processInfo.arguments
        let existing = dm.fetchFolders(parentId: nil)
        if existing.isEmpty {
            let names = ["Travel", "Family", "Screenshots", "Food", "Everything Else"]
            for name in names {
                dm.createFolder(name: name)
            }
        }
        // Seed real PHAsset identifiers into the first folder so the
        // photo grid pipeline can be visually verified without going
        // through PHPicker. Requires Photos auth.
        if args.contains("-seedPhotos") {
            let folders = dm.fetchFolders(parentId: nil)
            if let target = folders.first(where: { $0.name == "Travel" }) ?? folders.first {
                let existingPhotos = dm.fetchPhotos(in: target)
                if existingPhotos.isEmpty {
                    let identifiers = photoKitService.fetchAllAssetIdentifiers()
                    if !identifiers.isEmpty {
                        dm.addPhotos(assetIdentifiers: identifiers, to: target)
                    }
                }
            }
        }
        // Synthetic photos for visual preview without real PhotoKit access.
        // Identifiers prefixed with "demo:" render as colored placeholders.
        if args.contains("-seedDemoPhotos") {
            let folders = dm.fetchFolders(parentId: nil)
            if let target = folders.first(where: { $0.name == "Travel" }) ?? folders.first {
                let existingPhotos = dm.fetchPhotos(in: target)
                if existingPhotos.isEmpty {
                    let identifiers = (0..<24).map { "demo:travel:\($0)" }
                    dm.addPhotos(assetIdentifiers: identifiers, to: target)
                }
                // Subfolders + photos so the horizontal subfolder strip
                // and the mixed grid both render.
                let existingSubs = dm.fetchFolders(parentId: target.id)
                if existingSubs.isEmpty {
                    let subNames = ["Japan 2026", "Iceland", "Coast Roadtrip", "City Breaks"]
                    for (i, name) in subNames.enumerated() {
                        let sub = dm.createFolder(name: name, parentId: target.id)
                        let ids = (0..<(6 + i * 2)).map { "demo:sub:\(name):\($0)" }
                        dm.addPhotos(assetIdentifiers: ids, to: sub)
                    }
                }
            }
            if let family = folders.first(where: { $0.name == "Family" }) {
                if dm.fetchPhotos(in: family).isEmpty {
                    let identifiers = (0..<12).map { "demo:family:\($0)" }
                    dm.addPhotos(assetIdentifiers: identifiers, to: family)
                }
            }
            if let screenshots = folders.first(where: { $0.name == "Screenshots" }) {
                if dm.fetchPhotos(in: screenshots).isEmpty {
                    let identifiers = (0..<9).map { "demo:screens:\($0)" }
                    dm.addPhotos(assetIdentifiers: identifiers, to: screenshots)
                }
            }
            if let food = folders.first(where: { $0.name == "Food" }) {
                if dm.fetchPhotos(in: food).isEmpty {
                    let identifiers = (0..<6).map { "demo:food:\($0)" }
                    dm.addPhotos(assetIdentifiers: identifiers, to: food)
                }
            }
        }
        let s = dm.getOrCreateSettings()
        if args.contains("-showOnboarding") {
            // Force the onboarding flow for screenshots.
            s.hasCompletedOnboarding = false
            dm.saveSettings()
        } else if !s.hasCompletedOnboarding {
            s.hasCompletedOnboarding = true
            dm.saveSettings()
        }
        if args.contains("-mode") {
            if let idx = args.firstIndex(of: "-mode"), idx + 1 < args.count {
                let mode = args[idx + 1]
                if mode == "chrono" || mode == "chronological" {
                    s.homeViewMode = "chronological_feed"
                    dm.saveSettings()
                } else if mode == "folders" {
                    s.homeViewMode = "folder_list"
                    dm.saveSettings()
                }
            }
        }
    }
    #endif

    @ViewBuilder
    private var mainView: some View {
        switch settings.homeViewMode {
        case "chronological_feed":
            ChronologicalFeedView()
        case "last_opened":
            LastOpenedRouter()
        default:
            HomeView()
        }
    }
}

/// When the user picked "Last Opened" as their entry mode, this router
/// pushes the most recently opened folder onto the nav stack on launch.
/// Falls back to HomeView if there's nothing to restore.
struct LastOpenedRouter: View {
    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var navCoordinator: NavCoordinator
    @State private var didRestore = false

    var body: some View {
        HomeView()
            .onAppear {
                guard !didRestore else { return }
                didRestore = true
                let id = dataManager.getOrCreateSettings().lastOpenedViewId
                guard let id,
                      let folder = dataManager.fetchFolders(parentId: nil)
                        .first(where: { $0.id == id }) else { return }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                    navCoordinator.path.append(folder)
                }
            }
    }
}

struct PhotoPermissionView: View {
    let onRequest: () -> Void

    var body: some View {
        ZStack {
            Theme.Palette.bg.ignoresSafeArea()
            VStack(spacing: 24) {
                ZStack {
                    Circle()
                        .fill(Theme.Palette.accent.opacity(0.15))
                        .frame(width: 140, height: 140)
                        .blur(radius: 20)
                    Image(systemName: "photo.on.rectangle.angled")
                        .font(.system(size: 58, weight: .light))
                        .foregroundStyle(Theme.Palette.accent)
                        .symbolRenderingMode(.hierarchical)
                }

                VStack(spacing: 10) {
                    Text("Your photos,\nunder your control.")
                        .font(Theme.Font.display(28))
                        .foregroundStyle(Theme.Palette.text)
                        .multilineTextAlignment(.center)
                    Text("iFauxto needs access to your Photos library to get started.")
                        .font(Theme.Font.body(14))
                        .foregroundStyle(Theme.Palette.textMuted)
                        .multilineTextAlignment(.center)
                }

                Button {
                    Haptics.medium()
                    onRequest()
                } label: {
                    Text("Grant Access")
                        .font(Theme.Font.body(16, weight: .bold))
                        .foregroundStyle(Color.black)
                        .padding(.vertical, 14)
                        .padding(.horizontal, 44)
                        .background(
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .fill(Theme.Palette.accent)
                        )
                        .shadow(color: Theme.Palette.accentGlow, radius: 18, x: 0, y: 8)
                }
            }
            .padding(40)
        }
    }
}
