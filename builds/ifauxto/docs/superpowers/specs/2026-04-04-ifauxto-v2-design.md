# iFauxto v2 — Full Design Spec

**Date:** 2026-04-04
**Status:** Approved
**PRD:** `docs/PRD.md`
**Existing MVP:** 19 Swift files, 1,428 LOC, Phases 1-2 complete

---

## 1. Product Vision

A manual-first, customizable photo OS layered on top of Apple Photos. Looks like iPhoto, behaves like iPhoto, but gives users absolute control over structure, order, and access.

**Core positioning:** Apple Photos is algorithm-first. iFauxto is human-first.

**App name:** iFauxto
**Bundle ID:** `com.ifauxto.app`
**CloudKit container:** `iCloud.com.ifauxto.app`

---

## 2. Architecture

### 2.1 Layer Diagram

```
┌─────────────────────────────────────────────┐
│                SwiftUI Views                │
│  Home · Folder · Search · Editor · Settings │
├─────────────────────────────────────────────┤
│            View Routing Layer               │
│       HomeViewMode + AppSettings            │
├──────────────────┬──────────────────────────┤
│   SwiftData      │    SQLite FTS Store      │
│   (CloudKit)     │    (Local only)          │
│                  │                          │
│  Folder          │  TagRecord               │
│  PhotoReference  │  SearchIndex (FTS5)      │
│  EditState       │                          │
│  AppSettings     │  [Future: Embeddings]    │
├──────────────────┴──────────────────────────┤
│              Services Layer                 │
│  PhotoKitService      (exists)              │
│  DataManager          (exists)              │
│  VisionTaggingService (new)                 │
│  TagStore             (new)                 │
│  SearchService        (new)                 │
│  EditService          (new)                 │
│  IndexingManager      (new)                 │
│  SyncManager          (exists)              │
├─────────────────────────────────────────────┤
│            Apple Frameworks                 │
│  PhotoKit · Vision · CoreImage · CloudKit   │
└─────────────────────────────────────────────┘
```

### 2.2 Data Strategy — Hybrid

**SwiftData (with CloudKit sync):** Folder hierarchy, photo references, edit states, app settings. This is the existing stack — no changes needed.

**SQLite FTS5 (local only):** AI-generated tags and search index. Not synced via CloudKit — rebuilt from PHAssets on each device. Separate concern, separate store.

**Rationale:** SwiftData handles the user's organizational data (folders, order, edits) and syncs it. The search index is derived data that can be regenerated, so it doesn't need CloudKit overhead.

### 2.3 Key Invariants (carried from MVP)

- `PHAsset.localIdentifier` is the photo identity — never store UIImage
- `orderIndex` is explicit integers, never auto-sorted
- All CRUD goes through DataManager (single source of truth for SwiftData)
- Cascade delete: deleting a folder deletes its PhotoReferences
- Custom sort mode: system NEVER reorders folders unless user initiates

---

## 3. Feature Specifications

### 3.1 Feature 1 — Custom Home Screen (Entry Control)

**New models:**

```swift
// AppSettings.swift — SwiftData @Model
@Model class AppSettings {
    var homeViewMode: String  // "folder_list" | "chronological_feed" | "last_opened" | "custom_view"
    var lastOpenedViewId: String?
    var pinnedViewId: String?
    
    init() {
        self.homeViewMode = "folder_list"
    }
}
```

**New views:**
- `OnboardingView.swift` — First-launch preference picker. Shows 4 options with visual previews. Writes to AppSettings. Only shown once (tracked via AppSettings existence).
- `SettingsView.swift` — Change home mode, sort defaults. Accessible from toolbar.
- `ChronologicalFeedView.swift` — Time-ordered photo grid using PHAsset creation dates. Lazy-loaded, paginated.

**Modified files:**
- `ContentView.swift` — Replace hardcoded HomeView with routing logic:
  ```swift
  switch appSettings.homeViewMode {
  case "folder_list": HomeView()
  case "chronological_feed": ChronologicalFeedView()
  case "last_opened": // restore last view
  case "custom_view": // load pinned view
  }
  ```
- `iFauxtoApp.swift` — Ensure AppSettings singleton exists in ModelContainer.

**UX rules:**
- First launch → OnboardingView → user picks mode → never shown again
- Settings always accessible to change later
- Instant load — no spinner, no delay

---

