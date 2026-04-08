import Foundation
import AuthenticationServices
import SwiftUI
import Combine

/// Singleton that owns the current user identity. Persists the active
/// user id in UserDefaults so re-launches restore the session, and
/// scopes the SwiftData container path per-user so switching accounts
/// never mixes data.
@MainActor
final class UserSession: ObservableObject {
    static let shared = UserSession()

    private let activeUserKey = "iFauxto.activeUserId"

    @Published private(set) var currentProfile: UserProfile?
    @Published private(set) var isAuthenticated: Bool = false

    private init() {}

    /// The on-disk directory used to scope SwiftData / Documents files
    /// for the active user. Changes when the user signs in or out.
    var activeUserDirectory: URL {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        let userId = UserDefaults.standard.string(forKey: activeUserKey) ?? "_local"
        let dir = docs.appendingPathComponent("users/\(userId)", isDirectory: true)
        if !FileManager.default.fileExists(atPath: dir.path) {
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        }
        return dir
    }

    /// Bootstraps the session at app launch. If there's an active user
    /// id but no profile in the database yet (e.g. cleared cache), the
    /// session falls back to anonymous.
    func bootstrap(dataManager: DataManager) {
        guard let activeId = UserDefaults.standard.string(forKey: activeUserKey),
              activeId != "_local" else {
            isAuthenticated = false
            currentProfile = nil
            return
        }
        currentProfile = dataManager.fetchUserProfile(id: activeId)
        isAuthenticated = currentProfile != nil
    }

    /// Sign in via Sign in with Apple credential.
    func signInWithApple(
        credential: ASAuthorizationAppleIDCredential,
        dataManager: DataManager
    ) {
        let id = credential.user
        let name: String = {
            if let n = credential.fullName {
                return [n.givenName, n.familyName].compactMap { $0 }.joined(separator: " ")
            }
            return ""
        }()
        let email = credential.email ?? ""

        // First sign-in: capture the name/email Apple gives us only once.
        // Subsequent sign-ins reuse what's stored locally.
        let profile: UserProfile
        if let existing = dataManager.fetchUserProfile(id: id) {
            if !name.isEmpty { existing.displayName = name }
            if !email.isEmpty { existing.email = email }
            existing.updatedAt = Date()
            try? dataManager.modelContext.save()
            profile = existing
        } else {
            profile = dataManager.createUserProfile(
                id: id,
                displayName: name.isEmpty ? "Apple User" : name,
                email: email,
                provider: .apple
            )
        }

        UserDefaults.standard.set(id, forKey: activeUserKey)
        currentProfile = profile
        isAuthenticated = true
    }

    /// Continue without an account. Data is stored under "_local".
    func continueAsGuest() {
        UserDefaults.standard.set("_local", forKey: activeUserKey)
        currentProfile = nil
        isAuthenticated = false
    }

    /// Sign out — wipes the active user id but leaves the on-disk store
    /// intact so the user can sign back in and pick up where they left off.
    func signOut() {
        UserDefaults.standard.removeObject(forKey: activeUserKey)
        currentProfile = nil
        isAuthenticated = false
    }
}
