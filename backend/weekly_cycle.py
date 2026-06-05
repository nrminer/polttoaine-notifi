"""
Viikoittaisen hinnoittelurytmin tunnistus ja ennustaminen.

Suomen polttoainehinnat seuraavat tyypillisesti viikkorytmiä:
  - Hinnat nousevat usein ti-ke (ennen viikonloppua)
  - Pysyvät vakaana ke-pe
  - Laskevat su-ma (viikonlopun jälkeen)

Tämä moduuli:
  1. Tunnistaa viikoittaiset hintahypyt historiasta
  2. Laskee keskimääräisen syklin pituuden
  3. Ennustaa seuraavan hypyn todennäköisen ajankohdan
  4. Palauttaa day-ahead-ennusteen syklivaiheen perusteella
"""
from __future__ import annotations
import math
from datetime import datetime, timedelta, date as date_t
from typing import Optional

import numpy as np


# Syklivaiheet (Finnish labels)
PHASE_BEFORE_JUMP = "ennen_nousua"  # ennen nousua
PHASE_JUMP = "nousu"                # nousu
PHASE_STABLE = "vakaa"              # vakaa
PHASE_DECLINE = "lasku"             # lasku

PHASE_LABELS_FI = {
    PHASE_BEFORE_JUMP: "Ennen nousua",
    PHASE_JUMP: "Nousu",
    PHASE_STABLE: "Vakaa",
    PHASE_DECLINE: "Lasku",
}

# Hypyn tunnistuskynnys (€/L päivässä)
JUMP_THRESHOLD = 0.010  # 1.0 snt/L nousu yhdessä päivässä

# Minimi päivähavaintojen määrä syklin tunnistukseen
MIN_DAILY_POINTS = 21  # 3 viikkoa


def _parse_date(s: str) -> date_t:
    """Parse ISO date string to date object."""
    return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()


def _daily_tail(dates, prices, max_gap: int = 3, min_len: int = 4) -> list[tuple[date_t, float]]:
    """Palauta perän (date, price) -parit päivätason jaksona."""
    pairs = []
    for d, p in zip(dates or [], prices or []):
        if p is not None and d:
            try:
                pairs.append((_parse_date(d), float(p)))
            except Exception:
                pass

    if len(pairs) < min_len:
        return []

    # Suodata peräkkäisyys
    tail = [pairs[-1]]
    for i in range(len(pairs) - 1, 0, -1):
        if (pairs[i][0] - pairs[i - 1][0]).days <= max_gap:
            tail.append(pairs[i - 1])
        else:
            break
    tail.reverse()
    return tail if len(tail) >= min_len else []


def detect_jumps(dates: list[str], prices: list[float]) -> list[dict]:
    """Tunnista hintahypyt historiasta.

    Palauttaa listan hyppy-tapahtumista:
    [
      {"date": "2026-06-03", "jump": 0.025, "weekday": 1},
      ...
    ]
    """
    dt = _daily_tail(dates, prices, max_gap=3, min_len=MIN_DAILY_POINTS)
    if len(dt) < MIN_DAILY_POINTS:
        return []

    jumps = []
    for i in range(1, len(dt)):
        prev_date, prev_price = dt[i - 1]
        curr_date, curr_price = dt[i]

        delta = curr_price - prev_price
        if delta >= JUMP_THRESHOLD:
            jumps.append({
                "date": curr_date.isoformat(),
                "jump": round(delta, 4),
                "weekday": curr_date.weekday(),
                "weekday_fi": ["ma", "ti", "ke", "to", "pe", "la", "su"][curr_date.weekday()],
            })

    return jumps