### 3.2 Feature 2 — Fixed Folder Order (Enhancement)

**Existing behavior (keep):** `orderIndex` on Folder, drag-to-reorder, persists instantly.

**New: Sort mode toggle**

Add `sortMode` property to existing `Folder` model:

```swift
// Addition to Folder.swift
var sortMode: String = "custom"  // "custom" | "alpha" | "date" | "recent"
// Default value required — SwiftData CloudKit migration needs it
```

**Sort behavior:**
- `custom` — Display order = `orderIndex`. Drag reorder enabled. System NEVER changes order.
- `alpha` — Display order computed alphabetically. Drag reorder disabled.
- `date` — Display order by creation date. Drag reorder disabled.
- `recent` — Display order by most recently modified. Drag reorder disabled.

**Critical rule:** Non-custom sorts compute display order on the fly via `sorted()` in the view. They NEVER mutate `orderIndex`. Switching back to `custom` restores the user's manual order exactly as they left it.

**Modified files:**
- `Folder.swift` — Add `sortMode` property
- `HomeView.swift` — Add sort mode picker in toolbar, apply sort in view logic
- `FolderView.swift` — Same sort logic for photos within a folder

---

### 3.3 Feature 3 — AI Tagging + Instant Search

#### 3.3.1 Tagging Pipeline (Apple Vision — MVP)

**`VisionTaggingService.swift`** — Stateless service, processes one photo at a time:

```swift
struct PhotoTags {
    let assetId: String
    let objects: [(label: String, confidence: Float)]   // VNClassifyImageRequest
    let text: [String]                                   // VNRecognizeTextRequest (OCR)
    let faceCount: Int                                   // VNDetectFaceRectanglesRequest
    let sceneClassification: String?                     // top VNClassification
}

class VisionTaggingService {
    func tagPhoto(image: CGImage, assetId: String) async -> PhotoTags
}
```

Vision requests used:
- `VNClassifyImageRequest` — objects, scenes (beach, car, food, etc.)
- `VNRecognizeTextRequest` — OCR for screenshots, documents, signs
- `VNDetectFaceRectanglesRequest` — face count and bounding boxes

All run on-device via Neural Engine. Zero network calls. Zero cost.

#### 3.3.2 Tag Storage (SQLite FTS5)

**`TagStore.swift`** — Direct SQLite wrapper (not SwiftData):

```sql
CREATE VIRTUAL TABLE photo_tags USING fts5(
    asset_id,
    tag_type,      -- "object", "text", "face", "scene", "location", "time"
    tag_value,
    confidence UNINDEXED
);
```

Operations:
- `insertTags(assetId: String, tags: PhotoTags)`
- `search(query: String) -> [String]` — returns matching asset IDs
- `deleteTags(assetId: String)`
- `isIndexed(assetId: String) -> Bool`

#### 3.3.3 Indexing Manager

**`IndexingManager.swift`** — Background coordinator:

```swift
class IndexingManager {
    func startBackgroundIndexing()  // Called on app launch
    func indexPhoto(assetId: String) async
    func indexingProgress() -> (indexed: Int, total: Int)
}
```

Behavior:
- Runs on background queue, never blocks UI
- Processes newest photos first (progressive enrichment)
- Tracks indexed vs pending via TagStore
- Rate-limited: processes in batches of 10, yields between batches
- Pauses when app backgrounds, resumes on foreground
- 50k library: ~8 hours initial index, but search works immediately on indexed photos

#### 3.3.4 Search

**`SearchService.swift`** — Query layer:

```swift
class SearchService {
    func search(query: String) -> [SearchResult]
    func suggestions(prefix: String) -> [String]
}

struct SearchResult {
    let assetId: String
    let matchedTags: [String]
    let relevanceScore: Float
}
```

Query processing:
1. Tokenize user input
2. FTS5 MATCH query against photo_tags
3. Augment with metadata: time queries ("night") check PHAsset timestamps, location queries check EXIF
4. Rank by relevance (tag confidence + recency)
5. Return asset IDs for display

**`SearchView.swift`** — UI:
- Search bar always visible at top of main views
- As-you-type suggestions from indexed tags
- Results displayed as photo grid (reuses existing thumbnail components)
- Empty state: "Still indexing... X of Y photos processed"

**Performance targets:**
- Search response: < 200ms
- Suggestions: < 50ms
- Indexing: ~100 photos/minute background

