import CloudKit
import Foundation

/// Placeholder for CloudKit-specific operations (conflict resolution, sharing, etc.).
/// Core sync is handled by SwiftData's ModelConfiguration. This class extends as needed.
final class CloudKitService {
    static let containerIdentifier = "iCloud.com.ifauxto.app"
    private let container: CKContainer

    init() {
        container = CKContainer(identifier: Self.containerIdentifier)
    }

    /// Checks whether the user is signed into iCloud.
    func checkAccountStatus() async throws -> CKAccountStatus {
        return try await container.accountStatus()
    }
}
