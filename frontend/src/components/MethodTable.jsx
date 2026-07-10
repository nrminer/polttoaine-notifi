import React from "react";
import { Activity, Anchor, MessageSquareText, Minus, TrendingUp, Waves } from "lucide-react";

import { fmtPrice } from "../lib/utils";
import { formatModelName } from "../lib/modelName";
import { Card, CardLabel } from "./Card";


const METHODS = [
  { key: "persistence", label: "Vertailutaso", detail: "viimeisin klo 21 hinta", Icon: Minus },
  { key: "fundamental_anchor", label: "Markkina-ankkuri", detail: "tuotteet, Brent ja valuutta", Icon: Anchor },
  { key: "exp_smoothing", label: "Tasoitettu trendi", detail: "Holt", Icon: Waves },
  { key: "linear_regression", label: "Lyhyt trendi", detail: "painotettu regressio", Icon: TrendingUp },
  { key: "moving_average", label: "Liukuva keskiarvo", detail: "7 päivää", Icon: Activity },
  { key: "ai_llm", label: "Uutis- ja malliarvio", detail: "", Icon: MessageSquareText },
];

export default function MethodTable({ result }) {
  const methods = result?.methods || {};
  const challenger = result?.challenger_ensemble;

  return (
    <Card testId="method-comparison-card" className="diagnostic-card">
      <div className="diagnostic-card__header">
        <div>
          <CardLabel>Ennusteen perusteet</CardLabel>
          <h3>Mallien arviot</h3>
        </div>
        <span>Tekninen näkymä</span>
      </div>

      <div className="method-list">
        {METHODS.map(({ key, label, detail, Icon }) => {
          const method = methods[key] || {};
          const model = key === "ai_llm" ? formatModelName(method.model) : null;
          const weight = challenger?.weights?.[key];
          return (
            <div className="method-list__row" key={key} data-testid={`method-row-${key}`}>
              <Icon size={17} />
              <div>
                <strong>{label}</strong>
                <span>{model || detail}</span>
              </div>
              <span className="method-list__range">
                {method.confidence_low != null && method.confidence_high != null
                  ? `${fmtPrice(method.confidence_low)}-${fmtPrice(method.confidence_high)}`
                  : ""}
              </span>
              <strong className="method-list__value tnum">
                {method.value != null ? `${fmtPrice(method.value)} €/l` : "-"}
              </strong>
              <span className="method-list__weight tnum">{weight != null ? `${Math.round(weight * 100)} %` : ""}</span>
            </div>
          );
        })}
      </div>

      {challenger?.value != null && (
        <div className="challenger-summary">
          <div>
            <strong>Mallien yhdistelmä, haastaja</strong>
            <span>Ei käytössä ennen mitattua parannusta vertailutasoon.</span>
          </div>
          <strong className="tnum">{fmtPrice(challenger.value)} €/l</strong>
        </div>
      )}
    </Card>
  );
}
