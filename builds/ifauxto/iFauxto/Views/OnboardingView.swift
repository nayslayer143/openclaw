import SwiftUI

struct OnboardingView: View {
    @EnvironmentObject var dataManager: DataManager
    let onComplete: () -> Void

    @State private var selectedMode: String = "folder_list"

    private let modes: [(id: String, title: String, subtitle: String, icon: String)] = [
        ("folder_list", "Folders", "Your organized folder structure", "folder.fill"),
        ("chronological_feed", "Photo Feed", "All photos, newest first", "photo.on.rectangle"),
        ("last_opened", "Last Opened", "Pick up where you left off", "clock.arrow.circlepath"),
    ]

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            VStack(spacing: 12) {
                Text("Welcome to iFauxto")
                    .font(.largeTitle.weight(.bold))
                Text("Let's set this up your way.")
                    .font(.title3)
                    .foregroundStyle(.secondary)
            }

            VStack(spacing: 12) {
                ForEach(modes, id: \.id) { mode in
                    Button {
                        selectedMode = mode.id
                    } label: {
                        HStack(spacing: 16) {
                            Image(systemName: mode.icon)
                                .font(.title2)
                                .frame(width: 36)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(mode.title)
                                    .font(.body.weight(.semibold))
                                Text(mode.subtitle)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            if selectedMode == mode.id {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(.accentColor)
                            }
                        }
                        .padding(16)
                        .background(
                            RoundedRectangle(cornerRadius: 12)
                                .fill(selectedMode == mode.id ? Color.accentColor.opacity(0.1) : Color(.systemGray6))
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(selectedMode == mode.id ? Color.accentColor : Color.clear, lineWidth: 2)
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 24)

            Spacer()

            Button {
                let settings = dataManager.getOrCreateSettings()
                settings.homeViewMode = selectedMode
                settings.hasCompletedOnboarding = true
                try? dataManager.modelContext.save()
                onComplete()
            } label: {
                Text("Get Started")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
            }
            .buttonStyle(.borderedProminent)
            .padding(.horizontal, 24)
            .padding(.bottom, 32)
        }
    }
}
