import SwiftUI

/// Bottom toolbar shown while photos are selected for batch actions.
/// Glass material, large iPhoto-style action buttons.
struct EditModeToolbar: View {
    let selectedCount: Int
    let onMove: () -> Void
    let onDelete: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            Rectangle()
                .fill(Theme.Palette.divider)
                .frame(height: 0.5)

            HStack(spacing: 0) {
                actionButton(
                    label: "Move",
                    systemName: "folder.fill",
                    tint: Theme.Palette.accent,
                    action: onMove
                )

                Rectangle()
                    .fill(Theme.Palette.divider)
                    .frame(width: 0.5, height: 40)

                actionButton(
                    label: "Remove",
                    systemName: "trash.fill",
                    tint: .red,
                    action: onDelete
                )
            }
            .padding(.vertical, 6)
            .background(.ultraThinMaterial)
        }
        .overlay(alignment: .top) {
            // Selection count badge floats just above the toolbar.
            Text("\(selectedCount) selected")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(Capsule().fill(Theme.Palette.text.opacity(0.85)))
                .offset(y: -16)
        }
    }

    private func actionButton(
        label: String,
        systemName: String,
        tint: Color,
        action: @escaping () -> Void
    ) -> some View {
        Button {
            Haptics.medium()
            action()
        } label: {
            VStack(spacing: 3) {
                Image(systemName: systemName)
                    .font(.system(size: 18, weight: .regular))
                Text(label)
                    .font(.system(size: 11, weight: .medium))
            }
            .foregroundStyle(tint)
            .frame(maxWidth: .infinity)
            .frame(height: 44)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

/// Sheet to pick a destination folder when moving photos.
/// Same iPhoto grouped-list look as HomeView.
struct FolderPickerSheet: View {
    let excludingFolderId: String
    let onSelect: (Folder) -> Void

    @EnvironmentObject var dataManager: DataManager
    @Environment(\.dismiss) var dismiss
    @State private var rootFolders: [Folder] = []

    private var displayFolders: [Folder] {
        rootFolders.filter { $0.id != excludingFolderId }
    }

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                topBar

                if displayFolders.isEmpty {
                    emptyState
                } else {
                    folderList
                }
            }
        }
        .onAppear {
            rootFolders = dataManager.fetchFolders(parentId: nil)
        }
    }

    private var topBar: some View {
        ZStack {
            Text("Move To")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            HStack {
                Button {
                    Haptics.tap()
                    dismiss()
                } label: {
                    Text("Cancel")
                        .font(.system(size: 17))
                        .foregroundStyle(Theme.Palette.accent)
                }
                .buttonStyle(.plain)
                Spacer()
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

    private var folderList: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                Text("CHOOSE A DESTINATION")
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.Palette.textMuted)
                    .tracking(0.4)
                    .padding(.horizontal, 32)
                    .padding(.top, 12)

                VStack(spacing: 0) {
                    ForEach(Array(displayFolders.enumerated()), id: \.element.id) { index, folder in
                        Button {
                            Haptics.success()
                            onSelect(folder)
                        } label: {
                            HStack(spacing: 14) {
                                Image(systemName: "folder.fill")
                                    .font(.system(size: 28))
                                    .foregroundStyle(Theme.Palette.folder)
                                    .frame(width: 38, height: 38)
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(folder.name)
                                        .font(.system(size: 17))
                                        .foregroundStyle(Theme.Palette.text)
                                    Text("\((folder.photoReferences ?? []).count) photos")
                                        .font(.system(size: 13))
                                        .foregroundStyle(Theme.Palette.textMuted)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.system(size: 13, weight: .semibold))
                                    .foregroundStyle(Theme.Palette.textDim)
                            }
                            .padding(.horizontal, 16)
                            .padding(.vertical, 10)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .pressScale(0.985)

                        if index < displayFolders.count - 1 {
                            Rectangle()
                                .fill(Theme.Palette.divider)
                                .frame(height: 0.5)
                                .padding(.leading, 64)
                        }
                    }
                }
                .background(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(Theme.Palette.bgElevated)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
                )
                .padding(.horizontal, 16)
            }
            .padding(.bottom, 40)
        }
    }

    private var emptyState: some View {
        VStack(spacing: 14) {
            Spacer(minLength: 60)
            Image(systemName: "folder.badge.questionmark")
                .font(.system(size: 56, weight: .light))
                .foregroundStyle(Theme.Palette.folder)
                .symbolRenderingMode(.hierarchical)
            Text("No Other Albums")
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
            Text("Create another album first to move photos into.")
                .font(.system(size: 14))
                .foregroundStyle(Theme.Palette.textMuted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }
}
