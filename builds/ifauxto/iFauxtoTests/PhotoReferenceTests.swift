import Testing
@testable import iFauxto

@Suite("PhotoReference Model")
struct PhotoReferenceTests {

    @Test("PhotoReference stores PHAsset localIdentifier as id")
    func storesAssetIdentifier() {
        let assetId = "ABCD-1234-PHAsset-LocalIdentifier"
        let ref = PhotoReference(assetIdentifier: assetId, folderId: "folder-1", orderIndex: 0)
        #expect(ref.id == assetId)
        #expect(ref.folderId == "folder-1")
        #expect(ref.orderIndex == 0)
    }

    @Test("Two refs with different identifiers are distinct")
    func distinctIdentifiers() {
        let ref1 = PhotoReference(assetIdentifier: "id-1", folderId: "f", orderIndex: 0)
        let ref2 = PhotoReference(assetIdentifier: "id-2", folderId: "f", orderIndex: 1)
        #expect(ref1.id != ref2.id)
    }
}
