import SwiftUI

struct FolderCreationSheet: View {
    let parentId: String?
    @EnvironmentObject var dataManager: DataManager
    @Environment(\.dismiss) var dismiss

    @State private var folderName = ""
    @FocusState private var nameFieldFocused: Bool

    private var canCreate: Bool {
        !folderName.trimmingCharacters(in: .whitespaces).isEmpty
    }

    var body: some View {
        ZStack(alignment: .top) {
            Theme.Palette.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                topBar

                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        // Hero icon
                        HStack {
                            Spacer()
                            Image(systemName: "folder.badge.plus")
                                .font(.system(size: 56, weight: .light))
                                .foregroundStyle(Theme.Palette.folder)
                                .symbolRenderingMode(.hierarchical)
                                .padding(.top, 24)
                                .padding(.bottom, 12)
                            Spacer()
                        }

                        sectionHeader("ALBUM NAME")
                        nameField
                            .padding(.horizontal, 16)

                        if let parentId {
                            sectionHeader("LOCATION")
                            locationCard(parentId: parentId)
                                .padding(.horizontal, 16)
                        }

                        Spacer(minLength: 40)
                    }
                    .padding(.top, 4)
                }
                .scrollIndicators(.hidden)
            }
        }
        .onAppear { nameFieldFocused = true }
    }

    // MARK: - Top bar

    private var topBar: some View {
        ZStack {
            Text("New Album")
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

                Button {
                    createAndDismiss()
                } label: {
                    Text("Create")
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(canCreate ? Theme.Palette.accent : Theme.Palette.textDim)
                }
                .buttonStyle(.plain)
                .disabled(!canCreate)
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

    // MARK: - Bits

    private func sectionHeader(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 12))
            .foregroundStyle(Theme.Palette.textMuted)
            .tracking(0.4)
            .padding(.horizontal, 32)
            .padding(.top, 8)
    }

    private var nameField: some View {
        HStack {
            TextField("e.g. Japan 2026", text: $folderName)
                .font(.system(size: 17))
                .focused($nameFieldFocused)
                .submitLabel(.done)
                .onSubmit { if canCreate { createAndDismiss() } }
            if !folderName.isEmpty {
                Button {
                    folderName = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 16))
                        .foregroundStyle(Theme.Palette.textDim)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 16)
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

    private func locationCard(parentId: String) -> some View {
        HStack(spacing: 12) {
            Image(systemName: "folder.fill")
                .font(.system(size: 22))
                .foregroundStyle(Theme.Palette.folder)
            Text("Inside \(parentFolderName(for: parentId))")
                .font(.system(size: 15))
                .foregroundStyle(Theme.Palette.text)
            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Theme.Palette.bgElevated)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
        )
    }

    private func createAndDismiss() {
        let trimmed = folderName.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        Haptics.success()
        dataManager.createFolder(name: trimmed, parentId: parentId)
        dismiss()
    }

    private func parentFolderName(for id: String) -> String {
        let folders = dataManager.fetchFolders(parentId: nil)
        return folders.first(where: { $0.id == id })?.name ?? "Folder"
    }
}
