import SwiftUI

/// Large iPhoto-style title section. SF Pro bold, left aligned,
/// trailing slot for action buttons.
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
        HStack(alignment: .lastTextBaseline) {
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.system(size: 34, weight: .bold))
                    .foregroundStyle(Theme.Palette.text)
                if let subtitle {
                    Text(subtitle)
                        .font(.system(size: 13, weight: .regular))
                        .foregroundStyle(Theme.Palette.textMuted)
                }
            }
            Spacer()
            trailing()
        }
        .padding(.horizontal, 20)
        .padding(.top, 8)
        .padding(.bottom, 14)
    }
}

/// Toolbar icon button. Plain SF symbol in system blue — exactly the
/// affordance iPhoto / Photos.app uses.
struct GlassIconButton: View {
    let systemName: String
    let action: () -> Void
    var size: CGFloat = 34

    var body: some View {
        Button {
            Haptics.tap()
            action()
        } label: {
            Image(systemName: systemName)
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Theme.Palette.accent)
                .frame(width: size, height: size)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

/// Search field — looks like UISearchBar.
struct HeroSearchField: View {
    let placeholder: String
    let action: () -> Void

    var body: some View {
        Button {
            Haptics.tap()
            action()
        } label: {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(Theme.Palette.textMuted)
                Text(placeholder)
                    .font(.system(size: 15))
                    .foregroundStyle(Theme.Palette.textMuted)
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 9)
            .background(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(Color(red: 0.918, green: 0.918, blue: 0.937))
            )
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 16)
        .padding(.bottom, 8)
    }
}
