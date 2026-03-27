import SwiftUI

struct EditModeToolbar: View {
    let selectedCount: Int
    let onMove: () -> Void
    let onDelete: () -> Void

    var body: some View {
        HStack(spacing: 0) {
            Button(action: onMove) {
                VStack(spacing: 4) {
                    Image(systemName: "folder.badge.plus")
                    Text("Move")
                        .font(.caption)
                }
                .frame(maxWidth: .infinity)
            }

            Divider().frame(height: 36)

            Button(role: .destructive, action: onDelete) {
                VStack(spacing: 4) {
                    Image(systemName: "trash")
                    Text("Remove")
                        .font(.caption)
                }
                .frame(maxWidth: .infinity)
            }
        }
        .padding(.vertical, 8)
        .background(.regularMaterial)
        .overlay(alignment: .top) {
            Divider()
        }
    }
}

struct FolderPickerSheet: View {
    let excludingFolderId: String
    let onSelect: (Folder) -> Void

    @EnvironmentObject var dataManager: DataManager
    @Environment(\.dismiss) var dismiss
    @State private var rootFolders: [Folder] = []

    var body: some View {
        NavigationStack {
            List(rootFolders.filter { $0.id != excludingFolderId }) { folder in
                Button {
                    onSelect(folder)
                } label: {
                    HStack {
                        Image(systemName: "folder.fill")
                            .foregroundStyle(.yellow)
                        Text(folder.name)
                        Spacer()
                        Image(systemName: "chevron.right")
                            .foregroundStyle(.secondary)
                    }
                }
                .foregroundStyle(.primary)
            }
            .navigationTitle("Move To")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                }
            }
            .onAppear {
                rootFolders = dataManager.fetchFolders(parentId: nil)
            }
        }
    }
}
