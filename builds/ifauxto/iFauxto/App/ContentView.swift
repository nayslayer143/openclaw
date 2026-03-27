import SwiftUI
import Photos

struct ContentView: View {
    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var hasCheckedAuth = false

    var body: some View {
        Group {
            if !hasCheckedAuth {
                ProgressView("Loading…")
                    .task { await checkAuthorization() }
            } else if photoKitService.isAuthorized {
                HomeView()
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

    private func checkAuthorization() async {
        if photoKitService.authorizationStatus == .notDetermined {
            await photoKitService.requestAuthorization()
        }
        hasCheckedAuth = true
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
