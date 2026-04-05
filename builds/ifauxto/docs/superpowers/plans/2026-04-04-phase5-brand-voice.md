# Phase 5: Brand Voice

> Part of iFauxto v2 plan. Read `2026-04-04-ifauxto-v2-plan.md` first. Phases 1-4 must be complete.

**Goal:** Apply playful, slightly anti-Apple brand copy throughout the app. Centralized in one constants file for consistency.

---

### Task 1: Create BrandCopy constants and apply to all views

**Files:**
- Create: `iFauxto/Utils/BrandCopy.swift`
- Modify: `iFauxto/Views/HomeView.swift`
- Modify: `iFauxto/Views/FolderView.swift`
- Modify: `iFauxto/Views/SearchView.swift`
- Modify: `iFauxto/Views/OnboardingView.swift`

- [ ] **Step 1: Create BrandCopy.swift**

Create `iFauxto/Utils/BrandCopy.swift`:

```swift
import Foundation

enum BrandCopy {
    static let tagline = "Your photos. Your order."
    static let onboardingWelcome = "Welcome to iFauxto"
    static let onboardingSubtitle = "Let's set this up your way."
    static let emptyFolderTitle = "Nothing here yet"
    static let emptyFolderMessage = "Drag photos in, or just enjoy the silence."
    static let emptyLibraryTitle = "No Folders Yet"
    static let emptyLibraryMessage = "Import your Photos library structure or create a folder manually."
    static let searchPlaceholder = "Find anything. Instantly."
    static let searchNoResults = "Nothing matched"
    static let editSaved = "Saved. Your style, preserved."
    static let folderReordered = "Locked in."
    static let noSurprises = "No surprises. Just your system."
    static let indexingProgress = "Learning your library... %d%% done"
    static let permissionTitle = "iFauxto needs access to your Photos library to get started."
    static let permissionButton = "Grant Access"
    static let getStarted = "Get Started"
}
```

- [ ] **Step 2: Apply BrandCopy to OnboardingView**

In `iFauxto/Views/OnboardingView.swift`, replace the hardcoded strings:
- `"Welcome to iFauxto"` → `BrandCopy.onboardingWelcome`
- `"Let's set this up your way."` → `BrandCopy.onboardingSubtitle`
- `"Get Started"` → `BrandCopy.getStarted`

- [ ] **Step 3: Apply BrandCopy to HomeView**

In `iFauxto/Views/HomeView.swift`, in the `emptyState` view:
- `"No Folders Yet"` → `BrandCopy.emptyLibraryTitle`
- `"Import your Photos library..."` → `BrandCopy.emptyLibraryMessage`

- [ ] **Step 4: Apply BrandCopy to FolderView**

In `iFauxto/Views/FolderView.swift`, in the `emptyState` view:
- `"Empty Folder"` → `BrandCopy.emptyFolderTitle`
- `"Tap ··· to add photos or create a subfolder."` → `BrandCopy.emptyFolderMessage`

- [ ] **Step 5: Apply BrandCopy to SearchView**

In `iFauxto/Views/SearchView.swift`:
- `"Find anything. Instantly."` → `BrandCopy.searchPlaceholder`
- `"No results for..."` → replace with `BrandCopy.searchNoResults`

- [ ] **Step 6: Apply BrandCopy to ContentView**

In `iFauxto/App/ContentView.swift`, in `PhotoPermissionView`:
- `"iFauxto needs access..."` → `BrandCopy.permissionTitle`
- `"Grant Access"` → `BrandCopy.permissionButton`

- [ ] **Step 7: Build and run all tests**

```bash
cd ~/openclaw/builds/ifauxto && xcodegen generate && xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -30
```

Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add iFauxto/Utils/BrandCopy.swift iFauxto/Views/HomeView.swift iFauxto/Views/FolderView.swift iFauxto/Views/SearchView.swift iFauxto/Views/OnboardingView.swift iFauxto/App/ContentView.swift && git commit -m "feat: add centralized BrandCopy and apply brand voice to all views"
```

---

## Phase 5 Complete

After Task 1:
- All user-facing strings centralized in BrandCopy enum
- Consistent brand voice across all views
- Easy to update copy in one place for future iterations
