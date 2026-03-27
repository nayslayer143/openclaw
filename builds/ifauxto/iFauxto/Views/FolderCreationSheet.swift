import SwiftUI

struct FolderCreationSheet: View {
    let parentId: String?
    @EnvironmentObject var dataManager: DataManager
    @Environment(\.dismiss) var dismiss

    @State private var folderName = ""
    @FocusState private var nameFieldFocused: Bool

    var body: some View {
        NavigationStack {
            Form {
                Section("Folder Name") {
                    TextField("e.g. Japan 2025", text: $folderName)
                        .focused($nameFieldFocused)
                        .submitLabel(.done)
                        .onSubmit(createAndDismiss)
                }
                if let parentId {
                    Section("Location") {
                        Text("Inside: \(parentFolderName(for: parentId))")
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("New Folder")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Create") { createAndDismiss() }
                        .fontWeight(.semibold)
                        .disabled(folderName.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
            .onAppear { nameFieldFocused = true }
        }
    }

    private func createAndDismiss() {
        let trimmed = folderName.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        dataManager.createFolder(name: trimmed, parentId: parentId)
        dismiss()
    }

    private func parentFolderName(for id: String) -> String {
        let folders = dataManager.fetchFolders(parentId: nil)
        return folders.first(where: { $0.id == id })?.name ?? "Folder"
    }
}
