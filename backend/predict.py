"""
Polttoainehintojen ennustusalgoritmit Suomeen.

Antaa rinnakkaisia ennusteita huomisen hinnalle:
    - moving_average     : N päivän liukuva keskiarvo (päivätason häntä)
    - linear_regression  : recency-painotettu PNS-trendi (≤14 pv häntä), +1 KALENTERIPÄIVÄ
    - exp_smoothing      : Holt-tyylinen taso + trendi (päivätason häntä)
    - fundamental_anchor : live-hinta + Brent-EUR-pass-through + viikonpäivä + momentum
    - ai_llm             : Claude Fable 5 (uutiset + geopoliittinen riski)
    - weekly_cycle       : viikoittainen hinnoittelurytmi (hypyt, syklivaihe)

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
from datetime import datetime, timedelta, timezone

import numpy as np
from llm_client import LLMConfigError, configured_model, send_message
import weekly_cycle as wc_mod
import fi_holidays


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
# (poikkeus: tunnettu veromuutos voimaan → clamppia laajennetaan steppin verran)
_MAX_DAILY_MOVE = 0.06
# Breaking news → severity-based multiplier:
# severity 1-3 (moderate): 1.33x = ±0.08 EUR/L
# severity 4-6 (major):     1.67x = ±0.10 EUR/L
# severity 7-10 (critical): 2.50x = ±0.15 EUR/L
def _breaking_news_multiplier(severity: int) -> float:
    """Return clamp multiplier based on breaking news severity (0-10).
    
    Calibrated to avoid over-reaction while allowing material moves:
    - 0: 1.0x (no breaking news)
    - 1-3: 1.33x (moderate events)
    - 4-6: 1.67x (major supply/geopolitical events)
    - 7-10: 2.50x (critical market-moving events)
    """
    if severity >= 7:
        return 2.50
    elif severity >= 4:
        return 1.67
    elif severity >= 1:
        return 1.33
    else:
        return 1.0
# 1 tynnyri = 159 L
_BBL_LITRES = 159.0
# 1 US gallon = 3.785… L (RBOB / HO -futuurit hinnoitellaan USD/gallona)
_GAL_LITRES = 3.785411784
# Lag-feature-päivät, jotka näytetään AI-promptissa eksplisiittisesti
_LAG_DAYS = (1, 2, 3, 7)

# --- Pass-through-priorit (KÄYTÄNNÖN PRIORIT, EI MITATTU SUOMESTA) ---
# Nämä ovat ennalta valittuja painokertoimia joita kalibroidaan vasta kun
# daily_tracker-captureita kertyy riittävästi. Pidämme molemmat
# konservatiivisina ja yhtä suurina, jotta emme silmäkalibroi tuloksia.
# Suuntavalinta refined > Brent perustuu yleiseen markkinaintuitioon
# (jalostettu tuote on lähempänä pumppupuolta), ei mitattuun Suomi-spesifiseen
# tutkimustulokseen.
_BRENT_PASSTHROUGH_FRAC = 0.25   # ALKUPRIORI — säilytetty alkuperäinen
_REFINED_PASSTHROUGH_FRAC = 0.30  # ALKUPRIORI — vain hieman Brentiä korkeampi

# --- Self-training: bias-korjauksen vaimennus ---
# Nämä OVAT VALITTUJA INSINÖÖRIVAKIOITA, EIVÄT MITATTUJA ARVOJA.
# Tarkoitus: estää että alustava melu pienestä otoksesta vääristää
# fundamental_anchorin lähtötasoa. Linear damping (n / _BIAS_FULL_N) on
# arvattu heuristiikka — vakaampi vaihtoehto olisi Bayesian credibility
# weighting; tämä on kuitenkin yksinkertainen ja läpinäkyvä alku.
# Säätämällä näitä voi vaihtaa pehmeämpään tai aggressiivisempaan
# self-correctioniin ilman, että algoritmin logiikka muuttuu.
_BIAS_MIN_N = 8       # alle tämän → korjaus = 0 (estää melun)
_BIAS_FULL_N = 25     # tällä otoksella koko bias vähennetään
_BIAS_MAX = 0.020     # turvaraja ±2 snt/L (osa _MAX_DAILY_MOVE-budjetista)

# --- Lineaarinen regressio: day-ahead-viritys ---
# VALITTUJA INSINÖÖRIPRIOREJA, EI SUOMI-MITATTUJA. Toteutunut tarkkuus
# (daily_tracker) osoitti tasapainoisen koko hännän OLS:n heikoimmaksi
# menetelmäksi: kuukauden takainen hintaregiimi vetää huomisen trendiä.
# Day-ahead-ikkunaan rajataan tuore osa hännästä ja painotetaan
# eksponentiaalisesti tuoreutta; ennuste rajataan fysikaaliseen
# päivämuutosbudjettiin (_MAX_DAILY_MOVE) kuten muutkin ankkurimenetelmät.
_LR_MAX_WINDOW = 14       # max pistettä aidosta päivähännästä regressioon
_LR_HALFLIFE_DAYS = 5.0   # recency-painon puoliintumisaika (pv)

# --- Fundamental anchor: kohinanvaimennus ---
# VALITTUJA INSINÖÖRIPRIOREJA, EI SUOMI-MITATTUJA. "Halvin asema Suomessa"
# on yhden scrapen havainto jonka asemajoukko vaihtelee päivästä toiseen →
# yksittäinen live-lukema on kohinainen syöte. Ankkuri sekoitetaan kevyesti
# 3 pv mediaaniin (säilyttää ankkuroinnin, vaimentaa yksittäisen scrapen
# poikkeaman). Momentum-slope ≤7 pisteestä on itsessään kohinainen
# estimaatti → kutistetaan kohti nollaa ennen käyttöä (James-Stein-henkinen
# shrinkage, kerroin valittu eikä mitattu).
_ANCHOR_LIVE_W = 0.70     # live-hinnan paino; loppu 3 pv mediaanille
_MOM_SHRINK = 0.5         # momentum-slopen kutistuskerroin
_FA_BAND_MIN = 0.008      # kalibroidun luottamusvälin alaraja (€/L)
_FA_BAND_MAX = 0.035      # kalibroidun luottamusvälin yläraja (€/L)

# --- Empiirinen viikonpäivä-adj ---
# Kun aitoa päivähäntää on tarpeeksi (ks. _WD_MIN_PER_DAY), lasketaan
# kunkin viikonpäivän keskimääräinen poikkeama lokaalin keskiarvon
# ympäriltä; käytetään huomisen viikonpäivä-adj:na fundamental_anchorissa
# kiinteän priorin (±0.004 €/L) sijaan. Kun otos on lyhyt, palautetaan
# None ja kutsuja voi nojata prioriin — kyseessä on ASTEITTAINEN siirtymä
# priorin ja datan välillä.
_WD_MIN_TOTAL = 21              # min. aitoa päivähäntää, ennen kuin yritetään lainkaan
_WD_MIN_PER_DAY = 3             # min. havaintoa kohdeviikonpäivälle
_WD_MAX_ADJ = 0.008             # turvaraja ±0.8 snt/L (kaksi kertaa prior)


def _empirical_weekday_adj(dates, prices,
                           tomorrow_weekday: int) -> tuple[float | None, int]:
    """Empiirinen viikonpäivä-adjustment huomiselle.

    Lähestymistapa:
      1) Ota aito päivähäntä (max_gap=3, min_len suuri).
      2) Vähennä jokaisesta hinnasta sen 7-päivän keskittävä rolling-mean
         → "lokaalisti keskistetty" jäännös (paikallinen trendi poistettu).
      3) Keskimäärin per viikonpäivä → kunkin viikonpäivän systemaattinen
         poikkeama.
      4) Palauta huomisen viikonpäivän mean, rajattu ±_WD_MAX_ADJ.

    Palauttaa (adj, n_samples_for_tomorrow_wd). Jos data ei riitä → (None, 0).
    """
    dt = _daily_tail(dates, prices, max_gap=3, min_len=_WD_MIN_TOTAL)
    if len(dt) < _WD_MIN_TOTAL:
        return None, 0
    try:
        parsed = [(_parse_date(d), float(p)) for d, p in dt]
    except Exception:
        return None, 0

    # Pyhä- ja aattopäivät pois viikonpäiväjakaumista — esim. helatorstai
    # ei saa saastuttaa "torstain" systemaattista poikkeamaa.
    parsed = [(d, p) for d, p in parsed if not fi_holidays.is_special(d)]
    if len(parsed) < _WD_MIN_TOTAL:
        return None, 0

    # 7-pv keskittävä rolling mean — jättää reunoille ohuemman ikkunan
    n = len(parsed)
    prices_arr = np.array([p for _, p in parsed], dtype=float)
    half = 3  # ±3 → ikkunan koko 7 sisällä rajojen
    smoothed = np.empty(n, dtype=float)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        smoothed[i] = prices_arr[lo:hi].mean()
    residuals = prices_arr - smoothed

    by_wd: dict[int, list[float]] = {}
    for (d, _), r in zip(parsed, residuals):
        by_wd.setdefault(d.weekday(), []).append(float(r))

    samples = by_wd.get(int(tomorrow_weekday), [])
    if len(samples) < _WD_MIN_PER_DAY:
        return None, len(samples)

    adj = float(np.mean(samples))
    adj = max(-_WD_MAX_ADJ, min(_WD_MAX_ADJ, adj))
    return adj, len(samples)


def _bias_correction(stats: dict | None, method: str) -> float:
    """Palauta menetelmäkohtainen bias-korjaus (€/L), joka VÄHENNETÄÄN
    raakaennusteesta. Konservatiivinen: korjauksen suuruus skaalautuu
    näytemäärällä, ja se on aina rajattu ±_BIAS_MAX:n sisään."""
    if not stats:
        return 0.0
    rec = stats.get(method) or {}
    n = int(rec.get("n") or 0)
    bias = rec.get("bias")
    if n < _BIAS_MIN_N or bias is None:
        return 0.0
    try:
        bias = float(bias)
    except (TypeError, ValueError):
        return 0.0
    lam = min(1.0, n / float(_BIAS_FULL_N))
    corr = -lam * bias  # positiivinen bias → vähennetään
    return max(-_BIAS_MAX, min(_BIAS_MAX, corr))
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


def linear_regression(prices: list[float], lookback: int = 30, dates=None,
                      track_stats: dict | None = None) -> dict:
    """Recency-painotettu pienimmän neliösumman trendi, x = KALENTERIPÄIVÄ-
    offset, projisointi +1 pv.

    Day-ahead-viritykset (priorit, ks. _LR_*-vakiot):
      - aidosta päivähännästä käytetään enintään _LR_MAX_WINDOW tuoreinta
        pistettä — vanha hintaregiimi ei saa vetää huomisen trendiä
      - havainnot painotetaan eksponentiaalisesti tuoreuden mukaan
        (puoliintumisaika _LR_HALFLIFE_DAYS pv)
      - self-training: menetelmän toteutunut signed bias vähennetään
        (sama _bias_correction-mekanismi kuin fundamental_anchorissa)
      - tulos rajataan ±_MAX_DAILY_MOVE viimeisestä havainnosta — trendin
        ekstrapolointi ei saa ylittää fysikaalista päivämuutosbudjettia

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
            dt = dt[-_LR_MAX_WINDOW:]
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

    # Eksponentiaalinen recency-paino; np.polyfit painottaa residuaalia
    # kertoimella w ennen neliöintiä → sqrt(paino) antaa halutun WLS:n.
    age = x[-1] - x
    wts = np.power(0.5, age / _LR_HALFLIFE_DAYS)
    slope, intercept = np.polyfit(x, y, 1, w=np.sqrt(wts))
    pred = float(slope * target_x + intercept)
    residuals = y - (slope * x + intercept)
    sigma = max(float(np.sqrt(np.average(residuals ** 2, weights=wts))), 0.005)

    parts: list[str] = []
    bias_adj = _bias_correction(track_stats, "linear_regression")
    if abs(bias_adj) >= 0.0005:
        pred += bias_adj
        parts.append(f"itsekalibrointi {bias_adj*1000:+.1f} m€/L")

    last = float(y[-1])
    clamped = not (last - _MAX_DAILY_MOVE <= pred <= last + _MAX_DAILY_MOVE)
    if clamped:
        pred = max(last - _MAX_DAILY_MOVE, min(last + _MAX_DAILY_MOVE, pred))
        parts.append(f"rajattu ±{_MAX_DAILY_MOVE*100:.0f} snt viime havainnosta")

    direction = "nouseva" if slope > 0 else ("laskeva" if slope < 0 else "tasainen")
    expl = (f"Painotettu lineaarinen regressio {len(y)} pisteestä "
            f"(½-aika {_LR_HALFLIFE_DAYS:g} pv), trendi {direction} "
            f"({slope*1000:+.2f} m€/L/pv)")
    if parts:
        expl += " · " + ", ".join(parts)
    return {
        "value": round(pred, 4),
        "confidence_low": round(pred - 1.5 * sigma, 4),
        "confidence_high": round(pred + 1.5 * sigma, 4),
        "slope": round(float(slope), 6),
        "explanation": expl + ".",
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
    
    # Safety check: ensure seg has at least 2 elements
    if len(seg) < 2:
        return {"value": None, "confidence_low": None, "confidence_high": None,
                "explanation": "Liian vähän dataa eksponentiaaliseen tasoitukseen."}
    
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
                       tomorrow_weekday: int, conflict: bool = False,
                       product_usd_gal: float | None = None,
                       product_chg: float | None = None,
                       product_label: str | None = None,
                       tax_step_eur_l: float | None = None,
                       track_stats: dict | None = None,
                       tomorrow_date_iso: str | None = None) -> dict:
    """Fysikaalisesti motivoitu day-ahead-malli:

        ennuste = live-ankkuri
                + JALOSTETUN TUOTTEEN EUR/L-pass-through  (ensisijainen)
                  TAI Brent-pass-through                  (fallback)
                + EUR/USD-vaikutus
                + päivätason momentum (aito päivähäntä)
                + viikonpäiväefekti
                + tunnettu veroaskel (jos voimaan huomenna)

    Refined-tuote (RBOB/HO) on day-ahead-ennusteelle olennaisesti parempi
    syöte kuin Brent: Brent → pumppu -viive on 1–2 viikkoa, refined → pumppu
    on 3–7 päivää. Käytetään pääsignaalina kun saatavilla.

    Tulos rajataan ±0.06 €/L live-hinnasta — clamppia laajennetaan
    tunnetun verostepin verran kun se astuu voimaan."""
    p = _safe_prices(prices)
    base_live = live_anchor if live_anchor is not None else (p[-1] if p else None)
    if base_live is None:
        return {"value": None, "confidence_low": None, "confidence_high": None,
                "explanation": "Ei live-ankkuria fundamentaalimalliin."}

    parts: list[str] = []
    dt = _daily_tail(dates, prices, max_gap=3, min_len=4)

    # 0) kohinanvaimennettu ankkuri: yksittäinen "halvin Suomessa" -scrape
    # on kohinainen (asemajoukko vaihtelee päivittäin) → sekoita live-hinta
    # kevyesti 3 pv mediaaniin (_ANCHOR_LIVE_W on prior, ei mitattu).
    base = base_live
    if len(dt) >= 3:
        med3 = float(np.median([x[1] for x in dt[-3:]]))
        base = _ANCHOR_LIVE_W * base_live + (1.0 - _ANCHOR_LIVE_W) * med3
        if abs(base - base_live) >= 0.0005:
            parts.append(f"kohinanvaimennus {(base - base_live)*1000:+.1f} m€/L")

    # 1) Pass-through — refined-tuote ensisijainen, Brent fallback.
    # Käytetään moduulitason ENNALTA VALITTUJA priorikertoimia
    # (_REFINED_PASSTHROUGH_FRAC, _BRENT_PASSTHROUGH_FRAC). Niitä EI ole
    # mitattu Suomi-spesifisellä regressiolla; ne ovat alkupriorit, jotka
    # kalibroidaan kun daily_tracker-captureita on tarpeeksi.
    crude_adj = 0.0
    if (product_usd_gal is not None and product_chg is not None
            and eur_usd not in (None, 0)):
        prod_eur_l = (product_usd_gal / _GAL_LITRES) / eur_usd
        d_prod = prod_eur_l * product_chg
        d_fx = (-prod_eur_l * eur_usd_chg) if eur_usd_chg is not None else 0.0
        crude_adj = _REFINED_PASSTHROUGH_FRAC * (d_prod + d_fx)
        crude_adj = max(-0.035, min(0.035, crude_adj))
        if abs(crude_adj) >= 0.0005:
            tag = product_label or "refined"
            parts.append(f"{tag} {crude_adj*1000:+.1f} m€/L")
    elif brent is not None and eur_usd not in (None, 0):
        # Brent EUR/L = (USD/bbl ÷ EURUSD) ÷ 159.
        brent_eur_l = (brent / eur_usd) / _BBL_LITRES
        d_crude = brent_eur_l * brent_chg if brent_chg is not None else 0.0
        # EUR heikkenee (eur_usd_chg < 0) → tuontiöljy kallistuu
        d_fx = (-brent_eur_l * eur_usd_chg) if eur_usd_chg is not None else 0.0
        crude_adj = _BRENT_PASSTHROUGH_FRAC * (d_crude + d_fx)
        crude_adj = max(-0.035, min(0.035, crude_adj))
        if abs(crude_adj) >= 0.0005:
            parts.append(f"Brent-EUR {crude_adj*1000:+.1f} m€/L")

    # 2) päivätason momentum AIDOSTA päivähännästä — slope ≤7 pisteestä on
    # kohinainen estimaatti, joten se kutistetaan kohti nollaa
    # (_MOM_SHRINK) ennen lisäämistä.
    mom_adj = 0.0
    if len(dt) >= 4:
        seg = [x[1] for x in dt][-7:]
        xs = np.arange(len(seg), dtype=float)
        slope = float(np.polyfit(xs, np.array(seg, float), 1)[0])
        mom_adj = max(-0.02, min(0.02, _MOM_SHRINK * slope))
        if abs(mom_adj) >= 0.0005:
            parts.append(f"momentum {mom_adj*1000:+.1f} m€/L")

    # 3) viikonpäivä-adj — empiirinen kun otosta riittää, muutoin prior.
    #    Empiirinen: kunkin viikonpäivän keskimääräinen poikkeama lokaalin
    #    7-pv-keskiarvon ympärillä, rajattu ±_WD_MAX_ADJ. Kun aito
    #    päivähäntä on liian lyhyt (<21 pv) tai huomisen viikonpäivälle on
    #    <3 havaintoa, palaudutaan kiinteään ±0.004 €/L -prioriin (heikko
    #    suunnatieto — tarkoitus EI ole olla mitattu Suomi-spesifinen).
    wd_adj = 0.0
    wd_source = None  # "empiirinen N" | "prior" | pyhäkalenteri
    holiday_profile = None
    if tomorrow_date_iso:
        try:
            holiday_profile = fi_holidays.demand_profile(_parse_date(tomorrow_date_iso))
        except Exception:
            holiday_profile = None
    if holiday_profile is not None:
        # Pyhäkalenteri ohittaa viikonpäivärytmin: pyhäpäivä käyttäytyy kuin
        # sunnuntai (matala kysyntä), aatto kuin perjantai (matka-/tankkaus-
        # päivä). Sama ±0.004 €/L -priorimagnitudi kuin viikonpäivpriorissa.
        kind, name = holiday_profile
        wd_adj = -0.004 if kind == "holiday" else 0.004
        wd_source = name
    else:
        emp_wd, emp_n = _empirical_weekday_adj(dates, prices, tomorrow_weekday)
        if emp_wd is not None:
            wd_adj = emp_wd
            wd_source = f"empiirinen n={emp_n}"
        else:
            if tomorrow_weekday in (1, 2):       # ti, ke
                wd_adj = 0.004
            elif tomorrow_weekday in (6, 0):     # su, ma
                wd_adj = -0.004
            if wd_adj:
                wd_source = "prior"
    if wd_adj:
        tag = f"viikonpäivä-{wd_source}" if wd_source else "viikonpäivä"
        parts.append(f"{tag} {wd_adj*1000:+.1f} m€/L")

    # 4) tunnettu veroaskel — astuu voimaan huomenna, joten kuuluu hintaan
    tax_adj = float(tax_step_eur_l or 0.0)
    if abs(tax_adj) >= 0.0001:
        parts.append(f"vero {tax_adj*1000:+.1f} m€/L")

    # 5) self-training: vähennä tämän menetelmän aiempi signed bias
    # (vain jos otosta on riittävästi — pieni n → korjaus = 0)
    bias_adj = _bias_correction(track_stats, "fundamental_anchor")
    if abs(bias_adj) >= 0.0005:
        parts.append(f"itsekalibrointi {bias_adj*1000:+.1f} m€/L")

    pred = base + crude_adj + mom_adj + wd_adj + tax_adj + bias_adj
    # Verostep on tunnettu eksogeeninen muutos → laajenna clamppia steppin
    # verran. Clamp pysyy live-hinnan ympärillä (ei vaimennetun ankkurin):
    # ±_MAX_DAILY_MOVE on määritelty suhteessa tämän päivän hintaan.
    clamp_band = _MAX_DAILY_MOVE + abs(tax_adj)
    pred = max(base_live - clamp_band, min(base_live + clamp_band, pred))

    # Luottamusväli — kalibroidaan toteutuneeseen RMSE:hen kun otosta on
    # riittävästi (band ≈ 1·σ, rajattu [_FA_BAND_MIN, _FA_BAND_MAX]).
    # Ilman otosta priorileveydet: 0.012 €/L = "tyypillinen pumpun
    # päivämuutos on tätä pienempi", 0.020 €/L = "konfliktissa leveämpi".
    band = 0.020 if conflict else 0.012
    fa_rec = (track_stats or {}).get("fundamental_anchor") or {}
    fa_rmse = fa_rec.get("rmse")
    if fa_rmse is not None and int(fa_rec.get("n") or 0) >= _BIAS_MIN_N:
        try:
            band = max(_FA_BAND_MIN, min(_FA_BAND_MAX, float(fa_rmse)))
            if conflict:
                band = max(band, 0.020)
        except (TypeError, ValueError):
            pass
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
                         eur_usd_chg: float | None = None,
                         product_usd_gal: float | None = None,
                         product_chg: float | None = None,
                         product_label: str | None = None,
                         crack_eur_l: float | None = None,
                         tax_events: list[dict] | None = None,
                         tax_step_eur_l: float | None = None,
                         track_record: dict | None = None) -> dict:
    """Claude Fable 5 -ennuste. Hoitaa ETUPAINOTTEISEN geopoliittisen riskin:
    konflikti-/tarjontahäiriöuutiset jotka Brent ei vielä täysin hinnoittele."""
    if not os.environ.get("ANTHROPIC_AUTH_TOKEN") and not os.environ.get("ANTHROPIC_API_KEY"):
        return {"value": None, "confidence_low": None, "confidence_high": None,
                "explanation": "ANTHROPIC_AUTH_TOKEN puuttuu - AI-ennustetta ei voi tehdä."}

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
        # Safety check: ensure seg has at least 1 element
        if len(seg) >= 1:
            slope_val = (seg[-1] - seg[0]) / max(1, len(seg) - 1) * 1000
            slope_str = f"{slope_val:+.2f} m€/L/pv (aito päivähäntä, {len(seg)} pv)"
        else:
            slope_str = "ei laskettavissa (tyhjä segmentti)"
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

    # Jalostettu tuoteputki (RBOB / HO) — day-ahead-ennusteen tärkein
    # syöte: refined → pumppu -viive on 3–7 pv vs. Brentin 1–2 viikkoa.
    if product_usd_gal is not None and eur_usd not in (None, 0):
        prod_eur_l = (product_usd_gal / _GAL_LITRES) / eur_usd
        prod_line = (f"{product_label or 'refined-tuote'}: "
                     f"{product_usd_gal:.3f} USD/gal "
                     f"(≈ {prod_eur_l:.3f} €/L tukkuna)")
        if product_chg is not None:
            prod_line += f" · ≈{product_chg*100:+.1f} % viim. ~5 pv"
    else:
        prod_line = (f"{product_label or 'refined-tuote'}: ei tiedossa "
                     "(fallback: Brent)")

    if crack_eur_l is not None:
        crack_line = (f"crack-spread (tuote − Brent): {crack_eur_l:+.3f} €/L "
                      "(vertaile suhteessa edellispäivien tasoon — ei "
                      "absoluuttisia kynnyksiä)")
    else:
        crack_line = "crack-spread: ei tiedossa"

    # Lag-piikit aidosta päivähännästä — exposeataan eksplisiittisesti
    # malli ei joudu päättelemään niitä karkeasta listasta
    lag_lines: list[str] = []
    if dt:
        # dt = [(date_iso, price), …] järjestyksessä vanhin → uusin
        by_date = {d: pr for d, pr in dt}
        ordered_dates = [d for d, _ in dt]
        last_date_iso = ordered_dates[-1]
        try:
            last_date = _parse_date(last_date_iso)
            for lag in _LAG_DAYS:
                from datetime import timedelta as _td
                target = (last_date - _td(days=lag)).isoformat()
                if target in by_date:
                    lag_lines.append(f"  t-{lag} ({target}): {by_date[target]:.3f} €/L")
                else:
                    # lähin pienempi tai yhtä suuri päivä, jos tarkka osuma ei löydy
                    candidates = [d for d in ordered_dates if d <= target]
                    if candidates:
                        nearest = candidates[-1]
                        lag_lines.append(
                            f"  t-{lag} (~{nearest}): {by_date[nearest]:.3f} €/L "
                            "(lähin saatavilla oleva)"
                        )
        except Exception:
            pass
    lag_block = ("\n".join(lag_lines) if lag_lines
                 else "  (ei vielä riittävää päivähäntää lag-piikkeihin)")

    # Tunnetut veromuutokset — eksogeeninen askel; mallin EI pidä
    # opettelematta huomata sitä historiasta.
    if tax_events:
        ev_lines = []
        for e in tax_events:
            d = float(e.get("delta_eur_per_l") or 0.0)
            sign = "+" if d >= 0 else ""
            ev_lines.append(
                f"  · {e.get('effective_date', '?')}: "
                f"{sign}{d*100:.2f} snt/L — {e.get('note', '')}"
            )
        tax_block = "\n".join(ev_lines)
    else:
        tax_block = "  (ei tunnettuja veromuutoksia tulossa)"

    if tax_step_eur_l and abs(tax_step_eur_l) >= 0.0001:
        tax_step_line = (
            f"\nHUOM: huomenna astuu voimaan {tax_step_eur_l*100:+.2f} snt/L "
            "veroaskel — sisällytä se ennusteeseen koko summaltaan."
        )
    else:
        tax_step_line = ""

    # Self-training: aiempien ennusteiden vs. toteumien track record.
    # Antaa AI:lle näkyvyyden omaan systemaattiseen vinoumaansa.
    if track_record and track_record.get("n_total"):
        tr_rows = track_record.get("rows") or []
        tr_stats = track_record.get("stats") or {}
        recent = tr_rows[-10:]  # näytetään max 10 viimeisintä päivää
        recent_lines = []
        for r in recent:
            ai_pred = r["methods"].get("ai_llm")
            ens_pred = r["methods"].get("ensemble")
            actual = r.get("actual")
            ai_part = (f" AI {ai_pred:.3f} (Δ {r['signed'].get('ai_llm', 0):+.3f})"
                       if ai_pred is not None else "")
            ens_part = (f" · ens {ens_pred:.3f} (Δ {r['signed'].get('ensemble', 0):+.3f})"
                        if ens_pred is not None else "")
            recent_lines.append(
                f"  {r['date']}: toteuma {actual:.3f}{ai_part}{ens_part}"
            )
        ai_stat = tr_stats.get("ai_llm") or {}
        ai_bias = ai_stat.get("bias")
        ai_n = ai_stat.get("n") or 0

        bias_lines = []
        for m_key, m_label in (
            ("ai_llm", "AI (oma)"),
            ("fundamental_anchor", "fundamental_anchor"),
            ("moving_average", "MA"),
            ("linear_regression", "LR"),
            ("exp_smoothing", "Holt"),
            ("ensemble", "ensemble"),
        ):
            s = tr_stats.get(m_key) or {}
            if (s.get("n") or 0) <= 0:
                continue
            b = s.get("bias")
            m = s.get("mae")
            # Näytä RAAKANUMEROT — älä laita kategorista verdiktiä, anna
            # AI:n itse arvioida onko bias merkityksellinen otoksen koossa.
            bias_lines.append(
                f"  {m_label}: n={s['n']}, MAE={m:.4f} €/L, "
                f"signed bias {b:+.4f} €/L"
            )

        # Oma rivi näytetään aina kun otosta on lainkaan — ei keinotekoista
        # kynnystä, jonka alapuolella malli ei näe biastaan lainkaan.
        if ai_bias is not None and ai_n > 0:
            own_hint = (
                f"\nOma track record: n={ai_n} vertailupäivää, "
                f"signed bias {ai_bias:+.4f} €/L ({ai_bias*100:+.2f} snt/L). "
                "Arvioi itse onko otos riittävä korjaukseen ja kuinka paljon "
                "biasta on syytä huomioida."
            )
        else:
            own_hint = ""

        recent_block = "\n".join(recent_lines) if recent_lines else "  (ei vertailtavia päiviä)"
        bias_block = "\n".join(bias_lines) if bias_lines else "  (ei riittävää otosta vielä)"
        track_section = (
            f"\n\n=== AIEMPI TARKKUUS (self-training, raakanumerot) ===\n"
            f"Viim. {len(recent)} vertailupäivää (toteuma vs. ennuste):\n"
            f"{recent_block}\n\n"
            f"Menetelmäkohtainen signed bias (n päivää, MAE, bias €/L):\n"
            f"{bias_block}"
            f"{own_hint}"
        )
    else:
        track_section = (
            "\n\n=== AIEMPI TARKKUUS (self-training) ===\n"
            "  (ei vielä riittävää historiaa — kerätään tästä päivästä alkaen)"
        )

    today_iso = datetime.now(timezone.utc).date().isoformat()
    wd = ["maanantai", "tiistai", "keskiviikko", "torstai",
          "perjantai", "lauantai", "sunnuntai"]
    weekday_fi = wd[datetime.now(timezone.utc).weekday()]
    tomorrow_weekday_fi = wd[(datetime.now(timezone.utc).weekday() + 1) % 7]

    # Pyhäkalenteri: tunnettu deterministinen kysyntäsignaali (vrt. verot)
    tomorrow_date = datetime.now(timezone.utc).date() + timedelta(days=1)
    cal_profile = fi_holidays.demand_profile(tomorrow_date)
    if cal_profile:
        kind, cal_name = cal_profile
        if kind == "holiday":
            cal_line = (f"Huomenna on {cal_name} (pyhäpäivä) — kysyntä ja "
                        "asematarjonta tyypillisesti matalia, kuten sunnuntaina.")
        else:
            cal_line = (f"Huomenna on {cal_name} — matkustus- ja "
                        "tankkauspäivä, kysyntä tyypillisesti koholla kuten "
                        "perjantaina.")
    else:
        cal_line = "Ei pyhä- tai aattopäiviä huomenna."

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
        "Olet kvantitatiivinen analyytikko, joka ennustaa Suomen "
        "vähittäispolttoaineen pumppuhintoja day-ahead-ikkunassa. "
        "Käytät seuraavia periaatteita — ne ovat alkupriorit, kalibroidaan "
        "havaintodatasta kun sitä kertyy:\n"
        "1. ANKKURI: Live-hinta on totuus. KAIKKI hintadata on tänä päivänä "
        "ja sen jälkeen live-skrapattua — ei vanhaa tilastohistoriaa. "
        "Ankkuroi ennuste aina tuoreimpaan live-hintaan.\n"
        "2. VEROT TUNNETTU ASKEL: polttoaineen verot (excise / ALV) ovat "
        "julkista tietoa ennen voimaantuloa — ÄLÄ yritä oppia niitä "
        "historiasta. Jos VEROMUUTOKSET-osio ilmoittaa huomenna voimaan "
        "tulevan stepin, lisää se SELLAISENAAN (ei pehmennystä). Ilman "
        "askelta päivämuutos on tyypillisesti pieni; rajaa ennuste "
        "konservatiivisesti.\n"
        "3. JALOSTETTU TUOTE = lähempänä pumppua: tukkutason RBOB / ULSD "
        "liikkuu yleensä ennen Brentin pumppuvaikutusta, koska Brent on "
        "raakaöljytaso ja viive pumppuun on pidempi. Käytä jalostettua "
        "tuotetta day-ahead-pääsignaalina; Brent on taustakonteksti. Jos "
        "refined puuttuu, fallback Brentiin pienemmällä painolla. Tarkkoja "
        "viivepäiviä ei tähän markkinaan ole mitattu — käytä suuntaa, älä "
        "lukkoa.\n"
        "4. CRACK-SPREAD (tuote − Brent EUR/L): suuntasignaali "
        "jalostusmarginaalille. Laajeneva crack → tukkupuoli vetää pumppua "
        "ylös vaikka Brent jäisi paikoilleen; kapeneva crack → vastaava "
        "puristus alas. Älä käytä mitään kynnysarvoja kategorisointiin — "
        "vertaile suhteessa viime päivien tasoon.\n"
        "5. EUR/USD: heikkenevä EUR (eur_usd_chg < 0) → tuontiöljy "
        "kallistuu euroissa → pumppupaine ylös. Vaikuttaa sekä Brentin että "
        "jalostetun tuotteen kautta.\n"
        "6. VIIKONPÄIVÄ-PRIOR (heikko): yleinen havainto on, että hinnat "
        "voivat hivuttua ylös arkiviikon aikana ja laskea viikonlopun "
        "vaihteessa, mutta tämä on heikko suuntaprior — Suomi-spesifisiä "
        "viikonpäiväkertoimia ei ole tähän mitattu. Anna tuoreen lag-datan "
        "(esp. t-7) ratkaista, älä kiinteiden snt-arvojen. Huominen on "
        + tomorrow_weekday_fi + ".\n"
        "7. LAG-PIIKIT: t-1 ja t-2 ovat parhaita lähihistoriallisia "
        "ankkureita; t-7 paljastaa viikonpäivärytmin EMPIIRISESTI. Käytä "
        "LAG-PIIKIT-osion arvoja suoraan, älä keskiarvoista niitä pois.\n"
        "8. MOMENTUM: aito päivätason kaltevuus on paras lyhytsignaali — "
        "älä taistele trendiä vastaan ilman katalyyttiä.\n"
        "9. GEOPOLITIIKKA: sodat, konfliktit, OPEC+-leikkaukset, saarrot ja "
        "pakotteet nostavat Brentiä → jalostettua tuotetta → pumppuhintaa. "
        "ÄLÄ tuplalaske jo Brentissä näkyvää riskiä; lisää preemio vain jos "
        "konflikti ESKALOITUU eikä ole vielä täysin hinnoiteltu. "
        "Epävarmuusväli kasvaa.\n"
        "Vastaat AINA pelkkänä JSON-objektina, ei muuta tekstiä."
    )

    prompt = (
        f"Ennusta {fuel}-pump-hinta huomiselle ({today_iso}, "
        f"{tomorrow_weekday_fi}) alueella {region}. Tänään {weekday_fi}.\n\n"
        f"=== HINTA-ANKKURI (pääankkuri) ===\nLive nyt: {live_line}\n\n"
        f"=== LAG-PIIKIT (eksplisiittiset viiveet aidosta päivähännästä) ===\n"
        f"{lag_block}\n\n"
        f"=== MOMENTUMSIGNAALI ===\n7 pv trendi: {slope_str}\n\n"
        f"=== KALENTERI (tunnettu, deterministinen) ===\n{cal_line}\n\n"
        f"=== LIVE-SKRAPATTU PÄIVÄHISTORIA (kerätty tästä päivästä alkaen) ===\n"
        f"{sample_lines}\n\n"
        f"=== DATALAATU ===\n{data_quality_note}\n\n"
        f"=== JALOSTETTU TUOTE (day-ahead-pääsignaali) ===\n{prod_line}\n"
        f"{crack_line}\n\n"
        f"=== MAKROINPUTTEJA (tausta) ===\nBrent: {brent_line}\n"
        f"EUR/USD: {fx_line}\n\n"
        f"=== VEROMUUTOKSET (tunnettuja eksogeenisia askeleita) ===\n"
        f"{tax_block}{tax_step_line}"
        f"{track_section}"
        f"{news_block}{geo_block}\n\n"
        f"=== TEHTÄVÄSI ===\n"
        f"1. Refined-tuotteen 5 pv muutos + crack-spread → arvioi tukkupaine "
        f"pumpulle huomenna. Jalostettu tuote on day-ahead-ikkunan "
        f"pääsignaali; tarkkaa Suomi-kohtaista pass-through-viivettä ei ole "
        f"mitattu, joten käytä suuntaa eikä kiinteää viivelukua. Jos "
        f"refined puuttuu, käytä Brentiä pienemmällä painolla.\n"
        f"2. Tarkista LAG-PIIKIT — onko viime päivinä jo nähty trendi joka "
        f"jatkuu? Käytä t-1 lähtötasona, t-7 viikonpäivärytmin tarkasteluun.\n"
        f"3. Huomioi viikonpäivä ({tomorrow_weekday_fi}) heikkona priorina, "
        f"mutta anna lag-datan ratkaista jos se on ristiriidassa.\n"
        f"4. Jos VEROMUUTOKSET-osio ilmoittaa askeleen huomenna → lisää se "
        f"sellaisenaan. Älä levitä sitä päivien yli.\n"
        f"5. Lisää geopoliittinen preemio VAIN jos eskaloituva, ei jo "
        f"hinnoiteltu riski.\n"
        f"6. SELF-CHECK: katso AIEMPI TARKKUUS -osio. Arvioi itse onko oma "
        f"signed bias merkityksellinen kyseisellä otoskoolla (n). Jos näet "
        f"selkeän systemaattisen vinouman, korjaa huomista vastaavasti, mutta "
        f"älä yliampu — korjaus enintään oman biasin suuruinen.\n"
        f"7. Ankkuroi tulos live-hintaan. Ilman veroaskelta tai selvää "
        f"katalyyttiä päivämuutos on yleensä pieni — vältä yliampumista.\n"
        f"8. Confidence-väli: kapeampi normaalitilassa, leveämpi konfliktissa "
        f"tai veromuutoksen voimaantulopäivänä. Numerot valitsee mallisi "
        f"havainnoista, ei kiinteistä taulukoista.\n\n"
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
        configured_model("claude-fable-5"),
        "claude-fable-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-sonnet-4-5-20250929",
        "claude-haiku-4-5-20251001",
    ]
    models_to_try = list(dict.fromkeys(models_to_try))

    last_err = "unknown error"
    for model in models_to_try:
        for attempt in range(3):
            try:
                text = await send_message(
                    system_message=system_message,
                    user_message=prompt,
                    model=model,
                    max_tokens=1200,
                    temperature=0.2,
                )

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
                # Fallback-leveys ±0.02 €/L on degeneraatiotapaus: vain jos
                # malli jätti CI-kentät pois palautuksesta. EI mitattu
                # kattavuus — luottamusväli on aina mallin oman raportoinnin
                # varassa kun se on saatavilla.
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
            except LLMConfigError as e:
                return {"value": None, "confidence_low": None, "confidence_high": None,
                        "explanation": str(e)}
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

