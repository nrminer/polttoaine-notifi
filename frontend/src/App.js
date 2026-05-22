import React, { useEffect, useMemo, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Fuel,
  Gauge,
  Sparkles,
  RefreshCw,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Clock,
  Globe,
  Sun,
  Moon,
} from "lucide-react";

import "./App.css";
import { Card, CardLabel, StatNumber, DeltaBadge } from "./components/Card";
import FuelToggle from "./components/FuelToggle";
import TrackingChart from "./components/TrackingChart";
import CityAverageChart from "./components/CityAverageChart";
import MethodTable from "./components/MethodTable";
import AiAnalysis from "./components/AiAnalysis";
import RegionalGrid from "./components/RegionalGrid";
import AccuracyTracker from "./components/AccuracyTracker";
import FactorsCard from "./components/FactorsCard";
import {
  fetchCurrent,
  fetchHistory,
  fetchFactors,
  runPrediction,
  fetchLatestPrediction,
  fetchRegional,
  fetchAccuracy,
  fetchNews,
  fetchTrackHistory,
  runTrackCapture,
  seedHistory,
} from "./lib/api";
import { fmtDateTimeFi, fmtDateFi } from "./lib/utils";
import { formatModelName } from "./lib/modelName";
import NewsCard from "./components/NewsCard";

const RANGE_OPTIONS = [
  { value: 30, label: "30 PV" },
  { value: 90, label: "90 PV" },
  { value: 365, label: "1 V" },
];

const CHART_CITIES = [
  "Suomi",
  "Helsinki",
  "Espoo",
  "Vantaa",
  "Tampere",
  "Turku",
  "Lahti",
];
const CHART_RANGES = [
  { value: 14, label: "14 PV" },
  { value: 30, label: "30 PV" },
  { value: 90, label: "Kaikki" },
];
const CHART_SLOTS = [
  { value: "all", label: "Molemmat" },
  { value: 14, label: "14:00" },
  { value: 21, label: "21:00" },
];

/* Reusable filter button used in chart controls.
   h-9 (36px) + py implicit hit area pushes effective tap target near 44px;
   on touch devices users get the bigger area without visual bulk. */
