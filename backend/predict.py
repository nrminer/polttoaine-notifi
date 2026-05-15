"""
Polttoainehintojen ennustusalgoritmit Suomeen.

Antaa 4 rinnakkaista ennustetta huomisen hinnalle:
    - moving_average   : 7 päivän liukuva keskiarvo
    - linear_regression: pienimmän neliösumman trendi viim. 30 päivältä
    - exp_smoothing    : Holt-tyylinen taso + trendi (yksinkertaistettu)
    - ai_llm           : Claude Sonnet 4.5 -mallin tuottama ennuste + selitys

Sekä ensemble-keskiarvo painoilla.
"""
from __future__ import annotations
import asyncio
import json
import math
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

import numpy as np


# ---------------- yleiset apurit ----------------

def _safe_prices(prices: list[float]) -> list[float]:
    return [float(p) for p in prices if p is not None and not math.isnan(float(p))]


# ---------------- algoritmit ----------------

def moving_average(prices: list[float], window: int = 7) -> dict:
    p = _safe_prices(prices)
    if not p:
        return {"value": None, "confidence_low": None, "confidence_high": None,
                "explanation": "Ei dataa liukuvan keskiarvon laskemiseen."}
    w = min(window, len(p))
    recent = p[-w:]
    val = float(np.mean(recent))
    std = float(np.std(recent)) or 0.005
    return {
        "value": round(val, 4),
        "confidence_low": round(val - std, 4),
        "confidence_high": round(val + std, 4),
        "explanation": f"{w} päivän liukuva keskiarvo viimeisimmistä havainnoista (σ={std:.4f}).",
    }


def linear_regression(prices: list[float], lookback: int = 30) -> dict:
    p = _safe_prices(prices)
    if len(p) < 3:
        return {"value": None, "confidence_low": None, "confidence_high": None,
                "explanation": "Liian vähän dataa lineaariseen regressioon."}
    n = min(lookback, len(p))
    y = np.array(p[-n:], dtype=float)
    x = np.arange(n, dtype=float)
    # least squares fit
    slope, intercept = np.polyfit(x, y, 1)
    pred = float(slope * n + intercept)  # one step ahead
    residuals = y - (slope * x + intercept)
    sigma = float(np.std(residuals)) or 0.005
    direction = "nouseva" if slope > 0 else ("laskeva" if slope < 0 else "tasainen")
    return {
        "value": round(pred, 4),
        "confidence_low": round(pred - 1.5 * sigma, 4),
        "confidence_high": round(pred + 1.5 * sigma, 4),
        "slope": round(float(slope), 6),
        "explanation": f"Lineaarinen regressio {n} pv:n yli, trendi {direction} ({slope*1000:+.2f} m€/L/pv).",
    }


def exp_smoothing(prices: list[float], alpha: float = 0.4, beta: float = 0.2) -> dict:
    """Holt's linear trend method - simplified."""
    p = _safe_prices(prices)
    if len(p) < 2:
        return {"value": None, "confidence_low": None, "confidence_high": None,
                "explanation": "Liian vähän dataa eksponentiaaliseen tasoitukseen."}
    level = p[0]
    trend = p[1] - p[0]
    errors = []
    for i in range(1, len(p)):
        last_level = level
        forecast = level + trend
        level = alpha * p[i] + (1 - alpha) * forecast
        trend = beta * (level - last_level) + (1 - beta) * trend
        errors.append(p[i] - forecast)
    pred = float(level + trend)
    sigma = float(np.std(errors)) if errors else 0.005
    return {
        "value": round(pred, 4),
        "confidence_low": round(pred - 1.96 * sigma, 4),
        "confidence_high": round(pred + 1.96 * sigma, 4),
        "explanation": f"Holt-tyylinen eksponentiaalinen tasoitus (α={alpha}, β={beta}), σ={sigma:.4f}.",
    }


# ---------------- AI / LLM -ennuste ----------------