# Itsekalibrointi: menetelmää aletaan painottaa sen TOTEUTUNEEN tarkkuuden
# mukaan vasta kun siitä on tarpeeksi aitoa osumavertailua; siirtymä
# kiinteistä painoista opittuihin on asteittainen (per menetelmä).
_CALIB_MIN_N = 5            # vähimmäismäärä toteumavertailuja ennen oppimista
_CALIB_TARGET_N = 20        # tällä otoksella luotetaan täysin opittuun painoon
_CALIB_MAE_FLOOR = 0.001    # estää 1/MAE-räjähdyksen kun MAE ≈ 0


def _calibrated_weights(fixed: dict, method_mae: dict | None):
    """Sekoita kiinteät regime-painot menetelmäkohtaiseen 1/MAE-painoon.

    `method_mae` = {menetelmä: {"n": int, "mae": float}} laskettuna AIDOISTA
    daily_tracker-captureista (ei synteettistä dataa). Menetelmälle joka ei
    vielä yllä `_CALIB_MIN_N`-otokseen käytetään sellaisenaan kiinteää painoa,
    joten funktio palautuu nykykäytökseen kunnes oikeaa osumadataa kertyy.
    Palauttaa (painot, selitysteksti)."""
    if not method_mae:
        return fixed, "kiinteät painot"

    inv = {}
    for m in fixed:
        rec = method_mae.get(m) or {}
        n = rec.get("n") or 0
        mae = rec.get("mae")
        if n >= _CALIB_MIN_N and mae is not None and mae > 0:
            inv[m] = (1.0 / max(float(mae), _CALIB_MAE_FLOOR), n)

    inv_sum = sum(w for w, _ in inv.values())
    if inv_sum <= 0:
        return fixed, "kiinteät painot (ei vielä tarpeeksi toteumia)"

    out = {}
    learned_n = 0
    for m, fw in fixed.items():
        if m in inv:
            learned_share = inv[m][0] / inv_sum
            lam = min(1.0, inv[m][1] / _CALIB_TARGET_N)  # otosluottamus
            out[m] = lam * learned_share + (1.0 - lam) * fw
            learned_n = max(learned_n, inv[m][1])
        else:
            out[m] = fw
    total = sum(out.values())
    if total > 0:
        out = {k: v / total for k, v in out.items()}
    return out, f"itsekalibroitu (toteutunut MAE, n={learned_n})"


