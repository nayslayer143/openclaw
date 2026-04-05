# iFauxto v2 — Implementation Plan (Entry Point)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing iFauxto MVP with 5 new features (custom home, sort modes, AI tagging + search, VSCO editing, brand voice), performance hardening, and a landing page with interactive demo.

**Architecture:** Hybrid SwiftData (CloudKit sync) + SQLite FTS5 (local search index). Existing 19 Swift files stay intact — we add 13 new files and modify 7. Landing page is a separate web project in `landing/`.

**Tech Stack:** Swift 5.9, SwiftUI, SwiftData, PhotoKit, Vision framework, CoreImage, SQLite3 (C API), XcodeGen. Landing page: HTML/CSS/JS.

**Spec:** `docs/superpowers/specs/2026-04-04-ifauxto-v2-design.md`
**PRD:** `docs/PRD.md`

---

## Plan Files (read in order)

| Phase | File | What It Covers |
|---|---|---|
| 1 | `2026-04-04-phase1-sort-modes.md` | Feature 2 enhancement — folder sort modes |
| 2 | `2026-04-04-phase2-custom-home.md` | Feature 1 — custom home screen + onboarding + settings |
| 3 | `2026-04-04-phase3-ai-search.md` | Feature 3 — Vision tagging, SQLite FTS, search UI |
| 4 | `2026-04-04-phase4-editing.md` | Feature 4 — VSCO-style photo editing |
| 5 | `2026-04-04-phase5-brand-voice.md` | Feature 5 — brand copy + polish |
| 6 | `2026-04-04-phase6-performance.md` | Performance hardening for 50k+ photos |
| 7 | `2026-04-04-phase7-landing-page.md` | Landing page + interactive demo |

## Key Rules

1. **All work happens in `~/openclaw/builds/ifauxto/`**
2. **After modifying any Swift file, regenerate the Xcode project:** `cd ~/openclaw/builds/ifauxto && xcodegen generate`
3. **Run tests after every task:** `xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.0' 2>&1 | tail -20`
4. **Commit after every task** — small, focused commits
5. **Never modify `orderIndex` from a non-custom sort mode** — compute display order in the view
6. **Never store UIImage or pixel data** — only `PHAsset.localIdentifier`
7. **SQLite FTS store is separate from SwiftData** — it's a standalone `.sqlite` file in Application Support
8. **DataManager is the single source of truth** for SwiftData CRUD — all new models go through it
9. **SwiftData schema changes need default values** for CloudKit compatibility

## Existing File Map

```
iFauxto/
├── App/
│   ├── iFauxtoApp.swift          (31 LOC)  — @main, ModelContainer, env injection
│   └── ContentView.swift         (50 LOC)  — permission gate → HomeView
├── Models/
│   ├── Folder.swift              (23 LOC)  — @Model: id, name, parentId, order, photoReferences
│   ├── PhotoReference.swift      (17 LOC)  — @Model: id (=localIdentifier), folderId, orderIndex
│   └── DataManager.swift        (136 LOC)  — @MainActor CRUD for folders + photos
├── Views/
│   ├── HomeView.swift           (157 LOC)  — root folder list, reorder, create, import
│   ├── FolderView.swift         (224 LOC)  — photo grid, drag-and-drop, edit mode
│   ├── PhotoThumbnailView.swift  (64 LOC)  — grid cell with async thumbnail
│   ├── PhotoViewer.swift         (69 LOC)  — full-screen swipe viewer
│   ├── EditModeToolbar.swift     (75 LOC)  — move/delete toolbar
│   ├── FolderCreationSheet.swift (54 LOC)  — new folder modal
│   ├── PhotoPickerView.swift     (37 LOC)  — PHPicker wrapper
│   └── ImportProgressView.swift (118 LOC)  — library import progress
├── Services/
│   ├── PhotoKitService.swift     (77 LOC)  — auth, thumbnail/full image loading
│   ├── LibraryImportService.swift(195 LOC) — Photos library → SwiftData mirror
│   ├── SyncManager.swift         (54 LOC)  — CloudKit sync state
│   └── CloudKitService.swift     (18 LOC)  — account check placeholder
├── Utils/
│   ├── DragDropManager.swift     (24 LOC)  — reorder index math
│   └── Extensions.swift           (6 LOC)  — Array.move, Color helpers
└── Resources/
    ├── Assets.xcassets/
    ├── Info.plist
    └── iFauxto.entitlements

iFauxtoTests/
├── FolderTests.swift
├── PhotoReferenceTests.swift
├── DataManagerTests.swift
└── iFauxtoTests.swift
```
