import React from "react";
import { Card, CardLabel } from "./Card";
import { TrendingUp, TrendingDown, Minus, Droplet, DollarSign, Calendar, Newspaper, Database } from "lucide-react";

function DirectionIcon({ direction, size = 16 }) {
  if (direction === "up") return <TrendingUp size={size} className="text-red-500" />;
  if (direction === "down") return <TrendingDown size={size} className="text-green-500" />;
  return <Minus size={16} className="text-muted" />;
}

function DriverRow({ icon: Icon, iconColor, label, direction, explanation, change, testId }) {
  return (
    <div
      className="flex items-start gap-3 p-3 rounded-lg bg-surface border border-line"
      data-testid={testId}
    >
      <div
        className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5"
        style={{ backgroundColor: `${iconColor}18` }}
      >
        <Icon size={14} strokeWidth={2.2} style={{ color: iconColor }} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-semibold text-sm">{label}</span>
          <DirectionIcon direction={direction} />
          {change != null && (
            <span className="font-mono text-xs text-muted">
              {change > 0 ? "+" : ""}{change.toFixed(1)}%
            </span>
          )}
        </div>
        <p className="text-xs text-secondary leading-relaxed">{explanation}</p>
      </div>
    </div>
  );
}

export default function PriceDrivers({ brent, eurUsd, cyclePhase, newsCount, dataQuality }) {
  // Determine direction based on change %
  const brentDir = brent?.change_pct > 0.5 ? "up" : brent?.change_pct < -0.5 ? "down" : "flat";
  const fxDir = eurUsd?.change_pct > 0.5 ? "down" : eurUsd?.change_pct < -0.5 ? "up" : "flat"; // weaker EUR = higher fuel cost

  // Crude oil explanation
  const brentExpl = brentDir === "up"
    ? "Raakaöljyn hinta nousussa, nostopaine pumppuun"
    : brentDir === "down"
    ? "Raakaöljyn hinta laskussa, laskupaine pumppuun"
    : "Raakaöljyn hinta vakaa";

  // EUR/USD explanation (inverted: weaker EUR = more expensive imports)
  const fxExpl = fxDir === "up"
    ? "Euro heikkenee, tuontiöljy kallistuu"
    : fxDir === "down"
    ? "Euro vahvistuu, tuontiöljy halpenee"
    : "Valuuttakurssi vakaa";

  // Weekly cycle explanation
  const cycleExpl = cyclePhase === "peak"
    ? "Viikon huippupäivät, hinnat tyypillisesti korkeammat"
    : cyclePhase === "valley"
    ? "Viikon matalahinnat, edullisempi aika tankata"
    : "Viikon keskivaihe";

  // News explanation
  const newsExpl = newsCount > 0
    ? `${newsCount} tuoretta uutisotsikkoa, geopoliittiset riskit huomioitu`
    : "Ei merkittäviä uutisia";

  // Data quality explanation
  const dataExpl = dataQuality?.days > 0
    ? `${dataQuality.days} päivän historia, ${dataQuality.stations || 0} asemaa seurannassa`
    : "Ennuste perustuu tämänhetkiseen markkinatilanteeseen";

  return (
    <Card testId="price-drivers-card" className="p-6">
      <CardLabel className="mb-1">Hinnan muodostuminen</CardLabel>
      <p className="text-[11px] text-muted font-mono mb-4">
        Ennusteen perusteet · ei mallinimiä, ei teknisiä painotuksia
      </p>

      <div className="space-y-2">
        <DriverRow
          icon={Droplet}
          iconColor="#002FA7"
          label="Raakaöljy (Brent)"
          direction={brentDir}
          explanation={brentExpl}
          change={brent?.change_pct}
          testId="driver-brent"
        />
        <DriverRow
          icon={DollarSign}
          iconColor="#10B981"
          label="EUR / USD"
          direction={fxDir}
          explanation={fxExpl}
          change={eurUsd?.change_pct}
          testId="driver-fx"
        />
        <DriverRow
          icon={Calendar}
          iconColor="#F59E0B"
          label="Viikkosykli"
          direction={cyclePhase === "peak" ? "up" : cyclePhase === "valley" ? "down" : "flat"}
          explanation={cycleExpl}
          testId="driver-cycle"
        />
        <DriverRow
          icon={Newspaper}
          iconColor="#8B5CF6"
          label="Uutiset"
          direction="flat"
          explanation={newsExpl}
          testId="driver-news"
        />
        <DriverRow
          icon={Database}
          iconColor="#6B7280"
          label="Data"
          direction="flat"
          explanation={dataExpl}
          testId="driver-data"
        />
      </div>
    </Card>
  );
}
