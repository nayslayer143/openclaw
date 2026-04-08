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
    @State private var appeared = false

    private let modes: [OnboardingMode] = [
        OnboardingMode(id: "folder_list",
                       title: "Albums",
                       subtitle: "Your folder structure, untouched.",
                       icon: "folder.fill"),
        OnboardingMode(id: "chronological_feed",
                       title: "Photo Feed",
                       subtitle: "Every photo, newest first.",
                       icon: "photo.on.rectangle"),
        OnboardingMode(id: "last_opened",
                       title: "Last Opened",
                       subtitle: "Pick up where you left off.",
                       icon: "clock.arrow.circlepath")
    ]

    var body: some View {
        ZStack {
            Theme.Palette.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer()
                headerSection
                    .opacity(appeared ? 1 : 0)
                    .offset(y: appeared ? 0 : 16)

                Spacer().frame(height: 32)

                Text("Pick what you see when you open iFauxto.\nYou can change it later in Settings.")
                    .font(.system(size: 14))
                    .foregroundStyle(Theme.Palette.textMuted)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
                    .opacity(appeared ? 1 : 0)

                Spacer().frame(height: 24)

                modeSelector
                    .opacity(appeared ? 1 : 0)
                    .offset(y: appeared ? 0 : 24)

                Spacer()

                getStartedButton
                    .opacity(appeared ? 1 : 0)
                    .offset(y: appeared ? 0 : 24)
            }
        }
        .onAppear {
            withAnimation(.spring(response: 0.6, dampingFraction: 0.82).delay(0.1)) {
                appeared = true
            }
        }
    }

    private var headerSection: some View {
        VStack(spacing: 14) {
            Image(systemName: "photo.stack.fill")
                .font(.system(size: 54, weight: .regular))
                .foregroundStyle(Theme.Palette.folder)
                .symbolRenderingMode(.hierarchical)

            Text("Welcome to iFauxto")
                .font(.system(size: 30, weight: .bold))
                .foregroundStyle(Theme.Palette.text)
                .multilineTextAlignment(.center)

            Text("Your photos. Your order.")
                .font(.system(size: 16))
                .foregroundStyle(Theme.Palette.textMuted)
        }
    }

    private var modeSelector: some View {
        VStack(spacing: 0) {
            ForEach(Array(modes.enumerated()), id: \.element.id) { index, mode in
                modeRow(mode)
                if index < modes.count - 1 {
                    Rectangle()
                        .fill(Theme.Palette.divider)
                        .frame(height: 0.5)
                        .padding(.leading, 60)
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
        .padding(.horizontal, 20)
    }

    private func modeRow(_ mode: OnboardingMode) -> some View {
        let isSelected = selectedMode == mode.id
        return Button {
            Haptics.select()
            withAnimation(Theme.Motion.snappy) {
                selectedMode = mode.id
            }
        } label: {
            HStack(spacing: 14) {
                Image(systemName: mode.icon)
                    .font(.system(size: 22))
                    .foregroundStyle(Theme.Palette.accent)
                    .frame(width: 32)

                VStack(alignment: .leading, spacing: 1) {
                    Text(mode.title)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(Theme.Palette.text)
                    Text(mode.subtitle)
                        .font(.system(size: 13))
                        .foregroundStyle(Theme.Palette.textMuted)
                }

                Spacer()

                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 20))
                    .foregroundStyle(isSelected ? Theme.Palette.accent : Theme.Palette.textDim)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 13)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private var getStartedButton: some View {
        Button {
            Haptics.success()
            let dm: DataManager = dataManager
            let settings = dm.getOrCreateSettings()
            settings.homeViewMode = selectedMode
            settings.hasCompletedOnboarding = true
            dm.saveSettings()
            onComplete()
        } label: {
            Text("Get Started")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 15)
                .background(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(Theme.Palette.accent)
                )
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 20)
        .padding(.bottom, 36)
    }
}
