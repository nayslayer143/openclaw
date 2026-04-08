import SwiftUI

/// Top bar for pushed/modal screens. Looks like a UIKit nav bar but
/// always exposes back + home arrows so users can jump anywhere.
struct BrandTopBar<Trailing: View>: View {
    let title: String
    let subtitle: String?
    let onBack: (() -> Void)?
    let onHome: (() -> Void)?
    let trailing: () -> Trailing

    init(
        title: String,
        subtitle: String? = nil,
        onBack: (() -> Void)? = nil,
        onHome: (() -> Void)? = nil,
        @ViewBuilder trailing: @escaping () -> Trailing = { EmptyView() }
    ) {
        self.title = title
        self.subtitle = subtitle
        self.onBack = onBack
        self.onHome = onHome
        self.trailing = trailing
    }

    var body: some View {
        ZStack {
            // Title centered like a UIKit nav bar.
            VStack(spacing: 1) {
                Text(title)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(Theme.Palette.text)
                    .lineLimit(1)
                if let subtitle {
                    Text(subtitle)
                        .font(.system(size: 11, weight: .regular))
                        .foregroundStyle(Theme.Palette.textMuted)
                        .lineLimit(1)
                }
            }

            HStack(spacing: 4) {
                if let onBack {
                    Button {
                        Haptics.tap()
                        onBack()
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "chevron.left")
                                .font(.system(size: 17, weight: .semibold))
                            Text("Back")
                                .font(.system(size: 17))
                        }
                        .foregroundStyle(Theme.Palette.accent)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Back")
                }
                if let onHome {
                    GlassIconButton(systemName: "house.fill") {
                        onHome()
                    }
                    .accessibilityLabel("Home")
                }
                Spacer()
                trailing()
            }
            .padding(.horizontal, 12)
        }
        .frame(height: 44)
        .padding(.top, 4)
        .padding(.bottom, 6)
        .background(
            ZStack {
                Theme.Palette.bg.opacity(0.92)
                Rectangle()
                    .fill(Theme.Palette.divider)
                    .frame(height: 0.5)
                    .frame(maxHeight: .infinity, alignment: .bottom)
            }
        )
    }
}
