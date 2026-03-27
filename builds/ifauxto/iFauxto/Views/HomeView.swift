import SwiftUI

struct HomeView: View {
    @EnvironmentObject var dataManager: DataManager
    @State private var folders: [Folder] = []
    @State private var showingCreateFolder = false
    @State private var editMode: EditMode = .inactive

    var body: some View {
        NavigationStack {
            Group {
                if folders.isEmpty {
                    emptyState
                } else {
                    folderList
                }
            }
            .navigationTitle("iFauxto")
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    EditButton()
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        showingCreateFolder = true
                    } label: {
                        Image(systemName: "folder.badge.plus")
                    }
                }
            }
            .environment(\.editMode, $editMode)
            .sheet(isPresented: $showingCreateFolder, onDismiss: loadFolders) {
                FolderCreationSheet(parentId: nil)
            }
            .onAppear(perform: loadFolders)
        }
    }

    private var folderList: some View {
        List {
            ForEach(folders) { folder in
                NavigationLink {
                    FolderView(folder: folder)
                } label: {
                    FolderRowView(folder: folder)
                }
            }
            .onMove { source, destination in
                folders.move(fromOffsets: source, toOffset: destination)
                dataManager.updateFolderOrder(folders)
            }
            .onDelete { indexSet in
                indexSet.forEach { dataManager.deleteFolder(folders[$0]) }
                folders.remove(atOffsets: indexSet)
            }
        }
        .listStyle(.plain)
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "folder")
                .font(.system(size: 56))
                .foregroundStyle(.secondary)
            Text("No Folders Yet")
                .font(.title2.weight(.semibold))
            Text("Tap + to create your first folder.")
                .foregroundStyle(.secondary)
            Button("Create Folder") {
                showingCreateFolder = true
            }
            .buttonStyle(.borderedProminent)
        }
    }

    private func loadFolders() {
        folders = dataManager.fetchFolders(parentId: nil)
    }
}

struct FolderRowView: View {
    let folder: Folder

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: "folder.fill")
                .font(.title2)
                .foregroundStyle(.yellow)
            VStack(alignment: .leading, spacing: 2) {
                Text(folder.name)
                    .font(.body.weight(.medium))
                Text("\(folder.photoReferences.count) photos")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}
