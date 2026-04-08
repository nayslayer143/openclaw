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
            if !hasCheckedAuth {
                ZStack {
                    Theme.Palette.bg.ignoresSafeArea()
                    ProgressView()
                        .controlSize(.large)
                        .tint(Theme.Palette.accent)
                }
                .task { await checkAuthorization() }
            } else if photoKitService.isAuthorized {
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
            } else {
                PhotoPermissionView {
                    Task { await photoKitService.requestAuthorization() }
                }
            }
        }
        .animation(Theme.Motion.soft, value: showOnboarding)
        .animation(Theme.Motion.soft, value: settings.homeViewMode)
        .onChange(of: photoKitService.authorizationStatus) { _, _ in
            hasCheckedAuth = true
        }
    }

    @ViewBuilder
    private var mainView: some View {
        if settings.homeViewMode == "chronological_feed" {
            ChronologicalFeedView()
        } else {
            HomeView()
        }
    }

    private func checkAuthorization() async {
        if photoKitService.authorizationStatus == .notDetermined {
            await photoKitService.requestAuthorization()
        }
        hasCheckedAuth = true
        let dm: DataManager = dataManager
        if !dm.getOrCreateSettings().hasCompletedOnboarding {
            showOnboarding = true
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
