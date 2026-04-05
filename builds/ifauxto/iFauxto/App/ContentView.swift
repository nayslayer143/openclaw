import SwiftUI
import Photos

struct ContentView: View {
    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var hasCheckedAuth = false
    @State private var showOnboarding = false

    var body: some View {
        Group {
            if !hasCheckedAuth {
                ProgressView("Loading...")
                    .task { await checkAuthorization() }
            } else if photoKitService.isAuthorized {
                if showOnboarding {
                    OnboardingView {
                        showOnboarding = false
                    }
                } else {
                    mainView
                }
            } else {
                PhotoPermissionView {
                    Task { await photoKitService.requestAuthorization() }
                }
            }
        }
        .onChange(of: photoKitService.authorizationStatus) { _, _ in
            hasCheckedAuth = true
        }
    }

    @ViewBuilder
    private var mainView: some View {
        let settings = dataManager.getOrCreateSettings()
        switch settings.homeViewMode {
        case "chronological_feed":
            ChronologicalFeedView()
        default:
            HomeView()
        }
    }

    private func checkAuthorization() async {
        if photoKitService.authorizationStatus == .notDetermined {
            await photoKitService.requestAuthorization()
        }
        hasCheckedAuth = true
        let settings = dataManager.getOrCreateSettings()
        if !settings.hasCompletedOnboarding {
            showOnboarding = true
        }
    }
}

struct PhotoPermissionView: View {
    let onRequest: () -> Void

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "photo.on.rectangle.angled")
                .font(.system(size: 64))
                .foregroundStyle(.secondary)
            Text("iFauxto needs access to your Photos library to get started.")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
            Button("Grant Access", action: onRequest)
                .buttonStyle(.borderedProminent)
        }
        .padding(40)
    }
}
