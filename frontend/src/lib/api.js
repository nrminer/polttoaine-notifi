import axios from "axios";

const API = (process.env.REACT_APP_BACKEND_URL || "") + "/api";

const api = axios.create({
  baseURL: API,
  timeout: 90000,
});

export const fetchCurrent = (fuel) => api.get(`/prices/current`, { params: { fuel } });
export const fetchHistory = (fuel, region, days) =>
  api.get(`/prices/history`, { params: { fuel, region, days } });
export const fetchFactors = () => api.get(`/factors`);
export const fetchLatestPrediction = (fuel, region) =>
  api.get(`/predict/latest`, { params: { fuel, region } });
export const fetchRegional = (fuel) => api.get(`/regional`, { params: { fuel } });
export const fetchAccuracy = (fuel, region, days) =>
  api.get(`/accuracy`, { params: { fuel, region, days } });
export const fetchNews = (maxAgeDays = 14, limit = 15) =>
  api.get(`/news`, { params: { max_age_days: maxAgeDays, limit } });
export const fetchTrackHistory = (fuel, days = 60) =>
  api.get(`/track/history`, { params: { fuel, days } });
