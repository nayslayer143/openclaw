# PRD — "iPhoto, but under your control"

## Working Name: **Fauxto / Faux Photo / Control Photos (TBD)**

---

# 1. PRODUCT SUMMARY

## Core Idea

A **manual-first, customizable photo OS layered on top of Apple Photos** that:

* looks like iPhoto
* behaves like iPhoto
* but gives users **absolute control over structure, order, and access**

---

## Core Value Proposition

> Apple Photos = "We decide what matters"
> This app = **"You decide everything."**

---

# 2. CORE FEATURES

---

## FEATURE 1 — CUSTOM HOME SCREEN (ENTRY CONTROL)

### Description

User chooses what they see when opening the app.

### Options:

* Full photo feed (chronological)
* Folder view (default library replacement)
* Last opened view
* Custom pinned view

---

### Requirements

```yaml
HomeViewMode:
  - chronological_feed
  - folder_list
  - last_opened
  - custom_view
```

---

### UX Behavior

* First launch -> onboarding asks preference
* Can change anytime in settings
* Instant load, no delay

---

### Why This Matters

Apple removes agency at the first touchpoint. This restores **intent at entry**.

---

## FEATURE 2 — FIXED FOLDER ORDER (KILLER FEATURE)

### Description

User-defined folder order that **NEVER changes unless user changes it**

---

### Sorting Modes

```yaml
FolderSortMode:
  - custom (default)
  - alphabetical
  - chronological
  - most_recent
```

---

### CRITICAL RULE

> If `custom` is selected:

* system is NEVER allowed to reorder folders
* no background sorting
* no "helpful" changes

---

### Implementation

```typescript
Folder {
  id: string
  name: string
  orderIndex: number
  sortMode: "custom" | "alpha" | "date" | "recent"
}
```

---

### Drag Behavior

* long press -> reorder
* updates `orderIndex`
* persists instantly

---

### Key UX Detail

> Folder positions must feel **permanent like icons on a home screen**

---

### Why This Is The Wedge

This solves:

* cognitive load
* muscle memory breakage
* Apple's constant reshuffling

This is the **"once you have it, you can't go back" feature**

---

## FEATURE 3 — AI TAGGING + INSTANT SEARCH

### Description

Every photo/video is analyzed and tagged automatically.

---

### Tag Types

```yaml
AI Tags:
  - people
  - objects
  - locations
  - scenes
  - time of day
  - events
  - text (OCR)
```

---

### Architecture Options

#### Option A (FAST MVP)

* Use Apple Vision Framework
* Augment with lightweight local models

#### Option B (ADVANCED)

* Background pipeline:
  * CLIP-style embeddings
  * vector search index

---

### Search UX

* Search bar ALWAYS visible on open
* Instant suggestions:
  * "beach"
  * "Jacob"
  * "night"
  * "screenshots"

---

### Query Examples

* "Jacob at night"
* "cars in SF"
* "screenshots last week"

---

### Performance Requirements

* Indexing runs in background
* Does NOT block UI
* Progressive enrichment

---

### Why This Matters

High-volume ingestion problem (100-300 photos/day). Search becomes survival, not luxury.

---

## FEATURE 4 — EDITING SYSTEM (VSCO-INSPIRED)

### Description

Lightweight but powerful editing layer

---

### Core Tools

```yaml
Editing Tools:
  - exposure
  - contrast
  - saturation
  - temperature
  - highlights/shadows
  - grain
  - vignette
  - presets
```

---

### UX Model

* slider-based (VSCO style)
* real-time preview
* non-destructive edits

---

### Storage

```typescript
EditState {
  photoId: string
  adjustments: JSON
}
```

---

### Future Expansion

* LUT imports
* creator presets
* batch editing

---

## FEATURE 5 — BRAND VOICE (SUBTLE REBELLION)

### Tone

* playful
* slightly anti-Apple
* respectful but irreverent

---

### Examples

* "Finally, your photos behave."
* "No surprises. Just your system."
* "Organized like you meant it."

---

# 3. SYSTEM ARCHITECTURE

---

## 3.1 Core Stack

* SwiftUI
* Photos Framework (PHAsset)
* CoreData / SQLite
* CloudKit

---

## 3.2 Data Layers

### Layer 1 — Apple Photos

* source of truth for media

### Layer 2 — App Overlay

* folders
* order
* tags
* edits

---

## 3.3 Indexing Pipeline

```yaml
Pipeline:
  1. Fetch PHAsset
  2. Generate thumbnail
  3. Run AI tagging
  4. Store embeddings/tags
  5. Update search index
```

---

## 3.4 Search Engine

* SQLite FTS (MVP)
* Vector DB (future)

---

# 4. PERFORMANCE REQUIREMENTS

* Support 50k+ photos
* Scroll at 60fps
* Reorder latency < 30ms
* Search response < 200ms

---

# 5. UX DETAILS THAT MATTER

---

## 5.1 Muscle Memory Design

* folder positions never shift
* UI predictable every time

---

## 5.2 Zero Surprise Principle

* no auto grouping
* no reshuffling
* no "memories"

---

## 5.3 Speed Perception

* preload thumbnails
* instant tap response

---

# 6. NON-GOALS

* social network
* cloud storage replacement
* heavy AI editing

---

# 7. MVP BUILD PLAN

---

## Phase 1 — Foundation (Week 1-2)

* PHAsset integration
* grid rendering
* basic viewer

---

## Phase 2 — Folder System (Week 2-3)

* create folders
* drag reorder
* persist order

---

## Phase 3 — Home Customization (Week 3)

* entry mode selector

---

## Phase 4 — AI Indexing (Week 4-5)

* Vision tagging
* search bar

---

## Phase 5 — Editing (Week 5-6)

* sliders
* save edits

---

# 8. STRATEGIC INSIGHT

This is not just a photo app.

This is a **control layer over personal media** which expands into:

* files
* videos
* notes
* creative assets

---

# 9. POSITIONING

> Apple Photos is **algorithm-first**
>
> This is **human-first**

---

# 10. BUILD INSTRUCTION

Senior iOS engineer approach. Build step-by-step with production-quality SwiftUI code. Prioritize performance, clean architecture, and modularity. Do not skip implementation detail.
