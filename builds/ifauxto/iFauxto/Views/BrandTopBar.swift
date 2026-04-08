import SwiftUI

/// Custom top bar for pushed/modal screens. Always provides a back arrow
/// and an explicit "home" button to jump to the root view.
///
/// Used instead of the system navigation bar so the chrome matches the
/// brand (serif titles, tangerine accents, glass buttons).
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
        HStack(alignment: .center, spacing: 10) {
            if let onBack {
                GlassIconButton(systemName: "chevron.left") {
                    onBack()
                }
                .accessibilityLabel("Back")
            }

            if let onHome {
                GlassIconButton(systemName: "house.fill") {
                    onHome()
                }
                .accessibilityLabel("Home")
            }

            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(Theme.Font.display(22))
                    .foregroundStyle(Theme.Palette.text)
                    .lineLimit(1)
                    .truncationMode(.middle)
                if let subtitle {
                    Text(subtitle)
                        .font(Theme.Font.body(11, weight: .medium))
                        .foregroundStyle(Theme.Palette.textMuted)
                        .lineLimit(1)
                }
            }
            .padding(.leading, 4)

            Spacer()

            trailing()
        }
        .padding(.horizontal, 16)
        .padding(.top, 10)
        .padding(.bottom, 12)
        .background(
            LinearGradient(
                colors: [Theme.Palette.bg, Theme.Palette.bg.opacity(0)],
                startPoint: .top,
                endPoint: .bottom
            )
            .allowsHitTesting(false)
        )
    }
}
