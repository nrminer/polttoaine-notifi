import axios from "axios";

const API = (process.env.REACT_APP_BACKEND_URL || "") + "/api";

export const api = axios.create({
  baseURL: API,
  timeout: 90000,
});

/**
 * API response types (for documentation):
 *
 * fetchCurrent response:
 * {
 *   fuel: string,
 *   national_min: number,
 *   cheap_sample_avg: number,
 *   stations_count: number,
 *   fetched_at: string (ISO),
 *   stale: boolean,
 *   by_city: {
 *     [cityName]: {
 *       min: number,
 *       mean: number,
 *       count: number,
 *       sources: Array<{source: string, price: number, age_hours: number, station_count: number}>, // NEW
 *       confidence_data: {agreement_level: "high"|"medium"|"low", spread_cents: number} // NEW
 *     }
 *   }
 * }
 *
 * fetchLatestPrediction response:
 * {
 *   available: boolean,
 *   fuel: string,
 *   region: string,
 *   generated_at: string (ISO),
 *   target_date: string (ISO date),
 *   current_price: number,
 *   live_anchor: number,
 *   ensemble: {value: number, spread: number, weights: object},
 *   methods: {ai_llm: object, fundamental_anchor: object, ...},
 *   brent: number,
 *   eur_usd: number,
 *   data_sources: object | null,
 *   conflict_signal: boolean,
 *   n_daily_points: number,
 *   product_label: string,
 *   product_usd_gal: number,
 *   product_chg: number,
 *   crack_eur_l: number,
 *   tax_events: array,
 *   tax_step_eur_l: number,
 *   self_training: object,
 *   news_headlines: array,
 *   prediction_confidence: { // NEW
 *     most_recent_scrape: string (ISO),
 *     sources_count: number,
 *     stations_count: number,
 *     prediction_mae: number | null
 *   }
 * }
 */

export const fetchCurrent = (fuel) => api.get(`/prices/current`, { params: { fuel } });
export const fetchHistory = (fuel, region, days) =>
  api.get(`/prices/history`, { params: { fuel, region, days } });
export const fetchFactors = () => api.get(`/factors`);
export const runPrediction = (fuel, region) =>
  api.post(`/predict/run`, { fuel, region });
export const fetchLatestPrediction = (fuel, region) =>
  api.get(`/predict/latest`, { params: { fuel, region } });
export const fetchRegional = (fuel) => api.get(`/regional`, { params: { fuel } });
export const fetchAccuracy = (fuel, region, days) =>
  api.get(`/accuracy`, { params: { fuel, region, days } });
export const fetchNews = (maxAgeDays = 14, limit = 15) =>
  api.get(`/news`, { params: { max_age_days: maxAgeDays, limit } });
export const fetchTrackHistory = (fuel, days = 60) =>
  api.get(`/track/history`, { params: { fuel, days } });
export const runTrackCapture = (fuel) =>
  api.post(`/track/run`, null, { params: { fuel } });
export const runTrackCaptureAll = () => api.post(`/track/run-all`);
export const seedHistory = (days, force) =>
  api.post(`/seed`, null, { params: { days, force } });
