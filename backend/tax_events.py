"""
Tunnetut polttoaineverojen / ALV:n muutokset Suomessa.

Veromuutokset ovat AINA julkista tietoa hyvissä ajoin ennen voimaantuloa
(Verohallinnon ja VM:n tiedotteet). Niitä ei kannata antaa mallin "oppia"
historiasta — ne ovat tunnettuja askeltapahtumia.

Tämä moduuli pitää listaa tulevista ja äsken voimaantulleista muutoksista,
ja antaa predict-putken laskea oikean askelmuutoksen huomenna voimaan-
tulevasta verosta.

YLLÄPITO: lisää uudet rivit `_EVENTS`-listaan VM:n / Verohallinnon
ilmoituksen perusteella. Päiväys on muutoksen voimaantulopäivä;
`delta_eur_per_l` on bruttomuutos EUROINA/litra desimaalina
(0.025 = 2,5 snt/L; positiivinen = veron korotus → pumppuhinta nousee).
`note` on lyhyt suomenkielinen kuvaus.

Esimerkki — ei voimassaolevia tapahtumia syötetty oletuksena:
    {
        "effective_date": "2026-08-01",
        "fuels": ("95E10", "diesel"),
        "delta_eur_per_l": 0.025,   # = 2,5 snt/L
        "note": "Polttoaineverotuksen korotus +2,5 snt/L (HE 14/2026)",
    }
"""
from __future__ import annotations
from datetime import date
from typing import Iterable


_EVENTS: list[dict] = [
    # Lisää tähän tunnetut tulevat tai juuri voimaantulleet muutokset
    # alla olevan kaavan mukaisesti. Tyhjä lista = ei vaikutusta.
]


def _parse(s: str) -> date:
    return date.fromisoformat(s[:10])


def applicable_step(fuel: str,
                    today_iso: str,
                    target_date_iso: str,
                    events: Iterable[dict] | None = None) -> dict | None:
    """Palauta { 'delta_eur_per_l': float, 'effective_date': str, 'note': str }
    jos JOKIN veromuutos osuu väliin (today, target_date] eli pumppuhinnan
    "ennen/jälkeen"-rajalle. Live-ankkuri on otettu ennen voimaantuloa, joten
    huomisen ennusteen on otettava verostep huomioon.

    Palauttaa None jos mikään tapahtuma ei osu väliin tälle polttoaineelle."""
    try:
        td = _parse(today_iso)
        tg = _parse(target_date_iso)
    except Exception:
        return None
    if tg <= td:
        return None

    src = list(events) if events is not None else _EVENTS
    total = 0.0
    last_note = None
    last_date = None
    for e in src:
        fuels = e.get("fuels") or ()
        if fuel not in fuels:
            continue
        try:
            eff = _parse(e["effective_date"])
        except Exception:
            continue
        # voimaan ennen huomista TAI tasan huomenna, ja edelleen tämän
        # päivän live-ankkurin jälkeen → askel kuuluu huomisen hintaan
        if td < eff <= tg:
            try:
                total += float(e.get("delta_eur_per_l") or 0.0)
                last_note = e.get("note") or last_note
                last_date = e.get("effective_date") or last_date
            except (TypeError, ValueError):
                continue

    if total == 0.0 and not last_note:
        return None
    return {
        "delta_eur_per_l": round(total, 5),
        "effective_date": last_date,
        "note": last_note or "veromuutos",
    }


def upcoming(today_iso: str,
             lookahead_days: int = 30,
             fuel: str | None = None) -> list[dict]:
    """Listaa tulevat veromuutokset ikkunassa (today, today+lookahead].
    Käytetään AI-promptin VEROMUUTOKSET-osioon."""
    try:
        td = _parse(today_iso)
    except Exception:
        return []
    from datetime import timedelta
    limit = td + timedelta(days=lookahead_days)
    out = []
    for e in _EVENTS:
        try:
            eff = _parse(e["effective_date"])
        except Exception:
            continue
        if not (td < eff <= limit):
            continue
        fuels = e.get("fuels") or ()
        if fuel and fuel not in fuels:
            continue
        out.append({
            "effective_date": e["effective_date"],
            "fuels": list(fuels),
            "delta_eur_per_l": float(e.get("delta_eur_per_l") or 0.0),
            "note": e.get("note") or "",
        })
    out.sort(key=lambda x: x["effective_date"])
    return out
