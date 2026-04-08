import SwiftUI

/// Shared brand header. Wordmark + optional tagline + trailing slot.
struct BrandHeader<Trailing: View>: View {
    let title: String
    let subtitle: String?
    let trailing: () -> Trailing

    init(
        title: String = "iFauxto",
        subtitle: String? = nil,
        @ViewBuilder trailing: @escaping () -> Trailing = { EmptyView() }
    ) {
        self.title = title
        self.subtitle = subtitle
        self.trailing = trailing
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(Theme.Font.display(32))
                    .foregroundStyle(Theme.Palette.text)
                    .kerning(-0.5)
                if let subtitle {
                    Text(subtitle)
                        .font(Theme.Font.body(13, weight: .medium))
                        .foregroundStyle(Theme.Palette.textMuted)
                }
            }
            Spacer()
            trailing()
        }
        .padding(.horizontal, 20)
        .padding(.top, 8)
        .padding(.bottom, 12)
    }
}

/// Standard circular glass icon button used in toolbars.
struct GlassIconButton: View {
    let systemName: String
    let action: () -> Void
    var size: CGFloat = 38

    var body: some View {
        Button {
            Haptics.tap()
            action()
        } label: {
            Image(systemName: systemName)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(Theme.Palette.text)
                .frame(width: size, height: size)
                .background(
                    Circle().fill(.ultraThinMaterial)
                )
                .overlay(
                    Circle().strokeBorder(Theme.Palette.stroke, lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
    }
}

/// Hero search pill — ornamental trigger that opens real search.
struct HeroSearchField: View {
    let placeholder: String
    let action: () -> Void

    var body: some View {
        Button {
            Haptics.tap()
            action()
        } label: {
            HStack(spacing: 12) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(Theme.Palette.accent)
                Text(placeholder)
                    .font(Theme.Font.body(15, weight: .medium))
                    .foregroundStyle(Theme.Palette.textMuted)
                Spacer()
                Image(systemName: "sparkles")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.Palette.accent.opacity(0.7))
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 14)
            .background(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(.ultraThinMaterial)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .strokeBorder(
                        LinearGradient(
                            colors: [Theme.Palette.accent.opacity(0.5), Theme.Palette.stroke],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        lineWidth: 1
                    )
            )
            .shadow(color: Theme.Palette.accentGlow, radius: 14, x: 0, y: 6)
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 20)
    }
}
