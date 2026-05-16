"""
Polttoainehintojen ennustusalgoritmit Suomeen.

Antaa rinnakkaisia ennusteita huomisen hinnalle:
    - moving_average     : N päivän liukuva keskiarvo (päivätason häntä)
    - linear_regression  : pienimmän neliösumman trendi, projisoitu +1 KALENTERIPÄIVÄ
    - exp_smoothing      : Holt-tyylinen taso + trendi (päivätason häntä)
    - fundamental_anchor : live-hinta + Brent-EUR-pass-through + viikonpäivä + momentum
    - ai_llm             : Claude Opus 4.7 (uutiset + geopoliittinen riski)

Sekä datalaatutietoinen ensemble-yhdistelmä, joka ankkuroidaan live-hintaan.

Suunnitteluperiaate day-ahead-ennusteelle:
  KAIKKI hintadata on live-skrapattua ja kerätään vasta tästä päivästä
  alkaen (ei vanhaa Tilastokeskus-kuukausihistoriaa). Alkuvaiheessa
  havaintoja on vähän, joten menetelmät ovat päivämäärätietoisia ja
  ankkuroituvat tuoreimpaan live-hintaan; harvalla datalla nojataan
  fundamental_anchoriin ja AI:hin.
"""
from __future__ import annotations
import asyncio
import json
import math
import os
from datetime import datetime, timezone

import numpy as np


# ---------------- yleiset apurit ----------------

def _safe_prices(prices: list[float]) -> list[float]:
    return [float(p) for p in prices if p is not None and not math.isnan(float(p))]


def _parse_date(s: str):
    return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()


def _daily_tail(dates, prices, max_gap: int = 3, min_len: int = 4):
    """Palauta perän (date, price) -parit niin kauan kuin peräkkäisten
    havaintojen aikaväli on ≤ max_gap päivää — eli aito päivätason jakso
    live-skrapatuista capture-havainnoista."""
    pairs = [(d, p) for d, p in zip(dates or [], prices or [])
             if p is not None and d]
    if len(pairs) < min_len:
        return []
    tail = [pairs[-1]]
    for i in range(len(pairs) - 1, 0, -1):
        try:
            if (_parse_date(pairs[i][0]) - _parse_date(pairs[i - 1][0])).days <= max_gap:
                tail.append(pairs[i - 1])
            else:
                break
        except Exception:
            break
    tail.reverse()
    return tail if len(tail) >= min_len else []


# Suomen pumppuhinta liikkuu päivässä käytännössä alle tämän
_MAX_DAILY_MOVE = 0.06
# 1 tynnyri = 159 L
_BBL_LITRES = 159.0
# Konflikti-/tarjontahäiriösanat uutisseulontaan
_CONFLICT_KEYWORDS = (
    "sota", "sodan", "sodas", "konflikti", "kriisi", "isku", "hyökkä",
    "pakote", "pakott", "saarto", "embargo", "tuotantoleikk", "rajoit",
    "opec", "hormuz", "lähi-it", "lahi-it", "iran", "israel", "ukrain",
    "venäj", "venaj", "war", "strike", "sanction", "blockade", "attack",
    "supply", "outage", "refinery fire", "jalostamo",
)


def _scan_conflict(news_headlines) -> list[str]:
    """Palauta uutisotsikot jotka viittaavat konfliktiin / tarjontahäiriöön."""
    hits = []
    for it in (news_headlines or []):
        title = (it.get("title") or "")
        low = title.lower()
        if any(kw in low for kw in _CONFLICT_KEYWORDS):
            hits.append(title)
    return hits[:4]


# ---------------- tilastolliset algoritmit ----------------

def moving_average(prices: list[float], window: int = 7, dates=None) -> dict:
    p = _safe_prices(prices)
    if not p:
        return {"value": None, "confidence_low": None, "confidence_high": None,
                "explanation": "Ei dataa liukuvan keskiarvon laskemiseen."}
    seg = p
    tag = ""
    if dates:
        dt = _daily_tail(dates, prices, max_gap=3, min_len=window)
        if len(dt) >= window:
            seg = [x[1] for x in dt]
            tag = ", päivätason häntä"
    w = min(window, len(seg))
    recent = seg[-w:]
    val = float(np.mean(recent))
    std = max(float(np.std(recent)), 0.005)
    return {
        "value": round(val, 4),
        "confidence_low": round(val - std, 4),
        "confidence_high": round(val + std, 4),
        "explanation": f"{w} pv liukuva keskiarvo (σ={std:.4f}{tag}).",
    }


