# Consuming `style.json`

Workflow for the agent when the user hands over a `style.json` (path or content).

## 1. Read and parse

Read the file. Parse as JSON. If parsing fails, report the line/column and stop.

## 2. Validate

Open `adapters/style-schema.json`. Walk the user's `style.json`:
- `name` must be a non-empty string.
- One of `palette` or `mood_id` must be present.
- Any present `palette` must have `bg` and `fg` (other keys optional).
- Any present `typography.<voice>` must have `family`.
- Any present `forces.<dial>` must be 0 ≤ value ≤ 1.
- Any present `motion_intensity` must be 0 ≤ value ≤ 1.
- Any present `texture` must be one of `none`, `grain`, `glass`.
- Any present `mode_id` must be one of `swiss`, `brutalist`, `immersive`, `kinetic`, `gallery`.
- Any present `mood_id` must be one of `void`, `void-inverse`, `dusk`, `signal`, `earth`, `frost`, `blaze`, `bruise`, `concrete`.

If any check fails, report the failing field path and stop.

## 3. Pick base mode

- If `mode_id` present → use as `data-forces` on `<html>`.
- Else if `forces` present → find closest preset by L2 distance from the table below
  (sum over only the dials the user supplied, then sqrt). Tie-breaker: prefer `swiss`.
- Else → default `swiss`.

| mode_id | structure | disruption | density | breath | warmth | edge | stillness | motion | whisper | shout |
|---|---|---|---|---|---|---|---|---|---|---|
| swiss | 0.85 | 0.15 | 0.40 | 0.65 | 0.10 | 0.85 | 0.80 | 0.10 | 0.50 | 0.40 |
| brutalist | 0.40 | 0.80 | 0.85 | 0.10 | 0.00 | 1.00 | 0.85 | 0.05 | 0.00 | 1.00 |
| immersive | 0.25 | 0.60 | 0.20 | 0.80 | 0.60 | 0.40 | 0.10 | 0.90 | 0.50 | 0.40 |
| kinetic | 0.55 | 0.45 | 0.40 | 0.50 | 0.30 | 0.65 | 0.00 | 1.00 | 0.30 | 0.70 |
| gallery | 0.90 | 0.05 | 0.10 | 1.00 | 0.30 | 0.60 | 0.80 | 0.20 | 0.90 | 0.05 |

## 4. Pick base mood

- If `mood_id` present AND no `palette` → use as `data-mood`. No scope emitted.
- If `palette` present → set `data-mood="--custom"` on `<html>` and emit the custom
  scope (Step 5).
- If neither → default `void-inverse`.

## 5. Emit the style overrides block

Into `<style id="style-overrides">` in `templates/page-composed.html`'s head, write:

### Custom palette scope (if `palette` present)

```css
[data-mood="--custom"] {
  --color-bg:       <palette.bg>;
  --color-fg:       <palette.fg>;
  --color-accent-1: <palette.accent_1 || mix(fg, bg, 50%)>;
  --color-accent-2: <palette.accent_2 || mix(fg, bg, 30%)>;
  --color-discord:  <palette.discord  || palette.accent_1>;
  --color-muted:   color-mix(in oklch, var(--color-fg) 50%, var(--color-bg));
  --color-subtle:  color-mix(in oklch, var(--color-fg)  8%, var(--color-bg));
  --color-surface: color-mix(in oklch, var(--color-fg)  5%, var(--color-bg));
  --color-border:  color-mix(in oklch, var(--color-fg) 15%, var(--color-bg));
  --color-inverse: var(--color-fg);
}
```

Use the standard CSS `color-mix()` function for the four derived values. The four
required overrides (bg, fg, accent_1, accent_2, discord) get literal hex.

### Force overrides (if `forces` present)

```css
:root {
  --force-<dial>: <value>;   /* repeat per supplied dial */
}
```

Only emit the dials the user actually supplied; missing ones inherit from `mode_id`.

### Voice overrides (if `typography` present)

```css
:root {
  --font-monument:   '<typography.monument.family>', <fallback>;
  --font-swiss:      '<typography.swiss.family>', <fallback>;
  --font-editorial:  '<typography.editorial.family>', <fallback>;
  --font-brutalist:  '<typography.brutalist.family>', <fallback>;
  --font-expressive: '<typography.expressive.family>', <fallback>;
}
```

Fallback per voice: monument → sans-serif, swiss → sans-serif, editorial → serif,
brutalist → monospace, expressive → sans-serif.

### Motion scaling (if `motion_intensity` present)

```css
:root {
  --motion-scale: <max(motion_intensity, 0.01)>;
  --dur-instant:  calc(150ms  * var(--motion-scale, 1));
  --dur-swift:    calc(300ms  * var(--motion-scale, 1));
  --dur-natural:  calc(500ms  * var(--motion-scale, 1));
  --dur-drift:    calc(900ms  * var(--motion-scale, 1));
  --dur-meditate: calc(1800ms * var(--motion-scale, 1));
  --texture-grain-duration: calc(8s * var(--motion-scale, 1));
}
```

Clamp to a minimum of 0.01 so transitions stay parseable.

### Texture (if `texture` present and not `none`)

Set `<html data-texture="<value>">`. No CSS to emit — the `tokens/textures.css`
rules activate automatically.

## 6. Emit font links

For each `typography.<voice>` with `google: true`, append to the existing Google
Fonts `<link>` URL in `templates/page-composed.html`. Family names are
URL-encoded; weights joined with `;`. Example:

    family=Bodoni+Moda:wght@400;900

If `google` is false or missing, the agent assumes the family is system-available
or user-installed — no link emitted.

## 7. Pick sections

Read `sections/README.md`. Pick sections matching the brief and the style guide's
thesis. Honor `dos[]` / `donts[]`:
- A `dont` referencing "pure black backgrounds" steers away from `void` mood.
- A `do` referencing "warm grain" suggests `texture: "grain"` and a warm-mood
  palette.
- A `do` referencing "type that breathes" suggests `gallery` mode or generous
  `breath` force.

These are heuristics, not hard rules — pick what serves the brief.

## 8. Assemble

For each chosen section, read its partial, fill `{{...}}` placeholders by string
substitution, concatenate into the `<body>` of `templates/page-composed.html` in
the recommended order.

## 9. Verify

Open the page in a browser. Check that:
- bg color matches `palette.bg`
- hero font matches `typography.monument.family`
- No `{{...}}` placeholders leak through
- No console errors
- Texture (if not none) is visible