def cycle_statistics(jumps: list[dict]) -> dict:
    """Laske syklistatistiikka hypyistä.

    Palauttaa:
    {
      "detected": True/False,
      "n_jumps": int,
      "avg_cycle_days": float,
      "std_cycle_days": float,
      "common_weekday": int,
      "confidence": float,  # 0.0-1.0
    }
    """
    if len(jumps) < 2:
        return {
            "detected": False,
            "n_jumps": len(jumps),
            "avg_cycle_days": None,
            "std_cycle_days": None,
            "common_weekday": None,
            "confidence": 0.0,
        }

    # Laske hypypäivien välit
    jump_dates = [_parse_date(j["date"]) for j in jumps]
    intervals = [(jump_dates[i] - jump_dates[i - 1]).days for i in range(1, len(jump_dates))]

    if not intervals:
        return {
            "detected": False,
            "n_jumps": len(jumps),
            "avg_cycle_days": None,
            "std_cycle_days": None,
            "common_weekday": None,
            "confidence": 0.0,
        }

    avg_cycle = float(np.mean(intervals))
    std_cycle = float(np.std(intervals)) if len(intervals) > 1 else 0.0

    # Yleisimmän viikonpäivän laskenta
    weekdays = [j["weekday"] for j in jumps]
    weekday_counts = {}
    for wd in weekdays:
        weekday_counts[wd] = weekday_counts.get(wd, 0) + 1
    common_weekday = max(weekday_counts, key=weekday_counts.get) if weekday_counts else None

    # Luottamus: korkeampi jos sykli on säännöllinen (pieni std) ja hypyt keskittyvät tietylle viikonpäivälle
    weekday_concentration = weekday_counts.get(common_weekday, 0) / len(weekdays) if weekdays else 0.0
    regularity = max(0.0, 1.0 - std_cycle / max(avg_cycle, 1.0))  # pienempi std → korkeampi regularity
    confidence = min(1.0, (weekday_concentration + regularity) / 2.0 * (len(jumps) / 5.0))  # 5 hypyt → täysi luottamus

    detected = (
        len(jumps) >= 3
        and 5.0 <= avg_cycle <= 9.0  # viikkorytmi (5-9 pv)
        and std_cycle < 3.0           # säännöllinen
        and confidence >= 0.4
    )

    return {
        "detected": detected,
        "n_jumps": len(jumps),
        "avg_cycle_days": round(avg_cycle, 1),
        "std_cycle_days": round(std_cycle, 1),
        "common_weekday": common_weekday,
        "confidence": round(confidence, 2),
    }


def current_phase(dates: list[str], prices: list[float], today: Optional[date_t] = None) -> dict:
    """Määritä nykyinen syklivaihe.

    Palauttaa:
    {
      "phase": "ennen_nousua" | "nousu" | "vakaa" | "lasku",
      "phase_fi": "Ennen nousua" | ...,
      "days_since_last_jump": int,
      "next_jump_estimate_days": int | None,
      "next_jump_date": "YYYY-MM-DD" | None,
    }
    """
    if today is None:
        today = datetime.now().date()

    jumps = detect_jumps(dates, prices)
    stats = cycle_statistics(jumps)

    if not jumps or not stats["detected"]:
        return {
            "phase": None,
            "phase_fi": "Tuntematon",
            "days_since_last_jump": None,
            "next_jump_estimate_days": None,
            "next_jump_date": None,
            "confidence": 0.0,
        }

    # Viimeisin hyppy
    last_jump_date = _parse_date(jumps[-1]["date"])
    days_since = (today - last_jump_date).days

    # Ennustettu seuraava hyppy
    avg_cycle = stats["avg_cycle_days"]
    next_jump_estimate_days = max(0, int(round(avg_cycle - days_since))) if avg_cycle else None
    next_jump_date = (today + timedelta(days=next_jump_estimate_days)).isoformat() if next_jump_estimate_days is not None else None

    # Vaihe päätellään sykliasemasta
    if avg_cycle:
        cycle_position = days_since / avg_cycle  # 0.0 = juuri hyppy, 1.0 = seuraava hyppy

        if cycle_position < 0.15:  # 0-1 pv hypyn jälkeen
            phase = PHASE_JUMP
        elif cycle_position < 0.5:  # 1-3.5 pv hypyn jälkeen (viikolla ~7pv → 0-3.5pv)
            phase = PHASE_STABLE
        elif cycle_position < 0.85:  # 3.5-6 pv hypyn jälkeen
            phase = PHASE_DECLINE
        else:  # >6 pv hypyn jälkeen
            phase = PHASE_BEFORE_JUMP
    else:
        phase = None

    return {
        "phase": phase,
        "phase_fi": PHASE_LABELS_FI.get(phase, "Tuntematon"),
        "days_since_last_jump": days_since,
        "next_jump_estimate_days": next_jump_estimate_days,
        "next_jump_date": next_jump_date,
        "confidence": stats["confidence"],
    }


