"""
Suomen pyhäpäiväkalenteri kysyntäprofiilia varten.

Pyhäpäivät ovat TUNNETTUA, deterministisesti laskettavaa tietoa (kuten
veromuutokset) — niitä ei kannata antaa mallin "oppia" ohuesta
päivähistoriasta. Tämä moduuli laskee Suomen viralliset pyhäpäivät
(kiinteät + pääsiäisestä johdetut + juhannus-/pyhäinpäiväsäännöt) ilman
verkkoa tai riippuvuuksia.

Käyttö ennusteputkessa:
  - aattopäivä (matkustus-/tankkauspäivä) → viikonpäiväpriorissa
    korkean kysynnän päivä (kuten perjantai)
  - pyhäpäivä → matalan kysynnän päivä (kuten sunnuntai)
  - empiirisestä viikonpäivämallista pyhä-/aattopäivät jätetään pois,
    jotta esim. helatorstai ei saastuta "torstain" jakaumaa

Profiilit ovat SUUNTAPRIOREJA samalla ±0.004 €/L -magnitudilla kuin
olemassa oleva viikonpäivprior — ei uusia mittaamattomia kertoimia.
"""
from __future__ import annotations
from datetime import date, timedelta
from functools import lru_cache


def easter_date(year: int) -> date:
    """Länsimainen pääsiäissunnuntai (Anonymous Gregorian / Meeus-algoritmi)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _saturday_from(start: date) -> date:
    d = start
    while d.weekday() != 5:  # lauantai
        d += timedelta(days=1)
    return d


@lru_cache(maxsize=16)
def holidays(year: int) -> dict[date, str]:
    """Suomen viralliset pyhäpäivät annetulle vuodelle: {pvm: nimi}."""
    easter = easter_date(year)
    juhannuspaiva = _saturday_from(date(year, 6, 20))      # la 20.–26.6.
    pyhainpaiva = _saturday_from(date(year, 10, 31))       # la 31.10.–6.11.
    return {
        date(year, 1, 1): "uudenvuodenpäivä",
        date(year, 1, 6): "loppiainen",
        easter - timedelta(days=2): "pitkäperjantai",
        easter: "pääsiäispäivä",
        easter + timedelta(days=1): "2. pääsiäispäivä",
        date(year, 5, 1): "vappu",
        easter + timedelta(days=39): "helatorstai",
        easter + timedelta(days=49): "helluntaipäivä",
        juhannuspaiva: "juhannuspäivä",
        pyhainpaiva: "pyhäinpäivä",
        date(year, 12, 6): "itsenäisyyspäivä",
        date(year, 12, 25): "joulupäivä",
        date(year, 12, 26): "tapaninpäivä",
    }


def holiday_name(d: date) -> str | None:
    """Pyhäpäivän nimi tai None."""
    return holidays(d.year).get(d)


def eve_name(d: date) -> str | None:
    """Aattopäivän nimi tai None.

    Aatto = korkean kysynnän matkustuspäivä: päivä juuri ennen pyhäpäivää,
    sekä de facto -aatot (juhannus- ja jouluaatto, uudenvuodenaatto).
    Pyhäpäivä itse ei ole aatto (esim. tapaninpäivä ennen välipäiviä)."""
    if holiday_name(d) is not None:
        return None
    if d.month == 12 and d.day == 31:
        return "uudenvuodenaatto"
    nxt = holiday_name(d + timedelta(days=1))
    if nxt is not None:
        if nxt == "juhannuspäivä":
            return "juhannusaatto"
        if nxt == "joulupäivä":
            return "jouluaatto"
        return f"{nxt}n aatto"
    return None


def demand_profile(d: date) -> tuple[str, str] | None:
    """Palauta (profiili, nimi) jos päivä poikkeaa normaalista viikkorytmistä.

    profiili: "holiday" (matala kysyntä, kuten sunnuntai)
              "holiday_eve" (korkea kysyntä, kuten perjantai)
    """
    name = holiday_name(d)
    if name is not None:
        return ("holiday", name)
    eve = eve_name(d)
    if eve is not None:
        return ("holiday_eve", eve)
    return None


def is_special(d: date) -> bool:
    """True jos pyhä- tai aattopäivä (käytetään empiirisen
    viikonpäivämallin suodatukseen)."""
    return demand_profile(d) is not None
