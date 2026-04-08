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
            HStack(spacing: 10) {
                GlassIconButton(systemName: "chevron.left") {
                    dismiss()
                }
                GlassIconButton(systemName: "house.fill") {
                    navCoordinator.popToRoot()
                }
                Spacer()
                Text("\(currentIndex + 1) / \(photos.count)")
                    .font(Theme.Font.mono(13, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Capsule().fill(.ultraThinMaterial))
                    .overlay(Capsule().strokeBorder(Theme.Palette.stroke, lineWidth: 1))
                Spacer()
                GlassIconButton(systemName: "slider.horizontal.3") {
                    showingEditor = true
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)
        }
        .sheet(isPresented: $showingEditor) {
            PhotoEditorView(photoIdentifier: photos[currentIndex].id)
        }
        .onAppear { currentIndex = startIndex }
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