async def ai_llm_predict(fuel: str, prices: list[float],
                         dates: list[str],
                         brent: float | None,
                         eur_usd: float | None,
                         live_today_price: float | None = None,
                         news_headlines: list[dict] | None = None,
                         region: str = "Suomi") -> dict:
    """Kysytään Claude Sonnet 4.5 -mallilta ennuste ja perustelu.
    Käyttää uutisia + tämän hetken skrapattua hintaa kontekstina.
    Yrittää 3 kertaa, ja jos Sonnet ei vastaa, kokeilee Claude Haikua."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception as e:
        return {"value": None, "confidence_low": None, "confidence_high": None,
                "explanation": f"LLM-kirjastoa ei voitu ladata: {e}"}

    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return {"value": None, "confidence_low": None, "confidence_high": None,
                "explanation": "EMERGENT_LLM_KEY puuttuu - AI-ennustetta ei voi tehdä."}

    p = _safe_prices(prices)
    if not p:
        return {"value": None, "confidence_low": None, "confidence_high": None,
                "explanation": "Ei hintadataa AI-analyysiin."}

    recent_sample = list(zip(dates[-21:], p[-21:]))
    sample_lines = "\n".join(f"  {d}: {pr:.3f} €/L" for d, pr in recent_sample)

    brent_line = f"{brent:.2f} USD/bbl" if brent is not None else "ei tiedossa"
    fx_line = f"{eur_usd:.4f}" if eur_usd is not None else "ei tiedossa"
    live_line = (f"{live_today_price:.3f} €/L (skrapatun halvimpien otoksen keskiarvo)"
                 if live_today_price is not None else "ei tiedossa")

    today_iso = datetime.now(timezone.utc).date().isoformat()

    # uutiskonteksti
    news_block = ""
    if news_headlines:
        items = []
        for it in news_headlines[:6]:
            age = it.get("age_hours")
            age_str = f"{int(age)} h sitten" if age and age < 48 else \
                      f"{int(age/24)} pv sitten" if age else "?"
            items.append(f"  · [{age_str}] {it['title']} ({it.get('source','')})")
        news_block = "\n\nViimeisimmät polttoaine- ja öljymarkkinauutiset:\n" + "\n".join(items)

    prompt = f"""Olet polttoainemarkkina-analyytikko. Ennusta huomisen ({today_iso}) {fuel}-polttoaineen \
keskihinta {region}ssa. Vastaa AINOASTAAN JSON-objektina ilman muuta tekstiä:

{{
  "predicted_price": <luku desimaalipistein, esim. 1.923>,
  "confidence_low": <luku>,
  "confidence_high": <luku>,
  "direction": "up" | "down" | "flat",
  "explanation": "<2-3 lyhyttä lausetta suomeksi, perustele uutisilla & datalla>",
  "key_drivers": ["<ajuri 1>", "<ajuri 2>", "<ajuri 3>"]
}}

Käytettävissä oleva data:
- Polttoaine: {fuel}
- TÄMÄN HETKEN live-hinta (käytä tätä ankkurina, EI vanhempaa Tilastokeskusdataa): {live_line}
- Viimeisten 21 päivän hintaestimaatit Tilastokeskus + ekstrapolointi:
{sample_lines}
- Brent-raakaöljy: {brent_line}
- EUR/USD: {fx_line}
- Alue: {region}{news_block}

