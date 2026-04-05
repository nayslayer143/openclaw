# Phase 6: Performance Hardening

> Part of iFauxto v2 plan. Read `2026-04-04-ifauxto-v2-plan.md` first. Phases 1-5 must be complete.

**Goal:** Ensure the app handles 50k+ photo libraries smoothly. 60fps scroll, <30ms reorder, <200ms search, <1s launch.

---

### Task 1: Add pagination to ChronologicalFeedView

**Files:**
- Modify: `iFauxto/Views/ChronologicalFeedView.swift`

- [ ] **Step 1: Add paginated loading**

Replace the `task` modifier in `ChronologicalFeedView` with paginated loading. Change the `@State` declarations:

```swift
    @State private var assetIdentifiers: [String] = []
    @State private var isLoading = true
    @State private var loadedCount = 0
    private let pageSize = 100
```

Replace the `.task` modifier with:

```swift
            .task {
                loadNextPage()
                isLoading = false
            }
```

Add a method:

```swift
    private func loadNextPage() {
        let allIds = photoKitService.fetchAllAssetIdentifiers()
        let nextBatch = Array(allIds.dropFirst(loadedCount).prefix(pageSize))
        assetIdentifiers.append(contentsOf: nextBatch)
        loadedCount = assetIdentifiers.count
    }
```

In the `LazyVGrid`, add a load-more trigger at the end:

```swift
                        // Load more trigger
                        if loadedCount < photoKitService.fetchAllAssetIdentifiers().count {
                            Color.clear
                                .frame(height: 1)
                                .onAppear {
                                    loadNextPage()
                                }
                        }
```

- [ ] **Step 2: Build and verify**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -10
```

Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/Views/ChronologicalFeedView.swift && git commit -m "perf: add pagination to ChronologicalFeedView (100 photos per page)"
```

---

### Task 2: Add thumbnail caching

**Files:**
- Create: `iFauxto/Services/ThumbnailCache.swift`
- Modify: `iFauxto/Services/PhotoKitService.swift`

- [ ] **Step 1: Create ThumbnailCache.swift**

Create `iFauxto/Services/ThumbnailCache.swift`:

```swift
import UIKit

final class ThumbnailCache {
    static let shared = ThumbnailCache()

    private let cache = NSCache<NSString, UIImage>()

    private init() {
        cache.countLimit = 500  // Max 500 thumbnails in memory
        cache.totalCostLimit = 100 * 1024 * 1024  // 100MB
    }

    func get(key: String) -> UIImage? {
        cache.object(forKey: key as NSString)
    }

    func set(key: String, image: UIImage) {
        let cost = Int(image.size.width * image.size.height * image.scale * 4)
        cache.setObject(image, forKey: key as NSString, cost: cost)
    }
}
```

- [ ] **Step 2: Add cache lookup to PhotoKitService.loadThumbnail**

In `iFauxto/Services/PhotoKitService.swift`, modify `loadThumbnail` to check cache first.

Replace the `loadThumbnail` method with:

```swift
    func loadThumbnail(for identifier: String, targetSize: CGSize = CGSize(width: 200, height: 200)) async -> UIImage? {
        let cacheKey = "\(identifier)_\(Int(targetSize.width))x\(Int(targetSize.height))"

        // Check cache first
        if let cached = ThumbnailCache.shared.get(key: cacheKey) {
            return cached
        }

        guard let asset = fetchAsset(withIdentifier: identifier) else { return nil }
        let image = await withCheckedContinuation { continuation in
            let options = PHImageRequestOptions()
            options.deliveryMode = .highQualityFormat
            options.resizeMode = .fast
            options.isNetworkAccessAllowed = true
            options.isSynchronous = false
            PHImageManager.default().requestImage(
                for: asset,
                targetSize: targetSize,
                contentMode: .aspectFill,
                options: options
            ) { image, _ in
                continuation.resume(returning: image)
            }
        }

        // Cache the result
        if let image {
            ThumbnailCache.shared.set(key: cacheKey, image: image)
        }

        return image
    }
```

- [ ] **Step 3: Build and run all tests**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -30
```

Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/Services/ThumbnailCache.swift iFauxto/Services/PhotoKitService.swift && git commit -m "perf: add NSCache-backed thumbnail caching (500 items, 100MB limit)"
```

---

### Task 3: Optimize IndexingManager batch size and priority

**Files:**
- Modify: `iFauxto/Services/IndexingManager.swift`

- [ ] **Step 1: Tune indexing parameters**

In `iFauxto/Services/IndexingManager.swift`, adjust the `runIndexing` method:

Change `let batchSize = 10` to `let batchSize = 20`.

Change the sleep duration from `100_000_000` (100ms) to `50_000_000` (50ms) — faster indexing while still yielding.

Add a check to pause indexing when app goes to background. After the `guard !Task.isCancelled` line, add:

```swift
            // Yield more aggressively if system is under pressure
            if ProcessInfo.processInfo.isLowPowerModeEnabled {
                try? await Task.sleep(nanoseconds: 500_000_000) // 500ms in low power
            }
```

- [ ] **Step 2: Build and verify**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild build -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -10
```

Expected: BUILD SUCCEEDED

- [ ] **Step 3: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/Services/IndexingManager.swift && git commit -m "perf: tune indexing batch size and add low-power mode throttling"
```

---

## Phase 6 Complete

After all 3 tasks:
- ChronologicalFeedView loads 100 photos at a time (infinite scroll)
- Thumbnail cache prevents redundant PhotoKit requests (500 item NSCache)
- Indexing respects low-power mode
- App handles large libraries without memory pressure
