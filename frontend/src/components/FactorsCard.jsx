import React from "react";
import { Card, CardLabel, DeltaBadge } from "./Card";
import { Globe, DollarSign } from "lucide-react";

function FactorRow({ icon: Icon, iconColor, title, subtitle, value, deltaPct, testId }) {
  const dir = deltaPct == null ? null : deltaPct > 0.05 ? "up" : deltaPct < -0.05 ? "down" : "flat";
  return (
    <div className="flex items-center justify-between gap-4 p-4 rounded-xl bg-surface border border-line" data-testid={testId}>
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0" style={{ backgroundColor: `${iconColor}18` }}>
          <Icon size={16} strokeWidth={2.2} style={{ color: iconColor }} />
        </div>
        <div>
          <div className="font-semibold text-sm">{title}</div>
          <div className="font-mono text-[10px] text-muted uppercase tracking-wider">{subtitle}</div>
        </div>
      </div>
      <div className="text-right">
        <div className="font-mono tnum text-xl font-bold">
          {value ?? "—"}
        </div>
        {deltaPct != null && (
          <div className="mt-0.5 flex justify-end">
            <DeltaBadge delta={deltaPct / 100} unit="" suffix=" %" />
          </div>
        )}
      </div>
    </div>
  );
}

export default function FactorsCard({ factors }) {
  const brent = factors?.brent;
  const fx = factors?.eur_usd;

  return (
    <Card testId="factors-card" className="p-6">
      <CardLabel className="mb-4">Vaikuttavat tekijät</CardLabel>

      <div className="space-y-3">
        <FactorRow
          icon={Globe}
          iconColor="#002FA7"
          title="Brent-raakaöljy"
          subtitle="USD / barreli"
          value={brent?.latest != null ? Number(brent.latest).toFixed(2) : null}
          deltaPct={brent?.delta_pct}
          testId="factor-brent"
        />
        <FactorRow
          icon={DollarSign}
          iconColor="#10B981"
          title="EUR / USD"
          subtitle="valuuttakurssi"
          value={fx?.latest != null ? Number(fx.latest).toFixed(4) : null}
          deltaPct={fx?.delta_pct}
          testId="factor-fx"
        />
      </div>

      <div className="mt-4 font-mono text-[10px] text-muted pt-3 border-t border-line leading-relaxed">
        Heikkenevä EUR → kalliimpaa polttoainetta. Brent + 1 USD ≈ + 0,7 snt/L.
      </div>
    </Card>
  );
}