def linear_regression(prices: list[float], lookback: int = 30, dates=None) -> dict:
    """Pienimmän neliösumman trendi, x = KALENTERIPÄIVÄ-offset, projisointi +1 pv.

    Kun data on aitoa päivätason häntää, käytetään sitä; muuten viimeiset
    `lookback` pistettä mutta x silti päivinä (ei indeksinä) — jotta
    kuukausidata ei tuota valheellista jättidaily-trendiä."""
    p = _safe_prices(prices)
    if len(p) < 3:
        return {"value": None, "confidence_low": None, "confidence_high": None,
                "explanation": "Liian vähän dataa lineaariseen regressioon."}

    seg_dates = None
    if dates and len(dates) == len(prices):
        dt = _daily_tail(dates, prices, max_gap=3, min_len=5)
        if len(dt) >= 5:
            seg_dates = [x[0] for x in dt]
            yvals = [x[1] for x in dt]
        else:
            n = min(lookback, len(p))
            yvals = p[-n:]
            seg_dates = list(dates[-n:])
    else:
        n = min(lookback, len(p))
        yvals = p[-n:]

    y = np.array(yvals, dtype=float)
    if seg_dates:
        try:
            d0 = _parse_date(seg_dates[0])
            x = np.array([(_parse_date(d) - d0).days for d in seg_dates], dtype=float)
            target_x = (_parse_date(seg_dates[-1]) - d0).days + 1.0
        except Exception:
            x = np.arange(len(y), dtype=float)
            target_x = float(len(y))
    else:
        x = np.arange(len(y), dtype=float)
        target_x = float(len(y))

    if np.ptp(x) == 0:
        return {"value": round(float(y[-1]), 4),
                "confidence_low": round(float(y[-1]) - 0.01, 4),
                "confidence_high": round(float(y[-1]) + 0.01, 4),
                "slope": 0.0,
                "explanation": "Vain yksi aikapiste — trendi tasainen."}

    slope, intercept = np.polyfit(x, y, 1)
    pred = float(slope * target_x + intercept)
    residuals = y - (slope * x + intercept)
    sigma = max(float(np.std(residuals)), 0.005)
    direction = "nouseva" if slope > 0 else ("laskeva" if slope < 0 else "tasainen")
    return {
        "value": round(pred, 4),
        "confidence_low": round(pred - 1.5 * sigma, 4),
        "confidence_high": round(pred + 1.5 * sigma, 4),
        "slope": round(float(slope), 6),
        "explanation": (f"Lineaarinen regressio {len(y)} pisteestä, "
                        f"trendi {direction} ({slope*1000:+.2f} m€/L/pv)."),
    }


def exp_smoothing(prices: list[float], alpha: float = 0.4, beta: float = 0.2,
                  dates=None) -> dict:
    """Holt's linear trend. Ajetaan aidolle päivätason hännälle jos saatavilla
    (muuten kuukausi+päivä-sekoitus tuottaisi väärän trendin)."""
    p = _safe_prices(prices)
    if len(p) < 2:
        return {"value": None, "confidence_low": None, "confidence_high": None,
                "explanation": "Liian vähän dataa eksponentiaaliseen tasoitukseen."}
    seg = p
    tag = ""
    if dates:
        dt = _daily_tail(dates, prices, max_gap=3, min_len=4)
        if len(dt) >= 4:
            seg = [x[1] for x in dt]
            tag = ", päivätason häntä"
    level = seg[0]
    trend = seg[1] - seg[0]
    errors = []
    for i in range(1, len(seg)):
        last_level = level
        forecast = level + trend
        level = alpha * seg[i] + (1 - alpha) * forecast
        trend = beta * (level - last_level) + (1 - beta) * trend
        errors.append(seg[i] - forecast)
    pred = float(level + trend)
    sigma = max(float(np.std(errors)), 0.005) if errors else 0.005
    return {
        "value": round(pred, 4),
        "confidence_low": round(pred - 1.96 * sigma, 4),
        "confidence_high": round(pred + 1.96 * sigma, 4),
        "explanation": f"Holt-tasoitus (α={alpha}, β={beta}), σ={sigma:.4f}{tag}.",
    }


