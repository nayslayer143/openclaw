# Controlled Chaos

A creative design system skill for building award-level web pages. Five aesthetic modes, nine mood palettes, five typographic voices, and a creative force framework — inspired by Awwwards SOTD winners and Cargo graphic templates.

---

## Agent Instructions

This is a Claude Code skill. When invoked, it generates complete HTML pages styled through CSS custom properties. No build tools, no JavaScript frameworks — pure HTML + CSS tokens.

### Quick Start (Agent)

Generate a page by composing three decisions:

1. **Mode** — sets the creative force preset via `data-forces` on `<html>`
2. **Mood** — sets the color palette via `data-mood` on `<html>`
3. **Voices** — applies typographic character via `.voice-*` classes

```html
<html data-mood="signal" data-forces="immersive">
<head>
  <link rel="stylesheet" href="tokens/layout.css">
  <link rel="stylesheet" href="tokens/typography.css">
  <link rel="stylesheet" href="tokens/color.css">
  <link rel="stylesheet" href="tokens/motion.css">
  <link rel="stylesheet" href="tokens/forces.css">
</head>
<body>
  <h1 class="voice-monument">Title</h1>
  <p class="voice-swiss">Body text</p>
</body>
</html>
```

### Modes

| Mode | `data-forces` | Character | Force Profile |
|------|--------------|-----------|---------------|
| Swiss Editorial | `swiss` | Neue Grafik, grid-locked, systematic | structure:0.85, breath:0.65, edge:0.85, stillness:0.8 |
| Brutalist Poster | `brutalist` | Maximum volume, raw, unapologetic | disruption:0.8, density:0.85, edge:1, shout:1 |
| Immersive Dark | `immersive` | Atmospheric, scroll-driven, experiential | breath:0.8, warmth:0.6, motion:0.9 |
| Kinetic Type | `kinetic` | Typography in motion, animated, alive | motion:1, shout:0.7, structure:0.55 |
| Gallery Minimal | `gallery` | White cube, work speaks for itself | structure:0.9, breath:1, whisper:0.9, stillness:0.8 |

### Moods (Color Palettes)

| Mood | `data-mood` | Background | Foreground | Accent | Discord |
|------|------------|------------|------------|--------|---------|
| Void | `void` | #000000 | #ffffff | #ffffff | #ff0040 |
| Void Inverse | `void-inverse` | #ffffff | #000000 | #000000 | #ff0040 |
| Dusk | `dusk` | #0d1117 | #f0e6d3 | #d4a574 | #ff6b35 |
| Signal | `signal` | #0a0a0f | #e0ffe0 | #00ff88 | #ff0066 |
| Earth | `earth` | #f2ede4 | #2c2416 | #a0522d | #c73e1d |
| Frost | `frost` | #f0f4f8 | #1a1f36 | #5b6abf | #e53e3e |
| Blaze | `blaze` | #0a0000 | #fff0e0 | #ff3d00 | #00ff88 |
| Bruise | `bruise` | #0f0a1a | #e8dff5 | #a855f7 | #22d3ee |
| Concrete | `concrete` | #b8b8b0 | #1a1a18 | #1a1a18 | #ff4400 |

### Typographic Voices

| Class | Font | Character | Use |
|-------|------|-----------|-----|
| `.voice-monument` | Space Grotesk | Architectural, bold, uppercase | Heroes, statements |
| `.voice-editorial` | Playfair Display | Elegant serif, refined | Long reads, sophistication |
| `.voice-swiss` | Inter | Systematic sans | Information density, labels |
| `.voice-brutalist` | Space Mono | Raw monospace | Disruption, data |
| `.voice-expressive` | DM Sans | Fluid, versatile | Art direction, personality |

Subvariants: `.voice-monument.--massive`, `.voice-editorial.--display`, `.voice-swiss.--label`, `.voice-brutalist.--caption`, `.voice-expressive.--fluid`

### Type Scale

| Variable | Range | Use |
|----------|-------|-----|
| `--type-massive` | 56-192px | Page-defining statements |
| `--type-display` | 40-112px | Section heroes |
| `--type-headline` | 28-56px | Section titles |
| `--type-subhead` | 18-24px | Subsections |
| `--type-body` | 15-18px | Reading text |
| `--type-body-small` | 13-15px | Secondary text |
| `--type-caption` | 11-13px | Labels, metadata |
| `--type-micro` | 9-11px | Smallest text |

