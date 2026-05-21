import React from "react";
import { Newspaper, ExternalLink, Clock } from "lucide-react";
import { Card, CardLabel } from "./Card";

function ageLabel(h) {
  if (h == null) return "—";
  if (h < 1) return "juuri nyt";
  if (h < 48) return `${Math.round(h)} h sitten`;
  const d = Math.round(h / 24);
  return `${d} pv sitten`;
}

function AgeBadge({ h }) {
  if (h == null) return null;
  const fresh = h < 6;
  return (
    <span className={`inline-flex items-center gap-1 font-mono text-[10px] px-1.5 py-0.5 rounded-full ${
      fresh ? "bg-emerald-100 text-emerald-700" : "text-secondary"
    }`}>
      {fresh && <Clock size={9} />}
      {ageLabel(h)}
    </span>
  );
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
        <div className="font-mono text-xs text-secondary py-8 text-center border border-dashed border-line rounded-lg">
          Ei tuoreita uutisia.
        </div>
      ) : (
        <ul className="space-y-1" data-testid="news-list">
          {items.map((it, idx) => (
            <li
              key={idx}
              data-testid={`news-item-${idx}`}
            >
              <a
                href={it.link}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex gap-3 items-start p-2.5 rounded-lg hover:bg-surface transition-colors -mx-1"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-ink leading-snug line-clamp-2 group-hover:text-brand transition-colors">
                    {it.title}
                  </p>
                  <div className="mt-1 flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-[10px] uppercase tracking-wider text-muted">
                      {it.source || "Google News"}
                    </span>
                    <span className="text-muted">·</span>
                    <AgeBadge h={it.age_hours} />
                  </div>
                </div>
                <ExternalLink
                  size={12}
                  className="text-muted shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                />
              </a>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 pt-3 border-t border-line text-[10px] text-muted font-mono">
        AI lukee nämä otsikot ennustaessaan huomista. Ei mainoksia, suora syöte.
      </div>
    </Card>
  );
}