# ---------------- fundamentaalinen ankkurimalli ----------------

def fundamental_anchor(dates, prices, live_anchor,
                       brent, eur_usd, brent_chg, eur_usd_chg,
                       tomorrow_weekday: int, conflict: bool = False) -> dict:
    """Fysikaalisesti motivoitu day-ahead-malli:

        ennuste = live-ankkuri
                + Brent-EUR-pass-through (jo hinnoiteltu geopol. riski)
                + EUR/USD-vaikutus
                + päivätason momentum (aito päivähäntä)
                + viikonpäiväefekti

    Tulos rajataan ±0.06 €/L live-hinnasta (Suomen päivämuutos ei ylitä tätä)."""
    p = _safe_prices(prices)
    base = live_anchor if live_anchor is not None else (p[-1] if p else None)
    if base is None:
        return {"value": None, "confidence_low": None, "confidence_high": None,
                "explanation": "Ei live-ankkuria fundamentaalimalliin."}

    parts: list[str] = []

    # 1) Brent-EUR-pass-through. Brent EUR/L = (USD/bbl ÷ EURUSD) ÷ 159.
    crude_adj = 0.0
    if brent is not None and eur_usd not in (None, 0):
        brent_eur_l = (brent / eur_usd) / _BBL_LITRES
        d_crude = brent_eur_l * brent_chg if brent_chg is not None else 0.0
        # EUR heikkenee (eur_usd_chg < 0) → tuontiöljy kallistuu
        d_fx = (-brent_eur_l * eur_usd_chg) if eur_usd_chg is not None else 0.0
        # Vähittäishinta seuraa viiveellä → huomenna näkyy vain osa liikkeestä.
        frac = 0.25
        crude_adj = frac * (d_crude + d_fx)
        crude_adj = max(-0.035, min(0.035, crude_adj))
        if abs(crude_adj) >= 0.0005:
            parts.append(f"Brent-EUR {crude_adj*1000:+.1f} m€/L")

    # 2) päivätason momentum AIDOSTA päivähännästä
    mom_adj = 0.0
    dt = _daily_tail(dates, prices, max_gap=3, min_len=4)
    if len(dt) >= 4:
        seg = [x[1] for x in dt][-7:]
        xs = np.arange(len(seg), dtype=float)
        slope = float(np.polyfit(xs, np.array(seg, float), 1)[0])
        mom_adj = max(-0.02, min(0.02, slope))
        if abs(mom_adj) >= 0.0005:
            parts.append(f"momentum {mom_adj*1000:+.1f} m€/L")

    # 3) viikonpäiväefekti (Python: ma=0 … su=6)
    wd_adj = 0.0
    if tomorrow_weekday in (1, 2):       # ti, ke
        wd_adj = 0.004
    elif tomorrow_weekday in (6, 0):     # su, ma
        wd_adj = -0.004
    if wd_adj:
        parts.append(f"viikonpäivä {wd_adj*1000:+.1f} m€/L")

    pred = base + crude_adj + mom_adj + wd_adj
    pred = max(base - _MAX_DAILY_MOVE, min(base + _MAX_DAILY_MOVE, pred))

    # konfliktitilanteessa epävarmuus kasvaa
    band = 0.020 if conflict else 0.012
    expl = "Ankkuri " + f"{base:.3f} €/L"
    if parts:
        expl += " + " + ", ".join(parts)
    if conflict:
        expl += " · geopol. riski → leveämpi väli"
    return {
        "value": round(pred, 4),
        "confidence_low": round(pred - band, 4),
        "confidence_high": round(pred + band, 4),
        "explanation": expl + ".",
    }


# ---------------- AI / LLM -ennuste ----------------

