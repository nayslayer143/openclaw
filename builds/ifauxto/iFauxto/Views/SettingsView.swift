import SwiftUI

private struct ModeOption: Identifiable {
    let id: String
    let label: String
    let subtitle: String
    let icon: String
}

struct SettingsView: View {
    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var indexingManager: IndexingManager
    @ObservedObject var userSession = UserSession.shared
    @Environment(\.dismiss) var dismiss

    @State private var homeMode: String = "folder_list"

    private let modes: [ModeOption] = [
        ModeOption(id: "folder_list", label: "Folders",
                   subtitle: "Your structure, untouched.", icon: "folder.fill"),
        ModeOption(id: "chronological_feed", label: "Photo Feed",
                   subtitle: "Every photo, newest first.", icon: "photo.on.rectangle"),
        ModeOption(id: "last_opened", label: "Last Opened",
                   subtitle: "Pick up where you left off.", icon: "clock.arrow.circlepath")
    ]

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()

            ScrollView {
                Spacer().frame(height: 80)

                VStack(alignment: .leading, spacing: 28) {
                    accountCard

                    section(title: "Home Screen", subtitle: "What you see when you open iFauxto.") {
                        VStack(spacing: 10) {
                            ForEach(modes) { mode in
                                modeRow(mode)
                            }
                        }
                    }

                    section(title: "Search Index", subtitle: indexingManager.isIndexing
                            ? "Indexing your library so search works."
                            : "Auto-tags every photo on device using Apple Vision.") {
                        VStack(alignment: .leading, spacing: 10) {
                            HStack {
                                Image(systemName: "magnifyingglass.circle.fill")
                                    .font(.system(size: 18, weight: .semibold))
                                    .foregroundStyle(Theme.Palette.accent)
                                    .frame(width: 28)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Photo Index")
                                        .font(.system(size: 15, weight: .semibold))
                                        .foregroundStyle(Theme.Palette.text)
                                    Text(indexStatus)
                                        .font(.system(size: 12))
                                        .foregroundStyle(Theme.Palette.textMuted)
                                }
                                Spacer()
                                Button {
                                    Haptics.tap()
                                    indexingManager.startBackgroundIndexing()
                                } label: {
                                    Text(indexingManager.isIndexing ? "Indexing…" : "Re-index")
                                        .font(.system(size: 14, weight: .semibold))
                                        .foregroundStyle(Theme.Palette.accent)
                                }
                                .buttonStyle(.plain)
                                .disabled(indexingManager.isIndexing)
                            }
                            if indexingManager.isIndexing {
                                ProgressView(value: indexingManager.progress)
                                    .tint(Theme.Palette.accent)
                            }
                        }
                        .padding(.horizontal, 14)
                        .padding(.vertical, 12)
                        .background(
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .fill(.ultraThinMaterial)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .strokeBorder(Theme.Palette.stroke, lineWidth: 1)
                        )
                    }

                    section(title: "iCloud", subtitle: dataManager.isCloudKitEnabled
                            ? "Albums and metadata sync via iCloud."
                            : "Sync is off. Sign in with an Apple Developer account and flip iFauxtoCloudKitEnabled to enable.") {
                        HStack(spacing: 14) {
                            Image(systemName: dataManager.isCloudKitEnabled ? "icloud.fill" : "icloud.slash")
                                .font(.system(size: 18, weight: .semibold))
                                .foregroundStyle(dataManager.isCloudKitEnabled ? Theme.Palette.accent : Theme.Palette.textMuted)
                                .frame(width: 28)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("iCloud Sync")
                                    .font(.system(size: 15, weight: .semibold))
                                    .foregroundStyle(Theme.Palette.text)
                                Text(dataManager.isCloudKitEnabled ? "Enabled" : "Off")
                                    .font(.system(size: 12))
                                    .foregroundStyle(Theme.Palette.textMuted)
                            }
                            Spacer()
                        }
                        .padding(.horizontal, 14)
                        .padding(.vertical, 12)
                        .background(
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .fill(.ultraThinMaterial)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .strokeBorder(Theme.Palette.stroke, lineWidth: 1)
                        )
                    }

