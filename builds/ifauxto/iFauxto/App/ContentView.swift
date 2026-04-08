import SwiftUI
import SwiftData
import Photos
import UIKit

struct ContentView: View {
    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var photoKitService: PhotoKitService
    @ObservedObject var userSession = UserSession.shared
    @Query private var allSettings: [AppSettings]
    @State private var hasCheckedAuth = false
    @State private var showOnboarding = false
    @State private var authDecided = false

    private var settings: AppSettings {
        allSettings.first ?? dataManager.getOrCreateSettings()
    }

    /// True if the user opted into guest mode in a prior launch.
    private var hasGuestSession: Bool {
        UserDefaults.standard.string(forKey: "iFauxto.activeUserId") == "_local"
    }

    var body: some View {
        Group {
            if !authDecided && !userSession.isAuthenticated && !hasGuestSession {
                SignInView { authDecided = true }
                    .transition(.opacity)
            } else if showOnboarding {
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
        .animation(Theme.Motion.soft, value: authDecided)
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
        // The synthetic library lives in DemoLibrary (100 photos).
        // We do NOT seed folders — they should start empty so the user
        // can build albums by selecting from the photo feed.
        // The flag here just ensures the library is enabled.

        if args.contains("-seedFavorites") {
            // Pre-favorite a handful of demo photos so the Favorites
            // smart album has content for screenshot/preview.
            let toFavorite = (0..<8).map { "demo:travel:\($0 * 5)" }
            for id in toFavorite {
                let meta = dm.getOrCreateMeta(for: id)
                if !meta.isFavorite {
                    meta.isFavorite = true
                }
            }
            dm.saveSettings()
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
        // On iPad / Mac the sidebar shell takes over and ignores the
        // chosen home mode (sidebar is always the entry surface).
        if UIDevice.current.userInterfaceIdiom == .pad {
            SidebarShell()
        } else {
            switch settings.homeViewMode {
            case "chronological_feed":
                ChronologicalFeedView()
            case "last_opened":
                LastOpenedRouter(modeKey: "last_opened")
            case "custom_view":
                LastOpenedRouter(modeKey: "custom_view")
            default:
                HomeView()
            }
        }
    }
}

/// Routes the user straight into a folder on launch. Backs both the
/// "Last Opened" and "Custom View" (pinned) home modes — only the
/// settings key it reads from differs.
struct LastOpenedRouter: View {
    let modeKey: String  // "last_opened" or "custom_view"

    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var navCoordinator: NavCoordinator
    @State private var didRestore = false

    var body: some View {
        HomeView()
            .onAppear {
                guard !didRestore else { return }
                didRestore = true
                let s = dataManager.getOrCreateSettings()
                let targetId = (modeKey == "custom_view") ? s.pinnedViewId : s.lastOpenedViewId
                guard let id = targetId else { return }
                // Search across both root and nested folders.
                guard let folder = findFolder(id: id) else { return }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                    navCoordinator.path.append(folder)
                }
            }
    }

    private func findFolder(id: String) -> Folder? {
        var stack = dataManager.fetchFolders(parentId: nil)
        while let next = stack.popLast() {
            if next.id == id { return next }
            stack.append(contentsOf: dataManager.fetchFolders(parentId: next.id))
        }
        return nil
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
