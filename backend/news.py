"""
Real-time Finnish fuel + oil news via direct publisher RSS feeds.

We pull from publishers directly (Iltalehti, Helsingin Sanomat, Ilta-Sanomat)
so links are canonical — no Google News opaque redirect tokens — and they
open the actual article when clicked.

We filter by fuel/oil keywords client-side.
"""
from __future__ import annotations
import re
import requests
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BensaVahti/2.0)"}
TIMEOUT = 12

# Lähde-feedit + kanavanimet näytettäväksi UI:ssa
FEEDS = [
    ("https://www.iltalehti.fi/rss/uutiset.xml", "Iltalehti"),
    ("https://www.iltalehti.fi/rss/talous.xml", "Iltalehti · Talous"),
    ("https://www.iltalehti.fi/rss/autot.xml", "Iltalehti · Autot"),
    ("https://www.iltalehti.fi/rss/kotimaa.xml", "Iltalehti · Kotimaa"),
    ("https://www.hs.fi/rss/tuoreimmat.xml", "Helsingin Sanomat"),
    ("https://www.hs.fi/rss/talous.xml", "HS · Talous"),
    ("https://www.is.fi/rss/tuoreimmat.xml", "Ilta-Sanomat"),
    ("https://www.is.fi/rss/taloussanomat.xml", "Taloussanomat"),
    ("https://www.is.fi/rss/autot.xml", "IS · Autot"),
    ("https://www.mtvuutiset.fi/api/feed/rss/uutiset_uusimmat", "MTV Uutiset"),
]

# Avainsanat: polttoaine, raakaöljy-hinta, vero, OPEC, Brent, asemaketjut
# (riittävän tiukka jotta ei matchaa esim. liikenneonnettomuus-uutisia)
KEYWORDS = re.compile(
    r"("
    r"polttoaine|"
    r"bensiini|bensii?nin|95E10|"
    r"\bdiesel|dieselin|dieselöljy|"
    r"raakaöljy|öljyn\s+hin|öljymarkkin|"
    r"polttoaineverot|valmistevero|"
    r"\bOPEC|\bBrent\b|"
    r"Neste\s+(Oil|Express|huoltoasem)|Teboil|huoltoasem|tankkau"
    r")",
    re.IGNORECASE,
)


def _parse_rss(xml_text: str, source_label: str) -> list[dict]:
    out = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return out
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = (it.findtext("description") or "").strip()
        pub_raw = (it.findtext("pubDate") or "").strip()
        try:
            pub_dt = parsedate_to_datetime(pub_raw).astimezone(timezone.utc)
        except Exception:
            pub_dt = None
        out.append({
            "title": title,
            "description": re.sub(r"<[^>]+>", "", desc)[:240],
            "link": link,
            "source": source_label,
            "published": pub_dt.isoformat() if pub_dt else None,
            "age_hours": (
                (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600.0
                if pub_dt else None
            ),
        })
    return out


def fetch_news(queries=None, max_age_days: int = 14, limit: int = 8) -> list[dict]:
    """queries argumentti säilytetty allekirjoituksen yhteensopivuuden vuoksi
    mutta filtteröinti tehdään aina KEYWORDS-patternilla."""
    all_items: list[dict] = []
    for url, label in FEEDS:
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            all_items.extend(_parse_rss(r.text, label))
        except Exception:
            continue

    cutoff_h = max_age_days * 24
    seen = set()
    matched = []
    for it in all_items:
        if it.get("age_hours") is None or it["age_hours"] > cutoff_h:
            continue
        # match VAIN otsikkoa vasten — kuvaukset usein matchaavat aiheeseen
        # vain väljästi (esim. "huoltoaseman lähellä kolari")
        if not KEYWORDS.search(it["title"]):
            continue
        key = it["title"][:80].lower()
        if key in seen:
            continue
        seen.add(key)
        matched.append(it)

    matched.sort(key=lambda x: x["age_hours"])
    return matched[:limit]
