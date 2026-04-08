import SwiftUI
import Photos
import CoreLocation

/// Bottom sheet that surfaces full metadata for a single photo —
/// dimensions, file size, capture date, camera, lens, exposure, ISO,
/// aperture, shutter speed, location. Mirrors iPhoto's Info pane.
struct PhotoInfoSheet: View {
    let identifier: String

    @EnvironmentObject var dataManager: DataManager
    @State private var info: PhotoMetadata?
    @State private var isLoading = true
    @State private var rating: Int = 0
    @State private var isFavorite: Bool = false
    @State private var title: String = ""
    @State private var caption: String = ""
    @FocusState private var titleFocused: Bool
    @FocusState private var captionFocused: Bool

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                header
                Divider().background(Theme.Palette.divider)

                if isLoading {
                    loadingView
                } else if let info {
                    ScrollView {
                        content(for: info)
                    }
                } else {
                    notFoundView
                }
            }
        }
        .task(id: identifier) {
            isLoading = true
            info = await PhotoMetadataLoader.load(identifier: identifier)
            let meta = dataManager.metaIfExists(for: identifier)
            rating = meta?.rating ?? 0
            isFavorite = meta?.isFavorite ?? false
            title = meta?.title ?? ""
            caption = meta?.caption ?? ""
            isLoading = false
        }
    }

    private var header: some View {
        HStack {
            Text("Info")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            Spacer()
        }
        .padding(.horizontal, 20)
        .padding(.top, 14)
        .padding(.bottom, 12)
    }

    private var loadingView: some View {
        VStack {
            Spacer()
            ProgressView()
                .tint(Theme.Palette.accent)
            Spacer()
        }
    }

    private var notFoundView: some View {
        VStack(spacing: 8) {
            Spacer()
            Image(systemName: "photo.badge.exclamationmark")
                .font(.system(size: 38, weight: .light))
                .foregroundStyle(Theme.Palette.textDim)
            Text("No metadata available")
                .font(.system(size: 14))
                .foregroundStyle(Theme.Palette.textMuted)
            Spacer()
        }
    }

    @ViewBuilder
    private func content(for info: PhotoMetadata) -> some View {
        VStack(spacing: 18) {
            ratingCard
            titleCaptionCard

            section(title: "FILE") {
                row("Dimensions", info.dimensions ?? "—")
                row("File Size", info.fileSize ?? "—")
                row("Type", info.mediaType ?? "—")
            }

            section(title: "DATES") {
                row("Captured", info.captureDate ?? "—")
                if let modified = info.modifiedDate {
                    row("Modified", modified)
                }
            }

            if info.hasCamera {
                section(title: "CAMERA") {
                    if let camera = info.camera { row("Camera", camera) }
                    if let lens = info.lens { row("Lens", lens) }
                    if let aperture = info.aperture { row("Aperture", aperture) }
                    if let shutter = info.shutterSpeed { row("Shutter", shutter) }
                    if let iso = info.iso { row("ISO", iso) }
                    if let focal = info.focalLength { row("Focal", focal) }
                }
            }

            if info.hasLocation {
                section(title: "LOCATION") {
                    if let coords = info.coordinates { row("Coordinates", coords) }
                    if let altitude = info.altitude { row("Altitude", altitude) }
                }
            }

            section(title: "IDENTIFIER") {
                row("Asset ID", info.assetId, mono: true)
            }
        }
        .padding(.horizontal, 20)
        .padding(.bottom, 40)
    }

    /// Editable title + caption.
    private var titleCaptionCard: some View {
        VStack(spacing: 0) {
            HStack {
                Image(systemName: "textformat")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(Theme.Palette.textMuted)
                    .frame(width: 22)
                TextField("Add a title", text: $title)
                    .font(.system(size: 15, weight: .semibold))
                    .focused($titleFocused)
                    .submitLabel(.done)
                    .onSubmit { commitTitle() }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)

            Rectangle().fill(Theme.Palette.divider).frame(height: 0.5).padding(.leading, 36)

            HStack(alignment: .top) {
                Image(systemName: "text.alignleft")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(Theme.Palette.textMuted)
                    .frame(width: 22)
                    .padding(.top, 4)
                TextField("Add a caption", text: $caption, axis: .vertical)
                    .font(.system(size: 14))
                    .focused($captionFocused)
                    .lineLimit(1...4)
                    .onChange(of: captionFocused) { _, focused in
                        if !focused { commitCaption() }
                    }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
        }
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Theme.Palette.bgElevated)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
        )
        .onChange(of: titleFocused) { _, focused in
            if !focused { commitTitle() }
        }
    }

    private func commitTitle() {
        dataManager.setTitle(title, for: identifier)
    }

    private func commitCaption() {
        dataManager.setCaption(caption, for: identifier)
    }

    /// Star rating + favorite toggle in one card.
    private var ratingCard: some View {
        HStack(spacing: 0) {
            // Stars
            HStack(spacing: 6) {
                ForEach(1...5, id: \.self) { i in
                    Button {
                        Haptics.select()
                        // Tapping the current star clears the rating.
                        let next = (rating == i) ? 0 : i
                        rating = next
                        dataManager.setRating(next, for: identifier)
                    } label: {
                        Image(systemName: i <= rating ? "star.fill" : "star")
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundStyle(i <= rating ? Color(red: 1.0, green: 0.78, blue: 0.0) : Theme.Palette.textDim)
                    }
                    .buttonStyle(.plain)
                }
            }

            Spacer()

            // Favorite
            Button {
                Haptics.success()
                isFavorite = dataManager.toggleFavorite(for: identifier)
            } label: {
                Image(systemName: isFavorite ? "heart.fill" : "heart")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(isFavorite ? Color(red: 1.0, green: 0.30, blue: 0.30) : Theme.Palette.textDim)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 14)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Theme.Palette.bgElevated)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
        )
    }

    private func section<Content: View>(
        title: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.system(size: 12))
                .foregroundStyle(Theme.Palette.textMuted)
                .tracking(0.4)
                .padding(.horizontal, 16)
            VStack(spacing: 0) { content() }
                .background(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(Theme.Palette.bgElevated)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
                )
        }
    }

    private func row(_ label: String, _ value: String, mono: Bool = false) -> some View {
        HStack(alignment: .top) {
            Text(label)
                .font(.system(size: 14))
                .foregroundStyle(Theme.Palette.textMuted)
            Spacer()
            Text(value)
                .font(mono
                      ? .system(size: 12, design: .monospaced)
                      : .system(size: 14, weight: .medium))
                .foregroundStyle(Theme.Palette.text)
                .multilineTextAlignment(.trailing)
                .lineLimit(2)
                .truncationMode(.middle)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
        .overlay(
            Rectangle()
                .fill(Theme.Palette.divider)
                .frame(height: 0.5)
                .padding(.leading, 14),
            alignment: .bottom
        )
    }
}
