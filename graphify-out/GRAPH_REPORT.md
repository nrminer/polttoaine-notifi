# Graph Report - .  (2026-05-22)

## Corpus Check
- Corpus is ~31,723 words - fits in a single context window. You may not need a graph.

## Summary
- 502 nodes · 669 edges · 37 communities (30 shown, 7 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 13 edges (avg confidence: 0.81)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_FastAPI Route Handlers|FastAPI Route Handlers]]
- [[_COMMUNITY_Architecture Docs & Concepts|Architecture Docs & Concepts]]
- [[_COMMUNITY_Design System Guidelines|Design System Guidelines]]
- [[_COMMUNITY_Frontend Build & Dependencies|Frontend Build & Dependencies]]
- [[_COMMUNITY_Prediction Engine|Prediction Engine]]
- [[_COMMUNITY_Frontend App Core|Frontend App Core]]
- [[_COMMUNITY_Scheduled Capture & News Watcher|Scheduled Capture & News Watcher]]
- [[_COMMUNITY_Test Reports & QA Notes|Test Reports & QA Notes]]
- [[_COMMUNITY_Backend Test Suite|Backend Test Suite]]
- [[_COMMUNITY_UI Component Library|UI Component Library]]
- [[_COMMUNITY_Color & Theme Tokens|Color & Theme Tokens]]
- [[_COMMUNITY_Manual Capture Script|Manual Capture Script]]
- [[_COMMUNITY_City Average Chart|City Average Chart]]
- [[_COMMUNITY_GitHub Actions Price Checker|GitHub Actions Price Checker]]
- [[_COMMUNITY_Market Factors Fetcher|Market Factors Fetcher]]
- [[_COMMUNITY_ntfy Notification Publisher|ntfy Notification Publisher]]
- [[_COMMUNITY_Railway Deployment Config|Railway Deployment Config]]
- [[_COMMUNITY_AI Analysis & Method Table UI|AI Analysis & Method Table UI]]
- [[_COMMUNITY_Vercel Deployment Config|Vercel Deployment Config]]
- [[_COMMUNITY_tankille.fi Scraper|tankille.fi Scraper]]
- [[_COMMUNITY_Tax Event Parser|Tax Event Parser]]
- [[_COMMUNITY_Price Learning & Stats|Price Learning & Stats]]
- [[_COMMUNITY_RSS News Aggregator|RSS News Aggregator]]
- [[_COMMUNITY_polttoaine.net Scraper|polttoaine.net Scraper]]
- [[_COMMUNITY_tankille.fi Scraper (root)|tankille.fi Scraper (root)]]
- [[_COMMUNITY_polttoaine.net Scraper (backend)|polttoaine.net Scraper (backend)]]
- [[_COMMUNITY_Capture Purge Utility|Capture Purge Utility]]
- [[_COMMUNITY_Claude Code Settings|Claude Code Settings]]
- [[_COMMUNITY_Fuel Selector Toggle|Fuel Selector Toggle]]
- [[_COMMUNITY_App State Persistence|App State Persistence]]
- [[_COMMUNITY_README|README]]
- [[_COMMUNITY_Emergent Job Config|Emergent Job Config]]
- [[_COMMUNITY_Privacy HTML|Privacy HTML]]