function FilterBtn({ active, onClick, children, testId }) {
  return (
    <button
      data-testid={testId}
      onClick={onClick}
      type="button"
      className={`px-3 h-9 min-w-[2.5rem] font-mono text-[11px] font-semibold rounded-md border transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60 focus-visible:ring-offset-1 ${
        active
          ? "bg-brand text-white border-brand shadow-sm"
          : "bg-transparent text-secondary border-line hover:border-brand/50 hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}

/* Method abbreviations used in the dark hero prediction card.
   Kept short on purpose — the dark card needs to feel like a terminal,
   not a marketing paragraph. */
const DARK_METHODS = [
  { key: "fundamental_anchor", label: "ANKKURI" },
  { key: "ai_llm",             label: "AI" },
  { key: "exp_smoothing",      label: "HOLT" },
  { key: "linear_regression",  label: "REGR." },
  { key: "moving_average",     label: "MA·7" },
];

function deltaColorDark(d) {
  if (d == null) return "text-slate-500";
  if (d > 0.0005)  return "text-red-300";
  if (d < -0.0005) return "text-emerald-300";
  return "text-slate-400";
}
function deltaFmtMilli(d) {
  if (d == null) return "—";
  const v = d * 1000;
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  return `${sign}${Math.abs(v).toFixed(1)} m€`;
}

export default function App() {
  const [fuel, setFuel] = useState("95E10");
  const [range, setRange] = useState(90);
  const [current, setCurrent] = useState(null);
  const [history, setHistory] = useState([]);
  const [factors, setFactors] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [regional, setRegional] = useState(null);
  const [accuracy, setAccuracy] = useState(null);
  const [news, setNews] = useState([]);
  const [tracking, setTracking] = useState(null);
  const [chartCity, setChartCity] = useState("Suomi");
  const [chartRange, setChartRange] = useState(90);
  const [chartSlot, setChartSlot] = useState("all");
  const [loading, setLoading] = useState({});
  const [seeded, setSeeded] = useState(false);
  const [error, setError] = useState(null);
  const [theme, setTheme] = useState(() => {
    if (typeof window === "undefined") return "dark";
    const t = window.localStorage.getItem("theme");
    return t === "light" || t === "dark" ? t : "dark";
  });

  useEffect(() => {
    const isDark = theme === "dark";
    document.documentElement.classList.toggle("dark", isDark);
    try {
      window.localStorage.setItem("theme", theme);
    } catch (e) {
      /* ignore quota / privacy-mode errors */
    }
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", isDark ? "#0A0F1C" : "#FFFFFF");
  }, [theme]);

  const toggleTheme = useCallback(
    () => setTheme((t) => (t === "dark" ? "light" : "dark")),
    []
  );

  const setLoad = (k, v) => setLoading((s) => ({ ...s, [k]: v }));

  const ensureSeeded = useCallback(async () => {
    try {
      await seedHistory(180, false);
      setSeeded(true);
    } catch (e) {
      setSeeded(true);
    }
  }, []);

  const loadCurrent = useCallback(async (f) => {
    setLoad("current", true);
    try {
      const { data } = await fetchCurrent(f);
      setCurrent(data);
    } catch (e) {
      console.warn("current failed", e);
    } finally {
      setLoad("current", false);
    }
  }, []);

  const loadHistory = useCallback(async (f, r) => {
    setLoad("history", true);
    try {
      const { data } = await fetchHistory(f, "Suomi", r);
      setHistory(data.rows || []);
    } catch (e) {
      console.warn("history failed", e);
    } finally {
      setLoad("history", false);
    }
  }, []);

  const loadFactors = useCallback(async () => {
    setLoad("factors", true);
    try {
      const { data } = await fetchFactors();
      setFactors(data);
    } catch (e) {
      console.warn("factors failed", e);
    } finally {
      setLoad("factors", false);
    }
  }, []);

  const loadPrediction = useCallback(async (f, fresh = false) => {
    setLoad("prediction", true);
    try {
      if (fresh) {
        const { data } = await runPrediction(f, "Suomi");
        setPrediction(data);
      } else {
        const { data } = await fetchLatestPrediction(f, "Suomi");
        if (data.available) {
          setPrediction({
            fuel: data.fuel,
            region: data.region,
            generated_at: data.generated_at,
            target_date: data.target_date,
            current_price: data.current_price,
            live_anchor: data.live_anchor,
            ensemble: data.ensemble,
            methods: data.methods,
            brent: data.brent,
            eur_usd: data.eur_usd,
            data_sources: data.data_sources,
            // rikkaampi konteksti (taustamuuttujat + self-training)
            conflict_signal: data.conflict_signal,
            n_daily_points: data.n_daily_points,
            product_label: data.product_label,
            product_usd_gal: data.product_usd_gal,
            product_chg: data.product_chg,
            crack_eur_l: data.crack_eur_l,
            tax_events: data.tax_events,
            tax_step_eur_l: data.tax_step_eur_l,
            self_training: data.self_training,
            news_headlines: data.news_headlines,
          });
        } else {
          setPrediction(null);
        }
      }
    } catch (e) {
      console.warn("prediction failed", e);
      setError(e.response?.data?.detail || "Ennusteen ajaminen epäonnistui");
    } finally {
      setLoad("prediction", false);
    }
  }, []);

  const loadRegional = useCallback(async (f) => {
    setLoad("regional", true);
    try {
      const { data } = await fetchRegional(f);
      setRegional(data);
    } catch (e) {
      console.warn("regional failed", e);
    } finally {
      setLoad("regional", false);
    }
  }, []);

  const loadAccuracy = useCallback(async (f) => {
    setLoad("accuracy", true);
    try {
      const { data } = await fetchAccuracy(f, "Suomi", 30);
      setAccuracy(data);
    } catch (e) {
      console.warn("accuracy failed", e);
    } finally {
      setLoad("accuracy", false);
    }
  }, []);

  const loadNews = useCallback(async () => {
    setLoad("news", true);
    try {
      const { data } = await fetchNews(30, 8);
      setNews(data.items || []);
    } catch (e) {
      console.warn("news failed", e);
    } finally {
      setLoad("news", false);
    }
  }, []);

  const loadTracking = useCallback(async (f) => {
    setLoad("tracking", true);
    try {
      const { data } = await fetchTrackHistory(f, 90);
      setTracking(data);
    } catch (e) {
      console.warn("tracking failed", e);
    } finally {
      setLoad("tracking", false);
    }
  }, []);

  const captureToday = useCallback(async () => {
    setLoad("capture", true);
    try {
      await runTrackCapture(fuel);
      await loadTracking(fuel);
    } catch (e) {
      console.warn("capture failed", e);
    } finally {
      setLoad("capture", false);
    }
  }, [fuel, loadTracking]);

  useEffect(() => {
    (async () => {
      await ensureSeeded();
      await Promise.all([
        loadCurrent(fuel),
        loadHistory(fuel, range),
        loadFactors(),
        loadPrediction(fuel, false),
        loadRegional(fuel),
        loadAccuracy(fuel),
        loadNews(),
        loadTracking(fuel),
      ]);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!seeded) return;
    (async () => {
      await Promise.all([
        loadCurrent(fuel),
        loadHistory(fuel, range),
        loadPrediction(fuel, false),
        loadRegional(fuel),
        loadAccuracy(fuel),
        loadTracking(fuel),
      ]);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fuel]);

  useEffect(() => {
    if (!seeded) return;
    loadHistory(fuel, range);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range]);

  const handleRefreshAll = async () => {
    setError(null);
    await Promise.all([
      loadCurrent(fuel),
      loadHistory(fuel, range),
      loadFactors(),
      loadRegional(fuel),
      loadTracking(fuel),
      loadNews(),
    ]);
  };

  const todayMin = current?.national_min;
  const cheapAvg = current?.cheap_sample_avg;
  const tomorrowCheapest = tracking?.summary?.tomorrow_prediction;
  const cheapestDelta = useMemo(() => {
    if (todayMin == null) return null;
    const rows = tracking?.rows || [];
    if (rows.length < 2) return null;
    const prev = rows[rows.length - 2];
    if (prev?.actual_cheapest == null) return null;
    return todayMin - prev.actual_cheapest;
  }, [todayMin, tracking]);
  const yesterdayPrice = useMemo(() => {
    if (!history || history.length < 2) return null;
    const today = new Date().toISOString().slice(0, 10);
    const filtered = history.filter((h) => h.date < today);
    return filtered.length ? filtered[filtered.length - 1].price : null;
  }, [history]);

  const tomorrowVal = tomorrowCheapest;
  const tomorrowDelta = tomorrowVal != null && todayMin != null ? tomorrowVal - todayMin : null;

  const filteredTrackingRows = useMemo(() => {
    const rows = tracking?.rows || [];
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - chartRange);
    const cutoffStr = cutoff.toISOString().slice(0, 10);
    return rows.filter((r) => {
      if (r.date < cutoffStr) return false;
      if (chartSlot !== "all" && (r.hour ?? 20) !== chartSlot) return false;
      return true;
    });
  }, [tracking, chartRange, chartSlot]);

  const isLoading = Object.values(loading).some(Boolean);

  return (
    <div className="app-shell relative">
      <a href="#main-content" className="skip-link">
        Siirry pääsisältöön
      </a>
      {/* TOP BAR */}
      <header className="border-b border-line bg-white/80 backdrop-blur-xl sticky top-0 z-30">
        <div className="max-w-[1480px] mx-auto px-6 md:px-10 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-brand text-white flex items-center justify-center shadow-glow-brand">
              <Fuel size={16} strokeWidth={2.4} />
            </div>
            <div>
              <div className="font-display font-black tracking-tighter text-xl leading-none text-ink">
                BENSAVAHTI
              </div>
              <div className="font-mono text-[11px] text-muted uppercase tracking-[0.18em] mt-1">
                95E10 + Diesel · huominen ennuste
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="hidden md:flex items-center gap-2 px-3 h-9 rounded-lg bg-surface font-mono text-xs text-secondary">
              <Clock size={12} />
              {current?.fetched_at ? fmtDateTimeFi(current.fetched_at) : "—"}
              {current?.stale && (
                <span className="ml-1 bg-amber-100 text-amber-700 px-1.5 py-0.5 text-[11px] rounded-md">
                  CACHED
                </span>
              )}
            </div>
            <button
              data-testid="theme-toggle-btn"
              onClick={toggleTheme}
              type="button"
              aria-label={theme === "dark" ? "Vaalea teema" : "Tumma teema"}
              title={theme === "dark" ? "Vaalea teema" : "Tumma teema"}
              className="inline-flex items-center justify-center w-10 h-10 rounded-lg border border-line hover:bg-surface transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60"
            >
              {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <button
              data-testid="refresh-prices-btn"
              onClick={handleRefreshAll}
              disabled={isLoading}
              type="button"
              className="inline-flex items-center gap-2 px-3 h-10 rounded-lg border border-line hover:bg-surface text-sm font-mono font-semibold transition-colors disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60"
            >
              <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
              Päivitä
            </button>
          </div>
        </div>
      </header>

      {/* HERO */}
      <section
        id="main-content"
        className="max-w-[1480px] mx-auto px-6 md:px-10 pt-10 md:pt-16 pb-8"
      >
        <div className="grid grid-cols-12 gap-6">
          <div className="col-span-12 lg:col-span-7">
            <CardLabel className="mb-3">Suomi · day-ahead pumppuhinta-arvio</CardLabel>
            <h1 className="font-display text-5xl md:text-7xl font-black tracking-tightest leading-[0.95]">
              Huomisen<br />
              hinta <span className="deco-underline">tänään.</span>
            </h1>
            <p className="text-secondary text-base md:text-lg mt-5 max-w-xl leading-relaxed">
              Live capture klo 14 ja 21. Viisi mallia, datalaatupainotettu
              yhdistelmä, ankkuroitu live-hintaan.
            </p>

            {/* Context chips: real numbers, not marketing copy */}
            <div className="mt-5 flex flex-wrap items-center gap-2 font-mono text-[11px]">
              {prediction?.n_daily_points != null && (
                <span className="inline-flex items-center gap-1.5 px-2.5 h-7 rounded-md bg-surface border border-line text-secondary">
                  <span className="text-muted">päivähäntä</span>
                  <span className="text-ink font-semibold tnum">{prediction.n_daily_points} pv</span>
                </span>
              )}
              {current?.stations_count != null && (
                <span className="inline-flex items-center gap-1.5 px-2.5 h-7 rounded-md bg-surface border border-line text-secondary">
                  <span className="text-muted">otanta</span>
                  <span className="text-ink font-semibold tnum">{current.stations_count} as.</span>
                </span>
              )}
              {prediction?.methods?.ai_llm?.model && (
                <span className="inline-flex items-center gap-1.5 px-2.5 h-7 rounded-md bg-surface border border-line text-secondary">
                  <span className="text-muted">ai</span>
                  <span className="text-ink font-semibold">{formatModelName(prediction.methods.ai_llm.model)}</span>
                </span>
              )}
              {prediction?.conflict_signal && (
                <span
                  data-testid="geopol-chip"
                  className="inline-flex items-center gap-1.5 px-2.5 h-7 rounded-md bg-amber-50 dark:bg-amber-500/15 border border-amber-300 dark:border-amber-400/30 text-amber-800 dark:text-amber-200 font-semibold"
                  title="Uutisista poimittu konflikti-/tarjontahäiriösignaali — leveämpi epävarmuusväli."
                >
                  ⚑ geopol. signaali
                </span>
              )}
            </div>

            <div className="mt-7 flex flex-wrap items-center gap-3">
              <FuelToggle value={fuel} onChange={setFuel} />
              <div
                data-testid="auto-schedule-info"
                className="inline-flex items-center gap-2 px-3 h-10 rounded-lg bg-surface text-secondary font-mono text-xs font-semibold border border-line"
              >
                <Clock size={14} />
                Päivittyy klo 14 ja 21 (Helsinki)
              </div>
              {error && (
                <span data-testid="error-banner" className="text-signalUp font-mono text-xs bg-signalUpBg px-2.5 py-1 rounded-md">
                  {error}
                </span>
              )}
            </div>
          </div>

          <div className="col-span-12 lg:col-span-5">
            <Card testId="hero-today-card" className="p-7 h-full">
              <CardLabel className="mb-2">Tänään · halvin asema Suomessa</CardLabel>
              <div className="flex items-end justify-between">
                <StatNumber value={todayMin} testId="today-cheapest-price" />
                <DeltaBadge delta={cheapestDelta} />
              </div>
              <div className="mt-1 text-[11px] font-mono text-secondary line-clamp-1">
                {current?.by_city && Object.entries(current.by_city).sort((a,b)=>a[1].min-b[1].min)[0]?.[0]
                  ? `Halvin kaupunki: ${Object.entries(current.by_city).sort((a,b)=>a[1].min-b[1].min)[0][0]}`
                  : "—"}
              </div>
              <div className="mt-6 grid grid-cols-2 gap-4 tick-row border-t border-line pt-5">
                <div>
                  <div className="font-mono text-[11px] uppercase tracking-wider text-muted">
                    Huominen · halvin ennuste
                  </div>
                  <div
                    className="hero-num tnum text-2xl mt-1 text-brand"
                    data-testid="tomorrow-cheapest-price-hero"
                  >
                    {tomorrowCheapest != null ? tomorrowCheapest.toFixed(3) : "—"}
                    <span className="text-secondary text-xs ml-1">€/L</span>
                  </div>
                </div>
                <div className="pl-5">
                  <div className="font-mono text-[11px] uppercase tracking-wider text-muted">
                    Halvimpien {current?.stations_count || ""} ka.
                  </div>
                  <div className="hero-num tnum text-2xl mt-1">
                    {cheapAvg != null ? cheapAvg.toFixed(3) : "—"}
                    <span className="text-secondary text-xs ml-1">€/L</span>
                  </div>
                </div>
              </div>
              <div className="mt-4 text-[11px] text-muted font-mono leading-relaxed">
                Lähteet: polttoaine.net + tankille.fi (live, ≤ 24 h) · päivittyy automaattisesti klo 14 ja 21
              </div>
            </Card>
          </div>
        </div>
      </section>

      {/* TOMORROW PREDICTION (large) */}
      <section className="max-w-[1480px] mx-auto px-6 md:px-10 pb-8">
        <Card
          testId="tomorrow-prediction-card"
          dark
          className="p-7 md:p-10 relative"
        >
          <div
            aria-hidden
            className="absolute inset-0 pointer-events-none rounded-xl"
            style={{
              background:
                "radial-gradient(60rem 30rem at 110% -20%, rgba(0, 47, 167, 0.35), transparent 55%), radial-gradient(40rem 20rem at -10% 120%, rgba(253, 224, 71, 0.06), transparent 55%)",
            }}
          />
          <div className="relative z-10 grid grid-cols-12 gap-6 items-start">
            <div className="col-span-12 md:col-span-5">
              <CardLabel className="text-accent">
                Huominen · {prediction?.target_date ? fmtDateFi(prediction.target_date) : "—"}
              </CardLabel>
              <div className="mt-3 font-display text-[64px] md:text-[88px] font-black tracking-tightest leading-none text-white">
                {tomorrowVal != null ? tomorrowVal.toFixed(3) : "—"}
              </div>
              <div className="mt-2 font-mono text-sm text-slate-300">
                €/L · {prediction?.fuel || fuel} · ensemble-arvio
              </div>
              <div className="mt-5 flex items-center gap-3">
                <DirectionPill delta={tomorrowDelta} />
                {prediction?.ensemble?.spread != null && (
                  <span className="font-mono text-xs text-slate-400">
                    hajonta ±{prediction.ensemble.spread.toFixed(3)} €/L
                  </span>
                )}
              </div>
            </div>

            <div className="col-span-12 md:col-span-7 md:border-l md:border-slate-700/60 md:pl-8">
              <div className="flex items-center justify-between mb-4">
                <CardLabel className="text-slate-400">Mistä ennuste rakentuu</CardLabel>
                {prediction?.current_price != null && (
                  <span className="font-mono text-[11px] text-slate-500">
                    suhteessa live · <span className="tnum text-slate-300">{prediction.current_price.toFixed(3)}</span>
                  </span>
                )}
              </div>
              <div className="space-y-1.5" data-testid="dark-method-grid">
                {DARK_METHODS.map(({ key, label }) => {
                  const m = prediction?.methods?.[key];
                  const v = m?.value;
                  const live = prediction?.current_price ?? prediction?.live_anchor;
                  const d = v != null && live != null ? v - live : null;
                  const w = prediction?.ensemble?.weights?.[key];
                  const sub =
                    key === "ai_llm"
                      ? formatModelName(prediction?.methods?.ai_llm?.model) || "ei ajettu"
                      : key === "fundamental_anchor"
                      ? "Brent + RBOB/HO + FX"
                      : null;
                  return (
                    <div
                      key={key}
                      className="grid grid-cols-[5.5rem_1fr_4rem_3rem] md:grid-cols-[6rem_1fr_4.5rem_3.5rem] items-center gap-3 py-1.5 border-b border-slate-700/40 last:border-b-0"
                    >
                      <div className="min-w-0">
                        <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-slate-300">
                          {label}
                        </div>
                        {sub && (
                          <div className="font-mono text-[11px] text-slate-500 truncate" title={sub}>
                            {sub}
                          </div>
                        )}
                      </div>
                      <div className="font-mono tnum text-slate-100 text-sm md:text-base">
                        {v != null ? v.toFixed(3) : "—"}
                        <span className="text-slate-500 text-[11px] ml-1">€/L</span>
                      </div>
                      <div className={`font-mono tnum text-[11px] text-right ${deltaColorDark(d)}`}>
                        {deltaFmtMilli(d)}
                      </div>
                      <div className="font-mono tnum text-[11px] text-right text-slate-500">
                        {w != null ? `${Math.round(w * 100)}%` : ""}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="mt-5 flex flex-wrap items-center gap-2 font-mono text-[11px]">
                {prediction?.crack_eur_l != null && (
                  <span
                    className="inline-flex items-center gap-1.5 px-2.5 h-7 rounded-md bg-white/5 border border-slate-700/60 text-slate-300"
                    title="Crack-spread: jalostettu tuote − Brent (EUR/L). Positiivinen = jalostusmarginaali laajenee → pumppupaine ylös."
                  >
                    <span className="text-slate-500">crack</span>
                    <span className={`tnum font-semibold ${prediction.crack_eur_l >= 0 ? "text-amber-300" : "text-slate-200"}`}>
                      {prediction.crack_eur_l >= 0 ? "+" : ""}{prediction.crack_eur_l.toFixed(3)} €/L
                    </span>
                  </span>
                )}
                {prediction?.product_label && prediction?.product_chg != null && (
                  <span
                    className="inline-flex items-center gap-1.5 px-2.5 h-7 rounded-md bg-white/5 border border-slate-700/60 text-slate-300"
                    title="Jalostetun tuotteen (RBOB / NY Harbor ULSD) ≈5 päivän muutos. Day-ahead-pääsignaali."
                  >
                    <span className="text-slate-500">{prediction.product_label.startsWith("RBOB") ? "RBOB" : "ULSD"} ~5pv</span>
                    <span className={`tnum font-semibold ${prediction.product_chg >= 0 ? "text-red-300" : "text-emerald-300"}`}>
                      {prediction.product_chg >= 0 ? "+" : ""}{(prediction.product_chg * 100).toFixed(1)}%
                    </span>
                  </span>
                )}
                {prediction?.tax_step_eur_l && Math.abs(prediction.tax_step_eur_l) > 0.0001 && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 h-7 rounded-md bg-amber-500/15 border border-amber-400/30 text-amber-200 font-semibold">
                    veroaskel {prediction.tax_step_eur_l >= 0 ? "+" : ""}{(prediction.tax_step_eur_l * 100).toFixed(2)} snt/L
                  </span>
                )}
              </div>

              <div
                data-testid="auto-info-pill"
                className="mt-5 inline-flex items-center gap-2 px-4 h-9 rounded-lg bg-accent/15 text-accent border border-accent/30 font-semibold text-sm"
              >
                <Clock size={14} />
                Päivittyy automaattisesti klo 14 ja 21 Helsingin aikaa
              </div>
            </div>
          </div>
        </Card>
      </section>

      {/* CHART + METHOD COMPARE */}
      <section className="max-w-[1480px] mx-auto px-6 md:px-10 pb-8">
        <div className="grid grid-cols-12 gap-6">
          <Card span="col-span-12 lg:col-span-8" className="p-6" testId="tracking-chart-card">
            <div className="flex items-start justify-between mb-4 gap-4 flex-wrap">
              <div>
                <CardLabel>Ennuste vs. toteutunut · halvin asema</CardLabel>
                <h3 className="font-display text-2xl font-bold tracking-tight mt-1">
                  {fuel} · automaattinen mittaus klo 14 ja 21 (Helsinki)
                </h3>
                <p className="text-[11px] text-muted font-mono mt-1">
                  {chartCity === "Suomi"
                    ? "Vain todellisia havaintoja. Sininen = päivän halvin asema, harmaa risti = edellisen päivän ennuste, keltainen = huomisen ennuste."
                    : `${chartCity}: sininen = kaupungin halvin asema, oranssi katkoviiva = kaupungin keskihinta. Kertyy klo 14 ja 21 mittauksista.`}
                </p>
              </div>
              <div
                data-testid="schedule-pill"
                className="inline-flex items-center gap-2 px-3 h-8 rounded-lg bg-surface text-secondary font-mono text-[11px] font-semibold border border-line"
              >
                <Clock size={11} />
                {tracking?.summary?.today_date
                  ? `viim. mittaus: ${tracking.summary.today_date} klo ${
                      tracking.summary.today_captured_at
                        ? (() => {
                            const dt = new Date(tracking.summary.today_captured_at);
                            return `${String(dt.getHours()).padStart(2, "0")}:${String(dt.getMinutes()).padStart(2, "0")}`;
                          })()
                        : tracking.summary.today_hour != null
                        ? `${String(tracking.summary.today_hour).padStart(2, "0")}:00`
                        : "—"
                    }`
                  : "odottaa ensimmäistä mittausta"}
              </div>
            </div>

            {/* CHART FILTERS */}
            <div
              data-testid="chart-filters"
              className="flex flex-wrap items-center gap-x-5 gap-y-2 mb-4 pb-4 border-b border-line"
            >
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="font-mono text-[11px] uppercase tracking-wider text-muted mr-1">
                  Alue
                </span>
                {CHART_CITIES.map((c) => (
                  <FilterBtn
                    key={c}
                    active={chartCity === c}
                    onClick={() => setChartCity(c)}
                    testId={`chart-city-${c}`}
                  >
                    {c}
                  </FilterBtn>
                ))}
              </div>

              <div className="flex items-center gap-1.5">
                <span className="font-mono text-[11px] uppercase tracking-wider text-muted mr-1">
                  Jakso
                </span>
                {CHART_RANGES.map((r) => (
                  <FilterBtn
                    key={r.value}
                    active={chartRange === r.value}
                    onClick={() => setChartRange(r.value)}
                  >
                    {r.label}
                  </FilterBtn>
                ))}
              </div>

              <div className="flex items-center gap-1.5">
                <span className="font-mono text-[11px] uppercase tracking-wider text-muted mr-1">
                  Capture
                </span>
                {CHART_SLOTS.map((s) => (
                  <FilterBtn
                    key={s.value}
                    active={chartSlot === s.value}
                    onClick={() => setChartSlot(s.value)}
                  >
                    {s.label}
                  </FilterBtn>
                ))}
              </div>
            </div>

            <TrackingChart
              rows={filteredTrackingRows}
              city={chartCity}
              tomorrow={
                tracking?.summary?.tomorrow_prediction != null && tracking?.summary?.today_date
                  ? {
                      date: getNextDay(tracking.summary.today_date),
                      value: tracking.summary.tomorrow_prediction,
                    }
                  : null
              }
            />
            <TrackingFooter summary={tracking?.summary} fuel={fuel} />
          </Card>

          <div className="col-span-12 lg:col-span-4">
            <MethodTable result={prediction} />
          </div>
        </div>
      </section>

      {/* ALL-CITIES AVERAGE */}
      <section className="max-w-[1480px] mx-auto px-6 md:px-10 pb-8">
        <Card testId="city-average-card" className="p-6">
          <div className="flex items-start justify-between mb-4 gap-4 flex-wrap">
            <div>
              <CardLabel>Kaikkien kaupunkien keskihinta</CardLabel>
              <h3 className="font-display text-2xl font-bold tracking-tight mt-1">
                {fuel} · kaupunkien keskihinta + huomisen arvio
              </h3>
              <p className="text-[11px] text-muted font-mono mt-1">
                Ohuet viivat = yksittäisen kaupungin keskihinta (klo 14 ja 21
                mittauksista). Paksu sininen = kaikkien kaupunkien keskiarvo.
                Keltainen katkoviiva = huomisen arvio (kaikkien ka. + ennustettu
                markkinaliike). Käyttää samoja suodattimia kuin yllä.
              </p>
            </div>
          </div>
          <CityAverageChart
            rows={filteredTrackingRows}
            marketDelta={
              tracking?.summary?.tomorrow_prediction != null &&
              tracking?.summary?.today_actual != null
                ? tracking.summary.tomorrow_prediction -
                  tracking.summary.today_actual
                : null
            }
            tomorrowDate={
              tracking?.summary?.today_date
                ? getNextDay(tracking.summary.today_date)
                : null
            }
          />
        </Card>
      </section>

      {/* AI + NEWS */}
      <section className="max-w-[1480px] mx-auto px-6 md:px-10 pb-8">
        <div className="grid grid-cols-12 gap-6">
          <div className="col-span-12 lg:col-span-7">
            <AiAnalysis
              ai={prediction?.methods?.ai_llm}
              brent={prediction?.brent ?? factors?.brent?.latest}
              eurUsd={prediction?.eur_usd ?? factors?.eur_usd?.latest}
              anchor={prediction?.current_price ?? prediction?.live_anchor}
            />
          </div>
          <div className="col-span-12 lg:col-span-5">
            <NewsCard items={prediction?.news_headlines?.length ? prediction.news_headlines : news} />
          </div>
        </div>
      </section>

      {/* REGIONAL + FACTORS + ACCURACY */}
      <section className="max-w-[1480px] mx-auto px-6 md:px-10 pb-8">
        <div className="grid grid-cols-12 gap-6">
          <div className="col-span-12">
            <RegionalGrid data={regional} fuel={fuel} cityData={current?.by_city} />
          </div>
        </div>
      </section>

      <section className="max-w-[1480px] mx-auto px-6 md:px-10 pb-16">
        <div className="grid grid-cols-12 gap-6">
          <div className="col-span-12 lg:col-span-5">
            <FactorsCard factors={factors} prediction={prediction} />
          </div>
          <div className="col-span-12 lg:col-span-7">
            <AccuracyTracker data={accuracy} />
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="border-t border-line bg-surface">
        <div className="max-w-[1480px] mx-auto px-6 md:px-10 py-6 flex flex-wrap items-center justify-between gap-3 text-xs font-mono text-secondary">
          <div className="flex items-center gap-2">
            <Globe size={12} />
            Datalähteet: polttoaine.net · tankille.fi · Yahoo Finance (Brent, EUR/USD)
          </div>
          <div>
            <span className="text-muted">v2.0 · BensaVahti · ei takuuta tarkkuudesta</span>
          </div>
          <div className="w-full text-muted" data-testid="privacy-notice">
            Tietosuoja: emme kerää sinusta tietoja itse — vain alustojen (Railway, Vercel) automaattisesti keräämät tiedot.{" "}
            <a href="/privacy.html" className="underline hover:text-secondary transition-colors" data-testid="privacy-link">
              Lue tietosuojaseloste
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}

function getNextDay(isoDate) {
  if (!isoDate) return null;
  const d = new Date(isoDate);
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

function TrackingFooter({ summary, fuel }) {
  if (!summary) return null;
  const {
    n_compared,
    mae,
    within_2c_pct,
    today_actual,
    tomorrow_prediction,
    today_date,
  } = summary;
  return (
    <div
      data-testid="tracking-footer"
      className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3 border-t border-line pt-4"
    >
      <div className="bg-surface rounded-lg p-3 border border-line">
        <div className="font-mono text-[11px] uppercase tracking-wider text-muted">
          Tänään · {today_date ? today_date.slice(8, 10) + "." + today_date.slice(5, 7) + "." : "—"}
        </div>
        <div className="font-mono tnum text-lg font-bold mt-1">
          {today_actual != null ? today_actual.toFixed(3) : "—"}
          <span className="text-secondary text-xs ml-1">€/L</span>
        </div>
      </div>
      <div className="bg-surface rounded-lg p-3 border border-line">
        <div className="font-mono text-[11px] uppercase tracking-wider text-muted">
          Huominen ({fuel})
        </div>
        <div
          className="font-mono tnum text-lg font-bold mt-1 text-brand"
          data-testid="tomorrow-cheapest-prediction"
        >
          {tomorrow_prediction != null ? tomorrow_prediction.toFixed(3) : "—"}
          <span className="text-secondary text-xs ml-1">€/L</span>
        </div>
      </div>
      <div className="bg-surface rounded-lg p-3 border border-line">
        <div className="font-mono text-[11px] uppercase tracking-wider text-muted">
          MAE (vertailtu)
        </div>
        <div className="font-mono tnum text-lg font-bold mt-1">
          {mae != null ? mae.toFixed(4) : "—"}
          <span className="text-secondary text-xs ml-1">€/L</span>
        </div>
        <div className="font-mono text-[11px] text-muted mt-0.5">
          {n_compared > 0 ? `${n_compared} pv` : "kerää dataa"}
        </div>
      </div>
      <div className="bg-surface rounded-lg p-3 border border-line">
        <div className="font-mono text-[11px] uppercase tracking-wider text-muted">
          ≤2 snt tarkkuus
        </div>
        <div className="font-mono tnum text-lg font-bold mt-1">
          {within_2c_pct != null ? `${within_2c_pct.toFixed(0)}%` : "—"}
        </div>
      </div>
    </div>
  );
}

function DirectionPill({ delta }) {
  if (delta === null || delta === undefined || isNaN(delta)) {
    return (
      <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-800/80 text-slate-300 font-mono text-xs border border-slate-700/50">
        <Minus size={12} /> ei dataa
      </span>
    );
  }
  const n = Number(delta);
  if (n > 0.0005)
    return (
      <span
        data-testid="direction-pill"
        className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-red-500/15 text-red-300 border border-red-500/30 font-mono text-xs font-semibold"
      >
        <ArrowUpRight size={14} strokeWidth={2.6} /> kallistuu +{n.toFixed(3)} €/L
      </span>
    );
  if (n < -0.0005)
    return (
      <span
        data-testid="direction-pill"
        className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-mono text-xs font-semibold"
      >
        <ArrowDownRight size={14} strokeWidth={2.6} /> halpenee {n.toFixed(3)} €/L
      </span>
    );
  return (
    <span
      data-testid="direction-pill"
      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-800/80 text-slate-200 border border-slate-700/50 font-mono text-xs"
    >
      <Minus size={12} /> tasainen
    </span>
  );
}