### Layout Classes

**Grids:**
- `.grid-swiss` — 12-column foundation (responsive: 8col tablet, 4col mobile)
- `.grid-auto` — auto-fill responsive `minmax(280px, 1fr)`
- `.grid-asymmetric` — 2fr/1fr deliberate imbalance (`.--reverse`, `.--golden`, `.--extreme`)
- `.grid-editorial` — Named areas: full, wide, content
- `.grid-masonry` — CSS columns masonry
- `.grid-cargo` — Tight 1px-gap grid

**Sections:**
- `.section-hero` — Full viewport, centered (`.--end`, `.--split`)
- `.section-breath` — Generous vertical padding (`.--massive`)
- `.section-bleed` — Edge-to-edge 100vw
- `.section-sticky` — Sticky positioned, 100dvh

**Containers:**
- `.container` — Max 1600px centered
- `.container.--narrow` — 640px
- `.container.--regular` — 960px
- `.container.--wide` — 1200px
- `.container.--bleed` — Full width, no padding

**Flow & Flex:**
- `.flow` — Vertical rhythm (`.--tight`, `.--loose`, `.--breath`)
- `.flex`, `.flex-col`, `.flex-center`, `.flex-between`
- `.gap-xs` through `.gap-xl`

### Motion Classes

- `.motion-reveal` — Scroll-triggered fade+up (add `.--visible` via IntersectionObserver)
- `.motion-stagger` — Children cascade with stagger delays
- `.motion-clip-up` — Clip-path reveal animation
- `.motion-marquee` — Infinite horizontal scroll
- `.motion-hover-lift` — Hover translateY(-4px)
- `.motion-hover-scale` — Hover scale(1.03)
- `.motion-scroll-fade` — Scroll-driven fade (CSS scroll-timeline)
- `.motion-scroll-parallax` — Scroll-driven parallax

**Easing:** `--ease-out-expo`, `--ease-spring`, `--ease-snap`, `--ease-drift`
**Durations:** `--dur-instant` (100ms) through `--dur-meditate` (4000ms)

### Color Utility Classes

- `.mood-surface` — Background + text from mood
- `.mood-surface-invert` — Inverted surface
- `.mood-surface-accent` — Accent as background
- `.mood-discord` — Discord accent on text
- `.mood-gradient-subtle` — bg-to-surface gradient
- `.mood-gradient-accent` — Accent gradient
- `.mood-grain` — Fixed noise overlay texture

### The Five Forces (CSS Custom Properties)

Forces are spectrums from 0 to 1, set via `data-forces` presets or custom CSS:

| Force Pair | Low (0) | High (1) |
|-----------|---------|----------|
| `--force-structure` / `--force-disruption` | Chaos, freeform | Rigid grid, systematic |
| `--force-density` / `--force-breath` | Airy, spacious | Packed, heavy |
| `--force-warmth` / `--force-edge` | Rounded, organic | Sharp, angular |
| `--force-stillness` / `--force-motion` | Static, monumental | Kinetic, animated |
| `--force-whisper` / `--force-shout` | Barely there | Maximum volume |

**Derived values** auto-calculate from forces:
- `--derived-radius` — Border radius (0 to 1.5rem)
- `--derived-tracking` — Letter spacing
- `--derived-leading` — Line height (1.1 to 1.7)
- `--derived-section-pad` — Section padding (2rem to 12rem)
- `--derived-gap` — Element gap (0.25rem to 3.25rem)
- `--derived-duration` — Animation duration (0.15s to 1.35s)

### Scroll Reveal Pattern (JavaScript)

All showcase pages use this IntersectionObserver pattern:

```javascript
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('--visible');
    }
  });
}, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });

document.querySelectorAll('.motion-reveal, .motion-stagger').forEach(el => observer.observe(el));
```

### Recommended Mode + Mood Pairings

| Mode | Primary Mood | Alt Mood |
|------|-------------|----------|
| Swiss | `void-inverse` | `frost` |
| Brutalist | `concrete` | `blaze` |
| Immersive | `signal` | `dusk` |
| Kinetic | `dusk` | `bruise` |
| Gallery | `void-inverse` | `void` |

### Design Rules for Generation