## God Nodes (most connected - your core abstractions)
1. `BensaVahti AI Agent Documentation` - 20 edges
2. `predict_tomorrow()` - 12 edges
3. `server.py — FastAPI All-Routes Backend` - 11 edges
4. `spans` - 9 edges
5. `_daily_tail()` - 9 edges
6. `Card()` - 9 edges
7. `CardLabel()` - 9 edges
8. `main()` - 8 edges
9. `scales` - 8 edges
10. `ai_llm_predict()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `GitHub Actions Cron (check_prices.py every 15 min)` --semantically_similar_to--> `news_watch_loop — Auto AI Re-run on New Fuel News (rate-limited)`  [INFERRED] [semantically similar]
  .github/workflows/check.yml → CLAUDE.md
- `ai_llm_predict()` --calls--> `type`  [INFERRED]
  backend/predict.py → design_guidelines.json
- `admin_run()` --calls--> `type`  [INFERRED]
  backend/server.py → design_guidelines.json
- `Backend Python Dependencies` --references--> `server.py — FastAPI All-Routes Backend`  [INFERRED]
  backend/requirements.txt → CLAUDE.md
- `main()` --calls--> `type`  [INFERRED]
  backend/capture_now.py → design_guidelines.json

## Hyperedges (group relationships)
- **Full Prediction Pipeline: daily_tracker + factors + news → predict_py → ensemble → predictions collection** — concept_daily_tracker_collection, concept_factors_py, concept_news_py, concept_predict_py, concept_prediction_ensemble, concept_predictions_collection [EXTRACTED 0.95]
- **Scraper Sanity + Merge Flow: tankille_scraper + polttoaine_scraper + sanity_filter → snapshots** — concept_tankille_scraper, concept_polttoaine_scraper, concept_sanity_filter, concept_snapshots_collection [EXTRACTED 0.95]
- **Scheduled Capture + Notify Cycle: tracker_py captures → daily_tracker + predict → ntfy notification** — concept_tracker_py, concept_daily_tracker_collection, concept_predict_py, concept_notify_py, concept_ntfy_notification [EXTRACTED 0.90]

## Communities (37 total, 7 thin omitted)

### Community 0 - "FastAPI Route Handlers"
Cohesion: 0.05
Nodes (40): accuracy(), admin_run(), AdminRequest, _check_admin(), _city_aggregate(), current_prices(), _filter_to_allowed(), get_factors() (+32 more)

### Community 1 - "Architecture Docs & Concepts"
Cohesion: 0.08
Nodes (48): Backend Python Dependencies, BensaVahti AI Agent Documentation, AccuracyTracker.jsx — Historical Prediction Accuracy MAE, ADMIN_TOKEN Password-Protected Admin Endpoint, AI LLM Predict Method (Claude Opus 4.7 with geopolitical risk), AiAnalysis.jsx — Claude Analysis Card, api.js — Axios HTTP Contract Wrappers, App.js — React Main Page Component (~665 lines) (+40 more)

### Community 2 - "Design System Guidelines"
Cohesion: 0.05
Nodes (38): archetype, components, interactive, surfaces, design_philosophy, container, item, body (+30 more)

### Community 3 - "Frontend Build & Dependencies"
Cohesion: 0.07
Nodes (28): browserslist, development, production, dependencies, axios, class-variance-authority, clsx, framer-motion (+20 more)

### Community 4 - "Prediction Engine"
Cohesion: 0.16
Nodes (24): ai_llm_predict(), _bias_correction(), _calibrated_weights(), _daily_tail(), ensemble(), exp_smoothing(), fundamental_anchor(), linear_regression() (+16 more)

### Community 5 - "Frontend App Core"
Cohesion: 0.12
Nodes (17): api, fetchAccuracy(), fetchCurrent(), fetchFactors(), fetchHistory(), fetchLatestPrediction(), fetchNews(), fetchRegional() (+9 more)

### Community 6 - "Scheduled Capture & News Watcher"
Cohesion: 0.12
Nodes (21): capture_daily(), _city_breakdown(), _news_signature(), news_watch_loop(), next_18_helsinki(), next_scheduled_run(), Daily prediction-vs-actual tracker.  Every day at 14:00 and 21:00 Helsinki tim, Run both scrapers in parallel. Returns national cheapest station info     plus (+13 more)

### Community 7 - "Test Reports & QA Notes"
Cohesion: 0.09
Nodes (21): action_items, backend_issues, critical, minor, context_for_next_testing_agent, critical_code_review_comments, frontend_issues, design_issues (+13 more)

### Community 8 - "Backend Test Suite"
Cohesion: 0.09
Nodes (7): BensaVahti backend API tests.  Covers all endpoints in /app/backend/server.py:, May take 15-30s due to scraping; allow long timeout., Runs all 4 algorithms + ensemble; can take 5-30s due to AI call., Verify the prediction we just ran is now in /predict/latest., test_current_prices_95E10(), test_predict_latest_after_run(), test_predict_run_95E10()

### Community 9 - "UI Component Library"
Cohesion: 0.16
Nodes (10): METHOD_COLOR, METHOD_LABEL, Card(), CardLabel(), DeltaBadge(), StatNumber(), AgeBadge(), ageLabel() (+2 more)

### Community 10 - "Color & Theme Tokens"
Cohesion: 0.10
Nodes (21): dark_accent, default, muted, subtle, accent, primary, primary_hover, colors (+13 more)

### Community 11 - "Manual Capture Script"
Cohesion: 0.11
Nodes (18): main(), Manuaalinen capture NYT — skrapaa tämänhetkiset hinnat ja TALLENTAA ne pysyvästi, base_classes, spans, type, layout, grid, spacing (+10 more)

### Community 12 - "City Average Chart"
Cohesion: 0.14
Nodes (9): CITIES, CITY_COLOR, TooltipBody(), TooltipBody(), fmtDateFi(), fmtDateTimeFi(), fmtDelta(), App() (+1 more)

### Community 13 - "GitHub Actions Price Checker"
Cohesion: 0.18
Nodes (15): build_digest(), cheapest_any(), cheapest_in(), fingerprint(), gather(), load_config(), load_state(), main() (+7 more)

### Community 14 - "Market Factors Fetcher"
Cohesion: 0.15
Nodes (14): brent_eur_per_l(), change_frac(), crack_spread_eur_per_l(), fetch_brent(), fetch_eur_usd(), fetch_product_for_fuel(), product_eur_per_l(), Vaikuttavat tekijät: Brent-raakaöljy, EUR/USD-kurssi ja JALOSTETTUJEN TUOTTEIDE (+6 more)

### Community 15 - "ntfy Notification Publisher"
Cohesion: 0.20
Nodes (15): _brand_of(), build_detailed_message(), _cheapest_by_brand_in_city(), _cheapest_in_city(), _config(), _format_city_block(), _format_fuel_section(), ntfy.sh push notifications for BensaVahti daily summaries.  Format (matches us (+7 more)

### Community 16 - "Railway Deployment Config"
Cohesion: 0.18
Nodes (10): build, buildCommand, builder, deploy, healthcheckPath, healthcheckTimeout, restartPolicyMaxRetries, restartPolicyType (+2 more)

### Community 17 - "AI Analysis & Method Table UI"
Cohesion: 0.27
Nodes (7): AiAnalysis(), aiLabelFor(), META, METHOD_COLORS, MethodTable(), formatModelName(), fmtPrice()

### Community 18 - "Vercel Deployment Config"
Cohesion: 0.18
Nodes (10): buildCommand, cleanUrls, devCommand, framework, headers, installCommand, outputDirectory, rewrites (+2 more)

### Community 19 - "tankille.fi Scraper"
Cohesion: 0.43
Nodes (6): fetch_prices(), _parse_price(), Scraper for tankille.fi per-city public pages, e.g. www.tankille.fi/helsinki/, _scrape_city(), _freshness_hours(), Arvioi tankille.fi:n päivitystekstistä iän tunteina.      Esimerkkejä:

### Community 20 - "Tax Event Parser"
Cohesion: 0.38
Nodes (6): applicable_step(), _parse(), Tunnetut polttoaineverojen / ALV:n muutokset Suomessa.  Veromuutokset ovat AINA, Palauta { 'delta_eur_per_l': float, 'effective_date': str, 'note': str }     jos, Listaa tulevat veromuutokset ikkunassa (today, today+lookahead].     Käytetään A, upcoming()

### Community 21 - "Price Learning & Stats"
Cohesion: 0.40
Nodes (5): "Self-training" -kerros: lue aiemmat ennusteet + toteutuneet hinnat suoraan tiet, {n, mae, bias, rmse}. bias = signed mean (pred − actual); positiivinen     = mal, Lue viimeisen `days` päivän tallennetut ennusteet ja kelaa läpi     jokainen men, _stats(), track_record()

### Community 22 - "RSS News Aggregator"
Cohesion: 0.50
Nodes (4): fetch_news(), _parse_rss(), Real-time Finnish fuel + oil news via direct publisher RSS feeds.  We pull fro, queries argumentti säilytetty allekirjoituksen yhteensopivuuden vuoksi     mutt

### Community 23 - "polttoaine.net Scraper"
Cohesion: 0.50
Nodes (4): fetch_prices(), _parse_price(), Scraper for polttoaine.net - the "20 cheapest" page, per fuel kind. The site is, Returns up to 20 cheapest stations for the given fuel kind.

### Community 24 - "tankille.fi Scraper (root)"
Cohesion: 0.60
Nodes (4): fetch_prices(), _parse_price(), Scraper for tankille.fi per-city public pages, e.g. www.tankille.fi/helsinki/, _scrape_city()

### Community 25 - "polttoaine.net Scraper (backend)"
Cohesion: 0.67
Nodes (3): fetch_prices(), _parse_price(), Scraper for polttoaine.net - the "20 cheapest" page, per fuel kind. The site is

## Knowledge Gaps
- **136 isolated node(s):** `theme`, `archetype`, `design_philosophy`, `default`, `subtle` (+131 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `type` connect `Manual Capture Script` to `FastAPI Route Handlers`, `Prediction Engine`?**
  _High betweenness centrality (0.049) - this node is a cross-community bridge._
- **Why does `layout` connect `Manual Capture Script` to `Design System Guidelines`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **What connects `Polttoaine Notifi — digest with change detection.  Each run:   - Scrapes 95E10 a`, `Returns {source_name: cheapest_row_in_city} — used for cross-source validation.`, `Only the cheapest *price* per slot — station identity is ignored.` to the rest of the system?**
  _216 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `FastAPI Route Handlers` be split into smaller, more focused modules?**
  _Cohesion score 0.05102040816326531 - nodes in this community are weakly interconnected._
- **Should `Architecture Docs & Concepts` be split into smaller, more focused modules?**
  _Cohesion score 0.08244680851063829 - nodes in this community are weakly interconnected._
- **Should `Design System Guidelines` be split into smaller, more focused modules?**
  _Cohesion score 0.05128205128205128 - nodes in this community are weakly interconnected._
- **Should `Frontend Build & Dependencies` be split into smaller, more focused modules?**
  _Cohesion score 0.06896551724137931 - nodes in this community are weakly interconnected._