                    section(title: "About", subtitle: nil) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("iFauxto v1.0")
                                .font(Theme.Font.body(14, weight: .semibold))
                                .foregroundStyle(Theme.Palette.text)
                            Text("Manual-first photo organization. No surprises. Just your system.")
                                .font(Theme.Font.body(13))
                                .foregroundStyle(Theme.Palette.textMuted)
                        }
                        .padding(16)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            RoundedRectangle(cornerRadius: Theme.Radius.l, style: .continuous)
                                .fill(.ultraThinMaterial)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: Theme.Radius.l, style: .continuous)
                                .strokeBorder(Theme.Palette.stroke, lineWidth: 1)
                        )
                    }
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 40)
            }
            .scrollIndicators(.hidden)

            BrandTopBar(
                title: "Settings",
                onBack: {
                    saveAndDismiss()
                },
                onHome: {
                    saveAndDismiss()
                }
            ) {
                Button {
                    Haptics.success()
                    saveAndDismiss()
                } label: {
                    Text("Done")
                        .font(Theme.Font.body(14, weight: .bold))
                        .foregroundStyle(Theme.Palette.accent)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 9)
                        .background(Capsule().fill(.ultraThinMaterial))
                        .overlay(Capsule().strokeBorder(Theme.Palette.accent.opacity(0.5), lineWidth: 1))
                }
                .buttonStyle(.plain)
            }
        }
        .onAppear {
            homeMode = dataManager.getOrCreateSettings().homeViewMode
        }
    }

    @ViewBuilder
    private func section<Content: View>(
        title: String,
        subtitle: String?,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(Theme.Font.display(20))
                .foregroundStyle(Theme.Palette.text)
            if let subtitle {
                Text(subtitle)
                    .font(Theme.Font.body(12, weight: .medium))
                    .foregroundStyle(Theme.Palette.textMuted)
                    .padding(.bottom, 2)
            }
            content()
        }
    }

    private func modeRow(_ mode: ModeOption) -> some View {
        let isSelected = homeMode == mode.id
        return Button {
            Haptics.select()
            withAnimation(Theme.Motion.snappy) {
                homeMode = mode.id
            }
        } label: {
            HStack(spacing: 14) {
                Image(systemName: mode.icon)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(isSelected ? Theme.Palette.accent : Theme.Palette.textMuted)
                    .frame(width: 28)
                VStack(alignment: .leading, spacing: 2) {
                    Text(mode.label)
                        .font(Theme.Font.body(15, weight: .semibold))
                        .foregroundStyle(Theme.Palette.text)
                    Text(mode.subtitle)
                        .font(Theme.Font.body(12))
                        .foregroundStyle(Theme.Palette.textMuted)
                }
                Spacer()
                if isSelected {
                    Image(systemName: "checkmark")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(Theme.Palette.accent)
                        .transition(.scale.combined(with: .opacity))
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(.ultraThinMaterial)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(
                        isSelected ? Theme.Palette.accent.opacity(0.5) : Theme.Palette.stroke,
                        lineWidth: 1
                    )
            )
        }
        .buttonStyle(.plain)
    }

    private var accountCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("ACCOUNT")
                .font(.system(size: 12))
                .foregroundStyle(Theme.Palette.textMuted)
                .tracking(0.4)
                .padding(.horizontal, 16)

            HStack(spacing: 14) {
                ZStack {
                    Circle()
                        .fill(Theme.Palette.accent.opacity(0.15))
                        .frame(width: 44, height: 44)
                    Image(systemName: userSession.isAuthenticated ? "person.fill" : "person")
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundStyle(Theme.Palette.accent)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(userSession.currentProfile?.displayName ?? "Guest")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(Theme.Palette.text)
                    Text(userSession.isAuthenticated
                         ? (userSession.currentProfile?.email.isEmpty == false
                            ? userSession.currentProfile!.email
                            : "Signed in with \(userSession.currentProfile?.provider.label ?? "Apple")")
                         : "Photos stay on this device only")
                        .font(.system(size: 12))
                        .foregroundStyle(Theme.Palette.textMuted)
                }
                Spacer()
                if userSession.isAuthenticated {
                    Button {
                        Haptics.warning()
                        userSession.signOut()
                        dismiss()
                    } label: {
                        Text("Sign Out")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(.red)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(.ultraThinMaterial)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(Theme.Palette.stroke, lineWidth: 1)
            )
        }
    }

    private var indexStatus: String {
        if indexingManager.isIndexing {
            return "\(indexingManager.indexedCount) of \(indexingManager.totalCount)"
        }
        if indexingManager.indexedCount > 0 {
            return "\(indexingManager.indexedCount) photos indexed"
        }
        return "Tap Re-index to start"
    }

    private func saveAndDismiss() {
        let settings = dataManager.getOrCreateSettings()
        settings.homeViewMode = homeMode
        dataManager.saveSettings()
        dismiss()
    }
}
