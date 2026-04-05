import Foundation

struct SearchResult: Identifiable {
    let id: String  // PHAsset localIdentifier
    let matchedTags: [String]
}

final class SearchService {
    private let tagStore: TagStore

    init(tagStore: TagStore) {
        self.tagStore = tagStore
    }

    func search(query: String) -> [SearchResult] {
        guard !query.trimmingCharacters(in: .whitespaces).isEmpty else { return [] }
        let assetIds = (try? tagStore.search(query: query)) ?? []
        return assetIds.map { SearchResult(id: $0, matchedTags: [query]) }
    }

    func suggestions(prefix: String) -> [String] {
        guard prefix.count >= 2 else { return [] }
        return (try? tagStore.suggestions(prefix: prefix)) ?? []
    }
}
