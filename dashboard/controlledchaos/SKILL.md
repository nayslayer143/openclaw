---
name: controlledchaos
description: Generate award-level static HTML pages using the Controlled Chaos design system — five aesthetic modes (Swiss Editorial, Brutalist Poster, Immersive Dark, Kinetic Type, Gallery Minimal), nine mood palettes, five typographic voices. Pure HTML + CSS custom properties, no JS framework. Use when the user asks for an Awwwards-style page, a controlled-chaos page, a landing page in a named mode, or names a mode/mood/voice from this system.
triggers: controlled chaos, controlledchaos, awwwards-style page, awwwards page, swiss editorial page, brutalist poster page, immersive dark page, kinetic type page, gallery minimal page, design-system landing page, build a landing page in <mode>, style.json, style-driven page, compose using sections, add a hero, add a manifesto, add a stat-grid, add a quote, add a gallery, add a marquee, add a logo-wall, add a process, add a cta, add a footer, add a full-bleed, add a two-column, add a nav, add a feature grid, add a feature-grid, add a product showcase, add a product-showcase, add pricing, add an faq, add a faq, add a testimonial, add a signup form, add a signup-form, add integration logos, add an integration-logos, add a cta banner, add a cta-banner, add a comparison table, add a comparison-table, SMB tech landing page, SaaS landing page, out of the box landing page
allowed-tools:
  - "Read"
  - "Write"
  - "Edit"
  - "Bash"
  - "Glob"
  - "Grep"
---

# controlledchaos — Award-level pages from a token-based design system

The user wants a static HTML page that looks like it belongs on Awwwards SOTD or a Cargo template, built by composing **three decisions** against this skill's CSS token layer. No build tools, no JS framework — `<link>` five token files, set two attributes on `<html>`, apply voice classes to text.

The full reference (every mode, mood, voice, layout class, motion class, type-scale variable) lives in `README.md`. The deeper philosophy is in `AXIOMS.md` and `DESIGN.md`. Showcase pages — one per mode — are in `showcase/`. **Read the showcase page that matches the chosen mode before authoring** — it's the canonical example.

This file owns the workflow. The README owns the catalog.

---

## When to Use

The user asked for one of:
- A page in a named mode (*"swiss editorial"*, *"brutalist poster"*, *"immersive dark"*, *"kinetic type"*, *"gallery minimal"*)
- An Awwwards-style or design-driven static page
- A page using this system's moods (*"signal"*, *"void"*, *"dusk"*, *"earth"*, etc.) or voices (*"voice-monument"*, etc.)
- *"controlled chaos"* explicitly

## When NOT to Use

- React / Vue / Svelte / any framework page → wrong layer; this skill emits raw HTML + CSS only.
- The user already has a design system → don't impose this one.
- Backend/admin UIs, dashboards, dense forms → this is a creative-statement system, not a productivity-UI system.

---

## Two Workflows

This skill supports two authoring paths. Pick based on what the user brings:

| If the user provides… | Use… |
|---|---|
| A vibe in words (mode + mood + voices) | **The Three-Decision Recipe** (below) — the original workflow |
| A `style.json` file (path or content) | **Style-Driven Authoring** — read `adapters/from-style-json.md` |
| A request to compose with sections | Read `sections/README.md` first, then either workflow |

Both paths converge on `templates/page-composed.html` and the 22-section library
in `sections/`. The three-decision recipe stays the default for prompts without
a style guide.

**SMB-tech baseline:** The default polish baseline is *Editorial-Generous* (Stripe / Anthropic / Cursor-marketing DNA). The interaction-states layer in `tokens/states.css` makes every interactive element feel shipping-grade out of the box. Section variants are tuned for this baseline.

---

## The Three-Decision Recipe

Every page is the composition of:

1. **Mode** → `<html data-forces="...">` — picks one of `swiss | brutalist | immersive | kinetic | gallery`. Sets the creative-force preset (structure, breath, edge, motion, etc.).
2. **Mood** → `<html data-mood="...">` — picks one of `void | void-inverse | dusk | signal | earth | frost | blaze | bruise | concrete`. Sets background / foreground / accent / discord colors.
3. **Voices** → `class="voice-monument"` etc. on text — picks per-element typography. Five voices: `monument | editorial | swiss | brutalist | expressive`. Subvariants via `--massive`, `--display`, `--label`, `--caption`, `--fluid`.

Mode + mood is the **vibe**. Voices are how individual sentences sound.

See `README.md` for the full lookup tables (mode → force profile, mood → hex codes, voice → font + character).

---

## Workflow

### 1. Clarify the brief (if not stated)

If the user didn't pick mode/mood/voices, ask once:

> "Pick a mode (swiss / brutalist / immersive / kinetic / gallery) and a mood (signal / dusk / void / earth / frost / blaze / bruise / concrete / void-inverse). I'll suggest voices."

If they're vague (*"something cool"*), suggest a default pairing from the table below and proceed:

