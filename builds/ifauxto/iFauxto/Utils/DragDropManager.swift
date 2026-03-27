import Foundation

/// Stateless helpers for drag-and-drop index math.
/// All mutations are returned as new arrays — callers persist the result.
enum DragDropManager {

    /// Swaps the item with `draggedId` into the position of `targetId` and vice versa.
    /// Swap semantics: drop source takes target's slot, target fills the gap.
    /// - Returns: reordered array, or original array if either id is not found.
    static func reorder<T: Identifiable>(
        _ items: [T],
        draggedId: T.ID,
        targetId: T.ID
    ) -> [T] where T.ID: Equatable {
        guard draggedId != targetId,
              let sourceIndex = items.firstIndex(where: { $0.id == draggedId }),
              let destinationIndex = items.firstIndex(where: { $0.id == targetId })
        else { return items }

        var result = items
        result.swapAt(sourceIndex, destinationIndex)
        return result
    }
}
