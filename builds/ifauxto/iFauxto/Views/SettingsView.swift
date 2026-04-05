import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var dataManager: DataManager
    @Environment(\.dismiss) var dismiss

    @State private var homeMode: String = "folder_list"

    private let modes: [(id: String, label: String)] = [
        ("folder_list", "Folders"),
        ("chronological_feed", "Photo Feed"),
        ("last_opened", "Last Opened"),
    ]

    var body: some View {
        NavigationStack {
            List {
                Section("Home Screen") {
                    ForEach(modes, id: \.id) { mode in
                        Button {
                            homeMode = mode.id
                        } label: {
                            HStack {
                                Text(mode.label)
                                    .foregroundStyle(.primary)
                                Spacer()
                                if homeMode == mode.id {
                                    Image(systemName: "checkmark")
                                        .foregroundStyle(.accentColor)
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        let settings = dataManager.getOrCreateSettings()
                        settings.homeViewMode = homeMode
                        try? dataManager.modelContext.save()
                        dismiss()
                    }
                }
            }
            .onAppear {
                homeMode = dataManager.getOrCreateSettings().homeViewMode
            }
        }
    }
}
