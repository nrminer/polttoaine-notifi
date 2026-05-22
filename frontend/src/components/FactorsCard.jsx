import React from "react";
import { Card, CardLabel, DeltaBadge } from "./Card";
import { Globe, DollarSign, Droplet, Activity } from "lucide-react";

function FactorRow({ icon: Icon, iconColor, title, subtitle, value, deltaPct, deltaFrac, deltaSuffix = " %", testId, accent = false }) {
  // Either deltaPct (already in percent) or deltaFrac (fraction 0..1)
  let deltaForBadge = null;
  if (deltaPct != null) deltaForBadge = deltaPct / 100;
  else if (deltaFrac != null) deltaForBadge = deltaFrac;
  return (
    <div
      className={`flex items-center justify-between gap-4 p-4 rounded-xl border ${
        accent ? "bg-brand/5 border-brand/30" : "bg-surface border-line"
      }`}
      data-testid={testId}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
          style={{ backgroundColor: `${iconColor}18` }}
        >
          <Icon size={16} strokeWidth={2.2} style={{ color: iconColor }} />
        </div>
        <div className="min-w-0">
          <div className="font-semibold text-sm truncate">{title}</div>
          <div className="font-mono text-[11px] text-muted uppercase tracking-wider">
            {subtitle}
          </div>
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className="font-mono tnum text-xl font-bold">{value ?? "—"}</div>
        {deltaForBadge != null && (
          <div className="mt-0.5 flex justify-end">
            <DeltaBadge delta={deltaForBadge} unit="" suffix={deltaSuffix} />
          </div>
        )}
      </div>
    </div>
  );
}

export default function FactorsCard({ factors, prediction }) {
  const brent = factors?.brent;
  const fx = factors?.eur_usd;

  // Refined product (RBOB / NY Harbor ULSD) — supplied by /api/predict/latest
  // and the day-ahead PRIMARY signal; Brent is background context.
  const prodLabel = prediction?.product_label;
  const prodUsdGal = prediction?.product_usd_gal;
  const prodChg = prediction?.product_chg;
  const crack = prediction?.crack_eur_l;

  const prodShort = prodLabel
    ? prodLabel.startsWith("RBOB")
      ? "RBOB-bensiini"
      : "NY Harbor ULSD"
    : null;

  return (
    <Card testId="factors-card" className="p-6">
      <CardLabel className="mb-1">Vaikuttavat tekijät</CardLabel>
      <p className="text-[11px] text-muted font-mono mb-4">
        day-ahead-pääsignaali = jalostettu tuote · Brent + FX = tausta
      </p>

      <div className="space-y-3">
        {prodUsdGal != null && (
          <FactorRow
            icon={Droplet}
            iconColor="#F59E0B"
            title={prodShort || "Jalostettu tuote"}
            subtitle="USD / gallona · 5 pv muutos"
            value={Number(prodUsdGal).toFixed(3)}
            deltaFrac={prodChg}
            accent
            testId="factor-refined"
          />
        )}
        {crack != null && (
          <FactorRow
            icon={Activity}
            iconColor={crack >= 0 ? "#EF4444" : "#10B981"}
            title="Crack-spread"
            subtitle="jalostusmarginaali (EUR / L)"
            value={`${crack >= 0 ? "+" : ""}${crack.toFixed(3)}`}
            testId="factor-crack"
          />
        )}
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

      <div className="mt-4 font-mono text-[11px] text-muted pt-3 border-t border-line leading-relaxed">
        {crack != null
          ? "Laajeneva crack → jalostusmarginaali vetää pumppua ylös vaikka Brent jää paikoilleen. Heikkenevä EUR → tuontiöljy kallistuu."
          : "Heikkenevä EUR → kalliimpaa polttoainetta. Brent + 1 USD ≈ + 0,7 snt/L."}
      </div>
    </Card>
  );
}
