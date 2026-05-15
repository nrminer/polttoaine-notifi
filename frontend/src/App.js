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
import RangeToggle from "./components/RangeToggle";
import HistoryChart from "./components/HistoryChart";
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
  seedHistory,
} from "./lib/api";
import { fmtDateTimeFi, fmtDateFi } from "./lib/utils";
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
      ]);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fuel]);

  useEffect(() => {
    if (!seeded) return;
    loadHistory(fuel, range);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range]);

  const handleRunPrediction = async () => {
    setError(null);
    await loadPrediction(fuel, true);
    // refresh accuracy after running
    await loadAccuracy(fuel);
  };

  const handleRefreshAll = async () => {
    setError(null);
    await Promise.all([
      loadCurrent(fuel),
      loadHistory(fuel, range),
      loadFactors(),
      loadRegional(fuel),
    ]);
  };

  // hero metrics
  const todayAvg = current?.official_avg ?? current?.cheap_sample_avg;
  const officialMonth = current?.official_month;
  const todayMin = current?.national_min;
  const cheapAvg = current?.cheap_sample_avg;
  const yesterdayPrice = useMemo(() => {
    if (!history || history.length < 2) return null;
    // viim. ennen tämän päivän arvoa
    const today = new Date().toISOString().slice(0, 10);
    const filtered = history.filter((h) => h.date < today);
    return filtered.length ? filtered[filtered.length - 1].price : null;
  }, [history]);
  const dayDelta = todayAvg != null && yesterdayPrice != null ? todayAvg - yesterdayPrice : null;

  const tomorrowVal = prediction?.ensemble?.value;
  const tomorrowDelta = tomorrowVal != null && todayAvg != null ? tomorrowVal - todayAvg : null;

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
              tasoitus ja Claude Sonnet 4.5) yhdistettynä Brent-raakaöljyyn ja EUR/USD-kurssiin —
              ennustaa{" "}
              <span className="font-mono font-semibold text-ink">95E10:n</span> ja{" "}
              <span className="font-mono font-semibold text-ink">dieselin</span> hinnan huomenna.
            </p>

            <div className="mt-7 flex flex-wrap items-center gap-4">
              <FuelToggle value={fuel} onChange={setFuel} />
              <button
                data-testid="run-prediction-btn"
                onClick={handleRunPrediction}
                disabled={loading.prediction}
                className="inline-flex items-center gap-2 px-5 h-10 bg-nordDark text-white hover:bg-black font-semibold text-sm transition-colors disabled:opacity-60"
              >
                <Sparkles size={16} className={loading.prediction ? "animate-pulse" : ""} />
                {loading.prediction ? "Ennustetaan…" : "Aja ennustus"}
              </button>
              {error && (
                <span data-testid="error-banner" className="text-signalUp font-mono text-xs">
                  {error}
                </span>
              )}
            </div>
          </div>

          <div className="col-span-12 lg:col-span-5">
            <Card testId="hero-today-card" className="p-7 h-full" >
              <CardLabel className="mb-2">
                {officialMonth
                  ? `Virallinen kuukausiarvo · ${officialMonth.replace("-", "/")}`
                  : "Tänään · valtakunnan keskiarvo"}
              </CardLabel>
              <div className="flex items-end justify-between">
                <StatNumber value={todayAvg} testId="today-avg-price" />
                <DeltaBadge delta={dayDelta} />
              </div>
              <div className="mt-6 grid grid-cols-2 gap-4 tick-row border-t border-line pt-5">
                <div>
                  <div className="font-mono text-[10px] uppercase tracking-wider text-muted">
                    Halvin asema (live)
                  </div>
                  <div
                    className="hero-num tnum text-2xl mt-1"
                    data-testid="today-min-price"
                  >
                    {todayMin != null ? todayMin.toFixed(3) : "—"}
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
                Lähteet: Tilastokeskus 12ge (virallinen kk-ka.) · polttoaine.net + tankille.fi (live, ≤24h)
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
                  • <span className="font-mono text-accent">{prediction?.methods?.ai_llm?.value?.toFixed(3) ?? "—"}</span> · AI / Claude Sonnet 4.5
                </li>
              </ul>
              <button
                data-testid="run-prediction-btn-hero"
                onClick={handleRunPrediction}
                disabled={loading.prediction}
                className="mt-6 inline-flex items-center gap-2 px-5 h-10 bg-accent text-ink hover:bg-yellow-300 font-semibold text-sm transition-colors disabled:opacity-60"
              >
                <Sparkles size={16} className={loading.prediction ? "animate-pulse" : ""} />
                {loading.prediction ? "Lasketaan…" : "Aja ennustus uudelleen"}
              </button>
            </div>
          </div>
        </Card>
      </section>

      {/* CHART + METHOD COMPARE */}
      <section className="max-w-[1480px] mx-auto px-6 md:px-10 pb-8">
        <div className="grid grid-cols-12 gap-6">
          <Card span="col-span-12 lg:col-span-8" className="p-6" testId="history-chart-card">
            <div className="flex items-center justify-between mb-4">
              <div>
                <CardLabel>Hintahistoria + ennuste · todellinen data</CardLabel>
                <h3 className="font-display text-2xl font-bold tracking-tight mt-1">
                  {fuel} · valtakunnan keskihinta
                </h3>
                <p className="text-[11px] text-muted font-mono mt-1">
                  Lähde: Tilastokeskus 12ge (oikea kk-ka. 2020-2025) · Brent-ekstrapolointi joulukuusta 2025 alkaen · tämän päivän piste = live-skrapaus
                </p>
              </div>
              <RangeToggle value={range} onChange={setRange} options={RANGE_OPTIONS} />
            </div>
            <HistoryChart data={history} prediction={prediction} />
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

function DirectionPill({ delta }) {
  if (delta === null || delta === undefined || isNaN(delta)) {
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
