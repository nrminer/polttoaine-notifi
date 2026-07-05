import React, { useMemo, useState } from "react";
import { Fuel, Gauge, ReceiptText } from "lucide-react";
import { fmtPrice } from "../lib/utils";

const DEFAULT_AMOUNT = 40;
const E98_PREMIUM_EUR_L = 0.1;

const TEXT = {
  title: "Mit\u00e4 euroilla saa asemalla",
  euro: "\u20ac",
  euroPerLiter: "\u20ac/L",
  sameAmount: "sama m\u00e4\u00e4r\u00e4 kuin keskihinnalla",
  more: "enemm\u00e4n",
  less: "v\u00e4hemm\u00e4n",
};

function num(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function litersFor(amount, price) {
  if (price == null || price <= 0) return null;
  return amount / price;
}

function buildRow({ id, label, source, amount, derived = false }) {
  const cheapestPrice = num(source?.national_min);
  const averagePrice = num(source?.cheap_sample_avg);
  const liters = litersFor(amount, cheapestPrice);
  const averageLiters = litersFor(amount, averagePrice);
  const extraLiters = liters != null && averageLiters != null ? liters - averageLiters : null;

  return {
    id,
    label,
    cheapestPrice,
    averagePrice,
    liters,
    averageLiters,
    extraLiters,
    derived,
  };
}

export function buildPumpRows({ amount = DEFAULT_AMOUNT, petrol95, diesel }) {
  const normalizedAmount = Math.max(0, Number(amount) || 0);
  const e95Min = num(petrol95?.national_min);
  const e95Avg = num(petrol95?.cheap_sample_avg);

  const petrol98 =
    e95Min == null && e95Avg == null
      ? null
      : {
          national_min: e95Min == null ? null : e95Min + E98_PREMIUM_EUR_L,
          cheap_sample_avg: e95Avg == null ? null : e95Avg + E98_PREMIUM_EUR_L,
        };

  return [
    buildRow({ id: "95e", label: "95E", source: petrol95, amount: normalizedAmount }),
    buildRow({ id: "98e", label: "98E", source: petrol98, amount: normalizedAmount, derived: true }),
    buildRow({ id: "diesel", label: "Diesel", source: diesel, amount: normalizedAmount }),
  ];
}

function fmtLiters(value) {
  return value == null ? "-" : `${value.toFixed(2)} L`;
}

function fmtExtra(value) {
  if (value == null) return "odottaa keskihintaa";
  if (Math.abs(value) < 0.005) return TEXT.sameAmount;
  return `${value > 0 ? "+" : ""}${value.toFixed(2)} L ${value > 0 ? TEXT.more : TEXT.less} kuin keskihinnalla`;
}

export default function FuelPumpCalculator({ petrol95, diesel }) {
  const [amount, setAmount] = useState(DEFAULT_AMOUNT);
  const rows = useMemo(() => buildPumpRows({ amount, petrol95, diesel }), [amount, petrol95, diesel]);
  const handleAmountChange = (event) => setAmount(event.target.value);

  return (
    <section className="fuel-pump" data-testid="fuel-pump-card" aria-labelledby="fuel-pump-title">
      <div className="fuel-pump__tower" aria-hidden="true">
        <div className="fuel-pump__face">
          <Gauge size={28} />
          <span>{TEXT.euroPerLiter}</span>
        </div>
        <div className="fuel-pump__hose" />
      </div>

      <div className="fuel-pump__body">
        <div className="fuel-pump__header">
          <div>
            <span className="mono-label">Tankkauslaskuri</span>
            <h2 id="fuel-pump-title">{TEXT.title}</h2>
          </div>
          <label className="fuel-pump__amount">
            <span>Budjetti</span>
            <input
              data-testid="fuel-pump-amount-input"
              type="number"
              min="1"
              step="1"
              value={amount}
              onChange={handleAmountChange}
              onInput={handleAmountChange}
              aria-label="Tankkausbudjetti euroina"
            />
            <strong>{TEXT.euro}</strong>
          </label>
        </div>

        <div className="fuel-pump__rows">
          {rows.map((row) => (
            <article className="fuel-pump__row" key={row.id} data-testid={`fuel-pump-row-${row.id}`}>
              <div className="fuel-pump__fuel">
                <Fuel size={18} />
                <div>
                  <strong>{row.label}</strong>
                  <span>{row.derived ? "95E + 10 snt/L" : "livehinta"}</span>
                </div>
              </div>
              <div>
                <span className="fuel-pump__label">Halvin</span>
                <strong className="tnum" data-testid={`fuel-pump-price-${row.id}`}>
                  {fmtPrice(row.cheapestPrice)}
                </strong>
              </div>
              <div>
                <span className="fuel-pump__label">Saat</span>
                <strong className="tnum" data-testid={`fuel-pump-liters-${row.id}`}>
                  {fmtLiters(row.liters)}
                </strong>
              </div>
              <div className="fuel-pump__extra">
                <ReceiptText size={16} />
                <span data-testid={`fuel-pump-extra-${row.id}`}>{fmtExtra(row.extraLiters)}</span>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}