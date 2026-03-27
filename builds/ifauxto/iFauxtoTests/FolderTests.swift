import Testing
import Foundation
@testable import iFauxto

@Suite("Folder Model")
struct FolderTests {

    @Test("Folder initializes with generated UUID id")
    func folderHasUUID() {
        let folder = Folder(name: "Vacation", parentId: nil, order: 0)
        #expect(!folder.id.isEmpty)
        #expect(UUID(uuidString: folder.id) != nil)
    }

    @Test("Folder stores name and parentId correctly")
    func folderStoresFields() {
        let parent = Folder(name: "Travel", parentId: nil, order: 0)
        let child = Folder(name: "Japan", parentId: parent.id, order: 1)
        #expect(child.name == "Japan")
        #expect(child.parentId == parent.id)
        #expect(child.order == 1)
    }

    @Test("Root folder has nil parentId")
    func rootFolderHasNilParent() {
        let folder = Folder(name: "Root", parentId: nil, order: 0)
        #expect(folder.parentId == nil)
    }

    @Test("Folder createdAt is set on init")
    func folderHasCreatedAt() {
        let before = Date()
        let folder = Folder(name: "Test", parentId: nil, order: 0)
        let after = Date()
        #expect(folder.createdAt >= before)
        #expect(folder.createdAt <= after)
    }
}
