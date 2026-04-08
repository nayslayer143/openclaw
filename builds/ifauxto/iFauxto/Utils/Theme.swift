import SwiftUI

/// iFauxto theme — modeled directly on iPhoto.
/// Light backgrounds, San Francisco type, system blue accent, Apple-yellow folders.
enum Theme {

    // MARK: - Color

    enum Palette {
        /// iOS grouped-list background — what iPhoto / Photos.app sit on.
        static let bg           = Color(red: 0.949, green: 0.949, blue: 0.969)   // #F2F2F7
        /// Card / list-cell background.
        static let bgElevated   = Color.white
        static let bgCard       = Color.white

        static let text         = Color(red: 0.110, green: 0.110, blue: 0.118)   // #1C1C1E
        static let textMuted    = Color(red: 0.557, green: 0.557, blue: 0.576)   // #8E8E93
        static let textDim      = Color(red: 0.780, green: 0.780, blue: 0.800)

        /// Apple system blue — iPhoto's selection / link / action color.
        static let accent       = Color(red: 0.000, green: 0.478, blue: 1.000)   // #007AFF
        static let accentSoft   = Color(red: 0.357, green: 0.612, blue: 1.000)
        static let accentGlow   = Color(red: 0.000, green: 0.478, blue: 1.000).opacity(0.18)

        /// Apple Finder / iPhoto folder yellow.
        static let folder       = Color(red: 1.000, green: 0.831, blue: 0.310)   // #FFD44F
        static let folderEdge   = Color(red: 0.918, green: 0.733, blue: 0.184)

        static let divider      = Color(red: 0.847, green: 0.847, blue: 0.859)   // #D8D8DB
        static let stroke       = Color.black.opacity(0.08)
    }

    // MARK: - Typography (San Francisco only — no serif)

    enum Font {
        /// Large titles, exactly like iOS navigation .large titles.
        static func display(_ size: CGFloat, weight: SwiftUI.Font.Weight = .bold) -> SwiftUI.Font {
            .system(size: size, weight: weight, design: .default)
        }
        /// Body/control labels.
        static func title(_ size: CGFloat, weight: SwiftUI.Font.Weight = .semibold) -> SwiftUI.Font {
            .system(size: size, weight: weight, design: .default)
        }
        static func body(_ size: CGFloat = 16, weight: SwiftUI.Font.Weight = .regular) -> SwiftUI.Font {
            .system(size: size, weight: weight, design: .default)
        }
        static func mono(_ size: CGFloat = 12, weight: SwiftUI.Font.Weight = .medium) -> SwiftUI.Font {
            .system(size: size, weight: weight, design: .monospaced)
        }
    }

    // MARK: - Motion

    enum Motion {
        static let snappy    = Animation.spring(response: 0.32, dampingFraction: 0.78)
        static let bouncy    = Animation.spring(response: 0.45, dampingFraction: 0.72)
        static let soft      = Animation.spring(response: 0.55, dampingFraction: 0.86)
        static let instant   = Animation.interactiveSpring(response: 0.22, dampingFraction: 0.86)
    }

    // MARK: - Shape

    enum Radius {
        static let s: CGFloat  = 8
        static let m: CGFloat  = 12
        static let l: CGFloat  = 14
        static let xl: CGFloat = 18
    }
}

// MARK: - View modifiers

extension View {
    func brandBackground() -> some View {
        self.background(Theme.Palette.bg.ignoresSafeArea())
    }

    /// White card with hairline divider stroke and a soft drop shadow —
    /// the iPhoto / Photos.app cell look.
    func iphotoCard(radius: CGFloat = Theme.Radius.l) -> some View {
        self
            .background(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .fill(Theme.Palette.bgElevated)
            )
            .overlay(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .strokeBorder(Theme.Palette.stroke, lineWidth: 0.5)
            )
            .shadow(color: .black.opacity(0.06), radius: 6, x: 0, y: 2)
    }

    /// Legacy alias used by earlier views — same as iphotoCard now.
    func glassCard(radius: CGFloat = Theme.Radius.l, stroke: Bool = true) -> some View {
        iphotoCard(radius: radius)
    }

    func elevatedCard(radius: CGFloat = Theme.Radius.l) -> some View {
        iphotoCard(radius: radius)
    }
}
