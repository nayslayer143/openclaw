import SwiftUI
import UIKit

struct ImportProgressView: View {
    @ObservedObject var importService: LibraryImportService
    let onDismiss: () -> Void

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                topBar
                Spacer()
                content
                Spacer()
                bottomAction
                    .padding(.bottom, 32)
            }
        }
        .interactiveDismissDisabled(importService.isImporting)
    }

    // MARK: - Top bar

    private var topBar: some View {
        ZStack {
            Text("Import Library")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            HStack {
                Spacer()
                if !importService.isImporting {
                    Button {
                        Haptics.tap()
                        onDismiss()
                    } label: {
                        Text("Done")
                            .font(.system(size: 17, weight: .semibold))
                            .foregroundStyle(Theme.Palette.accent)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 16)
        }
        .frame(height: 44)
        .padding(.top, 8)
        .padding(.bottom, 6)
        .background(Theme.Palette.bg)
        .overlay(
            Rectangle().fill(Theme.Palette.divider).frame(height: 0.5),
            alignment: .bottom
        )
    }

    // MARK: - Content

    private var content: some View {
        VStack(spacing: 24) {
            icon
            statusText

            if importService.isImporting {
                counters
                progressBar
                    .padding(.horizontal, 40)
            } else if !importService.authorizationDenied {
                counters
            }
        }
        .padding(.horizontal, 28)
    }

    @ViewBuilder
    private var icon: some View {
        if importService.isImporting {
            ProgressView()
                .scaleEffect(1.6)
                .tint(Theme.Palette.accent)
                .frame(height: 64)
        } else if importService.authorizationDenied {
            Image(systemName: "lock.shield.fill")
                .font(.system(size: 56, weight: .regular))
                .foregroundStyle(.orange)
                .symbolRenderingMode(.hierarchical)
        } else if importService.progress >= 1.0 {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 64, weight: .regular))
                .foregroundStyle(Color.green)
                .symbolRenderingMode(.hierarchical)
        } else {
            Image(systemName: "photo.on.rectangle.angled")
                .font(.system(size: 60, weight: .light))
                .foregroundStyle(Theme.Palette.folder)
                .symbolRenderingMode(.hierarchical)
        }
    }

    private var statusText: some View {
        Text(importService.statusMessage.isEmpty ? "Mirror your Photos library structure into iFauxto." : importService.statusMessage)
            .font(.system(size: 14))
            .foregroundStyle(Theme.Palette.textMuted)
            .multilineTextAlignment(.center)
            .padding(.horizontal, 16)
            .animation(.easeInOut, value: importService.statusMessage)
    }

    private var counters: some View {
        HStack(spacing: 0) {
            counterCell(
                value: "\(importService.importedFolderCount)",
                label: "Folders",
                icon: "folder.fill",
                tint: Theme.Palette.folder
            )
            Rectangle()
                .fill(Theme.Palette.divider)
                .frame(width: 0.5, height: 44)
            counterCell(
                value: "\(importService.importedPhotoCount)",
                label: "Photos",
                icon: "photo.fill",
                tint: Theme.Palette.accent
            )
        }
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Theme.Palette.bgElevated)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
        )
    }

    private func counterCell(value: String, label: String, icon: String, tint: Color) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.system(size: 22, weight: .semibold).monospacedDigit())
                .foregroundStyle(Theme.Palette.text)
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 11))
                    .foregroundStyle(tint)
                Text(label)
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.Palette.textMuted)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 14)
    }

    private var progressBar: some View {
        VStack(spacing: 6) {
            ProgressView(value: importService.progress)
                .progressViewStyle(.linear)
                .tint(Theme.Palette.accent)
            Text("\(Int(importService.progress * 100))%")
                .font(.system(size: 11).monospacedDigit())
                .foregroundStyle(Theme.Palette.textMuted)
        }
    }

    // MARK: - Bottom action

    @ViewBuilder
    private var bottomAction: some View {
        if importService.isImporting {
            EmptyView()
        } else if importService.authorizationDenied {
            Button {
                Haptics.tap()
                if let url = URL(string: UIApplication.openSettingsURLString) {
                    UIApplication.shared.open(url)
                }
            } label: {
                Text("Open Settings")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 15)
                    .background(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .fill(Theme.Palette.accent)
                    )
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 20)
        } else if !importService.hasImportedLibrary || importService.progress < 1.0 {
            Button {
                Haptics.medium()
                Task { await importService.importLibrary() }
            } label: {
                Text(importService.hasImportedLibrary ? "Re-import" : "Start Import")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 15)
                    .background(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .fill(Theme.Palette.accent)
                    )
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 20)
        } else {
            Button {
                Haptics.tap()
                onDismiss()
            } label: {
                Text("Done")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 15)
                    .background(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .fill(Theme.Palette.accent)
                    )
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 20)
        }
    }
}
