import Foundation

/// Curated `EditAdjustments` presets — VSCO-style starting points the
/// user can tap and tune from. Each preset is a name + thumbnail color +
/// adjustments delta.
struct EditPreset: Identifiable, Equatable {
    let id: String
    let name: String
    let adjustments: EditAdjustments
}

enum EditPresets {

    static let all: [EditPreset] = [
        EditPreset(id: "original", name: "Original", adjustments: EditAdjustments()),

        // Warm, sunny daylight — adds a hint of saturation and warmth.
        EditPreset(id: "golden", name: "Golden", adjustments: {
            var a = EditAdjustments()
            a.exposure = 0.10
            a.contrast = 0.08
            a.saturation = 0.18
            a.temperature = 0.18
            a.shadows = 0.12
            return a
        }()),

        // Cool / cinematic — pulls warmth out, lifts shadows.
        EditPreset(id: "cinema", name: "Cinema", adjustments: {
            var a = EditAdjustments()
            a.contrast = 0.22
            a.saturation = -0.12
            a.temperature = -0.20
            a.shadows = 0.20
            a.highlights = -0.10
            a.vignette = 0.20
            return a
        }()),

        // Faded / matte film look.
        EditPreset(id: "faded", name: "Faded", adjustments: {
            var a = EditAdjustments()
            a.contrast = -0.18
            a.saturation = -0.10
            a.shadows = 0.30
            a.highlights = -0.20
            a.grain = 0.18
            return a
        }()),

        // Punchy / bold colors.
        EditPreset(id: "punch", name: "Punch", adjustments: {
            var a = EditAdjustments()
            a.exposure = 0.05
            a.contrast = 0.30
            a.saturation = 0.30
            a.shadows = -0.10
            return a
        }()),

        // High-contrast black and white.
        EditPreset(id: "noir", name: "Noir", adjustments: {
            var a = EditAdjustments()
            a.contrast = 0.40
            a.saturation = -1.0
            a.shadows = -0.15
            a.highlights = 0.10
            a.vignette = 0.30
            a.grain = 0.20
            return a
        }()),

        // Soft pastels — low contrast, lifted shadows, mild warmth.
        EditPreset(id: "pastel", name: "Pastel", adjustments: {
            var a = EditAdjustments()
            a.contrast = -0.22
            a.saturation = -0.08
            a.temperature = 0.10
            a.shadows = 0.40
            a.highlights = -0.15
            return a
        }()),

        // Cold blue grade.
        EditPreset(id: "frost", name: "Frost", adjustments: {
            var a = EditAdjustments()
            a.contrast = 0.15
            a.saturation = -0.18
            a.temperature = -0.40
            a.highlights = 0.05
            return a
        }())
    ]
}
