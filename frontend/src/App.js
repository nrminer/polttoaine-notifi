import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BarChart3,
  Clock3,
  Database,
  Fuel,
  Gauge,
  Globe2,
  History,
  MapPin,
  Moon,
  Newspaper,
  RefreshCw,
  ShieldCheck,
  Sun,
} from "lucide-react";

import "./App.css";
import AccuracyTracker from "./components/AccuracyTracker";
import AiAnalysis from "./components/AiAnalysis";
import CityOverview from "./components/CityOverview";
import FactorsCard from "./components/FactorsCard";
import FuelPumpCalculator from "./components/FuelPumpCalculator";
import FuelToggle from "./components/FuelToggle";
import MethodTable from "./components/MethodTable";
import NewsCard from "./components/NewsCard";
import RegionalGrid from "./components/RegionalGrid";
import TrackingChart from "./components/TrackingChart";
import {
  fetchAccuracy,
  fetchCurrent,
  fetchFactors,
  fetchLatestPrediction,
  fetchNews,
  fetchRegional,
  fetchTrackHistory,
} from "./lib/api";
import { CITIES, DEFAULT_CITY, storedCity } from "./lib/cities";
import { fmtDateFi, fmtDateTimeFi, fmtPrice } from "./lib/utils";


const HOME_CITY_KEY = "bensavahti-home-city";
const RANGES = [14, 30, 90];
const SLOTS = [
  { value: "all", label: "Molemmat" },
  { value: 14, label: "14:00" },
  { value: 21, label: "21:00" },
];
const DETAIL_TABS = [
  { id: "basis", label: "Perusteet", Icon: Database },
  { id: "accuracy", label: "Tarkkuus", Icon: ShieldCheck },
  { id: "markets", label: "Markkinat", Icon: Activity },
  { id: "news", label: "Uutiset", Icon: Newspaper },
];

function resultValue(result) {
  return result.status === "fulfilled" ? result.value.data : null;
}