def ensemble(predictions: dict, live_anchor: float | None = None,
             n_daily: int = 0, method_mae: dict | None = None,
             breaking_news_severity: int = 0) -> dict:
    """Datalaatutietoinen painotettu yhdistelmä.

    Kun aitoa päivädataa on vähän (kuukausidata hallitsee), tilastomenetelmät
    ylisovittavat → painotetaan ankkuripohjaista fundamental_anchoria ja AI:ta.
    `method_mae` (valinnainen): menetelmäkohtainen toteutunut MAE aidoista
    captureista → painot itsekalibroituvat tarkimpien menetelmien suuntaan.
    Lopputulos rajataan ±0.06 €/L live-hinnasta, paitsi jos `breaking_news_severity > 0`
    → clamp kerrotaan severity-perusteisella multiplikaattorilla (1.33x-2.50x)."""
    if n_daily >= 14:
        weights = {
            "fundamental_anchor": 0.28,
            "ai_llm": 0.20,
            "weekly_cycle": 0.15,
            "exp_smoothing": 0.16,
            "linear_regression": 0.12,
            "moving_average": 0.09,
        }
        mode = "riittävä päivädata"
    else:
        # ohut / kuukausivetoinen: luota ankkuriin + AI:hin
        weights = {
            "fundamental_anchor": 0.45,
            "ai_llm": 0.28,
            "weekly_cycle": 0.12,
            "moving_average": 0.08,
            "exp_smoothing": 0.05,
            "linear_regression": 0.02,
        }
        mode = "ohut päivädata → ankkuripainotus"

    weights, calib_note = _calibrated_weights(weights, method_mae)
    mode = f"{mode}, {calib_note}"

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
    clamp_multiplier = _breaking_news_multiplier(breaking_news_severity)
    if live_anchor is not None:
        clamp_limit = _MAX_DAILY_MOVE * clamp_multiplier
        lo, hi = live_anchor - clamp_limit, live_anchor + clamp_limit
        if weighted < lo or weighted > hi:
            weighted = max(lo, min(hi, weighted))
            clamped = True

    spread = max(v for v, _ in values) - min(v for v, _ in values)
    expl = f"{len(values)} menetelmää ({mode}), hajonta {spread:.4f} €/L"
    if clamped:
        if breaking_news_severity >= 7:
            limit_text = f"±{clamp_limit:.3f} €/L (CRITICAL severity={breaking_news_severity})"
        elif breaking_news_severity >= 4:
            limit_text = f"±{clamp_limit:.3f} €/L (MAJOR severity={breaking_news_severity})"
        elif breaking_news_severity >= 1:
            limit_text = f"±{clamp_limit:.3f} €/L (MODERATE severity={breaking_news_severity})"
        else:
            limit_text = "±0.06 €/L"
        expl += f" · rajattu {limit_text} live-hinnasta"
    return {
        "value": round(weighted, 4),
        "spread": round(spread, 4),
        "n_methods": len(values),
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "explanation": expl + ".",
        "breaking_news_severity": breaking_news_severity,
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
                           eur_usd_chg: float | None = None,
                           method_mae: dict | None = None,
                           product_usd_gal: float | None = None,
                           product_chg: float | None = None,
                           product_label: str | None = None,
                           crack_eur_l: float | None = None,
                           tax_events: list[dict] | None = None,
                           tax_step_eur_l: float | None = None,
                           track_record: dict | None = None,
                           breaking_news_severity: int = 0) -> dict:
    """Aja kaikki menetelmät ja palauta ennusteet + datalaatutietoinen ensemble.

    `brent_chg` / `eur_usd_chg` = murto-osamuutos (esim. 0.03 = +3 %) viim.
    ~5 pörssipäivältä; käytetään Brent-EUR-pass-throughiin (fallback).
    `product_usd_gal` / `product_chg` / `product_label` = jalostetun tuotteen
    (RBOB tai HO ULSD) viimeisin spot ja 5 pv muutos — ENSISIJAINEN day-ahead-
    pass-through; tarkempi kuin Brent. `crack_eur_l` = tuote − Brent EUR/L.
    `tax_events` = lista tunnetuista tulevista veromuutoksista (näytetään
    AI:lle). `tax_step_eur_l` = jos JOKIN niistä astuu voimaan huomenna,
    summa €/L → lisätään fundamental_anchoriin ja kerrotaan AI:lle.
    Jos live-hinta on annettu, se on ankkuri sekä historian viimeisenä
    pisteenä että ensemble-rajauksessa. `method_mae` = menetelmäkohtainen
    toteutunut MAE aidoista captureista → ensemble itsekalibroituu
    (None = kiinteät painot). `breaking_news_severity` = 0-10 severity score
    from news (0=none, 1-3=moderate, 4-6=major, 7-10=critical) → clamp multiplier."""
    if live_today_price is not None and prices:
        prices = list(prices)
        prices[-1] = float(live_today_price)

    tomorrow_weekday = (datetime.now(timezone.utc).weekday() + 1) % 7
    tomorrow_date_iso = (datetime.now(timezone.utc).date()
                         + timedelta(days=1)).isoformat()
    conflict = bool(_scan_conflict(news_headlines))
    n_daily = len(_daily_tail(dates, prices, max_gap=3, min_len=4))

    track_stats = (track_record or {}).get("stats")
    ma = moving_average(prices, 7, dates=dates)
    lr = linear_regression(prices, 30, dates=dates, track_stats=track_stats)
    es = exp_smoothing(prices, dates=dates)
    fa = fundamental_anchor(
        dates, prices, live_today_price, brent, eur_usd,
        brent_chg, eur_usd_chg, tomorrow_weekday, conflict=conflict,
        product_usd_gal=product_usd_gal, product_chg=product_chg,
        product_label=product_label, tax_step_eur_l=tax_step_eur_l,
        track_stats=track_stats, tomorrow_date_iso=tomorrow_date_iso,
    )
    ai = await ai_llm_predict(
        fuel, prices, dates, brent, eur_usd,
        live_today_price=live_today_price,
        news_headlines=news_headlines, region=region,
        brent_chg=brent_chg, eur_usd_chg=eur_usd_chg,
        product_usd_gal=product_usd_gal, product_chg=product_chg,
        product_label=product_label, crack_eur_l=crack_eur_l,
        tax_events=tax_events, tax_step_eur_l=tax_step_eur_l,
        track_record=track_record,
    )
    wc = wc_mod.weekly_cycle_predict(
        dates, prices,
        live_anchor=live_today_price,
        tomorrow_weekday=tomorrow_weekday,
    )

    predictions = {
        "moving_average": ma,
        "linear_regression": lr,
        "exp_smoothing": es,
        "fundamental_anchor": fa,
        "ai_llm": ai,
        "weekly_cycle": wc,
    }
    ens = ensemble(predictions, live_anchor=live_today_price, n_daily=n_daily,
                   method_mae=method_mae, breaking_news_severity=breaking_news_severity)
    return {
        "fuel": fuel,
        "region": region,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_price": round(_safe_prices(prices)[-1], 4) if _safe_prices(prices) else None,
        "live_anchor": live_today_price,
        "conflict_signal": conflict,
        "calendar_event": (
            {"kind": _prof[0], "name": _prof[1], "date": tomorrow_date_iso}
            if (_prof := fi_holidays.demand_profile(_parse_date(tomorrow_date_iso)))
            else None
        ),
        "n_daily_points": n_daily,
        "product_label": product_label,
        "product_usd_gal": product_usd_gal,
        "product_chg": product_chg,
        "crack_eur_l": crack_eur_l,
        "tax_events": tax_events or [],
        "tax_step_eur_l": tax_step_eur_l,
        "self_training": {
            "n_total": (track_record or {}).get("n_total", 0),
            "days_window": (track_record or {}).get("days_window"),
            "stats": track_stats or {},
        },
        "methods": predictions,
        "ensemble": ens,
    }

