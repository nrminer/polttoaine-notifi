# BensaVahti frontend dashboard redesign design

Date: 2026-06-02

## Goal

Redesign the React CRA frontend into a polished, practical Finnish fuel-price dashboard while preserving the current backend contract and live-data-only product constraints. The first screen must be the real dashboard, not a marketing landing page. Dark mode remains supported and default.

The approved direction is **A · Summary-first dashboard** with **Neutral summary** forecast presentation.

## Non-goals

- Do not redesign backend prediction behavior.
- Do not remove useful forecast functionality.
- Do not introduce Statfin, synthetic data, interpolation, extrapolation, or fake historical values.
- Do not expose backend-only internals, method IDs, model names, vendor names, or raw technical prediction mechanics in the normal UI.
- Do not translate the UI to English.

## User-facing AI/model cleanup

The redesigned UI must not show these terms or concepts in visible user-facing text:

- `AI`
- `ai_llm`
- `Codex`
- `Claude`
- `LLM`
- `model`
- `modelName`
- `tekoäly`
- AI-specific uses of `analyysi`
- backend method IDs or model version strings

Backend JSON may still contain those fields. The frontend should simply not render them.

Default forecast language:

- `Huomisen ennuste`
- `Markkinaennuste`
- `Hintasuunta`
- `Luottamusväli` or `Vaihteluväli`
- `Ennusteen perusteet`
- `Historiallinen osumatarkkuus`
- `Markkinatekijät`

## Target information architecture

### 1. Sticky compact header

Purpose: keep core controls reachable on desktop and mobile.

Contents:

- App name: `BensaVahti`
- selected fuel toggle: 95E10 / Diesel
- theme toggle with accessible label
- refresh action with loading state
- compact last-updated/status text when available

Requirements:

- Use buttons for all interactive controls.
- Preserve `data-testid` attributes for interactive elements.
- Use visible focus states and `aria-label` / `aria-pressed` where appropriate.
- Keep header compact; avoid a marketing hero.

### 2. `Tilanne nyt` summary strip

Purpose: answer the immediate user question at a glance.

Cards:

- cheapest national price for selected fuel
- selected fuel city average when available
- tomorrow estimate when available
- latest capture/update time and freshness

Behavior:

- Missing values render `—` with short Finnish helper text, not fake prices.
- Stale data gets a visible warning badge.
- Use consistent `€/L` formatting and tabular monospace numbers.

### 3. Main forecast panel

Purpose: keep forecasting useful while making it feel like a normal market dashboard.

Show by default:

- tomorrow estimated price
- direction: `nousussa`, `laskussa`, or `vakaa`
- range if available
- concise key drivers
- historical accuracy summary if available

Do not show by default:

- individual model names
- method IDs
- method weights
- vendor names
- model/version labels
- raw method-comparison table

Implementation guidance:

- Remove `AiAnalysis` from normal rendering.
- Remove or replace visible `MethodTable` usage.
- If backend returns method-level data, derive only neutral summary values from `ensemble_full`, `prediction_for_tomorrow`, direction, confidence/range, drivers, and accuracy payloads.

### 4. Current cheapest and city comparison

Purpose: make prices easier to compare and station details easier to inspect.

Contents:

- cheapest national station card
- regional/city comparison table
- station detail rows: station, address, city, source, report age/freshness
- sortable columns where existing data supports it:
  - cheapest price
  - average price
  - station/source freshness

Behavior:

- Highlight cheapest city.
- Show source badges for `tankille.fi` / `polttoaine.net` when present.
- Keep table horizontally scrollable on narrow screens.
- Use safe fallbacks for missing station/address/source fields.

### 5. Charts

Purpose: make movement and forecast accuracy readable without overwhelming the first screen.

Charts:

- prediction vs actual tracking chart
- all-cities average chart

Controls:

- 30 / 90 / 365 day range toggle where data supports it
- cheapest vs city-average toggle where data supports it
- selected city filter
- clear empty states when insufficient live captures exist

Behavior:

- Preserve Recharts usage.
- Keep chart container heights explicit so charts render correctly.
- Keep readable mobile labels and legends.

### 6. Market context section

Purpose: explain price movement using normal market-dashboard language.

Contents:

- Brent / EUR-USD / refined-product factors if already available
- Finnish news headlines if already available

Copy rules:

- Use neutral text such as `Markkinauutiset`, `Hintatekijät`, and `Seuratut lähteet`.
- Do not say that AI reads or analyzes headlines.
- Do not display raw model explanations.

Security and safety:

- External news links must allow only `http:` and `https:`.
- External links use `target="_blank"` with `rel="noopener noreferrer"`.

## Component/file impact

Likely edited files:

- `frontend/src/App.js`
- `frontend/src/App.css`
- `frontend/src/index.css`
- `frontend/src/components/RegionalGrid.jsx`
- `frontend/src/components/TrackingChart.jsx`
- `frontend/src/components/CityAverageChart.jsx`
- `frontend/src/components/NewsCard.jsx`
- `frontend/src/components/FactorsCard.jsx`
- `frontend/src/components/AccuracyTracker.jsx`
- `frontend/src/components/Card.jsx` if shared primitives need small additions
- `frontend/src/lib/utils.js` for safe formatting helpers if needed
- `frontend/public/index.html` only for title/meta copy if AI/model language is present

Likely removed from normal UI usage:

- `frontend/src/components/AiAnalysis.jsx`
- `frontend/src/components/MethodTable.jsx`
- `frontend/src/lib/modelName.js`

These files do not need to be deleted unless they become truly unused and removal is safe.

## Data flow

Keep all backend calls centralized through `frontend/src/lib/api.js`.

App-level data sources remain:

- current prices
- latest prediction
- regional prices
- tracking history
- city average/history data
- factors
- news
- accuracy

The redesign may reorganize how these values are displayed, but it must not trigger new backend writes from passive page rendering. Refresh actions may keep existing behavior.

## Error, loading, and empty states

Add or preserve:

- card-level loading indicators/skeletons
- friendly Finnish error messages
- retry/refresh action
- empty states for missing live captures
- stale-data indicators

Do not display raw backend error details to production users. Development logs may keep more detail if gated by `NODE_ENV === "development"`.

## Accessibility

Requirements:

- semantic sections with useful headings
- skip link preserved
- visible focus rings
- button controls instead of clickable divs
- `aria-label`, `aria-pressed`, and `aria-expanded` where relevant
- responsive touch targets
- reduced-motion support preserved
- dark/light contrast checked manually

## Testing and verification

Before completion:

1. Run frontend grep to confirm no user-facing AI/model branding remains.
2. Run frontend build: `yarn build` in `/frontend`.
3. Run lint/tests if available and practical.
4. Inspect desktop and mobile views manually.
5. Verify dark and light themes.
6. Verify missing/partial prediction data renders gracefully.
7. Verify a failed endpoint does not break the whole page.
8. Verify external news links are safe.

Acceptance checks:

- website loads current prices, prediction summary, regional data, charts, factors/news where available
- no visible AI/model branding remains in normal UI
- Finnish UI remains concise and practical
- mobile layout is usable
- dark/light theme works
- no fake data is introduced
- backend contract remains compatible