async def ai_llm_predict(fuel: str, prices: list[float],
                         dates: list[str],
                         brent: float | None,
                         eur_usd: float | None,
                         live_today_price: float | None = None,
                         news_headlines: list[dict] | None = None,
                         region: str = "Suomi",
                         brent_chg: float | None = None,
                         eur_usd_chg: float | None = None) -> dict:
    """Claude Opus 4.7 -ennuste. Hoitaa ETUPAINOTTEISEN geopoliittisen riskin:
    konflikti-/tarjontahäiriöuutiset jotka Brent ei vielä täysin hinnoittele."""
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

    # päivätaso
    slope_str = "ei laskettavissa"
    dt = _daily_tail(dates, prices, max_gap=3, min_len=4)
    if len(dt) >= 4:
        seg = [x[1] for x in dt][-7:]
        slope_val = (seg[-1] - seg[0]) / max(1, len(seg) - 1) * 1000
        slope_str = f"{slope_val:+.2f} m€/L/pv (aito päivähäntä, {len(seg)} pv)"
    elif len(p) >= 2:
        slope_str = "ei vielä luotettavaa trendiä (liian vähän päivähavaintoja)"

    n_real_daily = len(dt)
    if n_real_daily < 10:
        data_quality_note = (
            f"DATALAATU: vain {n_real_daily} live-skrapattua päivähavaintoa "
            "(historia kerätään vasta tästä päivästä alkaen). OHUT — mainitse "
            "selityksessä että ennuste nojaa pääosin live-ankkuriin ja "
            "epävarmuus on suuri."
        )
    else:
        data_quality_note = (
            f"DATALAATU: {n_real_daily} live-skrapattua päivähavaintoa. "
            "Riittävä."
        )

    brent_line = f"{brent:.2f} USD/bbl" if brent is not None else "ei tiedossa"
    if brent_chg is not None:
        brent_line += f" (≈{brent_chg*100:+.1f} % viim. ~5 pv)"
    fx_line = f"{eur_usd:.4f}" if eur_usd is not None else "ei tiedossa"
    if eur_usd_chg is not None:
        fx_line += f" (≈{eur_usd_chg*100:+.1f} % viim. ~5 pv)"
    live_line = (f"{live_today_price:.3f} €/L"
                 if live_today_price is not None else "ei tiedossa")

    today_iso = datetime.now(timezone.utc).date().isoformat()
    wd = ["maanantai", "tiistai", "keskiviikko", "torstai",
          "perjantai", "lauantai", "sunnuntai"]
    weekday_fi = wd[datetime.now(timezone.utc).weekday()]
    tomorrow_weekday_fi = wd[(datetime.now(timezone.utc).weekday() + 1) % 7]

    conflict_hits = _scan_conflict(news_headlines)

    news_block = ""
    if news_headlines:
        items = []
        for it in news_headlines[:6]:
            age = it.get("age_hours")
            age_str = f"{int(age)} h sitten" if age and age < 48 else \
                      f"{int(age/24)} pv sitten" if age else "?"
            items.append(f"  · [{age_str}] {it['title']} ({it.get('source', '')})")
        news_block = "\n\nTuoreimmat polttoaine- ja öljyuutiset:\n" + "\n".join(items)

    if conflict_hits:
        geo_block = (
            "\n\n=== GEOPOLIITTINEN RISKI (havaittu uutisista) ===\n"
            + "\n".join(f"  ⚠ {t}" for t in conflict_hits)
            + "\nArvioi: onko tämä JO Brentin hinnassa (älä tuplalaske) vai "
            "eskaloituuko se? Eskaloituva konflikti = etupainotteinen "
            "nousupaine + leveämpi epävarmuusväli."
        )
    else:
        geo_block = ("\n\n=== GEOPOLIITTINEN RISKI ===\n  Ei selviä "
                     "konflikti-/tarjontahäiriösignaaleja uutisissa.")

    system_message = (
        "Olet Mikko, Suomen vähittäispolttoainemarkkinoiden kvantitatiivinen "
        "analyytikko — 14 v kokemusta Neste/ABC/Teboil/Shell/St1-hinnoittelusta. "
        "Ydinperiaatteesi:\n"
        "1. ANKKURI: Live-hinta on totuus. KAIKKI data on tänä päivänä ja sen "
        "jälkeen live-skrapattua — ei vanhaa tilastohistoriaa. Ankkuroi "
        "ennuste aina tuoreimpaan live-hintaan.\n"
        "2. VERO VAKIO: ~70 % pump-hinnasta veroja → päivämuutos yleensä "
        "alle ±0,05 €/L.\n"
        "3. BRENT-VIIVE: Brent-muutos näkyy pumpulla 3–10 pv viiveellä; "
        "Neste nopein, ABC/Teboil seuraavat.\n"
        "4. EUR/USD-BETA: 1 % EUR-heikennys → ~+0,003–0,005 €/L (tuontiöljy "
        "kallistuu).\n"
        "5. VIIKONPÄIVÄ: Ti–Ke tyypillisesti +0,5–1,5 ¢/L vs. Su–Ma. Huominen "
        "on " + tomorrow_weekday_fi + ".\n"
        "6. MOMENTUM: aito päivätason kaltevuus on paras lyhytsignaali — älä "
        "taistele trendiä vastaan ilman katalyyttiä.\n"
        "7. GEOPOLITIIKKA: sodat, konfliktit, OPEC+-leikkaukset, saarrot ja "
        "pakotteet nostavat Brentiä → pumppuhintaa. ÄLÄ tuplalaske jo "
        "Brentissä näkyvää riskiä; lisää preemio vain jos konflikti "
        "ESKALOITUU eikä ole vielä täysin hinnoiteltu. Epävarmuus kasvaa.\n"
        "Vastaat AINA pelkkänä JSON-objektina, ei muuta tekstiä."
    )

    prompt = (
        f"Ennusta {fuel}-pump-hinta huomiselle ({today_iso}, "
        f"{tomorrow_weekday_fi}) alueella {region}. Tänään {weekday_fi}.\n\n"
        f"=== HINTA-ANKKURI (pääankkuri) ===\nLive nyt: {live_line}\n\n"
        f"=== MOMENTUMSIGNAALI ===\n7 pv trendi: {slope_str}\n\n"
        f"=== LIVE-SKRAPATTU PÄIVÄHISTORIA (kerätty tästä päivästä alkaen) ===\n"
        f"{sample_lines}\n\n"
        f"=== DATALAATU ===\n{data_quality_note}\n\n"
        f"=== MAKROINPUTTEJA ===\nBrent: {brent_line}\nEUR/USD: {fx_line}"
        f"{news_block}{geo_block}\n\n"
        f"=== TEHTÄVÄSI ===\n"
        f"1. Brent/FX-paine + 7 pv momentum → arvioi pre-tax muutos vs. tänään.\n"
        f"2. Lisää geopoliittinen preemio VAIN jos eskaloituva, ei jo "
        f"hinnoiteltu riski.\n"
        f"3. Lisää viikonpäiväefekti ({tomorrow_weekday_fi}).\n"
        f"4. Ankkuroi tulos live-hintaan (ei historiaan); päivämuutos "
        f"realistisesti alle ±0,05 €/L ilman selvää katalyyttiä.\n"
        f"5. Confidence-väli: normaali ±0,008–0,015; korkea volatiliteetti / "
        f"konflikti ±0,02–0,04 €/L.\n\n"
        f"Palauta VAIN tämä JSON:\n"
        f'{{\n'
        f'  "predicted_price": <€/L, 3 desimaalia>,\n'
        f'  "confidence_low": <€/L>,\n'
        f'  "confidence_high": <€/L>,\n'
        f'  "direction": "up" | "down" | "flat",\n'
        f'  "explanation": "<2–3 lausetta suomeksi: ajuri, suunta, miksi>",\n'
        f'  "key_drivers": ["<tärkein>", "<toinen>", "<kolmas>"]\n'
        f'}}'
    )

    models_to_try = [
        ("anthropic", "claude-opus-4-7"),
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
                    system_message=system_message,
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


# ---------------- ensemble ----------------

def ensemble(predictions: dict, live_anchor: float | None = None,
             n_daily: int = 0) -> dict:
    """Datalaatutietoinen painotettu yhdistelmä.

    Kun aitoa päivädataa on vähän (kuukausidata hallitsee), tilastomenetelmät
    ylisovittavat → painotetaan ankkuripohjaista fundamental_anchoria ja AI:ta.
    Lopputulos rajataan ±0.06 €/L live-hinnasta."""
    if n_daily >= 14:
        weights = {
            "fundamental_anchor": 0.30,
            "ai_llm": 0.22,
            "exp_smoothing": 0.18,
            "linear_regression": 0.17,
            "moving_average": 0.13,
        }
        mode = "riittävä päivädata"
    else:
        # ohut / kuukausivetoinen: luota ankkuriin + AI:hin
        weights = {
            "fundamental_anchor": 0.48,
            "ai_llm": 0.30,
            "moving_average": 0.12,
            "exp_smoothing": 0.06,
            "linear_regression": 0.04,
        }
        mode = "ohut päivädata → ankkuripainotus"

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

    clamped = False
    if live_anchor is not None:
        lo, hi = live_anchor - _MAX_DAILY_MOVE, live_anchor + _MAX_DAILY_MOVE
        if weighted < lo or weighted > hi:
            weighted = max(lo, min(hi, weighted))
            clamped = True

    spread = max(v for v, _ in values) - min(v for v, _ in values)
    expl = f"{len(values)} menetelmää ({mode}), hajonta {spread:.4f} €/L"
    if clamped:
        expl += " · rajattu ±0.06 €/L live-hinnasta"
    return {
        "value": round(weighted, 4),
        "spread": round(spread, 4),
        "n_methods": len(values),
        "explanation": expl + ".",
    }


# ---------------- pääfunktio ----------------

async def predict_tomorrow(fuel: str,
                           dates: list[str],
                           prices: list[float],
                           brent: float | None,
                           eur_usd: float | None,
                           live_today_price: float | None = None,
                           news_headlines: list[dict] | None = None,
                           region: str = "Suomi",
                           brent_chg: float | None = None,
                           eur_usd_chg: float | None = None) -> dict:
    """Aja kaikki menetelmät ja palauta ennusteet + datalaatutietoinen ensemble.

    `brent_chg` / `eur_usd_chg` = murto-osamuutos (esim. 0.03 = +3 %) viim.
    ~5 pörssipäivältä; käytetään Brent-EUR-pass-throughiin. Jos live-hinta on
    annettu, se on ankkuri sekä historian viimeisenä pisteenä että ensemble-
    rajauksessa."""
    if live_today_price is not None and prices:
        prices = list(prices)
        prices[-1] = float(live_today_price)

    tomorrow_weekday = (datetime.now(timezone.utc).weekday() + 1) % 7
    conflict = bool(_scan_conflict(news_headlines))
    n_daily = len(_daily_tail(dates, prices, max_gap=3, min_len=4))

    ma = moving_average(prices, 7, dates=dates)
    lr = linear_regression(prices, 30, dates=dates)
    es = exp_smoothing(prices, dates=dates)
    fa = fundamental_anchor(
        dates, prices, live_today_price, brent, eur_usd,
        brent_chg, eur_usd_chg, tomorrow_weekday, conflict=conflict,
    )
    ai = await ai_llm_predict(
        fuel, prices, dates, brent, eur_usd,
        live_today_price=live_today_price,
        news_headlines=news_headlines, region=region,
        brent_chg=brent_chg, eur_usd_chg=eur_usd_chg,
    )

    predictions = {
        "moving_average": ma,
        "linear_regression": lr,
        "exp_smoothing": es,
        "fundamental_anchor": fa,
        "ai_llm": ai,
    }
    ens = ensemble(predictions, live_anchor=live_today_price, n_daily=n_daily)
    return {
        "fuel": fuel,
        "region": region,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_price": round(_safe_prices(prices)[-1], 4) if _safe_prices(prices) else None,
        "live_anchor": live_today_price,
        "conflict_signal": conflict,
        "n_daily_points": n_daily,
        "methods": predictions,
        "ensemble": ens,
    }
