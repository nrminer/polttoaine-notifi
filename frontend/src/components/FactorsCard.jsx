import React from "react";
import { Card, CardLabel, DeltaBadge } from "./Card";
import { Globe, DollarSign } from "lucide-react";

export default function FactorsCard({ factors }) {
  const brent = factors?.brent;
  const fx = factors?.eur_usd;

  return (
    <Card testId="factors-card" className="p-6">
      <CardLabel className="mb-4">Vaikuttavat tekijät</CardLabel>

      <div className="space-y-5">
        <div className="flex items-center justify-between" data-testid="factor-brent">
          <div className="flex items-center gap-2">
            <Globe size={14} strokeWidth={2.4} className="text-brand" />
            <div>
              <div className="font-semibold text-sm">Brent-raakaöljy</div>
              <div className="font-mono text-[10px] text-muted uppercase tracking-wider">
                USD / barreli
              </div>
            </div>
          </div>
          <div className="text-right">
            <div className="font-mono tnum text-xl font-bold">
              {brent?.latest != null ? Number(brent.latest).toFixed(2) : "—"}
            </div>
            {brent?.delta_pct != null && (
              <DeltaBadge delta={brent.delta_pct / 100} unit="" suffix=" %" />
            )}
          </div>
        </div>

        <div className="flex items-center justify-between" data-testid="factor-fx">
          <div className="flex items-center gap-2">
            <DollarSign size={14} strokeWidth={2.4} className="text-brand" />
            <div>
              <div className="font-semibold text-sm">EUR / USD</div>
              <div className="font-mono text-[10px] text-muted uppercase tracking-wider">
                valuuttakurssi
              </div>
            </div>
          </div>
          <div className="text-right">
            <div className="font-mono tnum text-xl font-bold">
              {fx?.latest != null ? Number(fx.latest).toFixed(4) : "—"}
            </div>
            {fx?.delta_pct != null && (
              <DeltaBadge delta={fx.delta_pct / 100} unit="" suffix=" %" />
            )}
          </div>
        </div>

        <div className="font-mono text-[10px] text-muted pt-2 border-t border-line">
          Heikompi EUR → kalliimpaa polttoainetta. Brent + 1 USD ≈ + 0.7 snt/L.
        </div>
      </div>
    </Card>
  );
}
