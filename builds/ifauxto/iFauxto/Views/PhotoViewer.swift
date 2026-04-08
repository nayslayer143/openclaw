import SwiftUI

struct PhotoViewer: View {
    let photos: [PhotoReference]
    let startIndex: Int

    @EnvironmentObject var photoKitService: PhotoKitService
    @EnvironmentObject var navCoordinator: NavCoordinator
    @Environment(\.dismiss) var dismiss
    @State private var currentIndex: Int
    @State private var showingEditor = false

    init(photos: [PhotoReference], startIndex: Int) {
        self.photos = photos
        self.startIndex = startIndex
        _currentIndex = State(initialValue: startIndex)
    }

    var body: some View {
        TabView(selection: $currentIndex) {
            ForEach(Array(photos.enumerated()), id: \.offset) { index, photo in
                FullPhotoView(identifier: photo.id)
                    .tag(index)
            }
        }
        .tabViewStyle(.page(indexDisplayMode: .never))
        .background(Color.black)
        .ignoresSafeArea()
        .toolbar(.hidden, for: .navigationBar)
        .overlay(alignment: .top) {
            HStack(spacing: 8) {
                PhotoOverlayButton(systemName: "chevron.left") { dismiss() }
                PhotoOverlayButton(systemName: "house.fill") { navCoordinator.popToRoot() }
                Spacer()
                Text("\(currentIndex + 1) of \(photos.count)")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Capsule().fill(Color.black.opacity(0.45)))
                Spacer()
                PhotoOverlayButton(systemName: "slider.horizontal.3") { showingEditor = true }
            }
            .padding(.horizontal, 14)
            .padding(.top, 12)
        }
        .sheet(isPresented: $showingEditor) {
            PhotoEditorView(photoIdentifier: photos[currentIndex].id)
        }
        .onAppear { currentIndex = startIndex }
    }
}

/// Dark-capsule icon button used over photo backgrounds. Distinct from
/// `GlassIconButton` (which is blue-on-light for normal app chrome).
private struct PhotoOverlayButton: View {
    let systemName: String
    let action: () -> Void

    var body: some View {
        Button {
            Haptics.tap()
            action()
        } label: {
            Image(systemName: systemName)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 36, height: 36)
                .background(Circle().fill(Color.black.opacity(0.45)))
        }
        .buttonStyle(.plain)
    }
}

private struct FullPhotoView: View {
    let identifier: String
    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var image: UIImage?

    var body: some View {
        Group {
            if let img = image {
                Image(uiImage: img)
                    .resizable()
                    .scaledToFit()
            } else {
                ProgressView()
                    .tint(.white)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task(id: identifier) {
            image = await photoKitService.loadFullImage(for: identifier)
        }
    }
}
