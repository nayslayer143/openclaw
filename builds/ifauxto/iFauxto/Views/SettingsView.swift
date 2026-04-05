import SwiftUI

private struct ModeOption: Identifiable {
    let id: String
    let label: String
}

struct SettingsView: View {
    @EnvironmentObject var dataManager: DataManager
    @Environment(\.dismiss) var dismiss

    @State private var homeMode: String = "folder_list"

    private let modes: [ModeOption] = [
        ModeOption(id: "folder_list", label: "Folders"),
        ModeOption(id: "chronological_feed", label: "Photo Feed"),
        ModeOption(id: "last_opened", label: "Last Opened"),
    ]

    var body: some View {
        NavigationStack {
            List {
                Section("Home Screen") {
                    ForEach(modes) { mode in
                        modeRow(mode)
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

    private func modeRow(_ mode: ModeOption) -> some View {
        Button {
            homeMode = mode.id
        } label: {
            HStack {
                Text(mode.label)
                    .foregroundStyle(.primary)
                Spacer()
                if homeMode == mode.id {
                    Image(systemName: "checkmark")
                        .foregroundColor(.accentColor)
                }
            }
        }
    }
}
