import SwiftUI

private struct OnboardingMode: Identifiable {
    let id: String
    let title: String
    let subtitle: String
    let icon: String
}

struct OnboardingView: View {
    @EnvironmentObject var dataManager: DataManager
    let onComplete: () -> Void

    @State private var selectedMode: String = "folder_list"

    private let modes: [OnboardingMode] = [
        OnboardingMode(id: "folder_list", title: "Folders", subtitle: "Your organized folder structure", icon: "folder.fill"),
        OnboardingMode(id: "chronological_feed", title: "Photo Feed", subtitle: "All photos, newest first", icon: "photo.on.rectangle"),
        OnboardingMode(id: "last_opened", title: "Last Opened", subtitle: "Pick up where you left off", icon: "clock.arrow.circlepath"),
    ]

    var body: some View {
        VStack(spacing: 32) {
            Spacer()
            headerSection
            modeSelector
            Spacer()
            getStartedButton
        }
    }

    private var headerSection: some View {
        VStack(spacing: 12) {
            Text("Welcome to iFauxto")
                .font(.largeTitle.weight(.bold))
            Text("Let's set this up your way.")
                .font(.title3)
                .foregroundStyle(.secondary)
        }
    }

    private var modeSelector: some View {
        VStack(spacing: 12) {
            ForEach(modes) { mode in
                modeCard(mode)
            }
        }
        .padding(.horizontal, 24)
    }

    private func modeCard(_ mode: OnboardingMode) -> some View {
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
                        .foregroundColor(.accentColor)
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

    private var getStartedButton: some View {
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
