# iFauxto

**Your photos. Your order.**

Manual-first iOS photo organization. Layers on top of Apple Photos — no duplication, no AI, no auto-sorting.

## Requirements

- Xcode 15.4+
- iOS 17.0+ target
- XcodeGen (`brew install xcodegen`)
- Apple Developer account (for iCloud/CloudKit entitlements)

## Setup

```bash
cd ~/openclaw/builds/ifauxto
xcodegen generate
open iFauxto.xcodeproj
```

Set your Development Team in Xcode (Signing & Capabilities tab) before building to device.

## Architecture

- **Overlay model:** References PHAsset via localIdentifier only. Zero photo duplication.
- **SwiftData + CloudKit:** Folder structure and ordering syncs via iCloud automatically.
- **No auto-reorder:** orderIndex is explicit and never overwritten by the system.

## Key Files

| File | Purpose |
|------|---------|
| `Models/Folder.swift` | SwiftData folder hierarchy |
| `Models/PhotoReference.swift` | PHAsset reference with orderIndex |
| `Models/DataManager.swift` | All CRUD and ordering operations |
| `Services/PhotoKitService.swift` | PHAsset access and image loading |
| `Views/FolderView.swift` | Photo grid with drag-and-drop |
| `Views/PhotoViewer.swift` | Full-screen viewer, swipe only |

## Testing

```bash
xcodebuild test -project iFauxto.xcodeproj -scheme iFauxto \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=17.0'
```
