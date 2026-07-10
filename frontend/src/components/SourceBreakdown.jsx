import React from "react";
import { Clock3, Database } from "lucide-react";

import { fmtPrice } from "../lib/utils";


export default function SourceBreakdown({ sources = [] }) {
  if (!sources.length) return null;
  const sorted = [...sources].sort((a, b) => (a.age_hours ?? 999) - (b.age_hours ?? 999));
  const prices = sorted.map((item) => Number(item.price)).filter(Number.isFinite);
  const spread = prices.length > 1 ? (Math.max(...prices) - Math.min(...prices)) * 100 : 0;

  return (
    <div className="source-breakdown" data-testid="source-breakdown">
      <div className="source-breakdown__head">
        <span><Database size={14} /> Lähdevertailu</span>
        <strong className="tnum">ero {spread.toFixed(1)} snt/l</strong>
      </div>
      <ul>
        {sorted.map((item) => (
          <li key={item.source} data-testid={`source-${item.source}`}>
            <strong>{item.source}</strong>
            <span className="tnum">{item.price != null ? `${fmtPrice(item.price)} €/l` : "-"}</span>
            <span><Clock3 size={13} /> {item.age_hours != null ? `${Math.round(item.age_hours)} h` : "aika puuttuu"}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
