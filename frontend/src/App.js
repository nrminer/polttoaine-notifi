import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  CheckCircle2,
  Clock,
  Database,
  Fuel,
  Gauge,
  Globe,
  MapPin,
  Minus,
  Moon,
  Newspaper,
  RefreshCw,
  ShieldCheck,
  Sun,
  TrendingUp,
} from "lucide-react";

import "./App.css";
import { Card, CardLabel } from "./components/Card";
import FuelToggle from "./components/FuelToggle";
import TrackingChart from "./components/TrackingChart";
import CityAverageChart from "./components/CityAverageChart";
import MethodTable from "./components/MethodTable";
import AiAnalysis from "./components/AiAnalysis";
import RegionalGrid from "./components/RegionalGrid";
import AccuracyTracker from "./components/AccuracyTracker";
import FactorsCard from "./components/FactorsCard";
import NewsCard from "./components/NewsCard";
import { ConfidenceStrip } from "./components/ConfidenceStrip";
import {
  fetchAccuracy,
  fetchCurrent,
  fetchFactors,
  fetchHistory,
  fetchLatestPrediction,
  fetchNews,
  fetchRegional,
  fetchTrackHistory,
} from "./lib/api";
import { fmtDateFi, fmtDateTimeFi, fmtPrice } from "./lib/utils";
import { useRealtimeUpdates } from "./hooks/useRealtimeUpdates";

const CHART_CITIES = [
  "Suomi",
  "Helsinki",
  "Espoo",
  "Vantaa",
  "Tampere",
  "Turku",
  "Lahti",
];
const CITY_AVERAGE_CITIES = CHART_CITIES.filter((city) => city !== "Suomi");

const CHART_RANGES = [
  { value: 14, label: "14 pv" },
  { value: 30, label: "30 pv" },
  { value: 90, label: "Kaikki" },
];

const CHART_SLOTS = [
  { value: "all", label: "Molemmat" },
  { value: 14, label: "14:00" },
  { value: 21, label: "21:00" },
];

const HISTORY_RANGE_DAYS = 90;
const IMPORTANT_NEWS_HOLD_HOURS = 24;
const NEWS_DISPLAY_LIMIT = 12;

const METHOD_RAIL = [
  { key: "fundamental_anchor", label: "Ankkuri", detail: "Brent + FX" },
  { key: "ai_llm", label: "Uutiset", detail: "Claude" },
  { key: "exp_smoothing", label: "Holt", detail: "tasoitus" },
  { key: "linear_regression", label: "Regressio", detail: "trendi" },
  { key: "moving_average", label: "MA7", detail: "keskiarvo" },
];

const SOURCE_ROWS = [
  { name: "tankille.fi", role: "ensisijainen kaupunkilähde", tone: "green" },
  { name: "polttoaine.net", role: "ristitarkistus", tone: "blue" },
  { name: "Yahoo Finance", role: "Brent + EUR/USD", tone: "cyan" },
  { name: "RSS-uutiset", role: "AI-konteksti", tone: "amber" },
];

function newsIdentity(item) {
  const raw = item?.link || item?.title || "";
  return raw.toString().trim().toLowerCase().slice(0, 220);
}

function isRetainedImportantNews(item) {
  const age = Number(item?.age_hours ?? 999);
  return (
    Number.isFinite(age) &&
    age <= IMPORTANT_NEWS_HOLD_HOURS &&
    (item?.pinned_important || item?.breaking || Number(item?.severity || 0) >= 4)
  );
}

function mergeNewsItems(predictionItems = [], liveItems = []) {
  const seen = new Set();
  const merged = [];
  const sources = [
    ...liveItems.filter(isRetainedImportantNews),
    ...predictionItems.filter(isRetainedImportantNews),
    ...predictionItems,
    ...liveItems,
  ];

  for (const item of sources) {
    const key = newsIdentity(item);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    merged.push(item);
  }

  return merged.slice(0, NEWS_DISPLAY_LIMIT);
}

function FilterBtn({ active, onClick, children, testId }) {
  return (
    <button
      data-testid={testId}
      onClick={onClick}
      type="button"
      className={`filter-btn ${active ? "filter-btn--active" : ""}`}
    >
      {children}
    </button>
  );
}

function formatCents(delta) {
  if (delta === null || delta === undefined || isNaN(delta)) return "—";
  const cents = Number(delta) * 100;
  if (Math.abs(cents) < 0.05) return "0.0 snt";
  return `${cents > 0 ? "+" : "−"}${Math.abs(cents).toFixed(1)} snt`;
}

function formatPercent(value) {
  if (value === null || value === undefined || isNaN(value)) return "—";
  return `${Number(value).toFixed(0)}%`;
}