Huomioi:
- Suomessa polttoaineverotus on stabiili (n. 70 % hinnasta verot), joten muutokset ovat \
maltillisia (yleensä alle ±0.05 €/L päivässä).
- Viikonpäivätrendi: hinnat tyypillisesti hieman korkeammat tiistaisin ja keskiviikkoisin, \
matalammat sunnuntaina/maanantaina.
- ANKKUROI ennuste live-hintaan, älä historialliseen Tilastokeskuksen lukuun (joka on usein \
useita kuukausia vanha)."""

    models_to_try = [
        ("anthropic", "claude-opus-4-7"),
        ("anthropic", "claude-opus-4-7-20260416"),
        ("anthropic", "claude-opus-4-6"),
        ("anthropic", "claude-sonnet-4-5-20250929"),
        ("anthropic", "claude-haiku-4-5-20251001"),
    ]

    last_err = "unknown error"
    for provider, model in models_to_try:
        for attempt in range(3):
            try:
                chat = LlmChat(
                    api_key=key,
                    session_id=f"fuel-predict-{fuel}-{today_iso}-{provider}-{model}-{attempt}",
                    system_message="Olet kvantitatiivinen polttoainemarkkina-analyytikko. "
                                  "Vastaat aina pelkkänä JSON-objektina."
                ).with_model(provider, model)

                msg = UserMessage(text=prompt)
                text = await chat.send_message(msg)

                raw = text.strip()
                if raw.startswith("```"):
                    raw = raw.strip("`")
                    if raw.lower().startswith("json"):
                        raw = raw[4:].strip()
                first = raw.find("{")
                last = raw.rfind("}")
                if first != -1 and last > first:
                    raw = raw[first:last + 1]

                data = json.loads(raw)
                pred = float(data.get("predicted_price"))
                lo = float(data.get("confidence_low", pred - 0.02))
                hi = float(data.get("confidence_high", pred + 0.02))
                return {
                    "value": round(pred, 4),
                    "confidence_low": round(lo, 4),
                    "confidence_high": round(hi, 4),
                    "direction": data.get("direction", "flat"),
                    "explanation": data.get("explanation", "AI-analyysi"),
                    "key_drivers": data.get("key_drivers", []),
                    "model": model,
                }
            except Exception as e:
                last_err = f"{type(e).__name__}: {str(e)[:140]}"
                if "Budget" in str(e) or "budget" in str(e):
                    await asyncio.sleep(0.6)
                    if attempt == 2:
                        break
                else:
                    await asyncio.sleep(0.4 * (attempt + 1))

    return {"value": None, "confidence_low": None, "confidence_high": None,
            "explanation": f"AI ei vastannut: {last_err}"}


# ---------------- Ensemble ----------------

def ensemble(predictions: dict) -> dict:
    """Painotettu keskiarvo niistä menetelmistä jotka tuottivat luvun."""
    weights = {
        "moving_average": 0.20,
        "linear_regression": 0.25,
        "exp_smoothing": 0.30,
        "ai_llm": 0.25,
    }
    values = []
    total_w = 0.0
    for k, w in weights.items():
        v = predictions.get(k, {}).get("value")
        if v is not None:
            values.append((float(v), w))
            total_w += w
    if not values:
        return {"value": None, "explanation": "Ei käytettävissä olevia ennusteita."}
    weighted = sum(v * w for v, w in values) / total_w
    spread = max(v for v, _ in values) - min(v for v, _ in values)
    return {
        "value": round(weighted, 4),
        "spread": round(spread, 4),
        "n_methods": len(values),
        "explanation": f"{len(values)} menetelmän painotettu yhdistelmä, hajonta {spread:.4f} €/L.",
    }


# ---------------- pääfunktio ----------------

async def predict_tomorrow(fuel: str,
                           dates: list[str],
                           prices: list[float],
                           brent: float | None,
                           eur_usd: float | None,
                           live_today_price: float | None = None,
                           news_headlines: list[dict] | None = None,
                           region: str = "Suomi") -> dict:
    """Aja kaikki algoritmit ja palauta ennusteet + ensemble.

    Jos `live_today_price` on annettu, korvaa historian viimeinen piste
    sillä — jotta MA/LR/ES kaikki ennustavat live-anchorin lähistöä eivätkä
    vanhentuneen Tilastokeskusarvon.
    """
    # ankkuroi viimeinen historian piste live-skrapaukseen jos saatavilla
    if live_today_price is not None and prices:
        prices = list(prices)
        prices[-1] = float(live_today_price)

    ma = moving_average(prices, 7)
    lr = linear_regression(prices, 30)
    es = exp_smoothing(prices)
    ai = await ai_llm_predict(fuel, prices, dates, brent, eur_usd,
                              live_today_price=live_today_price,
                              news_headlines=news_headlines,
                              region=region)

    predictions = {
        "moving_average": ma,
        "linear_regression": lr,
        "exp_smoothing": es,
        "ai_llm": ai,
    }
    ens = ensemble(predictions)
    return {
        "fuel": fuel,
        "region": region,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_price": round(_safe_prices(prices)[-1], 4) if _safe_prices(prices) else None,
        "live_anchor": live_today_price,
        "methods": predictions,
        "ensemble": ens,
    }
