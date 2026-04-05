import SwiftUI

struct HomeView: View {
    @EnvironmentObject var dataManager: DataManager
    @EnvironmentObject var importService: LibraryImportService

    @State private var folders: [Folder] = []
    @State private var showingCreateFolder = false
    @State private var showingImport = false
    @State private var editMode: EditMode = .inactive
    @State private var folderSortMode: String = "custom"
    @State private var showingSettings = false

    private var displayFolders: [Folder] {
        switch folderSortMode {
        case "alpha":
            return folders.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
        case "date":
            return folders.sorted { $0.createdAt < $1.createdAt }
        case "recent":
            return folders.sorted { $0.createdAt > $1.createdAt }
        default:
            return folders
        }
    }

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
                    HStack {
                        EditButton()
                        Button {
                            showingSettings = true
                        } label: {
                            Image(systemName: "gearshape")
                        }
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Menu {
                        Button {
                            showingCreateFolder = true
                        } label: {
                            Label("New Folder", systemImage: "folder.badge.plus")
                        }
                        Divider()
                        Button {
                            showingImport = true
                        } label: {
                            Label(
                                importService.hasImportedLibrary ? "Re-import Library" : "Import Library",
                                systemImage: "square.and.arrow.down.on.square"
                            )
                        }
                        Divider()
                        Menu("Sort By") {
                            Button {
                                folderSortMode = "custom"
                            } label: {
                                Label("Manual Order", systemImage: folderSortMode == "custom" ? "checkmark" : "")
                            }
                            Button {
                                folderSortMode = "alpha"
                            } label: {
                                Label("Alphabetical", systemImage: folderSortMode == "alpha" ? "checkmark" : "")
                            }
                            Button {
                                folderSortMode = "date"
                            } label: {
                                Label("Date Created", systemImage: folderSortMode == "date" ? "checkmark" : "")
                            }
                            Button {
                                folderSortMode = "recent"
                            } label: {
                                Label("Most Recent", systemImage: folderSortMode == "recent" ? "checkmark" : "")
                            }
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                }
            }
            .environment(\.editMode, $editMode)
            .sheet(isPresented: $showingCreateFolder, onDismiss: loadFolders) {
                FolderCreationSheet(parentId: nil)
            }
            .sheet(isPresented: $showingSettings) {
                SettingsView()
            }
            .sheet(isPresented: $showingImport, onDismiss: loadFolders) {
                ImportProgressView(importService: importService) {
                    showingImport = false
                    loadFolders()
                }
            }
            .onAppear {
                loadFolders()
                // Auto-prompt on first launch if library not yet imported
                if !importService.hasImportedLibrary && !showingImport {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                        showingImport = true
                    }
                }
            }
        }
    }

    // MARK: Folder list

    private var folderList: some View {
        List {
            ForEach(displayFolders) { folder in
                NavigationLink {
                    FolderView(folder: folder)
                } label: {
                    FolderRowView(folder: folder)
                }
            }
            .onMove { source, destination in
                guard folderSortMode == "custom" else { return }
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

    // MARK: Empty state

    private var emptyState: some View {
        VStack(spacing: 20) {
            Image(systemName: "photo.on.rectangle.angled")
                .font(.system(size: 64, weight: .light))
                .foregroundStyle(.secondary)
            Text("No Folders Yet")
                .font(.title2.weight(.semibold))
            Text("Import your Photos library structure or create a folder manually.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
            VStack(spacing: 12) {
                Button {
                    showingImport = true
                } label: {
                    Label("Import from Photos", systemImage: "square.and.arrow.down.on.square")
                        .frame(maxWidth: 280)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)

                Button {
                    showingCreateFolder = true
                } label: {
                    Label("Create Folder", systemImage: "folder.badge.plus")
                        .frame(maxWidth: 280)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
            }
            .padding(.top, 8)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: Helpers

    private func loadFolders() {
        folders = dataManager.fetchFolders(parentId: nil)
    }
}

// MARK: - FolderRowView

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
                Text("\((folder.photoReferences ?? []).count) photos")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}
