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
        let s = dm.getOrCreateSettings()
        if args.contains("-showOnboarding") {
            // Force the onboarding flow for screenshots.
            s.hasCompletedOnboarding = false
            dm.saveSettings()
        } else if !s.hasCompletedOnboarding {
            s.hasCompletedOnboarding = true
            dm.saveSettings()
        }
    }
    #endif

    @ViewBuilder
    private var mainView: some View {
        if settings.homeViewMode == "chronological_feed" {
            ChronologicalFeedView()
        } else {
            HomeView()
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
