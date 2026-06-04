# Frontend Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved summary-first Finnish fuel-price dashboard and remove visible AI/model branding from the normal frontend UI while preserving the existing backend API contract.

**Architecture:** Keep `frontend/src/App.js` as the orchestration layer, but simplify what it renders: compact sticky header, `Tilanne nyt` strip, neutral `Huomisen ennuste`, city/station comparison, charts, and market context. Add small pure helper utilities in `frontend/src/lib/dashboard.js` so prediction/freshness/link/error logic can be tested without browser rendering.

**Tech Stack:** React 18 CRA, Tailwind utility classes, Recharts, framer-motion, lucide-react, Jest/react-scripts test runner, existing `frontend/src/lib/api.js` wrappers only.

---

## File map

- Create: `frontend/src/lib/dashboard.js` — pure dashboard helpers: safe URL validation, production-safe error message, forecast summary extraction, freshness labels, price formatting guards.
- Create: `frontend/src/lib/dashboard.test.js` — unit tests for the helper functions.
- Modify: `frontend/src/App.js` — remove visible AI/model UI, reorganize sections, add summary-first layout and neutral forecast panel.
- Modify: `frontend/src/components/NewsCard.jsx` — safe external links and neutral market-news copy.
- Modify: `frontend/src/components/RegionalGrid.jsx` — strengthen city comparison data-test coverage without changing API shape.
- Modify: `frontend/src/components/AccuracyTracker.jsx` — remove visible AI/model labels from method names if still rendered anywhere.
- Modify: `frontend/src/App.css` and `frontend/src/index.css` — polish summary-first layout, sticky/mobile controls, skeletons, and dark/light card treatment.
- Modify: `frontend/public/index.html` — only if title/meta text contains banned visible AI/model copy.
- Remove usage from normal UI: `frontend/src/components/AiAnalysis.jsx`, `frontend/src/components/MethodTable.jsx`, `frontend/src/lib/modelName.js`.

---

### Task 1: Add pure dashboard helpers and tests

**Files:**
- Create: `frontend/src/lib/dashboard.js`
- Create: `frontend/src/lib/dashboard.test.js`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/lib/dashboard.test.js`:

```javascript
import {
  getSafeExternalUrl,
  getPublicErrorMessage,
  getForecastSummary,
  getFreshnessLabel,
  isStaleHours,
} from "./dashboard";

