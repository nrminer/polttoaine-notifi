# BensaVahti - Total Frontend Revamp Brief

> **Read this whole brief before writing a single line.** Your job is not to "restyle"
> BensaVahti. It is to redesign it from the typography up into something a human designer
> with a strong point of view would be proud to ship - and that a stranger would screenshot
> and remember. Anything that looks like a default AI-generated SaaS dashboard is a failure,
> no matter how clean it is.

## 0. The one sentence

Redesign the BensaVahti frontend into a **distinctive, production-grade, unmistakably
*designed* interface** for Finnish drivers deciding *"do I fill up today or wait?"* - with a
committed aesthetic point of view, zero generic-AI tells, and craft in every detail.

## 1. What you are designing for (context dossier)

**Product.** BensaVahti ("Petrol Watch") shows today's cheapest Finnish pump prices
(nationally + per city) and **predicts tomorrow's cheapest price** using a 5-method ensemble
(moving average, linear regression, Holt exponential smoothing, a fundamental anchor of
Brent + EUR/USD pass-through, and Claude analysing news/geopolitics). It tracks
prediction-vs-actual accuracy and pushes notifications.

**The user & the moment.** A Finnish driver, often on a phone, at a petrol station or on the
sofa the night before. One question matters: *fill up now, or wait a day?* Cents-per-litre
swing week to week. The interface must make a **confident, legible recommendation** and
**earn trust in an algorithm** - clarity and credibility are features, not decoration.