def weekly_cycle_predict(dates: list[str], prices: list[float],
                        live_anchor: Optional[float] = None,
                        tomorrow_weekday: Optional[int] = None) -> dict:
    """Ennusta huomisen hinta syklivaiheen perusteella.

    Palauttaa:
    {
      "value": float | None,
      "confidence_low": float | None,
      "confidence_high": float | None,
      "explanation": str,
      "cycle_stats": dict,
      "current_phase": dict,
    }
    """
    dt = _daily_tail(dates, prices, max_gap=3, min_len=MIN_DAILY_POINTS)

    if len(dt) < MIN_DAILY_POINTS:
        return {
            "value": None,
            "confidence_low": None,
            "confidence_high": None,
            "explanation": f"Liian vähän päivädataa syklin tunnistukseen (tarvitaan {MIN_DAILY_POINTS}, saatavilla {len(dt)}).",
            "cycle_stats": {"detected": False},
            "current_phase": {"phase": None, "phase_fi": "Tuntematon"},
        }

    jumps = detect_jumps(dates, prices)
    stats = cycle_statistics(jumps)
    phase_info = current_phase(dates, prices)

    if not stats["detected"]:
        return {
            "value": None,
            "confidence_low": None,
            "confidence_high": None,
            "explanation": f"Viikkosykliä ei tunnistettu (hypyt: {stats['n_jumps']}, luottamus {stats['confidence']:.0%}).",
            "cycle_stats": stats,
            "current_phase": phase_info,
        }

    # Baseline = viimeisin hinta tai live-ankkuri
    if live_anchor is not None:
        base = live_anchor
    else:
        base = dt[-1][1]

    # Ennuste riippuu vaiheesta
    phase = phase_info["phase"]
    days_to_next = phase_info.get("next_jump_estimate_days", 999)

    if phase == PHASE_BEFORE_JUMP and days_to_next <= 1:
        # Hyppy todennäköisesti huomenna
        avg_jump = np.mean([j["jump"] for j in jumps[-3:]])  # viim. 3 hypyn keskiarvo
        pred = base + avg_jump
        expl = f"Sykli ennen nousua, hyppy odotettu {days_to_next} pv sisällä. Ennuste: +{avg_jump*1000:.1f} m€/L."
        band = 0.015
    elif phase == PHASE_JUMP:
        # Hyppy juuri tapahtunut, vakaa
        pred = base
        expl = "Sykli: nousu juuri tapahtunut, hinta vakaa."
        band = 0.008
    elif phase == PHASE_STABLE:
        # Vakaa vaihe
        pred = base
        expl = "Sykli: vakaa vaihe, ei suuria muutoksia."
        band = 0.008
    elif phase == PHASE_DECLINE:
        # Laskuvaihe
        if jumps:
            avg_jump = np.mean([j["jump"] for j in jumps[-3:]])
            decline_rate = -avg_jump / (stats["avg_cycle_days"] * 0.5)  # jakautuu laskuvaiheelle
            pred = base + decline_rate
            expl = f"Sykli: laskuvaihe, odotettu muutos {decline_rate*1000:+.1f} m€/L."
            band = 0.012
        else:
            pred = base
            expl = "Sykli: laskuvaihe, mutta ei riittävästi hypydataa."
            band = 0.012
    else:
        # Tuntematon vaihe
        pred = base
        expl = "Syklivaihe epäselvä, ennuste = nykyinen hinta."
        band = 0.015

    return {
        "value": round(pred, 4),
        "confidence_low": round(pred - band, 4),
        "confidence_high": round(pred + band, 4),
        "explanation": expl,
        "cycle_stats": stats,
        "current_phase": phase_info,
    }
