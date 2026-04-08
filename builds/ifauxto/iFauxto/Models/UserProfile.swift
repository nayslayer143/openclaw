import SwiftData
import Foundation

/// A signed-in user's local profile. Mirrors what the auth provider
/// gave us so the app can run offline. Multi-provider ready.
@Model
final class UserProfile {
    @Attribute(.unique) var id: String = ""
    var displayName: String = ""
    var email: String = ""
    var providerRaw: String = "apple"
    var avatarURL: String = ""
    var createdAt: Date = Date()
    var updatedAt: Date = Date()

    var provider: AuthProvider {
        get { AuthProvider(rawValue: providerRaw) ?? .apple }
        set { providerRaw = newValue.rawValue }
    }

    init(id: String, displayName: String, email: String, provider: AuthProvider, avatarURL: String = "") {
        self.id = id
        self.displayName = displayName
        self.email = email
        self.providerRaw = provider.rawValue
        self.avatarURL = avatarURL
        self.createdAt = Date()
        self.updatedAt = Date()
    }
}

enum AuthProvider: String, Codable, CaseIterable {
    case apple
    case google
    case email
    case anonymous

    var label: String {
        switch self {
        case .apple:     return "Apple"
        case .google:    return "Google"
        case .email:     return "Email"
        case .anonymous: return "Anonymous"
        }
    }
}
