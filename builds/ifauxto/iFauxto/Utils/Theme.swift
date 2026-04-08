import SwiftUI

/// iFauxto brand system. Playful, slightly anti-Apple, unmistakable.
/// Dark-first. Sharp typography. Warm accent. Glass materials.
enum Theme {

    // MARK: - Color

    enum Palette {
        /// Near-black with a warm tint — not Apple's cold #000
        static let bg           = Color(red: 0.055, green: 0.055, blue: 0.063)
        static let bgElevated   = Color(red: 0.094, green: 0.094, blue: 0.106)
        static let bgCard       = Color(red: 0.125, green: 0.125, blue: 0.137)

        /// Warm off-white text — reduces eye strain vs pure white
        static let text         = Color(red: 0.965, green: 0.961, blue: 0.949)
        static let textMuted    = Color(red: 0.608, green: 0.604, blue: 0.588)
        static let textDim      = Color(red: 0.408, green: 0.404, blue: 0.388)

        /// Tangerine — the anti-Apple-blue.
        static let accent       = Color(red: 1.000, green: 0.463, blue: 0.118)
        static let accentSoft   = Color(red: 1.000, green: 0.580, blue: 0.290)
        static let accentGlow   = Color(red: 1.000, green: 0.463, blue: 0.118).opacity(0.35)

        static let divider      = Color.white.opacity(0.06)
        static let stroke       = Color.white.opacity(0.10)
    }

    // MARK: - Typography

    /// Serif display face for brand moments. Falls back to rounded sans elsewhere.
    enum Font {
        static func display(_ size: CGFloat, weight: SwiftUI.Font.Weight = .black) -> SwiftUI.Font {
            .system(size: size, weight: weight, design: .serif)
        }
        static func title(_ size: CGFloat, weight: SwiftUI.Font.Weight = .bold) -> SwiftUI.Font {
            .system(size: size, weight: weight, design: .rounded)
        }
        static func body(_ size: CGFloat = 16, weight: SwiftUI.Font.Weight = .regular) -> SwiftUI.Font {
            .system(size: size, weight: weight, design: .rounded)
        }
        static func mono(_ size: CGFloat = 12, weight: SwiftUI.Font.Weight = .medium) -> SwiftUI.Font {
            .system(size: size, weight: weight, design: .monospaced)
        }
    }

    // MARK: - Motion

    enum Motion {
        static let snappy    = Animation.spring(response: 0.32, dampingFraction: 0.72)
        static let bouncy    = Animation.spring(response: 0.45, dampingFraction: 0.68)
        static let soft      = Animation.spring(response: 0.55, dampingFraction: 0.82)
        static let instant   = Animation.interactiveSpring(response: 0.22, dampingFraction: 0.86)
    }

    // MARK: - Shape

    enum Radius {
        static let s: CGFloat  = 10
        static let m: CGFloat  = 16
        static let l: CGFloat  = 22
        static let xl: CGFloat = 32
    }
}

// MARK: - View modifiers

extension View {
    /// Applies the app's base background.
    func brandBackground() -> some View {
        self.background(Theme.Palette.bg.ignoresSafeArea())
    }

    /// Elevated glass card — translucent, stroked, shadowed.
    func glassCard(radius: CGFloat = Theme.Radius.l, stroke: Bool = true) -> some View {
        self
            .background(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .fill(.ultraThinMaterial)
            )
            .overlay {
                if stroke {
                    RoundedRectangle(cornerRadius: radius, style: .continuous)
                        .strokeBorder(Theme.Palette.stroke, lineWidth: 1)
                }
            }
            .shadow(color: .black.opacity(0.35), radius: 18, x: 0, y: 10)
    }

    /// Solid elevated card with hairline stroke.
    func elevatedCard(radius: CGFloat = Theme.Radius.l) -> some View {
        self
            .background(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .fill(Theme.Palette.bgCard)
            )
            .overlay(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .strokeBorder(Theme.Palette.stroke, lineWidth: 1)
            )
    }
}
