import React from "react";
import {
  AlertCircle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  Database,
  MapPin,
  Minus,
  Store,
} from "lucide-react";

import { fmtDateFi, fmtPrice } from "../lib/utils";


function ageLabel(ageHours) {
  if (ageHours === null || ageHours === undefined) return "päivitysaika puuttuu";
  const age = Number(ageHours);
  if (!Number.isFinite(age)) return "päivitysaika puuttuu";
  if (age < 1) return "päivitetty alle tunti sitten";
  if (age < 24) return `päivitetty ${Math.round(age)} h sitten`;
  return `päivitetty ${Math.round(age / 24)} pv sitten`;
}

function fuelLabel(fuel) {
  return fuel === "95E10" ? "95 E10" : "diesel";
}

function Signal({ prediction, currentPrice, mae, predictionError }) {
  const value = prediction?.ensemble?.value;
  const isBaseline = String(prediction?.model_version || "").startsWith("persistence");
  const delta = value != null && currentPrice != null ? value - currentPrice : null;
  const threshold = Math.max(Number(mae) || 0.02, 0.01);

  if (value == null) {
    return {
      label: predictionError ? "Arviota ei saatu" : "Huomisen arvio puuttuu",
      detail: predictionError
        ? "Lataus epäonnistui. Nykyhintaa ei käytetä ennusteen korvikkeena."
        : "Nykyhintaa ei käytetä ennusteen korvikkeena.",
      tone: "neutral",
      Icon: AlertCircle,
    };
  }
  if (isBaseline) {
    return {
      label: "Vertailutaso",
      detail: "Tallennettu edellisestä klo 21 hinnasta. Se ei arvioi tuoreen hinnan muutosta.",
      tone: "neutral",
      Icon: Minus,
    };
  }
  if (delta > threshold) {
    return {
      label: "Tankkaa tänään",
      detail: `Odotettu nousu ${(delta * 100).toFixed(1)} snt/l ylittää mitatun virheen.`,
      tone: "up",
      Icon: ArrowUpRight,
    };
  }
  if (delta < -threshold) {
    return {
      label: "Odota",
      detail: `Odotettu lasku ${Math.abs(delta * 100).toFixed(1)} snt/l ylittää mitatun virheen.`,
      tone: "down",
      Icon: ArrowDownRight,
    };
  }
  return {
    label: "Epävarma",
    detail: "Odotettu muutos jää ennusteen mitatun virheen sisään.",
    tone: "neutral",
    Icon: Minus,
  };
}

function Price({ value, testId }) {
  return (
    <div className="city-price tnum" data-testid={testId}>
      <strong>{value != null ? fmtPrice(value) : "-"}</strong>
      <span>€/l</span>
    </div>
  );
}

export default function CityOverview({
  city,
  fuel,
  price,
  average,
  station,
  address,
  ageHours,
  source,
  sources = [],
  stationCount,
  prediction,
  accuracy,
  loading,
  error,
  predictionError,
}) {
  const mae = prediction?.prediction_confidence?.prediction_mae ?? accuracy?.summary?.ensemble?.mae;
  const signal = Signal({ prediction, currentPrice: price, mae, predictionError });
  const SignalIcon = signal.Icon;
  const forecast = prediction?.ensemble?.value;
  const isBaseline = String(prediction?.model_version || "").startsWith("persistence");
  const targetDate = prediction?.target_date;
  const statusText = loading && price == null
    ? "Haetaan tuoretta hintaa"
    : error && price == null
    ? "Hintaa ei saatu"
    : ageLabel(ageHours);

  return (
    <section id="now" className="city-overview" aria-labelledby="city-overview-title">
      <header className="city-overview__header">
        <div>
          <span className="section-kicker">Kotikaupunki</span>
          <h1 id="city-overview-title">{city} <span>{fuelLabel(fuel)}</span></h1>
        </div>
        <div className={`data-status ${error ? "data-status--warning" : ""}`}>
          {error ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
          <span>{statusText}</span>
        </div>
      </header>

      <div className="city-overview__grid">
        <div className="city-overview__current">
          <span className="metric-label">Halvin tuore hinta</span>
          <Price value={price} testId="today-cheapest-price" />
          <div className="station-line">
            <MapPin size={17} />
            <div>
              <strong>{station || "Asematieto puuttuu"}</strong>
              {address && <span>{address}</span>}
            </div>
          </div>
          <div className="source-line">
            <Clock3 size={15} /> {ageLabel(ageHours)}
            {source && <><span aria-hidden="true">·</span>{source}</>}
          </div>
        </div>

        <div className="city-overview__forecast">
          <div className="forecast-heading">
            <div>
              <span className="metric-label">
                {isBaseline ? "Huomisen vertailutaso" : "Huomisen arvio"}
              </span>
              <span>{targetDate ? `${fmtDateFi(targetDate)} klo 21` : "klo 21"}</span>
            </div>
            <span className={`signal-badge signal-badge--${signal.tone}`}>
              <SignalIcon size={17} /> {signal.label}
            </span>
          </div>
          <Price value={forecast} testId="tomorrow-cheapest-price-hero" />
          <p>{signal.detail}</p>
          {mae != null && (
            <span className="measured-error">Mitattu keskivirhe ±{(mae * 100).toFixed(1)} snt/l</span>
          )}
        </div>
      </div>

      <dl className="city-overview__facts">
        <div>
          <dt>Kaupungin keskihinta</dt>
          <dd className="tnum">{average != null ? `${fmtPrice(average)} €/l` : "-"}</dd>
        </div>
        <div>
          <dt><Store size={14} /> Asemia otoksessa</dt>
          <dd>{stationCount ?? "-"}</dd>
        </div>
        <div>
          <dt><Database size={14} /> Lähteitä</dt>
          <dd>{sources.length || "-"}</dd>
        </div>
        <div className="city-overview__source-list">
          <dt>Lähdehinnat</dt>
          <dd>
            {sources.length
              ? sources.map((item) => (
                  <span key={item.source}>{item.source} {fmtPrice(item.price)}</span>
                ))
              : "-"}
          </dd>
        </div>
      </dl>
    </section>
  );
}
