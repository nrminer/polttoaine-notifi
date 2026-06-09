import React from "react";
import { Newspaper, ExternalLink, Clock, AlertTriangle } from "lucide-react";
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

function BreakingBadge() {
  return (
    <span className="inline-flex items-center gap-1 font-mono text-[10px] font-bold px-2 py-1 rounded-md bg-red-100 text-red-700 border border-red-200 animate-pulse">
      <AlertTriangle size={10} strokeWidth={2.8} />
      JUURI NYT
    </span>
  );
}

export default function NewsCard({ items = [], fetchedAt }) {
  const breakingItems = items.filter(it => it.breaking && (it.age_hours || 999) <= 6);
  const hasBreaking = breakingItems.length > 0;
  const maxSeverity = hasBreaking ? Math.max(...breakingItems.map(it => it.severity || 0)) : 0;
  const severityLabel = maxSeverity >= 7 ? 'kriittinen' : maxSeverity >= 4 ? 'merkittävä' : 'kohtalainen';
  const severityColor = maxSeverity >= 7 ? 'red' : maxSeverity >= 4 ? 'orange' : 'yellow';

  return (
    <Card testId="news-card" className="p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Newspaper size={14} className="text-brand" strokeWidth={2.4} />
          <CardLabel>Markkinauutiset · FI + EN</CardLabel>
          {hasBreaking && (
            <span className={`ml-2 font-mono text-[10px] font-bold uppercase tracking-wider ${
              severityColor === 'red' ? 'text-red-600' : 
              severityColor === 'orange' ? 'text-orange-600' : 'text-yellow-600'
            }`}>
              {breakingItems.length} {severityLabel}
            </span>
          )}
        </div>
        <span className="font-mono text-[10px] text-muted uppercase tracking-wider">
          {items.length} otsikkoa
        </span>
      </div>

      {hasBreaking && (
        <div className={`mb-3 p-3 border rounded-lg ${
          severityColor === 'red' ? 'bg-red-50 border-red-200' :
          severityColor === 'orange' ? 'bg-orange-50 border-orange-200' : 'bg-yellow-50 border-yellow-200'
        }`}>
          <div className="flex items-start gap-2">
            <AlertTriangle size={14} className={`mt-0.5 shrink-0 ${
              severityColor === 'red' ? 'text-red-600' :
              severityColor === 'orange' ? 'text-orange-600' : 'text-yellow-600'
            }`} strokeWidth={2.4} />
            <div className="text-xs">
              <p className={`font-semibold ${
                severityColor === 'red' ? 'text-red-800' :
                severityColor === 'orange' ? 'text-orange-800' : 'text-yellow-800'
              }`}>
                {severityLabel.charAt(0).toUpperCase() + severityLabel.slice(1)} uutinen havaittu
              </p>
              <p className={`mt-0.5 ${
                severityColor === 'red' ? 'text-red-700' :
                severityColor === 'orange' ? 'text-orange-700' : 'text-yellow-700'
              }`}>
                Ennuste päivitetty automaattisesti. Ennusteen liikkumavara {
                  maxSeverity >= 7 ? '±0.15 €/L' :
                  maxSeverity >= 4 ? '±0.10 €/L' : '±0.08 €/L'
                }.
              </p>
            </div>
          </div>
        </div>
      )}

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
                className={`group flex gap-3 items-start p-2.5 rounded-lg hover:bg-surface transition-colors -mx-1 ${
                  it.breaking && (it.age_hours || 999) <= 6 ? 'bg-red-50 border border-red-100' : ''
                }`}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-start gap-2 mb-1">
                    <p className={`text-sm font-semibold leading-snug line-clamp-2 group-hover:text-brand transition-colors flex-1 ${
                      it.breaking && (it.age_hours || 999) <= 6 ? 'text-red-900' : 'text-ink'
                    }`}>
                      {it.title}
                    </p>
                    {it.breaking && (it.age_hours || 999) <= 6 && <BreakingBadge />}
                  </div>
                  <div className="mt-1 flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-[10px] uppercase tracking-wider text-muted">
                      {it.source || "News"}
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
        Otsikot syötetään huomisen arvion kontekstiksi. Suora RSS-pohjainen syöte (FI + EN).
      </div>
    </Card>
  );
}