#### 3.3.5 AI Phased Roadmap

| Phase | What | Cost | Dependency |
|---|---|---|---|
| MVP (now) | Apple Vision tags + SQLite FTS5 | Free, on-device | None |
| Phase 2 | MobileCLIP embeddings + vector search | Free, on-device, +60MB app size | MVP search UX validated |
| Phase 3 | Apple Intelligence query understanding | Free, iOS 18.1+, newer devices | FoundationModels framework |

Phase 2 adds natural language search ("cars in SF at night"). Phase 3 adds semantic reasoning. Each phase slots into the existing `SearchService` interface without touching UI.

---

### 3.4 Feature 4 — Editing System (VSCO-Inspired)

**`EditState.swift`** — SwiftData model:

```swift
@Model class EditState {
    @Attribute(.unique) var photoId: String
    @Attribute(.transformable(by: "JSONEncoder")) var adjustments: EditAdjustments  // Codable struct, SwiftData stores as JSON via Transformable
    var createdAt: Date
    var updatedAt: Date
}

struct EditAdjustments: Codable {
    var exposure: Float      // -1.0 to 1.0
    var contrast: Float      // -1.0 to 1.0
    var saturation: Float    // -1.0 to 1.0
    var temperature: Float   // -1.0 to 1.0
    var highlights: Float    // -1.0 to 1.0
    var shadows: Float       // -1.0 to 1.0
    var grain: Float         // 0.0 to 1.0
    var vignette: Float      // 0.0 to 1.0
    var presetName: String?  // optional preset identifier
}
```

**`EditService.swift`** — CIFilter pipeline:

```swift
class EditService {
    func applyAdjustments(_ adj: EditAdjustments, to image: CIImage) -> CIImage
    func renderPreview(_ adj: EditAdjustments, photo: PHAsset, size: CGSize) -> UIImage?
}
```

Filter mapping:
- exposure → `CIExposureAdjust`
- contrast → `CIColorControls`
- saturation → `CIColorControls`
- temperature → `CITemperatureAndTint`
- highlights/shadows → `CIHighlightShadowAdjust`
- grain → `CIRandomGenerator` + `CISourceOverCompositing`
- vignette → `CIVignette`

All filters chained, rendered via `CIContext` with Metal backing for GPU acceleration.

**`PhotoEditorView.swift`** — UI:
- Slider per adjustment (vertical list, VSCO-style)
- Real-time preview as sliders move
- Before/after toggle (long press to see original)
- Save button → writes EditState to SwiftData
- Cancel → discards changes
- Reset button → clears all adjustments

**Non-destructive guarantee:** Original PHAsset is never modified. EditState stores adjustments as data. Edited preview is rendered on-the-fly from original + adjustments.

**Modified files:**
- `PhotoViewer.swift` — Add "Edit" button that presents PhotoEditorView
- `PhotoThumbnailView.swift` — Show edit indicator badge if EditState exists for photo

**Future expansion (not in this build):**
- LUT imports (custom color grading files)
- Creator presets (shareable adjustment bundles)
- Batch editing (apply preset to multiple photos)

---

### 3.5 Feature 5 — Brand Voice

**`BrandCopy.swift`** — Constants file:

```swift
enum BrandCopy {
    static let tagline = "Your photos. Your order."
    static let onboardingWelcome = "Finally, your photos behave."
    static let emptyFolder = "Nothing here yet. Drag photos in, or just enjoy the silence."
    static let searchPlaceholder = "Find anything. Instantly."
    static let editSaved = "Saved. Your style, preserved."
    static let folderReordered = "Locked in. It'll be right here next time."
    static let noSurprises = "No surprises. Just your system."
    static let indexingProgress = "Learning your library... %d%% done"
    static let firstLaunchSubtitle = "Let's set this up your way."
}
```

Applied throughout all views during implementation. Tone: playful, slightly anti-Apple, respectful but irreverent.

---

## 4. Landing Page + Interactive Demo

### 4.1 Overview

A standalone web application that markets iFauxto and includes a fully interactive browser-based demo of the app.

**Location:** `landing/` directory within the ifauxto repo
**Deploy target:** Vercel / Netlify / GitHub Pages
**Tech:** HTML/CSS/JS (or lightweight React)

### 4.2 Landing Page Structure

