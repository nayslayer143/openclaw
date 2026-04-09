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
    @State private var didBootstrap = false

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
            } else if !didBootstrap {
                // Hold the main view until seed + auto-import have run so
                // HomeView sees the final folder list on its first onAppear.
                Color(red: 0.949, green: 0.949, blue: 0.969).ignoresSafeArea()
                    .overlay(ProgressView().tint(Color(red: 0.0, green: 0.478, blue: 1.0)))
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
        .animation(Theme.Motion.soft, value: didBootstrap)
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
            didBootstrap = true
        }
    }

    /// Scans the per-user Imports directory for any local photos
    /// that haven't been registered yet and auto-adds them to a
    /// "My Favorites" album.
    ///
    /// Identifiers are stored as `local:Imports/<filename>` — a
    /// RELATIVE path resolved against the current user's Documents
    /// directory at load time. Absolute file:// paths would break on
    /// every reinstall because the iOS Application container UUID
    /// changes and the stored path becomes dead.
    @MainActor
    private func autoImportLooseFiles(_ dm: DataManager) {
        let userDir = UserSession.shared.activeUserDirectory
        let importsDir = userDir.appendingPathComponent("Imports", isDirectory: true)
        guard FileManager.default.fileExists(atPath: importsDir.path) else { return }

        let files = (try? FileManager.default.contentsOfDirectory(
            at: importsDir,
            includingPropertiesForKeys: nil
        )) ?? []

        let imageExtensions: Set<String> = ["jpg", "jpeg", "heic", "heif", "png", "gif"]
        let imageFiles = files.filter {
            imageExtensions.contains($0.pathExtension.lowercased())
        }
        guard !imageFiles.isEmpty else { return }

        // Find or create the "My Favorites" album
        let folderName = "My Favorites"
        let roots = dm.fetchFolders(parentId: nil)
        let album = roots.first(where: { $0.name == folderName })
            ?? dm.createFolder(name: folderName)

        // Dedupe against a fresh fetch (relationship accessor is stale
        // on cold launches).
        let existingIds: Set<String> = Set(dm.fetchPhotos(in: album).map(\.id))
        let newIdentifiers: [String] = imageFiles.compactMap { url in
            let id = "local:Imports/\(url.lastPathComponent)"
            return existingIds.contains(id) ? nil : id
        }
        guard !newIdentifiers.isEmpty else { return }

        dm.addPhotos(assetIdentifiers: newIdentifiers, to: album)
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

        // On every launch: scan Documents/users/_local/Imports for any
        // file:// photos that aren't yet registered in a folder, and
        // auto-create a "My Favorites" album containing them. Lets us
        // drop photos into the sim container outside the app and have
        // them show up on next launch. Only runs when the folder exists.
        autoImportLooseFiles(dm)
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
