import SwiftUI

struct PhotoViewer: View {
    let photos: [PhotoReference]
    let startIndex: Int

    @EnvironmentObject var photoKitService: PhotoKitService
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
        .overlay(alignment: .topLeading) {
            Button {
                dismiss()
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.title)
                    .foregroundStyle(.white, .black.opacity(0.5))
                    .padding(16)
            }
        }
        .overlay(alignment: .topTrailing) {
            Button {
                showingEditor = true
            } label: {
                Image(systemName: "slider.horizontal.3")
                    .font(.title2)
                    .foregroundStyle(.white, .black.opacity(0.5))
                    .padding(16)
            }
        }
        .sheet(isPresented: $showingEditor) {
            PhotoEditorView(photoIdentifier: photos[currentIndex].id)
        }
        .overlay(alignment: .bottom) {
            Text("\(currentIndex + 1) / \(photos.count)")
                .font(.caption)
                .foregroundStyle(.white.opacity(0.7))
                .padding(.bottom, 20)
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