| Section | Content |
|---|---|
| Hero | "Your photos. Your order." + floating app mockup + CTA |
| Problem | "Apple decides what you see. We think that's your job." |
| Feature 1 | Fixed folder order — animation showing drag-reorder vs Apple's reshuffling |
| Feature 2 | AI search — typing demo showing instant results |
| Feature 3 | Editing — slider animation showing before/after |
| Feature 4 | Custom home — mode selector animation |
| Interactive Demo | Full playable simulation (see below) |
| CTA | App Store link or waitlist signup |

### 4.3 Interactive Demo

A browser-based replica of iFauxto that visitors can click/tap through.

**Fidelity:**
- Matches iOS app layout, colors, typography
- Renders inside a phone frame mockup
- Touch/click interactions work naturally

**Pre-loaded content:**
- ~30 sample photos (stock/AI-generated, royalty-free)
- 5 sample folders: "Trips", "Family", "Screenshots", "Food", "Architecture"
- Pre-indexed tags for all sample photos

**Working interactions:**
- Drag-and-drop folder reorder (the killer feature — users feel it)
- Search bar with pre-indexed tags (type "beach", "night", "food")
- Photo editor with working sliders and real-time preview
- Home mode selector

### 4.4 Guided Tooltip Workflow

Step-by-step walkthrough that activates on demo load. Each step requires user action — not passive reading.

```
Step 1: "Welcome to iFauxto. This is YOUR photo library."
        → Highlights folder list
        → [Next] button or auto-advance after 3s

Step 2: "Try dragging a folder. Go ahead — it stays where you put it."
        → Tooltip arrow on a folder
        → Waits for user to drag-reorder
        → On completion: "See? No reshuffling. Ever."

Step 3: "Now try searching. Type 'beach' or 'night'."
        → Tooltip on search bar
        → Waits for user to type and see results
        → On results: "Every photo tagged automatically. On your device. Free."

Step 4: "Pick a photo. Now edit it."
        → Tooltip on a photo thumbnail
        → Opens editor on tap
        → User adjusts a slider
        → "VSCO-quality editing. Non-destructive. Your style."

Step 5: "Choose how YOUR app opens."
        → Shows home mode selector
        → User picks an option
        → "Folders? Feed? Last opened? You decide."

Step 6: "Ready to take control?"
        → CTA button pulses
        → Links to App Store / waitlist
```