function mergeNews(predictionItems = [], liveItems = []) {
  const seen = new Set();
  return [...predictionItems, ...liveItems].filter((item) => {
    const key = String(item?.link || item?.title || "").trim().toLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 12);
}

function SectionHeader({ kicker, title, description, action }) {
  return (
    <header className="section-header">
      <div>
        <span className="section-kicker">{kicker}</span>
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {action}
    </header>
  );
}

function SegmentedControl({ label, options, value, onChange, testIdPrefix }) {
  return (
    <div className="segmented-control" role="group" aria-label={label}>
      {options.map((option) => {
        const optionValue = typeof option === "object" ? option.value : option;
        const optionLabel = typeof option === "object" ? option.label : `${option} pv`;
        return (
          <button
            key={optionValue}
            type="button"
            aria-pressed={value === optionValue}
            className={value === optionValue ? "is-active" : ""}
            onClick={() => onChange(optionValue)}
            data-testid={`${testIdPrefix}-${optionValue}`}
          >
            {optionLabel}
          </button>
        );
      })}
    </div>
  );
}

export default function App() {
  const [fuel, setFuel] = useState("95E10");
  const [homeCity, setHomeCity] = useState(() => {
    if (typeof window === "undefined") return DEFAULT_CITY;
    try {
      return storedCity(window.localStorage.getItem(HOME_CITY_KEY));
    } catch {
      return DEFAULT_CITY;
    }
  });
  const [theme, setTheme] = useState(() => {
    if (typeof window === "undefined") return "light";
    const saved = window.localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  const [refreshKey, setRefreshKey] = useState(0);
  const [chartRange, setChartRange] = useState(30);
  const [chartSlot, setChartSlot] = useState("all");
  const [detailTab, setDetailTab] = useState("basis");

  const [current, setCurrent] = useState(null);
  const [regional, setRegional] = useState(null);
  const [tracking, setTracking] = useState(null);
  const [cityPrediction, setCityPrediction] = useState(null);
  const [cityAccuracy, setCityAccuracy] = useState(null);
  const [nationalPrediction, setNationalPrediction] = useState(null);
  const [nationalAccuracy, setNationalAccuracy] = useState(null);
  const [factors, setFactors] = useState(null);
  const [news, setNews] = useState([]);
  const [loading, setLoading] = useState({ primary: true, city: true, context: true });
  const [errors, setErrors] = useState({});

  useEffect(() => {
    const dark = theme === "dark";
    document.documentElement.classList.toggle("dark", dark);
    try {
      window.localStorage.setItem("theme", theme);
    } catch {
      // Storage may be unavailable in private browsing modes.
    }
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", dark ? "#0b0e0d" : "#f3f5f4");
  }, [theme]);

  useEffect(() => {
    try {
      window.localStorage.setItem(HOME_CITY_KEY, homeCity);
    } catch {
      // Storage may be unavailable in private browsing modes.
    }
  }, [homeCity]);

  useEffect(() => {
    let ignore = false;
    setLoading((state) => ({ ...state, primary: true }));
    setErrors((state) => ({
      ...state,
      current: false,
      regional: false,
      tracking: false,
      nationalPrediction: false,
      nationalAccuracy: false,
    }));

    Promise.allSettled([
      fetchCurrent(fuel),
      fetchRegional(fuel),
      fetchTrackHistory(fuel, 90),
      fetchLatestPrediction(fuel, "Suomi"),
      fetchAccuracy(fuel, "Suomi", 30),
    ]).then((results) => {
      if (ignore) return;
      const [currentResult, regionalResult, trackingResult, predictionResult, accuracyResult] = results;
      if (currentResult.status === "fulfilled") setCurrent(resultValue(currentResult));
      if (regionalResult.status === "fulfilled") setRegional(resultValue(regionalResult));
      if (trackingResult.status === "fulfilled") setTracking(resultValue(trackingResult));
      if (predictionResult.status === "fulfilled") {
        const data = resultValue(predictionResult);
        setNationalPrediction(data?.available ? data : null);
      }
      if (accuracyResult.status === "fulfilled") setNationalAccuracy(resultValue(accuracyResult));
      setErrors((state) => ({
        ...state,
        current: currentResult.status === "rejected",
        regional: regionalResult.status === "rejected",
        tracking: trackingResult.status === "rejected",
        nationalPrediction: predictionResult.status === "rejected",
        nationalAccuracy: accuracyResult.status === "rejected",
      }));
      setLoading((state) => ({ ...state, primary: false }));
    });
    return () => { ignore = true; };
  }, [fuel, refreshKey]);

  useEffect(() => {
    let ignore = false;
    setLoading((state) => ({ ...state, city: true }));
    setErrors((state) => ({ ...state, cityPrediction: false, cityAccuracy: false }));
    Promise.allSettled([
      fetchLatestPrediction(fuel, homeCity),
      fetchAccuracy(fuel, homeCity, 30),
    ]).then((results) => {
      if (ignore) return;
      const [predictionResult, accuracyResult] = results;
      if (predictionResult.status === "fulfilled") {
        const data = resultValue(predictionResult);
        setCityPrediction(data?.available ? data : null);
      } else {
        setCityPrediction(null);
      }
      if (accuracyResult.status === "fulfilled") setCityAccuracy(resultValue(accuracyResult));
      setErrors((state) => ({
        ...state,
        cityPrediction: predictionResult.status === "rejected",
        cityAccuracy: accuracyResult.status === "rejected",
      }));
      setLoading((state) => ({ ...state, city: false }));
    });
    return () => { ignore = true; };
  }, [fuel, homeCity, refreshKey]);

  useEffect(() => {
    let ignore = false;
    setLoading((state) => ({ ...state, context: true }));
    setErrors((state) => ({ ...state, factors: false, news: false }));
    Promise.allSettled([fetchFactors(), fetchNews(30, 15)]).then((results) => {
      if (ignore) return;
      const [factorResult, newsResult] = results;
      if (factorResult.status === "fulfilled") setFactors(resultValue(factorResult));
      if (newsResult.status === "fulfilled") setNews(resultValue(newsResult)?.items || []);
      setErrors((state) => ({
        ...state,
        factors: factorResult.status === "rejected",
        news: newsResult.status === "rejected",
      }));
      setLoading((state) => ({ ...state, context: false }));
    });
    return () => { ignore = true; };
  }, [refreshKey]);

  const activeCurrent = current?.fuel === fuel ? current : null;
  const activeRegional = regional?.fuel === fuel ? regional : null;
  const activeTracking = tracking?.fuel === fuel ? tracking : null;
  const activeCityPrediction = cityPrediction?.fuel === fuel && cityPrediction?.region === homeCity
    ? cityPrediction : null;
  const activeNationalPrediction = nationalPrediction?.fuel === fuel && nationalPrediction?.region === "Suomi"
    ? nationalPrediction : null;
  const activeCityAccuracy = !errors.cityAccuracy && cityAccuracy?.fuel === fuel && cityAccuracy?.region === homeCity
    ? cityAccuracy : null;
  const activeNationalAccuracy = nationalAccuracy?.fuel === fuel && nationalAccuracy?.region === "Suomi"
    ? nationalAccuracy : null;
  const snapshot = activeCurrent?.stale ? null : activeCurrent?.by_city?.[homeCity];
  const liveCity = activeRegional?.rows?.find((row) => row.region === homeCity && row.fresh && row.price != null);
  const cityPrice = liveCity?.price ?? snapshot?.min ?? null;
  const cityStation = liveCity?.station ?? snapshot?.station_min ?? null;
  const cityAddress = liveCity?.address ?? snapshot?.address_min ?? null;
  const cityAge = liveCity?.age_hours ?? snapshot?.sources?.[0]?.age_hours ?? null;
  const citySource = liveCity?.source ?? snapshot?.sources?.[0]?.source ?? null;
  const citySources = snapshot?.sources || [];
  const nationalMin = activeCurrent?.national_min ?? null;
  const nationalForecast = activeNationalPrediction?.ensemble?.value ?? null;
  const nationalChallenger = activeNationalPrediction?.challenger_ensemble?.value ?? null;

  const filteredRows = useMemo(() => {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - chartRange);
    const cutoffText = cutoff.toISOString().slice(0, 10);
    return (activeTracking?.rows || []).filter((row) => (
      row.date >= cutoffText && (chartSlot === "all" || (row.hour ?? 21) === chartSlot)
    ));
  }, [activeTracking?.rows, chartRange, chartSlot]);

  const trendSummary = useMemo(() => {
    const points = filteredRows
      .map((row) => row.by_city?.[homeCity]?.cheapest)
      .filter((value) => Number.isFinite(Number(value)))
      .map(Number);
    if (points.length < 2) return "Hintatrendi odottaa vähintään kahta mittausta.";
    const delta = points[points.length - 1] - points[0];
    if (Math.abs(delta) < 0.001) return `Hinta on pysynyt vakaana ${points.length} mittauksen ajan.`;
    return `Halvin hinta on ${delta > 0 ? "noussut" : "laskenut"} ${Math.abs(delta * 100).toFixed(1)} snt/l valitulla jaksolla.`;
  }, [filteredRows, homeCity]);

  const displayedNews = useMemo(
    () => mergeNews(activeNationalPrediction?.news_headlines || [], news),
    [activeNationalPrediction?.news_headlines, news]
  );
  const cheapestCity = activeRegional?.rows
    ?.filter((row) => row.price != null)
    .sort((a, b) => a.price - b.price)[0]?.region;
  const latestTime = activeRegional?.fetched_at || activeCurrent?.fetched_at;
  const isLoading = Object.values(loading).some(Boolean);

  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">Siirry sisältöön</a>

      <header className="app-header">
        <div className="app-header__inner">
          <a className="brand-lockup" href="#now" aria-label="BensaVahti, nykytilanne">
            <Fuel size={20} />
            <span><strong>BensaVahti</strong><small>Tuoreet polttoainehinnat</small></span>
          </a>

          <nav className="top-nav" aria-label="Päänavigaatio">
            <a href="#now">Nyt</a>
            <a href="#cities">Kaupungit</a>
            <a href="#history">Historia</a>
            <a href="#background">Taustat</a>
          </nav>

          <div className="header-controls">
            <label className="city-select">
              <MapPin size={16} aria-hidden="true" />
              <span className="sr-only">Kotikaupunki</span>
              <select value={homeCity} onChange={(event) => setHomeCity(event.target.value)} data-testid="home-city-select">
                {CITIES.map((city) => <option value={city} key={city}>{city}</option>)}
              </select>
            </label>
            <FuelToggle value={fuel} onChange={setFuel} />
            <span className="header-freshness"><Clock3 size={15} />{latestTime ? fmtDateTimeFi(latestTime) : "ei päivitystä"}</span>
            <button type="button" className="icon-button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Vaihda teemaa">
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button type="button" className="icon-button" onClick={() => setRefreshKey((value) => value + 1)} disabled={isLoading} aria-label="Päivitä tiedot" data-testid="refresh-prices-btn">
              <RefreshCw size={18} className={isLoading ? "spin" : ""} />
            </button>
          </div>
        </div>
      </header>

      <main id="main" className="dashboard-shell">
        <CityOverview
          city={homeCity}
          fuel={fuel}
          price={cityPrice}
          average={snapshot?.mean}
          station={cityStation}
          address={cityAddress}
          ageHours={cityAge}
          source={citySource}
          sources={citySources}
          stationCount={snapshot?.count}
          prediction={activeCityPrediction}
          accuracy={activeCityAccuracy}
          loading={loading.primary || loading.city}
          error={cityPrice == null && (errors.current || errors.regional)}
          predictionError={errors.cityPrediction}
        />

        <div id="cities" className="section-anchor">
          <RegionalGrid
            data={activeRegional}
            fuel={fuel}
            cityData={activeCurrent?.stale ? null : activeCurrent?.by_city}
            selectedCity={homeCity}
            onSelectCity={setHomeCity}
            loading={loading.primary}
            error={errors.regional}
          />
        </div>

        <section id="history" className="dashboard-section">
          <SectionHeader
            kicker="Historia"
            title={`${homeCity}: halvin ja keskihinta`}
            description={errors.tracking ? "Hintahistoriaa ei saatu ladattua." : trendSummary}
            action={<span className="section-status"><History size={15} /> Mittaukset klo 14 ja 21</span>}
          />
          <div className="chart-toolbar">
            <SegmentedControl label="Aikajakso" options={RANGES} value={chartRange} onChange={setChartRange} testIdPrefix="chart-range" />
            <SegmentedControl label="Mittausaika" options={SLOTS} value={chartSlot} onChange={setChartSlot} testIdPrefix="chart-slot" />
          </div>
          <div className="chart-panel" data-testid="tracking-chart-card">
            <TrackingChart rows={filteredRows} city={homeCity} />
          </div>
        </section>

        <section className="national-outlook" aria-label="Valtakunnallinen huomisen näkymä">
          <SectionHeader
            kicker="Koko Suomi"
            title="Valtakunnallinen huomisen näkymä"
            description="Tämä osio ei kuvaa valitun kaupungin paikallista hintaa."
          />
          <div className="national-outlook__metrics">
            <div>
              <span>Halvin nyt</span>
              <strong className="tnum" data-testid="current-min-price">{nationalMin != null ? `${fmtPrice(nationalMin)} €/l` : "-"}</strong>
              <small>{cheapestCity ? `${cheapestCity} johtaa tuoretta otosta` : "kaupunki puuttuu"}</small>
            </div>
            <div>
              <span>Tuotannon vertailutaso</span>
              <strong className="tnum">{nationalForecast != null ? `${fmtPrice(nationalForecast)} €/l` : "-"}</strong>
              <small>{errors.nationalPrediction
                ? "lataus epäonnistui"
                : activeNationalPrediction?.target_date
                ? `${fmtDateFi(activeNationalPrediction.target_date)} klo 21`
                : "ennuste puuttuu"}</small>
            </div>
            <div>
              <span>Mallien haastaja</span>
              <strong className="tnum">{nationalChallenger != null ? `${fmtPrice(nationalChallenger)} €/l` : "-"}</strong>
              <small>Ei tuotannossa ennen mitattua parannusta</small>
            </div>
            <div>
              <span>Mitattu keskivirhe</span>
              <strong className="tnum">
                {activeNationalAccuracy?.summary?.ensemble?.mae != null
                  ? `±${(activeNationalAccuracy.summary.ensemble.mae * 100).toFixed(1)} snt/l`
                  : "-"}
              </strong>
              <small>{activeNationalAccuracy?.summary?.ensemble?.n || 0} vertailua</small>
            </div>
          </div>
        </section>

        <FuelPumpCalculator price={cityPrice} fuel={fuel} city={homeCity} />

        <section id="background" className="dashboard-section diagnostics-section">
          <SectionHeader
            kicker="Taustat"
            title="Perusteet ja seuranta"
            description="Tekniset yksityiskohdat ovat erillään paikallisesta hintanäkymästä."
          />
          <div className="detail-tabs" role="group" aria-label="Taustatiedot">
            {DETAIL_TABS.map(({ id, label, Icon }) => (
              <button
                type="button"
                aria-pressed={detailTab === id}
                className={detailTab === id ? "is-active" : ""}
                onClick={() => setDetailTab(id)}
                key={id}
              >
                <Icon size={16} /> {label}
              </button>
            ))}
          </div>
          <div className="detail-panel">
            {((detailTab === "markets" && errors.factors) || (detailTab === "news" && errors.news)) && (
              <div className="inline-state inline-state--error">Taustatietojen lataus epäonnistui.</div>
            )}
            {detailTab === "basis" && (
              <div className="detail-grid">
                <MethodTable result={activeNationalPrediction} />
                <AiAnalysis
                  ai={activeNationalPrediction?.methods?.ai_llm}
                  brent={activeNationalPrediction?.brent ?? factors?.brent?.latest}
                  eurUsd={activeNationalPrediction?.eur_usd ?? factors?.eur_usd?.latest}
                  anchor={nationalMin}
                />
              </div>
            )}
            {detailTab === "accuracy" && <AccuracyTracker data={activeNationalAccuracy} />}
            {detailTab === "markets" && <FactorsCard factors={factors} prediction={activeNationalPrediction} />}
            {detailTab === "news" && <NewsCard items={displayedNews} />}
          </div>
        </section>
      </main>

      <nav className="mobile-nav" aria-label="Mobiilinavigaatio">
        <a href="#now"><Gauge size={18} />Nyt</a>
        <a href="#cities"><MapPin size={18} />Kaupungit</a>
        <a href="#history"><BarChart3 size={18} />Historia</a>
        <a href="#background"><Globe2 size={18} />Taustat</a>
      </nav>

      <footer className="app-footer">
        <span>BensaVahti</span>
        <span>polttoaine.net · tankille.fi · Yahoo Finance · RSS</span>
        <a href="/privacy.html">Tietosuoja</a>
      </footer>
    </div>
  );
}
