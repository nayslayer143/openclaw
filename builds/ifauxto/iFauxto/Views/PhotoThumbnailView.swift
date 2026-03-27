import SwiftUI

struct PhotoThumbnailView: View {
    let photo: PhotoReference
    let isSelected: Bool
    let isEditMode: Bool

    @EnvironmentObject var photoKitService: PhotoKitService
    @State private var thumbnail: UIImage?

    private let size: CGFloat = 120

    var body: some View {
        ZStack(alignment: .topTrailing) {
            thumbnailImage
                .frame(width: size, height: size)
                .clipped()
                .contentShape(Rectangle())

            if isEditMode {
                selectionIndicator
                    .padding(4)
            }
        }
        .animation(.easeInOut(duration: 0.15), value: isSelected)
        .task(id: photo.id) {
            thumbnail = await photoKitService.loadThumbnail(
                for: photo.id,
                targetSize: CGSize(width: size * 2, height: size * 2)
            )
        }
    }

    @ViewBuilder
    private var thumbnailImage: some View {
        if let img = thumbnail {
            Image(uiImage: img)
                .resizable()
                .scaledToFill()
                .overlay(
                    isSelected
                        ? Color.black.opacity(0.3)
                        : Color.clear
                )
        } else {
            Rectangle()
                .fill(Color.secondarySystemBackground)
                .overlay(ProgressView())
        }
    }

    private var selectionIndicator: some View {
        ZStack {
            Circle()
                .fill(isSelected ? Color.accentColor : Color.white.opacity(0.7))
                .frame(width: 22, height: 22)
            if isSelected {
                Image(systemName: "checkmark")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.white)
            }
        }
    }
}