describe("dashboard helpers", () => {
  test("getSafeExternalUrl allows http and https only", () => {
    expect(getSafeExternalUrl("https://example.com/news")).toBe("https://example.com/news");
    expect(getSafeExternalUrl("http://example.com/news")).toBe("http://example.com/news");
    expect(getSafeExternalUrl("javascript:alert(1)")).toBeNull();
    expect(getSafeExternalUrl("data:text/html,hello")).toBeNull();
    expect(getSafeExternalUrl("not a url")).toBeNull();
    expect(getSafeExternalUrl(null)).toBeNull();
  });

  test("getPublicErrorMessage hides backend details in production", () => {
    const err = { response: { data: { detail: "Traceback: backend detail" } } };
    expect(getPublicErrorMessage(err, "production")).toBe("Tietojen haku epäonnistui. Yritä päivittää hetken päästä.");
    expect(getPublicErrorMessage(err, "development")).toBe("Traceback: backend detail");
  });

  test("getFreshnessLabel formats update age", () => {
    expect(getFreshnessLabel(null)).toBe("—");
    expect(getFreshnessLabel(0.4)).toBe("juuri nyt");
    expect(getFreshnessLabel(3.2)).toBe("3 h sitten");
    expect(getFreshnessLabel(49)).toBe("2 pv sitten");
  });

  test("isStaleHours treats 24 hours and above as stale", () => {
    expect(isStaleHours(null)).toBe(false);
    expect(isStaleHours(6)).toBe(false);
    expect(isStaleHours(23.9)).toBe(false);
    expect(isStaleHours(24)).toBe(true);
  });

  test("getForecastSummary returns neutral summary from prediction data", () => {
    const summary = getForecastSummary({
      fuel: "95E10",
      target_date: "2026-06-03",
      current_price: 1.900,
      ensemble: {
        value: 1.912,
        confidence_low: 1.890,
        confidence_high: 1.930,
        direction: "up",
      },
      methods: {
        ai_llm: { model: "claude-opus-4-7", explanation: "hidden" },
      },
    });

    expect(summary.value).toBe(1.912);
    expect(summary.directionLabel).toBe("nousussa");
    expect(summary.rangeLabel).toBe("1.890–1.930 €/L");
    expect(JSON.stringify(summary)).not.toMatch(/claude|ai_llm|model|hidden/i);
  });

  test("getForecastSummary handles partial prediction data", () => {
    const summary = getForecastSummary(null);
    expect(summary.value).toBeNull();
    expect(summary.directionLabel).toBe("vakaa");
    expect(summary.rangeLabel).toBe("—");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
yarn --cwd frontend test --watchAll=false --runTestsByPath src/lib/dashboard.test.js
```

Expected: FAIL because `frontend/src/lib/dashboard.js` does not exist.

- [ ] **Step 3: Implement helpers**

Create `frontend/src/lib/dashboard.js`:

```javascript
const PRICE_MIN = 1.0;
const PRICE_MAX = 4.0;

export function safeNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function safePrice(value) {
  const n = safeNumber(value);
  if (n == null) return null;
  return n >= PRICE_MIN && n <= PRICE_MAX ? n : null;
}

export function formatEurL(value) {
  const n = safePrice(value);
  return n == null ? "—" : `${n.toFixed(3)} €/L`;
}

export function getSafeExternalUrl(value) {
  if (!value || typeof value !== "string") return null;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch (_error) {
    return null;
  }
}

export function getPublicErrorMessage(error, env = process.env.NODE_ENV) {
  const fallback = "Tietojen haku epäonnistui. Yritä päivittää hetken päästä.";
  if (env === "development") {
    return error?.response?.data?.detail || error?.message || fallback;
  }
  return fallback;
}

export function getFreshnessLabel(ageHours) {
  const h = safeNumber(ageHours);
  if (h == null) return "—";
  if (h < 1) return "juuri nyt";
  if (h < 48) return `${Math.round(h)} h sitten`;
  return `${Math.round(h / 24)} pv sitten`;
}

export function isStaleHours(ageHours, threshold = 24) {
  const h = safeNumber(ageHours);
  return h != null && h >= threshold;
}

function normalizeDirection(raw, delta) {
  const value = String(raw || "").toLowerCase();
  if (value.includes("up") || value.includes("nous")) return "up";
  if (value.includes("down") || value.includes("lask")) return "down";
  if (delta > 0.002) return "up";
  if (delta < -0.002) return "down";
  return "stable";
}

export function getForecastSummary(prediction) {
  const ensemble = prediction?.ensemble || prediction?.ensemble_full || {};
  const value = safePrice(ensemble.value ?? prediction?.prediction_for_tomorrow ?? prediction?.value);
  const anchor = safePrice(prediction?.current_price ?? prediction?.live_anchor);
  const low = safePrice(ensemble.confidence_low ?? ensemble.low);
  const high = safePrice(ensemble.confidence_high ?? ensemble.high);
  const delta = value != null && anchor != null ? value - anchor : 0;
  const direction = normalizeDirection(ensemble.direction ?? prediction?.direction, delta);
  const directionLabel = direction === "up" ? "nousussa" : direction === "down" ? "laskussa" : "vakaa";
  const rangeLabel = low != null && high != null ? `${low.toFixed(3)}–${high.toFixed(3)} €/L` : "—";

  const drivers = [];
  if (prediction?.product_chg != null) drivers.push("jalostettu tuote");
  if (prediction?.brent != null || prediction?.brent_chg != null) drivers.push("Brent");
  if (prediction?.eur_usd != null || prediction?.fx_chg != null) drivers.push("EUR/USD");
  if (prediction?.conflict_signal) drivers.push("tarjontariski");
  if (drivers.length === 0) drivers.push("live-hinta", "viimeaikainen hintaliike");

  return {
    value,
    anchor,
    delta,
    low,
    high,
    rangeLabel,
    direction,
    directionLabel,
    drivers,
    targetDate: prediction?.target_date || null,
    generatedAt: prediction?.generated_at || null,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
yarn --cwd frontend test --watchAll=false --runTestsByPath src/lib/dashboard.test.js
```

Expected: PASS.

---

### Task 2: Harden and neutralize NewsCard

**Files:**
- Modify: `frontend/src/components/NewsCard.jsx`

- [ ] **Step 1: Replace direct news links and AI copy**

Replace `frontend/src/components/NewsCard.jsx` with:

```javascript
import React from "react";
import { Newspaper, ExternalLink, Clock } from "lucide-react";
import { Card, CardLabel } from "./Card";
import { getFreshnessLabel, getSafeExternalUrl } from "../lib/dashboard";

function AgeBadge({ h }) {
  if (h == null) return null;
  const fresh = h < 6;
  return (
    <span className={`inline-flex items-center gap-1 font-mono text-[10px] px-1.5 py-0.5 rounded-full ${
      fresh ? "bg-emerald-100 text-emerald-700" : "text-secondary"
    }`}>
      {fresh && <Clock size={9} />}
      {getFreshnessLabel(h)}
    </span>
  );
}

export default function NewsCard({ items = [] }) {
  return (
    <Card testId="news-card" className="p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Newspaper size={14} className="text-brand" strokeWidth={2.4} />
          <CardLabel>Markkinauutiset · Iltalehti · HS · IS · MTV</CardLabel>
        </div>
        <span className="font-mono text-[10px] text-muted uppercase tracking-wider" data-testid="news-count">
          {items.length} otsikkoa
        </span>
      </div>

      {items.length === 0 ? (
        <div className="font-mono text-xs text-secondary py-8 text-center border border-dashed border-line rounded-lg" data-testid="news-empty-state">
          Ei tuoreita markkinauutisia.
        </div>
      ) : (
        <ul className="space-y-1" data-testid="news-list">
          {items.map((it, idx) => {
            const safeUrl = getSafeExternalUrl(it.link);
            const content = (
              <>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-ink leading-snug line-clamp-2 group-hover:text-brand transition-colors" data-testid={`news-title-${idx}`}>
                    {it.title || "Otsikko puuttuu"}
                  </p>
                  <div className="mt-1 flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-[10px] uppercase tracking-wider text-muted" data-testid={`news-source-${idx}`}>
                      {it.source || "Uutislähde"}
                    </span>
                    <span className="text-muted">·</span>
                    <AgeBadge h={it.age_hours} />
                  </div>
                </div>
                {safeUrl && <ExternalLink size={12} className="text-muted shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity" />}
              </>
            );

            return (
              <li key={`${it.title || "news"}-${idx}`} data-testid={`news-item-${idx}`}>
                {safeUrl ? (
                  <a href={safeUrl} target="_blank" rel="noopener noreferrer" className="group flex gap-3 items-start p-2.5 rounded-lg hover:bg-surface transition-colors -mx-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60" data-testid={`news-link-${idx}`}>
                    {content}
                  </a>
                ) : (
                  <div className="group flex gap-3 items-start p-2.5 rounded-lg -mx-1" data-testid={`news-link-disabled-${idx}`}>
                    {content}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <div className="mt-3 pt-3 border-t border-line text-[10px] text-muted font-mono" data-testid="news-footnote">
        Seuratut lähteet ja markkinaotsikot. Ei mainoksia, suora syöte.
      </div>
    </Card>
  );
}
```

- [ ] **Step 2: Run helper tests**

Run:

```bash
yarn --cwd frontend test --watchAll=false --runTestsByPath src/lib/dashboard.test.js
```

Expected: PASS.

---

### Task 3: Rewrite App.js imports and neutral helper components

**Files:**
- Modify: `frontend/src/App.js`

- [ ] **Step 1: Remove AI/model imports and add dashboard helpers**

Remove these imports/usages from `frontend/src/App.js`:

```javascript
Sparkles,
MethodTable,
AiAnalysis,
formatModelName,
```

Add:

```javascript
import { getForecastSummary, getPublicErrorMessage, formatEurL } from "./lib/dashboard";
```

- [ ] **Step 2: Remove `DARK_METHODS`, `deltaColorDark`, and `deltaFmtMilli`**

Delete the method grid constants and replace them with:

```javascript
function DirectionPill({ direction }) {
  const config =
    direction === "up"
      ? { label: "nousussa", icon: ArrowUpRight, cls: "bg-red-500/15 text-red-200 border-red-400/30" }
      : direction === "down"
      ? { label: "laskussa", icon: ArrowDownRight, cls: "bg-emerald-500/15 text-emerald-200 border-emerald-400/30" }
      : { label: "vakaa", icon: Minus, cls: "bg-slate-500/15 text-slate-200 border-slate-400/30" };
  const Icon = config.icon;
  return (
    <span data-testid="forecast-direction" className={`inline-flex items-center gap-2 px-3 h-9 rounded-lg border font-mono text-xs font-semibold ${config.cls}`}>
      <Icon size={14} />
      {config.label}
    </span>
  );
}

function SummaryCard({ label, value, detail, stale = false, testId }) {
  return (
    <Card testId={testId} className={`summary-strip-card p-4 ${stale ? "border-amber-300 bg-amber-50/70 dark:bg-amber-500/10" : ""}`}>
      <div className="flex items-center justify-between gap-2">
        <CardLabel>{label}</CardLabel>
        {stale && <span className="font-mono text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700">vanha</span>}
      </div>
      <div className="mt-2 font-mono tnum text-2xl font-black tracking-tight" data-testid={`${testId}-value`}>
        {value}
      </div>
      <div className="mt-1 text-xs text-secondary" data-testid={`${testId}-detail`}>
        {detail || "—"}
      </div>
    </Card>
  );
}

function ForecastMetric({ label, value }) {
  return (
    <div className="rounded-lg border border-slate-700/60 bg-white/5 p-3">
      <div className="font-mono text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="mt-1 font-mono tnum text-sm font-semibold text-slate-100" data-testid={`forecast-metric-${label.toLowerCase().replace(/\s+/g, "-")}`}>
        {value || "—"}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Sanitize prediction error copy**

Replace:

```javascript
setError(e.response?.data?.detail || "Ennusteen ajaminen epäonnistui");
```

with:

```javascript
setError(getPublicErrorMessage(e));
```

---

### Task 4: Replace hero and forecast sections with summary-first layout

**Files:**
- Modify: `frontend/src/App.js`

- [ ] **Step 1: Add derived dashboard values**

Inside `App()` after `tomorrowDelta`, add:

```javascript
const forecastSummary = useMemo(() => getForecastSummary(prediction), [prediction]);

const latestCaptureLabel = useMemo(() => {
  const captured = tracking?.summary?.today_captured_at;
  if (captured) return fmtDateTimeFi(captured);
  if (tracking?.summary?.today_date && tracking?.summary?.today_hour != null) {
    return `${fmtDateFi(tracking.summary.today_date)} klo ${String(tracking.summary.today_hour).padStart(2, "0")}:00`;
  }
  return current?.fetched_at ? fmtDateTimeFi(current.fetched_at) : "—";
}, [tracking, current]);

const cheapestCity = useMemo(() => {
  const rows = regional?.rows || [];
  return rows.filter((row) => row.price != null).sort((a, b) => a.price - b.price)[0] || null;
}, [regional]);

const selectedCityAverage = useMemo(() => {
  const byCity = current?.by_city || {};
  const values = Object.values(byCity)
    .map((city) => city.mean ?? city.avg ?? city.average)
    .filter((value) => Number.isFinite(Number(value)))
    .map(Number);
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}, [current]);
```

- [ ] **Step 2: Replace current hero section**

Replace the current `{/* HERO */}` section with:

```jsx
<section id="main-content" className="max-w-[1480px] mx-auto px-4 md:px-10 pt-6 md:pt-10 pb-6">
  <div className="flex flex-col gap-5">
    <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
      <div>
        <CardLabel className="mb-2">Suomi · live-hinnat ja huomisen markkinaennuste</CardLabel>
        <h1 className="font-display text-3xl md:text-5xl font-black tracking-tightest leading-tight text-ink">
          Polttoaineen tilanne nyt
        </h1>
        <p className="text-secondary text-sm md:text-base mt-2 max-w-2xl leading-relaxed">
          Päivitetyt asemat, kaupunkivertailu ja huomisen hintasuunta yhdellä näkymällä.
        </p>
      </div>
      <FuelToggle value={fuel} onChange={setFuel} />
    </div>

    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3" data-testid="summary-strip">
      <SummaryCard label="Halvin nyt" value={formatEurL(todayMin)} detail={cheapestCity?.region || "Suomi"} testId="summary-current-cheapest" />
      <SummaryCard label="Kaupunkien keskiarvo" value={formatEurL(selectedCityAverage)} detail="seuratut kaupungit" testId="summary-city-average" />
      <SummaryCard label="Huomenna" value={formatEurL(forecastSummary.value)} detail={forecastSummary.directionLabel} testId="summary-tomorrow" />
      <SummaryCard label="Päivitetty" value={latestCaptureLabel} detail={current?.stale ? "välimuistista" : "tuorein havainto"} stale={Boolean(current?.stale)} testId="summary-updated" />
    </div>

    {error && (
      <div data-testid="error-banner" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-mono text-red-700 dark:bg-red-500/10 dark:border-red-400/30 dark:text-red-200">
        {error}
      </div>
    )}
  </div>
</section>
```

- [ ] **Step 3: Replace method grid in forecast card**

In the forecast section, replace the method-comparison right column with:

```jsx
<div className="col-span-12 md:col-span-7 md:border-l md:border-slate-700/60 md:pl-8">
  <div className="flex items-center justify-between mb-4">
    <CardLabel className="text-slate-400">Ennusteen perusteet</CardLabel>
    {forecastSummary.anchor != null && (
      <span className="font-mono text-[11px] text-slate-500">
        live · <span className="tnum text-slate-300">{forecastSummary.anchor.toFixed(3)} €/L</span>
      </span>
    )}
  </div>

  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="forecast-basis-grid">
    <ForecastMetric label="Hintasuunta" value={forecastSummary.directionLabel} />
    <ForecastMetric label="Vaihteluväli" value={forecastSummary.rangeLabel} />
    <ForecastMetric label="Muutos liveen" value={forecastSummary.delta ? `${forecastSummary.delta >= 0 ? "+" : ""}${forecastSummary.delta.toFixed(3)} €/L` : "—"} />
  </div>

  <div className="mt-5">
    <CardLabel className="text-slate-400">Markkinatekijät</CardLabel>
    <div className="mt-2 flex flex-wrap gap-2" data-testid="forecast-driver-list">
      {forecastSummary.drivers.map((driver) => (
        <span key={driver} className="inline-flex items-center px-2.5 h-7 rounded-md bg-white/5 border border-slate-700/60 text-slate-300 font-mono text-[11px]">
          {driver}
        </span>
      ))}
    </div>
  </div>

  <div data-testid="auto-info-pill" className="mt-5 inline-flex items-center gap-2 px-4 h-9 rounded-lg bg-accent/15 text-accent border border-accent/30 font-semibold text-sm">
    <Clock size={14} />
    Päivittyy automaattisesti klo 14 ja 21 Helsingin aikaa
  </div>
</div>
```

Also replace `DirectionPill delta={tomorrowDelta}` with:

```jsx
<DirectionPill direction={forecastSummary.direction} />
```

Replace `ensemble-arvio` with `markkinaennuste`.

---

### Task 5: Reorganize dashboard sections

**Files:**
- Modify: `frontend/src/App.js`
- Modify: `frontend/src/components/RegionalGrid.jsx`

- [ ] **Step 1: Remove visible MethodTable and AiAnalysis rendering**

In `frontend/src/App.js`:

- Delete the `<MethodTable result={prediction} />` column.
- Change tracking chart card span from `col-span-12 lg:col-span-8` to `col-span-12`.
- Delete the whole section that renders `<AiAnalysis ... />`.

- [ ] **Step 2: Move RegionalGrid directly after the forecast card**

Use:

```jsx
<section className="max-w-[1480px] mx-auto px-4 md:px-10 pb-8">
  <RegionalGrid data={regional} fuel={fuel} cityData={current?.by_city} />
</section>
```

- [ ] **Step 3: Update chart ranges to 30 / 90 / 365**

Replace `CHART_RANGES` with:

```javascript
const CHART_RANGES = [
  { value: 30, label: "30 PV" },
  { value: 90, label: "90 PV" },
  { value: 365, label: "1 V" },
];
```

- [ ] **Step 4: Put factors and news in neutral market context grid**

Use this section before accuracy:

```jsx
<section className="max-w-[1480px] mx-auto px-4 md:px-10 pb-8">
  <div className="grid grid-cols-12 gap-6">
    <div className="col-span-12 lg:col-span-5">
      <FactorsCard factors={factors} prediction={prediction} />
    </div>
    <div className="col-span-12 lg:col-span-7">
      <NewsCard items={prediction?.news_headlines?.length ? prediction.news_headlines : news} />
    </div>
  </div>
</section>

<section className="max-w-[1480px] mx-auto px-4 md:px-10 pb-16">
  <AccuracyTracker data={accuracy} />
</section>
```

- [ ] **Step 5: Add data-test IDs to RegionalGrid controls**

In `RegionalGrid.jsx`, add:

```jsx
data-testid="regional-all-cities-btn"
data-testid={`regional-city-${city}`}
data-testid="regional-sort-btn"
data-testid={`region-price-${row.region}`}
data-testid={`region-source-${row.region}`}
```

---

### Task 6: Remove visible AI/model labels from remaining render path

**Files:**
- Modify: `frontend/src/components/AccuracyTracker.jsx`
- Inspect: `frontend/src/components/FactorsCard.jsx`
- Inspect: `frontend/public/index.html`

- [ ] **Step 1: Search rendered frontend files**

Run:

```bash
python - <<'PY'
from pathlib import Path
terms = ['AI', 'ai_llm', 'Codex', 'Claude', 'LLM', 'modelName', 'tekoäly']
for path in Path('frontend/src').rglob('*'):
    if path.suffix.lower() not in {'.js', '.jsx', '.css'}:
        continue
    text = path.read_text(encoding='utf-8', errors='ignore')
    for term in terms:
        if term.lower() in text.lower():
            print(f'{path}: contains {term}')
PY
```

- [ ] **Step 2: Neutralize AccuracyTracker method labels**

In `frontend/src/components/AccuracyTracker.jsx`, replace any visible label like:

```javascript
ai_llm: "AI / Claude"
```

with:

```javascript
ai_llm: "Markkinasignaali"
```

If method IDs are rendered directly, map all visible names to Finnish neutral labels.

- [ ] **Step 3: Remove modelName import usage from normal render tree**

Run:

```bash
python - <<'PY'
from pathlib import Path
for p in Path('frontend/src').rglob('*.js*'):
    t = p.read_text(encoding='utf-8', errors='ignore')
    if 'formatModelName' in t or 'modelName' in t:
        print(p)
PY
```

Expected: no file imported by `App.js` should use `formatModelName`. If only unused `frontend/src/lib/modelName.js` remains, leave it or delete it only after confirming no imports.

---

### Task 7: Add responsive polish and dark/light utilities

**Files:**
- Modify: `frontend/src/App.css`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Append dashboard utilities to App.css**

Append:

```css
.dashboard-section {
  scroll-margin-top: 5rem;
}

.summary-strip-card {
  min-height: 7.25rem;
}

.skeleton-line {
  border-radius: 999px;
  background: rgba(var(--c-line), 0.85);
}

@media (max-width: 767px) {
  .app-shell header {
    position: sticky;
  }
}
```

- [ ] **Step 2: Add dark summary card treatment to index.css**

Append:

```css
.dark .summary-strip-card {
  background: rgba(17, 24, 39, 0.92);
}
```

---

### Task 8: Verification pass

**Files:**
- Inspect all changed frontend files

- [ ] **Step 1: Run helper tests**

Run:

```bash
yarn --cwd frontend test --watchAll=false --runTestsByPath src/lib/dashboard.test.js
```

Expected: PASS.

- [ ] **Step 2: Run production build**

Run:

```bash
yarn --cwd frontend build
```

Expected: PASS.

- [ ] **Step 3: Run user-facing AI/model branding grep**

Run:

```bash
python - <<'PY'
from pathlib import Path
terms = ['AI', 'ai_llm', 'Codex', 'Claude', 'LLM', 'modelName', 'tekoäly']
allowed = {
    Path('frontend/src/components/AiAnalysis.jsx'),
    Path('frontend/src/components/MethodTable.jsx'),
    Path('frontend/src/lib/modelName.js'),
}
for path in Path('frontend').rglob('*'):
    if path.suffix.lower() not in {'.js', '.jsx', '.html', '.css'}:
        continue
    if path in allowed:
        continue
    text = path.read_text(encoding='utf-8', errors='ignore')
    for term in terms:
        if term.lower() in text.lower():
            print(f'{path}: contains {term}')
PY
```

Expected: no output for files in the normal render path. Remove or neutralize any hits in `App.js`, `NewsCard.jsx`, `AccuracyTracker.jsx`, `FactorsCard.jsx`, `public/index.html`, or chart components.

- [ ] **Step 4: Manual browser verification**

Run:

```bash
yarn --cwd frontend start
```

Open the CRA local URL and verify:

- first screen is dashboard content, not landing copy
- fuel toggle works
- theme toggle works
- refresh button shows loading state
- summary strip renders `—` instead of fake data for missing fields
- forecast panel does not mention AI/model/vendor names
- news links open only for valid http/https URLs
- mobile width around 390px is usable
- desktop width around 1440px is usable

Stop the dev server with Ctrl+C.

---

## Self-review notes

Spec coverage:

- Summary-first layout: Tasks 4 and 5.
- Neutral forecast UI: Tasks 3, 4, and 6.
- AI/model cleanup: Tasks 3, 4, 6, and 8 grep.
- API contract preservation: all tasks use existing `api.js`; no backend changes.
- Safe links and production-safe errors: Tasks 1, 2, and 3.
- Responsive/mobile/dark polish: Task 7 and manual verification in Task 8.
- Build/test verification: Task 8.

No intentional placeholders remain. The plan avoids backend changes and avoids fake data.
