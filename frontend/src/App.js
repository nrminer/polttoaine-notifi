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
} from "lucide-react";

import "./App.css";
import { Card, CardLabel, StatNumber, DeltaBadge } from "./components/Card";
import FuelToggle from "./components/FuelToggle";
import TrackingChart from "./components/TrackingChart";
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
  const [loading, setLoading] = useState({});
  const [seeded, setSeeded] = useState(false);
  const [error, setError] = useState(null);

  const setLoad = (k, v) => setLoading((s) => ({ ...s, [k]: v }));

  const ensureSeeded = useCallback(async () => {
    try {
      await seedHistory(180, false);
      setSeeded(true);
    } catch (e) {
      // not fatal
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
          // backend palauttaa nyt jo "run"-yhteensopivan rakenteen
          setPrediction({
            fuel: data.fuel,
            region: data.region,
            generated_at: data.generated_at,
            target_date: data.target_date,
            current_price: data.current_price,
            ensemble: data.ensemble,
            methods: data.methods,
            brent: data.brent,
            eur_usd: data.eur_usd,
            data_sources: data.data_sources,
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
      const { data } = await fetchTrackHistory(f, 60);
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

  // init
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

  // fuel change
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

  // hero metrics
  const todayMin = current?.national_min;
  const cheapAvg = current?.cheap_sample_avg;
  // huomisen halvin ennuste tulee trackerista
  const tomorrowCheapest = tracking?.summary?.tomorrow_prediction;
  const cheapestDelta = useMemo(() => {
    if (todayMin == null) return null;
    // edellisen päivän halvin tracker-historiasta
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

  const isLoading = Object.values(loading).some(Boolean);

  return (
    <div className="app-shell relative">
      {/* TOP BAR */}
      <header className="border-b border-line bg-white/70 backdrop-blur-xl sticky top-0 z-30">
        <div className="max-w-[1480px] mx-auto px-6 md:px-10 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-nordDark text-accent flex items-center justify-center">
              <Fuel size={16} strokeWidth={2.4} />
            </div>
            <div>
              <div className="font-display font-black tracking-tighter text-xl leading-none">
                BENSAVAHTI
              </div>
              <div className="font-mono text-[10px] text-muted uppercase tracking-[0.2em]">
                Suomi · 95E10 + Diesel · Ennustealgoritmi
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden md:flex items-center gap-2 font-mono text-xs text-secondary">
              <Clock size={12} />
              {current?.fetched_at ? fmtDateTimeFi(current.fetched_at) : "—"}
              {current?.stale && (
                <span className="ml-1 bg-amber-100 text-amber-800 px-1.5 py-0.5 text-[10px]">
                  CACHED
                </span>
              )}
            </div>
            <button
              data-testid="refresh-prices-btn"
              onClick={handleRefreshAll}
              disabled={isLoading}
              className="inline-flex items-center gap-2 px-3 h-9 border border-line hover:bg-surface text-sm font-mono font-semibold transition-colors"
            >
              <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
              Päivitä
            </button>
          </div>
        </div>
      </header>

      {/* HERO */}
      <section className="max-w-[1480px] mx-auto px-6 md:px-10 pt-10 md:pt-16 pb-8">
        <div className="grid grid-cols-12 gap-6">
          <div className="col-span-12 lg:col-span-7">
            <CardLabel className="mb-3">Suomen polttoainemarkkina · ennustealgoritmi</CardLabel>
            <h1 className="font-display text-5xl md:text-7xl font-black tracking-tightest leading-[0.95]">
              Huomisen<br />
              hinta <span className="deco-underline">tänään.</span>
            </h1>
            <p className="text-secondary text-base md:text-lg mt-5 max-w-xl">
              Neljä rinnakkaista algoritmia (liukuva ka., lineaarinen regressio, eksponentiaalinen
              tasoitus ja {formatModelName(prediction?.methods?.ai_llm?.model)}) yhdistettynä Brent-raakaöljyyn ja EUR/USD-kurssiin —
              ennustaa{" "}
              <span className="font-mono font-semibold text-ink">95E10:n</span> ja{" "}
              <span className="font-mono font-semibold text-ink">dieselin</span> hinnan huomenna.
            </p>

            <div className="mt-7 flex flex-wrap items-center gap-4">
              <FuelToggle value={fuel} onChange={setFuel} />
              <div
                data-testid="auto-schedule-info"
                className="inline-flex items-center gap-2 px-3 h-10 bg-slate-100 text-secondary font-mono text-xs font-semibold"
              >
                <Clock size={14} />
                Auto: 06:00 + 20:00 (Helsinki)
              </div>
              {error && (
                <span data-testid="error-banner" className="text-signalUp font-mono text-xs">
                  {error}
                </span>
              )}
            </div>
          </div>

          <div className="col-span-12 lg:col-span-5">
            <Card testId="hero-today-card" className="p-7 h-full" >
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
                  <div className="font-mono text-[10px] uppercase tracking-wider text-muted">
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
                  <div className="font-mono text-[10px] uppercase tracking-wider text-muted">
                    Top-{current?.stations_count || "—"} ka.
                  </div>
                  <div className="hero-num tnum text-2xl mt-1">
                    {cheapAvg != null ? cheapAvg.toFixed(3) : "—"}
                    <span className="text-secondary text-xs ml-1">€/L</span>
                  </div>
                </div>
              </div>
              <div className="mt-4 text-[11px] text-muted font-mono leading-relaxed">
                Lähteet: polttoaine.net + tankille.fi (live, ≤24h) · automaattipäivitys klo 06:00 ja 20:00
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
            className="absolute inset-0 opacity-[0.13] pointer-events-none"
            style={{
              backgroundImage:
                "url(https://static.prod-images.emergentagent.com/jobs/fbe4dcec-63a2-4ae5-ab80-570a0bc91b44/images/2f4ce133904abe0795e741e29b1017783b57035191543b365ba039243069fe63.png)",
              backgroundSize: "cover",
              backgroundPosition: "center",
              mixBlendMode: "overlay",
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

            <div className="col-span-12 md:col-span-7 md:border-l md:border-slate-700 md:pl-8">
              <CardLabel className="text-slate-400">Mistä ennuste rakentuu</CardLabel>
              <ul className="mt-3 space-y-2 text-slate-200 text-sm leading-relaxed">
                <li>
                  • <span className="font-mono text-accent">{prediction?.methods?.moving_average?.value?.toFixed(3) ?? "—"}</span> · liukuva 7 pv keskiarvo
                </li>
                <li>
                  • <span className="font-mono text-accent">{prediction?.methods?.linear_regression?.value?.toFixed(3) ?? "—"}</span> · lineaarinen regressio
                </li>
                <li>
                  • <span className="font-mono text-accent">{prediction?.methods?.exp_smoothing?.value?.toFixed(3) ?? "—"}</span> · Holt-tasoitus
                </li>
                <li>
                  • <span className="font-mono text-accent">{prediction?.methods?.ai_llm?.value?.toFixed(3) ?? "—"}</span> · AI / {formatModelName(prediction?.methods?.ai_llm?.model)}
                </li>
              </ul>
              <button
                data-testid="auto-info-pill"
                disabled
                className="mt-6 inline-flex items-center gap-2 px-5 h-10 bg-accent/20 text-accent border border-accent/40 font-semibold text-sm cursor-default"
              >
                <Clock size={16} />
                Päivittyy automaattisesti 06:00 ja 20:00 Helsinki-aikaa
              </button>
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
                  {fuel} · automaattinen otanta klo 06:00 ja 20:00 (Helsinki)
                </h3>
                <p className="text-[11px] text-muted font-mono mt-1">
                  Vain todellisia havaintoja. Sininen viiva = päivän halvin asema, harmaa risti = edellisen päivän ennuste tästä päivästä, keltainen pisteviiva = huomisen ennuste.
                </p>
              </div>
              <div
                data-testid="schedule-pill"
                className="inline-flex items-center gap-2 px-3 h-8 bg-slate-100 text-secondary font-mono text-[11px] font-semibold"
              >
                <Clock size={11} />
                {tracking?.summary?.today_date
                  ? `viim. capture: ${tracking.summary.today_date}`
                  : "odottaa ensimmäistä captureeen"}
              </div>
            </div>
            <TrackingChart
              rows={tracking?.rows || []}
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

      {/* AI + NEWS */}
      <section className="max-w-[1480px] mx-auto px-6 md:px-10 pb-8">
        <div className="grid grid-cols-12 gap-6">
          <div className="col-span-12 lg:col-span-7">
            <AiAnalysis
              ai={prediction?.methods?.ai_llm}
              brent={prediction?.brent ?? factors?.brent?.latest}
              eurUsd={prediction?.eur_usd ?? factors?.eur_usd?.latest}
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
            <RegionalGrid data={regional} fuel={fuel} />
          </div>
        </div>
      </section>

      <section className="max-w-[1480px] mx-auto px-6 md:px-10 pb-16">
        <div className="grid grid-cols-12 gap-6">
          <div className="col-span-12 lg:col-span-5">
            <FactorsCard factors={factors} />
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
    within_1c_pct,
    today_actual,
    tomorrow_prediction,
    today_date,
  } = summary;
  return (
    <div
      data-testid="tracking-footer"
      className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-px bg-line border-t border-line"
    >
      <div className="bg-white p-3">
        <div className="font-mono text-[10px] uppercase tracking-wider text-muted">
          Tänään · {today_date ? today_date.slice(8, 10) + "." + today_date.slice(5, 7) + "." : "—"}
        </div>
        <div className="font-mono tnum text-lg font-bold mt-1">
          {today_actual != null ? today_actual.toFixed(3) : "—"}
          <span className="text-secondary text-xs ml-1">€/L</span>
        </div>
      </div>
      <div className="bg-white p-3">
        <div className="font-mono text-[10px] uppercase tracking-wider text-muted">
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
      <div className="bg-white p-3">
        <div className="font-mono text-[10px] uppercase tracking-wider text-muted">
          MAE (vertailtu)
        </div>
        <div className="font-mono tnum text-lg font-bold mt-1">
          {mae != null ? mae.toFixed(4) : "—"}
          <span className="text-secondary text-xs ml-1">€/L</span>
        </div>
        <div className="font-mono text-[10px] text-muted mt-0.5">
          {n_compared > 0 ? `${n_compared} pv` : "kerää dataa"}
        </div>
      </div>
      <div className="bg-white p-3">
        <div className="font-mono text-[10px] uppercase tracking-wider text-muted">
          ≤1 snt tarkkuus
        </div>
        <div className="font-mono tnum text-lg font-bold mt-1">
          {within_1c_pct != null ? `${within_1c_pct.toFixed(0)}%` : "—"}
        </div>
      </div>
    </div>
  );
}

function DirectionPill({ delta }) {  if (delta === null || delta === undefined || isNaN(delta)) {
    return (
      <span className="inline-flex items-center gap-2 px-3 py-1 bg-slate-800 text-slate-300 font-mono text-xs">
        <Minus size={12} /> ei dataa
      </span>
    );
  }
  const n = Number(delta);
  if (n > 0.0005)
    return (
      <span
        data-testid="direction-pill"
        className="inline-flex items-center gap-2 px-3 py-1 bg-signalUpBg text-signalUp font-mono text-xs font-semibold"
      >
        <ArrowUpRight size={14} strokeWidth={2.6} /> kallistuu +{n.toFixed(3)} €/L
      </span>
    );
  if (n < -0.0005)
    return (
      <span
        data-testid="direction-pill"
        className="inline-flex items-center gap-2 px-3 py-1 bg-signalDownBg text-signalDown font-mono text-xs font-semibold"
      >
        <ArrowDownRight size={14} strokeWidth={2.6} /> halpenee {n.toFixed(3)} €/L
      </span>
    );
  return (
    <span
      data-testid="direction-pill"
      className="inline-flex items-center gap-2 px-3 py-1 bg-slate-800 text-slate-200 font-mono text-xs"
    >
      <Minus size={12} /> tasainen
    </span>
  );
}