# ---------------- hourly predictions ----------------

def _hour_adjustment(hour: int, tomorrow_weekday: int) -> float:
    """Hour-of-day price adjustment (€/L).
    
    Uncalibrated prior based on general market observation:
    - Morning (6-10): slightly lower
    - Midday (11-15): baseline
    - Evening (16-21): slightly higher (commute demand)
    - Night (22-5): lower (fewer stations open)
    
    These are NOT Finland-measured coefficients — replace with data-calibrated
    values once hourly captures accumulate.
    """
    if 6 <= hour <= 10:
        return -0.003  # morning dip
    elif 16 <= hour <= 21:
        return +0.004  # evening peak
    elif 22 <= hour or hour <= 5:
        return -0.005  # night low
    else:
        return 0.0  # midday baseline


async def predict_by_hour(fuel: str,
                          dates: list[str],
                          prices: list[float],
                          target_hours: list[int],
                          brent: float | None,
                          eur_usd: float | None,
                          live_today_price: float | None = None,
                          news_headlines: list[dict] | None = None,
                          region: str = "Suomi",
                          brent_chg: float | None = None,
                          eur_usd_chg: float | None = None,
                          method_mae: dict | None = None,
                          product_usd_gal: float | None = None,
                          product_chg: float | None = None,
                          product_label: str | None = None,
                          crack_eur_l: float | None = None,
                          tax_events: list[dict] | None = None,
                          tax_step_eur_l: float | None = None,
                          track_record: dict | None = None,
                          breaking_news_severity: int = 0) -> dict:
    """Predict fuel price for specific hours of tomorrow.
    
    Returns:
    {
        "base_prediction": <predict_tomorrow result>,
        "hourly": {
            14: {"value": float, "confidence_low": float, "confidence_high": float},
            21: {"value": float, "confidence_low": float, "confidence_high": float},
        }
    }
    """
    # Get base day-ahead prediction
    base = await predict_tomorrow(
        fuel, dates, prices, brent, eur_usd,
        live_today_price=live_today_price,
        news_headlines=news_headlines,
        region=region,
        brent_chg=brent_chg,
        eur_usd_chg=eur_usd_chg,
        method_mae=method_mae,
        product_usd_gal=product_usd_gal,
        product_chg=product_chg,
        product_label=product_label,
        crack_eur_l=crack_eur_l,
        tax_events=tax_events,
        tax_step_eur_l=tax_step_eur_l,
        track_record=track_record,
        breaking_news_severity=breaking_news_severity,
    )
    
    base_value = base["ensemble"].get("value")
    if base_value is None:
        return {"base_prediction": base, "hourly": {}}
    
    tomorrow_weekday = (datetime.now(timezone.utc).weekday() + 1) % 7
    hourly = {}
    
    for hour in target_hours:
        adj = _hour_adjustment(hour, tomorrow_weekday)
        val = base_value + adj
        
        # Widen confidence interval slightly for hourly granularity
        base_low = base["ensemble"].get("confidence_low", val - 0.02)
        base_high = base["ensemble"].get("confidence_high", val + 0.02)
        spread = (base_high - base_low) / 2
        hourly_spread = spread * 1.15  # 15% wider for intra-day uncertainty
        
        # MongoDB requires string keys
        hourly[str(hour)] = {
            "value": round(val, 4),
            "confidence_low": round(val - hourly_spread, 4),
            "confidence_high": round(val + hourly_spread, 4),
            "hour_adjustment": round(adj, 4),
        }
    
    return {
        "base_prediction": base,
        "hourly": hourly,
    }