1. **Type is the hero.** If the design works without color or images, it succeeds.
2. **Tension is beauty.** Near-symmetry over perfect symmetry. Near-alignment over exact alignment.
3. **Whitespace is pressurized.** It pushes elements apart with intent, not emptiness.
4. **Motion has meaning.** Every animation must have a purpose or it should not exist.
5. **The discord accent breaks the mood.** Every palette has one rule-breaking color — use it sparingly.
6. **One mood per page.** Mix voices freely, but stay in one color world.
7. **Start from the five forces.** Decide where on each spectrum, then let derived values do the work.
8. **The screen is not paper.** Use viewport units, scroll position, pointer position, time.

---

## Human Guide

### What Is This?

Controlled Chaos is a CSS-only design system for building web pages that look like they belong on Awwwards. It gives you five complete aesthetic modes (Swiss editorial, brutalist poster, immersive dark, kinetic typography, gallery minimal), nine color moods, five typographic voices, and a force system that lets you dial creative tensions from 0 to 1.

No npm install. No build step. Just link five CSS files and start composing.

### Getting Started

1. Clone this repo
2. Serve locally: `npx serve .` or open `showcase/index.html` in a browser
3. Browse the five showcase demos to see each mode in action

### Creating a Page

```html
<!DOCTYPE html>
<html lang="en" data-mood="dusk" data-forces="kinetic">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="tokens/layout.css">
  <link rel="stylesheet" href="tokens/typography.css">
  <link rel="stylesheet" href="tokens/color.css">
  <link rel="stylesheet" href="tokens/motion.css">
  <link rel="stylesheet" href="tokens/forces.css">
</head>
<body>
  <section class="section-hero">
    <h1 class="voice-monument" style="font-size: var(--type-massive)">
      Your Title
    </h1>
    <p class="voice-swiss" style="font-size: var(--type-subhead); color: var(--color-muted)">
      Supporting text here
    </p>
  </section>
</body>
</html>
```

### Customizing Forces

Override force values directly in CSS for custom compositions:

```css
:root {
  --force-structure: 0.7;
  --force-disruption: 0.3;
  --force-density: 0.5;
  --force-breath: 0.5;
  --force-warmth: 0.8;
  --force-edge: 0.2;
  --force-stillness: 0.3;
  --force-motion: 0.7;
  --force-whisper: 0.4;
  --force-shout: 0.6;
}
```

All derived values (border-radius, spacing, animation speed) recalculate automatically.

## Section Library

Twenty-two reusable section partials live in `sections/`. Each is mode-agnostic —
the token cascade handles per-mode look. See `sections/README.md` for the
authoring contract and per-section placeholders.

| Section | Variants | Best modes |
|---|---|---|
| hero | monument, editorial, bleed | all |
| manifesto | default, numbered | swiss, brutalist, immersive |
| quote | default, monument, gutter | all |
| two-column | editorial, dialogue, before-after | swiss, gallery |
| cta | default, discord, monument | all |
| stat-grid | default, bleed, vertical | swiss, brutalist, kinetic |
| process | numbered, timeline, vertical | swiss, immersive |
| footer | minimal, editorial, bleed | all |
| logo-wall | grid, marquee, monolith | swiss, brutalist |
| gallery | rigid, asymmetric, mosaic | gallery, immersive, kinetic |
| full-bleed | type, image, color-field | immersive, brutalist, kinetic |
| marquee | default, slow, vertical | kinetic, immersive, brutalist |
| nav | default, centered, minimal | all |
| feature-grid | default, wide, compact | swiss, gallery, immersive |
| product-showcase | split, centered, callouts | gallery, immersive |
| pricing | cards, table | swiss, gallery |
| faq | accordion, static, numbered | swiss, gallery, immersive |
| testimonial | card, grid, featured | all |
| signup-form | inline, stacked, framed | all |
| integration-logos | grid, inline, categorized | swiss, gallery |
| cta-banner | inline, sticky-bottom, divider | all |
| comparison-table | vs-2, vs-3, vs-many | swiss, gallery |

## Polish Layer (`tokens/states.css`)

Every interactive element gets shipping-grade craft out of the box.

