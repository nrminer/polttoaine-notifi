import React from "react";
import { Newspaper, ExternalLink } from "lucide-react";
import { Card, CardLabel } from "./Card";

function ageLabel(h) {
  if (h == null) return "—";
  if (h < 1) return "juuri nyt";
  if (h < 48) return `${Math.round(h)} h sitten`;
  const d = Math.round(h / 24);
  return `${d} pv sitten`;
}

export default function NewsCard({ items = [], fetchedAt }) {
  return (
    <Card testId="news-card" className="p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Newspaper size={14} className="text-brand" strokeWidth={2.4} />
          <CardLabel>Markkinauutiset · Iltalehti · HS · IS · MTV</CardLabel>
        </div>
        <span className="font-mono text-[10px] text-muted uppercase tracking-wider">
          {items.length} otsikkoa
        </span>
      </div>

      {items.length === 0 ? (
        <div className="font-mono text-xs text-secondary py-6 text-center">
          Ei tuoreita uutisia.
        </div>
      ) : (
        <ul className="space-y-3" data-testid="news-list">
          {items.map((it, idx) => (
            <li
              key={idx}
              className="group border-b border-line/60 pb-3 last:border-b-0"
              data-testid={`news-item-${idx}`}
            >
              <a
                href={it.link}
                target="_blank"
                rel="noopener noreferrer"
                className="flex gap-3 items-start hover:bg-surface/60 -m-1 p-1 transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-ink leading-snug line-clamp-2 group-hover:text-brand">
                    {it.title}
                  </p>
                  <div className="mt-1 flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-[10px] uppercase tracking-wider text-muted">
                      {it.source || "Google News"}
                    </span>
                    <span className="font-mono text-[10px] tnum text-secondary">
                      · {ageLabel(it.age_hours)}
                    </span>
                  </div>
                </div>
                <ExternalLink
                  size={12}
                  className="text-muted shrink-0 mt-1 opacity-0 group-hover:opacity-100 transition-opacity"
                />
              </a>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 pt-3 border-t border-line text-[10px] text-muted font-mono">
        AI lukee näitä otsikoita ennustaessaan huomista. Ei mainoksia, suora syöte.
      </div>
    </Card>
  );
}
