# Section Library

Reusable HTML partials. Each section is a single `.html` file with Mustache
placeholders the agent fills via string substitution. No runtime, no JS.

## Authoring contract

Every partial:
- Begins with a top-comment listing best/ok/avoid modes + variants + placeholders
- Root element carries `class="cc-section cc-<name>"`, `data-pattern="<name>"`, `data-variant="<default>"`
- Uses Mustache: `{{scalar}}` for substitution, `{{#items}}…{{/items}}` for repeats
- Image slots use `<div class="cc-img-placeholder" data-slot="<name>"></div>`
- Section-specific CSS lives in `sections/sections.css`

## Catalog

| Section | Variants | Required placeholders | Best modes | Avoid in |
|---|---|---|---|---|
| [hero](hero.html) | monument, editorial, bleed | heading, subhead, (optional) eyebrow | all | — |
| [manifesto](manifesto.html) | default, numbered | heading, paragraphs[] (text) | swiss, brutalist, immersive | gallery |
| [quote](quote.html) | default, monument, gutter | quote, attribution, (optional) source | all | — |
| [two-column](two-column.html) | editorial, dialogue, before-after | left{heading,body}, right{heading,body} | swiss, gallery | kinetic |
| [cta](cta.html) | default, discord, monument | heading, action_text, action_href, (optional) supporting | all | — |
| [stat-grid](stat-grid.html) | default, bleed, vertical | heading, stats[] (num, label, optional caption) | swiss, brutalist, kinetic | gallery |
| [process](process.html) | numbered, timeline, vertical | heading, steps[] (title, body) | swiss, immersive | gallery |
| [footer](footer.html) | minimal, editorial, bleed | copyright, links[] (label, href) | all | — |
| [logo-wall](logo-wall.html) | grid, marquee, monolith | heading, logos[] (label, optional href) | swiss, brutalist | kinetic |
| [gallery](gallery.html) | rigid, asymmetric, mosaic | heading, items[] (slot_name, optional caption) | gallery, immersive, kinetic | brutalist |
| [full-bleed](full-bleed.html) | type, image, color-field | type → content; image → slot_name; color-field → content, optional --bleed-color | immersive, brutalist, kinetic | — |
| [marquee](marquee.html) | default, slow, vertical | items[] (text) | kinetic, immersive, brutalist | gallery |
| [nav](nav.html) | default, centered, minimal | brand, links[] (label, href), cta_text, cta_href | all | — |
| [feature-grid](feature-grid.html) | default, wide, compact | heading, eyebrow?, features[] (icon, title, body) | swiss, gallery, immersive | brutalist, kinetic |
| [product-showcase](product-showcase.html) | split, centered, callouts | heading, body, image_slot, callouts[] for callouts variant | gallery, immersive | brutalist |
| [pricing](pricing.html) | cards, table | heading, eyebrow?, tiers[] (name, price, period, features[], cta_text, cta_href, recommended?) | swiss, gallery | brutalist |
| [faq](faq.html) | accordion, static, numbered | heading, items[] (question, answer) | swiss, gallery, immersive | kinetic |
| [testimonial](testimonial.html) | card, grid, featured | testimonials[] (quote, author, role, company, monogram?) | all | — |
| [signup-form](signup-form.html) | inline, stacked, framed | heading?, supporting?, placeholder_text, button_text, action_href | all | brutalist |
| [integration-logos](integration-logos.html) | grid, inline, categorized | heading, logos[] (label, href?, category?) | swiss, gallery | kinetic |
| [cta-banner](cta-banner.html) | inline, sticky-bottom, divider | heading, supporting?, action_text, action_href, dismissible?, banner_key? | all | — |
| [comparison-table](comparison-table.html) | vs-2, vs-3, vs-many | heading, eyebrow?, columns[] (name, is_you), rows[] (feature, values[]) | swiss, gallery | brutalist, kinetic |

## Icons

`feature-grid` and `pricing` use inline SVG icons. Reference set (13 stroke-based icons) lives in [icons.md](icons.md). The agent picks the icon that matches the feature meaning, or authors a new one in the same style and adds it to the reference file.

## Image policy

Sections with image slots (`hero.bleed`, `gallery`, `full-bleed.image`, `logo-wall`) use
placeholder / agent-sourced / user-supplied content. **Never** pull images from a
style-guide source board — style-guide imagery is reference-only.

## Use from a template

Read `templates/page-composed.html` for a complete scaffold. The recommended order
for a typical page is:

    hero → manifesto / stat-grid / quote / two-column / process / gallery / full-bleed / marquee
         → cta → footer

For style.json-driven authoring, honor `dos[]` / `donts[]` when picking sections and
variants — see `adapters/from-style-json.md`.
