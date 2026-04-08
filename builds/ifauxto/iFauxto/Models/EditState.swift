import SwiftData
import Foundation

/// Structure holding normalized float values for common photo adjustments.
struct EditAdjustments: Codable, Equatable {
    var exposure: Float = 0.0
    var contrast: Float = 0.0
    var saturation: Float = 0.0
    var temperature: Float = 0.0
    var highlights: Float = 0.0
    var shadows: Float = 0.0
    var grain: Float = 0.0
    var vignette: Float = 0.0
    /// Quarter-turn rotations clockwise (0-3). Persists across sessions.
    var rotationQuarterTurns: Int = 0
    /// Normalized crop rectangle in 0..1 space. Default is full image.
    var cropOriginX: CGFloat = 0
    var cropOriginY: CGFloat = 0
    var cropWidth: CGFloat = 1
    var cropHeight: CGFloat = 1

    var hasCustomCrop: Bool {
        cropOriginX > 0.001 || cropOriginY > 0.001 || cropWidth < 0.999 || cropHeight < 0.999
    }
}

/// SwiftData model representing non-destructive photo editing state.
@Model final class EditState {
    @Attribute(.unique) var photoId: String = ""
    var adjustmentsData: Data = Data()
    var createdAt: Date = Date()
    var updatedAt: Date = Date()

    /// Computed property to access adjustments easily.
    var adjustments: EditAdjustments {
        get {
            do {
                return try JSONDecoder().decode(EditAdjustments.self, from: adjustmentsData)
            } catch {
                print("Error decoding adjustments data: \(error)")
                return EditAdjustments() // Return default if decoding fails
            }
        }
        set {
            guard let data = try? JSONEncoder().encode(newValue) else {
                print("Error encoding adjustments.")
                return
            }
            self.adjustmentsData = data
            self.updatedAt = Date()
        }
    }

    /// Initializes a new EditState record.
    init(photoId: String, adjustments: EditAdjustments) {
        self.photoId = photoId
        self.adjustments = adjustments
        self.createdAt = Date()
        self.updatedAt = Date()
    }
}