| Behavior | Element types | How |
|---|---|---|
| Hover lift | buttons, CTAs, nav-CTA | `transform: translateY(-2px)` at `var(--dur-swift)` |
| Active press | buttons, CTAs | `transform: translateY(1px)` at `var(--dur-instant)` |
| Focus ring | every focusable | `outline: 2px solid var(--color-discord)` via `:focus-visible` |
| Disabled | buttons, inputs | `opacity: 0.4` + `cursor: not-allowed` + `pointer-events: none` |
| Loading | buttons with `[aria-busy]` or `[data-loading]` | spinner pseudo-element |
| Touch targets | buttons, links, inputs, nav links | `min-height: 44px` |
| Input states | text/email/textarea/select | hover/focus/invalid/disabled |
| Reduced motion | universal | `prefers-reduced-motion: reduce` zeros transforms + spinner |

## Premium Motion

Added to `sections.css`:

- **Scroll-progress hairline** at top of viewport via `animation-timeline: scroll()` (Chrome/Edge; graceful absence on Firefox stable).
- **Smooth-scroll with sticky-nav offset** via `scroll-padding-top: calc(var(--nav-height, 0) + 1rem)`.
- **Image-placeholder upgrade** — `cc-img-placeholder` now uses radial-gradient + linear-gradient + SVG grain overlay + bottom-left attr() label.

All halt under `prefers-reduced-motion`.

## Template Scaffolding

Deploy-ready defaults in `templates/`:

| File | Purpose |
|---|---|
| `page-composed.html` | Full SEO/OG/Twitter/JSON-LD `<head>` with Mustache placeholders for `{{seo.*}}` and `{{org.*}}` |
| `404.html` | Style-driven 404 — hero + cta + footer, same `<link>` chain as the main page |
| `privacy.html` | 8-section privacy-policy scaffold (lorem-replaceable) |
| `terms.html` | 12-section terms-of-service scaffold |
| `meta.partial.html` | Standalone copy-pasteable `<head>` meta stack for non-CC pages |

## Style-Guide Adapter (`style.json`)

External style guides drive a page via `style.json`. Both SuperStyleGuide and
Pinterest Style Engine can export to this schema. Hand-authored is fine too.

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Free-form |
| `palette` *or* `mood_id` | one of | Five hex codes or one of 9 mood presets |
| `typography` | no | Per-voice family + weights + google flag |
| `forces` | no | 10 dials (0-1), inherits from `mode_id` |
| `motion_intensity` | no | 0-1, scales all `--dur-*` tokens |
| `texture` | no | `none` / `grain` / `glass` |
| `mode_id` | no | One of 5 mode presets |
| `mood_id` | no | One of 9 mood presets |
| `dos` / `donts` | no | Agent guidance arrays |

Schema: `adapters/style-schema.json`. Workflow: `adapters/from-style-json.md`.
Examples: `adapters/examples/`.

## Textures (`data-texture`)

`tokens/textures.css` ships three texture modes activated via `<html data-texture="...">`.

| Value | Effect | Tunables |
|---|---|---|
| `none` (default) | No overlay | — |
| `grain` | Living SVG noise overlay (page-level) | `--texture-grain-opacity`, `--texture-grain-scale`, `--texture-grain-duration` |
| `glass` | `.cc-glass` utility with backdrop-filter (element-level opt-in) | `--texture-glass-blur`, `--texture-glass-saturate` |

Both respect `prefers-reduced-motion: reduce`.

### File Structure

```
controlledchaos/
├── tokens/
│   ├── layout.css         CSS reset, spacing scale, grids, sections, flex
│   ├── typography.css     5 font voices, type scale, tracking, utilities
│   ├── color.css          9 mood palettes, color utilities, grain overlay
│   ├── motion.css         Easing, durations, keyframes, motion classes
│   └── forces.css         5 force spectrums, derived values, 5 presets
├── showcase/
│   ├── index.html         System overview with all modes
│   ├── swiss.html         Swiss editorial demo
│   ├── brutalist.html     Brutalist poster demo
│   ├── immersive.html     Immersive dark demo
│   ├── kinetic.html       Kinetic typography demo
│   └── gallery.html       Gallery minimal demo
├── CLAUDE.md              Agent skill instructions
├── DESIGN.md              Design philosophy and extended reference
└── README.md              This file
```

### Live Demos

Serve the project and visit `/showcase/` to see all five modes. Each demo is a self-contained HTML page that demonstrates the full range of its mode's capabilities.

### License

Creative commons. Build fearlessly.
