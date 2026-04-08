import SwiftUI

struct PhotoThumbnailView: View {
    let photo: PhotoReference
    let isSelected: Bool
    let isEditMode: Bool

    @EnvironmentObject var photoKitService: PhotoKitService
    @EnvironmentObject var dataManager: DataManager
    @State private var thumbnail: UIImage?

    private var isDemo: Bool { photo.id.hasPrefix("demo:") }

    private var demoColor: Color {
        DemoPalette.color(for: photo.id)
    }

    private var demoLabel: String {
        DemoPalette.label(for: photo.id)
    }

    private var demoIcon: String {
        DemoPalette.icon(for: photo.id)
    }

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .topTrailing) {
                thumbnailImage
                    .frame(width: geo.size.width, height: geo.size.width)
                    .clipped()
                    .contentShape(Rectangle())

                if isEditMode {
                    selectionIndicator
                        .padding(6)
                } else if dataManager.hasEdits(photoId: photo.id) {
                    Image(systemName: "slider.horizontal.3")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(.white)
                        .padding(5)
                        .background(Circle().fill(Color.black.opacity(0.55)))
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading)
                        .padding(6)
                }
            }
        }
        .aspectRatio(1, contentMode: .fit)
        .animation(.easeInOut(duration: 0.15), value: isSelected)
        .task(id: photo.id) {
            guard !isDemo else { return }
            thumbnail = await photoKitService.loadThumbnail(
                for: photo.id,
                targetSize: CGSize(width: 300, height: 300)
            )
        }
    }

    @ViewBuilder
    private var thumbnailImage: some View {
        if isDemo {
            ZStack {
                LinearGradient(
                    colors: [demoColor, demoColor.opacity(0.65)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                Image(systemName: demoIcon)
                    .font(.system(size: 22, weight: .light))
                    .foregroundStyle(.white.opacity(0.85))
                Text(demoLabel)
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.95))
                    .padding(.horizontal, 5)
                    .padding(.vertical, 2)
                    .background(Capsule().fill(.black.opacity(0.25)))
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
                    .padding(4)
            }
            .overlay(
                isSelected ? Color.black.opacity(0.28) : Color.clear
            )
            .overlay(
                Rectangle()
                    .strokeBorder(
                        isSelected ? Theme.Palette.accent : Color.clear,
                        lineWidth: 3
                    )
            )
        } else if let img = thumbnail {
            Image(uiImage: img)
                .resizable()
                .scaledToFill()
                .overlay(
                    isSelected
                        ? Color.black.opacity(0.28)
                        : Color.clear
                )
                .overlay(
                    Rectangle()
                        .strokeBorder(
                            isSelected ? Theme.Palette.accent : Color.clear,
                            lineWidth: 3
                        )
                )
        } else {
            Rectangle()
                .fill(Color(red: 0.918, green: 0.918, blue: 0.937))
                .overlay(
                    ProgressView()
                        .controlSize(.small)
                        .tint(Theme.Palette.textDim)
                )
        }
    }

    private var selectionIndicator: some View {
        ZStack {
            Circle()
                .fill(isSelected ? Theme.Palette.accent : Color.black.opacity(0.35))
                .frame(width: 24, height: 24)
            Circle()
                .strokeBorder(Color.white, lineWidth: 1.5)
                .frame(width: 24, height: 24)
            if isSelected {
                Image(systemName: "checkmark")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(.white)
            }
        }
    }
}
