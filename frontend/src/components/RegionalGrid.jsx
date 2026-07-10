import React, { useMemo, useState } from "react";
import { ArrowUpDown, ChevronDown, ChevronUp, Clock3, MapPin } from "lucide-react";

import { CITIES } from "../lib/cities";
import { fmtPrice } from "../lib/utils";
import SourceBreakdown from "./SourceBreakdown";


function ageLabel(value) {
  if (value === null || value === undefined) return "ei tuoretta aikaa";
  const age = Number(value);
  if (!Number.isFinite(age)) return "ei tuoretta aikaa";
  if (age < 1) return "alle 1 h";
  return `${Math.round(age)} h`;
}

export default function RegionalGrid({
  data,
  fuel,
  cityData,
  selectedCity,
  onSelectCity,
  loading,
  error,
}) {
  const [descending, setDescending] = useState(false);
  const [expandedCity, setExpandedCity] = useState(null);

  const rows = useMemo(() => {
    const liveByCity = new Map((data?.rows || []).map((row) => [row.region, row]));
    const combined = CITIES.map((city) => {
      const live = liveByCity.get(city) || {};
      const snapshot = cityData?.[city] || {};
      return {
        city,
        price: live.fresh ? live.price : null,
        station: live.station,
        address: live.address,
        ageHours: live.age_hours,
        source: live.source,
        average: snapshot.mean,
        count: snapshot.count,
        sources: snapshot.sources || [],
      };
    });
    return combined.sort((a, b) => {
      if (a.city === selectedCity) return -1;
      if (b.city === selectedCity) return 1;
      if (a.price == null) return 1;
      if (b.price == null) return -1;
      return descending ? b.price - a.price : a.price - b.price;
    });
  }, [cityData, data?.rows, descending, selectedCity]);

  return (
    <section className="city-comparison" aria-labelledby="city-comparison-title">
      <header className="section-header">
        <div>
          <span className="section-kicker">Kaupungit</span>
          <h2 id="city-comparison-title">Tuoreiden hintojen vertailu</h2>
          <p>Kotikaupunki on kiinnitetty ensimmäiseksi. Vanhentuneita hintoja ei näytetä.</p>
        </div>
        <button
          type="button"
          className="secondary-button"
          onClick={() => setDescending((value) => !value)}
          aria-label={descending ? "Lajittele halvin ensin" : "Lajittele kallein ensin"}
        >
          <ArrowUpDown size={16} /> {descending ? "Kallein ensin" : "Halvin ensin"}
        </button>
      </header>

      {error && !data ? <div className="inline-state inline-state--error">Kaupunkihintoja ei saatu ladattua.</div> : null}
      {loading && !data ? <div className="inline-state">Haetaan kaupunkihintoja...</div> : null}

      <div className="city-table-wrap">
        <table className="city-table">
          <thead>
            <tr>
              <th>Kaupunki</th>
              <th>Halvin</th>
              <th>Keskihinta</th>
              <th>Asema</th>
              <th>Ikä</th>
              <th>Lähde</th>
              <th><span className="sr-only">Lähdetiedot</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const selected = row.city === selectedCity;
              const expanded = expandedCity === row.city;
              return (
                <React.Fragment key={row.city}>
                  <tr className={selected ? "city-table__selected" : ""} data-testid={`region-cell-${row.city}`}>
                    <td data-label="Kaupunki">
                      <button
                        type="button"
                        className="city-name-button"
                        onClick={() => onSelectCity?.(row.city)}
                        aria-current={selected ? "true" : undefined}
                      >
                        <MapPin size={15} /> {row.city}
                        {selected && <span>Koti</span>}
                      </button>
                    </td>
                    <td data-label="Halvin" className="city-table__price tnum">
                      {row.price != null ? `${fmtPrice(row.price)} €/l` : "-"}
                    </td>
                    <td data-label="Keskihinta" className="tnum">
                      {row.average != null ? `${fmtPrice(row.average)} €/l` : "-"}
                    </td>
                    <td data-label="Asema" data-testid={`region-station-${row.city}`}>
                      <strong>{row.station || "Ei tuoretta asemaa"}</strong>
                      {row.address && <span>{row.address}</span>}
                    </td>
                    <td data-label="Ikä"><span className="age-cell"><Clock3 size={14} /> {ageLabel(row.ageHours)}</span></td>
                    <td data-label="Lähde">{row.source || "-"}</td>
                    <td className="city-table__action">
                      {row.sources.length > 0 && (
                        <button
                          type="button"
                          className="icon-button"
                          onClick={() => setExpandedCity(expanded ? null : row.city)}
                          aria-expanded={expanded}
                          aria-controls={`sources-${row.city}`}
                          title="Näytä lähdevertailu"
                        >
                          {expanded ? <ChevronUp size={17} /> : <ChevronDown size={17} />}
                        </button>
                      )}
                    </td>
                  </tr>
                  {expanded && (
                    <tr className="city-table__details" id={`sources-${row.city}`}>
                      <td colSpan={7}><SourceBreakdown sources={row.sources} /></td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="table-footnote">{fuel === "95E10" ? "95 E10" : "diesel"} · enintään {data?.max_age_hours || 24} h vanhat havainnot</div>
    </section>
  );
}