def find_best_window(hourly_predictions: dict, current_price: float | None = None) -> dict:
    """Find the hour with minimum predicted price.
    
    Args:
        hourly_predictions: {hour_str: {"value": float, ...}} (string keys from MongoDB)
        current_price: current live price for savings calculation
    
    Returns:
        {
            "best_hour": int,
            "best_price": float,
            "label_fi": str,  # "Aamulla" / "Iltapäivällä" / "Illalla"
            "savings_vs_now": float | None,  # €/L difference vs current
        }
    """
    if not hourly_predictions:
        return {
            "best_hour": None,
            "best_price": None,
            "label_fi": None,
            "savings_vs_now": None,
        }
    
    # Find hour with minimum value
    best_hour = None
    best_price = None
    for hour_key, pred in hourly_predictions.items():
        # Convert string key back to int for comparisons
        try:
            hour = int(hour_key)
        except (ValueError, TypeError):
            continue
        
        val = pred.get("value")
        if val is not None:
            if best_price is None or val < best_price:
                best_hour = hour
                best_price = val
    
    if best_hour is None:
        return {
            "best_hour": None,
            "best_price": None,
            "label_fi": None,
            "savings_vs_now": None,
        }
    
    # Finnish time label
    if 6 <= best_hour <= 11:
        label_fi = "Aamulla"
    elif 12 <= best_hour <= 17:
        label_fi = "Iltapäivällä"
    elif 18 <= best_hour <= 23:
        label_fi = "Illalla"
    else:
        label_fi = "Yöllä"
    
    savings = None
    if current_price is not None and best_price is not None:
        savings = current_price - best_price
    
    return {
        "best_hour": best_hour,
        "best_price": round(best_price, 4) if best_price else None,
        "label_fi": label_fi,
        "savings_vs_now": round(savings, 4) if savings is not None else None,
    }
