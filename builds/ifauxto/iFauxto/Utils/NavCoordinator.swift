import SwiftUI

/// Holds the root navigation path so any descendant view can pop to root
/// (return to home) without bubbling dismiss calls up the stack.
@MainActor
final class NavCoordinator: ObservableObject {
    @Published var path = NavigationPath()

    func popToRoot() {
        path = NavigationPath()
        Haptics.soft()
    }

    func pop() {
        guard !path.isEmpty else { return }
        path.removeLast()
        Haptics.tap()
    }

    func push<V: Hashable>(_ value: V) {
        path.append(value)
    }
}
