# First Principles of Visual Design

> Every rule in this system is derived from these axioms.
> If a rule contradicts an axiom, the axiom wins.
> If two axioms conflict, the tension between them IS the design.

---

## The Three Axioms

### Axiom I: Hierarchy is the only job.

Every pixel on the screen answers one question: **what do I look at first, second, third, never?**

Everything — size, weight, color, position, motion, space — exists to create or reinforce hierarchy. A design without clear hierarchy is not a design. It is noise.

This is not about making things "readable." It is about **controlling the eye**. The designer decides the sequence. The viewer follows.

**Derived truths:**
- If two elements compete for attention, one must yield or both fail.
- Contrast creates hierarchy. Sameness destroys it. The greater the difference between levels, the stronger the hierarchy.
- Size is the loudest signal. Weight is second. Color is third. Position is fourth. Motion is fifth.
- The most powerful hierarchy tool is *omission* — what you remove decides what remains important.

---

### Axiom II: Tension is beauty.

A composition with no tension is dead. A composition with only tension is chaos. Beauty lives in the space between order and disruption.

Tension arises when elements *almost* align, *almost* touch, *almost* match — but don't. The eye detects the deviation and becomes alert. This alertness is engagement. Engagement is the goal.

**Derived truths:**
- Perfect symmetry is resolved tension. Resolved tension is boring. Near-symmetry keeps the eye searching.
- Every composition needs at least one element that *breaks the pattern*. This is the discord — the wrong color, the misaligned element, the unexpected scale. It proves the rest is intentional.
- Whitespace is not absence. It is the counterforce to content. The pressure between filled and empty space creates the tension that holds a layout together.
- A grid exists to be *almost* followed. A layout that perfectly obeys its grid has no personality. One that breaks it in exactly one place has a voice.

---

### Axiom III: The medium is time.

A screen is not a poster. It exists in time — scroll time, hover time, load time, attention time. Designing for screen without designing for time is designing for the wrong medium.

Every element has a *when*, not just a *where*. The sequence of perception — what appears first, what reveals on scroll, what responds to the cursor — is a dimension of the design as real as x and y.

**Derived truths:**
- A page that shows everything at once wastes its medium. Revelation over time creates narrative.
- Motion without purpose is decoration. Motion with purpose is choreography. The difference is whether you can explain *why* it moves.
- The pause between events matters more than the events. Silence is a note.
- Scroll position is a design variable. Viewport size is a design variable. Pointer position is a design variable. Time elapsed is a design variable. Use them.

---

## The Five Corollaries

These follow directly from the three axioms. They are not separate principles — they are the axioms applied to specific materials.

### Corollary 1: Type is the primary material.

*From Axiom I (hierarchy) + Axiom II (tension):*

Typography creates hierarchy through size, weight, and spacing — simultaneously. No other element does this. Therefore typography is not decoration applied to content. Typography IS the design. Content and form are the same thing.

A composition that works in pure black text on white, with no images, no color, no effects — is a strong composition. Everything else is enhancement.

**In practice:**
- Choose typefaces for their *voice*, not their beauty. A typeface speaks before you read a word.
- The ratio between your largest and smallest type is the dynamic range of your design. A narrow range whispers. A wide range shouts. Most designs are too narrow.
- Letter-spacing, line-height, and measure (line length) are not details. They are structural decisions that change the meaning of the text.

### Corollary 2: Color is emotion, not information.

*From Axiom I (hierarchy) + Axiom II (tension):*

Color's primary job is emotional register — it tells the viewer how to *feel* before they read a word. Its secondary job is hierarchy (accent vs. background). It should almost never carry informational load (red = error) without a redundant signal.

**In practice:**
- One palette per composition. Then break it with one color that doesn't belong. The discord is the magic.
- Fewer colors = stronger design. Black and white is not an absence of color. It is the most decisive color choice possible.
- Dark backgrounds make content glow. Light backgrounds make content recede. Choose based on whether the content should radiate or rest.

### Corollary 3: Space is structure.

*From Axiom I (hierarchy) + Axiom II (tension):*

The space between elements defines their relationship more than any line, border, or box ever could. Proximity means relatedness. Distance means independence. Unequal spacing creates hierarchy. Equal spacing creates rhythm.

**In practice:**
- If you need a border or a box to separate elements, your spacing has failed.
- A section that is 70% empty is not 70% wasted. The negative space is doing the heavy lifting.
- Spacing should be rhythmic — based on a scale, not arbitrary. But the rhythm should occasionally break (Axiom II).

### Corollary 4: Layout is argument.

*From Axiom I (hierarchy) + Axiom III (time):*

A layout is not a container for content. It is an *argument* about which content matters, in what order, and how the pieces relate. The grid, the column widths, the breaks — these are rhetorical choices.

**In practice:**
- Asymmetric layouts argue that one side matters more. Use them when that's true.
- Full-bleed elements argue "this is the world." Contained elements argue "this is an object in the world." Choose deliberately.
- The first screen (above the fold) is a promise. It tells the viewer what kind of experience follows. Break that promise at your peril.

### Corollary 5: Motion is narrative.

*From Axiom II (tension) + Axiom III (time):*

Motion sequences elements in time, creating a story where there was a snapshot. A card that slides up is *arriving*. A card that fades in was always *there but hidden*. The difference is narrative.

**In practice:**
- Elements that enter together are perceived as a group. Stagger reveals to show hierarchy.
- Fast motion feels decisive. Slow motion feels considered. The speed communicates attitude.
- The entry animation is a first impression. The hover animation is a conversation. The exit animation is a goodbye. Each has different rules.

---

## The Decision Engine

When facing any design choice, run it through this filter:

```
1. Does this serve the hierarchy?          (Axiom I)
   → If not, remove it or subordinate it.

2. Does this create or resolve tension?    (Axiom II)
   → If it creates tension intentionally, keep it.
   → If it resolves all tension, add a discord.
   → If it creates tension accidentally, fix it.

3. Does this use the medium?               (Axiom III)
   → Could this be better if it responded to
     scroll, viewport, pointer, or time?
   → If it could be a poster, it's not using the screen.
```

If a design choice passes all three, it stays. If it fails any one, it must be justified by the others or removed.

---

## On Craft vs. Taste

These axioms don't tell you *what* to make. They tell you *how to evaluate* what you've made.

**Taste** is knowing that a brutalist poster in vermillion on black *feels right* for this project. That can't be taught by axioms. It comes from exposure — from studying Müller-Brockmann, Carson, Sagmeister, Toda, Immersive Garden, Cargo's finest templates, and every Awwwards SOTD.

**Craft** is knowing that the type is 2px too large, the letter-spacing is fighting the word-spacing, and the animation eases out when it should snap. That IS taught by axioms — by understanding hierarchy, tension, and time deeply enough that violations become visible.

Taste without craft produces work that feels right but looks amateur.
Craft without taste produces work that looks polished but feels empty.

The axioms live in the craft. The taste is on you.

---

*Three axioms. Five corollaries. One decision engine. Everything else is application.*