**Tone truths to honour (don't ignore the domain):**
- It is **Finnish**. All UI copy stays in Finnish (do not translate existing strings).
  Finnish design heritage is fair game and *encouraged* (functional rigor, austere
  confidence, Marimekko-scale boldness, transit/almanac/cartographic traditions).
- It is **money + time + motion**: prices rise and fall on a daily/weekly rhythm. Lean into
  rhythm, cadence, directionality.
- It is **a forecast**: there is uncertainty. Show confidence honestly, never fake precision.

## 2. The crime scene - what the current build does wrong (do NOT repeat)

The existing frontend has degraded into AI slop **even though its own
`design_guidelines.json` forbids it**. Concretely:
- **Typography:** `tailwind.config.js` sets `Inter` for both display and body - banned by the
  app's own brief, and the #1 generic-AI tell.
- **Colour:** generic `#2563EB` brand blue + the usual emerald/red signal pairs; no ownership.
- **Surfaces:** `glass-panel` glassmorphism, soft shadows, a uniform rounded card grid -
  the default "AI dashboard" look.
- **Voice:** filler eyebrow text like "Aether Fuel Dashboard" that means nothing.
- **Layout:** predictable 12-col card mosaic; every card the same weight; no hierarchy drama.

Treat all of the above as **anti-patterns to actively reverse**, not a starting point.

## 3. Hard rules - the anti-slop contract (non-negotiable)

**Banned outright:**
1. **Fonts:** Inter, Roboto, Open Sans, Lato, Arial, Helvetica, system-ui stacks, *and*
   Space Grotesk (the AI-default "designer" font). Pick fonts with genuine character.
2. **The purple/indigo gradient on white/near-white.** No "AI startup" gradients.
3. **Generic component-library defaults:** evenly rounded cards in a uniform grid, soft
   drop-shadow everywhere, glassmorphism-by-default, pill buttons with timid blue fills.
4. **Meaningless decoration:** floating blurred blobs, random gradient meshes with no concept,
   emoji as iconography, stock "abstract 3D" hero imagery.
5. **Filler copy / fake-deep eyebrows** ("Powered by AI", "Aether ...", "Next-gen ...").
6. **Centered everything.** No timid, symmetric, evenly-spaced everything-the-same layout.

**Required to avoid slop:**
1. **Commit to ONE of the three directions in section 5** (or a defensible fusion) and execute it
   with precision and consistency - every token, component, and animation serves it.
2. **A real type system:** a characterful display face + a refined text face + a mono for
   numbers. Numbers are the product -> tabular figures, deliberate numeric typography.
3. **Colour with ownership:** a dominant base + 1-2 sharp accents, derived from the concept,
   not from Tailwind defaults. Define everything as CSS variables / tokens.
4. **Hierarchy with drama:** the tomorrow-prediction is the hero - it should dominate. Vary
   card weight, scale, and density. Use asymmetry, overlap, or a grid-breaking element.
5. **Atmosphere, not flat fills:** texture/grain/print/instrument detailing true to the
   concept - never a plain background where the concept calls for depth.
6. **Motion with intent:** one well-orchestrated load (staggered reveal) + a signature
   interaction tied to the concept (e.g. the price "settling"). High-impact, not scattered.

## 4. Craft bar (how good "done" looks)

- **Typography:** deliberate scale, optical sizing on the big numerals, tabular/lining figures
  for all prices and deltas, considered tracking on labels/overlines. The EUR/L number is a
  designed object.
- **Colour & signal:** keep the semantic of "price down = good for the driver, price up = bad"
  but express it in the chosen palette, not default green/red. Ensure WCAG AA contrast in both
  themes.
- **Data-viz:** the Recharts charts (prediction-vs-actual, all-cities average, sparklines,
  the method-weight meters) must be **restyled to the concept** - custom grid, axis, dot,
  tooltip, and line treatments. No default Recharts look. The confidence band must read clearly.
- **Layout & space:** intentional negative space *or* controlled density (per concept). Strong
  responsive behaviour - the phone view is primary; it must feel native, not a squeezed desktop.
- **Micro-detail:** custom focus states, selection colour, scrollbar, empty/loading/error
  states, the refresh affordance, and the live-timestamp all styled in-concept.
- **Micro-copy:** keep Finnish; tighten any filler. Labels should sound like a confident
  Finnish product, not a template.

## 5. Choose your weapon - three original directions

Pick **one** and commit fully. Each is deliberately distinct in mood. None is a generic dark
dashboard. (A thoughtful hybrid is allowed if it stays coherent.) For the chosen one, design
the full token set, then the hero, then everything else.

### Direction A - "ASEMATAULU" (Departure Board)
*Kinetic / mechanical / utilitarian-Finnish / the price you're timing like a train.*
- **Concept:** Tomorrow's price is the **next departure**. The whole UI is a reimagined
  Nordic transit/airport **split-flap board** - you are *timing your fill-up like catching a
  train*. Confident, mechanical, a little playful.
- **Type:** a mechanical/grotesque display (e.g. a strong industrial sans with character) +
  a warm monospace for all numerics and labels. Heavy, condensed headlines.
- **Palette:** deep board-black / ink base, one **signal amber** as the hot accent, a cold
  Nordic blue-grey for structure, paper-white text. Light theme = enamel-sign cream.
- **Layout:** a top "board" hero with **split-flap animated digits** for the price; rows
  below read like a schedule (city = destination, price = time, delta = on-time/delayed).
- **Motion signature:** split-flap flip on price updates; rows "clack" into place on load.
- **Unforgettable thing:** the price literally **flips** into being like a station clock.

### Direction B - "ALMANAKKA" (Risograph Almanac / Barometer)
*Editorial / tactile / printed / the forecast as a Finnish almanac.*
- **Concept:** Fuel price as **weather/almanac**. Antique scientific-instrument and Finnish
  print-almanac feel - etched/engraved charts, barometer dials, paper texture. The tomorrow
  prediction reads like a weather forecast you trust.
- **Type:** a characterful editorial **serif display** (high contrast, almanac flavour) + a
  technical mono/grotesque for data. Real editorial rhythm.
- **Palette:** **two-colour risograph** - a deep ink (navy/oxblood) + ONE fluorescent
  spot (riso orange or sky-blue) over warm paper. Dark theme = night-sky deep navy with
  constellation-like data points. Grain/halftone texture throughout.
- **Layout:** magazine/almanac grid - a dominant forecast "plate", marginalia for sources &
  factors, engraved rule lines, drop-cap-scale numerals.
- **Motion signature:** ink "settles"/registers on load; charts draw like a plotter pen.
- **Unforgettable thing:** it looks **printed**, not rendered - a thing with paper and ink.

### Direction C - "REVONTULI" (Aurora Cartograph)
*Atmospheric / cartographic / luminous - but disciplined, never gradient-slop.*
- **Concept:** Finland as a **living price-map** lit like the aurora. Cities are nodes on a
  real cartographic base; price movement flows as **aurora ribbons** of cold light over deep
  ink. Map-led, not card-led.
- **Type:** a precise **cartographic/technical sans** (map-label character) + a fine mono for
  coordinates/figures. Restrained, exact.
- **Palette:** deep arctic ink base; luminous **aurora teal/green + a cold violet** used as
  *signal*, never as a lazy full-bleed gradient. Grain overlay to kill banding. Light theme =
  topographic-paper with contour lines.
- **Layout:** a map/figure hero (the cheapest-city map) with data ribbons; supporting panels
  framed like map legends and instrument readouts.
- **Motion signature:** aurora ribbons drift slowly; the predicted point pulses like a beacon.
- **Unforgettable thing:** a **cartographic, luminous** read of Finnish fuel - atmosphere with
  rigour, never a soft purple blur.

> Discipline note for C: gradients are easy slop. Keep them textured, grain-dithered, and
> map-grounded; the base must stay ink, with light used surgically.

## 6. Non-negotiable constraints (do not break the app)

This is a **rebuild of a real, shipping app**, not a greenfield mock. Preserve all of:
- **Stack:** React (CRA), Tailwind, Recharts, framer-motion, lucide-react (you may swap the
  icon set if the concept demands, but keep it consistent). No new heavy deps without reason.
- **Data contract:** `frontend/src/lib/api.js` is the source of truth for every backend route;
  field shapes must stay intact (prices are JSON floats in EUR/L, deltas signed, ISO timestamps).
  Don't invent data the backend doesn't return; design real **empty / loading / error / cold-
  start** states (the app often starts with thin data).
- **Components to serve (all must survive the redesign):** tomorrow-prediction hero,
  today/live anchor, the 5-method comparison + ensemble (`MethodTable` / method rail with
  weights), prediction-vs-actual chart (`TrackingChart`), all-cities average + market-move
  (`CityAverageChart`), regional per-city grid (`RegionalGrid`), AI analysis (`AiAnalysis`),
  Brent + EUR/USD factors (`FactorsCard`), news (`NewsCard`), accuracy/MAE (`AccuracyTracker`),
  confidence strip, fuel toggle (95E10 / Diesel), chart filters, header refresh + live time,
  footer, admin link.
- **Finnish UI:** keep all Finnish copy; only tighten filler. No English in the UI.
- **Theming:** keep **dark + light** with the existing toggle and no-FOUC behaviour
  (`localStorage` + the inline script in `public/index.html`). Both themes must be first-class,
  not an afterthought - design the concept for both.
- **Accessibility (hard requirement):** keep the skip-link, keep/extend **every `data-testid`**
  (the Playwright audit + tests depend on them - do not rename or drop them), honour
  `prefers-reduced-motion` (provide non-animated equivalents for the signature motion), full
  keyboard nav, visible focus, WCAG AA contrast, and aria labels on charts.
- **Performance & responsive:** mobile-first; smooth on a mid phone; don't ship megabytes of
  fonts/textures - subset fonts, keep grain/texture cheap (SVG/CSS), lazy-load the heavy chart.

## 7. Process (follow in order)

1. **Commit** to one direction from section 5 (state which, in one line) and write the **one
   unforgettable thing** you'll deliver.
2. **Design the token layer first:** CSS variables for colour (both themes), the type scale,
   spacing, radii (or sharp), shadows/borders, motion timing. Wire fonts (self-hosted/subset).
   This replaces the Inter/`#2563EB` defaults in `tailwind.config.js` + `index.css`.
3. **Build the hero** (tomorrow-prediction) to its full ambition first - it must dominate and
   carry the signature motion. Get this *unmistakably designed* before anything else.
4. **Cascade the system** to every component in section 6, restyling the Recharts charts to concept.
5. **States:** design loading / empty / cold-start / error in-concept (not spinners on grey).
6. **Self-audit against section 3 + the checklist in section 9.** Remove anything that reads as default.

## 8. Research hygiene - anti-slop source rules

When researching anything for this revamp - fonts, Finnish visual references, accessibility
rules, charting patterns, performance guidance, Recharts/Tailwind/framer-motion APIs, browser
support, or implementation details - aggressively filter out AI-generated slop and low-value
content. Prioritize source quality and verifiability over breadth. Fewer, stronger sources
beat many weak ones.

**Source priority, in order:**
1. **Primary sources:** official docs, original research and papers, standards bodies,
   government records, company filings, court documents, raw datasets.
2. **Accountable outlets and named experts:** publications with a masthead, editorial
   standards, bylined authors, or recognized domain practitioners.
3. **Verifiable community sources:** practitioner discussions where expertise can be checked
   and the substance is concrete.

**Avoid, and do not cite unless nothing better exists:**
- Content farms and SEO-bait pages with no named author and no real "About" / accountability.
- Pages that restate generic points found everywhere, with no original data, examples, or
  first-hand experience.
- Sites whose other articles are near-identical templated posts.
- AI-style "ultimate guides," listicles, and roundups full of vague claims and no verifiable
  specifics.

**Red flags that lower trust:**
- Generic, hollow phrasing that could describe any company or topic; buzzword salad;
  aspirational filler with no specifics.
- No author, no date, no contact/About page, no stated editorial standards.
- Testimonials, stats, or quotes that are unverifiable or suspiciously uniform; citations
  that look fabricated.
- Fluent but semantically empty text; evenly balanced, repetitive sentence rhythm; surface
  polish with nothing underneath.
- Statistics or claims that do not trace back to an identifiable origin.
- Visual signals that match common AI-template design: blue-to-purple gradients everywhere,
  default Inter font, glassmorphism/neon glows, thick accent borders on rounded cards,
  over-rounded blobs, and too-smooth AI stock imagery.

**Research behaviour required:**
- For every nontrivial claim, trace it to a primary or authoritative source and cite **that**,
  not an aggregator that copied it.
- Cross-check any surprising statistic, quote, or design claim against at least one
  independent credible source before relying on it.
- When citing a source, add a few words on **why** it is trustworthy (primary, official,
  named expert, standards body, etc.).
- If the best available source is questionable, say so explicitly and flag the uncertainty
  instead of presenting it as fact.
- If something cannot be verified, say "I couldn't verify this" rather than filling the gap
  with generic content.
- At handoff, state where weak sources were used and what would strengthen the answer.

Detection is an arms race. Surface tells disappear first, and skilled humans sometimes trip
the same signals. The durable filter is specificity and traceable primary sources, not
stylistic vibes - weight provenance over "this sounds AI-written."

## 9. Definition of done (self-check before you claim completion)

- [ ] Direction named; the "unforgettable thing" is actually present and works.
- [ ] **Zero** banned fonts; a real display + text + mono system is wired and self-hosted.
- [ ] Colour is concept-owned (no `#2563EB`/default Tailwind palette); AA contrast both themes.
- [ ] The hero dominates; hierarchy has drama; layout is not a uniform rounded-card grid.
- [ ] Charts are visibly restyled (no default Recharts look); confidence band reads clearly.
- [ ] Signature load animation + one concept interaction; full `prefers-reduced-motion` path.
- [ ] All Finnish copy intact; filler eyebrows removed/replaced with meaningful labels.
- [ ] Every existing `data-testid` preserved; skip-link, keyboard, focus, aria all intact.
- [ ] Dark + light both first-class; no-FOUC preserved; mobile view feels native.
- [ ] Could a designer screenshot this and be proud? Would a stranger remember it? If not, push further.

> Don't hold back. Show what BensaVahti looks like when a real designer with a point of view
> - not a template - gets hold of it.