function getNextDay(isoDate) {
  if (!isoDate) return null;
  const d = new Date(`${isoDate.slice(0, 10)}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

function formatSlotLabel(point) {
  if (!point?.date) return "ei aikaleimaa";
  const date = fmtDateFi(point.date);
  const hour = point.hour != null ? `klo ${String(point.hour).padStart(2, "0")}:00` : "";
  return [date, hour].filter(Boolean).join(" · ");
}

function directionFor(delta) {
  if (delta === null || delta === undefined || isNaN(delta)) {
    return { label: "odottaa dataa", tone: "neutral", Icon: Minus };
  }
  if (delta > 0.0005) return { label: `kallistuu ${formatCents(delta)}/L`, tone: "up", Icon: ArrowUpRight };
  if (delta < -0.0005) return { label: `halpenee ${formatCents(delta)}/L`, tone: "down", Icon: ArrowDownRight };
  return { label: "tasainen", tone: "neutral", Icon: Minus };
}

function DirectionPill({ delta }) {
  const { Icon, label, tone } = directionFor(delta);
  return (
    <span data-testid="direction-pill" className={`direction-pill direction-pill--${tone}`}>
      <Icon size={14} strokeWidth={2.6} />
      {label}
    </span>
  );
}

function StatusChip({ icon: Icon, label, tone = "blue", testId }) {
  return (
    <span data-testid={testId} className={`status-chip status-chip--${tone}`}>
      {Icon && <Icon size={13} strokeWidth={2.4} />}
      {label}
    </span>
  );
}

function MetricTile({ icon: Icon, label, value, detail, tone = "blue", testId }) {
  return (
    <div className={`metric-tile metric-tile--${tone}`} data-testid={testId}>
      <div className="metric-tile__icon">
        <Icon size={16} strokeWidth={2.4} />
      </div>
      <div className="metric-tile__body">
        <div className="metric-tile__label">{label}</div>
        <div className="metric-tile__value">{value}</div>
        {detail && <div className="metric-tile__detail">{detail}</div>}
      </div>
    </div>
  );
}

function DataPlane({ current, prediction, tracking, sourceCount, series }) {
  const [activeIndex, setActiveIndex] = useState(null);
  const captureRows = tracking?.rows?.length ?? 0;
  const dataSources = prediction?.data_sources;
  const confidence = prediction?.prediction_confidence;
  const latest = current?.fetched_at || confidence?.most_recent_scrape;
  const visibleSeries = series.slice(-14);
  const latestPoint = visibleSeries[visibleSeries.length - 1] ?? null;
  const firstPoint = visibleSeries[0]?.value ?? null;
  const lastPoint = visibleSeries[visibleSeries.length - 1]?.value ?? null;
  const latestMeasurementDate = latestPoint?.date ? fmtDateFi(latestPoint.date) : null;
  const trendDelta = firstPoint != null && lastPoint != null ? lastPoint - firstPoint : null;
  const values = visibleSeries.map((point) => point.value).filter(Number.isFinite);
  const activePoint =
    activeIndex != null && visibleSeries[activeIndex]?.value != null
      ? visibleSeries[activeIndex]
      : null;
  const activePrev =
    activeIndex != null && activeIndex > 0 && visibleSeries[activeIndex - 1]?.value != null
      ? visibleSeries[activeIndex - 1]
      : null;
  const activeDelta =
    activePoint && activePrev ? activePoint.value - activePrev.value : null;
  const minValue = values.length ? Math.min(...values) : null;
  const maxValue = values.length ? Math.max(...values) : null;
  const sampleLabel = values.length ? `${values.length} viime mittauksessa` : "viime mittauksissa";
  const trendLabel =
    trendDelta == null || values.length < 2
      ? "odottaa mittauksia"
      : trendDelta > 0.0005
      ? `${formatCents(trendDelta)} ${sampleLabel}`
      : trendDelta < -0.0005
      ? `${formatCents(trendDelta)} ${sampleLabel}`
      : `vakaa ${sampleLabel}`;

  return (
    <aside className="data-plane" data-testid="landing-data-plane">
      <div className="data-plane__header">
        <div>
          <div className="mono-label">Datan tila</div>
          <h2>Live-ankkuri</h2>
        </div>
        <StatusChip
          icon={current?.stale ? Clock : CheckCircle2}
          label={current?.stale ? "välimuisti" : "tuore"}
          tone={current?.stale ? "amber" : "green"}
        />
      </div>

      <div className="data-plane__grid">
        <div>
          <span>Lähteet</span>
          <strong>{sourceCount ?? "—"}</strong>
        </div>
        <div>
          <span>Asemat</span>
          <strong>{current?.stations_count ?? "—"}</strong>
        </div>
        <div>
          <span>Mittaukset</span>
          <strong>{captureRows}</strong>
        </div>
        <div>
          <span>Päiväpisteet</span>
          <strong>{dataSources?.combined_points ?? prediction?.n_daily_points ?? "—"}</strong>
        </div>
      </div>

      <div className="micro-trend" data-testid="data-plane-trend">
        <div className="micro-trend__head">
          <div>
            <span>Viimeiset mittaukset</span>
            <strong className={trendDelta > 0 ? "is-up" : trendDelta < 0 ? "is-down" : ""}>
              {trendLabel}
            </strong>
          </div>
          <div className="micro-trend__latest tnum">
            {lastPoint != null ? `${fmtPrice(lastPoint)} €/L` : "—"}
            {latestMeasurementDate && <small>{latestMeasurementDate}</small>}
          </div>
        </div>
        <div
          className="micro-chart"
          role="img"
          aria-label={
            lastPoint != null
              ? `Viimeisten mittausten hintakehitys. Viimeisin mittaus ${latestMeasurementDate || ""}: ${fmtPrice(lastPoint)} euroa litralta.`
              : "Viimeisten mittausten hintakehitys odottaa dataa."
          }
        >
          {(visibleSeries.length
            ? visibleSeries
            : Array.from({ length: 14 }, (_, i) => ({ height: 24 + ((i * 13) % 54), muted: true }))
          ).map((bar, idx) => (
            <button
              type="button"
              key={`${bar.value ?? "empty"}-${idx}`}
              className={`${bar.muted ? "is-muted" : ""} ${activeIndex === idx ? "is-active" : ""}`}
              style={{ height: `${bar.height}%` }}
              title={bar.value != null ? `${fmtPrice(bar.value)} €/L` : "ei dataa"}
              aria-label={
                bar.value != null
                  ? `${formatSlotLabel(bar)}, ${fmtPrice(bar.value)} euroa litralta`
                  : "ei dataa"
              }
              onMouseEnter={() => setActiveIndex(idx)}
              onFocus={() => setActiveIndex(idx)}
              onMouseLeave={() => setActiveIndex(null)}
              onBlur={() => setActiveIndex(null)}
            />
          ))}
          {activePoint && (
            <div className="micro-chart__tooltip" role="tooltip">
              <span>{formatSlotLabel(activePoint)}</span>
              <strong>{fmtPrice(activePoint.value)} €/L</strong>
              <small className={activeDelta > 0 ? "is-up" : activeDelta < 0 ? "is-down" : ""}>
                {activeDelta != null ? `${formatCents(activeDelta)} edellisestä` : "ensimmäinen piste"}
              </small>
            </div>
          )}
        </div>
        <div className="micro-trend__scale">
          <span>{minValue != null ? fmtPrice(minValue) : "—"}</span>
          <span>{maxValue != null ? fmtPrice(maxValue) : "—"}</span>
        </div>
      </div>

      <div className="source-stack">
        {SOURCE_ROWS.map((source) => (
          <div key={source.name} className={`source-row source-row--${source.tone}`}>
            <span />
            <div>
              <strong>{source.name}</strong>
              <small>{source.role}</small>
            </div>
          </div>
        ))}
      </div>

      <div className="data-plane__footer">
        <Clock size={13} />
        {latest ? fmtDateTimeFi(latest) : "odottaa ensimmäistä onnistunutta hakua"}
      </div>
    </aside>
  );
}

function MethodRail({ prediction, anchor }) {
  return (
    <div className="method-rail" data-testid="dark-method-grid">
      <div className="method-rail__head">
        <span>Menetelmä</span>
        <span>Arvio</span>
        <span>Δ live</span>
        <span>Paino</span>
      </div>
      {METHOD_RAIL.map((method) => {
        const row = prediction?.methods?.[method.key] || {};
        const value = row.value;
        const delta = value != null && anchor != null ? value - anchor : null;
        const weight = prediction?.ensemble?.weights?.[method.key];
        const weightPct = weight != null ? Math.max(0, Math.min(100, Math.round(weight * 100))) : null;
        return (
          <div key={method.key} className="method-rail__row">
            <div>
              <strong>{method.label}</strong>
              <small>{method.detail}</small>
            </div>
            <span className="tnum">{value != null ? fmtPrice(value) : "—"}</span>
            <span className={`tnum method-rail__delta ${delta > 0 ? "is-up" : delta < 0 ? "is-down" : ""}`}>
              {formatCents(delta)}
            </span>
            <span className="method-meter" title={weightPct != null ? `${weightPct}%` : "ei painoa"}>
              <i style={{ width: `${weightPct ?? 0}%` }} />
            </span>
          </div>
        );
      })}
    </div>
  );
}

function TrackingFooter({ summary, fuel }) {
  if (!summary) return null;
  const { n_compared, mae, within_2c_pct, today_actual, tomorrow_prediction, today_date } = summary;
  return (
    <div data-testid="tracking-footer" className="tracking-footer">
      <MetricTile
        icon={Fuel}
        label={`Tänään ${today_date ? fmtDateFi(today_date) : ""}`}
        value={
          <>
            <span>{today_actual != null ? fmtPrice(today_actual) : "—"}</span>
            <small>€/L</small>
          </>
        }
        detail="viimeisin toteuma"
        tone="blue"
      />
      <MetricTile
        icon={TrendingUp}
        label={`Huominen ${fuel}`}
        value={
          <>
            <span data-testid="tomorrow-cheapest-prediction">{tomorrow_prediction != null ? fmtPrice(tomorrow_prediction) : "—"}</span>
            <small>€/L</small>
          </>
        }
        detail="tallennettu ennuste"
        tone="cyan"
      />
      <MetricTile
        icon={Gauge}
        label="Keskivirhe"
        value={
          <>
            <span>{mae != null ? `±${(mae * 100).toFixed(1)}` : "—"}</span>
            <small>snt</small>
          </>
        }
        detail={n_compared > 0 ? `${n_compared} vertailua` : "kerää dataa"}
        tone="green"
      />
      <MetricTile
        icon={ShieldCheck}
        label="Osumat ±2 snt"
        value={<span>{within_2c_pct != null ? formatPercent(within_2c_pct) : "—"}</span>}
        detail="toteumaan nähden"
        tone="amber"
      />
    </div>
  );
}

export default function App() {
  const [fuel, setFuel] = useState("95E10");
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
  const [cityAverageCities, setCityAverageCities] = useState(CITY_AVERAGE_CITIES);
  const [loading, setLoading] = useState({});
  const [error, setError] = useState(null);
  const [theme, setTheme] = useState(() => {
    if (typeof window === "undefined") return "dark";
    const saved = window.localStorage.getItem("theme");
    return saved === "light" || saved === "dark" ? saved : "dark";
  });

  useEffect(() => {
    const isDark = theme === "dark";
    document.documentElement.classList.toggle("dark", isDark);
    try {
      window.localStorage.setItem("theme", theme);
    } catch (e) {
      // Ignore storage errors in private browsing modes.
    }
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", isDark ? "#0e1320" : "#f8fafc");
  }, [theme]);

  const setLoad = useCallback((key, value) => {
    setLoading((state) => ({ ...state, [key]: value }));
  }, []);

  const loadCurrent = useCallback(
    async (selectedFuel) => {
      setLoad("current", true);
      try {
        const { data } = await fetchCurrent(selectedFuel);
        setCurrent(data);
      } catch (e) {
        console.warn("current failed", e);
      } finally {
        setLoad("current", false);
      }
    },
    [setLoad]
  );

  const loadHistory = useCallback(
    async (selectedFuel, days) => {
      setLoad("history", true);
      try {
        const { data } = await fetchHistory(selectedFuel, "Suomi", days);
        setHistory(data.rows || []);
      } catch (e) {
        console.warn("history failed", e);
      } finally {
        setLoad("history", false);
      }
    },
    [setLoad]
  );

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
  }, [setLoad]);

  const loadPrediction = useCallback(
    async (selectedFuel) => {
      setLoad("prediction", true);
      try {
        const { data } = await fetchLatestPrediction(selectedFuel, "Suomi");
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
              conflict_signal: data.conflict_signal,
              calendar_event: data.calendar_event,
              n_daily_points: data.n_daily_points,
              product_label: data.product_label,
              product_usd_gal: data.product_usd_gal,
              product_chg: data.product_chg,
              crack_eur_l: data.crack_eur_l,
              tax_events: data.tax_events,
              tax_step_eur_l: data.tax_step_eur_l,
              self_training: data.self_training,
              news_headlines: data.news_headlines,
              prediction_confidence: data.prediction_confidence,
          });
        } else {
          setPrediction(null);
        }
      } catch (e) {
        console.warn("prediction failed", e);
        setError(e.response?.data?.detail || "Ennusteen ajaminen epäonnistui");
      } finally {
        setLoad("prediction", false);
      }
    },
    [setLoad]
  );

  const loadRegional = useCallback(
    async (selectedFuel) => {
      setLoad("regional", true);
      try {
        const { data } = await fetchRegional(selectedFuel);
        setRegional(data);
      } catch (e) {
        console.warn("regional failed", e);
      } finally {
        setLoad("regional", false);
      }
    },
    [setLoad]
  );

  const loadAccuracy = useCallback(
    async (selectedFuel) => {
      setLoad("accuracy", true);
      try {
        const { data } = await fetchAccuracy(selectedFuel, "Suomi", 30);
        setAccuracy(data);
      } catch (e) {
        console.warn("accuracy failed", e);
      } finally {
        setLoad("accuracy", false);
      }
    },
    [setLoad]
  );

  const loadNews = useCallback(async () => {
    setLoad("news", true);
    try {
      const { data } = await fetchNews(30, 15);
      setNews(data.items || []);
    } catch (e) {
      console.warn("news failed", e);
    } finally {
      setLoad("news", false);
    }
  }, [setLoad]);

  const loadTracking = useCallback(
    async (selectedFuel) => {
      setLoad("tracking", true);
      try {
        const { data } = await fetchTrackHistory(selectedFuel, 90);
        setTracking(data);
      } catch (e) {
        console.warn("tracking failed", e);
      } finally {
        setLoad("tracking", false);
      }
    },
    [setLoad]
  );

  const handleRealtimeUpdate = useCallback(
    (update) => {
      const payloadFuel = update.data?.fuel || update.data?.fuels?.[0]?.fuel;
      if (payloadFuel && payloadFuel !== fuel) return;

      if (update.type === "prediction") {
        loadPrediction(fuel, false);
        loadTracking(fuel);
      } else if (update.type === "capture") {
        loadCurrent(fuel);
        loadTracking(fuel);
      } else if (update.type === "correction") {
        loadCurrent(fuel);
        loadHistory(fuel, HISTORY_RANGE_DAYS);
        loadPrediction(fuel, false);
        loadTracking(fuel);
        loadAccuracy(fuel);
      }
    },
    [fuel, loadAccuracy, loadCurrent, loadHistory, loadPrediction, loadTracking]
  );

  const realtime = useRealtimeUpdates(handleRealtimeUpdate);

  useEffect(() => {
    setError(null);
    Promise.all([
      loadCurrent(fuel),
      loadHistory(fuel, HISTORY_RANGE_DAYS),
      loadFactors(),
      loadPrediction(fuel, false),
      loadRegional(fuel),
      loadAccuracy(fuel),
      loadNews(),
      loadTracking(fuel),
    ]);
  }, [fuel, loadAccuracy, loadCurrent, loadFactors, loadHistory, loadNews, loadPrediction, loadRegional, loadTracking]);

  const isLoading = Object.values(loading).some(Boolean);

  const handleRefreshAll = useCallback(async () => {
    setError(null);
    await Promise.all([
      loadCurrent(fuel),
      loadHistory(fuel, HISTORY_RANGE_DAYS),
      loadFactors(),
      loadRegional(fuel),
      loadTracking(fuel),
      loadNews(),
    ]);
  }, [fuel, loadCurrent, loadFactors, loadHistory, loadNews, loadRegional, loadTracking]);

  const allCityAveragesSelected = cityAverageCities.length === CITY_AVERAGE_CITIES.length;
  const toggleCityAverageCity = useCallback((city) => {
    setCityAverageCities((selected) => {
      if (selected.includes(city)) {
        return selected.length > 1 ? selected.filter((item) => item !== city) : selected;
      }
      return CITY_AVERAGE_CITIES.filter((item) => item === city || selected.includes(item));
    });
  }, []);

  const todayMin = current?.national_min;
  const cheapAvg = current?.cheap_sample_avg;
  const forecastAnchor =
    prediction?.current_price ?? prediction?.live_anchor ?? cheapAvg ?? todayMin ?? null;
  const tomorrowVal =
    prediction?.ensemble?.value ?? tracking?.summary?.tomorrow_prediction ?? null;
  const tomorrowDelta =
    tomorrowVal != null && forecastAnchor != null ? tomorrowVal - forecastAnchor : null;
  const targetDate =
    prediction?.target_date || getNextDay(tracking?.summary?.today_date) || null;

  const cheapestCity = useMemo(() => {
    const regionalRows = regional?.rows || [];
    const regionalWinner = regionalRows
      .filter((row) => row.price != null)
      .sort((a, b) => a.price - b.price)[0];
    if (regionalWinner?.region) return regionalWinner.region;

    if (!current?.by_city) return null;
    const entries = Object.entries(current.by_city)
      .filter(([, value]) => value?.min != null)
      .sort((a, b) => a[1].min - b[1].min);
    return entries[0]?.[0] || null;
  }, [current, regional]);

  const sourceCount = useMemo(() => {
    if (current?.stations?.length) {
      return new Set(current.stations.map((station) => station.source).filter(Boolean)).size;
    }
    const citySources = Object.values(current?.by_city || {}).flatMap((city) => city.sources || []);
    if (citySources.length) return new Set(citySources.map((source) => source.source).filter(Boolean)).size;
    return null;
  }, [current]);

  const landingSeries = useMemo(() => {
    const trackerPoints = (tracking?.rows || [])
      .filter((row) => row.actual_cheapest != null)
      .slice(-14)
      .map((row) => ({
        value: Number(row.actual_cheapest),
        date: row.date,
        hour: row.hour,
      }))
      .filter((point) => Number.isFinite(point.value));
    const historyPoints = (history || [])
      .slice(-14)
      .map((row) => ({
        value: Number(row.price),
        date: row.date || row.ts?.slice(0, 10),
        hour: row.hour,
      }))
      .filter((point) => Number.isFinite(point.value));
    const points = trackerPoints.length >= 3 ? trackerPoints : historyPoints;
    if (!points.length) return [];
    const values = points.map((point) => point.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = Math.max(max - min, 0.001);
    return points.map((point) => ({
      ...point,
      height: 18 + ((point.value - min) / span) * 74,
    }));
  }, [history, tracking]);

  const filteredTrackingRows = useMemo(() => {
    const rows = tracking?.rows || [];
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - chartRange);
    const cutoffStr = cutoff.toISOString().slice(0, 10);
    return rows.filter((row) => {
      if (row.date < cutoffStr) return false;
      if (chartSlot !== "all" && (row.hour ?? 20) !== chartSlot) return false;
      return true;
    });
  }, [chartRange, chartSlot, tracking]);

  const comparedCount = tracking?.summary?.n_compared ?? 0;
  const accuracyBadge =
    tracking?.summary?.mae != null
      ? `±${(tracking.summary.mae * 100).toFixed(1)} snt keskivirhe`
      : "tarkkuus kertyy";
  const scrapeTime = current?.fetched_at ? fmtDateTimeFi(current.fetched_at) : "odottaa dataa";
  const generatedTime = prediction?.generated_at ? fmtDateTimeFi(prediction.generated_at) : "ei tallennettua ennustetta";
  const predictionNews = prediction?.news_headlines;
  const displayNews = useMemo(
    () => mergeNewsItems(predictionNews || [], news),
    [predictionNews, news]
  );

  return (
    <div className="app-shell">
      <a href="#dashboard" className="skip-link">
        Siirry sisältöön
      </a>

      <header className="app-header">
        <div className="app-header__inner">
          <a href="#dashboard" className="brand-lockup" data-testid="brand-link">
            <span>
              <strong>BensaVahti</strong>
              <small>Livehinnat ja huomisen ennuste</small>
            </span>
          </a>

          <nav className="top-nav" aria-label="Päänavigaatio">
            <a href="#forecast">Ennuste</a>
            <a href="#charts">Historia</a>
            <a href="#cities">Kaupungit</a>
            <a href="#signals">Signaalit</a>
          </nav>

          <div className="header-actions">
            <span className="header-time">
              <Clock size={13} />
              {scrapeTime}
            </span>
            <button
              data-testid="theme-toggle-btn"
              onClick={() => setTheme((value) => (value === "dark" ? "light" : "dark"))}
              type="button"
              aria-label={theme === "dark" ? "Vaihda vaaleaan teemaan" : "Vaihda tummaan teemaan"}
              className="icon-btn"
            >
              {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <button
              data-testid="refresh-prices-btn"
              onClick={handleRefreshAll}
              disabled={isLoading}
              type="button"
              className="command-btn command-btn--ghost"
            >
              <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
              Päivitä
            </button>
          </div>
        </div>
      </header>

      <main id="dashboard" className="dashboard-shell landing-hero" data-testid="landing-hero">
        <section className="command-deck" aria-labelledby="dashboard-title">
          <div className="command-deck__top">
            <div>
              <div className="eyebrow">Aether Fuel Dashboard</div>
              <h1 id="dashboard-title">BensaVahti</h1>
            </div>
            <div className="command-deck__controls">
              <FuelToggle value={fuel} onChange={setFuel} />
              <button
                data-testid="landing-refresh-btn"
                onClick={handleRefreshAll}
                disabled={isLoading}
                type="button"
                className="command-btn command-btn--ghost"
              >
                <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
                Synkronoi
              </button>
            </div>
          </div>

          {error && (
            <div className="error-banner" data-testid="error-banner">
              {error}
            </div>
          )}

          <div className="cockpit-grid">
            <Card
              dark
              testId="tomorrow-prediction-card"
              className="forecast-panel"
              id="forecast"
            >
              <div className="forecast-panel__header">
                <div>
                  <CardLabel className="text-accent">Huomisen hintaennuste</CardLabel>
                  <h2>{fuel} · {targetDate ? fmtDateFi(targetDate) : "seuraava päivä"}</h2>
                </div>
                <DirectionPill delta={tomorrowDelta} />
              </div>

              <div className="forecast-readout">
                <div>
                  <span className="forecast-readout__label">Tänään · live-ankkuri</span>
                  <strong className="tnum" data-testid="today-cheapest-price">
                    {todayMin != null ? fmtPrice(todayMin) : "—"}
                    <small>€/L</small>
                  </strong>
                  <p>{cheapestCity ? `Halvin kaupunki: ${cheapestCity}` : "livehaku käynnistyy taustalla"}</p>
                </div>
                <div className="forecast-readout__main">
                  <span className="forecast-readout__label">Huomenna · ensemble</span>
                  <strong className="tnum" data-testid="tomorrow-cheapest-price-hero">
                    {tomorrowVal != null ? fmtPrice(tomorrowVal) : "—"}
                    <small>€/L</small>
                  </strong>
                  <p data-testid="forecast-delta">{formatCents(tomorrowDelta)} suhteessa ankkuriin</p>
                </div>
              </div>

              <div className="forecast-meta">
                <StatusChip
                  icon={Database}
                  label={`${prediction?.data_sources?.tracker_captures ?? tracking?.rows?.length ?? 0} mittausta`}
                  tone="blue"
                />
                <StatusChip icon={ShieldCheck} label={accuracyBadge} tone="green" />
                {prediction?.conflict_signal && (
                  <StatusChip icon={Newspaper} label="geopolitiikka mukana" tone="amber" testId="geopol-chip" />
                )}
                {prediction?.calendar_event && (
                  <StatusChip icon={Clock} label="kalenteritapahtuma" tone="cyan" testId="calendar-chip" />
                )}
                <StatusChip
                  icon={realtime.isConnected ? CheckCircle2 : Bell}
                  label={realtime.isConnected ? "livepäivitykset" : "automaattiset mittaukset klo 14 ja 21"}
                  tone={realtime.isConnected ? "green" : "blue"}
                  testId="auto-schedule-info"
                />
              </div>

              <MethodRail prediction={prediction} anchor={forecastAnchor} />

              {current && (
                <ConfidenceStrip
                  mostRecentScrape={current.fetched_at}
                  sourcesCount={sourceCount}
                  stationsCount={current.stations_count}
                  predictionMAE={tracking?.summary?.mae}
                  className="forecast-confidence"
                />
              )}
            </Card>

            <DataPlane
              current={current}
              prediction={prediction}
              tracking={tracking}
              sourceCount={sourceCount}
              series={landingSeries}
            />
          </div>
        </section>

        <section className="metric-grid" aria-label="Live-yhteenveto">
          <MetricTile
            icon={Fuel}
            label="Halvin koko Suomessa"
            value={
              <>
                <span data-testid="current-min-price">{todayMin != null ? fmtPrice(todayMin) : "—"}</span>
                <small>€/L</small>
              </>
            }
            detail={cheapestCity ? `${cheapestCity} johtaa otosta` : "ei vielä kaupunkitietoa"}
            tone="blue"
          />
          <MetricTile
            icon={Gauge}
            label="Halpojen otoksen keskiarvo"
            value={
              <>
                <span data-testid="cheap-sample-avg">{cheapAvg != null ? fmtPrice(cheapAvg) : "—"}</span>
                <small>€/L</small>
              </>
            }
            detail="käytetään ankkurina ennusteessa"
            tone="cyan"
          />
          <MetricTile
            icon={MapPin}
            label="Kaupunkivoittaja"
            value={<span data-testid="cheapest-city">{cheapestCity || "—"}</span>}
            detail={regional?.rows?.length ? `${regional.rows.length} kaupunkia` : "odottaa aluehakua"}
            tone="green"
          />
          <MetricTile
            icon={BarChart3}
            label="Vertailuhistoria"
            value={<span>{comparedCount}</span>}
            detail={comparedCount ? accuracyBadge : "mittauksia kertyy klo 14 ja 21"}
            tone="amber"
          />
        </section>

        <section id="charts" className="dashboard-section">
          <div className="section-heading">
            <div>
              <div className="eyebrow">Historia</div>
              <h2>Ennuste vastaan toteutunut</h2>
            </div>
            <span data-testid="schedule-pill" className="section-pill">
              <Clock size={13} />
              {tracking?.summary?.today_date
                ? `viimeisin mittaus ${fmtDateFi(tracking.summary.today_date)}`
                : "odottaa ensimmäistä mittausta"}
            </span>
          </div>

          <div className="chart-layout">
            <Card testId="tracking-chart-card" className="panel-pad tracking-chart-panel">
              <div className="panel-head">
                <div>
                  <CardLabel>{fuel} · halvin asema</CardLabel>
                  <h3>{chartCity === "Suomi" ? "Kansallinen hintajälki" : `${chartCity} · halvin ja keskiarvo`}</h3>
                </div>
              </div>

              <div data-testid="chart-filters" className="filter-grid">
                <div>
                  <span>Alue</span>
                  {CHART_CITIES.map((city) => (
                    <FilterBtn
                      key={city}
                      active={chartCity === city}
                      onClick={() => setChartCity(city)}
                      testId={`chart-city-${city}`}
                    >
                      {city}
                    </FilterBtn>
                  ))}
                </div>
                <div>
                  <span>Jakso</span>
                  {CHART_RANGES.map((range) => (
                    <FilterBtn
                      key={range.value}
                      active={chartRange === range.value}
                      onClick={() => setChartRange(range.value)}
                      testId={`chart-range-${range.value}`}
                    >
                      {range.label}
                    </FilterBtn>
                  ))}
                </div>
                <div>
                  <span>Mittaus</span>
                  {CHART_SLOTS.map((slot) => (
                    <FilterBtn
                      key={slot.value}
                      active={chartSlot === slot.value}
                      onClick={() => setChartSlot(slot.value)}
                      testId={`chart-slot-${slot.value}`}
                    >
                      {slot.label}
                    </FilterBtn>
                  ))}
                </div>
              </div>

              <TrackingChart
                rows={filteredTrackingRows}
                city={chartCity}
                tomorrow={
                  tomorrowVal != null && tracking?.summary?.today_date
                    ? {
                        date: getNextDay(tracking.summary.today_date),
                        value: tomorrowVal,
                        confidence_range: {
                          low: prediction?.ensemble?.confidence_low,
                          high: prediction?.ensemble?.confidence_high,
                        },
                      }
                    : null
                }
              />
              <TrackingFooter summary={tracking?.summary} fuel={fuel} />
            </Card>

            <MethodTable result={prediction} />
          </div>
        </section>

        <section className="dashboard-section">
          <Card testId="city-average-card" className="panel-pad">
            <div className="panel-head">
              <div>
                <CardLabel>Kaikkien kaupunkien keskihinta</CardLabel>
                <h3>{fuel} · kaupunkien keskiarvo ja markkinaliike</h3>
              </div>
              <div className="city-average-filters" data-testid="city-average-filters">
                <FilterBtn
                  active={allCityAveragesSelected}
                  onClick={() => setCityAverageCities(CITY_AVERAGE_CITIES)}
                  testId="city-average-all"
                >
                  Kaikki
                </FilterBtn>
                {CITY_AVERAGE_CITIES.map((city) => (
                  <FilterBtn
                    key={city}
                    active={cityAverageCities.includes(city)}
                    onClick={() => toggleCityAverageCity(city)}
                    testId={`city-average-${city}`}
                  >
                    {city}
                  </FilterBtn>
                ))}
              </div>
            </div>
            <CityAverageChart
              rows={filteredTrackingRows}
              cities={cityAverageCities}
              marketDelta={
                tomorrowVal != null && tracking?.summary?.today_actual != null
                  ? tomorrowVal - tracking.summary.today_actual
                  : null
              }
              tomorrowDate={tracking?.summary?.today_date ? getNextDay(tracking.summary.today_date) : null}
            />
          </Card>
        </section>

        <section id="cities" className="dashboard-section">
          <div className="section-heading">
            <div>
              <div className="eyebrow">Asemat</div>
              <h2>Kaupunkikohtainen vertailu</h2>
            </div>
          </div>
          <RegionalGrid data={regional} fuel={fuel} cityData={current?.by_city} />
        </section>

        <section id="signals" className="dashboard-section">
          <div className="section-heading">
            <div>
              <div className="eyebrow">Signaalit</div>
              <h2>AI, markkinat ja uutiset</h2>
            </div>
            <span className="section-pill">
              <Activity size={13} />
              ennuste luotu {generatedTime}
            </span>
          </div>

          <div className="signals-grid">
            <div className="signals-column">
              <AiAnalysis
                ai={prediction?.methods?.ai_llm}
                brent={prediction?.brent ?? factors?.brent?.latest}
                eurUsd={prediction?.eur_usd ?? factors?.eur_usd?.latest}
                anchor={forecastAnchor}
              />
              <FactorsCard factors={factors} prediction={prediction} />
            </div>
            <div className="signals-column">
              <NewsCard items={displayNews} />
              <AccuracyTracker data={accuracy} />
            </div>
          </div>
        </section>
      </main>

      <footer className="app-footer">
        <div>
          <Globe size={13} />
          Datalähteet: polttoaine.net · tankille.fi · Yahoo Finance · RSS
        </div>
        <span>v2.0 · BensaVahti · ennuste ei ole takuu hinnasta</span>
        <div data-testid="privacy-notice">
          <a href="/privacy.html" data-testid="privacy-link">Tietosuoja</a>
        </div>
      </footer>
    </div>
  );
}