| Brief vibe | Mode | Mood | Hero voice | Body voice |
|---|---|---|---|---|
| Editorial / refined | swiss | void-inverse | editorial | swiss |
| Loud / brand statement | brutalist | blaze | brutalist | brutalist |
| Atmospheric / scroll story | immersive | dusk | monument | expressive |
| Type-driven hero | kinetic | signal | monument.--massive | swiss |
| Portfolio / quiet | gallery | concrete | editorial | swiss |

### 2. Read the matching showcase

```bash
cat ~/.claude/skills/controlledchaos/showcase/<mode>.html
```

This is the canonical example for the chosen mode — copy its structure, swap content, retune mood/voices. Don't re-invent layouts that the showcase already solves.

### 3. Scaffold from `templates/page.html`

Copy `templates/page.html` to the user's destination. Set:

- `<html data-mood="..." data-forces="...">` to the chosen pair
- `<title>` to the page name
- Replace `<!-- HERO -->`, `<!-- BODY -->`, `<!-- FOOTER -->` blocks with content built from the showcase

### 4. Wire the tokens

The `<link>` tags in `templates/page.html` use **relative paths** that assume the page sits next to a `tokens/` directory. There are three patterns:

- **In-repo authoring** (page goes into `showcase/` or similar): keep `../tokens/<file>.css`
- **External authoring** (page goes into the user's project): copy the skill's `tokens/` folder next to the HTML, OR change the `<link>` paths to absolute `file:///` URLs pointing at `~/.claude/skills/controlledchaos/tokens/<file>.css`. Default to **copy** — keeps the page portable.
- **Public deploy**: copy `tokens/` and any fonts the voices reference (Space Grotesk, Playfair Display, Inter, Space Mono, DM Sans — load from Google Fonts via the existing `<link>` already in the showcase pages).

### 5. Verify in a browser

```bash
open <path-to-page>.html
```

Sanity-check: does it look like the mode? Mode-mismatch is the #1 silent failure (e.g. brutalist page with gallery breath spacing → looks lifeless).

---

## Token files (always link all five, in this order)

```html
<link rel="stylesheet" href="tokens/layout.css">      <!-- containers, grids, sections, flow, gap -->
<link rel="stylesheet" href="tokens/typography.css">  <!-- fonts, voices, type scale, tracking -->
<link rel="stylesheet" href="tokens/color.css">       <!-- mood palettes, foreground/background/accent/discord -->
<link rel="stylesheet" href="tokens/motion.css">      <!-- reveal, stagger, clip-up, marquee -->
<link rel="stylesheet" href="tokens/forces.css">      <!-- mode-driven force profiles (data-forces) -->
```

Order matters: `forces.css` last so its mode-overrides win.

---

## Common patterns

### Pattern A: Single-page hero + 2-3 sections

```
section-hero (mode-tuned)
  → section-breath × N (content)
    → section-bleed (visual statement)
      → section-breath (CTA / outro)
```

Use `flow` inside sections for vertical rhythm. Use `grid-swiss` for editorial/swiss/gallery, `grid-asymmetric` for brutalist/immersive, `grid-cargo` for kinetic.

### Pattern B: Voice mixing

Most pages use **two voices**: one hero voice (monument / editorial / brutalist) and one body voice (swiss / expressive). A third voice can appear once as a "discord" element (e.g. one `.voice-brutalist.--caption` line in an otherwise swiss page) — the discord color from the mood palette pairs with discord typography.

### Pattern C: Motion (optional)

Add `class="motion-reveal"` to scroll-triggered elements, `motion-stagger` to children that should cascade, `motion-marquee` to a horizontal-scroll strip. Need a tiny IntersectionObserver snippet in `<script>` to add `.--visible` on enter — copy from any showcase page that uses it.

---

## Hard-won knowledge

1. **`data-forces` and `data-mood` go on `<html>`, not `<body>`.** The CSS custom properties cascade from the root; setting them on `<body>` works for color but breaks force-driven spacing/scale.

2. **Don't mix voices arbitrarily.** Every voice is loud. Two per page is the convention; three is the ceiling and the third should be a single discord element.

3. **Type-scale variables are clamps, not fixed sizes.** `--type-massive` is `clamp(56px, ..., 192px)`. Don't override with absolute px — the responsive shrink is intentional.

4. **The mood `void` and `void-inverse` are not just dark/light flips.** They share the same accent ramp; `void-inverse` is for editorial moods that want black-on-white but keep the `#ff0040` discord. Use `frost` if you want a clean light page with cool accents.

5. **`data-forces="brutalist"` cranks every motion class to maximum.** If you also add `motion-marquee`, the page can become unreadable. For brutalist + motion, stick to `motion-reveal` only.

---

## Templates

- `templates/page.html` — minimal scaffold with the five `<link>`s, mood/forces placeholders, and three commented blocks (HERO, BODY, FOOTER) ready to fill.

Read `README.md` for the full reference catalog. Read `showcase/<mode>.html` before authoring in that mode.
