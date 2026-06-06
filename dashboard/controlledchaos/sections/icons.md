# Icon Reference — Inline SVG Snippets

Use these stroke-based icons inside `feature-grid` `{{{icon}}}` slots, `pricing` features, and anywhere else a small symbol earns its room. All are 24x24, `stroke="currentColor"`, `fill="none"`, `stroke-width="1.75"`, `stroke-linecap="round"`, `stroke-linejoin="round"`.

The agent picks the icon that matches the feature's meaning. If none fit, the agent authors a new SVG in the same style.

## Curated set

### Direction / motion
```html
<svg viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
```
Arrow right — navigation, "next."

```html
<svg viewBox="0 0 24 24"><path d="M12 5v14M6 13l6 6 6-6"/></svg>
```
Arrow down — descent, deeper.

### Convergence
```html
<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/></svg>
```
Hub — center with rays. "The room."

### Stack / layers
```html
<svg viewBox="0 0 24 24"><path d="M12 2l10 5-10 5L2 7l10-5zM2 12l10 5 10-5M2 17l10 5 10-5"/></svg>
```
Stack — three layers. Infrastructure / platform.

### Speed
```html
<svg viewBox="0 0 24 24"><path d="M13 2L3 14h7v8l10-12h-7V2z"/></svg>
```
Bolt — speed, instant.

### Trust
```html
<svg viewBox="0 0 24 24"><path d="M12 2L3 7v6c0 5 4 9 9 10 5-1 9-5 9-10V7l-9-5z"/><path d="M9 12l2 2 4-4"/></svg>
```
Shield-check — trust, security, verified.

### Network
```html
<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="2"/><circle cx="4" cy="6" r="2"/><circle cx="20" cy="6" r="2"/><circle cx="4" cy="18" r="2"/><circle cx="20" cy="18" r="2"/><path d="M6 7l5 4M18 7l-5 4M6 17l5-4M18 17l-5-4"/></svg>
```
Network — distributed nodes.

### Eye / vision
```html
<svg viewBox="0 0 24 24"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>
```
Eye — vision, insight, the needle.

### Globe
```html
<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 010 20M12 2a15 15 0 000 20"/></svg>
```
Globe — global, distributed.

### Cards / canvas
```html
<svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
```
Canvas — board, dashboard, layout.

### Plus / add
```html
<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
```
Plus — add, more.

### Sparkle / signal
```html
<svg viewBox="0 0 24 24"><path d="M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2 2-6z"/></svg>
```
Sparkle — magic, signal, AI.

### Map pin
```html
<svg viewBox="0 0 24 24"><path d="M12 2c-4 0-7 3-7 7 0 5 7 13 7 13s7-8 7-13c0-4-3-7-7-7z"/><circle cx="12" cy="9" r="2.5"/></svg>
```
Pin — location, neighborhood, place.

## Usage

In `feature-grid.html` the `{{{icon}}}` placeholder uses triple-stash so the inline SVG isn't HTML-escaped. The agent pastes the SVG directly:

```html
<div class="cc-feature__icon" aria-hidden="true">
  <svg viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
</div>
```

The icon inherits `color: var(--color-accent-1)` from the wrapping `.cc-feature__icon`, and `currentColor` cascades into the SVG's `stroke`.

## Authoring more

If none of the curated 13 match, author a new one in the same style:
- 24x24 viewBox
- Single `<path>` or minimal primitives
- `stroke="currentColor" fill="none" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"` (these are set globally in `sections.css` on `.cc-feature__icon svg`, so the SVG markup can omit them)
- No `<title>`, no `<defs>`, no styles — keep the markup minimal

Add the new SVG to this file under a sensible category so the next agent can find it.