**Implementation notes:**
- Tooltip engine: lightweight JS (no heavy framework needed)
- Each step has a trigger condition (user action) and completion message
- Users can skip the walkthrough and explore freely
- Walkthrough state persists in localStorage (don't re-show on return visit)

---

## 5. Execution Model

### 5.1 Roles

| Role | Entity | Responsibility |
|---|---|---|
| Manager/Director | Claude | Plans, reviews, asks questions, flags risks |
| Builder | Gemma 4 31B (via Ollama) | Writes code, implements features |
| Scout | Gemma 4 31B (ScoutClaw) | Explores codebase before each task |
| Tester | Gemma 4 31B (TestClaw) | Writes and runs tests |
| Reviewer | DeepSeek (ReviewClaw) | Adversarial code review |

### 5.2 Per-Feature Flow

```
Claude plans phase
  → ScoutClaw explores target files (Gemma 4, FREE)
Claude reviews scout findings
  → PatchClaw implements feature (Gemma 4, FREE)
Claude reviews diff
  → TestClaw writes + runs tests (Gemma 4, FREE)
Claude reviews test results
  → ReviewClaw adversarial review (DeepSeek, cheap)
Claude final decision → commit or fix cycle
```

### 5.3 Claude Checkpoints

After every dispatch, Claude checks:
1. **After scout** — Is the approach right? Are we touching the right files?
2. **After patch** — Does the code match the spec? Any anti-patterns?
3. **After tests** — Do tests validate real behavior or just compile?
4. **Red flag scan** — Performance (50k photos), memory leaks, Apple API misuse, thread safety

### 5.4 Escalation

Claude takes over directly when:
- 2 failed dispatches on the same task
- Threading/concurrency issues (Vision background + SwiftUI main actor)
- SQLite schema design decisions
- CloudKit sync edge cases

---

## 6. Build Order

| Phase | Feature | New Files | Modified Files | Risk |
|---|---|---|---|---|
| 1 | Feature 2 — sort modes | None | Folder.swift, HomeView.swift, FolderView.swift | Low |
| 2 | Feature 1 — custom home | AppSettings.swift, OnboardingView.swift, SettingsView.swift, ChronologicalFeedView.swift | ContentView.swift, iFauxtoApp.swift | Low |
| 3 | Feature 3 — AI tagging + search | VisionTaggingService.swift, TagStore.swift, SearchService.swift, IndexingManager.swift, SearchView.swift | iFauxtoApp.swift | Medium |
| 4 | Feature 4 — editing | EditState.swift, EditService.swift, PhotoEditorView.swift | PhotoViewer.swift, PhotoThumbnailView.swift | Medium |
| 5 | Feature 5 — brand voice | BrandCopy.swift | All views (copy updates) | Low |
| 6 | Performance hardening | None | Various (pagination, caching, lazy loading) | Medium |
| 7 | Landing page + demo | landing/ directory (web project) | None (separate codebase) | Low-Medium |

Phases 1-2 are low-risk warmups. Phase 3 is the biggest lift. Phase 7 is independent and can run in parallel with later iOS phases.

---

## 7. Performance Targets

| Metric | Target |
|---|---|
| Photo library support | 50k+ photos |
| Scroll FPS | 60fps |
| Folder reorder latency | < 30ms |
| Search response | < 200ms |
| Search suggestions | < 50ms |
| AI indexing throughput | ~100 photos/minute (background) |
| Editor preview latency | < 100ms per slider change |
| App launch to interactive | < 1 second |

---

## 8. File Inventory

### New files (iOS app)

| File | Layer | Purpose |
|---|---|---|
| `Models/AppSettings.swift` | Model | Home mode preference, sort defaults |
| `Models/EditState.swift` | Model | Non-destructive edit adjustments |
| `Services/VisionTaggingService.swift` | Service | Apple Vision tagging pipeline |
| `Services/TagStore.swift` | Service | SQLite FTS5 read/write |
| `Services/SearchService.swift` | Service | Query parsing + FTS execution |
| `Services/IndexingManager.swift` | Service | Background indexing coordinator |
| `Services/EditService.swift` | Service | CIFilter chain for edits |
| `Views/SearchView.swift` | View | Search bar + results grid |
| `Views/SettingsView.swift` | View | Preferences UI |
| `Views/OnboardingView.swift` | View | First-launch setup |
| `Views/ChronologicalFeedView.swift` | View | Time-ordered photo feed |
| `Views/PhotoEditorView.swift` | View | VSCO-style slider editing |
| `Utils/BrandCopy.swift` | Util | Brand voice copy constants |

### Modified files (iOS app)

| File | Changes |
|---|---|
| `Models/Folder.swift` | Add sortMode property |
| `Views/ContentView.swift` | Home mode routing |
| `Views/HomeView.swift` | Sort mode picker, search bar |
| `Views/FolderView.swift` | Sort mode for photos |
| `Views/PhotoViewer.swift` | Edit button |
| `Views/PhotoThumbnailView.swift` | Edit indicator badge |
| `App/iFauxtoApp.swift` | AppSettings init, IndexingManager launch |

### New directory (web)

```
landing/
├── index.html
├── src/
│   ├── demo.js          — Interactive demo engine
│   ├── tooltips.js      — Guided walkthrough
│   ├── styles.css       — App-matching design
│   └── data.js          — Sample photos + tags
├── assets/
│   ├── photos/          — 30 sample images
│   ├── mockup/          — Phone frame, app icon
│   └── icons/           — UI icons
└── demo/
    ├── components/      — Demo UI components
    └── state.js         — Demo state management
```

---

## 9. AI Roadmap

| Phase | Technology | What It Enables | Cost | App Size Impact |
|---|---|---|---|---|
| MVP | Apple Vision Framework | Object/scene tags, OCR, face detection | Free | None |
| Phase 2 | MobileCLIP (Core ML) | Natural language search ("cars in SF at night") | Free | +60MB |
| Phase 3 | Apple Intelligence (FoundationModels) | Semantic query understanding | Free | None (iOS 18.1+) |

Each phase adds capability without changing the SearchService interface or SearchView UI.

---

## 10. Non-Goals

- Social features / sharing network
- Cloud storage replacement (Apple Photos remains source of truth)
- Heavy AI editing (generative fill, background removal)
- Android version
- Photo duplication (overlay model only)
